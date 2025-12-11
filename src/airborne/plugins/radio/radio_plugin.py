"""Radio communications plugin for AirBorne flight simulator.

Provides radio communication functionality including:
- COM/NAV frequency management
- ATC communications with realistic phraseology
- ATIS information broadcasts
- Push-to-talk mechanics

The plugin integrates:
- FrequencyManager: Radio tuning and frequency management
- ATCManager: Context-aware ATC communications
- ATISGenerator: Automatic terminal information service
- PhraseMaker: ICAO standard phraseology generation

Typical usage:
    The radio plugin is loaded automatically and provides radio services
    to other plugins and the main loop via messages and the component registry.
"""

from typing import Any

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType
from airborne.physics.vectors import Vector3
from airborne.plugins.radio.atc_manager import ATCController, ATCManager, ATCRequest, ATCType
from airborne.plugins.radio.atc_menu import ATCMenu
from airborne.plugins.radio.atc_queue import ATCMessageQueue
from airborne.plugins.radio.atc_v2 import ATCV2Controller
from airborne.plugins.radio.atis import ATISGenerator, ATISInfo
from airborne.plugins.radio.frequency_manager import FrequencyManager, RadioType
from airborne.plugins.radio.phraseology import PhraseMaker
from airborne.plugins.radio.readback import ATCReadbackSystem
from airborne.services.atc.intent_processor import FlightContext
from airborne.settings import get_atc_v2_settings
from airborne.ui.widgets.text_input_dialog import TextInputDialog

logger = get_logger(__name__)


class RadioPlugin(IPlugin):
    """Radio communications plugin.

    Manages radio frequencies, ATC communications, and ATIS broadcasts.
    Provides push-to-talk functionality and realistic radio phraseology.

    Components provided:
    - frequency_manager: FrequencyManager for radio tuning
    - atc_manager: ATCManager for ATC communications
    - atis_generator: ATISGenerator for ATIS broadcasts
    - phrase_maker: PhraseMaker for phraseology generation

    Messages published:
    - radio.transmission: When pilot transmits
    - radio.reception: When radio receives (ATC, ATIS)
    - radio.frequency_changed: When frequency is changed

    Messages subscribed:
    - position_updated: To update nearest ATC controller
    - input.radio_tune: To tune radios
    - input.push_to_talk: To transmit
    """

    def __init__(self) -> None:
        """Initialize radio plugin."""
        self.context: PluginContext | None = None
        self.frequency_manager = FrequencyManager()
        self.atc_manager = ATCManager()
        self.atis_generator = ATISGenerator()
        self.phrase_maker = PhraseMaker()

        # Interactive ATC systems (initialized later with dependencies)
        self.atc_queue: ATCMessageQueue | None = None
        self.atc_menu: ATCMenu | None = None
        self.readback_system: ATCReadbackSystem | None = None

        # ATC V2 voice control (optional)
        self.atc_v2_controller: ATCV2Controller | None = None
        self._atc_v2_text_dialog: TextInputDialog | None = None

        # Current state
        self._current_position: Vector3 | None = None
        self._current_altitude: int = 0
        self._current_heading: int = 0
        self._callsign: str = "Cessna 123AB"
        self._aircraft_type: str = "cessna172"  # Aircraft type for telephony
        self._current_atis: ATISInfo | None = None
        self._atis_text: str | None = None  # Generated ATIS text for TTS
        self._push_to_talk_pressed: bool = False
        self._selected_radio: RadioType = "COM1"
        self._engine_running: bool = False
        self._on_ground: bool = True

        # Weather and airport info
        self._weather_service: Any = None
        self._departure_airport: str = ""
        self._departure_airport_name: str = ""  # Human-readable airport name
        self._departure_runway: str = "31"  # Default, should be determined from wind
        self._arrival_airport: str = ""  # Destination airport
        self._arrival_airport_name: str = ""  # Human-readable destination name
        self._circuit_training: bool = False  # True if doing pattern work at single airport

        # TTS voice for ATC (if available)
        self._atc_voice_rate: int = 150  # Slightly faster than normal

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata.

        Returns:
            PluginMetadata describing this radio plugin.
        """
        return PluginMetadata(
            name="radio_plugin",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.AVIONICS,
            dependencies=["audio"],
            provides=["frequency_manager", "atc_manager", "atis_generator", "phrase_maker"],
            optional=False,
            update_priority=30,  # Update after physics
            requires_physics=False,
            description="Radio communications and ATC plugin",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the radio plugin.

        Args:
            context: Plugin context with access to core systems.
        """
        self.context = context
        logger.info("Radio plugin initializing...")

        # Get radio config
        radio_config = context.config.get("radio", {})
        self._callsign = radio_config.get("callsign", "Cessna 123AB")
        self._aircraft_type = radio_config.get("aircraft_type", "cessna172")
        self._departure_airport = radio_config.get("departure_airport", "KPAO")
        self._departure_airport_name = self._get_airport_name(self._departure_airport)
        self._weather_service = radio_config.get("weather_service")

        # Get flight plan info from scenario (source of truth)
        if hasattr(context, "scenario") and context.scenario is not None:
            scenario = context.scenario
            # Departure airport (scenario overrides config)
            if hasattr(scenario, "airport_icao") and scenario.airport_icao:
                self._departure_airport = scenario.airport_icao
                self._departure_airport_name = self._get_airport_name(self._departure_airport)
            # Arrival airport
            if hasattr(scenario, "arrival_icao") and scenario.arrival_icao:
                self._arrival_airport = scenario.arrival_icao
                self._arrival_airport_name = self._get_airport_name(self._arrival_airport)
            # Circuit training mode
            if hasattr(scenario, "circuit_training"):
                self._circuit_training = scenario.circuit_training

            logger.info(
                "Flight plan from scenario: %s -> %s%s",
                self._departure_airport,
                self._arrival_airport or "(circuit training)"
                if self._circuit_training
                else self._arrival_airport or "(no destination)",
                " [circuit training]" if self._circuit_training else "",
            )

        # Generate initial ATIS from weather
        self._generate_initial_atis()

        # Get TTS provider and audio manager from audio plugin
        tts_provider = None
        atc_audio_manager = None
        if context.plugin_registry:
            audio_plugin = context.plugin_registry.get("audio_plugin")
            if audio_plugin:
                tts_provider = getattr(audio_plugin, "tts_provider", None)
                atc_audio_manager = getattr(audio_plugin, "atc_audio_manager", None)

        # Initialize interactive ATC systems
        if atc_audio_manager and tts_provider:
            self.atc_queue = ATCMessageQueue(atc_audio_manager, min_delay=2.0, max_delay=10.0)
            self.atc_menu = ATCMenu(tts_provider, self.atc_queue, context.message_queue)
            self.readback_system = ATCReadbackSystem(
                self.atc_queue, tts_provider, callsign=self._callsign
            )

            # Set flight context for realistic phraseology
            # Get ATIS info letter (default to "Alpha" if not yet generated)
            atis_letter = "Alpha"
            if self._current_atis:
                atis_letter = self._current_atis.information_letter

            self.atc_menu.set_flight_context(
                callsign=self._callsign,
                aircraft_type=self._aircraft_type,
                airport_icao=self._departure_airport,
                airport_name=self._departure_airport_name,
                runway=self._departure_runway,
                parking_location="ramp",
                atis_info=atis_letter,
            )

            # Connect readback system to ATC menu for Shift+F1 functionality
            self.atc_menu.set_readback_system(self.readback_system)

            # Set V2 callback for ATC menu - sends pilot text to NLU after TTS plays
            def v2_callback(text: str) -> None:
                if self.atc_v2_controller:
                    self.atc_v2_controller.process_text_input(text)

            self.atc_menu.set_v2_callback(v2_callback)

            logger.info("Interactive ATC systems initialized with flight context")
        else:
            logger.warning("ATC audio manager or TTS not available - interactive ATC disabled")

        # Initialize ATC V2 voice control (if enabled in settings)
        self._initialize_atc_v2(context)

        # Subscribe to messages
        context.message_queue.subscribe("position_updated", self.handle_message)
        context.message_queue.subscribe("input.radio_tune", self.handle_message)
        context.message_queue.subscribe("input.push_to_talk", self.handle_message)
        context.message_queue.subscribe("input.atis_request", self.handle_message)
        context.message_queue.subscribe("airport.nearby", self.handle_message)
        context.message_queue.subscribe("input.atc_menu", self.handle_message)
        context.message_queue.subscribe("input.atc_acknowledge", self.handle_message)
        context.message_queue.subscribe("input.atc_repeat", self.handle_message)
        # ATC menu navigation (arrow keys when menu is open)
        context.message_queue.subscribe("input.menu_previous", self.handle_message)
        context.message_queue.subscribe("input.menu_next", self.handle_message)
        context.message_queue.subscribe("input.menu_select", self.handle_message)
        context.message_queue.subscribe("aircraft.state", self.handle_message)
        context.message_queue.subscribe("atc.request", self.handle_message)
        context.message_queue.subscribe("input.atc_v2_text_input", self.handle_message)

        # Register components
        if context.plugin_registry:
            context.plugin_registry.register("frequency_manager", self.frequency_manager)
            context.plugin_registry.register("atc_manager", self.atc_manager)
            context.plugin_registry.register("atis_generator", self.atis_generator)
            context.plugin_registry.register("phrase_maker", self.phrase_maker)
            if self.atc_queue:
                context.plugin_registry.register("atc_queue", self.atc_queue)
            if self.atc_menu:
                context.plugin_registry.register("atc_menu", self.atc_menu)
            if self.readback_system:
                context.plugin_registry.register("readback_system", self.readback_system)

        logger.info("Radio plugin initialized with callsign: %s", self._callsign)

    def update(self, dt: float) -> None:
        """Update radio plugin state.

        Args:
            dt: Delta time since last update in seconds.
        """
        # Process ATC message queue
        if self.atc_queue:
            self.atc_queue.process(dt)

        # Update ATC V2 controller
        if self.atc_v2_controller and self.atc_v2_controller.is_enabled():
            self.atc_v2_controller.update(dt)
            # Update flight context for V2
            self._update_v2_flight_context()

        # Check if we need to update ATIS (e.g., every 5 minutes in real implementation)
        # For now, we'll keep the current ATIS if it exists

    def shutdown(self) -> None:
        """Shutdown the radio plugin."""
        # Shutdown ATC V2 controller
        if self.atc_v2_controller:
            self.atc_v2_controller.shutdown()
            self.atc_v2_controller = None

        # Shutdown interactive ATC systems
        if self.atc_queue:
            self.atc_queue.shutdown()

        if self.context:
            self.context.message_queue.unsubscribe("position_updated", self)
            self.context.message_queue.unsubscribe("input.radio_tune", self)
            self.context.message_queue.unsubscribe("input.push_to_talk", self)
            self.context.message_queue.unsubscribe("input.atis_request", self)
            self.context.message_queue.unsubscribe("airport.nearby", self)
            self.context.message_queue.unsubscribe("input.atc_menu", self)
            self.context.message_queue.unsubscribe("input.atc_acknowledge", self)
            self.context.message_queue.unsubscribe("input.atc_repeat", self)
            self.context.message_queue.unsubscribe("aircraft.state", self)
            self.context.message_queue.unsubscribe("atc.request", self)
            self.context.message_queue.unsubscribe("input.atc_v2_text_input", self)

        logger.info("Radio plugin shutdown")

    def handle_message(self, message: Message) -> None:
        """Handle incoming messages.

        Args:
            message: The message to handle.
        """
        if not self.context:
            return

        if message.topic == "position_updated":
            self._handle_position_update(message)
        elif message.topic == "input.radio_tune":
            self._handle_radio_tune(message)
        elif message.topic == "input.push_to_talk":
            self._handle_push_to_talk(message)
        elif message.topic == "input.atis_request":
            self._handle_atis_request(message)
        elif message.topic == "airport.nearby":
            self._handle_nearby_airport(message)
        elif message.topic == "input.atc_menu":
            self._handle_atc_menu(message)
        elif message.topic == "input.atc_acknowledge":
            self._handle_atc_acknowledge(message)
        elif message.topic == "input.atc_repeat":
            self._handle_atc_repeat(message)
        elif message.topic == "input.menu_previous":
            self._handle_menu_previous(message)
        elif message.topic == "input.menu_next":
            self._handle_menu_next(message)
        elif message.topic == "input.menu_select":
            self._handle_menu_select(message)
        elif message.topic == "aircraft.state":
            self._handle_aircraft_state(message)
        elif message.topic == "atc.request":
            self._handle_atc_request(message)
        elif message.topic == "input.atc_v2_text_input":
            self._handle_atc_v2_text_input(message)

    def _handle_position_update(self, message: Message) -> None:
        """Handle position updates from physics plugin.

        Args:
            message: Position update message.
        """
        data = message.data
        self._current_position = Vector3(data.get("x", 0), data.get("y", 0), data.get("z", 0))
        self._current_altitude = int(data.get("altitude_ft", 0))
        self._current_heading = int(data.get("heading", 0))

    def _handle_radio_tune(self, message: Message) -> None:
        """Handle radio tuning input.

        Args:
            message: Radio tune message with action (up, down, swap).
        """
        data = message.data
        radio = data.get("radio", "COM1")
        action = data.get("action", "swap")
        which = data.get("which", "active")  # active or standby

        if radio not in ["COM1", "COM2", "NAV1", "NAV2"]:
            logger.warning("Invalid radio type: %s", radio)
            return

        if action == "swap":
            self.frequency_manager.swap(radio)
            logger.info(
                "%s frequencies swapped - Active: %.3f",
                radio,
                self.frequency_manager.get_active(radio),
            )
            self._announce_frequency_change(radio)
        elif action == "up":
            self.frequency_manager.increment_frequency(radio, which)
            logger.debug("%s %s frequency increased", radio, which)
            self._announce_frequency_change(radio)
        elif action == "down":
            self.frequency_manager.decrement_frequency(radio, which)
            logger.debug("%s %s frequency decreased", radio, which)
            self._announce_frequency_change(radio)

        # Publish frequency changed message
        if self.context:
            self.context.message_queue.publish(
                Message(
                    sender="radio_plugin",
                    recipients=["*"],
                    topic="radio.frequency_changed",
                    data={
                        "radio": radio,
                        "active": self.frequency_manager.get_active(radio),
                        "standby": self.frequency_manager.get_standby(radio),
                    },
                    priority=MessagePriority.NORMAL,
                )
            )

    def _handle_push_to_talk(self, message: Message) -> None:
        """Handle push-to-talk button.

        Args:
            message: PTT message with pressed state and request type.
        """
        data = message.data
        pressed = data.get("pressed", False)
        request_type = data.get("request_type", "taxi")

        # If V2 is enabled, route PTT to voice control
        if self.atc_v2_controller and self.atc_v2_controller.is_enabled():
            if pressed and not self._push_to_talk_pressed:
                self._push_to_talk_pressed = True
                self.atc_v2_controller.on_ptt_pressed()
            elif not pressed and self._push_to_talk_pressed:
                self._push_to_talk_pressed = False
                self.atc_v2_controller.on_ptt_released()
            return

        # Legacy menu-based PTT handling
        if pressed and not self._push_to_talk_pressed:
            # PTT pressed - transmit
            self._push_to_talk_pressed = True
            self._transmit_request(request_type, data)
        elif not pressed:
            self._push_to_talk_pressed = False

    def _handle_atis_request(self, _message: Message) -> None:
        """Handle ATIS playback request.

        Args:
            _message: ATIS request message (unused).
        """
        # Prefer pre-generated ATIS text (from weather)
        if self._atis_text:
            logger.info("Playing ATIS for %s", self._departure_airport)
            self._speak_atis(self._atis_text)
            self._mark_atis_received()
        elif self._current_atis:
            # Fallback to legacy ATISInfo-based generation
            atis_text = self.atis_generator.generate(self._current_atis)
            self._speak_atis(atis_text)
            self._mark_atis_received()
        else:
            logger.warning("No ATIS available - generating default")
            self._generate_default_atis()
            if self._atis_text:
                self._speak_atis(self._atis_text)
                self._mark_atis_received()

    def _mark_atis_received(self) -> None:
        """Mark ATIS as received in the ATC menu."""
        if self.atc_menu:
            # Get ATIS letter from current ATIS
            atis_letter = "Alpha"
            if self._current_atis:
                atis_letter = self._current_atis.information_letter
            self.atc_menu.mark_atis_received(atis_letter)
            logger.info(f"ATIS marked as received: information {atis_letter}")

    def _handle_nearby_airport(self, message: Message) -> None:
        """Handle nearby airport information.

        Args:
            message: Airport data message.
        """
        data = message.data
        airport_icao = data.get("icao", "")
        airport_name = data.get("name", "")
        active_runway = data.get("active_runway", "31")
        position_data = data.get("position", {})

        if not airport_icao or not self._current_position:
            return

        # Create or update ATC controllers for this airport
        airport_pos = Vector3(
            position_data.get("x", 0),
            position_data.get("y", 0),
            position_data.get("z", 0),
        )

        # Add Ground controller
        ground_controller = ATCController(
            type=ATCType.GROUND,
            airport_icao=airport_icao,
            airport_name=airport_name,
            frequency=121.7,  # Default ground frequency
            position=airport_pos,
            active_runway=active_runway,
        )
        self.atc_manager.add_controller(ground_controller)

        # Add Tower controller
        tower_controller = ATCController(
            type=ATCType.TOWER,
            airport_icao=airport_icao,
            airport_name=airport_name,
            frequency=118.0,  # Default tower frequency
            position=airport_pos,
            active_runway=active_runway,
        )
        self.atc_manager.add_controller(tower_controller)

        # Generate ATIS
        self._current_atis = self.atis_generator.create_default_atis(airport_name, active_runway)

        logger.info("ATC controllers and ATIS created for %s (%s)", airport_name, airport_icao)

    def _transmit_request(self, request_type: str, data: dict[str, Any]) -> None:
        """Transmit a request to ATC.

        Args:
            request_type: Type of request (taxi, takeoff, landing, etc.)
            data: Additional request data.
        """
        if not self.context or not self._current_position:
            return

        # Determine which controller to contact
        controller_type = self._get_controller_for_request(request_type)
        controller = self.atc_manager.get_controller(controller_type)

        if not controller:
            logger.warning("No %s controller available", controller_type.value)
            return

        # Build request
        request = ATCRequest(
            request_type=request_type,
            callsign=self._callsign,
            location=data.get("location", "parking"),
            atis_letter=self._current_atis.information_letter if self._current_atis else "Alpha",
            altitude=self._current_altitude,
            heading=self._current_heading,
        )

        try:
            # Get ATC response
            response = self.atc_manager.process_request(controller_type, request)

            # Speak the response with ATC voice
            self._speak_atc(response)

            logger.info("ATC %s: %s", controller_type.value, response)

        except ValueError as e:
            logger.error("ATC request failed: %s", e)

    def _get_controller_for_request(self, request_type: str) -> ATCType:
        """Determine which controller to contact for a request type.

        Args:
            request_type: Type of request.

        Returns:
            Appropriate ATCType for the request.
        """
        ground_requests = ["taxi", "pushback", "taxi_complete"]
        tower_requests = [
            "takeoff_ready",
            "landing_request",
            "pattern_entry",
            "airborne",
            "clear_runway",
        ]

        if request_type in ground_requests:
            return ATCType.GROUND
        elif request_type in tower_requests:
            return ATCType.TOWER
        else:
            return ATCType.TOWER  # Default to tower

    def _announce_frequency_change(self, radio: RadioType) -> None:
        """Announce frequency change via TTS.

        Args:
            radio: Radio that changed.
        """
        if not self.context:
            return

        active = self.frequency_manager.get_active(radio)
        standby = self.frequency_manager.get_standby(radio)

        announcement = f"{radio}, Active {active:.3f}, Standby {standby:.3f}"

        # Get TTS from audio plugin
        try:
            if self.context.plugin_registry:
                audio_plugin = self.context.plugin_registry.get("audio_plugin")
                if audio_plugin and hasattr(audio_plugin, "tts_provider"):
                    audio_plugin.tts_provider.speak(announcement, interrupt=False)
        except Exception as e:
            logger.warning("Failed to announce frequency: %s", e)

    def _speak_radio_text(self, text: str, voice: str = "tower", name: str = "radio") -> bool:
        """Speak text with radio effects using ATCAudioManager.

        This is the unified method for playing dynamically generated radio
        communications (ATIS, ATC responses) with realistic radio effects.

        Args:
            text: Text to speak.
            voice: Voice name for TTS (tower, atis, pilot, etc.).
            name: Name for logging purposes.

        Returns:
            True if played successfully with radio effects, False otherwise.

        Note:
            Uses ATCAudioManager to apply radio effects (static noise, DSP filter)
            to the dynamically generated TTS audio for realistic radio sound.
        """
        if not self.context or not self.context.plugin_registry:
            return False

        try:
            audio_plugin = self.context.plugin_registry.get("audio_plugin")
            if not audio_plugin:
                return False

            atc_audio_manager = getattr(audio_plugin, "atc_audio_manager", None)
            tts_provider = getattr(audio_plugin, "tts_provider", None)

            if not atc_audio_manager or not tts_provider:
                return False

            # Generate audio bytes using TTS
            if not hasattr(tts_provider, "_get_realtime_tts"):
                return False

            realtime_tts = tts_provider._get_realtime_tts(voice)
            if not realtime_tts:
                return False

            result = realtime_tts.generate_audio_bytes(text)
            if not result:
                return False

            audio_bytes, _ = result
            atc_audio_manager.play_dynamic_text(audio_bytes, volume=1.0, name=name)
            logger.info("%s played with radio effects", name)
            return True

        except Exception as e:
            logger.warning("Failed to speak %s: %s", name, e)
            return False

    def _speak_atc(self, text: str) -> None:
        """Speak ATC message with radio effects.

        Args:
            text: Text to speak.
        """
        if self._speak_radio_text(text, voice="tower", name="atc_message"):
            return

        # Fallback: use TTS directly without radio effects
        self._speak_fallback(text, voice="tower", interrupt=False)

    def _speak_atis(self, text: str) -> None:
        """Speak ATIS broadcast with radio effects.

        Args:
            text: ATIS text to speak.
        """
        if self._speak_radio_text(text, voice="atis", name="atis_broadcast"):
            return

        # Fallback: use TTS directly without radio effects
        self._speak_fallback(text, voice="atis", interrupt=True)

    def _speak_fallback(self, text: str, voice: str, interrupt: bool) -> None:
        """Fallback TTS playback without radio effects.

        Args:
            text: Text to speak.
            voice: Voice name.
            interrupt: Whether to interrupt current speech.
        """
        if not self.context or not self.context.plugin_registry:
            return

        try:
            audio_plugin = self.context.plugin_registry.get("audio_plugin")
            if not audio_plugin:
                return

            tts_provider = getattr(audio_plugin, "tts_provider", None)
            if tts_provider and hasattr(tts_provider, "speak_text"):
                tts_provider.speak_text(text, voice=voice, interrupt=interrupt)
                logger.info("%s played without radio effects (fallback)", voice)
            elif tts_provider:
                tts_provider.speak(text, interrupt=interrupt)
        except Exception as e:
            logger.warning("Fallback TTS failed: %s", e)

    def _generate_initial_atis(self) -> None:
        """Generate initial ATIS from weather service.

        Gets weather from weather_service (real METAR if available, simulated otherwise)
        and generates ATIS text for the departure airport.
        """
        if not self._weather_service:
            logger.warning("No weather service available - using default ATIS")
            self._generate_default_atis()
            return

        try:
            # Wait briefly for background METAR fetch to complete (max 3 seconds)
            if hasattr(self._weather_service, "wait_for_prefetch"):
                if self._weather_service.wait_for_prefetch(self._departure_airport, timeout=3.0):
                    logger.info("METAR prefetch completed for %s", self._departure_airport)
                else:
                    logger.debug("METAR prefetch timed out, using available data")

            # Get weather (sync version - uses cache from background prefetch)
            weather = self._weather_service.get_weather_sync(self._departure_airport)

            # Get airport name - for now use a simple lookup, can expand later
            airport_name = self._get_airport_name(self._departure_airport)

            # Determine active runway from wind direction
            active_runway = self._determine_active_runway(weather.wind.direction)

            # Generate ATIS text from weather
            self._atis_text = self.atis_generator.generate_from_weather(
                airport_name=airport_name,
                airport_icao=self._departure_airport,
                active_runway=active_runway,
                weather=weather,
            )
            self._departure_runway = active_runway

            logger.info(
                "ATIS generated for %s (runway %s, %s)",
                self._departure_airport,
                active_runway,
                "real METAR" if not weather.is_simulated else "simulated",
            )

        except Exception as e:
            logger.warning("Failed to generate ATIS from weather: %s", e)
            self._generate_default_atis()

    def _generate_default_atis(self) -> None:
        """Generate default ATIS when weather is unavailable."""
        airport_name = self._get_airport_name(self._departure_airport)
        atis_info = self.atis_generator.create_default_atis(
            airport_name=airport_name,
            active_runway=self._departure_runway,
        )
        self._current_atis = atis_info
        self._atis_text = self.atis_generator.generate(atis_info)
        logger.info("Default ATIS generated for %s", self._departure_airport)

    def _get_airport_name(self, icao: str) -> str:
        """Get airport name from ICAO code.

        Args:
            icao: Airport ICAO code.

        Returns:
            Human-readable airport name.
        """
        # Common airports - can be expanded or loaded from database
        airport_names = {
            "KPAO": "Palo Alto Airport",
            "KSFO": "San Francisco International",
            "KSJC": "San Jose International",
            "KOAK": "Oakland International",
            "KLAX": "Los Angeles International",
            "KJFK": "John F Kennedy International",
            "KSEA": "Seattle-Tacoma International",
            "KORD": "Chicago O'Hare International",
            "KATL": "Atlanta Hartsfield-Jackson",
            "KDFW": "Dallas Fort Worth International",
            "EGLL": "London Heathrow",
            "LFPG": "Paris Charles de Gaulle",
            "LFLY": "Lyon Bron Airport",
        }
        return airport_names.get(icao.upper(), f"{icao} Airport")

    def _determine_active_runway(self, wind_direction: int) -> str:
        """Determine active runway based on wind direction.

        Args:
            wind_direction: Wind direction in degrees (0-360), or -1 for variable.

        Returns:
            Active runway identifier (e.g., "31", "04L").
        """
        # For variable wind, use default runway
        if wind_direction < 0:
            return self._departure_runway

        # Round to nearest 10 degrees and divide by 10 to get runway number
        runway_heading = round(wind_direction / 10) * 10
        if runway_heading == 0:
            runway_heading = 360

        runway_num = runway_heading // 10
        if runway_num == 0:
            runway_num = 36

        return f"{runway_num:02d}"

    def _handle_atc_menu(self, message: Message) -> None:
        """Handle ATC menu request (F1 key).

        Args:
            message: ATC menu message with action (open, select).
        """
        if not self.atc_menu:
            logger.warning("ATC menu not available")
            return

        data = message.data
        action = data.get("action", "toggle")

        if action == "toggle":
            if self.atc_menu.is_open():
                self.atc_menu.close()
            else:
                # Get current aircraft state
                aircraft_state = {
                    "on_ground": self._on_ground,
                    "engine_running": self._engine_running,
                    "altitude_agl": float(self._current_altitude),
                }
                self.atc_menu.open(aircraft_state)
        elif action == "select":
            option_key = data.get("option", "")
            if option_key:
                self.atc_menu.select_option(option_key)
        elif action == "close":
            self.atc_menu.close()

    def _handle_atc_acknowledge(self, _message: Message) -> None:
        """Handle ATC acknowledge request (Shift+F1).

        Args:
            _message: Acknowledge message (unused).
        """
        if not self.readback_system:
            logger.warning("Readback system not available")
            return

        self.readback_system.acknowledge()

    def _handle_atc_repeat(self, _message: Message) -> None:
        """Handle ATC repeat request (Ctrl+F1).

        Args:
            _message: Repeat message (unused).
        """
        if not self.readback_system:
            logger.warning("Readback system not available")
            return

        self.readback_system.request_repeat()

    def _handle_menu_previous(self, _message: Message) -> None:
        """Handle menu navigation up (arrow up key).

        Args:
            _message: Menu previous message (unused).
        """
        if self.atc_menu and self.atc_menu.is_open():
            self.atc_menu.move_selection_up()

    def _handle_menu_next(self, _message: Message) -> None:
        """Handle menu navigation down (arrow down key).

        Args:
            _message: Menu next message (unused).
        """
        if self.atc_menu and self.atc_menu.is_open():
            self.atc_menu.move_selection_down()

    def _handle_menu_select(self, _message: Message) -> None:
        """Handle menu selection (Enter key).

        Args:
            _message: Menu select message (unused).
        """
        if self.atc_menu and self.atc_menu.is_open():
            self.atc_menu.select_current()

    def _handle_aircraft_state(self, message: Message) -> None:
        """Handle aircraft state updates.

        Args:
            message: Aircraft state message.
        """
        data = message.data
        self._engine_running = data.get("engine_running", False)
        self._on_ground = data.get("on_ground", True)

    def _handle_atc_request(self, message: Message) -> None:
        """Handle ATC request from autopilot demo or other sources.

        Args:
            message: ATC request message with request_type.
        """
        if not self.atc_queue:
            logger.warning("ATC queue not available")
            return

        from airborne.plugins.radio.atc_queue import ATCMessage

        data = message.data
        request_type = data.get("request_type", "")

        logger.info(f"Processing ATC request: {request_type}")

        # Map request types to ATC messages
        if request_type == "takeoff_clearance":
            # ATC clears for takeoff
            atc_msg = ATCMessage(
                message_key="ATC_TOWER_CLEARED_TAKEOFF_31",
                sender="ATC",
                delay_after=3.0,
            )
            self.atc_queue.enqueue(atc_msg)
        elif request_type == "departure_checkin":
            # Tower: Contact departure
            atc_msg = ATCMessage(
                message_key="ATC_TOWER_CONTACT_DEPARTURE",
                sender="ATC",
                delay_after=3.0,
            )
            self.atc_queue.enqueue(atc_msg)
        elif request_type == "landing_clearance":
            # ATC clears to land
            atc_msg = ATCMessage(
                message_key="ATC_TOWER_CLEARED_LAND_31",
                sender="ATC",
                delay_after=3.0,
            )
            self.atc_queue.enqueue(atc_msg)
        else:
            logger.warning(f"Unknown ATC request type: {request_type}")

    def _handle_atc_v2_text_input(self, message: Message) -> None:
        """Handle ATC V2 text input request (Shift+Space).

        Args:
            message: Text input message with optional text data.
        """
        # Check if V2 settings are enabled (even if initialization failed)
        v2_settings = get_atc_v2_settings()
        if not v2_settings.enabled:
            logger.warning("ATC V2 is disabled in settings")
            return

        data = message.data
        text = data.get("text", "")

        if text:
            # Text provided directly in message
            if self.atc_v2_controller and self.atc_v2_controller.process_text_input(text):
                logger.info(f"ATC V2 processing text: {text}")
        else:
            # Show text input dialog (works even if V2 not fully initialized)
            self._show_atc_v2_text_dialog()

    def _show_atc_v2_text_dialog(self) -> None:
        """Show the ATC V2 text input dialog."""
        if self._atc_v2_text_dialog and self._atc_v2_text_dialog.is_visible:
            # Already visible
            return

        from airborne.core.i18n import t

        # Create dialog
        self._atc_v2_text_dialog = TextInputDialog(
            label=t("widget.dialog.atc_command"),
            on_submit=self._on_atc_v2_text_submit,
            on_cancel=self._on_atc_v2_text_cancel,
            use_phonetic=False,  # Use real letters for text input
            max_length=200,
        )

        # Set up audio callbacks
        if self.context and self.context.tts_service:
            self._atc_v2_text_dialog.set_audio_callbacks(
                speak=lambda text: self.context.tts_service.speak(text) if self.context else None,
                click=None,  # Optional click sounds
            )

        self._atc_v2_text_dialog.show()
        logger.info("ATC V2 text input dialog opened")

    def _on_atc_v2_text_submit(self, text: str) -> None:
        """Handle text input dialog submission.

        Args:
            text: The entered text.
        """
        logger.info(f"ATC V2 text submitted: {text}")
        if self.atc_v2_controller and text:
            self.atc_v2_controller.process_text_input(text)

    def _on_atc_v2_text_cancel(self) -> None:
        """Handle text input dialog cancellation."""
        logger.debug("ATC V2 text input cancelled")

    def handle_text_input_key(self, key: int, unicode: str, mods: int = 0) -> bool:
        """Handle key input for text input dialog.

        This should be called from the main loop when the dialog is visible.

        Args:
            key: pygame key code.
            unicode: Unicode character.
            mods: Modifier keys state.

        Returns:
            True if key was consumed.
        """
        if self._atc_v2_text_dialog and self._atc_v2_text_dialog.is_visible:
            return self._atc_v2_text_dialog.handle_key(key, unicode, mods)
        return False

    def is_text_input_active(self) -> bool:
        """Check if text input dialog is active.

        Returns:
            True if text input dialog is visible.
        """
        return bool(self._atc_v2_text_dialog and self._atc_v2_text_dialog.is_visible)

    def on_config_changed(self, config: dict[str, Any]) -> None:
        """Handle configuration changes.

        Args:
            config: New configuration dictionary.
        """
        radio_config = config.get("radio", {})
        new_callsign = radio_config.get("callsign", self._callsign)

        if new_callsign != self._callsign:
            self._callsign = new_callsign
            logger.info("Callsign changed to: %s", self._callsign)

    def _initialize_atc_v2(self, context: PluginContext) -> None:
        """Initialize ATC V2 voice control if enabled.

        Args:
            context: Plugin context with access to core systems.
        """
        settings = get_atc_v2_settings()
        if not settings.enabled:
            logger.info("ATC V2 voice control is disabled")
            return

        # Get audio engine from audio plugin
        audio_engine = None
        tts_service = None
        if context.plugin_registry:
            audio_plugin = context.plugin_registry.get("audio_plugin")
            if audio_plugin:
                audio_engine = getattr(audio_plugin, "audio_engine", None)
                tts_service = getattr(audio_plugin, "tts_service", None)

        if not audio_engine:
            logger.warning("Audio engine not available - ATC V2 disabled")
            return

        # Create V2 controller
        self.atc_v2_controller = ATCV2Controller(
            audio_engine=audio_engine,
            tts_service=tts_service,
        )

        # Initialize
        try:
            if self.atc_v2_controller.initialize():
                logger.info("ATC V2 voice control initialized")
            else:
                logger.warning("ATC V2 initialization failed")
                self.atc_v2_controller = None
        except Exception as e:
            logger.error(f"ATC V2 initialization error: {e}")
            self.atc_v2_controller = None

    def _update_v2_flight_context(self) -> None:
        """Update the V2 controller's flight context."""
        if not self.atc_v2_controller:
            return

        context = FlightContext(
            callsign=self._callsign,
            airport_icao=self._departure_airport,
            on_ground=self._on_ground,
            current_frequency=self.frequency_manager.get_active("COM1"),
            assigned_runway=self._departure_runway,
            assigned_taxiway="",  # Could track this from ATC handler
            flight_phase="ground" if self._on_ground else "airborne",
        )
        self.atc_v2_controller.set_flight_context(context)

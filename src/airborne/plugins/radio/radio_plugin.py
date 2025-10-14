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
from airborne.plugins.radio.atis import ATISGenerator, ATISInfo
from airborne.plugins.radio.frequency_manager import FrequencyManager, RadioType
from airborne.plugins.radio.phraseology import PhraseMaker
from airborne.plugins.radio.readback import ATCReadbackSystem

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

        # Current state
        self._current_position: Vector3 | None = None
        self._current_altitude: int = 0
        self._current_heading: int = 0
        self._callsign: str = "Cessna 123AB"
        self._current_atis: ATISInfo | None = None
        self._push_to_talk_pressed: bool = False
        self._selected_radio: RadioType = "COM1"
        self._engine_running: bool = False
        self._on_ground: bool = True

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
            logger.info("Interactive ATC systems initialized")
        else:
            logger.warning("ATC audio manager or TTS not available - interactive ATC disabled")

        # Subscribe to messages
        context.message_queue.subscribe("position_updated", self.handle_message)
        context.message_queue.subscribe("input.radio_tune", self.handle_message)
        context.message_queue.subscribe("input.push_to_talk", self.handle_message)
        context.message_queue.subscribe("input.atis_request", self.handle_message)
        context.message_queue.subscribe("airport.nearby", self.handle_message)
        context.message_queue.subscribe("input.atc_menu", self.handle_message)
        context.message_queue.subscribe("input.atc_acknowledge", self.handle_message)
        context.message_queue.subscribe("input.atc_repeat", self.handle_message)
        context.message_queue.subscribe("aircraft.state", self.handle_message)

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

        # Check if we need to update ATIS (e.g., every 5 minutes in real implementation)
        # For now, we'll keep the current ATIS if it exists

    def shutdown(self) -> None:
        """Shutdown the radio plugin."""
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
        elif message.topic == "aircraft.state":
            self._handle_aircraft_state(message)

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
        if self._current_atis:
            atis_text = self.atis_generator.generate(self._current_atis)
            self._speak_atis(atis_text)
        else:
            logger.warning("No ATIS available")

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

    def _speak_atc(self, text: str) -> None:
        """Speak ATC message with appropriate voice.

        Args:
            text: Text to speak.
        """
        if not self.context:
            return

        try:
            if self.context.plugin_registry:
                audio_plugin = self.context.plugin_registry.get("audio_plugin")
                if audio_plugin and hasattr(audio_plugin, "tts_provider"):
                    # TODO: Set different voice/rate for ATC if supported
                    audio_plugin.tts_provider.speak(text, interrupt=False)
        except Exception as e:
            logger.warning("Failed to speak ATC message: %s", e)

    def _speak_atis(self, text: str) -> None:
        """Speak ATIS broadcast.

        Args:
            text: ATIS text to speak.
        """
        if not self.context:
            return

        try:
            if self.context.plugin_registry:
                audio_plugin = self.context.plugin_registry.get("audio_plugin")
                if audio_plugin and hasattr(audio_plugin, "tts_provider"):
                    audio_plugin.tts_provider.speak(text, interrupt=True)
        except Exception as e:
            logger.warning("Failed to speak ATIS: %s", e)

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

    def _handle_aircraft_state(self, message: Message) -> None:
        """Handle aircraft state updates.

        Args:
            message: Aircraft state message.
        """
        data = message.data
        self._engine_running = data.get("engine_running", False)
        self._on_ground = data.get("on_ground", True)

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

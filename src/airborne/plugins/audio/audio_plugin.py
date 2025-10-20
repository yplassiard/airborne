"""Audio plugin for the AirBorne flight simulator.

This plugin wraps the audio system (engine and TTS) as a plugin component,
making it available to other plugins through the plugin context.

Typical usage:
    The audio plugin is loaded automatically by the plugin loader and provides
    audio services to other plugins via the component registry.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from airborne.core.input import InputActionEvent

from airborne.audio.engine.base import IAudioEngine, Vector3
from airborne.audio.sound_manager import SoundManager
from airborne.audio.tts.base import ITTSProvider
from airborne.audio.tts.speech_messages import SpeechMessages
from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType

logger = get_logger(__name__)

# Try to import audio engines, prioritizing FMOD
AUDIO_ENGINE_AVAILABLE = False
FMODEngine: type | None = None

# Loads FMOD
try:
    from airborne.audio.engine.fmod_engine import FMODEngine

    AUDIO_ENGINE_AVAILABLE = True
    logger.info("FMODEngine available")
except (ImportError, OSError) as e:
    logger.info(f"FMODEngine not available: {e}.")


class AudioPlugin(IPlugin):
    """Audio plugin that manages audio engine and TTS.

    This plugin wraps the sound manager, audio engine, and TTS provider,
    making them available to other plugins. It subscribes to position
    updates to maintain the 3D audio listener position.

    The plugin provides:
    - audio_engine: IAudioEngine instance
    - sound_manager: SoundManager instance
    """

    def __init__(self) -> None:
        """Initialize audio plugin."""
        self.context: PluginContext | None = None
        self.sound_manager: SoundManager | None = None
        self.audio_engine: IAudioEngine | None = None
        self.tts_provider: ITTSProvider | None = None
        self.atc_audio_manager: Any = None  # ATCAudioManager for radio communications

        # Listener state
        self._listener_position = Vector3(0.0, 0.0, 0.0)
        self._listener_forward = Vector3(0.0, 0.0, 1.0)
        self._listener_up = Vector3(0.0, 1.0, 0.0)
        self._listener_velocity = Vector3(0.0, 0.0, 0.0)

        # Aircraft state tracking for sounds
        self._last_gear_state = 1.0  # Start with gear down
        self._last_flaps_state = 0.0
        self._last_brakes_state = 0.0
        self._engine_sound_active = False  # Whether engine sound is currently playing
        self._last_engine_rpm = 0.0  # Track RPM for wind-down
        self._last_master_switch: bool | None = None  # Track battery state changes
        self._master_switch_initialized = False  # Track if we've received first message

        # High-frequency audio update timer
        self._audio_update_accumulator = 0.0
        self._audio_update_interval = 0.005  # Update audio every 5ms (200Hz) for smooth transitions

        # Flight state for instrument readouts
        self._airspeed = 0.0  # knots
        self._groundspeed = 0.0  # knots
        self._altitude = 0.0  # feet
        self._heading = 0.0  # degrees
        self._vspeed = 0.0  # feet per minute
        self._bank = 0.0  # degrees
        self._pitch = 0.0  # degrees

        # Engine state for instrument readouts
        self._engine_rpm = 0.0
        self._manifold_pressure = 0.0  # inches Hg
        self._oil_pressure = 0.0  # PSI
        self._oil_temp = 0.0  # Celsius
        self._fuel_flow = 0.0  # GPH
        self._engine_running = False

        # Electrical state for instrument readouts
        self._battery_voltage = 0.0  # Volts
        self._battery_percent = 0.0  # 0-100%
        self._battery_current = 0.0  # Amps (positive = charging, negative = discharging)
        self._alternator_output = 0.0  # Amps

        # Fuel state for instrument readouts
        self._fuel_quantity = 0.0  # Gallons
        self._fuel_remaining_minutes = 0.0  # Minutes

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata.

        Returns:
            PluginMetadata describing this audio plugin.
        """
        return PluginMetadata(
            name="audio_plugin",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.CORE,
            dependencies=[],
            provides=["audio_engine", "sound_manager", "tts"],
            optional=False,
            update_priority=100,  # Update late (after physics)
            requires_physics=False,
            description="Audio system plugin with 3D audio and TTS",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the audio plugin.

        Args:
            context: Plugin context with access to core systems.
        """
        self.context = context

        # Get audio config from context
        audio_config = context.config.get("audio", {})
        tts_config = context.config.get("tts", {})

        # Create audio engine and TTS provider
        if AUDIO_ENGINE_AVAILABLE:
            try:
                # Initialize FMOD
                if FMODEngine is not None:
                    self.audio_engine = FMODEngine()
                    logger.info("FMODEngine created successfully")
                else:
                    self.audio_engine = None
            except Exception as e:
                logger.error(f"Failed to create audio engine: {e}")
                self.audio_engine = None
        else:
            logger.error("Audio engine not available, running without audio")
            self.audio_engine = None

        # Create audio speech provider only if audio engine is available
        if self.audio_engine:
            from airborne.audio.tts.audio_provider import AudioSpeechProvider

            self.tts_provider = AudioSpeechProvider()
            # Pass audio engine reference to TTS provider
            tts_config["audio_engine"] = self.audio_engine
            self.tts_provider.initialize(tts_config)
        else:
            logger.error("TTS provider disabled due to missing audio engine")
            self.tts_provider = None

        # Create sound manager only if audio engine is available
        if self.audio_engine and self.tts_provider:
            self.sound_manager = SoundManager()
            # Don't pass tts_config again - TTS is already initialized
            self.sound_manager.initialize(
                audio_engine=self.audio_engine,
                tts_provider=self.tts_provider,
                audio_config=audio_config,
                tts_config=None,  # Already initialized above
            )
        else:
            logger.error("Sound manager disabled due to missing audio engine or TTS")
            self.sound_manager = None

        # Create ATC audio manager for radio communications
        if self.audio_engine:
            try:
                from pathlib import Path

                from airborne.audio.atc.atc_audio import ATCAudioManager

                config_dir = Path("config")
                speech_dir = Path("data/speech/en")  # ATC uses same speech dir for now
                self.atc_audio_manager = ATCAudioManager(self.audio_engine, config_dir, speech_dir)
                logger.info("ATC audio manager initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize ATC audio manager: {e}")
                self.atc_audio_manager = None
        else:
            self.atc_audio_manager = None

        # Register components in registry
        if context.plugin_registry:
            if self.audio_engine:
                context.plugin_registry.register("audio_engine", self.audio_engine)
            if self.sound_manager:
                context.plugin_registry.register("sound_manager", self.sound_manager)
            context.plugin_registry.register("tts", self.tts_provider)

        # Subscribe to position updates, TTS requests, control inputs, and system states
        context.message_queue.subscribe(MessageTopic.POSITION_UPDATED, self.handle_message)
        context.message_queue.subscribe(MessageTopic.TTS_SPEAK, self.handle_message)
        context.message_queue.subscribe(MessageTopic.TTS_INTERRUPT, self.handle_message)
        context.message_queue.subscribe(MessageTopic.PROXIMITY_BEEP, self.handle_message)
        context.message_queue.subscribe(MessageTopic.CONTROL_INPUT, self.handle_message)
        context.message_queue.subscribe(MessageTopic.ENGINE_STATE, self.handle_message)
        context.message_queue.subscribe(MessageTopic.SYSTEM_STATE, self.handle_message)

        # Subscribe to electrical panel control messages for battery sounds
        context.message_queue.subscribe("electrical.master_switch", self.handle_message)

        # Subscribe to click sound messages from panel controls
        context.message_queue.subscribe("audio.play_click", self.handle_message)

        # Subscribe to input action events from event bus for TTS feedback
        if context.event_bus:
            from airborne.core.input import InputActionEvent

            context.event_bus.subscribe(InputActionEvent, self._handle_input_action)

        # Configure engine sound pitch range from aircraft config
        if self.sound_manager:
            aircraft_audio = audio_config.get("aircraft", {})
            engine_sounds = aircraft_audio.get("engine_sounds", {})
            if engine_sounds:
                pitch_idle = engine_sounds.get("pitch_idle", 0.7)
                pitch_full = engine_sounds.get("pitch_full", 1.3)
                self.sound_manager.set_engine_pitch_range(pitch_idle, pitch_full)
                logger.info(f"Engine pitch range configured: {pitch_idle} to {pitch_full}")

                # Store custom engine sound file path for later use
                self._engine_sound_path = engine_sounds.get(
                    "running", "assets/sounds/aircraft/engine.wav"
                )
                logger.info(f"Engine sound configured: {self._engine_sound_path}")
            else:
                self._engine_sound_path = "assets/sounds/aircraft/engine.wav"

            self.sound_manager.start_wind_sound()
            self._engine_sound_active = False  # Engine sound starts off
            self._last_engine_rpm = 0.0

        logger.info("Audio plugin initialized")

    def update(self, dt: float) -> None:
        """Update audio systems.

        Args:
            dt: Delta time in seconds since last update.
        """
        if not self.sound_manager:
            return

        # Accumulate time for high-frequency audio updates
        self._audio_update_accumulator += dt

        # Update audio at high frequency (every 5ms / 200Hz) for smooth sound transitions
        while self._audio_update_accumulator >= self._audio_update_interval:
            self.sound_manager.update()
            self._audio_update_accumulator -= self._audio_update_interval

        # Update TTS sequential playback (once per frame is fine)
        if self.tts_provider and hasattr(self.tts_provider, "update"):
            self.tts_provider.update()

        # Update listener position (once per frame is fine)
        self.sound_manager.update_listener(
            position=self._listener_position,
            forward=self._listener_forward,
            up=self._listener_up,
            velocity=self._listener_velocity,
        )

    def shutdown(self) -> None:
        """Shutdown the audio plugin."""
        if self.context:
            # Unsubscribe from messages
            self.context.message_queue.unsubscribe(
                MessageTopic.POSITION_UPDATED, self.handle_message
            )
            self.context.message_queue.unsubscribe(MessageTopic.TTS_SPEAK, self.handle_message)
            self.context.message_queue.unsubscribe(MessageTopic.TTS_INTERRUPT, self.handle_message)
            self.context.message_queue.unsubscribe(MessageTopic.PROXIMITY_BEEP, self.handle_message)
            self.context.message_queue.unsubscribe(MessageTopic.CONTROL_INPUT, self.handle_message)
            self.context.message_queue.unsubscribe(MessageTopic.ENGINE_STATE, self.handle_message)
            self.context.message_queue.unsubscribe(MessageTopic.SYSTEM_STATE, self.handle_message)
            self.context.message_queue.unsubscribe("electrical.master_switch", self.handle_message)
            self.context.message_queue.unsubscribe("audio.play_click", self.handle_message)

            # Unregister components (only if they were registered)
            if self.context.plugin_registry:
                if self.audio_engine:
                    self.context.plugin_registry.unregister("audio_engine")
                if self.sound_manager:
                    self.context.plugin_registry.unregister("sound_manager")
                self.context.plugin_registry.unregister("tts")

        # Shutdown sound manager (which shutdowns engine and TTS)
        if self.sound_manager:
            self.sound_manager.shutdown()

        logger.info("Audio plugin shutdown")

    def handle_message(self, message: Message) -> None:
        """Handle messages from other plugins.

        Args:
            message: Message from the queue.
        """
        if message.topic == MessageTopic.CONTROL_INPUT:
            # Handle control input changes for sound effects
            data = message.data

            # Gear change
            if "gear" in data and self.sound_manager:
                gear = data["gear"]
                if gear != self._last_gear_state:
                    self.sound_manager.play_gear_sound(gear > 0.5)
                    self._last_gear_state = gear

            # Flaps change
            if "flaps" in data and self.sound_manager:
                flaps = data["flaps"]
                if flaps != self._last_flaps_state:
                    extending = flaps > self._last_flaps_state
                    self.sound_manager.play_flaps_sound(extending)
                    self._last_flaps_state = flaps

            # Brakes change
            if "brakes" in data and self.sound_manager:
                brakes = data["brakes"]
                if brakes != self._last_brakes_state:
                    self.sound_manager.play_brakes_sound(brakes > 0.0)
                    self._last_brakes_state = brakes

            # Note: Engine sound is now updated by RPM in ENGINE_STATE handler, not throttle

        elif message.topic == MessageTopic.TTS_SPEAK:
            # Handle TTS speak requests
            if self.tts_provider:
                text = message.data.get("text", "")
                priority_str = message.data.get("priority", "normal")

                # Map priority string to TTSPriority enum
                from airborne.audio.tts.base import TTSPriority

                priority_map = {
                    "low": TTSPriority.LOW,
                    "normal": TTSPriority.NORMAL,
                    "high": TTSPriority.HIGH,
                    "critical": TTSPriority.CRITICAL,
                }
                priority = priority_map.get(priority_str.lower(), TTSPriority.NORMAL)

                interrupt = message.data.get("interrupt", False)

                logger.debug(f"TTS request: '{text}' (priority={priority.name})")
                self.tts_provider.speak(text, priority=priority, interrupt=interrupt)

        elif message.topic == MessageTopic.TTS_INTERRUPT:
            # Handle TTS interrupt (stop current speech)
            if self.tts_provider:
                logger.debug("TTS interrupt requested")
                self.tts_provider.stop()

        elif message.topic == MessageTopic.PROXIMITY_BEEP:
            # Handle proximity beep requests from ground navigation
            if self.audio_engine:
                import numpy as np

                data = message.data
                samples = np.array(data.get("samples", []), dtype=np.float32)
                _ = data.get("sample_rate", 44100)  # For future use

                if len(samples) > 0:
                    # Play raw audio samples through audio engine
                    # For now, we log the beep info. Full implementation would call
                    # audio_engine.play_raw_samples(samples, sample_rate)
                    target_id = data.get("target_id", "unknown")
                    distance = data.get("distance", 0.0)
                    frequency = data.get("frequency", 0.0)
                    logger.debug(
                        "Playing proximity beep: target=%s, distance=%.1fm, freq=%.2fHz, samples=%d",
                        target_id,
                        distance,
                        frequency,
                        len(samples),
                    )
                    # TODO: Implement play_raw_samples() in audio engines
                    # self.audio_engine.play_raw_samples(samples, sample_rate)

        elif message.topic == MessageTopic.POSITION_UPDATED:
            # Update listener position from aircraft position
            data = message.data

            # Update flight state for instrument readouts
            if "airspeed" in data:
                self._airspeed = data["airspeed"]
            if "groundspeed" in data:
                self._groundspeed = data["groundspeed"]
            if "altitude" in data:
                self._altitude = data["altitude"]
            if "heading" in data:
                self._heading = data["heading"]
            if "vspeed" in data:
                self._vspeed = data["vspeed"]
            if "bank" in data:
                self._bank = data["bank"]
            if "pitch" in data:
                self._pitch = data["pitch"]

            # Update wind sound based on airspeed
            if "airspeed" in data and self.sound_manager:
                airspeed = data["airspeed"]
                self.sound_manager.update_wind_sound(airspeed)

            # Update rolling sound based on ground speed and on_ground status
            if "groundspeed" in data and "on_ground" in data and self.sound_manager:
                ground_speed = data["groundspeed"]
                on_ground = data["on_ground"]
                self.sound_manager.update_rolling_sound(ground_speed, on_ground)

            if "position" in data:
                pos = data["position"]
                if isinstance(pos, dict):
                    self._listener_position = Vector3(
                        pos.get("x", 0.0), pos.get("y", 0.0), pos.get("z", 0.0)
                    )
                elif isinstance(pos, (tuple, list)) and len(pos) >= 3:
                    self._listener_position = Vector3(float(pos[0]), float(pos[1]), float(pos[2]))

            if "forward" in data:
                fwd = data["forward"]
                if isinstance(fwd, dict):
                    self._listener_forward = Vector3(
                        fwd.get("x", 0.0), fwd.get("y", 0.0), fwd.get("z", 1.0)
                    )
                elif isinstance(fwd, (tuple, list)) and len(fwd) >= 3:
                    self._listener_forward = Vector3(float(fwd[0]), float(fwd[1]), float(fwd[2]))

            if "up" in data:
                up = data["up"]
                if isinstance(up, dict):
                    self._listener_up = Vector3(
                        up.get("x", 0.0), up.get("y", 1.0), up.get("z", 0.0)
                    )
                elif isinstance(up, (tuple, list)) and len(up) >= 3:
                    self._listener_up = Vector3(float(up[0]), float(up[1]), float(up[2]))

            if "velocity" in data:
                vel = data["velocity"]
                if isinstance(vel, dict):
                    self._listener_velocity = Vector3(
                        vel.get("x", 0.0), vel.get("y", 0.0), vel.get("z", 0.0)
                    )
                elif isinstance(vel, (tuple, list)) and len(vel) >= 3:
                    self._listener_velocity = Vector3(float(vel[0]), float(vel[1]), float(vel[2]))

        elif message.topic == MessageTopic.ENGINE_STATE:
            # Update engine state for instrument readouts
            data = message.data
            engine_running = data.get("running", False)
            engine_rpm = data.get("rpm", 0.0)

            # Start/stop engine sound based on RPM (not just running state)
            # This allows sound during cranking and gradual wind-down
            if self.sound_manager and hasattr(self, "_engine_sound_active"):
                if engine_rpm > 0 and not self._engine_sound_active:
                    # RPM > 0: Start engine sound (starter engaged or running)
                    engine_sound_path = getattr(
                        self, "_engine_sound_path", "assets/sounds/aircraft/engine.wav"
                    )
                    self.sound_manager.start_engine_sound(engine_sound_path)
                    self._engine_sound_active = True
                    logger.info(f"Engine sound started at {engine_rpm:.0f} RPM")
                elif engine_rpm <= 0 and self._engine_sound_active:
                    # RPM = 0: Stop engine sound (fully stopped)
                    if (
                        hasattr(self.sound_manager, "_engine_source_id")
                        and self.sound_manager._engine_source_id is not None
                    ):
                        self.sound_manager.stop_sound(self.sound_manager._engine_source_id)
                        self.sound_manager._engine_source_id = None
                        self._engine_sound_active = False
                        logger.info("Engine sound stopped (RPM = 0)")

                # Update engine sound pitch based on RPM
                if self._engine_sound_active and engine_rpm > 0:
                    # Get engine RPM limits from config or use defaults
                    idle_rpm = 600.0  # Cessna 172 idle RPM
                    max_rpm = 2700.0  # Cessna 172 max RPM
                    self.sound_manager.update_engine_sound_rpm(engine_rpm, idle_rpm, max_rpm)

            self._engine_running = engine_running
            self._engine_rpm = engine_rpm
            self._last_engine_rpm = engine_rpm  # Track for potential future use
            self._manifold_pressure = data.get("manifold_pressure", 0.0)
            self._oil_pressure = data.get("oil_pressure", 0.0)
            self._oil_temp = data.get("oil_temp", 0.0)
            self._fuel_flow = data.get("fuel_flow", 0.0)

        elif message.topic == MessageTopic.SYSTEM_STATE:
            # Update system states for instrument readouts
            data = message.data
            system = data.get("system")

            if system == "electrical":
                # Battery sounds are handled by electrical.master_switch messages from control panel
                # This handler only tracks electrical state for instrument readouts
                self._battery_voltage = data.get("battery_voltage", 0.0)
                self._battery_percent = data.get("battery_soc_percent", 0.0)
                self._battery_current = data.get("battery_current_amps", 0.0)
                self._alternator_output = data.get("alternator_output_amps", 0.0)

            elif system == "fuel":
                self._fuel_quantity = data.get("total_quantity_gallons", 0.0)
                self._fuel_remaining_minutes = data.get("time_remaining_minutes", 0.0)

        elif message.topic == "electrical.master_switch":
            # Handle master switch from control panel
            data = message.data
            state = data.get("state", "")

            # Handle both string ("ON"/"OFF") and boolean (True/False) formats
            if isinstance(state, bool):
                master_on = state
            elif isinstance(state, str):
                master_on = state == "ON"
            else:
                master_on = False

            logger.info(
                f"Received electrical.master_switch message: state={state} (type={type(state).__name__}), master_on={master_on}, last={self._last_master_switch}, initialized={self._master_switch_initialized}"
            )

            # Play battery sound when master switch changes
            # Skip ONLY if this is the very first message AND the state is already correct
            should_play = False
            if self.sound_manager:
                if not self._master_switch_initialized:
                    # First message - only skip if this is startup state (False/OFF)
                    # If it's ON, it means user pressed it, so play the sound
                    should_play = master_on  # Play only if turning ON
                    self._master_switch_initialized = True
                elif master_on != self._last_master_switch:
                    # Subsequent messages - play if state changed
                    should_play = True

            if should_play:
                if master_on:
                    # Turning ON - play sequence with callback
                    def on_battery_ready():
                        """Called when battery loop starts (battery is truly ON)."""
                        logger.info("Battery ready - activating electrical system")
                        # Send message to electrical system to actually turn on
                        if self.context:
                            self.context.message_queue.publish(
                                Message(
                                    sender="audio_plugin",
                                    recipients=["simple_electrical_system"],
                                    topic=MessageTopic.ELECTRICAL_STATE,
                                    data={"battery_master": True},
                                    priority=MessagePriority.HIGH,
                                )
                            )

                    self.sound_manager.play_battery_sound(
                        True, on_complete_callback=on_battery_ready
                    )
                    logger.info("Battery startup sequence initiated")
                else:
                    # Turning OFF - immediate
                    self.sound_manager.play_battery_sound(False)
                    logger.info("Battery shutdown (panel control)")

            # Always update the last state (even on first time)
            self._last_master_switch = master_on

        elif message.topic == "audio.play_click":
            # Handle click sound request from panel controls
            if self.sound_manager:
                control_type = message.data.get("control_type", "knob")

                # Use different click sounds for different control types
                if control_type == "switch":
                    sound_file = "assets/sounds/aircraft/click_switch.mp3"
                else:  # knob or slider - both use knob click
                    sound_file = "assets/sounds/aircraft/click_knob.mp3"

                self.sound_manager.play_sound_2d(sound_file, volume=0.8)

    def on_config_changed(self, config: dict[str, Any]) -> None:
        """Handle configuration changes.

        Args:
            config: New configuration dictionary.
        """
        # Update audio settings if changed
        audio_config = config.get("audio", {})

        if self.sound_manager and "master_volume" in audio_config:
            self.sound_manager.set_master_volume(audio_config["master_volume"])

        if self.sound_manager and "tts_enabled" in audio_config:
            self.sound_manager.set_tts_enabled(audio_config["tts_enabled"])

        if self.tts_provider:
            if "rate" in audio_config:
                self.tts_provider.set_rate(audio_config["rate"])
            if "volume" in audio_config:
                self.tts_provider.set_volume(audio_config["volume"])

        logger.info("Audio plugin configuration updated")

    def _handle_input_action(self, event: "InputActionEvent") -> None:
        """Handle input action events and provide TTS feedback.

        Args:
            event: Input action event from event bus.
        """
        logger.debug(f"Input action received: {event.action}")

        # Handle throttle click sound (no TTS needed)
        if event.action == "throttle_click":
            if self.sound_manager:
                self.sound_manager.play_sound_2d(
                    "assets/sounds/aircraft/click_knob.mp3", volume=0.3
                )
            return

        # Handle throttle released (announce percent)
        if event.action == "throttle_released" and event.value is not None:
            if self.tts_provider:
                throttle_percent = int(event.value)
                keys = SpeechMessages.throttle_percent(throttle_percent)
                # Interrupt any current speech to announce throttle immediately
                self.tts_provider.speak(keys, interrupt=True)  # type: ignore[arg-type]
            return

        if not self.tts_provider:
            logger.warning("No TTS provider available for input action feedback")
            return

        message: str | None = None

        # Handle instrument readouts
        if event.action == "read_airspeed":
            message = f"Airspeed {int(self._airspeed)} knots"
        elif event.action == "read_altitude":
            message = f"Altitude {int(self._altitude)} feet"
        elif event.action == "read_heading":
            message = f"Heading {int(self._heading)} degrees"
        elif event.action == "read_vspeed":
            # Format vertical speed with sign
            vspeed_int = int(self._vspeed)
            if vspeed_int > 0:
                message = f"Climbing {vspeed_int} feet per minute"
            elif vspeed_int < 0:
                message = f"Descending {abs(vspeed_int)} feet per minute"
            else:
                message = "Level flight"
        elif event.action == "read_attitude":
            # Format bank and pitch angles
            bank_int = int(self._bank)
            pitch_int = int(self._pitch)
            bank_dir = "left" if bank_int < 0 else "right" if bank_int > 0 else "level"
            pitch_dir = "up" if pitch_int > 0 else "down" if pitch_int < 0 else "level"
            if bank_int == 0 and pitch_int == 0:
                message = "Level attitude"
            elif bank_int == 0:
                message = f"Pitch {abs(pitch_int)} degrees {pitch_dir}"
            elif pitch_int == 0:
                message = f"Bank {abs(bank_int)} degrees {bank_dir}"
            else:
                message = f"Bank {abs(bank_int)} {bank_dir}, pitch {abs(pitch_int)} {pitch_dir}"

        # Engine instrument readouts
        elif event.action == "read_rpm":
            if self._engine_running:
                message = f"Engine RPM {int(self._engine_rpm)}"
            else:
                message = "Engine stopped"
        elif event.action == "read_manifold_pressure":
            message = f"Manifold pressure {self._manifold_pressure:.1f} inches"
        elif event.action == "read_oil_pressure":
            message = f"Oil pressure {int(self._oil_pressure)} PSI"
        elif event.action == "read_oil_temp":
            # Convert Celsius to Fahrenheit for readout
            oil_temp_f = self._oil_temp * 9 / 5 + 32
            message = f"Oil temperature {int(oil_temp_f)} degrees"
        elif event.action == "read_fuel_flow":
            message = f"Fuel flow {self._fuel_flow:.1f} gallons per hour"

        # Electrical instrument readouts
        elif event.action == "read_battery_voltage":
            message = f"Battery {self._battery_voltage:.1f} volts"
        elif event.action == "read_battery_percent":
            message = f"Battery {int(self._battery_percent)} percent"
        elif event.action == "read_battery_status":
            if self._battery_current > 1.0:
                message = f"Battery charging at {self._battery_current:.1f} amps"
            elif self._battery_current < -1.0:
                message = f"Battery discharging at {abs(self._battery_current):.1f} amps"
            else:
                message = "Battery stable"
        elif event.action == "read_alternator":
            message = f"Alternator output {self._alternator_output:.1f} amps"

        # Fuel instrument readouts
        elif event.action == "read_fuel_quantity":
            message = f"Fuel quantity {self._fuel_quantity:.1f} gallons"
        elif event.action == "read_fuel_remaining":
            fuel_minutes = self._fuel_remaining_minutes or 0.0
            hours = int(fuel_minutes / 60)
            minutes = int(fuel_minutes % 60)
            if hours > 0:
                message = f"Fuel remaining {hours} hours {minutes} minutes"
            else:
                message = f"Fuel remaining {minutes} minutes"

        # Comprehensive status readouts (Alt+5, Alt+6, Alt+7)
        elif event.action == "read_engine":
            if self._engine_running:
                message = f"Engine {int(self._engine_rpm)} RPM"
            else:
                message = "Engine stopped"
        elif event.action == "read_electrical":
            message = (
                f"Battery {self._battery_voltage:.1f} volts {int(self._battery_percent)} percent"
            )
        elif event.action == "read_fuel":
            fuel_minutes = self._fuel_remaining_minutes or 0.0
            hours = int(fuel_minutes / 60)
            minutes = int(fuel_minutes % 60)
            if hours > 0:
                message = f"Fuel {self._fuel_quantity:.1f} gallons remaining {hours} hours {minutes} minutes"
            else:
                message = f"Fuel {self._fuel_quantity:.1f} gallons remaining {minutes} minutes"

        else:
            # Map actions to TTS announcements
            action_messages = {
                "gear_toggle": "Gear " + ("down" if self._last_gear_state > 0.5 else "up"),
                "flaps_down": "Flaps extending",
                "flaps_up": "Flaps retracting",
                "throttle_increase": "Throttle increased",
                "throttle_decrease": "Throttle decreased",
                "throttle_full": "Full throttle",
                "throttle_idle": "Throttle idle",
                "brakes_on": "Brakes on",
                "pause": "Paused",
                "tts_next": "Next",
            }

            message = action_messages.get(event.action)

        if not message:
            logger.debug(f"No TTS message for action: {event.action}")
            return

        from airborne.audio.tts.base import TTSPriority

        # Convert message to message key
        message_key = self._get_message_key(message, event.action)

        # Handle both str and list[str] cases
        if isinstance(message_key, list):
            # Log the list of keys for debugging
            logger.info(f"Speaking: {' '.join(message_key)} ({message})")
            # Pass the list directly to TTS provider for composable playback
            self.tts_provider.speak(message_key, priority=TTSPriority.NORMAL)  # type: ignore[arg-type]
        else:
            logger.info(f"Speaking: {message_key} ({message})")
            self.tts_provider.speak(message_key, priority=TTSPriority.NORMAL)

    def _get_message_key(self, message: str, action: str) -> str | list[str]:
        """Convert human-readable message to message key.

        Args:
            message: Human-readable message.
            action: Input action that triggered the message.

        Returns:
            Message key or list of message keys for YAML lookup.
        """
        from airborne.audio.tts.speech_messages import SpeechMessages

        # Map instrument reading actions to helper methods
        if action == "read_airspeed":
            return SpeechMessages.airspeed(int(self._airspeed))
        elif action == "read_altitude":
            return SpeechMessages.altitude(int(self._altitude))
        elif action == "read_heading":
            return SpeechMessages.heading(int(self._heading))
        elif action == "read_vspeed":
            return SpeechMessages.vertical_speed(int(self._vspeed))
        elif action == "read_attitude":
            # For attitude, we read pitch first, then bank
            # Always include instrument names
            bank_int = int(self._bank)
            pitch_int = int(self._pitch)

            result = [SpeechMessages.MSG_WORD_PITCH]
            if abs(pitch_int) < 3:
                result.append(SpeechMessages.MSG_LEVEL_ATTITUDE)
            else:
                result.append(SpeechMessages.pitch(pitch_int))

            result.append(SpeechMessages.MSG_WORD_BANK)
            if abs(bank_int) < 3:
                result.append(SpeechMessages.MSG_LEVEL_ATTITUDE)
            else:
                result.append(SpeechMessages.bank(bank_int))

            return result

        # Engine instrument readouts
        elif action == "read_rpm":
            return SpeechMessages.engine_rpm(int(self._engine_rpm), self._engine_running)
        elif action == "read_manifold_pressure":
            return SpeechMessages.manifold_pressure(self._manifold_pressure)
        elif action == "read_oil_pressure":
            return SpeechMessages.oil_pressure(int(self._oil_pressure))
        elif action == "read_oil_temp":
            # Convert Celsius to Fahrenheit
            oil_temp_f = self._oil_temp * 9 / 5 + 32
            return SpeechMessages.oil_temperature(int(oil_temp_f))
        elif action == "read_fuel_flow":
            return SpeechMessages.fuel_flow(self._fuel_flow)

        # Electrical instrument readouts
        elif action == "read_battery_voltage":
            return SpeechMessages.battery_voltage(self._battery_voltage)
        elif action == "read_battery_percent":
            return SpeechMessages.battery_percent(int(self._battery_percent))
        elif action == "read_battery_status":
            return SpeechMessages.battery_status(self._battery_current)
        elif action == "read_alternator":
            return SpeechMessages.alternator_output(self._alternator_output)

        # Fuel instrument readouts
        elif action == "read_fuel_quantity":
            return SpeechMessages.fuel_quantity(self._fuel_quantity)
        elif action == "read_fuel_remaining":
            return SpeechMessages.fuel_remaining(self._fuel_remaining_minutes or 0.0)

        # Comprehensive status readouts - return first message, queue rest
        elif action == "read_engine":
            # Comprehensive engine status (RPM)
            return SpeechMessages.engine_status(int(self._engine_rpm), self._engine_running)

        elif action == "read_electrical":
            # Comprehensive electrical status (voltage, percent, charging/discharging)
            return SpeechMessages.electrical_status(
                self._battery_voltage, int(self._battery_percent), self._battery_current
            )

        elif action == "read_fuel":
            # Comprehensive fuel status (quantity, remaining time)
            return SpeechMessages.fuel_status(
                self._fuel_quantity, self._fuel_remaining_minutes or 0.0
            )

        # Map action messages to constants
        action_to_key = {
            "Gear down": SpeechMessages.MSG_GEAR_DOWN,
            "Gear up": SpeechMessages.MSG_GEAR_UP,
            "Flaps extending": SpeechMessages.MSG_FLAPS_EXTENDING,
            "Flaps retracting": SpeechMessages.MSG_FLAPS_RETRACTING,
            "Throttle increased": SpeechMessages.MSG_THROTTLE_INCREASED,
            "Throttle decreased": SpeechMessages.MSG_THROTTLE_DECREASED,
            "Full throttle": SpeechMessages.MSG_FULL_THROTTLE,
            "Throttle idle": SpeechMessages.MSG_THROTTLE_IDLE,
            "Brakes on": SpeechMessages.MSG_BRAKES_ON,
            "Paused": SpeechMessages.MSG_PAUSED,
            "Next": SpeechMessages.MSG_NEXT,
            "Level flight": SpeechMessages.MSG_LEVEL_FLIGHT,
            "Level attitude": SpeechMessages.MSG_LEVEL_ATTITUDE,
        }

        return action_to_key.get(message, SpeechMessages.MSG_ERROR)

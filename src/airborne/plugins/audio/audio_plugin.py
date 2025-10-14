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
from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType

logger = get_logger(__name__)

# Try to import audio engines, prioritizing FMOD
AUDIO_ENGINE_AVAILABLE = False
PyBASSEngine: type | None = None
FMODEngine: type | None = None

# Try FMOD first (preferred, cross-platform)
try:
    from airborne.audio.engine.fmod_engine import FMODEngine

    AUDIO_ENGINE_AVAILABLE = True
    logger.info("FMODEngine available")
except (ImportError, OSError) as e:
    logger.info(f"FMODEngine not available: {e}. Trying PyBASSEngine...")

# Fall back to PyBASS if FMOD not available
if not AUDIO_ENGINE_AVAILABLE:
    try:
        from airborne.audio.engine.pybass_engine import PyBASSEngine

        AUDIO_ENGINE_AVAILABLE = True
        logger.info("PyBASSEngine available")
    except (ImportError, OSError) as e:
        logger.warning(f"PyBASSEngine not available: {e}. Audio plugin will run in stub mode.")


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
        self._engine_started = False

        # Flight state for instrument readouts
        self._airspeed = 0.0  # knots
        self._groundspeed = 0.0  # knots
        self._altitude = 0.0  # feet
        self._heading = 0.0  # degrees
        self._vspeed = 0.0  # feet per minute
        self._bank = 0.0  # degrees
        self._pitch = 0.0  # degrees

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
                # Try FMOD first, fall back to PyBASS
                if FMODEngine is not None:
                    self.audio_engine = FMODEngine()
                    logger.info("FMODEngine created successfully")
                elif PyBASSEngine is not None:
                    self.audio_engine = PyBASSEngine()
                    logger.info("PyBASSEngine created successfully")
                else:
                    self.audio_engine = None
            except Exception as e:
                logger.error(f"Failed to create audio engine: {e}")
                self.audio_engine = None
        else:
            logger.warning("Audio engine not available, running without audio")
            self.audio_engine = None

        # Create audio speech provider only if audio engine is available
        if self.audio_engine:
            from airborne.audio.tts.audio_provider import AudioSpeechProvider

            self.tts_provider = AudioSpeechProvider()
            # Pass audio engine reference to TTS provider
            tts_config["audio_engine"] = self.audio_engine
            self.tts_provider.initialize(tts_config)
        else:
            logger.warning("TTS provider disabled due to missing audio engine")
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
            logger.warning("Sound manager disabled due to missing audio engine or TTS")
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

        # Subscribe to position updates, TTS requests, control inputs, and input actions
        context.message_queue.subscribe(MessageTopic.POSITION_UPDATED, self.handle_message)
        context.message_queue.subscribe(MessageTopic.TTS_SPEAK, self.handle_message)
        context.message_queue.subscribe(MessageTopic.TTS_INTERRUPT, self.handle_message)
        context.message_queue.subscribe(MessageTopic.CONTROL_INPUT, self.handle_message)

        # Subscribe to input action events from event bus for TTS feedback
        if context.event_bus:
            from airborne.core.input import InputActionEvent

            context.event_bus.subscribe(InputActionEvent, self._handle_input_action)

        # Start engine and wind sounds if sound manager available
        if self.sound_manager:
            self.sound_manager.start_engine_sound()
            self.sound_manager.start_wind_sound()
            self._engine_started = True

        logger.info("Audio plugin initialized")

    def update(self, dt: float) -> None:
        """Update audio systems.

        Args:
            dt: Delta time in seconds since last update.
        """
        # Update FMOD system if using FMODEngine
        if self.audio_engine and hasattr(self.audio_engine, "update"):
            self.audio_engine.update()

        # Update TTS sequential playback
        if self.tts_provider and hasattr(self.tts_provider, "update"):
            self.tts_provider.update()

        if not self.sound_manager:
            return

        # Update listener position
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
            self.context.message_queue.unsubscribe(MessageTopic.CONTROL_INPUT, self.handle_message)

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

            # Update engine sound based on throttle
            if "throttle" in data and self.sound_manager:
                throttle = data["throttle"]
                self.sound_manager.update_engine_sound(throttle)

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
            # If it's a list, join with spaces or use the first one
            text_to_speak = " ".join(message_key) if message_key else message
        else:
            text_to_speak = message_key

        logger.info(f"Speaking: {text_to_speak} ({message})")
        self.tts_provider.speak(text_to_speak, priority=TTSPriority.NORMAL)

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
            # For attitude, we need bank/pitch combination
            bank_int = int(self._bank)
            pitch_int = int(self._pitch)
            if abs(bank_int) < 3 and abs(pitch_int) < 3:
                return SpeechMessages.MSG_LEVEL_ATTITUDE
            elif abs(bank_int) < 3:
                return SpeechMessages.pitch(pitch_int)
            elif abs(pitch_int) < 3:
                return SpeechMessages.bank(bank_int)
            else:
                # For combined attitude, use bank message for now
                # TODO: Support combined attitude messages
                return SpeechMessages.bank(bank_int)

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

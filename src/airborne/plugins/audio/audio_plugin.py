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
from airborne.core.i18n import t
from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType
from airborne.core.resource_path import get_data_path, get_resource_path
from airborne.plugins.instruments.altimeter import AltimeterManager

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

        # Aircraft configuration
        self._fixed_gear = False  # Will be updated during initialize

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

        # Stall warning state
        self._angle_of_attack = 0.0  # degrees
        self._stall_warning_active = False
        self._stall_warning_sound: Any = None  # Sound object
        self._stall_warning_source_id: int | None = None  # Source ID for stopping
        self._stall_announced = False  # Track if we've announced "Stall!" for current stall event
        self._stall_warn_aoa_threshold = 14.0  # Start warning at 14° AOA
        self._stall_aoa_threshold = 16.0  # Full stall at 16° AOA

        # Trim state for readouts
        self._pitch_trim = 0.0  # -1.0 to 1.0 (0.0 = neutral)
        self._rudder_trim = 0.0  # -1.0 to 1.0 (0.0 = neutral)

        # Pitch control feedback - continuous sweeping tone
        self._last_pitch_control = 0.0  # Track pitch control position
        self._pitch_tone_channel: int | None = None  # Currently playing tone
        self._pitch_tone_active = False  # Whether tone is currently playing
        self._last_pitch_freq = 440.0  # Last frequency played (for change detection)

        # Ground surface type for rolling sounds (updated by position tracker)
        self._current_surface_type = "concrete"  # Default to concrete

        # Altimeter instrument
        self._altimeter = AltimeterManager()  # Defaults to 29.92 inHg (standard pressure)

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

        # Get aircraft config (for fixed_gear, etc.)
        aircraft_config = context.config.get("aircraft", {})
        self._fixed_gear = aircraft_config.get("fixed_gear", False)
        logger.info(f"AudioPlugin: fixed_gear={self._fixed_gear}")

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
            # Pass audio engine reference and resource paths to TTS provider
            tts_config["audio_engine"] = self.audio_engine
            tts_config["speech_dir"] = str(get_data_path("speech"))
            tts_config["config_dir"] = str(get_resource_path("config"))
            # Pass shared TTSService from registry (for system TTS mode)
            tts_service = context.plugin_registry.get("tts_service")
            if tts_service:
                tts_config["tts_service"] = tts_service
                logger.info("Passing shared TTSService to AudioSpeechProvider")
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

            # Enable 3D spatial audio for cockpit sounds using aircraft-specific preset
            # Get aircraft type from config (defaults to "cessna_172")
            aircraft_name = aircraft_config.get("name", "").lower().replace(" ", "_")
            icao_code = aircraft_config.get("icao_code", "").lower()
            # Try preset name in order: explicit preset, icao code, aircraft name, default
            cockpit_preset = audio_config.get("cockpit_preset")
            if not cockpit_preset:
                # Convert common ICAO codes to preset names
                icao_to_preset = {"c172": "cessna_172", "c152": "cessna_152", "pa28": "piper_pa28", "dr40": "dr400"}
                cockpit_preset = icao_to_preset.get(icao_code, icao_code or "cessna_172")

            presets_dir = str(get_resource_path("config/cockpit_presets"))
            if self.sound_manager.load_cockpit_preset(cockpit_preset, presets_dir):
                logger.info(f"3D spatial audio enabled for cockpit (preset: {cockpit_preset})")
        else:
            logger.error("Sound manager disabled due to missing audio engine or TTS")
            self.sound_manager = None

        # Create ATC audio manager for radio communications
        if self.audio_engine:
            try:
                from airborne.audio.atc.atc_audio import ATCAudioManager
                from airborne.audio.engine.base import Vector3

                config_dir = get_resource_path("config")
                speech_dir = get_data_path("speech/en")  # ATC uses same speech dir for now
                self.atc_audio_manager = ATCAudioManager(self.audio_engine, config_dir, speech_dir)
                # Wire up TTS provider for system TTS fallback
                if self.tts_provider:
                    self.atc_audio_manager.set_tts_provider(self.tts_provider)

                # Enable 3D radio speaker positioning from preset (or default)
                radio_pos = Vector3(0.0, 0.15, 0.55)  # Default position
                if self.sound_manager and self.sound_manager._spatial_manager:
                    radio_pos = self.sound_manager._spatial_manager.get_radio_speaker_position()
                self.atc_audio_manager.set_radio_speaker_position(radio_pos)

                logger.info(
                    f"ATC audio manager initialized with 3D radio speaker at "
                    f"({radio_pos.x:.2f}, {radio_pos.y:.2f}, {radio_pos.z:.2f})"
                )
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

        # Subscribe to navigation location messages for surface type tracking
        context.message_queue.subscribe("navigation.entered_taxiway", self.handle_message)
        context.message_queue.subscribe("navigation.entered_runway", self.handle_message)
        context.message_queue.subscribe("navigation.entered_parking", self.handle_message)
        context.message_queue.subscribe("navigation.entered_apron", self.handle_message)
        context.message_queue.subscribe("navigation.location_changed", self.handle_message)

        # Subscribe to altimeter messages from control panel
        context.message_queue.subscribe("instruments.read_altimeter", self.handle_message)
        context.message_queue.subscribe("instruments.altimeter", self.handle_message)

        # Subscribe to altimeter input actions from context system
        context.message_queue.subscribe("input.altimeter_increase", self.handle_message)
        context.message_queue.subscribe("input.altimeter_decrease", self.handle_message)
        context.message_queue.subscribe("input.altimeter_toggle_unit", self.handle_message)
        context.message_queue.subscribe("input.altimeter_enter_digit", self.handle_message)
        context.message_queue.subscribe("input.altimeter_confirm_entry", self.handle_message)
        context.message_queue.subscribe("input.altimeter_clear_entry", self.handle_message)
        context.message_queue.subscribe("input.altimeter_announce", self.handle_message)

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

                # Check if we have start/idle/shutdown sound structure (new format)
                if "start" in engine_sounds and "idle" in engine_sounds:
                    # New format: start/idle/shutdown sequence
                    start_path = str(get_resource_path(engine_sounds.get("start")))
                    idle_path = str(get_resource_path(engine_sounds.get("idle")))
                    shutdown_path = (
                        str(get_resource_path(engine_sounds.get("shutdown", "")))
                        if "shutdown" in engine_sounds
                        else None
                    )

                    self.sound_manager.set_engine_sound_paths(start_path, idle_path, shutdown_path)
                    self._engine_sound_path = idle_path  # Store idle path for compatibility
                    logger.info(
                        f"Engine sound sequence configured: start={start_path}, idle={idle_path}, shutdown={shutdown_path}"
                    )
                else:
                    # Old format: single running sound
                    engine_sound_relative = engine_sounds.get(
                        "running", "assets/sounds/aircraft/engine.wav"
                    )
                    self._engine_sound_path = str(get_resource_path(engine_sound_relative))
                    logger.info(f"Engine sound configured: {self._engine_sound_path}")
            else:
                self._engine_sound_path = str(
                    get_resource_path("assets/sounds/aircraft/engine.wav")
                )

            # Configure battery sounds from aircraft config
            system_sounds = aircraft_audio.get("system_sounds", {})
            if system_sounds:
                battery_on = system_sounds.get("battery_on")
                battery_off = system_sounds.get("battery_off")
                battery_loop = system_sounds.get("battery_loop")
                self.sound_manager.set_battery_sound_paths(battery_on, battery_off, battery_loop)
                logger.info(
                    f"Battery sounds configured: on={battery_on}, off={battery_off}, loop={battery_loop}"
                )

            # Wind sound starts/stops automatically based on airspeed threshold (20+ knots)
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

        # NOTE: Stall warning disabled - not working correctly with current AOA values
        # self._update_stall_warning()

        # Update listener position (once per frame is fine)
        # For cockpit-relative 3D audio, listener stays at origin (0,0,0)
        # since all cockpit sound positions are defined relative to pilot's head.
        # Forward/up vectors still provide orientation for directional cues.
        self.sound_manager.update_listener(
            position=Vector3(0.0, 0.0, 0.0),  # Cockpit-relative origin
            forward=self._listener_forward,
            up=self._listener_up,
            velocity=Vector3(0.0, 0.0, 0.0),  # No doppler inside cockpit
        )

    def _update_stall_warning(self) -> None:
        """Update stall warning sound based on angle of attack."""
        if not self.audio_engine:
            return

        aoa = abs(self._angle_of_attack)  # Use absolute value for both positive and negative AOA

        # Determine if we should play stall warning
        should_warn = aoa >= self._stall_warn_aoa_threshold
        is_stalling = aoa >= self._stall_aoa_threshold

        # Start/stop stall warning sound (looping)
        if should_warn and not self._stall_warning_active:
            # Start playing stall warning sound (looping)
            logger.info(f"Stall warning activated (AOA={aoa:.1f}°)")
            sound_path = str(get_resource_path("assets/sounds/aircraft/stall_warn.mp3"))
            try:
                self._stall_warning_sound = self.audio_engine.load_sound(sound_path)
                if self._stall_warning_sound is not None:
                    self._stall_warning_source_id = self.audio_engine.play_2d(
                        self._stall_warning_sound, loop=True, volume=0.7
                    )
                    self._stall_warning_active = True
            except Exception as e:
                logger.error(f"Failed to play stall warning sound: {e}")

        elif not should_warn and self._stall_warning_active:
            # Stop playing stall warning sound
            logger.info(f"Stall warning deactivated (AOA={aoa:.1f}°)")
            if self._stall_warning_source_id is not None:
                self.audio_engine.stop_source(self._stall_warning_source_id)
                self._stall_warning_source_id = None
            self._stall_warning_active = False
            self._stall_announced = False  # Reset announcement flag when exiting stall

        # Announce "Stall!" once when entering full stall
        if is_stalling and not self._stall_announced and self.tts_provider:
            logger.info(f"STALL! (AOA={aoa:.1f}°)")
            # Play "Stall!" message with high priority, interrupting other speech
            from airborne.audio.tts.base import TTSPriority

            stall_message = f"{t('actions.stall')}! {t('actions.stall')}!"
            self.tts_provider.speak(stall_message, priority=TTSPriority.CRITICAL, interrupt=True)
            self._stall_announced = True

    def _update_pitch_feedback_tone(self, pitch: float) -> None:
        """Update sweeping tone to indicate pitch control position.

        Uses rapid short beeps that change frequency, creating a sweeping effect:
        - pitch = 0.0 (neutral): SILENT (no tone)
        - pitch = +0.05 to +1.0 (forward/nose down): 330-220 Hz (falling sweep)
        - pitch = -0.05 to -1.0 (back/nose up): 550-880 Hz (rising sweep)

        Args:
            pitch: Pitch control position (-1.0 to 1.0).
        """
        if not self.audio_engine:
            return

        # Threshold for silence (dead zone around neutral)
        silence_threshold = 0.05

        # If pitch is near neutral, stop any active tone
        if abs(pitch) < silence_threshold:
            if self._pitch_tone_active:
                if self._pitch_tone_channel is not None:
                    from contextlib import suppress

                    with suppress(Exception):
                        self.audio_engine.stop_source(self._pitch_tone_channel)
                    self._pitch_tone_channel = None
                self._pitch_tone_active = False
                self._last_pitch_freq = 440.0
            return

        # Calculate frequency based on pitch position
        # Base frequency is 440 Hz (A4)
        # Range: 220 Hz (pitch = +1.0) to 880 Hz (pitch = -1.0)
        base_freq = 440.0
        # Map pitch from [-1.0, 1.0] to frequency [880, 220]
        # Higher pitch (nose up) = higher frequency
        freq = base_freq * (2.0 ** (-pitch))  # Exponential mapping for musical scale

        # Only update if frequency changed significantly (creates sweeping effect)
        freq_change_threshold = 10.0  # Hz
        if abs(freq - self._last_pitch_freq) < freq_change_threshold:
            return  # No significant change, don't restart beep

        self._last_pitch_freq = freq

        # Stop previous beep
        if self._pitch_tone_channel is not None:
            from contextlib import suppress

            with suppress(Exception):
                self.audio_engine.stop_source(self._pitch_tone_channel)
            self._pitch_tone_channel = None

        # Generate and play new beep at current frequency
        import tempfile
        import wave

        import numpy as np

        # Generate short beep (100ms for rapid updates)
        sample_rate = 44100
        duration = 0.1  # 100ms beep
        samples = int(sample_rate * duration)

        # Create sine wave at current frequency
        t = np.linspace(0, duration, samples, False)
        tone = np.sin(2 * np.pi * freq * t)

        # Apply envelope (fade in/out to avoid clicks)
        fade_samples = int(sample_rate * 0.01)  # 10ms fade
        fade_in = np.linspace(0, 1, fade_samples)
        fade_out = np.linspace(1, 0, fade_samples)
        tone[:fade_samples] *= fade_in
        tone[-fade_samples:] *= fade_out

        # Convert to float32
        tone = tone.astype(np.float32) * 0.25  # Volume

        try:
            # Create temporary WAV file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
                temp_path = temp_wav.name

            # Write WAV file
            with wave.open(temp_path, "wb") as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(sample_rate)
                tone_int16 = (tone * 32767).astype(np.int16)
                wav_file.writeframes(tone_int16.tobytes())

            # Load and play the sound (non-looping)
            sound = self.audio_engine.load_sound(temp_path)
            if sound is not None:
                self._pitch_tone_channel = self.audio_engine.play_2d(sound, loop=False, volume=0.5)
                self._pitch_tone_active = True
                logger.debug(f"Pitch sweep: {freq:.1f} Hz (pitch={pitch:.2f})")

            # Clean up temp file
            import os
            from contextlib import suppress

            with suppress(Exception):
                os.unlink(temp_path)

        except Exception as e:
            logger.warning(f"Failed to play pitch sweep tone: {e}")

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
            self.context.message_queue.unsubscribe(
                "navigation.entered_taxiway", self.handle_message
            )
            self.context.message_queue.unsubscribe("navigation.entered_runway", self.handle_message)
            self.context.message_queue.unsubscribe(
                "navigation.entered_parking", self.handle_message
            )
            self.context.message_queue.unsubscribe("navigation.entered_apron", self.handle_message)
            self.context.message_queue.unsubscribe(
                "navigation.location_changed", self.handle_message
            )

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

            # Gear change (skip for fixed gear aircraft)
            if "gear" in data and self.sound_manager and not self._fixed_gear:
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

            # Pitch control feedback with continuous tone
            # Tone plays continuously while yoke is deflected, stops at neutral
            if "pitch" in data and self.audio_engine:
                pitch = data["pitch"]
                # Update tone frequency to match current pitch position
                # Tone starts when pitch moves away from neutral, stops when returning to neutral
                self._update_pitch_feedback_tone(pitch)
                self._last_pitch_control = pitch

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
            if "angle_of_attack_deg" in data:
                aoa_value = data["angle_of_attack_deg"]
                if aoa_value is not None:
                    self._angle_of_attack = aoa_value

            # Update wind sound based on airspeed (only when airborne)
            if "airspeed" in data and self.sound_manager:
                airspeed = data["airspeed"]
                on_ground = data.get("on_ground", True)  # Default to on_ground if not provided
                self.sound_manager.update_wind_sound(airspeed, on_ground)

            # Update rolling sound based on ground speed, on_ground status, and surface type
            if "groundspeed" in data and "on_ground" in data and self.sound_manager:
                ground_speed = data["groundspeed"]
                on_ground = data["on_ground"]
                self.sound_manager.update_rolling_sound(
                    ground_speed, on_ground, self._current_surface_type
                )

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

            # Start/stop engine sound based on ENGINE RUNNING state
            # Only play engine sounds when the engine actually catches and runs
            # Do NOT play sounds just from starter cranking
            if self.sound_manager and hasattr(self, "_engine_sound_active"):
                if engine_running and not self._engine_sound_active:
                    # Engine started: Play start.wav -> idle.wav sequence
                    # Check if we have the new sound sequence configured
                    if (
                        hasattr(self.sound_manager, "_engine_start_path")
                        and self.sound_manager._engine_start_path
                    ):
                        # New format: use start_engine_sequence (start.wav -> idle.wav)
                        self.sound_manager.start_engine_sequence()
                        logger.info(
                            f"Engine started: sound sequence playing (RPM = {engine_rpm:.0f})"
                        )
                    else:
                        # Old format: use single engine sound
                        engine_sound_path = getattr(
                            self, "_engine_sound_path", "assets/sounds/aircraft/engine.wav"
                        )
                        self.sound_manager.start_engine_sound(engine_sound_path)
                        logger.info(f"Engine started: sound playing (RPM = {engine_rpm:.0f})")
                    self._engine_sound_active = True
                elif not engine_running and self._engine_sound_active:
                    # Engine stopped: Play shutdown.wav and stop idle loop
                    if hasattr(self.sound_manager, "stop_engine_sound"):
                        # New format: stop with shutdown.wav
                        self.sound_manager.stop_engine_sound(play_shutdown=True)
                        logger.info("Engine stopped: shutdown sound playing")
                    else:
                        # Old format: just stop the sound
                        if (
                            hasattr(self.sound_manager, "_engine_source_id")
                            and self.sound_manager._engine_source_id is not None
                        ):
                            self.sound_manager.stop_sound(self.sound_manager._engine_source_id)
                            self.sound_manager._engine_source_id = None
                        logger.info("Engine stopped: sound stopped")
                    self._engine_sound_active = False

                # Update engine sound pitch based on RPM
                if self._engine_sound_active and engine_rpm > 0:
                    # Get engine RPM limits from config or use defaults
                    max_rpm = 2700.0  # Cessna 172 max RPM
                    # Map RPM directly to throttle (0 RPM = 0.0, max RPM = 1.0)
                    # This works correctly for both cranking (low RPM) and running
                    throttle = max(0.0, min(1.0, engine_rpm / max_rpm))
                    self.sound_manager.update_engine_sound(throttle)
                    logger.debug(
                        f"Engine sound updated: {engine_rpm:.0f} RPM → throttle {throttle:.2f}"
                    )

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
            # Handle click sound request from panel controls (3D spatialized)
            if self.sound_manager:
                control_type = message.data.get("control_type", "knob")
                control_name = message.data.get("control_name")  # For 3D spatial positioning

                # Use spatialized sound methods based on control type
                if control_type == "switch":
                    self.sound_manager.play_switch_sound(control_name=control_name)
                elif control_type == "button":
                    self.sound_manager.play_button_sound(control_name=control_name)
                else:  # knob or slider
                    self.sound_manager.play_knob_sound(control_name=control_name)

        elif message.topic.startswith("navigation."):
            # Handle navigation location messages for surface type tracking
            data = message.data
            if "surface_type" in data:
                new_surface = data["surface_type"]
                if new_surface != self._current_surface_type:
                    logger.debug(
                        f"Surface type changed: {self._current_surface_type} -> {new_surface}"
                    )
                    self._current_surface_type = new_surface

        # Altimeter instrument messages
        elif message.topic == "instruments.read_altimeter":
            # Announce current altimeter setting
            self._announce_altimeter_value()

        elif message.topic == "instruments.altimeter":
            # Altimeter value changed from panel control (slider)
            data = message.data
            if "value" in data:
                # Value is in inHg * 100 (e.g., 2992 = 29.92 inHg)
                value_x100 = data["value"]
                self._altimeter.set_value(value_x100 / 100.0, "inHg")
                logger.debug(f"Altimeter set from panel: {value_x100 / 100.0:.2f} inHg")

        # Altimeter input actions from context system
        elif message.topic == "input.altimeter_increase":
            self._handle_altimeter_increase()

        elif message.topic == "input.altimeter_decrease":
            self._handle_altimeter_decrease()

        elif message.topic == "input.altimeter_toggle_unit":
            self._handle_altimeter_toggle_unit()

        elif message.topic == "input.altimeter_enter_digit":
            # Extract the key that was pressed to get the digit
            key = message.data.get("key")
            if key is not None:
                self._handle_altimeter_digit(key)

        elif message.topic == "input.altimeter_confirm_entry":
            self._handle_altimeter_confirm()

        elif message.topic == "input.altimeter_clear_entry":
            self._handle_altimeter_clear()

        elif message.topic == "input.altimeter_announce":
            self._announce_altimeter_value()

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

        # Handle trim adjustment sound and TTS
        # event.value is now in DEGREES (e.g., 5.0 = 5° nose up)
        if event.action == "trim_pitch_adjusted":
            if event.value is not None:
                trim_deg = float(event.value)
                # Store normalized value for internal use
                # Assuming C172-like range (-10 to +20), neutral at 0
                self._pitch_trim = trim_deg / 15.0  # Approximate normalization

            # Play click sound
            if self.sound_manager:
                self.sound_manager.play_sound_2d(
                    "assets/sounds/aircraft/click_knob.mp3", volume=0.3
                )

            # Announce trim position in degrees
            if self.tts_provider and event.value is not None:
                from airborne.audio.tts.base import TTSPriority

                trim_deg = float(event.value)
                rounded_deg = round(trim_deg)

                if abs(rounded_deg) < 1:
                    # Near neutral
                    message = t("cockpit.pitch_trim_neutral")
                else:
                    # Format: "Pitch trim 5 degrees nose up"
                    direction = t("cockpit.trim_nose_up") if rounded_deg > 0 else t("cockpit.trim_nose_down")
                    message = t("cockpit.pitch_trim_deg", value=abs(rounded_deg), direction=direction)

                self.tts_provider.speak(message, priority=TTSPriority.HIGH, interrupt=True)
            return

        # Handle rudder trim adjustment sound and TTS
        if event.action == "trim_rudder_adjusted":
            if event.value is not None:
                trim_deg = float(event.value)
                self._rudder_trim = trim_deg / 15.0  # Approximate normalization

            # Play click sound
            if self.sound_manager:
                self.sound_manager.play_sound_2d(
                    "assets/sounds/aircraft/click_knob.mp3", volume=0.3
                )

            # Announce rudder trim position in degrees
            if self.tts_provider and event.value is not None:
                from airborne.audio.tts.base import TTSPriority

                trim_deg = float(event.value)
                rounded_deg = round(trim_deg)

                if abs(rounded_deg) < 1:
                    # Near neutral
                    message = t("cockpit.rudder_trim_neutral")
                else:
                    # Format: "Rudder trim 3 degrees right"
                    direction = t("cockpit.trim_right") if rounded_deg > 0 else t("cockpit.trim_left")
                    message = t("cockpit.rudder_trim_deg", value=abs(rounded_deg), direction=direction)

                self.tts_provider.speak(message, priority=TTSPriority.HIGH, interrupt=True)
            return

        # Handle parking brake click sound (3D spatialized, then continue to TTS)
        if event.action in ("parking_brake_set", "parking_brake_release") and self.sound_manager:
            self.sound_manager.play_switch_sound(
                switch_on=(event.action == "parking_brake_set"),
                control_name="parking_brake",
            )

        # Handle throttle released (announce percent)
        if event.action == "throttle_released" and event.value is not None:
            if self.tts_provider:
                throttle_percent = int(event.value)
                message = t("actions.throttle_percent", value=throttle_percent)
                # Interrupt any current speech to announce throttle immediately
                self.tts_provider.speak(message, interrupt=True)
            return

        # Handle flaps commanded (announce target position)
        if event.action == "flaps_commanded" and event.value is not None:
            if self.tts_provider:
                from airborne.audio.tts.base import TTSPriority

                flap_degrees = int(event.value)
                if flap_degrees == 0:
                    message = t("actions.flaps_up")
                else:
                    message = t("actions.flaps_degrees", value=flap_degrees)
                self.tts_provider.speak(message, priority=TTSPriority.HIGH, interrupt=True)
            return

        # Handle flaps set (announce when flaps reach target position)
        if event.action == "flaps_set" and event.value is not None:
            if self.tts_provider:
                from airborne.audio.tts.base import TTSPriority

                flap_degrees = int(event.value)
                if flap_degrees == 0:
                    message = t("actions.flaps_up_set")
                else:
                    message = t("actions.flaps_degrees_set", value=flap_degrees)
                self.tts_provider.speak(message, priority=TTSPriority.NORMAL)
            return

        # Handle flaps read (announce current flap position)
        if event.action == "flaps_read" and event.value is not None:
            if self.tts_provider:
                from airborne.audio.tts.base import TTSPriority

                flap_degrees = int(event.value)
                if flap_degrees == 0:
                    message = t("actions.flaps_up")
                else:
                    message = t("actions.flaps_degrees", value=flap_degrees)
                self.tts_provider.speak(message, priority=TTSPriority.HIGH, interrupt=True)
            return

        # Handle auto-trim enabled
        if event.action == "auto_trim_enabled":
            if self.tts_provider:
                from airborne.audio.tts.base import TTSPriority

                message = t("actions.auto_trim_on")
                self.tts_provider.speak(message, priority=TTSPriority.HIGH, interrupt=True)
            return

        # Handle auto-trim disabled
        if event.action == "auto_trim_disabled":
            if self.tts_provider:
                from airborne.audio.tts.base import TTSPriority

                message = t("actions.auto_trim_off")
                self.tts_provider.speak(message, priority=TTSPriority.HIGH, interrupt=True)
            return

        # Handle auto-trim read (announce status)
        if event.action == "auto_trim_read":
            if self.tts_provider:
                from airborne.audio.tts.base import TTSPriority

                enabled = event.value is not None and event.value > 0.5
                message = t("actions.auto_trim_on") if enabled else t("actions.auto_trim_off")
                self.tts_provider.speak(message, priority=TTSPriority.HIGH, interrupt=True)
            return

        if not self.tts_provider:
            logger.warning("No TTS provider available for input action feedback")
            return

        message: str | None = None

        # Handle instrument readouts (using translations)
        if event.action == "read_airspeed":
            import math

            airspeed_val = 0 if math.isnan(self._airspeed) else int(self._airspeed)
            message = t("cockpit.airspeed_readout", value=airspeed_val)
        elif event.action == "read_altitude":
            import math

            # Use indicated altitude (adjusted for altimeter setting)
            indicated_alt = self.get_indicated_altitude()
            altitude_val = 0 if math.isnan(indicated_alt) else int(indicated_alt)
            message = t("cockpit.altitude_readout", value=altitude_val)
        elif event.action == "read_heading":
            import math

            heading_val = 0 if math.isnan(self._heading) else int(self._heading)
            message = t("cockpit.heading_readout", value=heading_val)
        elif event.action == "read_vspeed":
            # Format vertical speed with sign
            import math

            vspeed_int = 0 if math.isnan(self._vspeed) else int(self._vspeed)
            if vspeed_int > 0:
                message = t("cockpit.climbing_readout", value=vspeed_int)
            elif vspeed_int < 0:
                message = t("cockpit.descending_readout", value=abs(vspeed_int))
            else:
                message = t("cockpit.level")
        elif event.action == "read_attitude":
            # Format bank and pitch angles
            bank_int = int(self._bank)
            pitch_int = int(self._pitch)
            if bank_int == 0 and pitch_int == 0:
                message = t("cockpit.wings_level")
            elif bank_int == 0:
                pitch_key = "cockpit.pitch_up" if pitch_int > 0 else "cockpit.pitch_down"
                message = f"{t(pitch_key)} {abs(pitch_int)} {t('cockpit.degrees')}"
            elif pitch_int == 0:
                bank_key = "cockpit.bank_left" if bank_int < 0 else "cockpit.bank_right"
                message = f"{t(bank_key)} {abs(bank_int)} {t('cockpit.degrees')}"
            else:
                bank_key = "cockpit.bank_left" if bank_int < 0 else "cockpit.bank_right"
                pitch_key = "cockpit.pitch_up" if pitch_int > 0 else "cockpit.pitch_down"
                message = f"{t(bank_key)} {abs(bank_int)}, {t(pitch_key)} {abs(pitch_int)}"

        # Engine instrument readouts
        elif event.action == "read_rpm":
            if self._engine_running:
                message = t("cockpit.engine_rpm", value=int(self._engine_rpm))
            else:
                message = t("cockpit.engine_stopped")
        elif event.action == "read_manifold_pressure":
            message = t("cockpit.manifold_pressure", value=f"{self._manifold_pressure:.1f}")
        elif event.action == "read_oil_pressure":
            message = t("cockpit.oil_pressure", value=int(self._oil_pressure))
        elif event.action == "read_oil_temp":
            # Convert Celsius to Fahrenheit for readout
            oil_temp_f = self._oil_temp * 9 / 5 + 32
            message = t("cockpit.oil_temperature", value=int(oil_temp_f))
        elif event.action == "read_fuel_flow":
            message = t("cockpit.fuel_flow", value=f"{self._fuel_flow:.1f}")

        # Electrical instrument readouts
        elif event.action == "read_battery_voltage":
            message = t("cockpit.battery_volts", value=f"{self._battery_voltage:.1f}")
        elif event.action == "read_battery_percent":
            message = t("cockpit.battery_percent", value=int(self._battery_percent))
        elif event.action == "read_battery_status":
            if self._battery_current > 1.0:
                message = t("cockpit.battery_charging", value=f"{self._battery_current:.1f}")
            elif self._battery_current < -1.0:
                message = t(
                    "cockpit.battery_discharging", value=f"{abs(self._battery_current):.1f}"
                )
            else:
                message = t("cockpit.battery_stable")
        elif event.action == "read_alternator":
            message = t("cockpit.alternator_output", value=f"{self._alternator_output:.1f}")

        # Fuel instrument readouts
        elif event.action == "read_fuel_quantity":
            message = t("cockpit.fuel_quantity", value=f"{self._fuel_quantity:.1f}")
        elif event.action == "read_fuel_remaining":
            fuel_minutes = self._fuel_remaining_minutes or 0.0
            hours = int(fuel_minutes / 60)
            minutes = int(fuel_minutes % 60)
            if hours > 0:
                message = t("cockpit.fuel_remaining_hours", hours=hours, minutes=minutes)
            else:
                message = t("cockpit.fuel_remaining_minutes", value=minutes)

        # Comprehensive status readouts (Alt+5, Alt+6, Alt+7)
        elif event.action == "read_engine":
            if self._engine_running:
                message = t("cockpit.engine_rpm", value=int(self._engine_rpm))
            else:
                message = t("cockpit.engine_stopped")
        elif event.action == "read_electrical":
            message = (
                f"{t('cockpit.battery_volts', value=f'{self._battery_voltage:.1f}')} "
                f"{int(self._battery_percent)} {t('cockpit.percent')}"
            )
        elif event.action == "read_fuel":
            fuel_minutes = self._fuel_remaining_minutes or 0.0
            hours = int(fuel_minutes / 60)
            minutes = int(fuel_minutes % 60)
            if hours > 0:
                message = t(
                    "cockpit.fuel_status_hours",
                    gallons=f"{self._fuel_quantity:.1f}",
                    hours=hours,
                    minutes=minutes,
                )
            else:
                message = t(
                    "cockpit.fuel_status_minutes",
                    gallons=f"{self._fuel_quantity:.1f}",
                    minutes=minutes,
                )

        # Trim readouts
        elif event.action == "read_pitch_trim":
            # Convert trim value (-1.0 to 1.0) to percentage (0-100) for announcement
            trim_percent = int((self._pitch_trim + 1.0) * 50)
            message = t("cockpit.pitch_trim", value=trim_percent)
        elif event.action == "read_rudder_trim":
            # Convert trim value (-1.0 to 1.0) to direction for announcement
            if self._rudder_trim < -0.1:
                trim_dir = t("cockpit.trim_left")
            elif self._rudder_trim > 0.1:
                trim_dir = t("cockpit.trim_right")
            else:
                trim_dir = t("cockpit.trim_neutral")
            message = t("cockpit.rudder_trim", value=trim_dir)

        else:
            # Map actions to TTS announcements (using translations)
            # Skip gear_toggle announcement for fixed gear aircraft
            action_messages = {}
            if not self._fixed_gear:
                gear_key = "actions.gear_down" if self._last_gear_state > 0.5 else "actions.gear_up"
                action_messages["gear_toggle"] = t(gear_key)

            action_messages.update(
                {
                    "flaps_down": t("actions.flaps_extending"),
                    "flaps_up": t("actions.flaps_retracting"),
                    "throttle_increase": t("actions.throttle_increased"),
                    "throttle_decrease": t("actions.throttle_decreased"),
                    "throttle_full": t("actions.throttle_full"),
                    "throttle_idle": t("actions.throttle_idle"),
                    "brakes_on": t("actions.brakes_on"),
                    "parking_brake_set": t("actions.parking_brake_set"),
                    "parking_brake_release": t("actions.parking_brake_released"),
                    "pause": t("actions.paused"),
                    "tts_next": "Next",
                }
            )

            message = action_messages.get(event.action)

        if not message:
            logger.debug(f"No TTS message for action: {event.action}")
            return

        from airborne.audio.tts.base import TTSPriority

        # Determine priority: instrument readouts should interrupt previous readouts
        is_instrument_readout = event.action in (
            "read_airspeed",
            "read_altitude",
            "read_heading",
            "read_vspeed",
            "read_engine",
            "read_electrical",
            "read_fuel",
            "read_attitude",
            "read_pitch_trim",
            "read_rudder_trim",
        )
        priority = TTSPriority.HIGH if is_instrument_readout else TTSPriority.NORMAL
        # Interrupt previous speech for instrument readouts
        interrupt = is_instrument_readout

        # Speak translated text directly (all messages now use t() function)
        logger.info(f"Speaking translated: {message}")
        self.tts_provider.speak(message, priority=priority, interrupt=interrupt)

    # ==================== Altimeter Methods ====================

    def _announce_altimeter_value(self) -> None:
        """Announce current altimeter setting via TTS."""
        if not self.tts_provider:
            return

        from airborne.audio.tts.base import TTSPriority

        message = self._altimeter.get_display_string()
        logger.info(f"Announcing altimeter: {message}")
        self.tts_provider.speak(message, priority=TTSPriority.HIGH, interrupt=True)

    def _announce_altimeter_adjustment(self, value: float) -> None:
        """Announce altimeter value after knob adjustment.

        Args:
            value: New value in current display unit.
        """
        if not self.tts_provider:
            return

        from airborne.audio.tts.base import TTSPriority

        message = f"{int(value)}" if self._altimeter.unit == "hPa" else f"{value:.2f}"
        self.tts_provider.speak(message, priority=TTSPriority.HIGH, interrupt=True)

    def _handle_altimeter_increase(self) -> None:
        """Handle altimeter increase action from context system."""
        new_value = self._altimeter.increase()
        self._announce_altimeter_adjustment(new_value)

    def _handle_altimeter_decrease(self) -> None:
        """Handle altimeter decrease action from context system."""
        new_value = self._altimeter.decrease()
        self._announce_altimeter_adjustment(new_value)

    def _handle_altimeter_toggle_unit(self) -> None:
        """Handle altimeter unit toggle action from context system."""
        from airborne.audio.tts.base import TTSPriority

        new_unit = self._altimeter.toggle_unit()
        if self.tts_provider:
            unit_name = t("cockpit.hectopascals") if new_unit == "hPa" else t("cockpit.inches_hg")
            self.tts_provider.speak(unit_name, priority=TTSPriority.HIGH, interrupt=True)

    def _handle_altimeter_digit(self, key: int) -> None:
        """Handle digit entry for altimeter from context system.

        Args:
            key: pygame key code for the digit.
        """
        import pygame

        from airborne.audio.tts.base import TTSPriority

        # Map pygame key codes to digit characters
        digit_map = {
            pygame.K_0: "0",
            pygame.K_1: "1",
            pygame.K_2: "2",
            pygame.K_3: "3",
            pygame.K_4: "4",
            pygame.K_5: "5",
            pygame.K_6: "6",
            pygame.K_7: "7",
            pygame.K_8: "8",
            pygame.K_9: "9",
        }

        digit = digit_map.get(key)
        if digit:
            self._altimeter.add_digit(digit)
            if self.tts_provider:
                self.tts_provider.speak(digit, priority=TTSPriority.HIGH, interrupt=True)

    def _handle_altimeter_confirm(self) -> None:
        """Handle altimeter entry confirmation from context system."""
        from airborne.audio.tts.base import TTSPriority

        buffer = self._altimeter.get_input_buffer()
        if buffer:
            if self._altimeter.confirm_input():
                if self.tts_provider:
                    message = self._altimeter.get_display_string()
                    self.tts_provider.speak(
                        t("cockpit.altimeter_set", value=message),
                        priority=TTSPriority.HIGH,
                        interrupt=True,
                    )
            else:
                if self.tts_provider:
                    self.tts_provider.speak(
                        t("cockpit.altimeter_invalid"),
                        priority=TTSPriority.HIGH,
                        interrupt=True,
                    )
            self._altimeter.clear_input_buffer()

    def _handle_altimeter_clear(self) -> None:
        """Handle altimeter input buffer clear from context system."""
        from airborne.audio.tts.base import TTSPriority

        self._altimeter.clear_input_buffer()
        if self.tts_provider:
            self.tts_provider.speak(t("common.cleared"), priority=TTSPriority.NORMAL)

    def get_indicated_altitude(self) -> float:
        """Get indicated altitude based on current altimeter setting.

        Returns:
            Indicated altitude in feet.
        """
        return self._altimeter.get_indicated_altitude(self._altitude)

    @property
    def altimeter(self) -> AltimeterManager:
        """Get the altimeter manager instance."""
        return self._altimeter

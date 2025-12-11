"""ATC audio manager with radio effects.

This module manages ATC audio playback with realistic radio effect
filtering using FMOD DSP. ATC messages use pre-recorded speech files
(different voice from cockpit TTS) and are processed through a radio
effect chain to simulate VHF AM aviation radio communications.

Typical usage example:
    from airborne.audio.atc.atc_audio import ATCAudioManager

    atc_audio = ATCAudioManager(audio_engine, config_dir, speech_dir)
    atc_audio.play_atc_message("ATC_TOWER_CLEARED_TAKEOFF")
"""

import time
from pathlib import Path
from typing import Any

import yaml

try:
    import pyfmodex  # type: ignore[import-untyped]

    FMOD_AVAILABLE = True
except ImportError:
    FMOD_AVAILABLE = False
    pyfmodex = None

from airborne.audio.effects.radio_filter import RadioEffectFilter
from airborne.core.logging_system import get_logger
from airborne.core.resource_path import get_resource_path

logger = get_logger(__name__)


class ATCAudioManager:
    """Manages ATC audio playback with radio effects.

    Loads ATC message configurations, sets up radio effect DSP chain,
    and plays ATC messages with realistic radio filtering.

    The ATC voice is separate from cockpit TTS and uses a different
    voice (e.g., male voice for ATC, female voice for cockpit).

    Note:
        All playback methods are NON-BLOCKING. They start playback and return
        immediately. Use is_playing() to check if audio is still playing.

    Examples:
        >>> atc_audio = ATCAudioManager(engine, Path("config"), Path("data/atc/en"))
        >>> atc_audio.play_atc_message("ATC_TOWER_CLEARED_TAKEOFF")
        42  # Returns source ID
        >>> atc_audio.is_playing()
        True
    """

    def __init__(
        self, audio_engine: Any, config_dir: Path, speech_dir: Path, language: str = "en"
    ) -> None:
        """Initialize ATC audio manager.

        Args:
            audio_engine: FMOD audio engine instance.
            config_dir: Path to configuration directory (contains atc_en.yaml, radio_effects.yaml).
            speech_dir: Path to ATC speech files directory (e.g., data/atc/en/).
            language: Language code (default: "en").

        Note:
            If configuration files are not found, the manager will still
            initialize but with empty message mappings and default radio effect.
        """
        self._audio_engine = audio_engine
        self._speech_dir = speech_dir
        self._language = language
        self._radio_filter: RadioEffectFilter | None = None
        self._message_map: dict[str, str] = {}
        self._file_extension = "mp3"
        self._initialized = False
        self._ptt_config: dict[str, Any] = {}  # PTT beep configuration
        self._ptt_enabled = True
        self._static_layer_config: dict[str, Any] = {}  # Static layer configuration
        self._static_sound: Any = None  # Loaded static sound
        self._sidechain_dsp: Any = None  # Side-chain compressor DSP
        self._tts_provider: Any = None  # TTS provider for system TTS fallback
        self._current_voice_channel: Any = None  # Current playing voice channel
        self._current_static_channel_id: int | None = None  # Current static layer ID

        # Ensure speech directory exists
        if not self._speech_dir.exists():
            logger.warning(f"ATC speech directory does not exist: {self._speech_dir}")
            self._speech_dir.mkdir(parents=True, exist_ok=True)

        # Load ATC message configuration
        atc_config_file = config_dir / f"atc_{language}.yaml"
        self._load_atc_config(atc_config_file)

        # Load pilot message configuration
        pilot_config_file = config_dir / f"pilot_{language}.yaml"
        self._load_pilot_config(pilot_config_file)

        # Load radio effect configuration
        radio_config_file = config_dir / "radio_effects.yaml"
        self._load_radio_effect(radio_config_file)

        self._initialized = True
        logger.info(
            f"ATC audio manager initialized: {len(self._message_map)} messages, "
            f"radio effect {'enabled' if self._radio_filter else 'disabled'}"
        )

    def _load_atc_config(self, config_file: Path) -> None:
        """Load ATC message configuration from YAML.

        Args:
            config_file: Path to ATC configuration file (e.g., atc_en.yaml).

        The configuration file should have the format:
            language: en
            voice: Alex
            file_extension: mp3
            messages:
              ATC_TOWER_CLEARED_TAKEOFF: "runway_31_cleared_for_takeoff"
              ATC_GROUND_TAXI_RWY_31: "taxi_to_runway_31_via_alpha"
        """
        if not config_file.exists():
            logger.error(f"ATC config not found: {config_file}")
            logger.info("ATC messages will not be available until config is created")
            return

        try:
            with open(config_file, encoding="utf-8") as f:
                config = yaml.safe_load(f)

            self._file_extension = config.get("file_extension", "mp3")
            self._message_map = config.get("messages", {})

            voice = config.get("voice", "unknown")
            logger.info(
                f"Loaded {len(self._message_map)} ATC messages from {config_file} "
                f"(voice: {voice}, format: {self._file_extension})"
            )

        except Exception as e:
            logger.error(f"Error loading ATC config: {e}")

    def _load_pilot_config(self, config_file: Path) -> None:
        """Load pilot message configuration from YAML.

        Args:
            config_file: Path to pilot configuration file (e.g., pilot_en.yaml).

        The configuration file should have the format:
            language: en
            voice: Oliver
            file_extension: mp3
            messages:
              PILOT_REQUEST_STARTUP: "request_startup_clearance"
              PILOT_REQUEST_ATIS: "request_atis"
        """
        if not config_file.exists():
            logger.warning(f"Pilot config not found: {config_file}")
            logger.info("Pilot messages will not be available until config is created")
            return

        try:
            with open(config_file, encoding="utf-8") as f:
                config = yaml.safe_load(f)

            # Add pilot messages to the same message map
            pilot_messages = config.get("messages", {})
            self._message_map.update(pilot_messages)

            voice = config.get("voice", "unknown")
            logger.info(
                f"Loaded {len(pilot_messages)} pilot messages from {config_file} (voice: {voice})"
            )

        except Exception as e:
            logger.error(f"Error loading pilot config: {e}")

    def _load_radio_effect(self, config_file: Path) -> None:
        """Load and setup radio effect DSP.

        Args:
            config_file: Path to radio effects configuration file (radio_effects.yaml).

        If the configuration file is not found, a default radio effect
        configuration is used (300 Hz - 3400 Hz bandwidth, 10:1 compression).
        """
        if not config_file.exists():
            logger.warning(f"Radio effect config not found: {config_file}, using defaults")
            # Default radio effect configuration
            radio_config = {
                "highpass": {"enabled": True, "cutoff_hz": 300.0},
                "lowpass": {"enabled": True, "cutoff_hz": 3400.0},
                "compressor": {
                    "enabled": True,
                    "threshold_db": -20.0,
                    "ratio": 10.0,
                    "attack_ms": 1.0,
                    "release_ms": 100.0,
                },
                "distortion": {"enabled": False},
                "static_noise": {"enabled": False},
            }
        else:
            try:
                with open(config_file, encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                radio_config = config.get("radio_effect", {})
                # Store PTT beep configuration
                self._ptt_config = radio_config.get("ptt_beeps", {})
                self._ptt_enabled = self._ptt_config.get("enabled", True)
                # Store static layer configuration
                self._static_layer_config = radio_config.get("static_layer", {})
                logger.info(f"Loaded radio effect config from {config_file}")
            except Exception as e:
                logger.error(f"Error loading radio effect config: {e}, using defaults")
                radio_config = {}
                self._ptt_config = {}

        # Create radio filter
        try:
            # Get FMOD system from audio engine
            if hasattr(self._audio_engine, "_system"):
                self._radio_filter = RadioEffectFilter(self._audio_engine._system, radio_config)
                logger.info("Radio effect filter created successfully")
            else:
                logger.error("Audio engine does not have FMOD system, radio effect disabled")

        except Exception as e:
            logger.error(f"Failed to create radio filter: {e}")

        # Load static layer sound if enabled
        self._load_static_layer()

    def _load_static_layer(self) -> None:
        """Load static layer sound file if enabled.

        This loads the background static audio file that will be layered
        with voice transmissions.
        """
        if not self._static_layer_config.get("enabled", False):
            logger.debug("Static layer disabled")
            return

        static_file = self._static_layer_config.get("file", "")
        if not static_file:
            logger.warning("Static layer enabled but no file specified")
            return

        static_path = get_resource_path(static_file)
        if not static_path.exists():
            logger.warning(f"Static layer file not found: {static_path}")
            return

        try:
            # Load static sound with loop mode enabled at sound level
            # Use streaming mode for better performance with looping background sounds
            self._static_sound = self._audio_engine.load_sound(
                str(static_path), preload=False, loop_mode=True
            )
            logger.info(f"Loaded static layer (streaming, loop): {static_path}")
        except Exception as e:
            logger.error(f"Failed to load static layer: {e}")

    def _play_ptt_beep(self, beep_type: str = "start") -> None:
        """Play PTT (Push-to-Talk) beep sound.

        Args:
            beep_type: Type of beep - "start" or "end".

        Note:
            Generates a simple sine wave beep using FMOD oscillator.
            The beep is played through the radio effect filter.
        """
        if not self._ptt_enabled or not self._ptt_config:
            return

        beep_config = self._ptt_config.get(f"{beep_type}_beep", {})
        if not beep_config.get("enabled", True):
            return

        try:
            # Get beep parameters
            frequency = beep_config.get("frequency_hz", 1000.0)
            duration_ms = beep_config.get("duration_ms", 50)
            volume = beep_config.get("volume", 0.3)

            # Generate beep using FMOD oscillator
            system = self._audio_engine._system
            oscillator = system.create_dsp_by_type(__import__("pyfmodex").enums.DSP_TYPE.OSCILLATOR)

            # Set oscillator to sine wave
            oscillator.set_parameter_int(0, 0)  # Type: Sine wave
            oscillator.set_parameter_float(1, frequency)  # Frequency
            oscillator.set_parameter_float(2, volume)  # Volume

            # Create channel and add oscillator (play_dsp returns tuple: (channel, dsp_connection))
            result = system.play_dsp(oscillator)
            if isinstance(result, tuple):
                channel, _ = result
            else:
                channel = result

            # Wait for duration
            time.sleep(duration_ms / 1000.0)

            # Stop and cleanup
            channel.stop()
            oscillator.release()

            logger.debug(f"Played PTT {beep_type} beep: {frequency}Hz, {duration_ms}ms")

        except Exception as e:
            logger.warning(f"Error playing PTT beep: {e}")

    def set_tts_provider(self, tts_provider: Any) -> None:
        """Set the TTS provider for system TTS fallback.

        When pre-recorded audio files don't exist, the manager can fall back
        to generating audio using the system TTS provider.

        Args:
            tts_provider: TTS provider instance with _get_realtime_tts() method.
        """
        self._tts_provider = tts_provider
        logger.info("TTS provider set for ATC audio manager")

    def set_radio_speaker_position(self, position: Any) -> None:
        """Set the 3D position of the radio speaker for spatial audio.

        Args:
            position: Vector3 position of the radio speaker in cockpit space.

        Note:
            Currently ATC audio uses 2D playback, so this position is stored
            but not actively used. In future, could enable 3D positional audio
            for more realistic radio speaker placement.
        """
        self._radio_speaker_position = position
        logger.debug(f"Radio speaker position set: ({position.x:.2f}, {position.y:.2f}, {position.z:.2f})")

    def _get_voice_for_key(self, key: str) -> str:
        """Get the appropriate TTS voice for a message key.

        Args:
            key: Message key (e.g., "PILOT_REQUEST_STARTUP", "ATC_CLEARED").

        Returns:
            Voice name (tower, pilot, etc.).
        """
        if key.startswith("PILOT_"):
            return "pilot"
        return "tower"

    def _generate_tts_audio(self, text: str, voice: str) -> bytes | None:
        """Generate audio bytes using system TTS.

        Args:
            text: Text to speak.
            voice: Voice name (tower, pilot, etc.).

        Returns:
            Audio bytes or None if generation failed.
        """
        if not self._tts_provider:
            return None

        if not hasattr(self._tts_provider, "_get_realtime_tts"):
            return None

        realtime_tts = self._tts_provider._get_realtime_tts(voice)
        if not realtime_tts:
            return None

        result = realtime_tts.generate_audio_bytes(text)
        if not result:
            return None

        audio_bytes, _ = result
        return audio_bytes

    def play_atc_message(self, message_key: str | list[str], volume: float = 1.0) -> int | None:
        """Play an ATC message with radio effect and static layer (NON-BLOCKING).

        Args:
            message_key: Message key (e.g., "ATC_TOWER_CLEARED_TAKEOFF") or
                        list of keys to play in sequence.
            volume: Volume level (0.0 to 1.0, default: 1.0).

        Returns:
            Source ID of the last played sound, or None if playback failed.

        Note:
            This method is NON-BLOCKING. It starts playback and returns immediately.
            Use is_playing() to check if audio is still playing.

            If message key is not found in configuration, a warning is logged
            and None is returned. If pre-recorded file doesn't exist but a TTS
            provider is set, it will fall back to system TTS.

        Examples:
            >>> # Single message
            >>> atc_audio.play_atc_message("ATC_TOWER_CLEARED_TAKEOFF")
            42
            >>> atc_audio.is_playing()
            True
        """
        if not self._initialized:
            logger.warning("ATC audio manager not initialized")
            return None

        # Convert single key to list (but only play first for now in non-blocking mode)
        message_keys = [message_key] if isinstance(message_key, str) else message_key

        if not message_keys:
            return None

        # Start static layer (if enabled)
        self._current_static_channel_id = self._start_static_layer()

        source_id = None

        # Play the first message (sequence playback would need different handling)
        key = message_keys[0]

        # Resolve message key to filename
        filename_base = self._message_map.get(key)
        if not filename_base:
            logger.warning(f"ATC message key not found: {key}")
            self._stop_static_layer(self._current_static_channel_id)
            return None

        filename = f"{filename_base}.{self._file_extension}"
        filepath = self._speech_dir / filename

        # Try to load pre-recorded file, fall back to TTS if not found
        sound = None
        use_tts = False

        if filepath.exists():
            # Use pre-recorded file
            try:
                sound = self._audio_engine.load_sound(str(filepath))
            except Exception as e:
                logger.error(f"Error loading ATC audio file {filepath}: {e}")
        else:
            # Fall back to system TTS
            if self._tts_provider:
                # Convert filename to spoken text (replace underscores with spaces)
                spoken_text = filename_base.replace("_", " ")
                voice = self._get_voice_for_key(key)
                audio_bytes = self._generate_tts_audio(spoken_text, voice)
                if audio_bytes:
                    try:
                        sound = self._audio_engine.load_sound_from_bytes(audio_bytes, f"tts_{key}")
                        use_tts = True
                    except Exception as e:
                        logger.error(f"Error loading TTS audio for {key}: {e}")
                else:
                    logger.warning(f"TTS generation failed for: {key}")
            else:
                logger.warning(f"ATC speech file not found and no TTS fallback: {filepath}")

        if not sound:
            self._stop_static_layer(self._current_static_channel_id)
            return None

        # Play sound (NON-BLOCKING)
        try:
            source_id = self._audio_engine.play_2d(sound, volume=volume, pitch=1.0, loop=False)

            # Get the voice channel for radio effect
            if source_id:
                self._current_voice_channel = self._audio_engine._channels.get(source_id)

            # Apply radio effect to the channel
            if self._radio_filter and self._radio_filter.is_enabled() and source_id:
                if self._current_voice_channel:
                    self._radio_filter.apply_to_channel(self._current_voice_channel)
                    mode = "TTS" if use_tts else "file"
                    logger.info(f"Playing ATC message with radio effect ({mode}): {key}")
                else:
                    logger.warning(f"Channel not found for source {source_id}")
            else:
                logger.info(f"Playing ATC message without radio effect: {key}")

            # NON-BLOCKING: Return immediately, caller uses is_playing() to check status

        except Exception as e:
            logger.error(f"Error playing ATC message {key}: {e}")
            self._stop_static_layer(self._current_static_channel_id)
            return None

        return source_id

    def play_dynamic_text(
        self,
        audio_bytes: bytes,
        volume: float = 1.0,
        name: str = "dynamic_tts",
    ) -> int | None:
        """Play dynamically generated audio (e.g., system TTS) with radio effects (NON-BLOCKING).

        This method allows playing audio generated at runtime (like ATIS from
        system TTS) through the same radio effect chain as pre-recorded messages.

        Args:
            audio_bytes: Raw audio data (WAV format).
            volume: Volume level (0.0 to 1.0, default: 1.0).
            name: Name for the sound (for logging).

        Returns:
            Source ID of the played sound, or None if playback failed.

        Note:
            This method is NON-BLOCKING. It starts playback and returns immediately.
            Use is_playing() to check if audio is still playing.

        Examples:
            >>> # Generate TTS audio bytes
            >>> audio_bytes = tts.generate_audio_bytes("Hello world")
            >>> atc_audio.play_dynamic_text(audio_bytes, name="atis")
            42
            >>> atc_audio.is_playing()
            True
        """
        if not self._initialized:
            logger.warning("ATC audio manager not initialized")
            return None

        if not audio_bytes:
            logger.warning("No audio bytes provided for dynamic text")
            return None

        # Start static layer (if enabled)
        self._current_static_channel_id = self._start_static_layer()

        source_id = None

        try:
            # Load sound from bytes
            sound = self._audio_engine.load_sound_from_bytes(audio_bytes, name)
            if not sound:
                logger.error(f"Failed to load dynamic audio: {name}")
                self._stop_static_layer(self._current_static_channel_id)
                return None

            # Play the sound (NON-BLOCKING)
            source_id = self._audio_engine.play_2d(sound, volume=volume, pitch=1.0, loop=False)

            # Get the voice channel for radio effect
            if source_id:
                self._current_voice_channel = self._audio_engine._channels.get(source_id)

            # Apply radio effect to the channel
            if self._radio_filter and self._radio_filter.is_enabled() and source_id:
                if self._current_voice_channel:
                    self._radio_filter.apply_to_channel(self._current_voice_channel)
                    logger.info(f"Playing dynamic text with radio effect: {name}")
                else:
                    logger.warning(f"Channel not found for source {source_id}")
            else:
                logger.info(f"Playing dynamic text without radio effect: {name}")

            # NON-BLOCKING: Return immediately, caller uses is_playing() to check status

        except Exception as e:
            logger.error(f"Error playing dynamic text {name}: {e}")
            self._stop_static_layer(self._current_static_channel_id)
            return None

        return source_id

    def play_dynamic_speech(
        self,
        text: str,
        sender: str = "ATC",
        volume: float = 1.0,
    ) -> int | None:
        """Play dynamically generated speech text with radio effects.

        This method generates TTS audio from text and plays it through the
        radio effect chain. Used for dynamic phraseology generated at runtime.

        Args:
            text: Text to speak (e.g., "Palo Alto Ground, Skyhawk November...").
            sender: Who is speaking - "PILOT" or "ATC" (determines voice).
            volume: Volume level (0.0 to 1.0, default: 1.0).

        Returns:
            Source ID of the played sound, or None if playback failed.

        Examples:
            >>> atc_audio.play_dynamic_speech(
            ...     "Palo Alto Ground, Skyhawk one two three, request taxi",
            ...     sender="PILOT"
            ... )
            42
        """
        if not self._initialized:
            logger.warning("ATC audio manager not initialized")
            return None

        if not text or not text.strip():
            logger.warning("Empty text provided for dynamic speech")
            return None

        # Select voice based on sender
        voice = "pilot" if sender == "PILOT" else "tower"

        # Generate TTS audio bytes
        audio_bytes = self._generate_tts_audio(text, voice)
        if not audio_bytes:
            logger.warning(f"Failed to generate TTS audio for: {text[:50]}...")
            return None

        # Play with radio effects
        name = f"dynamic_{sender.lower()}"
        return self.play_dynamic_text(audio_bytes, volume=volume, name=name)

    def _start_static_layer(self) -> int | None:
        """Start playing the static layer sound.

        Returns:
            Source ID of the static channel, or None if not enabled/failed.
        """
        if not self._static_layer_config.get("enabled", False) or not self._static_sound:
            return None

        try:
            static_volume = self._static_layer_config.get("volume", 0.15)

            # Play static sound in loop mode
            static_id: int | None = self._audio_engine.play_2d(
                self._static_sound, volume=static_volume, pitch=1.0, loop=True
            )

            if static_id:
                static_channel = self._audio_engine._channels.get(static_id)

                # Verify loop is actually set
                if static_channel:
                    logger.info(
                        f"Started static layer (source {static_id}, loop_count={static_channel.loop_count})"
                    )

                    if static_channel.loop_count != -1:
                        logger.warning(
                            f"Static layer loop_count is {static_channel.loop_count}, expected -1 for infinite loop"
                        )

                    if self._static_layer_config.get("ducking", {}).get("enabled", False):
                        # Apply side-chain compressor to duck static when voice plays
                        self._setup_sidechain_ducking(static_channel)
                else:
                    logger.warning(
                        f"Started static layer but channel not found (source {static_id})"
                    )

                return static_id

        except Exception as e:
            logger.error(f"Failed to start static layer: {e}")

        return None

    def _stop_static_layer(self, static_channel_id: int | None) -> None:
        """Stop the static layer sound.

        Args:
            static_channel_id: Source ID of the static channel to stop.
        """
        if not static_channel_id:
            return

        try:
            # Check if channel still exists and is playing
            from airborne.audio.engine.base import SourceState

            state = self._audio_engine.get_source_state(static_channel_id)
            if state != SourceState.STOPPED:
                self._audio_engine.stop_source(static_channel_id)
                logger.debug(f"Stopped static layer (source {static_channel_id})")
            else:
                logger.debug(f"Static layer already stopped (source {static_channel_id})")
        except Exception as e:
            logger.warning(f"Failed to stop static layer: {e}")

    def _setup_sidechain_ducking(self, static_channel: Any) -> None:
        """Setup side-chain compression to duck static when voice plays.

        Args:
            static_channel: FMOD channel for the static layer.

        Note:
            FMOD doesn't have built-in side-chain compression, so we use
            a regular compressor with aggressive settings to duck the static.
            This is a simplified approach - true side-chain would require
            analyzing voice channel amplitude and controlling static volume.
        """
        if not FMOD_AVAILABLE:
            return

        try:
            ducking_config = self._static_layer_config.get("ducking", {})
            threshold = ducking_config.get("threshold_db", -40.0)
            ratio = ducking_config.get("ratio", 4.0)
            attack = ducking_config.get("attack_ms", 10.0)
            release = ducking_config.get("release_ms", 200.0)

            # Create compressor DSP for ducking effect
            system = self._audio_engine._system
            compressor = system.create_dsp_by_type(pyfmodex.enums.DSP_TYPE.COMPRESSOR)

            compressor.set_parameter_float(0, threshold)
            compressor.set_parameter_float(1, ratio)
            compressor.set_parameter_float(2, attack)
            compressor.set_parameter_float(3, release)
            compressor.set_parameter_float(4, 0.0)  # No makeup gain

            # Add to static channel
            static_channel.add_dsp(0, compressor)
            compressor.active = True

            self._sidechain_dsp = compressor

            logger.debug(
                f"Setup side-chain ducking: threshold={threshold}dB, "
                f"ratio={ratio}:1, attack={attack}ms, release={release}ms"
            )

        except Exception as e:
            logger.warning(f"Could not setup side-chain ducking: {e}")

    def set_radio_effect_enabled(self, enabled: bool) -> None:
        """Enable or disable radio effect for ATC messages.

        Args:
            enabled: True to enable radio effect, False to disable.

        Note:
            When disabled, ATC messages will play without filtering.
        """
        if self._radio_filter:
            self._radio_filter.set_enabled(enabled)
            logger.info(f"Radio effect {'enabled' if enabled else 'disabled'}")
        else:
            logger.warning("Radio filter not initialized, cannot change state")

    def is_radio_effect_enabled(self) -> bool:
        """Check if radio effect is enabled.

        Returns:
            True if radio effect is enabled and functional.
        """
        return self._radio_filter is not None and self._radio_filter.is_enabled()

    def is_playing(self) -> bool:
        """Check if audio is currently playing.

        Returns:
            True if voice audio is currently playing.

        Examples:
            >>> atc_audio.play_atc_message("ATC_TOWER_CLEARED")
            42
            >>> atc_audio.is_playing()
            True
            >>> # After message finishes...
            >>> atc_audio.is_playing()
            False
        """
        if self._current_voice_channel:
            try:
                return bool(self._current_voice_channel.is_playing)
            except Exception:
                return False
        return False

    def update(self) -> None:
        """Update audio state and cleanup finished playback.

        Call this method every frame to check if playback has finished
        and clean up resources (stop static layer, etc.).

        Note:
            This is essential for non-blocking audio to work correctly.
            If not called, the static layer will continue playing after
            the voice has finished.
        """
        # Check if voice finished playing
        if self._current_voice_channel and not self.is_playing():
            # Voice finished, cleanup
            self._stop_static_layer(self._current_static_channel_id)
            self._current_voice_channel = None
            self._current_static_channel_id = None
            logger.debug("Voice playback finished, cleaned up static layer")

    def get_available_messages(self) -> list[str]:
        """Get list of available ATC message keys.

        Returns:
            List of message key strings.

        Examples:
            >>> messages = atc_audio.get_available_messages()
            >>> print(messages)
            ['ATC_TOWER_CLEARED_TAKEOFF', 'ATC_GROUND_TAXI_RWY_31', ...]
        """
        return list(self._message_map.keys())

    def shutdown(self) -> None:
        """Shutdown ATC audio manager.

        Releases radio effect DSP resources and static layer. Should be
        called when the manager is no longer needed.
        """
        if self._radio_filter:
            self._radio_filter.shutdown()
            self._radio_filter = None

        if self._sidechain_dsp:
            try:
                self._sidechain_dsp.release()
            except Exception as e:
                logger.warning(f"Error releasing side-chain DSP: {e}")
            self._sidechain_dsp = None

        self._static_sound = None
        self._initialized = False
        logger.info("ATC audio manager shut down")

"""Audio file-based TTS provider implementation.

This module provides a TTS implementation using pre-recorded audio files (OGG format)
instead of real-time text-to-speech synthesis. Messages are mapped to audio files
using YAML configuration files in config/speech_{language}.yaml.

Typical usage example:
    from airborne.audio.tts.audio_provider import AudioSpeechProvider
    from airborne.audio.tts.speech_messages import MSG_STARTUP

    tts = AudioSpeechProvider()
    tts.initialize({"language": "en", "audio_engine": engine})
    tts.speak(MSG_STARTUP)
"""

import contextlib
import threading
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

try:
    import pyfmodex
    from pyfmodex.enums import CHANNELCONTROL_CALLBACK_TYPE
except ImportError:
    pyfmodex = None
    CHANNELCONTROL_CALLBACK_TYPE = None

from airborne.audio.tts.base import ITTSProvider, TTSPriority, TTSState
from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


class SpeechItem:
    """Item in the speech queue."""

    def __init__(
        self,
        text: str,
        priority: TTSPriority,
        callback: Callable[[], None] | None = None,
    ) -> None:
        """Initialize speech item.

        Args:
            text: Text to speak (will be mapped to audio file).
            priority: Priority level.
            callback: Optional completion callback.
        """
        self.text = text
        self.priority = priority
        self.callback = callback


class AudioSpeechProvider(ITTSProvider):
    """Audio file-based TTS provider.

    Uses pre-recorded audio files (OGG format) with YAML-based configuration.
    Messages are identified by keys (e.g., MSG_STARTUP) and mapped to audio files
    via config/speech_{language}.yaml.

    Examples:
        >>> from airborne.audio.tts.speech_messages import MSG_STARTUP
        >>> tts = AudioSpeechProvider()
        >>> tts.initialize({"language": "en", "audio_engine": engine})
        >>> tts.speak(MSG_STARTUP)
        >>> tts.shutdown()
    """

    def __init__(self) -> None:
        """Initialize the provider (not started yet)."""
        self._initialized = False
        self._state = TTSState.IDLE
        self._queue: deque[SpeechItem] = deque()
        self._current_item: SpeechItem | None = None
        self._lock = threading.Lock()
        self._stop_requested = False
        self._shutdown_requested = False
        self._speech_dir = Path("data/speech")
        self._config_dir = Path("config")
        self._language = "en"
        self._file_extension = "wav"
        self._message_map: dict[str, dict[str, str]] = {}  # key -> {text, voice}
        self._voice_dirs: dict[str, Path] = {}  # voice -> directory path

        # Audio engine reference (will be injected)
        self._audio_engine: Any = None
        self._current_source_id: int | None = None

        # Sequential playback queue
        self._playback_queue: deque[Any] = deque()  # Preloaded sound objects
        self._playing = False
        self._callback_lock = threading.Lock()  # Protect callback access

    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize audio speech provider.

        Args:
            config: Configuration with keys:
                - language: Language code (default: "en")
                - speech_dir: Path to speech files directory (default: "data/speech")
                - config_dir: Path to config directory (default: "config")
                - audio_engine: Reference to audio engine (required)
        """
        if self._initialized:
            logger.warning("AudioSpeechProvider already initialized")
            return

        self._language = config.get("language", "en")
        speech_dir = config.get("speech_dir", "data/speech")
        self._config_dir = Path(config.get("config_dir", "config"))
        self._speech_dir = Path(speech_dir) / self._language
        self._audio_engine = config.get("audio_engine")

        if not self._audio_engine:
            logger.error("No audio engine provided to AudioSpeechProvider")
            return

        # Load unified speech configuration YAML
        config_file = self._config_dir / "speech.yaml"
        if not config_file.exists():
            # Fall back to old format
            config_file = self._config_dir / f"speech_{self._language}.yaml"
            if not config_file.exists():
                logger.error(f"Speech config not found: {config_file}")
                return
            # Load old format
            try:
                with open(config_file, encoding="utf-8") as f:
                    speech_config = yaml.safe_load(f)
                self._file_extension = speech_config.get("file_extension", "wav")
                # Convert old format to new format
                old_messages = speech_config.get("messages", {})
                self._message_map = {key: {"text": key, "voice": "cockpit"} for key in old_messages}
                self._voice_dirs = {"cockpit": self._speech_dir}
                logger.info("Loaded %d speech messages (old format)", len(self._message_map))
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error(f"Error loading speech config: {e}")
                return
        else:
            # Load new unified format
            try:
                with open(config_file, encoding="utf-8") as f:
                    speech_config = yaml.safe_load(f)

                # Build voice directory map
                voices = speech_config.get("voices", {})
                for voice_name, voice_config in voices.items():
                    output_dir = voice_config.get("output_dir", voice_name)
                    self._voice_dirs[voice_name] = self._speech_dir / output_dir

                # Load messages
                self._message_map = speech_config.get("messages", {})
                self._file_extension = "wav"  # New format uses WAV to avoid MP3 decoder latency

                logger.info(
                    "Loaded %d speech messages from %s (%d voices)",
                    len(self._message_map),
                    config_file,
                    len(self._voice_dirs),
                )
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error(f"Error loading speech config: {e}")
                return

        # Create speech directory if it doesn't exist
        self._speech_dir.mkdir(parents=True, exist_ok=True)

        self._initialized = True
        logger.info(
            "AudioSpeechProvider initialized: language=%s, dir=%s, format=%s",
            self._language,
            self._speech_dir,
            self._file_extension,
        )

    def shutdown(self) -> None:
        """Shutdown audio speech provider."""
        if not self._initialized:
            return

        self.stop()
        self.clear_queue()
        self._initialized = False
        logger.info("AudioSpeechProvider shutdown")

    def speak(
        self,
        message_key: str | list[str],
        priority: TTSPriority = TTSPriority.NORMAL,
        interrupt: bool = False,
        callback: Callable[[], None] | None = None,
    ) -> None:
        """Speak message by playing corresponding audio file(s).

        Args:
            message_key: Message key or list of keys to play in sequence
                        (e.g., MSG_STARTUP or ["MSG_DIGIT_1", "MSG_DIGIT_2", "MSG_DIGIT_0"]).
            priority: Priority level.
            interrupt: If True, stop current speech.
            callback: Optional callback when done.
        """
        if not self._initialized:
            return

        # Convert single key to list
        if isinstance(message_key, str):
            if not message_key.strip():
                return
            message_keys = [message_key]
        else:
            message_keys = message_key

        if not message_keys:
            return

        # Stop current speech if interrupt or critical
        if interrupt or priority == TTSPriority.CRITICAL:
            self.stop()

        # Resolve all file paths and preload sounds
        sound_objects = []
        for key in message_keys:
            message_config = self._message_map.get(key)

            # If not in config, try to find file directly in voice directories
            if not message_config:
                # Try common voice directories: pilot, cockpit
                found = False
                for voice_name, voice_dir in self._voice_dirs.items():
                    filepath = voice_dir / f"{key}.{self._file_extension}"
                    if filepath.exists():
                        found = True
                        break

                if not found:
                    logger.warning(f"Message key not found: {key}")
                    continue
            else:
                # Get voice type and resolve directory from config
                voice = message_config.get("voice", "cockpit")
                voice_dir = self._voice_dirs.get(voice, self._speech_dir)

                # Build filename (use filename field from config, fallback to key name)
                filename_base = message_config.get("filename", key)
                filename = f"{filename_base}.{self._file_extension}"
                filepath = voice_dir / filename

                if not filepath.exists():
                    logger.warning(f"Speech file not found: {filepath}")
                    continue

            # Preload sound to avoid delays during playback
            if self._audio_engine:
                try:
                    sound = self._audio_engine.load_sound(str(filepath))
                    sound_objects.append(sound)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.error(f"Error preloading sound {filepath}: {e}")
                    continue

        if not sound_objects:
            logger.error(f"No valid speech files found for keys: {message_keys}")
            return

        # Add preloaded sounds to playback queue
        # If interrupt, clear existing queue
        if interrupt or priority == TTSPriority.CRITICAL:
            self._playback_queue.clear()
            self._playing = False
            if self._current_source_id is not None and self._audio_engine:
                with contextlib.suppress(Exception):
                    self._audio_engine.stop_source(self._current_source_id)
            self._current_source_id = None

        # Add new sounds to queue
        self._playback_queue.extend(sound_objects)

        self._state = TTSState.SPEAKING
        logger.info(f"Queued speech sequence: {message_keys} ({len(sound_objects)} files)")

        # Start playback if not already playing
        if not self._playing:
            self._play_next_in_sequence()

    def stop(self) -> None:
        """Stop current speech immediately."""
        if not self._initialized:
            return

        self._stop_requested = True
        if self._current_source_id is not None and self._audio_engine:
            try:
                self._audio_engine.stop_source(self._current_source_id)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error(f"Error stopping speech: {e}")
        self._state = TTSState.IDLE
        self._current_source_id = None
        self._playing = False
        self._playback_queue.clear()

        logger.debug("Stopped speech")

    def pause(self) -> None:
        """Pause current speech (not implemented for audio files)."""
        self.stop()
        self._state = TTSState.PAUSED

    def resume(self) -> None:
        """Resume speech (not implemented for audio files)."""
        self._state = TTSState.IDLE

    def is_speaking(self) -> bool:
        """Check if currently speaking.

        Returns:
            True if speaking.
        """
        with self._lock:
            return self._state == TTSState.SPEAKING

    def get_state(self) -> TTSState:
        """Get current TTS state.

        Returns:
            Current state.
        """
        with self._lock:
            return self._state

    def set_rate(self, rate: int) -> None:
        """Set speech rate (not applicable for pre-recorded audio).

        Args:
            rate: Words per minute (ignored).
        """
        logger.debug("set_rate not applicable for audio files")

    def set_volume(self, volume: float) -> None:
        """Set speech volume (not applicable for pre-recorded audio).

        Args:
            volume: Volume 0.0 to 1.0 (ignored).
        """
        logger.debug("set_volume not applicable for audio files")

    def set_voice(self, voice_id: str) -> None:
        """Set voice by ID (not applicable for pre-recorded audio).

        Args:
            voice_id: Voice identifier (ignored).
        """
        logger.debug("set_voice not applicable for audio files")

    def get_voices(self) -> list[dict[str, Any]]:
        """Get available voices.

        Returns:
            Empty list (pre-recorded audio).
        """
        return []

    def _on_sound_end(self, channelcontrol, controltype, callbacktype, data1, data2) -> None:
        """Callback when a sound finishes - immediately play next in sequence.

        This is called by FMOD's callback system when a channel stops.
        """
        try:
            with self._callback_lock:
                logger.debug("Sound finished via callback, playing next")
                self._playing = False
                self._current_source_id = None
                self._play_next_in_sequence()
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error(f"Error in sound end callback: {e}")

    def _play_next_in_sequence(self) -> None:
        """Play the next sound in the sequence (if any).

        Called either initially or from the callback when a sound finishes.
        """
        # Check state and pop sound from queue within lock
        with self._callback_lock:
            if not self._playback_queue:
                self._playing = False
                self._state = TTSState.IDLE
                logger.info("TTS playback complete")
                return

            if self._playing:
                return

            # Mark as playing before releasing lock
            self._playing = True
            sound = self._playback_queue.popleft()

        # Play sound OUTSIDE the lock to avoid blocking update()
        try:
            source_id = self._audio_engine.play_2d(
                sound,
                volume=1.0,
                pitch=1.0,
                loop=False,
            )
            self._current_source_id = source_id
            logger.info(
                f"TTS playing sound (source_id={source_id}, {len(self._playback_queue)} remaining)"
            )

            # Callback setup removed - using polling in update() instead
            # FMOD callbacks are complex and fallback polling works fine

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error(f"Error playing speech sound: {e}")
            self._playing = False
            # Try next sound
            if self._playback_queue:
                self._play_next_in_sequence()

    def update(self) -> None:
        """Update sequential playback - call every frame.

        Uses polling to detect when sounds finish and trigger the next in sequence.
        """
        if not self._initialized or not self._audio_engine:
            return

        # Fallback polling - check if sound finished
        if self._playing and self._current_source_id is not None:
            try:
                if hasattr(self._audio_engine, "_channels"):
                    channel = self._audio_engine._channels.get(self._current_source_id)
                    if channel:
                        try:
                            if not channel.is_playing:
                                # Sound finished - trigger next
                                logger.info("TTS sound finished")
                                self._playing = False
                                self._current_source_id = None
                                self._play_next_in_sequence()
                        except Exception as e:  # pylint: disable=broad-exception-caught
                            logger.error(f"Error checking channel.is_playing: {e}")
                    else:
                        # Channel not found means it was removed after finishing
                        logger.info("TTS sound finished")
                        self._playing = False
                        self._current_source_id = None
                        self._play_next_in_sequence()
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error(f"Error in update() polling: {e}")

    def clear_queue(self) -> None:
        """Clear the speech queue."""
        with self._lock:
            self._queue.clear()
        logger.debug("Cleared speech queue")

    def get_queue_length(self) -> int:
        """Get queue length.

        Returns:
            Number of queued items.
        """
        with self._lock:
            return len(self._queue)

"""Sound manager coordinating audio engine and TTS.

This module provides a high-level interface for managing all audio in the
flight simulator, coordinating the audio engine, TTS, and sound effects.

Typical usage example:
    from airborne.audio.sound_manager import SoundManager

    manager = SoundManager()
    manager.initialize(audio_engine, tts_provider)
    manager.play_sound_3d("engine.wav", position)
    manager.speak("Engine started")
"""

from typing import Any

from airborne.audio.engine.base import IAudioEngine, Sound, Vector3
from airborne.audio.tts.base import ITTSProvider, TTSPriority
from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


class SoundManager:
    """High-level sound manager.

    Coordinates audio engine and TTS provider, manages sound caching,
    and provides convenient methods for common audio operations.

    Examples:
        >>> from airborne.audio.engine.pybass_engine import PyBASSEngine
        >>> from airborne.audio.tts.pyttsx_provider import PyTTSXProvider
        >>>
        >>> manager = SoundManager()
        >>> manager.initialize(PyBASSEngine(), PyTTSXProvider())
        >>> manager.play_sound_2d("beep.wav")
        >>> manager.speak("Welcome to AirBorne")
    """

    def __init__(self) -> None:
        """Initialize the sound manager (not started yet)."""
        self._audio_engine: IAudioEngine | None = None
        self._tts_provider: ITTSProvider | None = None
        self._sound_cache: dict[str, Sound] = {}
        self._master_volume = 1.0
        self._tts_enabled = True

    def initialize(
        self,
        audio_engine: IAudioEngine,
        tts_provider: ITTSProvider,
        audio_config: dict[str, Any] | None = None,
        tts_config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize audio systems.

        Args:
            audio_engine: Audio engine instance.
            tts_provider: TTS provider instance.
            audio_config: Configuration for audio engine.
            tts_config: Configuration for TTS provider.
        """
        self._audio_engine = audio_engine
        self._tts_provider = tts_provider

        # Initialize audio engine
        if audio_config is None:
            audio_config = {"sample_rate": 44100, "enable_3d": True}
        self._audio_engine.initialize(audio_config)

        # Initialize TTS
        if tts_config is None:
            tts_config = {"rate": 200, "volume": 1.0}
        self._tts_provider.initialize(tts_config)

        logger.info("Sound manager initialized")

    def shutdown(self) -> None:
        """Shutdown all audio systems."""
        if self._tts_provider:
            self._tts_provider.shutdown()

        if self._audio_engine:
            # Unload all cached sounds
            for sound in list(self._sound_cache.values()):
                try:
                    self._audio_engine.unload_sound(sound)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.error("Error unloading sound: %s", e)

            self._audio_engine.shutdown()

        self._sound_cache.clear()
        logger.info("Sound manager shutdown")

    def load_sound(self, path: str, preload: bool = True) -> Sound:
        """Load a sound file.

        Args:
            path: Path to sound file.
            preload: Whether to load into memory.

        Returns:
            Loaded sound.
        """
        if not self._audio_engine:
            raise RuntimeError("Sound manager not initialized")

        # Check cache
        if path in self._sound_cache:
            return self._sound_cache[path]

        # Load sound
        sound = self._audio_engine.load_sound(path, preload)
        self._sound_cache[path] = sound
        return sound

    def play_sound_2d(
        self,
        path: str,
        volume: float = 1.0,
        pitch: float = 1.0,
        loop: bool = False,
    ) -> int:
        """Play a sound in 2D.

        Args:
            path: Path to sound file.
            volume: Volume level.
            pitch: Pitch multiplier.
            loop: Whether to loop.

        Returns:
            Source ID.
        """
        if not self._audio_engine:
            raise RuntimeError("Sound manager not initialized")

        sound = self.load_sound(path)
        return self._audio_engine.play_2d(sound, volume, pitch, loop)

    def play_sound_3d(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        path: str,
        position: Vector3,
        velocity: Vector3 | None = None,
        volume: float = 1.0,
        pitch: float = 1.0,
        loop: bool = False,
    ) -> int:
        """Play a sound in 3D.

        Args:
            path: Path to sound file.
            position: 3D position.
            velocity: 3D velocity.
            volume: Volume level.
            pitch: Pitch multiplier.
            loop: Whether to loop.

        Returns:
            Source ID.
        """
        if not self._audio_engine:
            raise RuntimeError("Sound manager not initialized")

        sound = self.load_sound(path)
        return self._audio_engine.play_3d(sound, position, velocity, volume, pitch, loop)

    def stop_sound(self, source_id: int) -> None:
        """Stop a playing sound.

        Args:
            source_id: Source ID.
        """
        if self._audio_engine:
            self._audio_engine.stop_source(source_id)

    def update_listener(
        self,
        position: Vector3,
        forward: Vector3,
        up: Vector3,
        velocity: Vector3 | None = None,
    ) -> None:
        """Update listener position and orientation.

        Args:
            position: Listener position.
            forward: Forward direction.
            up: Up direction.
            velocity: Listener velocity.
        """
        if self._audio_engine:
            self._audio_engine.set_listener(position, forward, up, velocity)

    def speak(
        self,
        text: str,
        priority: TTSPriority = TTSPriority.NORMAL,
        interrupt: bool = False,
    ) -> None:
        """Speak text using TTS.

        Args:
            text: Text to speak.
            priority: Speech priority.
            interrupt: Whether to interrupt current speech.
        """
        if not self._tts_enabled or not self._tts_provider:
            return

        self._tts_provider.speak(text, priority, interrupt)

    def stop_speech(self) -> None:
        """Stop current speech."""
        if self._tts_provider:
            self._tts_provider.stop()

    def set_master_volume(self, volume: float) -> None:
        """Set master volume for sounds.

        Args:
            volume: Volume level (0.0 to 1.0).
        """
        self._master_volume = max(0.0, min(1.0, volume))
        if self._audio_engine:
            self._audio_engine.set_master_volume(self._master_volume)

    def set_tts_enabled(self, enabled: bool) -> None:
        """Enable or disable TTS.

        Args:
            enabled: Whether TTS is enabled.
        """
        self._tts_enabled = enabled
        logger.info("TTS %s", "enabled" if enabled else "disabled")

    def is_speaking(self) -> bool:
        """Check if TTS is currently speaking.

        Returns:
            True if speaking.
        """
        if self._tts_provider:
            return self._tts_provider.is_speaking()
        return False

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

        # Active sound sources (for continuous sounds like engine)
        self._engine_source_id: int | None = None
        self._wind_source_id: int | None = None

        # Engine sound pitch configuration (can be overridden per aircraft)
        self._engine_pitch_idle = 0.7  # Pitch at 0% throttle
        self._engine_pitch_full = 1.3  # Pitch at 100% throttle

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

        # Initialize TTS only if config provided (may already be initialized)
        if tts_config is not None:
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

    def start_engine_sound(self, path: str = "assets/sounds/aircraft/engine.wav") -> None:
        """Start looping engine sound.

        Args:
            path: Path to engine sound file.
        """
        if not self._audio_engine:
            return

        # Stop existing engine sound
        if self._engine_source_id is not None:
            self._audio_engine.stop_source(self._engine_source_id)

        # Start new looping engine sound at low pitch/volume (idle)
        try:
            self._engine_source_id = self.play_sound_2d(path, volume=0.3, pitch=0.5, loop=True)
            logger.debug("Engine sound started")
        except FileNotFoundError:
            logger.warning(f"Engine sound not found: {path}")

    def update_engine_sound(self, throttle: float) -> None:
        """Update engine sound based on throttle.

        Args:
            throttle: Throttle position (0.0 to 1.0).
        """
        if not self._audio_engine or self._engine_source_id is None:
            return

        # Map throttle to pitch using configured range
        pitch = self._engine_pitch_idle + (
            throttle * (self._engine_pitch_full - self._engine_pitch_idle)
        )
        # Map throttle to volume (0.3 at idle to 1.0 at full throttle)
        volume = 0.3 + (throttle * 0.7)

        self._audio_engine.update_source_pitch(self._engine_source_id, pitch)
        self._audio_engine.update_source_volume(self._engine_source_id, volume)

    def set_engine_pitch_range(self, pitch_idle: float, pitch_full: float) -> None:
        """Configure engine sound pitch range.

        Args:
            pitch_idle: Audio pitch at 0% throttle.
            pitch_full: Audio pitch at 100% throttle.
        """
        self._engine_pitch_idle = pitch_idle
        self._engine_pitch_full = pitch_full
        logger.debug(f"Engine pitch range set: {pitch_idle} to {pitch_full}")

    def start_wind_sound(self, path: str = "assets/sounds/aircraft/wind.mp3") -> None:
        """Start looping wind sound.

        Args:
            path: Path to wind sound file.
        """
        if not self._audio_engine:
            return

        # Stop existing wind sound
        if self._wind_source_id is not None:
            self._audio_engine.stop_source(self._wind_source_id)

        # Start new looping wind sound at low volume (stopped)
        try:
            self._wind_source_id = self.play_sound_2d(path, volume=0.0, pitch=1.0, loop=True)
            logger.debug("Wind sound started")
        except FileNotFoundError:
            logger.warning(f"Wind sound not found: {path}")

    def update_wind_sound(self, airspeed: float) -> None:
        """Update wind sound based on airspeed.

        Args:
            airspeed: Airspeed in knots.
        """
        if not self._audio_engine or self._wind_source_id is None:
            return

        # Map airspeed to volume (0 at 0 knots, 1.0 at 100+ knots)
        volume = min(airspeed / 100.0, 1.0)
        # Map airspeed to pitch (0.8 at low speed, 1.5 at high speed)
        pitch = 0.8 + (min(airspeed / 200.0, 1.0) * 0.7)

        self._audio_engine.update_source_volume(self._wind_source_id, volume)
        self._audio_engine.update_source_pitch(self._wind_source_id, pitch)

    def play_gear_sound(self, gear_down: bool) -> None:
        """Play gear up/down sound.

        Args:
            gear_down: True for gear down, False for gear up.
        """
        if gear_down:
            path = "assets/sounds/aircraft/geardown1.mp3"
        else:
            path = "assets/sounds/aircraft/gearup1.mp3"

        try:
            self.play_sound_2d(path, volume=0.8)
        except FileNotFoundError:
            logger.warning(f"Gear sound not found: {path}")

    def play_flaps_sound(self, extending: bool) -> None:
        """Play flaps sound.

        Args:
            extending: True for extending, False for retracting.
        """
        if extending:
            path = "assets/sounds/aircraft/flapson1.mp3"
        else:
            path = "assets/sounds/aircraft/flapsoff1.mp3"

        try:
            self.play_sound_2d(path, volume=0.6)
        except FileNotFoundError:
            logger.warning(f"Flaps sound not found: {path}")

    def play_brakes_sound(self, brakes_on: bool) -> None:
        """Play brakes sound.

        Args:
            brakes_on: True for brakes on, False for brakes off.
        """
        if brakes_on:
            path = "assets/sounds/aircraft/brakeson.mp3"
        else:
            path = "assets/sounds/aircraft/brakesoff.mp3"

        try:
            self.play_sound_2d(path, volume=0.7)
        except FileNotFoundError:
            logger.warning(f"Brakes sound not found: {path}")

    def play_switch_sound(self, switch_on: bool) -> None:
        """Play switch click sound.

        Args:
            switch_on: True for switch on, False for switch off.
        """
        if switch_on:
            path = "assets/sounds/aircraft/switch_on.wav"
        else:
            path = "assets/sounds/aircraft/switch_off.wav"

        try:
            self.play_sound_2d(path, volume=0.5)
        except FileNotFoundError:
            logger.warning(f"Switch sound not found: {path}")

    def play_button_sound(self) -> None:
        """Play button press sound."""
        path = "assets/sounds/aircraft/button_press.wav"

        try:
            self.play_sound_2d(path, volume=0.5)
        except FileNotFoundError:
            logger.warning(f"Button sound not found: {path}")

    def play_knob_sound(self) -> None:
        """Play knob turn sound."""
        path = "assets/sounds/aircraft/knob_turn.wav"

        try:
            self.play_sound_2d(path, volume=0.4)
        except FileNotFoundError:
            logger.warning(f"Knob sound not found: {path}")

    def start_rolling_sound(self, path: str = "assets/sounds/aircraft/rolling.wav") -> None:
        """Start looping rolling/tire sound.

        Args:
            path: Path to rolling sound file.
        """
        if not self._audio_engine:
            return

        # Check if we already have a rolling source
        if hasattr(self, "_rolling_source_id") and self._rolling_source_id is not None:
            return  # Already playing

        # Start new looping rolling sound at zero volume (controlled by ground speed)
        try:
            self._rolling_source_id = self.play_sound_2d(path, volume=0.0, pitch=1.0, loop=True)
            logger.debug("Rolling sound started")
        except FileNotFoundError:
            logger.warning(f"Rolling sound not found: {path}")

    def update_rolling_sound(self, ground_speed: float, on_ground: bool) -> None:
        """Update rolling sound based on ground speed.

        Args:
            ground_speed: Ground speed in knots
            on_ground: Whether aircraft is on the ground
        """
        if not self._audio_engine:
            return

        if not hasattr(self, "_rolling_source_id"):
            self._rolling_source_id = None

        # Start rolling sound if on ground and not already playing
        if on_ground and self._rolling_source_id is None:
            self.start_rolling_sound()

        # Stop rolling sound if airborne
        if not on_ground and self._rolling_source_id is not None:
            self._audio_engine.stop_source(self._rolling_source_id)
            self._rolling_source_id = None
            return

        # Update volume and pitch based on ground speed
        if self._rolling_source_id is not None:
            # Volume: 0 at 0 knots, 1.0 at 50+ knots
            volume = min(ground_speed / 50.0, 1.0)
            # Pitch: 0.5 at 0 knots, 2.0 at 100+ knots
            pitch = 0.5 + (min(ground_speed / 100.0, 1.0) * 1.5)

            self._audio_engine.update_source_volume(self._rolling_source_id, volume)
            self._audio_engine.update_source_pitch(self._rolling_source_id, pitch)

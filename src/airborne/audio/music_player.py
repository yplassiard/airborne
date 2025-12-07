"""Music player with looping, fading, and volume control.

This module provides music playback functionality with support for
looping, crossfading, and volume control integrated with VolumeManager.

Typical usage example:
    from airborne.audio.music_player import MusicPlayer

    music = MusicPlayer(audio_engine, volume_manager)
    music.play("path/to/music.ogg", loop=True, fade_in=2.0)
    music.fade_out(1.0)
    music.stop()
"""

import time
from typing import Any

from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


class MusicPlayer:
    """Manages music playback with fading and looping.

    The MusicPlayer handles background music playback with support for
    looping,  crossfading transitions, and volume control integrated with
    the VolumeManager.

    Examples:
        >>> music = MusicPlayer(audio_engine, volume_manager)
        >>> music.play("menu.ogg", loop=True, fade_in=1.0)
        >>> music.set_volume(0.7)
        >>> music.fade_out(2.0)
    """

    def __init__(self, audio_engine: Any, volume_manager: Any) -> None:
        """Initialize the music player.

        Args:
            audio_engine: Audio engine with play_2d/stop_source methods.
            volume_manager: VolumeManager for category volumes.
        """
        self._audio_engine = audio_engine
        self._volume_manager = volume_manager
        self._current_source_id: int | None = None
        self._current_file: str | None = None
        self._is_looping: bool = False
        self._current_volume: float = 1.0  # Track current volume

        # Fading state
        self._fading: bool = False
        self._fade_start_time: float = 0.0
        self._fade_duration: float = 0.0
        self._fade_start_volume: float = 0.0
        self._fade_target_volume: float = 0.0

    def play(
        self,
        file_path: str,
        loop: bool = True,
        fade_in: float = 0.0,
        volume: float = 1.0,
    ) -> bool:
        """Play music file with optional fading and looping.

        Args:
            file_path: Path to music file to play.
            loop: Whether to loop the music.
            fade_in: Fade-in duration in seconds (0 = no fade).
            volume: Initial volume (0.0 to 1.0), scaled by category volume.

        Returns:
            True if playback started successfully.

        Examples:
            >>> music.play("menu.ogg", loop=True, fade_in=1.0)
            True
        """
        # Stop current music if playing
        if self._current_source_id is not None:
            self.stop()

        # Calculate final volume (music category * volume parameter)
        final_volume = self._volume_manager.get_final_volume("music") * volume

        # Start with 0 volume if fading in
        start_volume = 0.0 if fade_in > 0 else final_volume

        # Load the sound file
        sound = self._audio_engine.load_sound(file_path, preload=True, loop_mode=loop)

        # Play the music as 2D (non-positional)
        source_id = self._audio_engine.play_2d(sound, loop=loop, volume=start_volume)

        if source_id is None:
            return False

        self._current_source_id = source_id
        self._current_file = file_path
        self._is_looping = loop
        self._current_volume = start_volume if fade_in > 0 else final_volume

        # Start fade-in if requested
        if fade_in > 0:
            self._start_fade(start_volume, final_volume, fade_in)

        return True

    def stop(self) -> None:
        """Stop currently playing music immediately.

        Examples:
            >>> music.stop()
        """
        if self._current_source_id is not None:
            self._audio_engine.stop_source(self._current_source_id)
            self._current_source_id = None
            self._current_file = None
            self._is_looping = False
            self._fading = False

    def fade_out(self, duration: float) -> None:
        """Fade out and stop current music.

        Args:
            duration: Fade-out duration in seconds.

        Examples:
            >>> music.fade_out(2.0)
        """
        if self._current_source_id is None:
            logger.debug("fade_out called but no music is playing")
            return

        logger.debug(
            "Starting fade_out: duration=%f, current_volume=%f",
            duration,
            self._current_volume,
        )
        # Use our tracked volume instead of querying the engine
        self._start_fade(self._current_volume, 0.0, duration)

    def set_volume(self, volume: float) -> None:
        """Set music volume.

        Args:
            volume: Volume level (0.0 to 1.0), scaled by category volume.

        Examples:
            >>> music.set_volume(0.5)
        """
        if self._current_source_id is None:
            return

        final_volume = self._volume_manager.get_final_volume("music") * volume
        self._current_volume = final_volume

        # Set volume on the FMOD channel
        channel = self._audio_engine.get_channel(self._current_source_id)
        if channel:
            channel.volume = final_volume

    def update(self, delta_time: float) -> None:
        """Update fading state (call each frame).

        Args:
            delta_time: Time since last update in seconds.

        Examples:
            >>> music.update(0.016)  # ~60 FPS
        """
        if not self._fading or self._current_source_id is None:
            return

        # Calculate fade progress
        elapsed = time.time() - self._fade_start_time
        progress = min(elapsed / self._fade_duration, 1.0)

        # Calculate current volume
        volume_range = self._fade_target_volume - self._fade_start_volume
        current_volume = self._fade_start_volume + (volume_range * progress)

        # Apply volume to the FMOD channel
        self._current_volume = current_volume
        channel = self._audio_engine.get_channel(self._current_source_id)
        if channel:
            channel.volume = current_volume
            logger.debug(
                "Fading: progress=%.2f, volume=%.3f (target=%.3f)",
                progress,
                current_volume,
                self._fade_target_volume,
            )
        else:
            logger.warning(
                "Cannot fade - channel not found for source_id=%s", self._current_source_id
            )

        # Check if fade is complete
        if progress >= 1.0:
            self._fading = False
            logger.debug("Fade complete")

            # Stop if faded to zero
            if self._fade_target_volume == 0.0:
                self.stop()

    def is_playing(self) -> bool:
        """Check if music is currently playing.

        Returns:
            True if music is playing.

        Examples:
            >>> music.is_playing()
            True
        """
        if self._current_source_id is None:
            return False

        channel = self._audio_engine.get_channel(self._current_source_id)
        if channel:
            return channel.is_playing
        return False

    def _start_fade(self, start_volume: float, target_volume: float, duration: float) -> None:
        """Start a volume fade.

        Args:
            start_volume: Starting volume.
            target_volume: Target volume.
            duration: Fade duration in seconds.
        """
        self._fading = True
        self._fade_start_time = time.time()
        self._fade_duration = duration
        self._fade_start_volume = start_volume
        self._fade_target_volume = target_volume

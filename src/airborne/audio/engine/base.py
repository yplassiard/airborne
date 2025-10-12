"""Abstract audio engine interface.

This module defines the interface for audio engines that provide 3D spatial
audio, sound loading, playback control, and effects.

Typical usage example:
    from airborne.audio.engine.base import IAudioEngine

    class MyAudioEngine(IAudioEngine):
        def initialize(self, config: dict[str, Any]) -> None:
            # Setup audio system
            pass
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

import numpy as np


class AudioFormat(Enum):
    """Supported audio file formats."""

    UNKNOWN = auto()
    WAV = auto()
    MP3 = auto()
    OGG = auto()
    FLAC = auto()


class SourceState(Enum):
    """Audio source playback states."""

    STOPPED = auto()
    PLAYING = auto()
    PAUSED = auto()


@dataclass
class Vector3:
    """3D vector for positions and velocities.

    Attributes:
        x: X coordinate.
        y: Y coordinate (up/down).
        z: Z coordinate.
    """

    x: float
    y: float
    z: float

    def to_array(self) -> np.ndarray:
        """Convert to numpy array.

        Returns:
            Numpy array [x, y, z].
        """
        return np.array([self.x, self.y, self.z])

    @classmethod
    def from_array(cls, arr: np.ndarray) -> "Vector3":
        """Create from numpy array.

        Args:
            arr: Array with at least 3 elements.

        Returns:
            Vector3 instance.
        """
        return cls(float(arr[0]), float(arr[1]), float(arr[2]))

    def __add__(self, other: "Vector3") -> "Vector3":
        """Add two vectors."""
        return Vector3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vector3") -> "Vector3":
        """Subtract two vectors."""
        return Vector3(self.x - other.x, self.y - other.y, self.z - other.z)


@dataclass
class Sound:
    """Loaded sound resource.

    Attributes:
        path: Path to the sound file.
        format: Audio format.
        duration: Duration in seconds.
        sample_rate: Sample rate in Hz.
        channels: Number of channels (1=mono, 2=stereo).
        handle: Engine-specific sound handle.
    """

    path: str
    format: AudioFormat
    duration: float
    sample_rate: int
    channels: int
    handle: Any  # Engine-specific handle


@dataclass
class AudioSource:
    """Active audio source.

    Represents a sound being played with position and state.

    Attributes:
        source_id: Unique source identifier.
        sound: The sound being played.
        position: 3D position in world space.
        velocity: 3D velocity for doppler effect.
        volume: Volume level (0.0 to 1.0).
        pitch: Pitch multiplier (1.0 = normal).
        loop: Whether the sound loops.
        state: Current playback state.
    """

    source_id: int
    sound: Sound
    position: Vector3
    velocity: Vector3
    volume: float
    pitch: float
    loop: bool
    state: SourceState


class IAudioEngine(ABC):
    """Abstract interface for audio engines.

    Audio engines provide 3D spatial audio, sound loading, playback control,
    and audio effects. Implementations might use PyBASS, OpenAL, etc.

    Examples:
        >>> engine = PyBASSEngine()
        >>> engine.initialize({"sample_rate": 44100})
        >>> sound = engine.load_sound("sounds/engine.wav")
        >>> source_id = engine.play_3d(sound, Vector3(0, 0, 10))
        >>> engine.set_listener(Vector3(0, 0, 0), Vector3(0, 0, 1), Vector3(0, 1, 0))
        >>> engine.shutdown()
    """

    @abstractmethod
    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize the audio engine.

        Args:
            config: Configuration dictionary with engine-specific settings.

        Raises:
            RuntimeError: If initialization fails.

        Examples:
            >>> engine.initialize({"sample_rate": 44100, "device": -1})
        """

    @abstractmethod
    def shutdown(self) -> None:
        """Shutdown the audio engine.

        Stops all sources, unloads sounds, and releases resources.

        Examples:
            >>> engine.shutdown()
        """

    @abstractmethod
    def load_sound(self, path: str, preload: bool = True) -> Sound:
        """Load a sound from file.

        Args:
            path: Path to the sound file.
            preload: Whether to load into memory immediately.

        Returns:
            Loaded sound resource.

        Raises:
            FileNotFoundError: If sound file not found.
            RuntimeError: If loading fails.

        Examples:
            >>> sound = engine.load_sound("sounds/beep.wav")
            >>> streaming_sound = engine.load_sound("music/track.mp3", preload=False)
        """

    @abstractmethod
    def unload_sound(self, sound: Sound) -> None:
        """Unload a sound and free resources.

        Args:
            sound: Sound to unload.

        Examples:
            >>> engine.unload_sound(sound)
        """

    @abstractmethod
    def play_2d(
        self, sound: Sound, volume: float = 1.0, pitch: float = 1.0, loop: bool = False
    ) -> int:
        """Play a sound in 2D (no spatial positioning).

        Args:
            sound: Sound to play.
            volume: Volume level (0.0 to 1.0).
            pitch: Pitch multiplier (1.0 = normal).
            loop: Whether to loop the sound.

        Returns:
            Source ID for controlling playback.

        Examples:
            >>> source_id = engine.play_2d(beep_sound, volume=0.8)
        """

    @abstractmethod
    def play_3d(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        sound: Sound,
        position: Vector3,
        velocity: Vector3 | None = None,
        volume: float = 1.0,
        pitch: float = 1.0,
        loop: bool = False,
    ) -> int:
        """Play a sound in 3D space.

        Args:
            sound: Sound to play.
            position: 3D position in world space.
            velocity: 3D velocity for doppler effect.
            volume: Volume level (0.0 to 1.0).
            pitch: Pitch multiplier (1.0 = normal).
            loop: Whether to loop the sound.

        Returns:
            Source ID for controlling playback.

        Examples:
            >>> pos = Vector3(10, 0, 5)
            >>> vel = Vector3(0, 0, -50)
            >>> source_id = engine.play_3d(engine_sound, pos, vel, loop=True)
        """

    @abstractmethod
    def stop_source(self, source_id: int) -> None:
        """Stop a playing source.

        Args:
            source_id: ID of source to stop.

        Examples:
            >>> engine.stop_source(source_id)
        """

    @abstractmethod
    def pause_source(self, source_id: int) -> None:
        """Pause a playing source.

        Args:
            source_id: ID of source to pause.

        Examples:
            >>> engine.pause_source(source_id)
        """

    @abstractmethod
    def resume_source(self, source_id: int) -> None:
        """Resume a paused source.

        Args:
            source_id: ID of source to resume.

        Examples:
            >>> engine.resume_source(source_id)
        """

    @abstractmethod
    def update_source_position(
        self, source_id: int, position: Vector3, velocity: Vector3 | None = None
    ) -> None:
        """Update a source's position and velocity.

        Args:
            source_id: ID of source to update.
            position: New 3D position.
            velocity: New 3D velocity (for doppler).

        Examples:
            >>> engine.update_source_position(source_id, Vector3(20, 0, 10))
        """

    @abstractmethod
    def update_source_volume(self, source_id: int, volume: float) -> None:
        """Update a source's volume.

        Args:
            source_id: ID of source to update.
            volume: New volume level (0.0 to 1.0).

        Examples:
            >>> engine.update_source_volume(source_id, 0.5)
        """

    @abstractmethod
    def update_source_pitch(self, source_id: int, pitch: float) -> None:
        """Update a source's pitch.

        Args:
            source_id: ID of source to update.
            pitch: New pitch multiplier (1.0 = normal).

        Examples:
            >>> engine.update_source_pitch(source_id, 1.2)
        """

    @abstractmethod
    def set_listener(
        self,
        position: Vector3,
        forward: Vector3,
        up: Vector3,
        velocity: Vector3 | None = None,
    ) -> None:
        """Set listener (player) position and orientation.

        Args:
            position: Listener 3D position.
            forward: Forward direction vector (normalized).
            up: Up direction vector (normalized).
            velocity: Listener velocity for doppler.

        Examples:
            >>> engine.set_listener(
            ...     Vector3(0, 0, 0),
            ...     Vector3(0, 0, 1),
            ...     Vector3(0, 1, 0)
            ... )
        """

    @abstractmethod
    def get_source_state(self, source_id: int) -> SourceState:
        """Get the current state of a source.

        Args:
            source_id: ID of source to query.

        Returns:
            Current source state.

        Examples:
            >>> state = engine.get_source_state(source_id)
            >>> if state == SourceState.PLAYING:
            ...     print("Still playing")
        """

    @abstractmethod
    def set_master_volume(self, volume: float) -> None:
        """Set the master volume for all sounds.

        Args:
            volume: Master volume level (0.0 to 1.0).

        Examples:
            >>> engine.set_master_volume(0.7)
        """

    def get_active_sources(self) -> list[AudioSource]:
        """Get all currently active audio sources.

        Returns:
            List of active audio sources.

        Note:
            Default implementation returns empty list. Override if tracking
            sources is supported by the engine.
        """
        return []

"""PyBASS audio engine implementation.

This module provides a concrete implementation of the IAudioEngine interface
using the PyBASS3 library for high-quality 3D spatial audio.

Typical usage example:
    from airborne.audio.engine.pybass_engine import PyBASSEngine

    engine = PyBASSEngine()
    engine.initialize({"sample_rate": 44100})
    sound = engine.load_sound("sounds/engine.wav")
    source_id = engine.play_3d(sound, Vector3(0, 0, 10))
"""

from pathlib import Path
from typing import Any

try:
    import pybass3 as pybass  # type: ignore[import-untyped]
    from pybass3 import bass_3d

    PYBASS_AVAILABLE = True
except ImportError:
    PYBASS_AVAILABLE = False

from airborne.audio.engine.base import (
    AudioFormat,
    AudioSource,
    IAudioEngine,
    Sound,
    SourceState,
    Vector3,
)
from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


class PyBASSError(Exception):
    """Raised when PyBASS operations fail."""


class PyBASSEngine(IAudioEngine):
    """PyBASS3-based audio engine with 3D spatial audio support.

    Provides high-quality audio playback with 3D positioning, doppler effect,
    and multiple simultaneous sources.

    Examples:
        >>> engine = PyBASSEngine()
        >>> engine.initialize({"sample_rate": 44100, "device": -1})
        >>> sound = engine.load_sound("sounds/beep.wav")
        >>> source_id = engine.play_3d(sound, Vector3(10, 0, 0))
        >>> engine.shutdown()
    """

    def __init__(self) -> None:
        """Initialize the PyBASS engine (not started yet)."""
        if not PYBASS_AVAILABLE:
            raise ImportError("PyBASS3 is not installed. Install it with: uv add PyBASS3")

        self._initialized = False
        self._sounds: dict[str, Sound] = {}
        self._sources: dict[int, AudioSource] = {}
        self._next_source_id = 1
        self._master_volume = 1.0

    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize PyBASS audio system.

        Args:
            config: Configuration with keys:
                - sample_rate: Sample rate in Hz (default: 44100)
                - device: Device ID or -1 for default (default: -1)
                - enable_3d: Enable 3D positioning (default: True)

        Raises:
            PyBASSError: If initialization fails.
        """
        if self._initialized:
            logger.warning("PyBASS engine already initialized")
            return

        sample_rate = config.get("sample_rate", 44100)
        device = config.get("device", -1)
        enable_3d = config.get("enable_3d", True)

        # Initialize BASS
        flags = pybass.BASS_DEVICE_3D if enable_3d else 0
        if not pybass.BASS_Init(device, sample_rate, flags, 0, None):
            error_code = pybass.BASS_ErrorGetCode()
            raise PyBASSError("Failed to initialize BASS: error code %d", error_code)

        # Set 3D factors
        if enable_3d:
            bass_3d.BASS_Set3DFactors(1.0, 1.0, 1.0)  # Distance, rolloff, doppler
            bass_3d.BASS_Set3DPosition(
                (0.0, 0.0, 0.0),  # position
                (0.0, 0.0, 0.0),  # velocity
                (0.0, 0.0, 1.0),  # forward
                (0.0, 1.0, 0.0),  # up
            )
            bass_3d.BASS_Apply3D()

        self._initialized = True
        logger.info("PyBASS engine initialized: sample_rate=%d, device=%d", sample_rate, device)

    def shutdown(self) -> None:
        """Shutdown PyBASS and release all resources."""
        if not self._initialized:
            return

        # Stop all sources
        for source_id in list(self._sources.keys()):
            try:
                self.stop_source(source_id)
            except Exception as e:
                logger.error("Error stopping source %d: %s", source_id, e)

        # Free all sounds
        for sound in list(self._sounds.values()):
            try:
                self.unload_sound(sound)
            except Exception as e:
                logger.error("Error unloading sound %s: %s", sound.path, e)

        # Shutdown BASS
        pybass.BASS_Free()
        self._initialized = False
        logger.info("PyBASS engine shutdown")

    def load_sound(self, path: str, preload: bool = True) -> Sound:
        """Load a sound file using BASS.

        Args:
            path: Path to sound file.
            preload: Whether to decode into memory (True) or stream (False).

        Returns:
            Loaded sound resource.

        Raises:
            FileNotFoundError: If file doesn't exist.
            PyBASSError: If loading fails.
        """
        if not self._initialized:
            raise PyBASSError("Engine not initialized")

        # Check if already loaded
        if path in self._sounds:
            logger.debug("Sound already loaded: %s", path)
            return self._sounds[path]

        # Check file exists
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError("Sound file not found: %s", path)

        # Determine flags
        flags = pybass.BASS_SAMPLE_3D | pybass.BASS_SAMPLE_MONO
        if not preload:
            flags |= pybass.BASS_STREAM_DECODE

        # Load the sound
        handle = pybass.BASS_StreamCreateFile(False, str(file_path), 0, 0, flags)
        if not handle:
            error_code = pybass.BASS_ErrorGetCode()
            raise PyBASSError("Failed to load sound %s: error code %d", path, error_code)

        # Get sound info
        info = pybass.BASS_ChannelGetInfo(handle)
        length_bytes = pybass.BASS_ChannelGetLength(handle, pybass.BASS_POS_BYTE)
        duration = pybass.BASS_ChannelBytes2Seconds(handle, length_bytes)

        # Determine format
        audio_format = AudioFormat.UNKNOWN
        ext = file_path.suffix.lower()
        if ext == ".wav":
            audio_format = AudioFormat.WAV
        elif ext == ".mp3":
            audio_format = AudioFormat.MP3
        elif ext == ".ogg":
            audio_format = AudioFormat.OGG
        elif ext == ".flac":
            audio_format = AudioFormat.FLAC

        sound = Sound(
            path=path,
            format=audio_format,
            duration=duration,
            sample_rate=info.freq,
            channels=info.chans,
            handle=handle,
        )

        self._sounds[path] = sound
        logger.debug("Loaded sound: %s (%.2fs, %dHz)", path, duration, info.freq)
        return sound

    def unload_sound(self, sound: Sound) -> None:
        """Unload a sound and free BASS resources.

        Args:
            sound: Sound to unload.
        """
        if sound.path in self._sounds:
            pybass.BASS_StreamFree(sound.handle)
            del self._sounds[sound.path]
            logger.debug("Unloaded sound: %s", sound.path)

    def play_2d(
        self, sound: Sound, volume: float = 1.0, pitch: float = 1.0, loop: bool = False
    ) -> int:
        """Play a sound in 2D (non-spatial).

        Args:
            sound: Sound to play.
            volume: Volume level (0.0 to 1.0).
            pitch: Pitch multiplier.
            loop: Whether to loop.

        Returns:
            Source ID.
        """
        # Clone the channel for playback
        handle = pybass.BASS_StreamCreateFile(False, sound.path, 0, 0, 0)
        if not handle:
            error_code = pybass.BASS_ErrorGetCode()
            raise PyBASSError("Failed to create playback stream: error code %d", error_code)

        # Set properties
        pybass.BASS_ChannelSetAttribute(
            handle, pybass.BASS_ATTRIB_VOL, volume * self._master_volume
        )
        pybass.BASS_ChannelSetAttribute(handle, pybass.BASS_ATTRIB_FREQ, sound.sample_rate * pitch)

        if loop:
            pybass.BASS_ChannelFlags(handle, pybass.BASS_SAMPLE_LOOP, pybass.BASS_SAMPLE_LOOP)

        # Play
        if not pybass.BASS_ChannelPlay(handle, False):
            error_code = pybass.BASS_ErrorGetCode()
            pybass.BASS_StreamFree(handle)
            raise PyBASSError("Failed to play channel: error code %d", error_code)

        # Track source
        source_id = self._next_source_id
        self._next_source_id += 1

        source = AudioSource(
            source_id=source_id,
            sound=sound,
            position=Vector3(0, 0, 0),
            velocity=Vector3(0, 0, 0),
            volume=volume,
            pitch=pitch,
            loop=loop,
            state=SourceState.PLAYING,
        )
        source.sound.handle = handle  # Update to the playback handle
        self._sources[source_id] = source

        logger.debug("Playing 2D sound: %s (source_id=%d)", sound.path, source_id)
        return source_id

    def play_3d(
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
            position: 3D position.
            velocity: 3D velocity (for doppler).
            volume: Volume level.
            pitch: Pitch multiplier.
            loop: Whether to loop.

        Returns:
            Source ID.
        """
        if velocity is None:
            velocity = Vector3(0, 0, 0)

        # Create 3D channel
        handle = pybass.BASS_StreamCreateFile(
            False, sound.path, 0, 0, pybass.BASS_SAMPLE_3D | pybass.BASS_SAMPLE_MONO
        )
        if not handle:
            error_code = pybass.BASS_ErrorGetCode()
            raise PyBASSError("Failed to create 3D stream: error code %d", error_code)

        # Set 3D position
        bass_3d.BASS_ChannelSet3DPosition(
            handle, (position.x, position.y, position.z), None, (velocity.x, velocity.y, velocity.z)
        )

        # Set properties
        pybass.BASS_ChannelSetAttribute(
            handle, pybass.BASS_ATTRIB_VOL, volume * self._master_volume
        )
        pybass.BASS_ChannelSetAttribute(handle, pybass.BASS_ATTRIB_FREQ, sound.sample_rate * pitch)

        if loop:
            pybass.BASS_ChannelFlags(handle, pybass.BASS_SAMPLE_LOOP, pybass.BASS_SAMPLE_LOOP)

        # Apply 3D changes
        bass_3d.BASS_Apply3D()

        # Play
        if not pybass.BASS_ChannelPlay(handle, False):
            error_code = pybass.BASS_ErrorGetCode()
            pybass.BASS_StreamFree(handle)
            raise PyBASSError("Failed to play 3D channel: error code %d", error_code)

        # Track source
        source_id = self._next_source_id
        self._next_source_id += 1

        source = AudioSource(
            source_id=source_id,
            sound=sound,
            position=position,
            velocity=velocity,
            volume=volume,
            pitch=pitch,
            loop=loop,
            state=SourceState.PLAYING,
        )
        source.sound.handle = handle
        self._sources[source_id] = source

        logger.debug(
            "Playing 3D sound: %s at (%s) (source_id=%d)",
            sound.path,
            f"{position.x:.1f}, {position.y:.1f}, {position.z:.1f}",
            source_id,
        )
        return source_id

    def stop_source(self, source_id: int) -> None:
        """Stop a playing source.

        Args:
            source_id: ID of source to stop.
        """
        if source_id not in self._sources:
            logger.warning("Attempted to stop unknown source: %d", source_id)
            return

        source = self._sources[source_id]
        pybass.BASS_ChannelStop(source.sound.handle)
        pybass.BASS_StreamFree(source.sound.handle)
        source.state = SourceState.STOPPED
        del self._sources[source_id]
        logger.debug("Stopped source: %d", source_id)

    def pause_source(self, source_id: int) -> None:
        """Pause a playing source.

        Args:
            source_id: ID of source to pause.
        """
        if source_id not in self._sources:
            return

        source = self._sources[source_id]
        pybass.BASS_ChannelPause(source.sound.handle)
        source.state = SourceState.PAUSED
        logger.debug("Paused source: %d", source_id)

    def resume_source(self, source_id: int) -> None:
        """Resume a paused source.

        Args:
            source_id: ID of source to resume.
        """
        if source_id not in self._sources:
            return

        source = self._sources[source_id]
        pybass.BASS_ChannelPlay(source.sound.handle, False)
        source.state = SourceState.PLAYING
        logger.debug("Resumed source: %d", source_id)

    def update_source_position(
        self, source_id: int, position: Vector3, velocity: Vector3 | None = None
    ) -> None:
        """Update source position and velocity.

        Args:
            source_id: Source ID.
            position: New position.
            velocity: New velocity.
        """
        if source_id not in self._sources:
            return

        source = self._sources[source_id]
        source.position = position
        if velocity:
            source.velocity = velocity

        bass_3d.BASS_ChannelSet3DPosition(
            source.sound.handle,
            (position.x, position.y, position.z),
            None,
            (source.velocity.x, source.velocity.y, source.velocity.z),
        )
        bass_3d.BASS_Apply3D()

    def update_source_volume(self, source_id: int, volume: float) -> None:
        """Update source volume.

        Args:
            source_id: Source ID.
            volume: New volume (0.0 to 1.0).
        """
        if source_id not in self._sources:
            return

        source = self._sources[source_id]
        source.volume = volume
        pybass.BASS_ChannelSetAttribute(
            source.sound.handle, pybass.BASS_ATTRIB_VOL, volume * self._master_volume
        )

    def update_source_pitch(self, source_id: int, pitch: float) -> None:
        """Update source pitch.

        Args:
            source_id: Source ID.
            pitch: New pitch multiplier.
        """
        if source_id not in self._sources:
            return

        source = self._sources[source_id]
        source.pitch = pitch
        pybass.BASS_ChannelSetAttribute(
            source.sound.handle, pybass.BASS_ATTRIB_FREQ, source.sound.sample_rate * pitch
        )

    def set_listener(
        self,
        position: Vector3,
        forward: Vector3,
        up: Vector3,
        velocity: Vector3 | None = None,
    ) -> None:
        """Set listener position and orientation.

        Args:
            position: Listener position.
            forward: Forward direction (normalized).
            up: Up direction (normalized).
            velocity: Listener velocity.
        """
        if velocity is None:
            velocity = Vector3(0, 0, 0)

        bass_3d.BASS_Set3DPosition(
            (position.x, position.y, position.z),
            (velocity.x, velocity.y, velocity.z),
            (forward.x, forward.y, forward.z),
            (up.x, up.y, up.z),
        )
        bass_3d.BASS_Apply3D()

    def get_source_state(self, source_id: int) -> SourceState:
        """Get source playback state.

        Args:
            source_id: Source ID.

        Returns:
            Current source state.
        """
        if source_id not in self._sources:
            return SourceState.STOPPED

        source = self._sources[source_id]
        state = pybass.BASS_ChannelIsActive(source.sound.handle)

        if state == pybass.BASS_ACTIVE_PLAYING:
            return SourceState.PLAYING
        elif state == pybass.BASS_ACTIVE_PAUSED:
            return SourceState.PAUSED
        else:
            return SourceState.STOPPED

    def set_master_volume(self, volume: float) -> None:
        """Set master volume for all sounds.

        Args:
            volume: Master volume (0.0 to 1.0).
        """
        self._master_volume = max(0.0, min(1.0, volume))
        pybass.BASS_SetConfig(pybass.BASS_CONFIG_GVOL_STREAM, int(self._master_volume * 10000))
        logger.debug("Set master volume: %.2f", self._master_volume)

    def get_active_sources(self) -> list[AudioSource]:
        """Get all active audio sources.

        Returns:
            List of active sources.
        """
        return list(self._sources.values())

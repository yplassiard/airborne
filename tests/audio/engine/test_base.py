"""Tests for audio engine base classes."""


from airborne.audio.engine.base import (
    AudioFormat,
    AudioSource,
    Sound,
    SourceState,
    Vector3,
)


class TestVector3:
    """Test suite for Vector3 class."""

    def test_vector_creation(self) -> None:
        """Test creating a vector."""
        vec = Vector3(1.0, 2.0, 3.0)
        assert vec.x == 1.0
        assert vec.y == 2.0
        assert vec.z == 3.0

    def test_vector_addition(self) -> None:
        """Test vector addition."""
        v1 = Vector3(1.0, 2.0, 3.0)
        v2 = Vector3(4.0, 5.0, 6.0)
        result = v1 + v2
        assert result.x == 5.0
        assert result.y == 7.0
        assert result.z == 9.0

    def test_vector_subtraction(self) -> None:
        """Test vector subtraction."""
        v1 = Vector3(10.0, 8.0, 6.0)
        v2 = Vector3(1.0, 2.0, 3.0)
        result = v1 - v2
        assert result.x == 9.0
        assert result.y == 6.0
        assert result.z == 3.0

    def test_vector_to_array(self) -> None:
        """Test converting vector to numpy array."""
        vec = Vector3(1.0, 2.0, 3.0)
        arr = vec.to_array()
        assert arr[0] == 1.0
        assert arr[1] == 2.0
        assert arr[2] == 3.0

    def test_vector_from_array(self) -> None:
        """Test creating vector from numpy array."""
        import numpy as np

        arr = np.array([1.0, 2.0, 3.0])
        vec = Vector3.from_array(arr)
        assert vec.x == 1.0
        assert vec.y == 2.0
        assert vec.z == 3.0


class TestSound:
    """Test suite for Sound dataclass."""

    def test_sound_creation(self) -> None:
        """Test creating a sound."""
        sound = Sound(
            path="test.wav",
            format=AudioFormat.WAV,
            duration=5.0,
            sample_rate=44100,
            channels=2,
            handle=12345,
        )
        assert sound.path == "test.wav"
        assert sound.format == AudioFormat.WAV
        assert sound.duration == 5.0
        assert sound.sample_rate == 44100
        assert sound.channels == 2
        assert sound.handle == 12345


class TestAudioSource:
    """Test suite for AudioSource dataclass."""

    def test_audio_source_creation(self) -> None:
        """Test creating an audio source."""
        sound = Sound(
            path="test.wav",
            format=AudioFormat.WAV,
            duration=5.0,
            sample_rate=44100,
            channels=2,
            handle=12345,
        )
        source = AudioSource(
            source_id=1,
            sound=sound,
            position=Vector3(10.0, 0.0, 5.0),
            velocity=Vector3(0.0, 0.0, 0.0),
            volume=0.8,
            pitch=1.0,
            loop=False,
            state=SourceState.PLAYING,
        )
        assert source.source_id == 1
        assert source.sound == sound
        assert source.position.x == 10.0
        assert source.volume == 0.8
        assert source.state == SourceState.PLAYING


class TestAudioFormat:
    """Test suite for AudioFormat enum."""

    def test_audio_formats_exist(self) -> None:
        """Test that all expected formats exist."""
        assert AudioFormat.UNKNOWN
        assert AudioFormat.WAV
        assert AudioFormat.MP3
        assert AudioFormat.OGG
        assert AudioFormat.FLAC


class TestSourceState:
    """Test suite for SourceState enum."""

    def test_source_states_exist(self) -> None:
        """Test that all expected states exist."""
        assert SourceState.STOPPED
        assert SourceState.PLAYING
        assert SourceState.PAUSED

"""Tests for sound manager."""

import pytest

from airborne.audio.engine.base import (
    AudioFormat,
    IAudioEngine,
    Sound,
    SourceState,
    Vector3,
)
from airborne.audio.sound_manager import SoundManager
from airborne.audio.tts.base import ITTSProvider, TTSPriority, TTSState


class MockAudioEngine(IAudioEngine):
    """Mock audio engine for testing."""

    def __init__(self) -> None:
        """Initialize mock engine."""
        self.initialized = False
        self.sounds: dict[str, Sound] = {}
        self.sources: dict[int, int] = {}
        self.next_source_id = 1

    def initialize(self, config: dict) -> None:
        """Initialize the engine."""
        self.initialized = True

    def shutdown(self) -> None:
        """Shutdown the engine."""
        self.initialized = False
        self.sounds.clear()
        self.sources.clear()

    def load_sound(self, path: str, preload: bool = True) -> Sound:
        """Load a sound."""
        if path not in self.sounds:
            self.sounds[path] = Sound(
                path=path,
                format=AudioFormat.WAV,
                duration=1.0,
                sample_rate=44100,
                channels=2,
                handle=len(self.sounds),
            )
        return self.sounds[path]

    def unload_sound(self, sound: Sound) -> None:
        """Unload a sound."""
        if sound.path in self.sounds:
            del self.sounds[sound.path]

    def play_2d(
        self, sound: Sound, volume: float = 1.0, pitch: float = 1.0, loop: bool = False
    ) -> int:
        """Play a sound in 2D."""
        source_id = self.next_source_id
        self.next_source_id += 1
        self.sources[source_id] = sound.handle
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
        """Play a sound in 3D."""
        source_id = self.next_source_id
        self.next_source_id += 1
        self.sources[source_id] = sound.handle
        return source_id

    def stop_source(self, source_id: int) -> None:
        """Stop a source."""
        if source_id in self.sources:
            del self.sources[source_id]

    def pause_source(self, source_id: int) -> None:
        """Pause a source."""
        pass

    def resume_source(self, source_id: int) -> None:
        """Resume a source."""
        pass

    def update_source_position(
        self, source_id: int, position: Vector3, velocity: Vector3 | None = None
    ) -> None:
        """Update source position."""
        pass

    def update_source_volume(self, source_id: int, volume: float) -> None:
        """Update source volume."""
        pass

    def update_source_pitch(self, source_id: int, pitch: float) -> None:
        """Update source pitch."""
        pass

    def set_listener(
        self,
        position: Vector3,
        forward: Vector3,
        up: Vector3,
        velocity: Vector3 | None = None,
    ) -> None:
        """Set listener position."""
        pass

    def get_source_state(self, source_id: int) -> SourceState:
        """Get source state."""
        if source_id in self.sources:
            return SourceState.PLAYING
        return SourceState.STOPPED

    def set_master_volume(self, volume: float) -> None:
        """Set master volume."""
        pass


class MockTTSProvider(ITTSProvider):
    """Mock TTS provider for testing."""

    def __init__(self) -> None:
        """Initialize mock TTS."""
        self.initialized = False
        self.speaking = False
        self.speech_queue: list[str] = []

    def initialize(self, config: dict) -> None:
        """Initialize the TTS."""
        self.initialized = True

    def shutdown(self) -> None:
        """Shutdown the TTS."""
        self.initialized = False
        self.speaking = False
        self.speech_queue.clear()

    def speak(
        self,
        text: str,
        priority: TTSPriority = TTSPriority.NORMAL,
        interrupt: bool = False,
        callback=None,
    ) -> None:
        """Speak text."""
        self.speech_queue.append(text)
        self.speaking = True

    def stop(self) -> None:
        """Stop speech."""
        self.speaking = False

    def pause(self) -> None:
        """Pause speech."""
        pass

    def resume(self) -> None:
        """Resume speech."""
        pass

    def is_speaking(self) -> bool:
        """Check if speaking."""
        return self.speaking

    def get_state(self) -> TTSState:
        """Get TTS state."""
        return TTSState.SPEAKING if self.speaking else TTSState.IDLE

    def set_rate(self, rate: int) -> None:
        """Set speech rate."""
        pass

    def set_volume(self, volume: float) -> None:
        """Set speech volume."""
        pass

    def set_voice(self, voice_id: str) -> None:
        """Set voice."""
        pass

    def get_voices(self) -> list[dict]:
        """Get available voices."""
        return []


class TestSoundManager:
    """Test suite for SoundManager."""

    def test_initialization(self) -> None:
        """Test sound manager initialization."""
        manager = SoundManager()
        audio_engine = MockAudioEngine()
        tts_provider = MockTTSProvider()

        manager.initialize(audio_engine, tts_provider, tts_config={})

        assert audio_engine.initialized
        assert tts_provider.initialized

    def test_shutdown(self) -> None:
        """Test sound manager shutdown."""
        manager = SoundManager()
        audio_engine = MockAudioEngine()
        tts_provider = MockTTSProvider()

        manager.initialize(audio_engine, tts_provider)
        manager.shutdown()

        assert not audio_engine.initialized
        assert not tts_provider.initialized

    def test_load_sound(self) -> None:
        """Test loading a sound."""
        manager = SoundManager()
        audio_engine = MockAudioEngine()
        tts_provider = MockTTSProvider()

        manager.initialize(audio_engine, tts_provider)

        sound = manager.load_sound("test.wav")
        assert sound.path == "test.wav"
        assert "test.wav" in audio_engine.sounds

    def test_load_sound_caching(self) -> None:
        """Test that sounds are cached."""
        manager = SoundManager()
        audio_engine = MockAudioEngine()
        tts_provider = MockTTSProvider()

        manager.initialize(audio_engine, tts_provider)

        sound1 = manager.load_sound("test.wav")
        sound2 = manager.load_sound("test.wav")

        assert sound1 is sound2  # Same object

    def test_play_sound_2d(self) -> None:
        """Test playing a 2D sound."""
        manager = SoundManager()
        audio_engine = MockAudioEngine()
        tts_provider = MockTTSProvider()

        manager.initialize(audio_engine, tts_provider)

        source_id = manager.play_sound_2d("test.wav", volume=0.8)
        assert source_id > 0
        assert source_id in audio_engine.sources

    def test_play_sound_3d(self) -> None:
        """Test playing a 3D sound."""
        manager = SoundManager()
        audio_engine = MockAudioEngine()
        tts_provider = MockTTSProvider()

        manager.initialize(audio_engine, tts_provider)

        position = Vector3(10.0, 0.0, 5.0)
        source_id = manager.play_sound_3d("test.wav", position)
        assert source_id > 0
        assert source_id in audio_engine.sources

    def test_stop_sound(self) -> None:
        """Test stopping a sound."""
        manager = SoundManager()
        audio_engine = MockAudioEngine()
        tts_provider = MockTTSProvider()

        manager.initialize(audio_engine, tts_provider)

        source_id = manager.play_sound_2d("test.wav")
        manager.stop_sound(source_id)

        assert source_id not in audio_engine.sources

    def test_speak(self) -> None:
        """Test TTS speak."""
        manager = SoundManager()
        audio_engine = MockAudioEngine()
        tts_provider = MockTTSProvider()

        manager.initialize(audio_engine, tts_provider)

        manager.speak("Test message")
        assert "Test message" in tts_provider.speech_queue

    def test_speak_with_priority(self) -> None:
        """Test TTS speak with priority."""
        manager = SoundManager()
        audio_engine = MockAudioEngine()
        tts_provider = MockTTSProvider()

        manager.initialize(audio_engine, tts_provider)

        manager.speak("Critical message", priority=TTSPriority.CRITICAL)
        assert "Critical message" in tts_provider.speech_queue

    def test_stop_speech(self) -> None:
        """Test stopping speech."""
        manager = SoundManager()
        audio_engine = MockAudioEngine()
        tts_provider = MockTTSProvider()

        manager.initialize(audio_engine, tts_provider)

        manager.speak("Test message")
        manager.stop_speech()

        assert not tts_provider.speaking

    def test_is_speaking(self) -> None:
        """Test checking if speaking."""
        manager = SoundManager()
        audio_engine = MockAudioEngine()
        tts_provider = MockTTSProvider()

        manager.initialize(audio_engine, tts_provider)

        assert not manager.is_speaking()

        manager.speak("Test message")
        assert manager.is_speaking()

    def test_set_master_volume(self) -> None:
        """Test setting master volume."""
        manager = SoundManager()
        audio_engine = MockAudioEngine()
        tts_provider = MockTTSProvider()

        manager.initialize(audio_engine, tts_provider)

        # Should not raise
        manager.set_master_volume(0.7)

    def test_set_tts_enabled(self) -> None:
        """Test enabling/disabling TTS."""
        manager = SoundManager()
        audio_engine = MockAudioEngine()
        tts_provider = MockTTSProvider()

        manager.initialize(audio_engine, tts_provider)

        manager.set_tts_enabled(False)
        manager.speak("Test message")

        # Should not be added to queue when disabled
        assert len(tts_provider.speech_queue) == 0

    def test_update_listener(self) -> None:
        """Test updating listener position."""
        manager = SoundManager()
        audio_engine = MockAudioEngine()
        tts_provider = MockTTSProvider()

        manager.initialize(audio_engine, tts_provider)

        position = Vector3(0.0, 0.0, 0.0)
        forward = Vector3(0.0, 0.0, 1.0)
        up = Vector3(0.0, 1.0, 0.0)

        # Should not raise
        manager.update_listener(position, forward, up)

    def test_load_sound_without_initialization(self) -> None:
        """Test that loading sound without initialization raises error."""
        manager = SoundManager()

        with pytest.raises(RuntimeError, match="not initialized"):
            manager.load_sound("test.wav")

    def test_play_sound_without_initialization(self) -> None:
        """Test that playing sound without initialization raises error."""
        manager = SoundManager()

        with pytest.raises(RuntimeError, match="not initialized"):
            manager.play_sound_2d("test.wav")

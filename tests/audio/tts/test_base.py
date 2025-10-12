"""Tests for TTS base classes."""

from airborne.audio.tts.base import TTSPriority, TTSState


class TestTTSState:
    """Test suite for TTSState enum."""

    def test_tts_states_exist(self) -> None:
        """Test that all expected states exist."""
        assert TTSState.IDLE
        assert TTSState.SPEAKING
        assert TTSState.PAUSED


class TestTTSPriority:
    """Test suite for TTSPriority enum."""

    def test_tts_priorities_exist(self) -> None:
        """Test that all expected priorities exist."""
        assert TTSPriority.CRITICAL
        assert TTSPriority.HIGH
        assert TTSPriority.NORMAL
        assert TTSPriority.LOW

    def test_priority_values(self) -> None:
        """Test that priorities have correct values for ordering."""
        assert TTSPriority.CRITICAL.value == 0
        assert TTSPriority.HIGH.value == 1
        assert TTSPriority.NORMAL.value == 2
        assert TTSPriority.LOW.value == 3

    def test_priority_ordering(self) -> None:
        """Test that priorities are ordered correctly."""
        assert TTSPriority.CRITICAL.value < TTSPriority.HIGH.value
        assert TTSPriority.HIGH.value < TTSPriority.NORMAL.value
        assert TTSPriority.NORMAL.value < TTSPriority.LOW.value

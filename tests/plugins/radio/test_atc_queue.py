"""Unit tests for ATC message queue system."""

import time
from unittest.mock import Mock

import pytest

from airborne.plugins.radio.atc_queue import ATCMessage, ATCMessageQueue


class TestATCMessage:
    """Test ATCMessage dataclass."""

    def test_create_message(self):
        """Test creating a basic ATC message."""
        msg = ATCMessage(
            message_key="ATC_TOWER_CLEARED_TAKEOFF_31",
            sender="ATC",
            priority=0,
            delay_after=2.0,
        )

        assert msg.message_key == "ATC_TOWER_CLEARED_TAKEOFF_31"
        assert msg.sender == "ATC"
        assert msg.priority == 0
        assert msg.delay_after == 2.0
        assert msg.timestamp > 0

    def test_create_message_with_list(self):
        """Test creating message with multiple keys."""
        msg = ATCMessage(
            message_key=["ATC_ROGER", "ATC_TOWER_CLEARED_TAKEOFF_31"],
            sender="ATC",
        )

        assert len(msg.message_key) == 2
        assert msg.message_key[0] == "ATC_ROGER"

    def test_invalid_sender(self):
        """Test that invalid sender raises error."""
        with pytest.raises(ValueError, match="sender must be"):
            ATCMessage(message_key="TEST", sender="INVALID")

    def test_invalid_priority(self):
        """Test that invalid priority raises error."""
        with pytest.raises(ValueError, match="priority must be"):
            ATCMessage(message_key="TEST", sender="ATC", priority=11)

        with pytest.raises(ValueError, match="priority must be"):
            ATCMessage(message_key="TEST", sender="ATC", priority=-1)

    def test_invalid_delay(self):
        """Test that invalid delay raises error."""
        with pytest.raises(ValueError, match="delay_after must be"):
            ATCMessage(message_key="TEST", sender="ATC", delay_after=-1.0)


class TestATCMessageQueue:
    """Test ATCMessageQueue."""

    @pytest.fixture
    def mock_atc_audio(self):
        """Create mock ATC audio manager."""
        mock = Mock()
        mock.play_atc_message = Mock(return_value=42)  # Return fake source ID
        return mock

    @pytest.fixture
    def queue(self, mock_atc_audio):
        """Create ATC message queue with mock audio."""
        return ATCMessageQueue(mock_atc_audio, min_delay=2.0, max_delay=10.0)

    def test_create_queue(self, queue):
        """Test creating message queue."""
        assert queue.get_queue_size() == 0
        assert not queue.is_busy()
        assert not queue.is_transmitting()
        assert queue.get_current_message() is None

    def test_enqueue_single_message(self, queue):
        """Test enqueueing a single message."""
        msg = ATCMessage(message_key="TEST", sender="PILOT")
        queue.enqueue(msg)

        assert queue.get_queue_size() == 1

    def test_enqueue_multiple_messages(self, queue):
        """Test enqueueing multiple messages."""
        msg1 = ATCMessage(message_key="TEST1", sender="PILOT")
        msg2 = ATCMessage(message_key="TEST2", sender="ATC")
        msg3 = ATCMessage(message_key="TEST3", sender="PILOT")

        queue.enqueue(msg1)
        queue.enqueue(msg2)
        queue.enqueue(msg3)

        assert queue.get_queue_size() == 3

    def test_priority_ordering(self, queue):
        """Test that messages are ordered by priority."""
        msg_low = ATCMessage(message_key="LOW", sender="ATC", priority=0)
        msg_high = ATCMessage(message_key="HIGH", sender="ATC", priority=5)
        msg_urgent = ATCMessage(message_key="URGENT", sender="ATC", priority=9)

        # Enqueue in reverse priority order
        queue.enqueue(msg_low)
        queue.enqueue(msg_high)
        queue.enqueue(msg_urgent)

        # Process to get first message
        queue.process(0.0)

        # Should play highest priority first (URGENT)
        assert queue.get_current_message().message_key == "URGENT"

    def test_process_plays_message(self, queue, mock_atc_audio):
        """Test that process plays queued message."""
        msg = ATCMessage(message_key="TEST", sender="PILOT")
        queue.enqueue(msg)

        # Process to start playback
        queue.process(0.0)

        # Should be transmitting
        assert queue.is_transmitting()
        assert queue.is_busy()
        assert queue.get_current_message().message_key == "TEST"

        # Audio manager should have been called
        mock_atc_audio.play_atc_message.assert_called_once_with("TEST", volume=1.0)

    def test_message_completion_and_delay(self, queue):
        """Test that message completes and waits before next."""
        msg = ATCMessage(message_key="TEST", sender="PILOT", delay_after=2.0)
        queue.enqueue(msg)

        # Start playback
        queue.process(0.0)
        assert queue.is_transmitting()

        # Simulate message completion (wait 1.5 seconds)
        time.sleep(1.5)
        queue.process(1.5)

        # Should be waiting now (not idle yet)
        assert not queue.is_transmitting()
        assert queue.is_busy()  # Still busy (waiting)

    def test_clear_queue(self, queue):
        """Test clearing the queue."""
        msg1 = ATCMessage(message_key="TEST1", sender="PILOT")
        msg2 = ATCMessage(message_key="TEST2", sender="ATC")

        queue.enqueue(msg1)
        queue.enqueue(msg2)

        assert queue.get_queue_size() == 2

        queue.clear()

        assert queue.get_queue_size() == 0

    def test_message_callback(self, queue):
        """Test that message callback is called on completion."""
        callback_called = False

        def callback():
            nonlocal callback_called
            callback_called = True

        msg = ATCMessage(message_key="TEST", sender="PILOT", callback=callback)
        queue.enqueue(msg)

        # Start and complete message
        queue.process(0.0)
        time.sleep(1.5)
        queue.process(1.5)

        # Callback should have been called
        assert callback_called

    def test_shutdown(self, queue):
        """Test shutting down the queue."""
        msg = ATCMessage(message_key="TEST", sender="PILOT")
        queue.enqueue(msg)

        queue.shutdown()

        assert queue.get_queue_size() == 0
        assert not queue.is_busy()

    def test_atc_random_delay(self, queue):
        """Test that ATC messages get random delays."""
        # Enqueue multiple ATC messages and verify delays vary
        msg1 = ATCMessage(message_key="TEST1", sender="ATC", delay_after=0.0)
        msg2 = ATCMessage(message_key="TEST2", sender="ATC", delay_after=0.0)

        # Start first message
        queue.enqueue(msg1)
        queue.process(0.0)

        # Wait for completion
        time.sleep(1.5)
        queue.process(1.5)

        # Record wait time
        wait_time_1 = queue._wait_until - time.time()

        # Clear and test second message
        queue.clear()
        queue._state = "IDLE"

        queue.enqueue(msg2)
        queue.process(0.0)
        time.sleep(1.5)
        queue.process(1.5)

        wait_time_2 = queue._wait_until - time.time()

        # Wait times should be in range [2, 10] seconds
        assert 0 <= wait_time_1 <= 11  # Allow some tolerance
        assert 0 <= wait_time_2 <= 11

        # Note: We can't reliably test that they're different due to
        # randomness, but we can verify they're in the valid range

    def test_pilot_message_uses_specified_delay(self, queue):
        """Test that pilot messages use their specified delay."""
        msg = ATCMessage(message_key="TEST", sender="PILOT", delay_after=5.0)
        queue.enqueue(msg)

        # Start message
        queue.process(0.0)

        # Complete message
        time.sleep(1.5)
        queue.process(1.5)

        # Check that wait time is approximately 5 seconds
        wait_time = queue._wait_until - time.time()
        assert 4.5 <= wait_time <= 5.5  # Allow some tolerance

    def test_queue_state_transitions(self, queue):
        """Test state transitions: IDLE -> TRANSMITTING -> WAITING -> IDLE."""
        msg = ATCMessage(message_key="TEST", sender="PILOT", delay_after=2.0)

        # Initial state: IDLE
        assert queue._state == "IDLE"
        assert not queue.is_busy()
        assert not queue.is_transmitting()

        # Enqueue and process
        queue.enqueue(msg)
        queue.process(0.0)

        # State: TRANSMITTING
        assert queue._state == "TRANSMITTING"
        assert queue.is_busy()
        assert queue.is_transmitting()

        # Complete message
        time.sleep(1.5)
        queue.process(1.5)

        # State: WAITING
        assert queue._state == "WAITING"
        assert queue.is_busy()
        assert not queue.is_transmitting()

        # Wait for delay to expire
        time.sleep(2.5)
        queue.process(0.0)

        # State: IDLE
        assert queue._state == "IDLE"
        assert not queue.is_busy()

    def test_multiple_messages_sequential_playback(self, queue, mock_atc_audio):
        """Test that multiple messages play sequentially with proper spacing."""
        msg1 = ATCMessage(message_key="TEST1", sender="PILOT", delay_after=2.0)
        msg2 = ATCMessage(message_key="TEST2", sender="PILOT", delay_after=2.0)
        msg3 = ATCMessage(message_key="TEST3", sender="PILOT", delay_after=2.0)

        queue.enqueue(msg1)
        queue.enqueue(msg2)
        queue.enqueue(msg3)

        assert queue.get_queue_size() == 3

        # Process first message
        queue.process(0.0)
        assert queue.get_current_message().message_key == "TEST1"
        assert queue.get_queue_size() == 2

        # Complete first, should start second after delay
        time.sleep(1.5)
        queue.process(1.5)
        time.sleep(2.5)
        queue.process(0.0)

        assert queue.get_current_message().message_key == "TEST2"
        assert queue.get_queue_size() == 1

    def test_emergency_interrupt_priority(self, queue):
        """Test that emergency messages (priority >= 9) can interrupt."""
        normal_msg = ATCMessage(message_key="NORMAL", sender="PILOT", priority=0)
        emergency_msg = ATCMessage(message_key="EMERGENCY", sender="PILOT", priority=9)

        # Start playing normal message
        queue.enqueue(normal_msg)
        queue.process(0.0)
        assert queue.is_transmitting()

        # Enqueue emergency message
        queue.enqueue(emergency_msg)

        # Emergency should interrupt (state reset to IDLE)
        assert queue._state == "IDLE"

    def test_get_current_message_returns_none_when_idle(self, queue):
        """Test that get_current_message returns None when idle."""
        assert queue.get_current_message() is None

    def test_get_current_message_during_transmission(self, queue):
        """Test that get_current_message returns message during transmission."""
        msg = ATCMessage(message_key="TEST", sender="PILOT")
        queue.enqueue(msg)
        queue.process(0.0)

        current = queue.get_current_message()
        assert current is not None
        assert current.message_key == "TEST"

    def test_clear_does_not_interrupt_current_message(self, queue):
        """Test that clearing queue doesn't interrupt current message."""
        msg1 = ATCMessage(message_key="CURRENT", sender="PILOT")
        msg2 = ATCMessage(message_key="QUEUED", sender="PILOT")

        queue.enqueue(msg1)
        queue.enqueue(msg2)
        queue.process(0.0)

        # Currently transmitting msg1, msg2 in queue
        assert queue.is_transmitting()
        assert queue.get_queue_size() == 1

        # Clear queue
        queue.clear()

        # Should still be transmitting current message
        assert queue.is_transmitting()
        assert queue.get_current_message().message_key == "CURRENT"
        # But queue should be empty
        assert queue.get_queue_size() == 0

    def test_audio_playback_error_handling(self, queue, mock_atc_audio):
        """Test handling of audio playback errors."""
        # Make audio manager raise exception
        mock_atc_audio.play_atc_message.side_effect = Exception("Audio error")

        msg = ATCMessage(message_key="TEST", sender="PILOT")
        queue.enqueue(msg)

        # Process should handle error gracefully
        queue.process(0.0)

        # Should transition to WAITING state despite error
        assert queue._state == "WAITING"

    def test_callback_error_handling(self, queue):
        """Test that callback errors don't crash the queue."""

        def bad_callback():
            raise Exception("Callback error")

        msg = ATCMessage(message_key="TEST", sender="PILOT", callback=bad_callback)
        queue.enqueue(msg)

        # Start and complete message
        queue.process(0.0)
        time.sleep(1.5)

        # Should handle callback error gracefully
        queue.process(1.5)

        # Queue should continue functioning
        assert queue._state == "WAITING"

    def test_min_max_delay_configuration(self, mock_atc_audio):
        """Test custom min/max delay configuration."""
        queue = ATCMessageQueue(mock_atc_audio, min_delay=5.0, max_delay=15.0)

        msg = ATCMessage(message_key="TEST", sender="ATC", delay_after=0.0)
        queue.enqueue(msg)

        queue.process(0.0)
        time.sleep(1.5)
        queue.process(1.5)

        # Delay should be in custom range
        wait_time = queue._wait_until - time.time()
        assert 4.0 <= wait_time <= 16.0  # Allow tolerance

    def test_message_with_list_of_keys(self, queue, mock_atc_audio):
        """Test message with list of message keys."""
        msg = ATCMessage(
            message_key=["MSG1", "MSG2", "MSG3"], sender="PILOT", delay_after=2.0
        )
        queue.enqueue(msg)

        queue.process(0.0)

        # Audio should be called with list
        mock_atc_audio.play_atc_message.assert_called_once_with(
            ["MSG1", "MSG2", "MSG3"], volume=1.0
        )

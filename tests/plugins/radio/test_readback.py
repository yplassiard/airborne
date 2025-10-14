"""Unit tests for ATC readback system."""

from unittest.mock import Mock

import pytest

from airborne.plugins.radio.readback import (
    ATCInstruction,
    ATCReadbackSystem,
    ReadbackValidator,
)


class TestATCInstruction:
    """Test ATCInstruction dataclass."""

    def test_create_instruction(self):
        """Test creating basic ATC instruction."""
        inst = ATCInstruction(
            message_key="ATC_TOWER_CLEARED_TAKEOFF_31",
            full_text="Runway 31, cleared for takeoff",
            elements={"runway": "31"},
        )

        assert inst.message_key == "ATC_TOWER_CLEARED_TAKEOFF_31"
        assert inst.full_text == "Runway 31, cleared for takeoff"
        assert inst.elements["runway"] == "31"

    def test_create_instruction_without_elements(self):
        """Test creating instruction without elements (auto-initializes)."""
        inst = ATCInstruction(message_key="TEST")

        assert inst.elements == {}


class TestReadbackValidator:
    """Test ReadbackValidator."""

    @pytest.fixture
    def validator(self):
        """Create readback validator."""
        return ReadbackValidator()

    def test_extract_altitude(self, validator):
        """Test extracting altitude from message."""
        message = "Climb and maintain 3000 feet"
        elements = validator.extract_critical_elements(message)

        assert "altitude" in elements
        assert elements["altitude"] == "3000"

    def test_extract_heading(self, validator):
        """Test extracting heading from message."""
        message = "Turn left heading 270"
        elements = validator.extract_critical_elements(message)

        assert "heading" in elements
        assert elements["heading"] == "270"

    def test_extract_runway(self, validator):
        """Test extracting runway from message."""
        message = "Runway 31, cleared for takeoff"
        elements = validator.extract_critical_elements(message)

        assert "runway" in elements
        assert elements["runway"] == "31"

    def test_extract_frequency(self, validator):
        """Test extracting frequency from message."""
        message = "Contact departure 125.35"
        elements = validator.extract_critical_elements(message)

        assert "frequency" in elements
        assert elements["frequency"] == "125.35"

    def test_extract_squawk(self, validator):
        """Test extracting squawk code from message."""
        message = "Squawk 1200"
        elements = validator.extract_critical_elements(message)

        assert "squawk" in elements
        assert elements["squawk"] == "1200"

    def test_extract_speed(self, validator):
        """Test extracting speed from message."""
        message = "Maintain 180 knots"
        elements = validator.extract_critical_elements(message)

        assert "speed" in elements
        assert elements["speed"] == "180"

    def test_extract_multiple_elements(self, validator):
        """Test extracting multiple elements from complex message."""
        message = "Turn left heading 270, climb and maintain 5000 feet, contact departure 125.35"
        elements = validator.extract_critical_elements(message)

        assert "heading" in elements
        assert "altitude" in elements
        assert "frequency" in elements
        assert elements["heading"] == "270"
        assert elements["altitude"] == "5000"
        assert elements["frequency"] == "125.35"

    def test_extract_runway_with_suffix(self, validator):
        """Test extracting runway with L/R/C suffix."""
        message = "Runway 31L, cleared to land"
        elements = validator.extract_critical_elements(message)

        assert elements["runway"] == "31L"

    def test_generate_readback_altitude(self, validator):
        """Test generating readback for altitude."""
        elements = {"altitude": "3000"}
        readback = validator.generate_readback(elements, "Cessna 123AB")

        assert "maintain 3000" in readback.lower()
        assert "123AB" in readback

    def test_generate_readback_heading(self, validator):
        """Test generating readback for heading."""
        elements = {"heading": "270"}
        readback = validator.generate_readback(elements)

        assert "heading 270" in readback.lower()

    def test_generate_readback_runway(self, validator):
        """Test generating readback for runway."""
        elements = {"runway": "31"}
        readback = validator.generate_readback(elements)

        assert "runway 31" in readback.lower()

    def test_generate_readback_multiple_elements(self, validator):
        """Test generating readback with multiple elements."""
        elements = {"altitude": "5000", "heading": "270"}
        readback = validator.generate_readback(elements, "Cessna 123AB")

        assert "5000" in readback
        assert "270" in readback
        assert "123AB" in readback

    def test_generate_readback_no_elements(self, validator):
        """Test generating generic readback when no critical elements."""
        elements = {}
        readback = validator.generate_readback(elements, "Cessna 123AB")

        assert "roger" in readback.lower()
        assert "123AB" in readback

    def test_validate_readback_correct(self, validator):
        """Test validating correct readback."""
        original = {"altitude": "3000", "heading": "270"}
        readback = {"altitude": "3000", "heading": "270"}

        is_correct, errors = validator.validate_readback(original, readback)

        assert is_correct is True
        assert len(errors) == 0

    def test_validate_readback_incorrect_altitude(self, validator):
        """Test validating incorrect altitude readback."""
        original = {"altitude": "3000"}
        readback = {"altitude": "5000"}

        is_correct, errors = validator.validate_readback(original, readback)

        assert is_correct is False
        assert len(errors) == 1
        assert "altitude" in errors[0].lower()

    def test_validate_readback_missing_element(self, validator):
        """Test validating readback with missing element."""
        original = {"altitude": "3000", "heading": "270"}
        readback = {"altitude": "3000"}

        is_correct, errors = validator.validate_readback(original, readback)

        assert is_correct is False
        assert len(errors) == 1
        assert "heading" in errors[0].lower()

    def test_altitude_comma_normalization(self, validator):
        """Test that altitude with comma is normalized correctly."""
        original = {"altitude": "10,000"}
        readback = {"altitude": "10000"}

        is_correct, errors = validator.validate_readback(original, readback)

        assert is_correct is True  # Should match after normalization


class TestATCReadbackSystem:
    """Test ATCReadbackSystem."""

    @pytest.fixture
    def mock_queue(self):
        """Create mock ATC queue."""
        mock = Mock()
        mock.enqueue = Mock()
        return mock

    @pytest.fixture
    def mock_tts(self):
        """Create mock TTS provider."""
        mock = Mock()
        mock.speak = Mock()
        return mock

    @pytest.fixture
    def readback_system(self, mock_queue, mock_tts):
        """Create readback system with mocks."""
        return ATCReadbackSystem(mock_queue, mock_tts, callsign="Cessna 123AB")

    def test_create_system(self, readback_system):
        """Test creating readback system."""
        assert readback_system is not None
        assert readback_system._callsign == "Cessna 123AB"

    def test_record_atc_instruction(self, readback_system):
        """Test recording ATC instruction."""
        readback_system.record_atc_instruction(
            "ATC_TOWER_CLEARED_TAKEOFF_31", "Runway 31, cleared for takeoff"
        )

        history = readback_system.get_instruction_history()
        assert len(history) == 1
        assert history[0].message_key == "ATC_TOWER_CLEARED_TAKEOFF_31"

    def test_record_multiple_instructions(self, readback_system):
        """Test recording multiple instructions."""
        readback_system.record_atc_instruction("MSG1", "Test 1")
        readback_system.record_atc_instruction("MSG2", "Test 2")
        readback_system.record_atc_instruction("MSG3", "Test 3")

        history = readback_system.get_instruction_history()
        assert len(history) == 3

    def test_history_limited_to_3(self, readback_system):
        """Test that history is limited to last 3 instructions."""
        readback_system.record_atc_instruction("MSG1")
        readback_system.record_atc_instruction("MSG2")
        readback_system.record_atc_instruction("MSG3")
        readback_system.record_atc_instruction("MSG4")

        history = readback_system.get_instruction_history()
        assert len(history) == 3
        # Should have MSG2, MSG3, MSG4 (MSG1 dropped)
        assert history[0].message_key == "MSG2"
        assert history[2].message_key == "MSG4"

    def test_get_last_atc_message(self, readback_system):
        """Test getting last ATC message."""
        readback_system.record_atc_instruction("MSG1")
        readback_system.record_atc_instruction("MSG2")

        last = readback_system.get_last_atc_message()
        assert last is not None
        assert last.message_key == "MSG2"

    def test_get_last_atc_message_when_empty(self, readback_system):
        """Test getting last message when history is empty."""
        last = readback_system.get_last_atc_message()
        assert last is None

    def test_acknowledge_with_instruction(self, readback_system, mock_queue):
        """Test acknowledging with instruction in history."""
        readback_system.record_atc_instruction(
            "ATC_TOWER_CLEARED_TAKEOFF_31", "Runway 31, cleared for takeoff"
        )

        result = readback_system.acknowledge()

        assert result is True
        # Should enqueue 2 messages: pilot readback + ATC confirmation
        assert mock_queue.enqueue.call_count == 2

    def test_acknowledge_without_instruction(self, readback_system, mock_queue, mock_tts):
        """Test acknowledging with no instruction."""
        result = readback_system.acknowledge()

        assert result is False
        # Should not enqueue any messages
        mock_queue.enqueue.assert_not_called()
        # Should give audio feedback
        mock_tts.speak.assert_called_once()

    def test_request_repeat_with_instruction(self, readback_system, mock_queue):
        """Test requesting repeat with instruction in history."""
        readback_system.record_atc_instruction("ATC_GROUND_TAXI_RWY_31")

        result = readback_system.request_repeat()

        assert result is True
        # Should enqueue 2 messages: pilot "say again" + ATC repeat
        assert mock_queue.enqueue.call_count == 2

    def test_request_repeat_without_instruction(self, readback_system, mock_queue, mock_tts):
        """Test requesting repeat with no instruction."""
        result = readback_system.request_repeat()

        assert result is False
        # Should not enqueue any messages
        mock_queue.enqueue.assert_not_called()
        # Should give audio feedback
        mock_tts.speak.assert_called_once()

    def test_clear_history(self, readback_system):
        """Test clearing instruction history."""
        readback_system.record_atc_instruction("MSG1")
        readback_system.record_atc_instruction("MSG2")

        assert len(readback_system.get_instruction_history()) == 2

        readback_system.clear_history()

        assert len(readback_system.get_instruction_history()) == 0
        assert readback_system.get_last_atc_message() is None

    def test_set_callsign(self, readback_system):
        """Test updating callsign."""
        assert readback_system._callsign == "Cessna 123AB"

        readback_system.set_callsign("Cessna 456CD")

        assert readback_system._callsign == "Cessna 456CD"

    def test_extract_elements_on_record(self, readback_system):
        """Test that elements are extracted when recording instruction."""
        readback_system.record_atc_instruction(
            "ATC_DEPARTURE_CLIMB_3000", "Climb and maintain 3000 feet"
        )

        last = readback_system.get_last_atc_message()
        assert last is not None
        assert "altitude" in last.elements
        assert last.elements["altitude"] == "3000"

    def test_acknowledge_enqueues_correct_messages(self, readback_system, mock_queue):
        """Test that acknowledge enqueues pilot readback and ATC confirmation."""
        readback_system.record_atc_instruction("MSG")

        readback_system.acknowledge()

        # Get enqueued messages
        calls = mock_queue.enqueue.call_args_list
        assert len(calls) == 2

        # First message should be pilot readback
        pilot_msg = calls[0][0][0]
        assert pilot_msg.sender == "PILOT"
        assert pilot_msg.message_key == "PILOT_READBACK"

        # Second message should be ATC confirmation
        atc_msg = calls[1][0][0]
        assert atc_msg.sender == "ATC"
        assert atc_msg.message_key == "ATC_READBACK_CORRECT"

    def test_repeat_enqueues_correct_messages(self, readback_system, mock_queue):
        """Test that repeat enqueues pilot request and ATC repeat."""
        original_key = "ATC_GROUND_TAXI_RWY_31"
        readback_system.record_atc_instruction(original_key)

        readback_system.request_repeat()

        # Get enqueued messages
        calls = mock_queue.enqueue.call_args_list
        assert len(calls) == 2

        # First message should be pilot "say again"
        pilot_msg = calls[0][0][0]
        assert pilot_msg.sender == "PILOT"
        assert pilot_msg.message_key == "PILOT_SAY_AGAIN"

        # Second message should be ATC repeat of original
        atc_msg = calls[1][0][0]
        assert atc_msg.sender == "ATC"
        assert atc_msg.message_key == original_key

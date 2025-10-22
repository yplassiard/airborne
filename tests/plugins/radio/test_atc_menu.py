"""Unit tests for ATC menu system."""

from unittest.mock import Mock

import pytest

from airborne.plugins.radio.atc_menu import ATCMenu, FlightPhase


class TestFlightPhase:
    """Test FlightPhase enum."""

    def test_flight_phase_values(self):
        """Test that all flight phases are defined."""
        assert FlightPhase.ON_GROUND_ENGINE_OFF
        assert FlightPhase.ON_GROUND_ENGINE_RUNNING
        assert FlightPhase.HOLDING_SHORT
        assert FlightPhase.ON_RUNWAY
        assert FlightPhase.AIRBORNE_DEPARTURE
        assert FlightPhase.AIRBORNE_CRUISE
        assert FlightPhase.AIRBORNE_APPROACH
        assert FlightPhase.UNKNOWN


class TestATCMenu:
    """Test ATCMenu."""

    @pytest.fixture
    def mock_tts(self):
        """Create mock TTS provider."""
        mock = Mock()
        mock.speak = Mock()
        return mock

    @pytest.fixture
    def mock_queue(self):
        """Create mock ATC queue."""
        mock = Mock()
        mock.enqueue = Mock()
        mock.is_busy = Mock(return_value=False)
        return mock

    @pytest.fixture
    def mock_message_queue(self):
        """Create mock message queue."""
        mock = Mock()
        mock.publish = Mock()
        return mock

    @pytest.fixture
    def menu(self, mock_tts, mock_queue, mock_message_queue):
        """Create ATC menu with mocks."""
        return ATCMenu(mock_tts, mock_queue, mock_message_queue)

    def test_create_menu(self, menu):
        """Test creating menu."""
        assert menu is not None
        assert not menu.is_open()
        assert menu.get_state() == "CLOSED"
        assert menu.get_current_phase() == FlightPhase.UNKNOWN

    def test_determine_flight_phase_engine_off(self, menu):
        """Test flight phase determination for engine off."""
        state = {
            "on_ground": True,
            "engine_running": False,
            "altitude_agl": 0.0,
        }

        phase = menu._determine_flight_phase(state)
        assert phase == FlightPhase.ON_GROUND_ENGINE_OFF

    def test_determine_flight_phase_engine_running(self, menu):
        """Test flight phase determination for engine running."""
        state = {
            "on_ground": True,
            "engine_running": True,
            "altitude_agl": 0.0,
        }

        phase = menu._determine_flight_phase(state)
        assert phase == FlightPhase.ON_GROUND_ENGINE_RUNNING

    def test_determine_flight_phase_holding_short(self, menu):
        """Test flight phase determination for holding short."""
        state = {
            "on_ground": True,
            "engine_running": True,
            "altitude_agl": 0.0,
            "holding_short": True,
        }

        phase = menu._determine_flight_phase(state)
        assert phase == FlightPhase.HOLDING_SHORT

    def test_determine_flight_phase_on_runway(self, menu):
        """Test flight phase determination for on runway."""
        state = {
            "on_ground": True,
            "engine_running": True,
            "altitude_agl": 0.0,
            "on_runway": True,
        }

        phase = menu._determine_flight_phase(state)
        assert phase == FlightPhase.ON_RUNWAY

    def test_determine_flight_phase_airborne_departure(self, menu):
        """Test flight phase determination for departure."""
        state = {
            "on_ground": False,
            "engine_running": True,
            "altitude_agl": 1500.0,
        }

        phase = menu._determine_flight_phase(state)
        assert phase == FlightPhase.AIRBORNE_DEPARTURE

    def test_determine_flight_phase_airborne_cruise(self, menu):
        """Test flight phase determination for cruise."""
        state = {
            "on_ground": False,
            "engine_running": True,
            "altitude_agl": 15000.0,
        }

        phase = menu._determine_flight_phase(state)
        assert phase == FlightPhase.AIRBORNE_CRUISE

    def test_get_context_options_engine_off(self, menu):
        """Test getting options for engine off phase."""
        options = menu._get_context_options(FlightPhase.ON_GROUND_ENGINE_OFF)

        assert len(options) >= 1
        assert any("Startup" in opt.label for opt in options)
        assert any("ATIS" in opt.label for opt in options)

    def test_get_context_options_engine_running(self, menu):
        """Test getting options for engine running phase."""
        options = menu._get_context_options(FlightPhase.ON_GROUND_ENGINE_RUNNING)

        assert len(options) >= 1
        assert any("Taxi" in opt.label for opt in options)

    def test_get_context_options_holding_short(self, menu):
        """Test getting options for holding short phase."""
        options = menu._get_context_options(FlightPhase.HOLDING_SHORT)

        assert len(options) >= 1
        assert any("Takeoff" in opt.label for opt in options)

    def test_get_context_options_airborne(self, menu):
        """Test getting options for airborne phase."""
        options = menu._get_context_options(FlightPhase.AIRBORNE_DEPARTURE)

        assert len(options) >= 1
        # Should have departure-related options

    def test_open_menu(self, menu, mock_message_queue):
        """Test opening menu."""
        state = {
            "on_ground": True,
            "engine_running": True,
            "altitude_agl": 0.0,
        }

        menu.open(state)

        assert menu.is_open()
        assert menu.get_state() == "OPEN"
        assert menu.get_current_phase() == FlightPhase.ON_GROUND_ENGINE_RUNNING
        assert len(menu.get_current_options()) > 0

        # Should have published TTS message to read menu
        mock_message_queue.publish.assert_called()

    def test_close_menu(self, menu):
        """Test closing menu."""
        state = {"on_ground": True, "engine_running": True, "altitude_agl": 0.0}
        menu.open(state)

        assert menu.is_open()

        menu.close()

        assert not menu.is_open()
        assert menu.get_state() == "CLOSED"
        assert len(menu.get_current_options()) == 0

    def test_select_valid_option(self, menu, mock_queue):
        """Test selecting valid menu option."""
        state = {"on_ground": True, "engine_running": True, "altitude_agl": 0.0}
        menu.open(state)

        # Select first option
        result = menu.select_option("1")

        assert result is True
        assert menu.get_state() == "WAITING_RESPONSE"

        # Should have enqueued messages
        assert mock_queue.enqueue.call_count == 2  # Pilot + ATC

    def test_select_invalid_option(self, menu, mock_queue, mock_message_queue):
        """Test selecting invalid menu option."""
        state = {"on_ground": True, "engine_running": True, "altitude_agl": 0.0}
        menu.open(state)

        # Clear previous message queue calls
        mock_message_queue.publish.reset_mock()

        # Select invalid option
        result = menu.select_option("9")

        assert result is False
        assert menu.is_open()  # Menu stays open

        # Should not enqueue messages
        mock_queue.enqueue.assert_not_called()

        # Should give audio feedback via message queue
        mock_message_queue.publish.assert_called()

    def test_select_option_when_closed(self, menu, mock_queue):
        """Test selecting option when menu is closed."""
        result = menu.select_option("1")

        assert result is False
        mock_queue.enqueue.assert_not_called()

    def test_is_available_when_queue_busy(self, menu, mock_queue):
        """Test menu availability when queue is busy."""
        mock_queue.is_busy.return_value = True

        state = {"on_ground": True, "engine_running": True, "altitude_agl": 0.0}

        assert not menu.is_available(state)

    def test_is_available_when_queue_idle(self, menu, mock_queue):
        """Test menu availability when queue is idle."""
        mock_queue.is_busy.return_value = False

        state = {"on_ground": True, "engine_running": True, "altitude_agl": 0.0}

        assert menu.is_available(state)

    def test_read_menu(self, menu, mock_message_queue):
        """Test reading menu aloud."""
        state = {"on_ground": True, "engine_running": True, "altitude_agl": 0.0}

        # Open menu - this automatically announces the menu
        menu.open(state)

        # Should have published TTS message during open
        mock_message_queue.publish.assert_called()

        # Check that message data contains message keys (menu now uses keys)
        call_args = mock_message_queue.publish.call_args[0][0]
        message_keys = call_args.data.get("text", [])
        # Should be a list of message keys
        assert isinstance(message_keys, list)
        assert len(message_keys) > 0
        # Should contain menu-related message keys
        assert any(
            "MSG_ATC_MENU" in str(key) or "MSG_ATC_OPTION" in str(key) for key in message_keys
        )

    def test_option_with_callback(self, menu, mock_queue):
        """Test that option callback is executed."""
        callback_called = False

        def callback():
            nonlocal callback_called
            callback_called = True

        state = {"on_ground": True, "engine_running": True, "altitude_agl": 0.0}
        menu.open(state)

        # Modify first option to have callback (callbacks are now in data dict)
        menu._current_options[0].data["callback"] = callback

        # Select option
        menu.select_option("1")

        # Callback should have been called
        assert callback_called

    def test_atc_response_completion_callback(self, menu):
        """Test ATC response completion callback."""
        state = {"on_ground": True, "engine_running": True, "altitude_agl": 0.0}
        menu.open(state)
        menu.select_option("1")

        # Should be waiting for response
        assert menu.is_waiting_response()

        # Simulate ATC response completion
        menu._on_atc_response_complete()

        # Should return to closed state
        assert menu.get_state() == "CLOSED"
        assert not menu.is_waiting_response()

    def test_multiple_phases_have_options(self, menu):
        """Test that all major flight phases have menu options."""
        phases_to_test = [
            FlightPhase.ON_GROUND_ENGINE_OFF,
            FlightPhase.ON_GROUND_ENGINE_RUNNING,
            FlightPhase.HOLDING_SHORT,
            FlightPhase.ON_RUNWAY,
            FlightPhase.AIRBORNE_DEPARTURE,
            FlightPhase.AIRBORNE_CRUISE,
        ]

        for phase in phases_to_test:
            options = menu._get_context_options(phase)
            assert len(options) > 0, f"Phase {phase.value} should have options"

"""Unit tests for PerformanceDisplay."""

import pytest

from airborne.core.messaging import MessageQueue
from airborne.systems.performance.performance_calculator import PerformanceCalculator
from airborne.systems.weight_balance.weight_balance_system import WeightBalanceSystem
from airborne.ui.performance_display import PerformanceDisplay


@pytest.fixture
def weight_balance_system():
    """Create a weight and balance system for testing."""
    config = {
        "empty_weight": 1600.0,
        "empty_moment": 136000.0,
        "max_gross_weight": 2550.0,
        "cg_limits": {"forward": 82.9, "aft": 95.5},
        "stations": {
            "fuel": [
                {
                    "name": "fuel_main",
                    "arm": 95.0,
                    "max_weight": 312.0,
                    "initial_weight": 312.0,  # Full fuel
                }
            ],
            "seats": [
                {
                    "name": "seat_pilot",
                    "arm": 85.0,
                    "max_weight": 200.0,
                    "initial_weight": 200.0,  # Pilot present
                }
            ],
            "cargo": [],
        },
    }
    return WeightBalanceSystem(config)


@pytest.fixture
def performance_calculator():
    """Create a performance calculator for testing."""
    config = {
        "reference_weight_lbs": 2550.0,
        "wing_area_sqft": 174.0,
        "cl_max_clean": 1.4,
        "cl_max_landing": 2.0,
        "vspeeds_reference": {
            "V_S": 47.0,  # Stall speed at reference weight
            "V_R": 55.0,
            "V_X": 59.0,
            "V_Y": 73.0,
        },
        "takeoff_reference": {
            "ground_roll_ft": 960.0,
            "distance_50ft": 1685.0,
            "climb_rate_fpm": 730.0,
        },
        "max_power_hp": 180.0,
    }
    return PerformanceCalculator(config)


@pytest.fixture
def message_queue():
    """Create a message queue for testing."""
    return MessageQueue()


@pytest.fixture
def performance_display(weight_balance_system, performance_calculator, message_queue):
    """Create a performance display for testing."""
    return PerformanceDisplay(
        wb_system=weight_balance_system,
        perf_calculator=performance_calculator,
        message_queue=message_queue,
    )


def test_performance_display_initialization(performance_display):
    """Test performance display initializes correctly."""
    assert performance_display is not None
    assert performance_display.wb_system is not None
    assert performance_display.perf_calculator is not None
    assert not performance_display.is_open()
    assert performance_display.get_current_page() == 1


def test_performance_display_open(performance_display):
    """Test opening the performance display."""
    success = performance_display.open()
    assert success
    assert performance_display.is_open()
    assert performance_display.get_current_page() == 1


def test_performance_display_open_twice(performance_display):
    """Test opening display twice returns False."""
    assert performance_display.open()
    assert not performance_display.open()  # Second open should fail


def test_performance_display_close(performance_display):
    """Test closing the performance display."""
    performance_display.open()
    success = performance_display.close()
    assert success
    assert not performance_display.is_open()


def test_performance_display_close_when_closed(performance_display):
    """Test closing when already closed returns False."""
    assert not performance_display.close()


def test_performance_display_next_page(performance_display):
    """Test navigating to next page."""
    performance_display.open()
    assert performance_display.get_current_page() == 1

    # Page 1 -> 2
    assert performance_display.next_page()
    assert performance_display.get_current_page() == 2

    # Page 2 -> 3
    assert performance_display.next_page()
    assert performance_display.get_current_page() == 3

    # Page 3 -> can't go further
    assert not performance_display.next_page()
    assert performance_display.get_current_page() == 3


def test_performance_display_previous_page(performance_display):
    """Test navigating to previous page."""
    performance_display.open()

    # Navigate to page 3 first
    performance_display.next_page()
    performance_display.next_page()
    assert performance_display.get_current_page() == 3

    # Page 3 -> 2
    assert performance_display.previous_page()
    assert performance_display.get_current_page() == 2

    # Page 2 -> 1
    assert performance_display.previous_page()
    assert performance_display.get_current_page() == 1

    # Page 1 -> can't go back
    assert not performance_display.previous_page()
    assert performance_display.get_current_page() == 1


def test_performance_display_navigation_when_closed(performance_display):
    """Test navigation when display is closed returns False."""
    assert not performance_display.next_page()
    assert not performance_display.previous_page()
    assert not performance_display.read_current_page()


def test_performance_display_read_weight_balance_page(performance_display):
    """Test reading Weight & Balance page."""
    performance_display.open()
    assert performance_display.get_current_page() == 1

    # Read page - should not raise errors
    success = performance_display.read_current_page()
    assert success

    # Verify weight calculation works
    weight = performance_display.wb_system.calculate_total_weight()
    assert weight > 0


def test_performance_display_read_vspeeds_page(performance_display):
    """Test reading V-speeds page."""
    performance_display.open()
    performance_display.next_page()  # Move to page 2
    assert performance_display.get_current_page() == 2

    # Read page - should not raise errors
    success = performance_display.read_current_page()
    assert success

    # Verify V-speed calculation works
    weight = performance_display.wb_system.calculate_total_weight()
    vspeeds = performance_display.perf_calculator.calculate_vspeeds(weight)
    assert vspeeds.v_s > 0


def test_performance_display_read_takeoff_page(performance_display):
    """Test reading Takeoff Performance page."""
    performance_display.open()
    performance_display.next_page()  # Page 2
    performance_display.next_page()  # Page 3
    assert performance_display.get_current_page() == 3

    # Read page - should not raise errors
    success = performance_display.read_current_page()
    assert success

    # Verify takeoff calculation works
    weight = performance_display.wb_system.calculate_total_weight()
    takeoff = performance_display.perf_calculator.calculate_takeoff_distance(weight)
    assert takeoff.ground_roll_ft > 0


def test_performance_display_without_systems():
    """Test display without weight/balance or performance systems."""
    display = PerformanceDisplay(wb_system=None, perf_calculator=None, message_queue=None)
    assert not display.open()  # Should fail to open


def test_performance_display_weight_to_speech(performance_display):
    """Test weight-to-speech conversion."""
    # Test simple numbers (0-100)
    assert performance_display._weight_to_speech(50.0) == "MSG_NUMBER_50"
    assert performance_display._weight_to_speech(100.0) == "MSG_NUMBER_100"

    # Test rounding to nearest 10 and speech conversion
    # 2547 rounds to 2550 -> ['MSG_NUMBER_2', 'MSG_WORD_THOUSAND', ...]
    result = performance_display._weight_to_speech(2547.0)
    assert isinstance(result, list)
    assert "MSG_NUMBER_2" in result
    assert "MSG_WORD_THOUSAND" in result

    # 2543 rounds to 2540
    result = performance_display._weight_to_speech(2543.0)
    assert isinstance(result, list)
    assert "MSG_NUMBER_2" in result
    assert "MSG_WORD_THOUSAND" in result


def test_performance_display_number_to_speech(performance_display):
    """Test number-to-speech conversion."""
    # Simple numbers
    assert performance_display._number_to_speech(0) == "MSG_NUMBER_0"
    assert performance_display._number_to_speech(50) == "MSG_NUMBER_50"
    assert performance_display._number_to_speech(100) == "MSG_NUMBER_100"

    # Hundreds
    result = performance_display._number_to_speech(500)
    assert isinstance(result, list)
    assert "MSG_NUMBER_5" in result
    assert "MSG_WORD_HUNDRED" in result

    # Thousands
    result = performance_display._number_to_speech(2000)
    assert isinstance(result, list)
    assert "MSG_NUMBER_2" in result
    assert "MSG_WORD_THOUSAND" in result

    # Thousands with remainder
    result = performance_display._number_to_speech(2500)
    assert isinstance(result, list)
    assert "MSG_NUMBER_2" in result
    assert "MSG_WORD_THOUSAND" in result
    assert "MSG_NUMBER_5" in result
    assert "MSG_WORD_HUNDRED" in result


def test_performance_display_calculates_correct_weight(performance_display):
    """Test display calculates correct current weight."""
    # Initial weight: empty (1600) + fuel (312) + pilot (200) = 2112 lbs
    performance_display.open()

    # Weight should be around 2112 lbs
    total_weight = performance_display.wb_system.calculate_total_weight()
    assert 2110 <= total_weight <= 2115


def test_performance_display_calculates_vspeeds(performance_display):
    """Test display calculates V-speeds for current weight."""
    performance_display.open()

    # Calculate V-speeds
    weight = performance_display.wb_system.calculate_total_weight()
    vspeeds = performance_display.perf_calculator.calculate_vspeeds(weight)

    # V-speeds should be lower than reference (aircraft is lighter)
    assert vspeeds.v_s < 47.0  # Stall speed lower than reference
    assert vspeeds.v_r < 55.0  # Rotation speed lower
    assert vspeeds.v_y < 73.0  # Best rate of climb lower


def test_performance_display_calculates_takeoff_distance(performance_display):
    """Test display calculates takeoff distances."""
    performance_display.open()

    # Calculate takeoff performance
    weight = performance_display.wb_system.calculate_total_weight()
    takeoff = performance_display.perf_calculator.calculate_takeoff_distance(weight)

    # Lighter aircraft should have shorter ground roll than reference
    assert takeoff.ground_roll_ft < 960.0
    assert takeoff.distance_50ft < 1685.0

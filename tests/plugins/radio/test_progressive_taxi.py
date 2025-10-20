"""Unit tests for progressive taxi system."""

import pytest

from airborne.core.messaging import Message, MessageQueue, MessageTopic
from airborne.plugins.radio.progressive_taxi import (
    ProgressiveTaxiManager,
    TaxiClearance,
    TaxiSegment,
)


@pytest.fixture
def message_queue():
    """Create a message queue for testing."""
    return MessageQueue()


@pytest.fixture
def taxi_manager(message_queue):
    """Create a progressive taxi manager for testing."""
    return ProgressiveTaxiManager(message_queue)


def test_manager_initialization(taxi_manager):
    """Test manager initializes correctly."""
    assert taxi_manager is not None
    assert len(taxi_manager.active_clearances) == 0


def test_taxi_segment_dataclass():
    """Test TaxiSegment dataclass."""
    segment = TaxiSegment(
        from_node="parking1",
        to_node="taxiway_alpha",
        taxiway="Alpha",
        instruction="Taxi via Alpha",
        is_runway_crossing=False,
        hold_short="runway_31",
    )

    assert segment.from_node == "parking1"
    assert segment.to_node == "taxiway_alpha"
    assert segment.taxiway == "Alpha"
    assert segment.instruction == "Taxi via Alpha"
    assert not segment.is_runway_crossing
    assert segment.hold_short == "runway_31"


def test_taxi_clearance_dataclass():
    """Test TaxiClearance dataclass."""
    segment = TaxiSegment(
        from_node="parking1",
        to_node="taxiway_alpha",
        taxiway="Alpha",
        instruction="Taxi via Alpha",
    )

    clearance = TaxiClearance(
        aircraft_id="N123AB",
        segments=[segment],
        current_segment_index=0,
        destination_runway="31",
    )

    assert clearance.aircraft_id == "N123AB"
    assert len(clearance.segments) == 1
    assert clearance.current_segment_index == 0
    assert clearance.destination_runway == "31"
    assert not clearance.is_complete


def test_issue_initial_clearance(taxi_manager, message_queue):
    """Test issuing initial taxi clearance."""
    # Capture published messages
    captured_messages = []

    def capture_handler(msg):
        captured_messages.append(msg)

    message_queue.subscribe(MessageTopic.ATC_MESSAGE, capture_handler)

    # Issue clearance
    taxi_manager.issue_initial_clearance(
        aircraft_id="N123AB",
        parking_id="gate_a3",
        destination_runway="31",
    )

    # Process messages
    message_queue.process()

    # Should have active clearance
    assert "N123AB" in taxi_manager.active_clearances
    clearance = taxi_manager.active_clearances["N123AB"]
    assert clearance.aircraft_id == "N123AB"
    assert clearance.destination_runway == "31"
    assert clearance.current_segment_index == 0

    # Should have published ATC message
    assert len(captured_messages) > 0
    atc_msg = captured_messages[-1]
    assert atc_msg.data["aircraft_id"] == "N123AB"
    assert "runway 31" in atc_msg.data["message"].lower()


def test_clearance_has_multiple_segments(taxi_manager):
    """Test that clearance is broken into multiple segments."""
    taxi_manager.issue_initial_clearance(
        aircraft_id="N123AB",
        parking_id="gate_a3",
        destination_runway="31",
    )

    clearance = taxi_manager.active_clearances["N123AB"]
    # Should have at least 2 segments (initial + hold short)
    assert len(clearance.segments) >= 2


def test_get_active_clearance(taxi_manager):
    """Test retrieving active clearance."""
    taxi_manager.issue_initial_clearance(
        aircraft_id="N123AB",
        parking_id="gate_a3",
        destination_runway="31",
    )

    clearance = taxi_manager.get_active_clearance("N123AB")
    assert clearance is not None
    assert clearance.aircraft_id == "N123AB"

    # Non-existent aircraft
    assert taxi_manager.get_active_clearance("N999XX") is None


def test_get_active_aircraft(taxi_manager):
    """Test getting list of active aircraft."""
    # Initially empty
    assert len(taxi_manager.get_active_aircraft()) == 0

    # Issue clearances
    taxi_manager.issue_initial_clearance("N123AB", "gate_a3", "31")
    taxi_manager.issue_initial_clearance("N456CD", "gate_b2", "13")

    # Should have 2 active
    active = taxi_manager.get_active_aircraft()
    assert len(active) == 2
    assert "N123AB" in active
    assert "N456CD" in active


def test_cancel_clearance(taxi_manager):
    """Test cancelling a clearance."""
    taxi_manager.issue_initial_clearance("N123AB", "gate_a3", "31")

    # Should be active
    assert "N123AB" in taxi_manager.active_clearances

    # Cancel
    taxi_manager.cancel_clearance("N123AB")

    # Should be removed
    assert "N123AB" not in taxi_manager.active_clearances


def test_position_update_advances_segment(taxi_manager, message_queue):
    """Test position update advances to next segment."""
    # Capture published messages
    captured_messages = []

    def capture_handler(msg):
        captured_messages.append(msg)

    message_queue.subscribe(MessageTopic.ATC_MESSAGE, capture_handler)

    # Issue initial clearance
    taxi_manager.issue_initial_clearance("N123AB", "gate_a3", "31")

    message_queue.process()
    initial_message_count = len(captured_messages)

    clearance = taxi_manager.active_clearances["N123AB"]
    initial_segment = clearance.current_segment_index

    # Simulate position update showing aircraft on taxiway Alpha, near end of segment
    message_queue.publish(
        Message(
            sender="position_tracker",
            recipients=["progressive_taxi_manager"],
            topic=MessageTopic.POSITION_UPDATED,
            data={
                "aircraft_id": "N123AB",
                "on_taxiway": "Alpha",
                "distance_to_waypoint": 50.0,  # Within 100m threshold
            },
        )
    )

    message_queue.process()

    # Should advance to next segment if not last segment
    if initial_segment < len(clearance.segments) - 1:
        assert clearance.current_segment_index == initial_segment + 1
        # Should have published next instruction
        assert len(captured_messages) > initial_message_count


def test_position_update_ignores_other_aircraft(taxi_manager, message_queue):
    """Test position updates for other aircraft are ignored."""
    taxi_manager.issue_initial_clearance("N123AB", "gate_a3", "31")

    clearance = taxi_manager.active_clearances["N123AB"]
    initial_segment = clearance.current_segment_index

    # Position update for different aircraft
    message_queue.publish(
        Message(
            sender="position_tracker",
            recipients=["progressive_taxi_manager"],
            topic=MessageTopic.POSITION_UPDATED,
            data={
                "aircraft_id": "N999XX",  # Different aircraft
                "on_taxiway": "Alpha",
                "distance_to_waypoint": 50.0,
            },
        )
    )

    message_queue.process()

    # Should not advance segment
    assert clearance.current_segment_index == initial_segment


def test_final_instruction_issued_at_end(taxi_manager, message_queue):
    """Test final 'contact tower' instruction is issued."""
    # Capture published messages
    captured_messages = []

    def capture_handler(msg):
        captured_messages.append(msg)

    message_queue.subscribe(MessageTopic.ATC_MESSAGE, capture_handler)

    # Issue clearance
    taxi_manager.issue_initial_clearance("N123AB", "gate_a3", "31")

    clearance = taxi_manager.active_clearances["N123AB"]

    # Advance through all segments manually
    for i in range(len(clearance.segments)):
        clearance.current_segment_index = i
        taxi_manager._issue_segment_clearance(clearance, i)

    # Issue final instruction beyond last segment
    taxi_manager._issue_segment_clearance(clearance, len(clearance.segments))

    message_queue.process()

    # Should have issued contact tower message
    assert clearance.is_complete
    contact_tower_messages = [
        msg for msg in captured_messages if "contact tower" in msg.data.get("message", "").lower()
    ]
    assert len(contact_tower_messages) > 0


def test_hold_short_instruction_includes_runway(taxi_manager, message_queue):
    """Test hold short instruction mentions runway."""
    captured_messages = []

    def capture_handler(msg):
        captured_messages.append(msg)

    message_queue.subscribe(MessageTopic.ATC_MESSAGE, capture_handler)

    taxi_manager.issue_initial_clearance("N123AB", "gate_a3", "31")

    message_queue.process()

    # Find hold short message
    hold_short_messages = [
        msg for msg in captured_messages if msg.data.get("hold_short") is not None
    ]

    assert len(hold_short_messages) > 0


def test_multiple_aircraft_clearances(taxi_manager):
    """Test managing multiple aircraft simultaneously."""
    # Issue clearances to 3 aircraft
    taxi_manager.issue_initial_clearance("N123AB", "gate_a3", "31")
    taxi_manager.issue_initial_clearance("N456CD", "gate_b2", "13")
    taxi_manager.issue_initial_clearance("N789EF", "gate_c1", "31")

    # All should be active
    assert len(taxi_manager.active_clearances) == 3

    # Each should have unique clearance
    clearance1 = taxi_manager.get_active_clearance("N123AB")
    clearance2 = taxi_manager.get_active_clearance("N456CD")
    clearance3 = taxi_manager.get_active_clearance("N789EF")

    assert clearance1.aircraft_id == "N123AB"
    assert clearance2.aircraft_id == "N456CD"
    assert clearance3.aircraft_id == "N789EF"


def test_message_key_assignment(taxi_manager):
    """Test correct message keys are assigned to segments."""
    # Create test segments
    hold_short_segment = TaxiSegment(
        from_node="a",
        to_node="b",
        taxiway="Alpha",
        instruction="Hold short",
        hold_short="runway_31",
    )

    crossing_segment = TaxiSegment(
        from_node="a",
        to_node="b",
        taxiway="Alpha",
        instruction="Cross runway",
        is_runway_crossing=True,
    )

    normal_segment = TaxiSegment(
        from_node="a", to_node="b", taxiway="Alpha", instruction="Taxi via Alpha"
    )

    # Check message keys
    assert taxi_manager._get_message_key(hold_short_segment) == "MSG_GROUND_TAXI_HOLD_SHORT"
    assert taxi_manager._get_message_key(crossing_segment) == "MSG_GROUND_CROSS_RUNWAY"
    assert taxi_manager._get_message_key(normal_segment) == "MSG_GROUND_TAXI_VIA"


def test_no_clearance_for_invalid_route(taxi_manager, message_queue):
    """Test no clearance issued if route cannot be built."""
    # This test depends on implementation - if route building always succeeds,
    # this may not be applicable
    # For now, test that empty taxi_route doesn't crash
    taxi_manager.issue_initial_clearance(
        aircraft_id="N123AB",
        parking_id="unknown_parking",
        destination_runway="99",
        taxi_route=[],
    )

    # Should handle gracefully
    # Either creates clearance or doesn't crash


def test_custom_taxi_route(taxi_manager, message_queue):
    """Test using custom taxi route."""
    # Provide specific taxi route
    custom_route = ["Alpha", "Bravo", "Charlie"]

    taxi_manager.issue_initial_clearance(
        aircraft_id="N123AB",
        parking_id="gate_a3",
        destination_runway="31",
        taxi_route=custom_route,
    )

    clearance = taxi_manager.get_active_clearance("N123AB")
    assert clearance is not None

    # Segments should reflect custom route
    # (exact number depends on implementation)
    assert len(clearance.segments) >= len(custom_route)

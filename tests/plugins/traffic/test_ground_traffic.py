"""Unit tests for ground traffic management."""

import time

import pytest

from airborne.core.messaging import MessageQueue, MessageTopic
from airborne.plugins.traffic.ground_traffic import (
    GroundTrafficAircraft,
    GroundTrafficManager,
    GroundTrafficState,
)


@pytest.fixture
def message_queue():
    """Create a message queue for testing."""
    return MessageQueue()


@pytest.fixture
def traffic_manager(message_queue):
    """Create a ground traffic manager for testing."""
    return GroundTrafficManager(message_queue)


def test_manager_initialization(traffic_manager):
    """Test manager initializes correctly."""
    assert traffic_manager is not None
    assert traffic_manager.get_traffic_count() == 0
    assert traffic_manager.taxi_speed_kts == 12.0


def test_ground_traffic_state_enum():
    """Test GroundTrafficState enum."""
    assert GroundTrafficState.PARKED.value == "parked"
    assert GroundTrafficState.TAXIING.value == "taxiing"
    assert GroundTrafficState.HOLDING.value == "holding"


def test_ground_traffic_aircraft_dataclass():
    """Test GroundTrafficAircraft dataclass."""
    aircraft = GroundTrafficAircraft(
        aircraft_id="AI_N001CD",
        callsign="N001CD",
        aircraft_type="C172",
        position=(0.0, 0.0, 0.0),
        heading=0.0,
        speed=0.0,
        state=GroundTrafficState.PARKED,
        parking_id="parking_1",
        destination_runway="31",
        taxi_route=["Alpha", "Bravo"],
    )

    assert aircraft.aircraft_id == "AI_N001CD"
    assert aircraft.state == GroundTrafficState.PARKED
    assert aircraft.destination_runway == "31"
    assert len(aircraft.taxi_route) == 2


def test_spawn_single_aircraft(traffic_manager, message_queue):
    """Test spawning a single aircraft."""
    # Capture traffic updates
    captured_messages = []

    def capture_handler(msg):
        captured_messages.append(msg)

    message_queue.subscribe(MessageTopic.TRAFFIC_UPDATE, capture_handler)

    # Spawn aircraft
    traffic_manager.spawn_traffic(count=1)

    # Should have 1 aircraft
    assert traffic_manager.get_traffic_count() == 1

    # Process messages
    message_queue.process()

    # Should have published traffic update
    assert len(captured_messages) > 0
    traffic_msg = captured_messages[-1]
    assert "aircraft_id" in traffic_msg.data
    assert traffic_msg.data["on_ground"] is True


def test_spawn_multiple_aircraft(traffic_manager):
    """Test spawning multiple aircraft."""
    traffic_manager.spawn_traffic(count=3)

    assert traffic_manager.get_traffic_count() == 3

    # Each should have unique ID
    ids = list(traffic_manager.traffic.keys())
    assert len(ids) == len(set(ids))  # All unique


def test_max_traffic_limit(traffic_manager):
    """Test maximum traffic limit is enforced."""
    # Set low max
    traffic_manager.max_traffic = 2

    # Try to spawn 5
    traffic_manager.spawn_traffic(count=5)

    # Should only have 2
    assert traffic_manager.get_traffic_count() == 2


def test_get_aircraft(traffic_manager):
    """Test retrieving specific aircraft."""
    traffic_manager.spawn_traffic(count=1)

    # Get first aircraft ID
    aircraft_id = list(traffic_manager.traffic.keys())[0]

    # Retrieve it
    aircraft = traffic_manager.get_aircraft(aircraft_id)
    assert aircraft is not None
    assert aircraft.aircraft_id == aircraft_id

    # Non-existent aircraft
    assert traffic_manager.get_aircraft("NONEXISTENT") is None


def test_aircraft_starts_parked(traffic_manager):
    """Test aircraft starts in PARKED state."""
    traffic_manager.spawn_traffic(count=1)

    aircraft_id = list(traffic_manager.traffic.keys())[0]
    aircraft = traffic_manager.get_aircraft(aircraft_id)

    assert aircraft.state == GroundTrafficState.PARKED
    assert aircraft.speed == 0.0


def test_aircraft_requests_taxi_after_delay(traffic_manager):
    """Test aircraft requests taxi after spawn delay."""
    traffic_manager.spawn_traffic(count=1)

    aircraft_id = list(traffic_manager.traffic.keys())[0]
    aircraft = traffic_manager.get_aircraft(aircraft_id)

    # Set spawn time in past
    aircraft.spawn_time = time.time() - 15.0

    # Update should trigger taxi request
    traffic_manager._update_aircraft(aircraft, 1.0)

    # Should be requesting taxi
    assert aircraft.state == GroundTrafficState.REQUESTING_TAXI


def test_aircraft_starts_taxiing_after_clearance(traffic_manager):
    """Test aircraft starts taxiing after clearance."""
    traffic_manager.spawn_traffic(count=1)

    aircraft_id = list(traffic_manager.traffic.keys())[0]
    aircraft = traffic_manager.get_aircraft(aircraft_id)

    # Move to requesting state
    aircraft.state = GroundTrafficState.REQUESTING_TAXI
    aircraft.spawn_time = time.time() - 20.0

    # Update should start taxiing
    traffic_manager._update_aircraft(aircraft, 1.0)

    # Should be taxiing
    assert aircraft.state == GroundTrafficState.TAXIING
    assert aircraft.speed == traffic_manager.taxi_speed_kts


def test_aircraft_moves_when_taxiing(traffic_manager):
    """Test aircraft position updates when taxiing."""
    traffic_manager.spawn_traffic(count=1)

    aircraft_id = list(traffic_manager.traffic.keys())[0]
    aircraft = traffic_manager.get_aircraft(aircraft_id)

    # Set to taxiing
    aircraft.state = GroundTrafficState.TAXIING
    aircraft.speed = 12.0
    initial_pos = aircraft.position

    # Update for 1 second
    traffic_manager._move_aircraft(aircraft, 1.0)

    # Position should have changed
    assert aircraft.position != initial_pos


def test_aircraft_holds_when_instructed(traffic_manager):
    """Test aircraft holds when hold_short_node is set."""
    traffic_manager.spawn_traffic(count=1)

    aircraft_id = list(traffic_manager.traffic.keys())[0]
    aircraft = traffic_manager.get_aircraft(aircraft_id)

    # Set to taxiing with hold-short
    aircraft.state = GroundTrafficState.TAXIING
    aircraft.speed = 12.0
    aircraft.hold_short_node = "conflict_hold"

    # Move should stop aircraft
    traffic_manager._move_aircraft(aircraft, 1.0)

    # Should be holding
    assert aircraft.state == GroundTrafficState.HOLDING
    assert aircraft.speed == 0.0


def test_conflict_detection(traffic_manager, message_queue):
    """Test conflict detection between aircraft."""
    # Capture ATC messages
    captured_messages = []

    def capture_handler(msg):
        captured_messages.append(msg)

    message_queue.subscribe(MessageTopic.ATC_MESSAGE, capture_handler)

    # Spawn 2 aircraft
    traffic_manager.spawn_traffic(count=2)

    # Set both to taxiing on same taxiway
    aircraft_list = list(traffic_manager.traffic.values())
    aircraft1, aircraft2 = aircraft_list[0], aircraft_list[1]

    aircraft1.state = GroundTrafficState.TAXIING
    aircraft2.state = GroundTrafficState.TAXIING
    aircraft1.taxi_route = ["Alpha"]
    aircraft2.taxi_route = ["Alpha"]
    aircraft1.current_route_index = 0
    aircraft2.current_route_index = 0

    # Detect conflicts
    traffic_manager._detect_conflicts()

    # One aircraft should be instructed to hold
    assert (
        aircraft1.state == GroundTrafficState.HOLDING
        or aircraft2.state == GroundTrafficState.HOLDING
    )

    # Should have published hold-short message
    message_queue.process()

    hold_messages = [
        msg for msg in captured_messages if "hold short" in msg.data.get("message", "").lower()
    ]
    assert len(hold_messages) > 0


def test_no_conflict_different_taxiways(traffic_manager):
    """Test no conflict when aircraft on different taxiways."""
    traffic_manager.spawn_traffic(count=2)

    aircraft_list = list(traffic_manager.traffic.values())
    aircraft1, aircraft2 = aircraft_list[0], aircraft_list[1]

    # Set to taxiing on different taxiways
    aircraft1.state = GroundTrafficState.TAXIING
    aircraft2.state = GroundTrafficState.TAXIING
    aircraft1.taxi_route = ["Alpha"]
    aircraft2.taxi_route = ["Bravo"]
    aircraft1.current_route_index = 0
    aircraft2.current_route_index = 0

    # Detect conflicts
    traffic_manager._detect_conflicts()

    # Neither should be holding
    assert aircraft1.state == GroundTrafficState.TAXIING
    assert aircraft2.state == GroundTrafficState.TAXIING


def test_remove_aircraft(traffic_manager):
    """Test removing aircraft from traffic."""
    traffic_manager.spawn_traffic(count=2)

    initial_count = traffic_manager.get_traffic_count()
    assert initial_count == 2

    # Remove one
    aircraft_id = list(traffic_manager.traffic.keys())[0]
    traffic_manager._remove_aircraft(aircraft_id)

    # Should have one less
    assert traffic_manager.get_traffic_count() == initial_count - 1
    assert traffic_manager.get_aircraft(aircraft_id) is None


def test_clear_all_traffic(traffic_manager):
    """Test clearing all traffic."""
    traffic_manager.spawn_traffic(count=5)

    assert traffic_manager.get_traffic_count() == 5

    # Clear all
    traffic_manager.clear_all_traffic()

    assert traffic_manager.get_traffic_count() == 0


def test_update_processes_all_aircraft(traffic_manager):
    """Test update() processes all aircraft."""
    traffic_manager.spawn_traffic(count=3)

    # Set spawn times in past to trigger state changes (past both thresholds)
    for aircraft in traffic_manager.traffic.values():
        aircraft.spawn_time = time.time() - 20.0

    # Update twice to allow progression through states
    traffic_manager.update(1.0)
    traffic_manager.update(1.0)

    # Count how many progressed (at least some should have)
    progressed = sum(
        1
        for aircraft in traffic_manager.traffic.values()
        if aircraft.state != GroundTrafficState.PARKED
    )
    assert progressed > 0  # At least one should have progressed


def test_aircraft_reaches_runway(traffic_manager):
    """Test aircraft reaches runway and stops."""
    traffic_manager.spawn_traffic(count=1)

    aircraft_id = list(traffic_manager.traffic.keys())[0]
    aircraft = traffic_manager.get_aircraft(aircraft_id)

    # Set to taxiing and advance through route
    aircraft.state = GroundTrafficState.TAXIING
    aircraft.spawn_time = time.time() - 100.0  # Long time ago
    aircraft.current_route_index = len(aircraft.taxi_route)  # Past end of route

    # Move
    traffic_manager._move_aircraft(aircraft, 1.0)

    # Should be at runway
    assert aircraft.state == GroundTrafficState.AT_RUNWAY


def test_unique_aircraft_ids(traffic_manager):
    """Test each spawned aircraft has unique ID."""
    traffic_manager.spawn_traffic(count=10)

    ids = [aircraft.aircraft_id for aircraft in traffic_manager.traffic.values()]

    # All should be unique
    assert len(ids) == len(set(ids))


def test_custom_parking_positions(traffic_manager):
    """Test spawning with custom parking positions."""
    custom_parking = ["gate_a1", "gate_a2", "gate_a3"]

    traffic_manager.spawn_traffic(count=3, parking_positions=custom_parking)

    # All aircraft should be at one of the custom parking spots
    for aircraft in traffic_manager.traffic.values():
        assert aircraft.parking_id in custom_parking


def test_traffic_publishes_updates(traffic_manager, message_queue):
    """Test traffic publishes regular updates."""
    captured_messages = []

    def capture_handler(msg):
        captured_messages.append(msg)

    message_queue.subscribe(MessageTopic.TRAFFIC_UPDATE, capture_handler)

    # Spawn and update
    traffic_manager.spawn_traffic(count=1)
    message_queue.process()

    # Should have published
    assert len(captured_messages) > 0

    traffic_msg = captured_messages[-1]
    assert traffic_msg.topic == MessageTopic.TRAFFIC_UPDATE
    assert "aircraft_id" in traffic_msg.data


def test_conflict_resolution_priority(traffic_manager):
    """Test conflict resolution uses aircraft ID priority."""
    traffic_manager.spawn_traffic(count=2)

    aircraft_list = list(traffic_manager.traffic.values())
    aircraft1, aircraft2 = aircraft_list[0], aircraft_list[1]

    # Ensure aircraft1 has lower ID (alphabetically)
    if aircraft1.aircraft_id > aircraft2.aircraft_id:
        aircraft1, aircraft2 = aircraft2, aircraft1

    # Set to taxiing on same taxiway
    aircraft1.state = GroundTrafficState.TAXIING
    aircraft2.state = GroundTrafficState.TAXIING
    aircraft1.taxi_route = ["Alpha"]
    aircraft2.taxi_route = ["Alpha"]
    aircraft1.current_route_index = 0
    aircraft2.current_route_index = 0

    # Resolve conflict
    traffic_manager._resolve_conflict(aircraft1, aircraft2)

    # Aircraft with lower ID should hold
    assert aircraft1.state == GroundTrafficState.HOLDING
    assert aircraft2.state == GroundTrafficState.TAXIING

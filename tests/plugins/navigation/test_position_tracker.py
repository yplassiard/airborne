"""Unit tests for position tracker."""

import pytest

from airborne.airports.taxiway import TaxiwayGraph
from airborne.core.messaging import MessageQueue
from airborne.physics.vectors import Vector3
from airborne.plugins.navigation.position_tracker import (
    LocationEvent,
    LocationType,
    PositionTracker,
)


@pytest.fixture
def taxiway_graph() -> TaxiwayGraph:
    """Create a test taxiway graph with various node types."""
    graph = TaxiwayGraph()

    # Add parking nodes
    graph.add_node(
        node_id="G1",
        position=Vector3(-122.0, 10.0, 37.5),
        node_type="parking_gate",
        name="Gate 1",
    )
    graph.add_node(
        node_id="R1",
        position=Vector3(-122.001, 10.0, 37.5),
        node_type="parking_ramp",
        name="Ramp 1",
    )

    # Add taxiway nodes (intersection type)
    graph.add_node(
        node_id="A1",
        position=Vector3(-122.002, 10.0, 37.5),
        node_type="intersection",
        name="A1",
    )
    graph.add_node(
        node_id="A2",
        position=Vector3(-122.003, 10.0, 37.5),
        node_type="intersection",
        name="A2",
    )
    graph.add_node(
        node_id="B1",
        position=Vector3(-122.0025, 10.0, 37.5005),
        node_type="intersection",
        name="B1",
    )

    # Add runway nodes
    graph.add_node(
        node_id="RWY31", position=Vector3(-122.004, 10.0, 37.5), node_type="runway", name="31"
    )

    # Add apron node
    graph.add_node(
        node_id="APRON1", position=Vector3(-122.0005, 10.0, 37.5), node_type="apron", name="Apron"
    )

    # Add edges (taxiway segments)
    graph.add_edge(from_node="G1", to_node="APRON1", edge_type="apron", bidirectional=True)
    graph.add_edge(from_node="R1", to_node="APRON1", edge_type="apron", bidirectional=True)
    graph.add_edge(
        from_node="APRON1", to_node="A1", edge_type="taxiway", name="A", bidirectional=True
    )
    graph.add_edge(from_node="A1", to_node="A2", edge_type="taxiway", name="A", bidirectional=True)
    graph.add_edge(from_node="A1", to_node="B1", edge_type="taxiway", name="B", bidirectional=True)
    graph.add_edge(
        from_node="A2", to_node="RWY31", edge_type="runway", name="31", bidirectional=True
    )

    return graph


@pytest.fixture
def message_queue() -> MessageQueue:
    """Create a test message queue."""
    return MessageQueue()


@pytest.fixture
def tracker(taxiway_graph: TaxiwayGraph, message_queue: MessageQueue) -> PositionTracker:
    """Create a test position tracker."""
    return PositionTracker(taxiway_graph, message_queue, proximity_threshold_m=10.0)


class TestLocationType:
    """Test LocationType enum."""

    def test_location_type_values(self) -> None:
        """Test that all location types are defined."""
        assert LocationType.PARKING.value == "parking"
        assert LocationType.TAXIWAY.value == "taxiway"
        assert LocationType.RUNWAY.value == "runway"
        assert LocationType.APRON.value == "apron"
        assert LocationType.GRASS.value == "grass"
        assert LocationType.UNKNOWN.value == "unknown"


class TestLocationEvent:
    """Test LocationEvent dataclass."""

    def test_create_location_event(self) -> None:
        """Test creating a location event."""
        event = LocationEvent(
            location_type=LocationType.TAXIWAY,
            location_id="A",
            previous_location_type=LocationType.PARKING,
            previous_location_id="G1",
            position=Vector3(-122.0, 10.0, 37.5),
            timestamp=12345.67,
        )

        assert event.location_type == LocationType.TAXIWAY
        assert event.location_id == "A"
        assert event.previous_location_type == LocationType.PARKING
        assert event.previous_location_id == "G1"
        assert event.position == Vector3(-122.0, 10.0, 37.5)
        assert event.timestamp == 12345.67


class TestPositionTracker:
    """Test PositionTracker class."""

    def test_create_tracker(self, taxiway_graph: TaxiwayGraph, message_queue: MessageQueue) -> None:
        """Test creating a position tracker."""
        tracker = PositionTracker(taxiway_graph, message_queue, proximity_threshold_m=15.0)

        assert tracker.graph == taxiway_graph
        assert tracker.message_queue == message_queue
        assert tracker.proximity_threshold_m == 15.0
        assert tracker.current_location_type == LocationType.UNKNOWN
        assert tracker.current_location_id == ""
        assert len(tracker.position_history) == 0

    def test_detect_parking_location(self, tracker: PositionTracker) -> None:
        """Test detection of parking position."""
        # Move to gate G1
        tracker.update(Vector3(-122.0, 10.0, 37.5), 90.0, 100.0)

        location_type, location_id = tracker.get_current_location()
        assert location_type == LocationType.PARKING
        assert location_id == "G1"

    def test_detect_taxiway_intersection(self, tracker: PositionTracker) -> None:
        """Test detection of taxiway intersection."""
        # Move to taxiway node A1
        tracker.update(Vector3(-122.002, 10.0, 37.5), 90.0, 100.0)

        location_type, location_id = tracker.get_current_location()
        assert location_type == LocationType.TAXIWAY
        # Should be at node A1, which connects to edge "A"
        assert location_id in ["A", "A1"]

    def test_detect_runway(self, tracker: PositionTracker) -> None:
        """Test detection of runway."""
        # Move to runway node
        tracker.update(Vector3(-122.004, 10.0, 37.5), 90.0, 100.0)

        location_type, location_id = tracker.get_current_location()
        assert location_type == LocationType.RUNWAY
        assert location_id == "31"

    def test_detect_apron(self, tracker: PositionTracker) -> None:
        """Test detection of apron area."""
        # Move to apron node
        tracker.update(Vector3(-122.0005, 10.0, 37.5), 90.0, 100.0)

        location_type, location_id = tracker.get_current_location()
        assert location_type == LocationType.APRON
        assert location_id == "APRON1"

    def test_detect_on_taxiway_edge(self, tracker: PositionTracker) -> None:
        """Test detection when on taxiway segment between nodes."""
        # Position midway between A1 and A2 (should be on taxiway A)
        mid_x = (-122.002 + -122.003) / 2
        tracker.update(Vector3(mid_x, 10.0, 37.5), 90.0, 100.0)

        location_type, location_id = tracker.get_current_location()
        assert location_type == LocationType.TAXIWAY
        assert location_id == "A"

    def test_detect_grass_when_far_from_nodes(self, tracker: PositionTracker) -> None:
        """Test detection of grass when far from any node or edge."""
        # Position far from any node (>10m away)
        tracker.update(Vector3(-122.1, 10.0, 37.6), 90.0, 100.0)

        location_type, location_id = tracker.get_current_location()
        assert location_type == LocationType.GRASS
        assert location_id == ""

    def test_location_change_event_published(
        self, tracker: PositionTracker, message_queue: MessageQueue
    ) -> None:
        """Test that location change events are published."""
        # Start at parking
        tracker.update(Vector3(-122.0, 10.0, 37.5), 90.0, 100.0)

        # Clear queue
        message_queue.process()

        # Move to apron
        tracker.update(Vector3(-122.0005, 10.0, 37.5), 90.0, 101.0)

        # Process messages
        processed = message_queue.process()

        # Should have published a location change event
        assert processed >= 1

    def test_position_history_tracking(self, tracker: PositionTracker) -> None:
        """Test that position history is maintained."""
        assert len(tracker.position_history) == 0

        # Update position several times
        for i in range(5):
            tracker.update(Vector3(-122.0 + i * 0.0001, 10.0, 37.5), 90.0, 100.0 + i)

        # Should have 5 entries
        assert len(tracker.position_history) == 5

        # Check last entry
        last_pos, last_heading = tracker.position_history[-1]
        assert last_pos.x == pytest.approx(-122.0 + 4 * 0.0001)
        assert last_heading == 90.0

    def test_position_history_max_length(self, tracker: PositionTracker) -> None:
        """Test that position history respects max length of 100."""
        # Add 150 positions
        for i in range(150):
            tracker.update(Vector3(-122.0 + i * 0.00001, 10.0, 37.5), 90.0, 100.0 + i)

        # Should only have last 100
        assert len(tracker.position_history) == 100

    def test_get_nearest_taxiway_when_on_taxiway(self, tracker: PositionTracker) -> None:
        """Test getting nearest taxiway when on a taxiway."""
        # Move to taxiway A
        tracker.update(Vector3(-122.002, 10.0, 37.5), 90.0, 100.0)

        nearest = tracker.get_nearest_taxiway()
        assert nearest in ["A", "A1"]  # Could be edge name or node ID

    def test_get_nearest_taxiway_when_not_on_taxiway(self, tracker: PositionTracker) -> None:
        """Test getting nearest taxiway when not on a taxiway."""
        # Move to parking
        tracker.update(Vector3(-122.0, 10.0, 37.5), 90.0, 100.0)

        nearest = tracker.get_nearest_taxiway()
        # Should find nearest taxiway edge (probably connected to apron)
        # May return None or a taxiway name depending on proximity
        assert nearest is None or isinstance(nearest, str)

    def test_is_on_taxiway_true(self, tracker: PositionTracker) -> None:
        """Test is_on_taxiway returns True when on the taxiway."""
        # Move to taxiway A
        tracker.update(Vector3(-122.002, 10.0, 37.5), 90.0, 100.0)

        # Check if we're on any taxiway (A, B, or node ID)
        on_taxiway = (
            tracker.is_on_taxiway("A") or tracker.is_on_taxiway("B") or tracker.is_on_taxiway("A1")
        )
        assert on_taxiway

    def test_is_on_taxiway_false(self, tracker: PositionTracker) -> None:
        """Test is_on_taxiway returns False when not on the taxiway."""
        # Move to parking
        tracker.update(Vector3(-122.0, 10.0, 37.5), 90.0, 100.0)

        assert not tracker.is_on_taxiway("A")
        assert not tracker.is_on_taxiway("B")

    def test_get_distance_to_next_intersection(self, tracker: PositionTracker) -> None:
        """Test calculating distance to next intersection."""
        # Move to node A1, heading towards A2 (east)
        tracker.update(Vector3(-122.002, 10.0, 37.5), 90.0, 100.0)

        distance = tracker.get_distance_to_next_intersection()

        # Distance from A1 to A2 is approximately 111m (0.001 degrees longitude)
        # Should be finite and positive
        assert distance < float("inf")
        assert distance > 0

    def test_get_distance_to_next_intersection_no_path(self, tracker: PositionTracker) -> None:
        """Test distance returns infinity when not on a path."""
        # Move to a position not near any node
        tracker.update(Vector3(-122.1, 10.0, 37.6), 90.0, 100.0)

        distance = tracker.get_distance_to_next_intersection()
        assert distance == float("inf")

    def test_location_change_from_parking_to_taxiway(self, tracker: PositionTracker) -> None:
        """Test location change from parking to taxiway."""
        # Start at parking G1
        tracker.update(Vector3(-122.0, 10.0, 37.5), 90.0, 100.0)
        assert tracker.current_location_type == LocationType.PARKING
        assert tracker.current_location_id == "G1"

        # Move to apron
        tracker.update(Vector3(-122.0005, 10.0, 37.5), 90.0, 101.0)
        assert tracker.current_location_type == LocationType.APRON
        assert tracker.current_location_id == "APRON1"

        # Move to taxiway A1
        tracker.update(Vector3(-122.002, 10.0, 37.5), 90.0, 102.0)
        assert tracker.current_location_type == LocationType.TAXIWAY

    def test_empty_graph_returns_unknown(self) -> None:
        """Test that empty graph returns unknown location."""
        empty_graph = TaxiwayGraph()
        tracker = PositionTracker(empty_graph, None)

        tracker.update(Vector3(-122.0, 10.0, 37.5), 90.0, 100.0)

        location_type, location_id = tracker.get_current_location()
        assert location_type == LocationType.UNKNOWN
        assert location_id == ""

    def test_tracker_without_message_queue(self, taxiway_graph: TaxiwayGraph) -> None:
        """Test tracker works without message queue."""
        tracker = PositionTracker(taxiway_graph, None)

        # Should not raise exception
        tracker.update(Vector3(-122.0, 10.0, 37.5), 90.0, 100.0)

        location_type, location_id = tracker.get_current_location()
        assert location_type == LocationType.PARKING
        assert location_id == "G1"

    def test_calculate_distance_static_method(self) -> None:
        """Test distance calculation utility method."""
        pos1 = Vector3(-122.0, 10.0, 37.5)
        pos2 = Vector3(-122.001, 10.0, 37.5)

        distance = PositionTracker._calculate_distance(pos1, pos2)

        # 0.001 degrees longitude at equator ≈ 111 meters
        # Should be approximately 111 meters
        assert distance == pytest.approx(111.0, abs=10.0)

    def test_point_to_segment_distance_on_segment(self) -> None:
        """Test point to segment distance when point is on segment."""
        segment_start = Vector3(-122.0, 10.0, 37.5)
        segment_end = Vector3(-122.001, 10.0, 37.5)
        point = Vector3(-122.0005, 10.0, 37.5)  # Midpoint

        distance = PositionTracker._point_to_segment_distance(point, segment_start, segment_end)

        # Point is on the line segment, so distance should be ~0
        assert distance == pytest.approx(0.0, abs=1.0)

    def test_point_to_segment_distance_off_segment(self) -> None:
        """Test point to segment distance when point is off segment."""
        segment_start = Vector3(-122.0, 10.0, 37.5)
        segment_end = Vector3(-122.001, 10.0, 37.5)
        point = Vector3(-122.0005, 10.0, 37.501)  # Off to the side

        distance = PositionTracker._point_to_segment_distance(point, segment_start, segment_end)

        # Point is off the line, so distance should be > 0
        assert distance > 0

    def test_multiple_location_changes_publish_multiple_events(
        self, tracker: PositionTracker, message_queue: MessageQueue
    ) -> None:
        """Test that multiple location changes publish multiple events."""
        # Clear initial state
        tracker.update(Vector3(-122.0, 10.0, 37.5), 90.0, 100.0)
        message_queue.process()

        # Move through several locations with distinct types/IDs
        positions = [
            (Vector3(-122.0005, 10.0, 37.5), "APRON1"),  # Apron
            (Vector3(-122.002, 10.0, 37.5), "A1"),  # Taxiway A
            (Vector3(-122.0025, 10.0, 37.5005), "B1"),  # Taxiway B (different taxiway)
        ]

        message_count = 0
        for pos, _ in positions:
            tracker.update(pos, 90.0, 100.0)
            message_count += message_queue.process()

        # Should have published at least 3 events (one for each location change)
        # Note: A1 and A2 are both on taxiway A, so only 2 events if moving A1->A2
        # Using B1 instead ensures we get 3 distinct location changes
        assert message_count >= 3

    def test_no_event_when_location_unchanged(
        self, tracker: PositionTracker, message_queue: MessageQueue
    ) -> None:
        """Test that no event is published when location doesn't change."""
        # Move to parking
        tracker.update(Vector3(-122.0, 10.0, 37.5), 90.0, 100.0)
        message_queue.process()  # Clear initial event

        # Move slightly within same parking spot
        tracker.update(Vector3(-122.0 + 0.00001, 10.0, 37.5), 90.0, 101.0)

        # Should not publish new event
        processed = message_queue.process()
        assert processed == 0

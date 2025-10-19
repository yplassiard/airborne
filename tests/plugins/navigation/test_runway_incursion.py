"""Unit tests for runway incursion detection."""

import time

import pytest

from airborne.airports.database import Runway, SurfaceType
from airborne.core.messaging import Message, MessageQueue
from airborne.physics.vectors import Vector3
from airborne.plugins.navigation.runway_incursion import (
    IncursionLevel,
    RunwayIncursionDetector,
    RunwayProximity,
)


@pytest.fixture
def message_queue() -> MessageQueue:
    """Create a test message queue."""
    return MessageQueue()


@pytest.fixture
def sample_runway() -> Runway:
    """Create a sample runway for testing."""
    return Runway(
        airport_icao="KSFO",
        runway_id="28L/10R",
        length_ft=11870,
        width_ft=200,
        surface=SurfaceType.ASPH,
        lighted=True,
        closed=False,
        le_ident="10R",
        le_latitude=37.61,
        le_longitude=-122.38,
        le_elevation_ft=10,
        le_heading_deg=105,
        he_ident="28L",
        he_latitude=37.62,
        he_longitude=-122.36,
        he_elevation_ft=10,
        he_heading_deg=285,
    )


@pytest.fixture
def detector(message_queue: MessageQueue, sample_runway: Runway) -> RunwayIncursionDetector:
    """Create a test runway incursion detector."""
    return RunwayIncursionDetector(message_queue, [sample_runway], warning_cooldown=2.0)


class TestIncursionLevel:
    """Test IncursionLevel enum."""

    def test_incursion_levels(self) -> None:
        """Test all incursion levels."""
        assert IncursionLevel.NONE.value == "none"
        assert IncursionLevel.CAUTION.value == "caution"
        assert IncursionLevel.WARNING.value == "warning"
        assert IncursionLevel.ALERT.value == "alert"


class TestRunwayProximity:
    """Test RunwayProximity dataclass."""

    def test_create_proximity(self, sample_runway: Runway) -> None:
        """Test creating runway proximity data."""
        prox = RunwayProximity(
            runway=sample_runway,
            distance_m=100.0,
            last_warning_level=IncursionLevel.NONE,
            last_warning_time=0.0,
        )

        assert prox.runway == sample_runway
        assert prox.distance_m == 100.0
        assert prox.last_warning_level == IncursionLevel.NONE
        assert prox.last_warning_time == 0.0


class TestRunwayIncursionDetector:
    """Test RunwayIncursionDetector class."""

    def test_create_detector(self, message_queue: MessageQueue, sample_runway: Runway) -> None:
        """Test creating a runway incursion detector."""
        detector = RunwayIncursionDetector(message_queue, [sample_runway], warning_cooldown=3.0)

        assert detector.message_queue == message_queue
        assert len(detector.runways) == 1
        assert detector.runways[0] == sample_runway
        assert detector.warning_cooldown == 3.0
        assert len(detector.cleared_runways) == 0
        assert len(detector.proximity_data) == 0

    def test_create_detector_without_queue(self, sample_runway: Runway) -> None:
        """Test creating detector without message queue."""
        detector = RunwayIncursionDetector(None, [sample_runway])

        assert detector.message_queue is None
        assert len(detector.runways) == 1

    def test_subscribe_to_events(self, detector: RunwayIncursionDetector) -> None:
        """Test subscribing to ATC clearance events."""
        # Should not raise exception
        detector.subscribe_to_events()
        detector.unsubscribe_from_events()

    def test_grant_clearance(self, detector: RunwayIncursionDetector) -> None:
        """Test granting runway clearance."""
        detector.grant_clearance("28L")

        assert detector.is_cleared("28L")
        assert "28L" in detector.cleared_runways

    def test_revoke_specific_clearance(self, detector: RunwayIncursionDetector) -> None:
        """Test revoking specific runway clearance."""
        detector.grant_clearance("28L")
        detector.grant_clearance("10R")

        assert detector.is_cleared("28L")
        assert detector.is_cleared("10R")

        detector.revoke_clearance("28L")

        assert not detector.is_cleared("28L")
        assert detector.is_cleared("10R")

    def test_revoke_all_clearances(self, detector: RunwayIncursionDetector) -> None:
        """Test revoking all runway clearances."""
        detector.grant_clearance("28L")
        detector.grant_clearance("10R")

        detector.revoke_clearance(None)

        assert not detector.is_cleared("28L")
        assert not detector.is_cleared("10R")
        assert len(detector.cleared_runways) == 0

    def test_get_nearest_runway_close(self, detector: RunwayIncursionDetector) -> None:
        """Test getting nearest runway when close."""
        # Position near runway
        position = Vector3(37.615, 10.0, -122.37)

        runway, distance = detector.get_nearest_runway(position)

        assert runway is not None
        assert runway.runway_id == "28L/10R"
        assert distance < 1000.0  # Within 1km

    def test_get_nearest_runway_far(self, detector: RunwayIncursionDetector) -> None:
        """Test getting nearest runway when far."""
        # Position far from runway
        position = Vector3(40.0, 10.0, -120.0)

        runway, distance = detector.get_nearest_runway(position)

        assert runway is not None
        assert distance > 100000.0  # More than 100km

    def test_update_without_clearance_far(
        self, detector: RunwayIncursionDetector, message_queue: MessageQueue
    ) -> None:
        """Test update when far from runway without clearance."""
        # Position 1km from runway
        position = Vector3(37.63, 10.0, -122.37)

        detector.update(position, 270.0, time.time())

        # No warning should be issued (too far)
        assert message_queue.process() == 0

    def test_update_without_clearance_caution(
        self, detector: RunwayIncursionDetector, message_queue: MessageQueue
    ) -> None:
        """Test caution warning at 50m without clearance."""
        # Position ~40m from runway (within 50m threshold)
        position = Vector3(37.6145, 10.0, -122.370)

        detector.update(position, 270.0, time.time())

        # Caution warning should be issued
        processed = message_queue.process()
        assert processed == 1

    def test_update_without_clearance_warning(
        self, detector: RunwayIncursionDetector, message_queue: MessageQueue
    ) -> None:
        """Test warning at 20m without clearance."""
        # Position ~15m from runway (within 20m threshold)
        position = Vector3(37.6148, 10.0, -122.370)

        detector.update(position, 270.0, time.time())

        # Warning should be issued
        processed = message_queue.process()
        assert processed == 1

    def test_update_with_clearance_no_warning(
        self, detector: RunwayIncursionDetector, message_queue: MessageQueue
    ) -> None:
        """Test no warning when cleared for runway."""
        detector.grant_clearance("28L")

        # Position close to runway
        position = Vector3(37.6148, 10.0, -122.370)

        detector.update(position, 270.0, time.time())

        # No warning should be issued (cleared)
        assert message_queue.process() == 0

    def test_warning_cooldown(
        self, detector: RunwayIncursionDetector, message_queue: MessageQueue
    ) -> None:
        """Test that warnings respect cooldown period."""
        position = Vector3(37.6145, 10.0, -122.370)

        # First warning
        detector.update(position, 270.0, time.time())
        assert message_queue.process() == 1

        # Second warning within cooldown - should be suppressed
        detector.update(position, 270.0, time.time())
        assert message_queue.process() == 0

        # Wait for cooldown
        time.sleep(2.1)

        # Third warning after cooldown - should be issued
        detector.update(position, 270.0, time.time())
        assert message_queue.process() == 1

    def test_escalating_warnings(
        self, detector: RunwayIncursionDetector, message_queue: MessageQueue
    ) -> None:
        """Test escalating warning levels as aircraft approaches."""
        # Start at 40m (caution)
        position1 = Vector3(37.6145, 10.0, -122.370)
        detector.update(position1, 270.0, time.time())
        assert message_queue.process() == 1  # Caution

        # Move to 15m (warning)
        time.sleep(2.1)  # Wait for cooldown
        position2 = Vector3(37.6148, 10.0, -122.370)
        detector.update(position2, 270.0, time.time())
        assert message_queue.process() == 1  # Warning

    def test_clearance_granted_message(
        self, detector: RunwayIncursionDetector, message_queue: MessageQueue
    ) -> None:
        """Test handling clearance granted message."""
        detector.subscribe_to_events()

        # Simulate ATC clearance message
        msg = Message(
            sender="atc",
            recipients=["runway_incursion"],
            topic="atc.clearance.takeoff",
            data={"runway_id": "28L"},
        )

        detector._on_clearance_granted(msg)

        assert detector.is_cleared("28L")

        detector.unsubscribe_from_events()

    def test_clearance_revoked_message(
        self, detector: RunwayIncursionDetector, message_queue: MessageQueue
    ) -> None:
        """Test handling clearance revoked message."""
        detector.subscribe_to_events()
        detector.grant_clearance("28L")

        # Simulate ATC revocation message
        msg = Message(
            sender="atc",
            recipients=["runway_incursion"],
            topic="atc.clearance.revoked",
            data={"runway_id": "28L"},
        )

        detector._on_clearance_revoked(msg)

        assert not detector.is_cleared("28L")

        detector.unsubscribe_from_events()

    def test_point_to_segment_distance_perpendicular(
        self, detector: RunwayIncursionDetector
    ) -> None:
        """Test distance calculation perpendicular to segment."""
        # Point perpendicular to midpoint of segment
        distance = detector._point_to_segment_distance(
            1.0,
            1.0,  # Point
            0.0,
            0.0,  # Segment start
            2.0,
            0.0,  # Segment end
        )

        # Should be ~111km (1 degree)
        assert 110000 < distance < 112000

    def test_point_to_segment_distance_at_endpoint(self, detector: RunwayIncursionDetector) -> None:
        """Test distance calculation at segment endpoint."""
        distance = detector._point_to_segment_distance(
            0.0,
            0.0,  # Point at start
            0.0,
            0.0,  # Segment start
            1.0,
            0.0,  # Segment end
        )

        # Should be 0
        assert distance == 0.0

    def test_warning_messages(self, detector: RunwayIncursionDetector) -> None:
        """Test warning message generation."""
        msg_caution = detector._generate_warning_message("28L/10R", IncursionLevel.CAUTION, 45.0)
        assert "Caution" in msg_caution
        assert "28L" in msg_caution

        msg_warning = detector._generate_warning_message("28L/10R", IncursionLevel.WARNING, 15.0)
        assert "Warning" in msg_warning
        assert "hold short" in msg_warning.lower()

        msg_alert = detector._generate_warning_message("28L/10R", IncursionLevel.ALERT, 0.0)
        assert "Alert" in msg_alert
        assert "incursion" in msg_alert.lower()

    def test_multiple_runways(self, message_queue: MessageQueue) -> None:
        """Test detector with multiple runways."""
        runway1 = Runway(
            airport_icao="KSFO",
            runway_id="09L/27R",
            length_ft=11000,
            width_ft=200,
            surface=SurfaceType.ASPH,
            lighted=True,
            closed=False,
            le_ident="09L",
            le_latitude=37.61,
            le_longitude=-122.38,
            le_elevation_ft=10,
            le_heading_deg=90,
            he_ident="27R",
            he_latitude=37.62,
            he_longitude=-122.36,
            he_elevation_ft=10,
            he_heading_deg=270,
        )

        runway2 = Runway(
            airport_icao="KSFO",
            runway_id="09R/27L",
            length_ft=11000,
            width_ft=200,
            surface=SurfaceType.ASPH,
            lighted=True,
            closed=False,
            le_ident="09R",
            le_latitude=37.60,
            le_longitude=-122.38,
            le_elevation_ft=10,
            le_heading_deg=90,
            he_ident="27L",
            he_latitude=37.61,
            he_longitude=-122.36,
            he_elevation_ft=10,
            he_heading_deg=270,
        )

        detector = RunwayIncursionDetector(message_queue, [runway1, runway2])

        assert len(detector.runways) == 2

    def test_detector_without_queue_does_not_crash(self, sample_runway: Runway) -> None:
        """Test that detector without queue handles calls gracefully."""
        detector = RunwayIncursionDetector(None, [sample_runway])

        # Should not crash
        detector.subscribe_to_events()
        detector.update(Vector3(37.615, 10.0, -122.37), 270.0, time.time())
        detector.grant_clearance("28L")
        detector.revoke_clearance("28L")
        detector.unsubscribe_from_events()

    def test_cleared_for_either_runway_end(
        self, detector: RunwayIncursionDetector, message_queue: MessageQueue
    ) -> None:
        """Test clearance for either end of runway prevents warnings."""
        # Grant clearance for 10R (opposite end of runway)
        detector.grant_clearance("10R")

        # Position close to 28L end
        position = Vector3(37.6145, 10.0, -122.370)

        detector.update(position, 270.0, time.time())

        # No warning should be issued (cleared for runway, either end)
        assert message_queue.process() == 0

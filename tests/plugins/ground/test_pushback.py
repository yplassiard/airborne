"""Unit tests for pushback service."""

import time

import pytest

from airborne.core.messaging import MessageQueue
from airborne.physics.vectors import Vector3
from airborne.plugins.ground.ground_services import ServiceRequest, ServiceStatus, ServiceType
from airborne.plugins.ground.services.pushback import (
    PushbackDirection,
    PushbackPhase,
    PushbackService,
)


@pytest.fixture
def message_queue() -> MessageQueue:
    """Create a test message queue."""
    return MessageQueue()


@pytest.fixture
def pushback_service(message_queue: MessageQueue) -> PushbackService:
    """Create a pushback service instance."""
    return PushbackService(message_queue)


class TestPushbackDirection:
    """Test PushbackDirection enum."""

    def test_direction_values(self) -> None:
        """Test all pushback direction values."""
        assert PushbackDirection.NORTH.value == "north"
        assert PushbackDirection.SOUTH.value == "south"
        assert PushbackDirection.EAST.value == "east"
        assert PushbackDirection.WEST.value == "west"
        assert PushbackDirection.TO_TAXIWAY.value == "to_taxiway"

    def test_to_heading_north(self) -> None:
        """Test NORTH direction to heading conversion."""
        assert PushbackDirection.NORTH.to_heading() == 360.0

    def test_to_heading_east(self) -> None:
        """Test EAST direction to heading conversion."""
        assert PushbackDirection.EAST.to_heading() == 90.0

    def test_to_heading_south(self) -> None:
        """Test SOUTH direction to heading conversion."""
        assert PushbackDirection.SOUTH.to_heading() == 180.0

    def test_to_heading_west(self) -> None:
        """Test WEST direction to heading conversion."""
        assert PushbackDirection.WEST.to_heading() == 270.0


class TestPushbackPhase:
    """Test PushbackPhase enum."""

    def test_pushback_phases(self) -> None:
        """Test all pushback phases."""
        assert PushbackPhase.WAITING_BRAKE_RELEASE.value == "waiting_brake_release"
        assert PushbackPhase.PUSHING_BACK.value == "pushing_back"
        assert PushbackPhase.COMPLETE.value == "complete"


class TestPushbackService:
    """Test PushbackService class."""

    def test_create_service(self, pushback_service: PushbackService) -> None:
        """Test creating a pushback service."""
        assert pushback_service.service_type == ServiceType.PUSHBACK
        assert pushback_service.status == ServiceStatus.IDLE
        assert pushback_service.pushback_distance == 50.0
        assert pushback_service.pushback_duration == 30.0

    def test_start_pushback_north(
        self, pushback_service: PushbackService, message_queue: MessageQueue
    ) -> None:
        """Test starting pushback with NORTH direction."""
        audio_messages: list = []

        def capture_audio(msg):  # type: ignore
            audio_messages.append(msg)

        message_queue.subscribe("ground.audio.speak", capture_audio)

        request = ServiceRequest(
            service_type=ServiceType.PUSHBACK,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={
                "direction": "NORTH",
                "current_position": {"x": -122.0, "y": 100.0, "z": 37.0},
            },
        )

        result = pushback_service.start(request)

        assert result is True
        assert pushback_service.status == ServiceStatus.IN_PROGRESS
        assert pushback_service.pushback_phase == PushbackPhase.WAITING_BRAKE_RELEASE
        assert pushback_service.pushback_direction == PushbackDirection.NORTH
        assert pushback_service.target_heading == 360.0

        # Check audio message
        message_queue.process()
        assert len(audio_messages) == 1
        assert "brake" in audio_messages[0].data["text"].lower()

    def test_start_pushback_with_heading(self, pushback_service: PushbackService) -> None:
        """Test starting pushback with specific heading."""
        request = ServiceRequest(
            service_type=ServiceType.PUSHBACK,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={
                "direction": "NORTH",
                "heading": 045.0,  # Override with specific heading
                "current_position": {"x": -122.0, "y": 100.0, "z": 37.0},
            },
        )

        pushback_service.start(request)

        assert pushback_service.target_heading == 45.0

    def test_start_pushback_invalid_direction(self, pushback_service: PushbackService) -> None:
        """Test pushback with invalid direction defaults to TO_TAXIWAY."""
        request = ServiceRequest(
            service_type=ServiceType.PUSHBACK,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={
                "direction": "INVALID",
                "current_position": {"x": -122.0, "y": 100.0, "z": 37.0},
            },
        )

        pushback_service.start(request)

        assert pushback_service.pushback_direction == PushbackDirection.TO_TAXIWAY

    def test_release_parking_brake(self, pushback_service: PushbackService) -> None:
        """Test releasing parking brake transitions to pushing back."""
        request = ServiceRequest(
            service_type=ServiceType.PUSHBACK,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={
                "direction": "NORTH",
                "current_position": {"x": -122.0, "y": 100.0, "z": 37.0},
            },
        )

        pushback_service.start(request)
        assert pushback_service.pushback_phase == PushbackPhase.WAITING_BRAKE_RELEASE

        pushback_service.release_parking_brake()

        assert pushback_service.pushback_phase == PushbackPhase.PUSHING_BACK

    def test_auto_proceed_after_timeout(self, pushback_service: PushbackService) -> None:
        """Test automatic proceed after brake release timeout."""
        request = ServiceRequest(
            service_type=ServiceType.PUSHBACK,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={
                "direction": "NORTH",
                "current_position": {"x": -122.0, "y": 100.0, "z": 37.0},
            },
        )

        pushback_service.start(request)

        # Fast-forward to timeout
        pushback_service.phase_start_time = time.time() - 61.0
        pushback_service.update(1.0)

        assert pushback_service.pushback_phase == PushbackPhase.PUSHING_BACK

    def test_pushback_completes_after_duration(self, pushback_service: PushbackService) -> None:
        """Test pushback completes after duration."""
        request = ServiceRequest(
            service_type=ServiceType.PUSHBACK,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={
                "direction": "NORTH",
                "current_position": {"x": -122.0, "y": 100.0, "z": 37.0},
            },
        )

        pushback_service.start(request)
        pushback_service.release_parking_brake()

        # Fast-forward past pushback duration
        pushback_service.phase_start_time = time.time() - 31.0
        pushback_service.update(1.0)

        assert pushback_service.pushback_phase == PushbackPhase.COMPLETE

    def test_service_completes_after_pushback_phase(
        self, pushback_service: PushbackService
    ) -> None:
        """Test service status changes to COMPLETE after pushback."""
        request = ServiceRequest(
            service_type=ServiceType.PUSHBACK,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={
                "direction": "NORTH",
                "current_position": {"x": -122.0, "y": 100.0, "z": 37.0},
            },
        )

        pushback_service.start(request)

        # Fast-forward to complete phase
        pushback_service.pushback_phase = PushbackPhase.COMPLETE
        pushback_service.update(0.1)

        assert pushback_service.status == ServiceStatus.COMPLETE

    def test_calculate_target_position_north(self, pushback_service: PushbackService) -> None:
        """Test target position calculation for NORTH pushback."""
        request = ServiceRequest(
            service_type=ServiceType.PUSHBACK,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={
                "direction": "NORTH",
                "current_position": {"x": -122.0, "y": 100.0, "z": 37.0},
            },
        )

        pushback_service.start(request)

        # Target should be ~50m south (pushing back from north heading)
        target = pushback_service.target_position
        assert target is not None
        assert target.z < 37.0  # Latitude should decrease (moving south)
        assert abs(target.x - (-122.0)) < 0.001  # Longitude should stay same

    def test_calculate_target_position_east(self, pushback_service: PushbackService) -> None:
        """Test target position calculation for EAST pushback."""
        request = ServiceRequest(
            service_type=ServiceType.PUSHBACK,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={
                "direction": "EAST",
                "current_position": {"x": -122.0, "y": 100.0, "z": 37.0},
            },
        )

        pushback_service.start(request)

        # Target should be ~50m west (pushing back from east heading)
        target = pushback_service.target_position
        assert target is not None
        assert target.x < -122.0  # Longitude should decrease (moving west)

    def test_position_updates_during_pushback(
        self, pushback_service: PushbackService, message_queue: MessageQueue
    ) -> None:
        """Test position updates are published during pushback."""
        position_messages: list = []

        def capture_position(msg):  # type: ignore
            position_messages.append(msg)

        message_queue.subscribe("aircraft.position.update", capture_position)

        request = ServiceRequest(
            service_type=ServiceType.PUSHBACK,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={
                "direction": "NORTH",
                "current_position": {"x": -122.0, "y": 100.0, "z": 37.0},
            },
        )

        pushback_service.start(request)
        pushback_service.pushback_phase = PushbackPhase.PUSHING_BACK
        pushback_service.phase_start_time = time.time()

        # Simulate some time passing
        time.sleep(0.1)
        pushback_service.update(0.1)

        # Process queue and check position update
        message_queue.process()
        assert len(position_messages) > 0

    def test_pushback_complete_event_published(
        self, pushback_service: PushbackService, message_queue: MessageQueue
    ) -> None:
        """Test pushback complete event is published."""
        complete_messages: list = []

        def capture_complete(msg):  # type: ignore
            complete_messages.append(msg)

        message_queue.subscribe("ground.pushback.complete", capture_complete)

        request = ServiceRequest(
            service_type=ServiceType.PUSHBACK,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={
                "direction": "NORTH",
                "current_position": {"x": -122.0, "y": 100.0, "z": 37.0},
            },
        )

        pushback_service.start(request)
        pushback_service.pushback_phase = PushbackPhase.PUSHING_BACK
        pushback_service.phase_start_time = time.time() - 31.0
        pushback_service.update(1.0)

        # Process queue and check complete event
        message_queue.process()
        assert len(complete_messages) == 1
        assert complete_messages[0].data["aircraft_id"] == "N123AB"

    def test_audio_messages_at_each_phase(
        self, pushback_service: PushbackService, message_queue: MessageQueue
    ) -> None:
        """Test audio messages are published at each phase."""
        audio_messages: list = []

        def capture_audio(msg):  # type: ignore
            audio_messages.append(msg)

        message_queue.subscribe("ground.audio.speak", capture_audio)

        request = ServiceRequest(
            service_type=ServiceType.PUSHBACK,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={
                "direction": "NORTH",
                "current_position": {"x": -122.0, "y": 100.0, "z": 37.0},
            },
        )

        pushback_service.start(request)
        message_queue.process()

        # Should have initial brake release message
        assert len(audio_messages) == 1
        audio_messages.clear()

        # Transition to pushing back
        pushback_service._transition_to_pushing_back()
        message_queue.process()
        assert len(audio_messages) == 1
        assert "started" in audio_messages[0].data["text"].lower()

        # Transition to complete
        pushback_service._transition_to_complete()
        message_queue.process()
        assert len(audio_messages) == 2
        assert "complete" in audio_messages[1].data["text"].lower()

    def test_get_progress_waiting_brake(self, pushback_service: PushbackService) -> None:
        """Test progress during brake release wait."""
        request = ServiceRequest(
            service_type=ServiceType.PUSHBACK,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={"direction": "NORTH"},
        )

        pushback_service.start(request)
        progress = pushback_service.get_progress()

        # Should be at 10% during wait
        assert progress == pytest.approx(0.1, rel=0.01)

    def test_get_progress_during_pushback(self, pushback_service: PushbackService) -> None:
        """Test progress during pushback."""
        request = ServiceRequest(
            service_type=ServiceType.PUSHBACK,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={"direction": "NORTH"},
        )

        pushback_service.start(request)
        pushback_service.status = ServiceStatus.IN_PROGRESS
        pushback_service.pushback_phase = PushbackPhase.PUSHING_BACK
        pushback_service.phase_start_time = time.time() - 15.0  # 50% through
        pushback_service.pushback_duration = 30.0

        progress = pushback_service.get_progress()

        # Should be 30% + 70% * 50% = 65%
        assert progress == pytest.approx(0.65, rel=0.02)

    def test_get_progress_when_complete(self, pushback_service: PushbackService) -> None:
        """Test progress is 100% when complete."""
        request = ServiceRequest(
            service_type=ServiceType.PUSHBACK,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={"direction": "NORTH"},
        )

        pushback_service.start(request)
        pushback_service.status = ServiceStatus.COMPLETE
        pushback_service.pushback_phase = PushbackPhase.COMPLETE

        progress = pushback_service.get_progress()

        assert progress == 1.0

    def test_interpolate_position(self, pushback_service: PushbackService) -> None:
        """Test position interpolation during pushback."""
        pushback_service.start_position = Vector3(-122.0, 100.0, 37.0)
        pushback_service.target_position = Vector3(-122.0, 100.0, 36.99955)

        # 50% progress
        mid_position = pushback_service._interpolate_position(0.5)

        assert mid_position.x == pytest.approx(-122.0, rel=0.001)
        assert mid_position.y == pytest.approx(100.0, rel=0.001)
        assert mid_position.z == pytest.approx(36.999775, rel=0.001)

    def test_custom_pushback_distance(self, pushback_service: PushbackService) -> None:
        """Test custom pushback distance."""
        request = ServiceRequest(
            service_type=ServiceType.PUSHBACK,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={
                "direction": "NORTH",
                "distance": 75.0,  # Custom distance
                "current_position": {"x": -122.0, "y": 100.0, "z": 37.0},
            },
        )

        pushback_service.start(request)

        assert pushback_service.pushback_distance == 75.0

    def test_update_when_idle(self, pushback_service: PushbackService) -> None:
        """Test that update does nothing when service is idle."""
        pushback_service.status = ServiceStatus.IDLE
        initial_phase = pushback_service.pushback_phase

        pushback_service.update(1.0)

        assert pushback_service.pushback_phase == initial_phase

    def test_vector3_position_input(self, pushback_service: PushbackService) -> None:
        """Test pushback with Vector3 position input."""
        request = ServiceRequest(
            service_type=ServiceType.PUSHBACK,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={
                "direction": "NORTH",
                "current_position": Vector3(-122.0, 100.0, 37.0),
            },
        )

        pushback_service.start(request)

        assert pushback_service.start_position is not None
        assert pushback_service.start_position.x == -122.0
        assert pushback_service.start_position.y == 100.0
        assert pushback_service.start_position.z == 37.0

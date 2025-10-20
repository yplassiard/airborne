"""Unit tests for boarding and deboarding services."""

import time

import pytest

from airborne.core.messaging import MessageQueue
from airborne.plugins.ground.ground_services import ServiceRequest, ServiceStatus, ServiceType
from airborne.plugins.ground.services.boarding import BoardingService, DeboardingService


@pytest.fixture
def message_queue() -> MessageQueue:
    """Create a test message queue."""
    return MessageQueue()


@pytest.fixture
def boarding_service(message_queue: MessageQueue) -> BoardingService:
    """Create a boarding service instance."""
    return BoardingService(message_queue)


@pytest.fixture
def deboarding_service(message_queue: MessageQueue) -> DeboardingService:
    """Create a deboarding service instance."""
    return DeboardingService(message_queue)


class TestBoardingService:
    """Test BoardingService class."""

    def test_create_service(self, boarding_service: BoardingService) -> None:
        """Test creating a boarding service."""
        assert boarding_service.service_type == ServiceType.BOARDING
        assert boarding_service.status == ServiceStatus.IDLE

    def test_start_boarding_jet(
        self, boarding_service: BoardingService, message_queue: MessageQueue
    ) -> None:
        """Test starting boarding for jet aircraft."""
        audio_messages: list = []

        def capture_audio(msg):  # type: ignore
            audio_messages.append(msg)

        message_queue.subscribe("ground.audio.speak", capture_audio)

        request = ServiceRequest(
            service_type=ServiceType.BOARDING,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={"passenger_count": 100, "is_jet": True},
        )

        result = boarding_service.start(request)

        assert result is True
        assert boarding_service.status == ServiceStatus.IN_PROGRESS
        assert boarding_service.passenger_count == 100
        assert boarding_service.boarding_rate == 3.0
        assert boarding_service.estimated_duration == 300.0  # 100 * 3

        message_queue.process()
        assert len(audio_messages) == 1
        assert "100 passengers" in audio_messages[0].data["text"]

    def test_start_boarding_ga(self, boarding_service: BoardingService) -> None:
        """Test boarding for GA aircraft is faster."""
        request = ServiceRequest(
            service_type=ServiceType.BOARDING,
            aircraft_id="N456CD",
            parking_id="G2",
            timestamp=time.time(),
            parameters={"passenger_count": 4, "is_jet": False},
        )

        boarding_service.start(request)

        assert boarding_service.boarding_rate == 1.0  # Faster
        assert boarding_service.estimated_duration == 4.0

    def test_boarding_progress(self, boarding_service: BoardingService) -> None:
        """Test boarding progress calculation."""
        request = ServiceRequest(
            service_type=ServiceType.BOARDING,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={"passenger_count": 100, "is_jet": True},
        )

        boarding_service.start(request)
        assert boarding_service.get_progress() == 0.0

        boarding_service.passengers_boarded = 50
        assert boarding_service.get_progress() == pytest.approx(0.5, rel=0.01)

        boarding_service.passengers_boarded = 100
        assert boarding_service.get_progress() == 1.0

    def test_boarding_completes_when_all_boarded(
        self, boarding_service: BoardingService
    ) -> None:
        """Test boarding completes when all passengers board."""
        request = ServiceRequest(
            service_type=ServiceType.BOARDING,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={"passenger_count": 10, "is_jet": False},
        )

        boarding_service.start(request)
        boarding_service.boarding_rate = 0.1  # Very fast for testing

        # Fast-forward
        boarding_service.last_update_time = time.time() - 2.0
        boarding_service.update(2.0)

        assert boarding_service.status == ServiceStatus.COMPLETE

    def test_boarding_progress_announcements(
        self, boarding_service: BoardingService, message_queue: MessageQueue
    ) -> None:
        """Test progress announcements at 25% intervals."""
        audio_messages: list = []

        def capture_audio(msg):  # type: ignore
            audio_messages.append(msg)

        message_queue.subscribe("ground.audio.speak", capture_audio)

        request = ServiceRequest(
            service_type=ServiceType.BOARDING,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={"passenger_count": 100, "is_jet": True},
        )

        boarding_service.start(request)
        message_queue.process()
        audio_messages.clear()

        # Simulate 25% progress
        boarding_service.passengers_boarded = 25
        boarding_service.update(0.1)
        message_queue.process()
        assert any("25%" in msg.data["text"] for msg in audio_messages)

        # Simulate 50% progress
        boarding_service.passengers_boarded = 50
        boarding_service.update(0.1)
        message_queue.process()
        assert any("50%" in msg.data["text"] for msg in audio_messages)


class TestDeboardingService:
    """Test DeboardingService class."""

    def test_create_service(self, deboarding_service: DeboardingService) -> None:
        """Test creating a deboarding service."""
        assert deboarding_service.service_type == ServiceType.DEBOARDING
        assert deboarding_service.status == ServiceStatus.IDLE

    def test_start_deboarding(
        self, deboarding_service: DeboardingService, message_queue: MessageQueue
    ) -> None:
        """Test starting deboarding service."""
        audio_messages: list = []

        def capture_audio(msg):  # type: ignore
            audio_messages.append(msg)

        message_queue.subscribe("ground.audio.speak", capture_audio)

        request = ServiceRequest(
            service_type=ServiceType.DEBOARDING,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={"passenger_count": 100, "is_jet": True},
        )

        result = deboarding_service.start(request)

        assert result is True
        assert deboarding_service.status == ServiceStatus.IN_PROGRESS
        assert deboarding_service.passenger_count == 100
        assert deboarding_service.deboarding_rate == 2.0  # Faster than boarding

        message_queue.process()
        assert len(audio_messages) == 1
        assert "Deboarding started" in audio_messages[0].data["text"]

    def test_deboarding_faster_than_boarding(
        self, deboarding_service: DeboardingService
    ) -> None:
        """Test deboarding is faster than boarding."""
        request = ServiceRequest(
            service_type=ServiceType.DEBOARDING,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={"passenger_count": 100, "is_jet": True},
        )

        deboarding_service.start(request)

        # Deboarding rate should be faster (lower value = faster)
        assert deboarding_service.deboarding_rate < 3.0  # Less than jet boarding rate

    def test_deboarding_progress(self, deboarding_service: DeboardingService) -> None:
        """Test deboarding progress calculation."""
        request = ServiceRequest(
            service_type=ServiceType.DEBOARDING,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={"passenger_count": 100, "is_jet": True},
        )

        deboarding_service.start(request)
        assert deboarding_service.get_progress() == 0.0

        deboarding_service.passengers_deboarded = 50
        assert deboarding_service.get_progress() == pytest.approx(0.5, rel=0.01)

        deboarding_service.passengers_deboarded = 100
        assert deboarding_service.get_progress() == 1.0

    def test_deboarding_completes(self, deboarding_service: DeboardingService) -> None:
        """Test deboarding completes when all passengers deplane."""
        request = ServiceRequest(
            service_type=ServiceType.DEBOARDING,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={"passenger_count": 10, "is_jet": False},
        )

        deboarding_service.start(request)
        deboarding_service.deboarding_rate = 0.1  # Very fast for testing

        # Fast-forward
        deboarding_service.last_update_time = time.time() - 2.0
        deboarding_service.update(2.0)

        assert deboarding_service.status == ServiceStatus.COMPLETE

    def test_ga_deboarding_faster(self, deboarding_service: DeboardingService) -> None:
        """Test GA aircraft deboard faster."""
        request = ServiceRequest(
            service_type=ServiceType.DEBOARDING,
            aircraft_id="N456CD",
            parking_id="G2",
            timestamp=time.time(),
            parameters={"passenger_count": 4, "is_jet": False},
        )

        deboarding_service.start(request)

        assert deboarding_service.deboarding_rate == 0.5  # Faster for GA

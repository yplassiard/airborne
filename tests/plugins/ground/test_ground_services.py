"""Unit tests for ground services framework."""

import time

import pytest

from airborne.airports.classifier import AirportCategory
from airborne.core.messaging import MessageQueue
from airborne.plugins.ground.ground_services import (
    GroundService,
    GroundServiceManager,
    ServiceRequest,
    ServiceStatus,
    ServiceType,
)


@pytest.fixture
def message_queue() -> MessageQueue:
    """Create a test message queue."""
    return MessageQueue()


class MockGroundService(GroundService):
    """Mock ground service for testing."""

    def __init__(self, service_type: ServiceType, message_queue: MessageQueue | None = None):
        super().__init__(service_type, message_queue)
        self.started = False
        self.updated = False
        self.duration = 10.0  # 10 seconds

    def start(self, request: ServiceRequest) -> bool:
        """Start the mock service."""
        self.request = request
        self.status = ServiceStatus.IN_PROGRESS
        self.start_time = time.time()
        self.estimated_duration = self.duration
        self.started = True
        self._publish_status_update()
        return True

    def update(self, dt: float) -> None:
        """Update the mock service."""
        self.updated = True
        if self.get_progress() >= 1.0:
            self.status = ServiceStatus.COMPLETE
            self._publish_status_update()


class TestServiceType:
    """Test ServiceType enum."""

    def test_service_types(self) -> None:
        """Test all service types."""
        assert ServiceType.REFUEL.value == "refuel"
        assert ServiceType.PUSHBACK.value == "pushback"
        assert ServiceType.BOARDING.value == "boarding"
        assert ServiceType.DEBOARDING.value == "deboarding"
        assert ServiceType.CARGO_LOAD.value == "cargo_load"
        assert ServiceType.CARGO_UNLOAD.value == "cargo_unload"
        assert ServiceType.GPU.value == "gpu"
        assert ServiceType.CATERING.value == "catering"
        assert ServiceType.LAVATORY.value == "lavatory"
        assert ServiceType.WATER.value == "water"


class TestServiceStatus:
    """Test ServiceStatus enum."""

    def test_service_statuses(self) -> None:
        """Test all service statuses."""
        assert ServiceStatus.IDLE.value == "idle"
        assert ServiceStatus.REQUESTED.value == "requested"
        assert ServiceStatus.IN_PROGRESS.value == "in_progress"
        assert ServiceStatus.COMPLETE.value == "complete"
        assert ServiceStatus.CANCELLED.value == "cancelled"
        assert ServiceStatus.FAILED.value == "failed"


class TestServiceRequest:
    """Test ServiceRequest dataclass."""

    def test_create_request(self) -> None:
        """Test creating a service request."""
        timestamp = time.time()
        request = ServiceRequest(
            service_type=ServiceType.REFUEL,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=timestamp,
        )

        assert request.service_type == ServiceType.REFUEL
        assert request.aircraft_id == "N123AB"
        assert request.parking_id == "G1"
        assert request.timestamp == timestamp
        assert request.parameters is None

    def test_create_request_with_parameters(self) -> None:
        """Test creating a service request with parameters."""
        request = ServiceRequest(
            service_type=ServiceType.REFUEL,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={"quantity": 50.0},
        )

        assert request.parameters is not None
        assert request.parameters["quantity"] == 50.0


class TestGroundService:
    """Test GroundService base class."""

    def test_create_service(self, message_queue: MessageQueue) -> None:
        """Test creating a ground service."""
        service = MockGroundService(ServiceType.REFUEL, message_queue)

        assert service.service_type == ServiceType.REFUEL
        assert service.status == ServiceStatus.IDLE
        assert service.request is None
        assert service.message_queue == message_queue

    def test_start_service(self, message_queue: MessageQueue) -> None:
        """Test starting a service."""
        service = MockGroundService(ServiceType.REFUEL, message_queue)
        request = ServiceRequest(
            service_type=ServiceType.REFUEL,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
        )

        result = service.start(request)

        assert result is True
        assert service.started is True
        assert service.status == ServiceStatus.IN_PROGRESS
        assert service.request == request

    def test_update_service(self, message_queue: MessageQueue) -> None:
        """Test updating a service."""
        service = MockGroundService(ServiceType.REFUEL, message_queue)
        service.duration = 0.1  # Short duration for testing
        request = ServiceRequest(
            service_type=ServiceType.REFUEL,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
        )

        service.start(request)
        time.sleep(0.2)  # Wait for completion
        service.update(0.1)

        assert service.updated is True
        assert service.status == ServiceStatus.COMPLETE

    def test_cancel_service(self, message_queue: MessageQueue) -> None:
        """Test cancelling a service."""
        service = MockGroundService(ServiceType.REFUEL, message_queue)
        request = ServiceRequest(
            service_type=ServiceType.REFUEL,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
        )

        service.start(request)
        service.cancel()

        assert service.status == ServiceStatus.CANCELLED

    def test_get_progress(self, message_queue: MessageQueue) -> None:
        """Test getting service progress."""
        service = MockGroundService(ServiceType.REFUEL, message_queue)
        service.duration = 1.0
        request = ServiceRequest(
            service_type=ServiceType.REFUEL,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
        )

        # Before starting
        assert service.get_progress() == 0.0

        # After starting
        service.start(request)
        time.sleep(0.5)
        progress = service.get_progress()
        assert 0.4 < progress < 0.6  # Approximately 50%

    def test_get_progress_idle(self, message_queue: MessageQueue) -> None:
        """Test progress when service is idle."""
        service = MockGroundService(ServiceType.REFUEL, message_queue)
        assert service.get_progress() == 0.0


class TestGroundServiceManager:
    """Test GroundServiceManager class."""

    def test_create_manager(self, message_queue: MessageQueue) -> None:
        """Test creating a ground service manager."""
        manager = GroundServiceManager(message_queue, AirportCategory.LARGE)

        assert manager.message_queue == message_queue
        assert manager.airport_category == AirportCategory.LARGE
        assert len(manager.services) == 0
        assert len(manager.active_requests) == 0

    def test_register_service(self, message_queue: MessageQueue) -> None:
        """Test registering a service."""
        manager = GroundServiceManager(message_queue)
        service = MockGroundService(ServiceType.REFUEL, message_queue)

        manager.register_service(service)

        assert ServiceType.REFUEL in manager.services
        assert manager.services[ServiceType.REFUEL] == service

    def test_service_availability_small_airport(self, message_queue: MessageQueue) -> None:
        """Test service availability at small airport."""
        manager = GroundServiceManager(message_queue, AirportCategory.SMALL)
        manager.register_service(MockGroundService(ServiceType.REFUEL, message_queue))
        manager.register_service(MockGroundService(ServiceType.PUSHBACK, message_queue))

        # Small airports: only refuel
        assert manager.is_service_available(ServiceType.REFUEL)
        assert not manager.is_service_available(ServiceType.PUSHBACK)

    def test_service_availability_medium_airport(self, message_queue: MessageQueue) -> None:
        """Test service availability at medium airport."""
        manager = GroundServiceManager(message_queue, AirportCategory.MEDIUM)
        manager.register_service(MockGroundService(ServiceType.REFUEL, message_queue))
        manager.register_service(MockGroundService(ServiceType.GPU, message_queue))
        manager.register_service(MockGroundService(ServiceType.BOARDING, message_queue))
        manager.register_service(MockGroundService(ServiceType.CATERING, message_queue))

        # Medium airports: refuel, GPU, boarding
        assert manager.is_service_available(ServiceType.REFUEL)
        assert manager.is_service_available(ServiceType.GPU)
        assert manager.is_service_available(ServiceType.BOARDING)
        assert not manager.is_service_available(ServiceType.CATERING)

    def test_service_availability_large_airport(self, message_queue: MessageQueue) -> None:
        """Test service availability at large airport."""
        manager = GroundServiceManager(message_queue, AirportCategory.LARGE)
        manager.register_service(MockGroundService(ServiceType.REFUEL, message_queue))
        manager.register_service(MockGroundService(ServiceType.PUSHBACK, message_queue))
        manager.register_service(MockGroundService(ServiceType.CATERING, message_queue))

        # Large airports: all services
        assert manager.is_service_available(ServiceType.REFUEL)
        assert manager.is_service_available(ServiceType.PUSHBACK)
        assert manager.is_service_available(ServiceType.CATERING)

    def test_request_service(self, message_queue: MessageQueue) -> None:
        """Test requesting a service."""
        manager = GroundServiceManager(message_queue, AirportCategory.LARGE)
        manager.register_service(MockGroundService(ServiceType.REFUEL, message_queue))

        result = manager.request_service(ServiceType.REFUEL, "N123AB", "G1", quantity=50.0)

        assert result is True
        assert "N123AB" in manager.active_requests
        assert manager.active_requests["N123AB"].service_type == ServiceType.REFUEL

    def test_request_unavailable_service(self, message_queue: MessageQueue) -> None:
        """Test requesting unavailable service."""
        manager = GroundServiceManager(message_queue, AirportCategory.SMALL)
        manager.register_service(MockGroundService(ServiceType.PUSHBACK, message_queue))

        result = manager.request_service(ServiceType.PUSHBACK, "N123AB", "G1")

        assert result is False
        assert "N123AB" not in manager.active_requests

    def test_request_service_already_active(self, message_queue: MessageQueue) -> None:
        """Test requesting service when already active."""
        manager = GroundServiceManager(message_queue, AirportCategory.LARGE)
        manager.register_service(MockGroundService(ServiceType.REFUEL, message_queue))
        manager.register_service(MockGroundService(ServiceType.BOARDING, message_queue))

        # First request succeeds
        result1 = manager.request_service(ServiceType.REFUEL, "N123AB", "G1")
        assert result1 is True

        # Second request fails (aircraft already has active service)
        result2 = manager.request_service(ServiceType.BOARDING, "N123AB", "G1")
        assert result2 is False

    def test_cancel_service(self, message_queue: MessageQueue) -> None:
        """Test cancelling a service."""
        manager = GroundServiceManager(message_queue, AirportCategory.LARGE)
        manager.register_service(MockGroundService(ServiceType.REFUEL, message_queue))

        manager.request_service(ServiceType.REFUEL, "N123AB", "G1")
        result = manager.cancel_service("N123AB")

        assert result is True
        assert "N123AB" not in manager.active_requests

    def test_cancel_nonexistent_service(self, message_queue: MessageQueue) -> None:
        """Test cancelling service that doesn't exist."""
        manager = GroundServiceManager(message_queue)

        result = manager.cancel_service("N123AB")

        assert result is False

    def test_update_manager(self, message_queue: MessageQueue) -> None:
        """Test updating manager updates all services."""
        manager = GroundServiceManager(message_queue, AirportCategory.LARGE)
        service = MockGroundService(ServiceType.REFUEL, message_queue)
        service.duration = 0.1
        manager.register_service(service)

        manager.request_service(ServiceType.REFUEL, "N123AB", "G1")
        time.sleep(0.2)
        manager.update(0.1)

        assert service.updated is True
        assert service.status == ServiceStatus.COMPLETE
        # Completed service should be removed from active requests
        assert "N123AB" not in manager.active_requests

    def test_get_service_status(self, message_queue: MessageQueue) -> None:
        """Test getting service status."""
        manager = GroundServiceManager(message_queue, AirportCategory.LARGE)
        manager.register_service(MockGroundService(ServiceType.REFUEL, message_queue))

        # Before request
        status = manager.get_service_status("N123AB")
        assert status is None

        # After request
        manager.request_service(ServiceType.REFUEL, "N123AB", "G1")
        status = manager.get_service_status("N123AB")
        assert status == ServiceStatus.IN_PROGRESS

    def test_get_active_service_type(self, message_queue: MessageQueue) -> None:
        """Test getting active service type."""
        manager = GroundServiceManager(message_queue, AirportCategory.LARGE)
        manager.register_service(MockGroundService(ServiceType.REFUEL, message_queue))

        # Before request
        service_type = manager.get_active_service_type("N123AB")
        assert service_type is None

        # After request
        manager.request_service(ServiceType.REFUEL, "N123AB", "G1")
        service_type = manager.get_active_service_type("N123AB")
        assert service_type == ServiceType.REFUEL

    def test_multiple_aircraft(self, message_queue: MessageQueue) -> None:
        """Test managing services for multiple aircraft."""
        manager = GroundServiceManager(message_queue, AirportCategory.LARGE)
        manager.register_service(MockGroundService(ServiceType.REFUEL, message_queue))
        manager.register_service(MockGroundService(ServiceType.BOARDING, message_queue))

        result1 = manager.request_service(ServiceType.REFUEL, "N123AB", "G1")
        result2 = manager.request_service(ServiceType.BOARDING, "N456CD", "G2")

        assert result1 is True
        assert result2 is True
        assert len(manager.active_requests) == 2

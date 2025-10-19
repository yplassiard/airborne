"""Ground services framework for AirBorne.

This module provides the base framework for all ground services including
refueling, pushback, boarding, and cargo operations. Services are managed
by the GroundServiceManager and have availability based on airport type.

Typical usage:
    from airborne.plugins.ground.ground_services import GroundServiceManager, ServiceType

    manager = GroundServiceManager(message_queue, airport_category)
    manager.request_service(ServiceType.REFUEL, "N123AB", "G1")
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

from airborne.airports.classifier import AirportCategory
from airborne.core.messaging import Message, MessageQueue

logger = logging.getLogger(__name__)


class ServiceType(Enum):
    """Types of ground services available at airports.

    Attributes:
        REFUEL: Aircraft refueling service
        PUSHBACK: Pushback tug service for departing from gates
        BOARDING: Passenger boarding service
        DEBOARDING: Passenger deboarding service
        CARGO_LOAD: Cargo loading service
        CARGO_UNLOAD: Cargo unloading service
        GPU: Ground Power Unit hookup
        CATERING: Catering service for passenger aircraft
        LAVATORY: Lavatory servicing
        WATER: Potable water servicing

    Examples:
        >>> service_type = ServiceType.REFUEL
        >>> service_type.value
        'refuel'
    """

    REFUEL = "refuel"
    PUSHBACK = "pushback"
    BOARDING = "boarding"
    DEBOARDING = "deboarding"
    CARGO_LOAD = "cargo_load"
    CARGO_UNLOAD = "cargo_unload"
    GPU = "gpu"
    CATERING = "catering"
    LAVATORY = "lavatory"
    WATER = "water"


class ServiceStatus(Enum):
    """Status of a ground service request.

    Attributes:
        IDLE: Service is not active
        REQUESTED: Service has been requested but not started
        IN_PROGRESS: Service is currently being performed
        COMPLETE: Service has been completed successfully
        CANCELLED: Service was cancelled before completion
        FAILED: Service failed to complete

    Examples:
        >>> status = ServiceStatus.IN_PROGRESS
        >>> status == ServiceStatus.COMPLETE
        False
    """

    IDLE = "idle"
    REQUESTED = "requested"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class ServiceRequest:
    """Request for a ground service.

    Attributes:
        service_type: Type of service requested
        aircraft_id: Aircraft callsign/identifier
        parking_id: Parking position ID where aircraft is located
        timestamp: Time request was made (Unix timestamp)
        parameters: Optional service-specific parameters (e.g., fuel quantity)

    Examples:
        >>> request = ServiceRequest(
        ...     service_type=ServiceType.REFUEL,
        ...     aircraft_id="N123AB",
        ...     parking_id="G1",
        ...     timestamp=time.time(),
        ...     parameters={"quantity": 50.0}
        ... )
    """

    service_type: ServiceType
    aircraft_id: str
    parking_id: str
    timestamp: float
    parameters: dict[str, Any] | None = None


class GroundService(ABC):
    """Abstract base class for all ground services.

    All ground services must inherit from this class and implement the
    abstract methods. Services manage their own state and publish status
    updates via the message queue.

    Attributes:
        service_type: Type of service this class provides
        status: Current status of the service
        request: The service request being processed
        message_queue: Queue for publishing service events
        start_time: Time service was started (Unix timestamp)
        estimated_duration: Estimated time to complete service (seconds)

    Examples:
        class MyService(GroundService):
            def start(self, request: ServiceRequest) -> bool:
                # Implementation
                return True

            def update(self, dt: float) -> None:
                # Update service state
                pass

            def cancel(self) -> None:
                self.status = ServiceStatus.CANCELLED
    """

    def __init__(
        self, service_type: ServiceType, message_queue: MessageQueue | None = None
    ) -> None:
        """Initialize ground service.

        Args:
            service_type: Type of service this class provides
            message_queue: Optional message queue for publishing events
        """
        self.service_type = service_type
        self.status = ServiceStatus.IDLE
        self.request: ServiceRequest | None = None
        self.message_queue = message_queue
        self.start_time: float = 0.0
        self.estimated_duration: float = 0.0

    @abstractmethod
    def start(self, request: ServiceRequest) -> bool:
        """Start the service with the given request.

        Args:
            request: Service request details

        Returns:
            True if service started successfully, False otherwise
        """

    @abstractmethod
    def update(self, dt: float) -> None:
        """Update service state.

        Called periodically to update service progress. Services should
        check if they're complete and update status accordingly.

        Args:
            dt: Time since last update (seconds)
        """

    def cancel(self) -> None:
        """Cancel the service if in progress.

        Changes status to CANCELLED and publishes cancellation event.
        """
        if self.status == ServiceStatus.IN_PROGRESS:
            self.status = ServiceStatus.CANCELLED
            self._publish_status_update()
            logger.info(
                "Cancelled service: %s for %s",
                self.service_type.value,
                self.request.aircraft_id if self.request else "unknown",
            )

    def get_progress(self) -> float:
        """Get service completion progress.

        Returns:
            Progress as percentage (0.0 to 1.0)
        """
        if self.status != ServiceStatus.IN_PROGRESS or self.estimated_duration == 0:
            return 0.0

        elapsed = time.time() - self.start_time
        return min(1.0, elapsed / self.estimated_duration)

    def _publish_status_update(self) -> None:
        """Publish service status update to message queue."""
        if not self.message_queue or not self.request:
            return

        self.message_queue.publish(
            Message(
                sender="ground_services",
                recipients=["all"],
                topic="ground.service.status_changed",
                data={
                    "service_type": self.service_type.value,
                    "aircraft_id": self.request.aircraft_id,
                    "parking_id": self.request.parking_id,
                    "status": self.status.value,
                    "progress": self.get_progress(),
                },
            )
        )


class GroundServiceManager:
    """Manages all ground services at an airport.

    Coordinates service requests, tracks active services, and determines
    service availability based on airport category and parking position.

    Attributes:
        message_queue: Queue for service events
        airport_category: Category of airport (determines service availability)
        services: Dictionary of registered services by type
        active_requests: Dictionary of active service requests by aircraft ID

    Examples:
        >>> manager = GroundServiceManager(queue, AirportCategory.LARGE)
        >>> manager.register_service(RefuelingService(queue))
        >>> available = manager.is_service_available(ServiceType.REFUEL, "G1")
        >>> if available:
        ...     manager.request_service(ServiceType.REFUEL, "N123AB", "G1")
    """

    def __init__(
        self,
        message_queue: MessageQueue | None = None,
        airport_category: AirportCategory = AirportCategory.MEDIUM,
    ) -> None:
        """Initialize ground service manager.

        Args:
            message_queue: Optional message queue for events
            airport_category: Airport category (affects service availability)
        """
        self.message_queue = message_queue
        self.airport_category = airport_category
        self.services: dict[ServiceType, GroundService] = {}
        self.active_requests: dict[str, ServiceRequest] = {}

        logger.info(
            "GroundServiceManager initialized (airport_category=%s)", airport_category.value
        )

    def register_service(self, service: GroundService) -> None:
        """Register a ground service.

        Args:
            service: Ground service instance to register
        """
        self.services[service.service_type] = service
        logger.info("Registered service: %s", service.service_type.value)

    def is_service_available(
        self, service_type: ServiceType, parking_id: str | None = None
    ) -> bool:
        """Check if a service is available.

        Availability depends on airport category and parking position type.

        Args:
            service_type: Type of service to check
            parking_id: Optional parking position ID (for position-specific services)

        Returns:
            True if service is available, False otherwise

        Examples:
            >>> manager.is_service_available(ServiceType.REFUEL, "G1")
            True
            >>> manager.is_service_available(ServiceType.PUSHBACK, "RAMP_1")
            False
        """
        # Service must be registered
        if service_type not in self.services:
            return False

        # Check airport category constraints
        if self.airport_category == AirportCategory.SMALL:
            # Small airports: only refuel (self-service), limited hours
            return service_type == ServiceType.REFUEL

        if self.airport_category == AirportCategory.MEDIUM:
            # Medium airports: refuel, GPU, limited boarding
            allowed = {
                ServiceType.REFUEL,
                ServiceType.GPU,
                ServiceType.BOARDING,
                ServiceType.DEBOARDING,
            }
            return service_type in allowed

        # Large airports: all services available
        return True

    def request_service(
        self, service_type: ServiceType, aircraft_id: str, parking_id: str, **parameters: Any
    ) -> bool:
        """Request a ground service.

        Args:
            service_type: Type of service requested
            aircraft_id: Aircraft identifier
            parking_id: Parking position ID
            **parameters: Service-specific parameters

        Returns:
            True if request accepted, False if unavailable or already active

        Examples:
            >>> manager.request_service(ServiceType.REFUEL, "N123AB", "G1", quantity=50.0)
            True
        """
        # Check if service is available
        if not self.is_service_available(service_type, parking_id):
            logger.warning(
                "Service %s not available at %s (category=%s)",
                service_type.value,
                parking_id,
                self.airport_category.value,
            )
            return False

        # Check if aircraft already has active request
        if aircraft_id in self.active_requests:
            logger.warning("Aircraft %s already has active service request", aircraft_id)
            return False

        # Create service request
        request = ServiceRequest(
            service_type=service_type,
            aircraft_id=aircraft_id,
            parking_id=parking_id,
            timestamp=time.time(),
            parameters=parameters if parameters else None,
        )

        # Start the service
        service = self.services[service_type]
        if service.start(request):
            self.active_requests[aircraft_id] = request
            logger.info(
                "Started service: %s for %s at %s", service_type.value, aircraft_id, parking_id
            )
            return True

        logger.error("Failed to start service: %s for %s", service_type.value, aircraft_id)
        return False

    def cancel_service(self, aircraft_id: str) -> bool:
        """Cancel active service for an aircraft.

        Args:
            aircraft_id: Aircraft identifier

        Returns:
            True if service was cancelled, False if no active service
        """
        if aircraft_id not in self.active_requests:
            return False

        request = self.active_requests[aircraft_id]
        service = self.services.get(request.service_type)
        if service:
            service.cancel()

        del self.active_requests[aircraft_id]
        return True

    def update(self, dt: float) -> None:
        """Update all active services.

        Args:
            dt: Time since last update (seconds)
        """
        # Update all registered services
        for service in self.services.values():
            if service.status == ServiceStatus.IN_PROGRESS:
                service.update(dt)

        # Remove completed/cancelled services from active requests
        completed = [
            aircraft_id
            for aircraft_id, request in self.active_requests.items()
            if self.services[request.service_type].status
            in {ServiceStatus.COMPLETE, ServiceStatus.CANCELLED, ServiceStatus.FAILED}
        ]

        for aircraft_id in completed:
            del self.active_requests[aircraft_id]

    def get_service_status(self, aircraft_id: str) -> ServiceStatus | None:
        """Get status of service for an aircraft.

        Args:
            aircraft_id: Aircraft identifier

        Returns:
            Service status, or None if no active service
        """
        if aircraft_id not in self.active_requests:
            return None

        request = self.active_requests[aircraft_id]
        service = self.services.get(request.service_type)
        return service.status if service else None

    def get_active_service_type(self, aircraft_id: str) -> ServiceType | None:
        """Get type of active service for an aircraft.

        Args:
            aircraft_id: Aircraft identifier

        Returns:
            Service type, or None if no active service
        """
        request = self.active_requests.get(aircraft_id)
        return request.service_type if request else None

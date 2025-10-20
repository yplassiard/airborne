"""Ground Services Plugin for AirBorne flight simulator.

Provides realistic ground services including refueling, pushback, boarding,
and deboarding operations at airports. Services are only available when
the aircraft is parked at a designated parking position.

Typical usage:
    The ground services plugin is loaded automatically and provides ground
    services to the simulation when aircraft is parked.
"""

import logging

from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType
from airborne.plugins.ground.ground_services import (
    AirportCategory,
    GroundServiceManager,
    ServiceRequest,
    ServiceStatus,
    ServiceType,
)
from airborne.plugins.ground.services.boarding import BoardingService, DeboardingService
from airborne.plugins.ground.services.pushback import PushbackService
from airborne.plugins.ground.services.refueling import RefuelingService

logger = logging.getLogger(__name__)


class GroundServicesPlugin(IPlugin):
    """Ground services plugin for airport operations.

    Provides refueling, pushback, boarding, and deboarding services
    when aircraft is parked at a gate. Services are integrated with
    aircraft systems (fuel, weight) and provide audio feedback.

    Components provided:
    - ground_service_manager: GroundServiceManager instance for service operations
    """

    def __init__(self) -> None:
        """Initialize ground services plugin."""
        self.context: PluginContext | None = None
        self.service_manager: GroundServiceManager | None = None
        self.is_at_parking: bool = False
        self.current_parking_id: str | None = None
        self.current_position: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return PluginMetadata(
            name="ground_services_plugin",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.FEATURE,
            dependencies=["fuel_plugin", "position_awareness_plugin"],
            provides=["ground_services", "refueling", "pushback", "boarding"],
            optional=False,
            update_priority=60,  # After systems, before UI
            requires_physics=False,
            description="Ground services for refueling, pushback, boarding, and deboarding",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the ground services plugin."""
        self.context = context

        # Get airport category from config
        airport_config = context.config.get("airport", {})
        airport_category_str = airport_config.get("category", "MEDIUM")
        try:
            airport_category = AirportCategory(airport_category_str.lower())
        except ValueError:
            logger.warning("Invalid airport category '%s', using MEDIUM", airport_category_str)
            airport_category = AirportCategory.MEDIUM

        # Create service manager
        self.service_manager = GroundServiceManager(
            message_queue=context.message_queue,
            airport_category=airport_category,
        )

        # Register services
        self.service_manager.register_service(RefuelingService(context.message_queue))
        self.service_manager.register_service(PushbackService(context.message_queue))
        self.service_manager.register_service(BoardingService(context.message_queue))
        self.service_manager.register_service(DeboardingService(context.message_queue))

        # Register in component registry
        if context.plugin_registry:
            context.plugin_registry.register("ground_service_manager", self.service_manager)

        # Subscribe to messages
        context.message_queue.subscribe(MessageTopic.POSITION_UPDATED, self.handle_message)
        context.message_queue.subscribe("ground.service.request", self.handle_message)
        context.message_queue.subscribe("parking.status", self.handle_message)

        logger.info(
            "Ground services plugin initialized with %d services at %s airport",
            len(self.service_manager.services),
            airport_category.value,
        )

    def update(self, dt: float) -> None:
        """Update ground services."""
        if not self.service_manager:
            return

        # Update all active services
        self.service_manager.update(dt)

    def shutdown(self) -> None:
        """Shutdown the ground services plugin."""
        if self.context:
            # Unsubscribe from messages
            self.context.message_queue.unsubscribe(
                MessageTopic.POSITION_UPDATED, self.handle_message
            )
            self.context.message_queue.unsubscribe("ground.service.request", self.handle_message)
            self.context.message_queue.unsubscribe("parking.status", self.handle_message)

            # Unregister components
            if self.context.plugin_registry:
                self.context.plugin_registry.unregister("ground_service_manager")

        logger.info("Ground services plugin shutdown")

    def handle_message(self, message: Message) -> None:
        """Handle messages from other plugins."""
        if not self.service_manager or not self.context:
            return

        if message.topic == MessageTopic.POSITION_UPDATED:
            # Track current position for pushback service
            position = message.data.get("position", {})
            if isinstance(position, dict):
                self.current_position = (
                    position.get("x", 0.0),
                    position.get("y", 0.0),
                    position.get("z", 0.0),
                )

        elif message.topic == "parking.status":
            # Update parking status
            self.is_at_parking = message.data.get("at_parking", False)
            self.current_parking_id = message.data.get("parking_id")

            # If parking status changes, publish service availability
            self._publish_service_availability()

        elif message.topic == "ground.service.request":
            # Handle service request
            self._handle_service_request(message)

    def _handle_service_request(self, message: Message) -> None:
        """Handle a ground service request."""
        if not self.service_manager:
            return

        service_type_str = message.data.get("service_type", "")
        aircraft_id = message.data.get("aircraft_id", "UNKNOWN")
        parameters = message.data.get("parameters", {})

        # Parse service type
        try:
            service_type = ServiceType(service_type_str.lower())
        except ValueError:
            logger.warning("Invalid service type: %s", service_type_str)
            return

        # Check if at parking
        if not self.is_at_parking:
            self._publish_error("Ground services only available when parked at gate")
            return

        # Check if service is available
        if not self.service_manager.is_service_available(service_type, self.current_parking_id):
            self._publish_error(f"{service_type.value} not available at this airport")
            return

        # Add current position to parameters for pushback
        if service_type == ServiceType.PUSHBACK:
            parameters["current_position"] = {
                "x": self.current_position[0],
                "y": self.current_position[1],
                "z": self.current_position[2],
            }

        # Request service
        success = self.service_manager.request_service(
            service_type, aircraft_id, self.current_parking_id or "UNKNOWN", **parameters
        )

        if success:
            logger.info(
                "Service requested: %s for %s at %s",
                service_type.value,
                aircraft_id,
                self.current_parking_id,
            )
        else:
            self._publish_error(f"Failed to request {service_type.value}")

    def _publish_service_availability(self) -> None:
        """Publish available services based on parking status."""
        if not self.context or not self.service_manager:
            return

        available_services = []
        if self.is_at_parking:
            for service_type in ServiceType:
                if self.service_manager.is_service_available(service_type, self.current_parking_id):
                    available_services.append(service_type.value)

        self.context.message_queue.publish(
            Message(
                sender="ground_services_plugin",
                recipients=["*"],
                topic="ground.services.available",
                data={
                    "at_parking": self.is_at_parking,
                    "parking_id": self.current_parking_id,
                    "available_services": available_services,
                },
                priority=MessagePriority.NORMAL,
            )
        )

    def _publish_error(self, error_message: str) -> None:
        """Publish error message via audio."""
        if not self.context:
            return

        self.context.message_queue.publish(
            Message(
                sender="ground_services_plugin",
                recipients=["audio"],
                topic="ground.audio.speak",
                data={
                    "text": error_message,
                    "voice": "ground",
                    "priority": "high",
                },
                priority=MessagePriority.HIGH,
            )
        )

    def is_service_available(self, service_type: ServiceType) -> bool:
        """Check if a service is currently available.

        Args:
            service_type: Type of service to check.

        Returns:
            True if service is available.
        """
        if not self.service_manager or not self.is_at_parking:
            return False

        return self.service_manager.is_service_available(service_type, self.current_parking_id)

    def get_active_services(self) -> list[ServiceType]:
        """Get list of currently active services.

        Returns:
            List of active service types.
        """
        if not self.service_manager:
            return []

        active = []
        for service_type, service in self.service_manager.services.items():
            if service.status in [ServiceStatus.IN_PROGRESS, ServiceStatus.REQUESTED]:
                active.append(service_type)

        return active

    def get_service_status(self, service_type: ServiceType) -> ServiceStatus | None:
        """Get status of a specific service.

        Args:
            service_type: Type of service to query.

        Returns:
            Service status, or None if service not found.
        """
        if not self.service_manager:
            return None

        service = self.service_manager.services.get(service_type)
        return service.status if service else None

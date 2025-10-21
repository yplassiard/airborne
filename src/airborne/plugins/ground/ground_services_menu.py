"""Ground services menu system for interactive service requests.

This module provides a context-aware menu system for player-initiated
ground service requests (refueling, pushback, boarding, etc.). The menu
displays options based on parking status and handles player input.

Typical usage example:
    menu = GroundServicesMenu(ground_services_plugin, message_queue)

    # Check if menu should be available
    if menu.is_available():
        menu.open()

    # Handle key press
    menu.select_option("1")
"""

from typing import Any

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageQueue
from airborne.plugins.ground.ground_services import ServiceType
from airborne.ui.menu import Menu, MenuOption

logger = get_logger(__name__)


class GroundServicesMenu(Menu):
    """Interactive menu for ground service requests.

    Extends the generic Menu base class to provide ground service-specific
    functionality including:
    - Viewing available ground services
    - Requesting services (refuel, pushback, boarding, etc.)
    - Monitoring service status
    - Cancelling active services

    The menu uses a state machine:
    - CLOSED: Menu not visible
    - OPEN: Showing list of available services
    - SERVICE_ACTIVE: Service in progress (additional state beyond base Menu)

    Services communicate via message queue and use pre-recorded TTS
    with service-specific voices (refuel, tug, boarding, ops).
    """

    def __init__(
        self,
        ground_services_plugin: Any,
        message_queue: MessageQueue,
        aircraft_id: str = "N123AB",
    ):
        """Initialize ground services menu.

        Args:
            ground_services_plugin: GroundServicesPlugin instance for service operations.
            message_queue: Message queue for sending service requests and TTS.
            aircraft_id: Aircraft callsign for service requests.
        """
        super().__init__(message_queue, sender_name="ground_services_menu")

        self._ground_services = ground_services_plugin
        self._aircraft_id = aircraft_id
        self._is_at_parking = False
        self._available_services: list[str] = []
        self._active_service: ServiceType | None = None

        # Subscribe to service availability updates
        message_queue.subscribe("ground.services.available", self._handle_service_availability)

        logger.info("Ground services menu initialized for aircraft %s", aircraft_id)

    def open(self, context: Any = None) -> bool:
        """Open the ground services menu with audio feedback.

        Overrides base Menu.open() to provide specific audio feedback when
        the menu is unavailable.

        Args:
            context: Optional context (not used).

        Returns:
            True if menu opened successfully, False otherwise.
        """
        # Check if we're at parking
        if not self._is_at_parking:
            logger.info("Ground services menu not available: not at parking")
            self._speak("MSG_GROUND_NOT_AT_PARKING")
            return False

        # Check if services are available
        if not self._available_services:
            logger.info("Ground services menu not available: no services available")
            self._speak("MSG_GROUND_NO_SERVICES")
            return False

        # Call base class open()
        return super().open(context)

    def _handle_service_availability(self, message: Message) -> None:
        """Handle service availability updates from ground services plugin.

        Args:
            message: Message containing service availability data.
        """
        self._is_at_parking = message.data.get("at_parking", False)
        self._available_services = message.data.get("available_services", [])

    # Public API methods

    def is_available(self) -> bool:
        """Check if ground services menu is available.

        Returns:
            True if aircraft is at parking and services are available.
        """
        return self._is_available(None)

    # Override base methods to handle SERVICE_ACTIVE state

    def get_state(self) -> str:
        """Get current menu state.

        Returns:
            Current state string (CLOSED, SERVICE_SELECTION, SERVICE_ACTIVE).
        """
        # If active service, return SERVICE_ACTIVE instead of base state
        if self._active_service is not None:
            return "SERVICE_ACTIVE"

        # Map OPEN to SERVICE_SELECTION for backward compatibility
        base_state = super().get_state()
        if base_state == "OPEN":
            return "SERVICE_SELECTION"
        return base_state

    def select_option(self, key: str) -> bool:
        """Select a menu option by key.

        Extends base select_option to handle SERVICE_ACTIVE state for cancellation.

        Args:
            key: Option key (e.g., "1", "2", "3").

        Returns:
            True if option was handled, False otherwise.
        """
        # Handle cancellation in SERVICE_ACTIVE state
        if self._active_service is not None and key.upper() == "C":
            self._cancel_active_service()
            return True

        # Otherwise use base class logic
        return super().select_option(key)

    def get_active_service(self) -> ServiceType | None:
        """Get the currently active service type.

        Returns:
            Active service type, or None if no service is active.
        """
        return self._active_service

    # Implement abstract methods from Menu base class

    def _build_options(self, context: Any) -> list[MenuOption]:
        """Build menu options based on available services.

        Args:
            context: Not used for ground services menu.

        Returns:
            List of MenuOption for available services.
        """
        options = []
        key_counter = 1

        # Define all possible services and their menu options
        service_configs = {
            ServiceType.REFUEL: {
                "label": "Request Refueling",
                "message_key": "MSG_GROUND_OPTION_REFUEL",
            },
            ServiceType.PUSHBACK: {
                "label": "Request Pushback",
                "message_key": "MSG_GROUND_OPTION_PUSHBACK",
            },
            ServiceType.BOARDING: {
                "label": "Request Boarding",
                "message_key": "MSG_GROUND_OPTION_BOARDING",
            },
            ServiceType.DEBOARDING: {
                "label": "Request Deboarding",
                "message_key": "MSG_GROUND_OPTION_DEBOARDING",
            },
            ServiceType.GPU: {
                "label": "Request Ground Power",
                "message_key": "MSG_GROUND_OPTION_GPU",
            },
            ServiceType.CATERING: {
                "label": "Request Catering",
                "message_key": "MSG_GROUND_OPTION_CATERING",
            },
        }

        # Build options for available services
        for service_type, config in service_configs.items():
            if service_type.value in self._available_services:
                option = MenuOption(
                    key=str(key_counter),
                    label=config["label"],
                    message_key=config["message_key"],
                    data={"service_type": service_type},
                )
                options.append(option)
                key_counter += 1

        return options

    def _handle_selection(self, option: MenuOption) -> None:
        """Handle selection of a ground service.

        Args:
            option: The selected MenuOption containing service_type in data.
        """
        service_type = option.data.get("service_type")
        if not service_type:
            logger.error("Selected option missing service_type")
            return

        self._request_service(service_type)

    def _get_menu_opened_message(self) -> str:
        """Get TTS message key for menu opened.

        Returns:
            Message key string.
        """
        return "MSG_GROUND_MENU_OPENED"

    def _get_menu_closed_message(self) -> str:
        """Get TTS message key for menu closed.

        Returns:
            Message key string.
        """
        return "MSG_GROUND_MENU_CLOSED"

    def _get_invalid_option_message(self) -> str:
        """Get TTS message key for invalid option.

        Returns:
            Message key string.
        """
        return "MSG_GROUND_INVALID_OPTION"

    def _is_available(self, context: Any) -> bool:
        """Check if ground services menu is available.

        Args:
            context: Not used.

        Returns:
            True if aircraft is at parking and services are available.
        """
        return self._is_at_parking and len(self._available_services) > 0

    # Ground services specific methods

    def _request_service(self, service_type: ServiceType) -> None:
        """Request a ground service.

        Args:
            service_type: Type of service to request.
        """
        logger.info("Requesting service: %s", service_type.value)

        # Close menu (using base class close, but don't speak)
        super().close(speak=False)

        # Build service request parameters
        parameters: dict[str, Any] = {}

        # Add service-specific parameters
        if service_type == ServiceType.REFUEL:
            # Request full tanks (could make this configurable later)
            parameters["target_fuel_percent"] = 100.0
        elif service_type == ServiceType.BOARDING:
            # Board full capacity (could make this configurable later)
            parameters["target_passengers"] = 4  # Cessna 172 default
        elif service_type == ServiceType.PUSHBACK:
            # Use straight back pushback (could add direction selection later)
            parameters["direction"] = "straight"
            parameters["distance"] = 30.0  # 30 feet back

        # Publish service request
        self._message_queue.publish(
            Message(
                sender="ground_services_menu",
                recipients=["ground_services_plugin"],
                topic="ground.service.request",
                data={
                    "service_type": service_type.value,
                    "aircraft_id": self._aircraft_id,
                    "parameters": parameters,
                },
                priority=MessagePriority.NORMAL,
            )
        )

        self._active_service = service_type

        logger.info("Service request sent: %s", service_type.value)

    def _cancel_active_service(self) -> None:
        """Cancel the currently active service."""
        if not self._active_service:
            return

        logger.info("Cancelling active service: %s", self._active_service.value)

        # Publish cancellation message
        self._message_queue.publish(
            Message(
                sender="ground_services_menu",
                recipients=["ground_services_plugin"],
                topic="ground.service.cancel",
                data={
                    "service_type": self._active_service.value,
                    "aircraft_id": self._aircraft_id,
                },
                priority=MessagePriority.HIGH,
            )
        )

        self._speak("MSG_GROUND_SERVICE_CANCELLED")
        self._active_service = None
        # State will return to CLOSED automatically

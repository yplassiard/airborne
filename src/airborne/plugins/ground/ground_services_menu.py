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

from dataclasses import dataclass
from typing import Any

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageQueue, MessageTopic
from airborne.plugins.ground.ground_services import ServiceType

logger = get_logger(__name__)


@dataclass
class GroundServiceMenuOption:
    """Represents a single ground service menu option.

    Attributes:
        key: Key to select this option (e.g., "1", "2").
        label: Human-readable label shown in menu.
        service_type: Type of ground service.
        request_message: Message key for service request announcement.
        availability_check: Function to check if service is available.
    """

    key: str
    label: str
    service_type: ServiceType
    request_message: str
    availability_check: Any = None  # Callable[[], bool] | None


class GroundServicesMenu:
    """Interactive menu for ground service requests.

    Provides a user-friendly interface for:
    - Viewing available ground services
    - Requesting services (refuel, pushback, boarding, etc.)
    - Monitoring service status
    - Cancelling active services

    The menu uses a state machine:
    - CLOSED: Menu not visible
    - SERVICE_SELECTION: Showing list of available services
    - SERVICE_ACTIVE: Service in progress, showing status

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
        self._ground_services = ground_services_plugin
        self._message_queue = message_queue
        self._aircraft_id = aircraft_id
        self._state = "CLOSED"  # CLOSED, SERVICE_SELECTION, SERVICE_ACTIVE
        self._current_options: list[GroundServiceMenuOption] = []
        self._is_at_parking = False
        self._available_services: list[str] = []
        self._active_service: ServiceType | None = None

        # Subscribe to service availability updates
        message_queue.subscribe("ground.services.available", self._handle_service_availability)

        logger.info("Ground services menu initialized for aircraft %s", aircraft_id)

    def _handle_service_availability(self, message: Message) -> None:
        """Handle service availability updates from ground services plugin.

        Args:
            message: Message containing service availability data.
        """
        self._is_at_parking = message.data.get("at_parking", False)
        self._available_services = message.data.get("available_services", [])

    def is_available(self) -> bool:
        """Check if ground services menu is available.

        Returns:
            True if aircraft is at parking and services are available.
        """
        return self._is_at_parking and len(self._available_services) > 0

    def open(self) -> None:
        """Open the ground services menu showing available services."""
        if not self.is_available():
            logger.warning("Ground services not available - not at parking")
            self._speak_message("MSG_GROUND_NOT_AT_PARKING", voice="ops")
            return

        # Build menu options based on available services
        self._current_options = self._build_menu_options()

        if not self._current_options:
            logger.warning("No ground services available at this location")
            self._speak_message("MSG_GROUND_NO_SERVICES", voice="ops")
            return

        self._state = "SERVICE_SELECTION"
        logger.info("Ground services menu opened with %d options", len(self._current_options))

        # Announce menu opening and first option only
        self._speak_message("MSG_GROUND_MENU_OPENED", voice="cockpit")

        # Announce only the first (focused) option
        if self._current_options:
            first_option = self._current_options[0]
            self._speak_message(f"MSG_{first_option.request_message}", voice="cockpit")

    def close(self) -> None:
        """Close the ground services menu."""
        if self._state == "CLOSED":
            return

        self._state = "CLOSED"
        self._current_options = []
        self._active_service = None
        logger.info("Ground services menu closed")

        self._speak_message("MSG_GROUND_MENU_CLOSED", voice="cockpit")

    def select_option(self, key: str) -> None:
        """Select a menu option by key press.

        Args:
            key: The key pressed (e.g., "1", "2", "3").
        """
        if self._state == "CLOSED":
            return

        if self._state == "SERVICE_SELECTION":
            self._handle_service_selection(key)
        elif self._state == "SERVICE_ACTIVE" and key.upper() == "C":
            # Allow cancellation with 'C' key
            self._cancel_active_service()

    def _handle_service_selection(self, key: str) -> None:
        """Handle service selection in SERVICE_SELECTION state.

        Args:
            key: The key pressed.
        """
        # Find matching option
        option = None
        for opt in self._current_options:
            if opt.key == key:
                option = opt
                break

        if not option:
            logger.warning("Invalid menu option: %s", key)
            self._speak_message("MSG_GROUND_INVALID_OPTION", voice="cockpit")
            return

        # Request the service
        self._request_service(option)

    def _request_service(self, option: GroundServiceMenuOption) -> None:
        """Request a ground service.

        Args:
            option: The selected menu option.
        """
        logger.info("Requesting service: %s", option.service_type.value)

        # Close menu
        self.close()

        # Build service request parameters
        parameters: dict[str, Any] = {}

        # Add service-specific parameters
        if option.service_type == ServiceType.REFUEL:
            # Request full tanks (could make this configurable later)
            parameters["target_fuel_percent"] = 100.0
        elif option.service_type == ServiceType.BOARDING:
            # Board full capacity (could make this configurable later)
            parameters["target_passengers"] = 4  # Cessna 172 default
        elif option.service_type == ServiceType.PUSHBACK:
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
                    "service_type": option.service_type.value,
                    "aircraft_id": self._aircraft_id,
                    "parameters": parameters,
                },
                priority=MessagePriority.NORMAL,
            )
        )

        self._active_service = option.service_type
        self._state = "SERVICE_ACTIVE"

        logger.info("Service request sent: %s", option.service_type.value)

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

        self._speak_message("MSG_GROUND_SERVICE_CANCELLED", voice="ops")
        self._active_service = None
        self._state = "CLOSED"

    def _build_menu_options(self) -> list[GroundServiceMenuOption]:
        """Build menu options based on available services.

        Returns:
            List of available menu options.
        """
        options = []
        key_counter = 1

        # Define all possible services and their menu options
        service_configs = {
            ServiceType.REFUEL: {
                "label": "Request Refueling",
                "request_message": "GROUND_OPTION_REFUEL",
            },
            ServiceType.PUSHBACK: {
                "label": "Request Pushback",
                "request_message": "GROUND_OPTION_PUSHBACK",
            },
            ServiceType.BOARDING: {
                "label": "Request Boarding",
                "request_message": "GROUND_OPTION_BOARDING",
            },
            ServiceType.DEBOARDING: {
                "label": "Request Deboarding",
                "request_message": "GROUND_OPTION_DEBOARDING",
            },
            ServiceType.GPU: {
                "label": "Request Ground Power",
                "request_message": "GROUND_OPTION_GPU",
            },
            ServiceType.CATERING: {
                "label": "Request Catering",
                "request_message": "GROUND_OPTION_CATERING",
            },
        }

        # Build options for available services
        for service_type, config in service_configs.items():
            if service_type.value in self._available_services:
                option = GroundServiceMenuOption(
                    key=str(key_counter),
                    label=config["label"],
                    service_type=service_type,
                    request_message=config["request_message"],
                )
                options.append(option)
                key_counter += 1

        return options

    def _speak_message(self, message_key: str, voice: str = "cockpit") -> None:
        """Speak a pre-recorded message via audio plugin.

        Args:
            message_key: The message key to speak (e.g., "MSG_GROUND_MENU_OPENED").
            voice: Voice type to use (cockpit, ops, refuel, tug, boarding).
        """
        self._message_queue.publish(
            Message(
                sender="ground_services_menu",
                recipients=["*"],
                topic=MessageTopic.TTS_SPEAK,
                data={
                    "text": message_key,
                    "voice": voice,
                    "priority": "high",
                    "interrupt": True,
                },
                priority=MessagePriority.HIGH,
            )
        )

    def get_state(self) -> str:
        """Get current menu state.

        Returns:
            Current state string (CLOSED, SERVICE_SELECTION, SERVICE_ACTIVE).
        """
        return self._state

    def is_open(self) -> bool:
        """Check if menu is currently open.

        Returns:
            True if menu is open (not in CLOSED state).
        """
        return self._state != "CLOSED"

    def get_active_service(self) -> ServiceType | None:
        """Get the currently active service type.

        Returns:
            Active service type, or None if no service is active.
        """
        return self._active_service

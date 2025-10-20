"""Unit tests for ground services menu system."""

import pytest

from airborne.core.messaging import Message, MessageQueue
from airborne.plugins.ground.ground_services import ServiceType
from airborne.plugins.ground.ground_services_menu import GroundServicesMenu


class MockGroundServicesPlugin:
    """Mock ground services plugin for testing."""

    def __init__(self):
        """Initialize mock plugin."""
        self.is_at_parking = False
        self.available_services = []

    def is_service_available(self, service_type: ServiceType) -> bool:
        """Check if service is available."""
        return service_type.value in self.available_services


@pytest.fixture
def message_queue():
    """Create a message queue for testing."""
    return MessageQueue()


@pytest.fixture
def mock_plugin():
    """Create a mock ground services plugin."""
    return MockGroundServicesPlugin()


@pytest.fixture
def menu(mock_plugin, message_queue):
    """Create a ground services menu for testing."""
    return GroundServicesMenu(
        ground_services_plugin=mock_plugin,
        message_queue=message_queue,
        aircraft_id="N123AB",
    )


def test_menu_initialization(menu):
    """Test menu initializes correctly."""
    assert menu is not None
    assert menu.get_state() == "CLOSED"
    assert not menu.is_open()


def test_menu_not_available_when_not_at_parking(menu, mock_plugin):
    """Test menu is not available when not at parking."""
    mock_plugin.is_at_parking = False
    mock_plugin.available_services = []

    # Simulate service availability message
    menu._handle_service_availability(
        Message(
            sender="test",
            recipients=["menu"],
            topic="ground.services.available",
            data={"at_parking": False, "available_services": []},
        )
    )

    assert not menu.is_available()


def test_menu_available_when_at_parking_with_services(menu, mock_plugin):
    """Test menu is available when at parking with services."""
    # Simulate service availability message
    menu._handle_service_availability(
        Message(
            sender="test",
            recipients=["menu"],
            topic="ground.services.available",
            data={
                "at_parking": True,
                "available_services": ["refuel", "pushback", "boarding"],
            },
        )
    )

    assert menu.is_available()


def test_menu_not_available_at_parking_without_services(menu, mock_plugin):
    """Test menu is not available at parking without services."""
    # Simulate service availability message
    menu._handle_service_availability(
        Message(
            sender="test",
            recipients=["menu"],
            topic="ground.services.available",
            data={"at_parking": True, "available_services": []},
        )
    )

    assert not menu.is_available()


def test_menu_opens_when_available(menu, message_queue):
    """Test menu opens successfully when available."""
    # Make menu available
    menu._handle_service_availability(
        Message(
            sender="test",
            recipients=["menu"],
            topic="ground.services.available",
            data={
                "at_parking": True,
                "available_services": ["refuel", "pushback"],
            },
        )
    )

    menu.open()

    assert menu.is_open()
    assert menu.get_state() == "SERVICE_SELECTION"


def test_menu_does_not_open_when_unavailable(menu, message_queue):
    """Test menu does not open when not available."""
    # Menu not available (not at parking)
    menu._handle_service_availability(
        Message(
            sender="test",
            recipients=["menu"],
            topic="ground.services.available",
            data={"at_parking": False, "available_services": []},
        )
    )

    menu.open()

    assert not menu.is_open()
    assert menu.get_state() == "CLOSED"


def test_menu_close(menu):
    """Test menu closes correctly."""
    # Make menu available and open it
    menu._handle_service_availability(
        Message(
            sender="test",
            recipients=["menu"],
            topic="ground.services.available",
            data={
                "at_parking": True,
                "available_services": ["refuel"],
            },
        )
    )
    menu.open()

    # Close menu
    menu.close()

    assert not menu.is_open()
    assert menu.get_state() == "CLOSED"


def test_menu_builds_options_correctly(menu):
    """Test menu builds correct options based on available services."""
    # Set available services
    menu._handle_service_availability(
        Message(
            sender="test",
            recipients=["menu"],
            topic="ground.services.available",
            data={
                "at_parking": True,
                "available_services": ["refuel", "pushback", "boarding"],
            },
        )
    )

    menu.open()

    # Menu should have 3 options
    assert len(menu._current_options) == 3
    assert menu._current_options[0].service_type == ServiceType.REFUEL
    assert menu._current_options[1].service_type == ServiceType.PUSHBACK
    assert menu._current_options[2].service_type == ServiceType.BOARDING


def test_menu_select_option_publishes_service_request(menu, message_queue):
    """Test selecting an option publishes service request."""
    # Capture published messages
    captured_messages = []

    def capture_handler(msg):
        captured_messages.append(msg)

    message_queue.subscribe("ground.service.request", capture_handler)

    # Setup
    menu._handle_service_availability(
        Message(
            sender="test",
            recipients=["menu"],
            topic="ground.services.available",
            data={
                "at_parking": True,
                "available_services": ["refuel"],
            },
        )
    )
    menu.open()

    # Select option 1 (refuel)
    menu.select_option("1")

    # Process messages
    message_queue.process()

    # Check that a service request message was published
    assert len(captured_messages) > 0
    assert captured_messages[-1].data["service_type"] == "refuel"
    assert captured_messages[-1].data["aircraft_id"] == "N123AB"


def test_menu_invalid_option_does_not_crash(menu, message_queue):
    """Test selecting invalid option doesn't crash."""
    # Setup
    menu._handle_service_availability(
        Message(
            sender="test",
            recipients=["menu"],
            topic="ground.services.available",
            data={
                "at_parking": True,
                "available_services": ["refuel"],
            },
        )
    )
    menu.open()

    # Try to select option that doesn't exist
    menu.select_option("9")

    # Menu should still be open
    assert menu.is_open()


def test_menu_service_request_includes_default_parameters(menu, message_queue):
    """Test service request includes appropriate default parameters."""
    # Capture published messages
    captured_messages = []

    def capture_handler(msg):
        captured_messages.append(msg)

    message_queue.subscribe("ground.service.request", capture_handler)

    # Setup with refuel service
    menu._handle_service_availability(
        Message(
            sender="test",
            recipients=["menu"],
            topic="ground.services.available",
            data={
                "at_parking": True,
                "available_services": ["refuel"],
            },
        )
    )
    menu.open()

    # Select refuel
    menu.select_option("1")

    # Process messages
    message_queue.process()

    # Check parameters
    assert len(captured_messages) > 0
    params = captured_messages[-1].data.get("parameters", {})
    assert "target_fuel_percent" in params
    assert params["target_fuel_percent"] == 100.0


def test_menu_pushback_parameters(menu, message_queue):
    """Test pushback service request includes correct parameters."""
    # Capture published messages
    captured_messages = []

    def capture_handler(msg):
        captured_messages.append(msg)

    message_queue.subscribe("ground.service.request", capture_handler)

    # Setup with pushback service
    menu._handle_service_availability(
        Message(
            sender="test",
            recipients=["menu"],
            topic="ground.services.available",
            data={
                "at_parking": True,
                "available_services": ["pushback"],
            },
        )
    )
    menu.open()

    # Select pushback
    menu.select_option("1")

    # Process messages
    message_queue.process()

    # Check parameters
    assert len(captured_messages) > 0
    params = captured_messages[-1].data.get("parameters", {})
    assert "direction" in params
    assert "distance" in params
    assert params["direction"] == "straight"
    assert params["distance"] == 30.0


def test_menu_boarding_parameters(menu, message_queue):
    """Test boarding service request includes correct parameters."""
    # Capture published messages
    captured_messages = []

    def capture_handler(msg):
        captured_messages.append(msg)

    message_queue.subscribe("ground.service.request", capture_handler)

    # Setup with boarding service
    menu._handle_service_availability(
        Message(
            sender="test",
            recipients=["menu"],
            topic="ground.services.available",
            data={
                "at_parking": True,
                "available_services": ["boarding"],
            },
        )
    )
    menu.open()

    # Select boarding
    menu.select_option("1")

    # Process messages
    message_queue.process()

    # Check parameters
    assert len(captured_messages) > 0
    params = captured_messages[-1].data.get("parameters", {})
    assert "target_passengers" in params
    assert params["target_passengers"] == 4  # Cessna 172 default


def test_menu_closes_after_service_selection(menu):
    """Test menu closes after selecting a service."""
    # Setup
    menu._handle_service_availability(
        Message(
            sender="test",
            recipients=["menu"],
            topic="ground.services.available",
            data={
                "at_parking": True,
                "available_services": ["refuel"],
            },
        )
    )
    menu.open()

    # Select service
    menu.select_option("1")

    # Menu should transition to SERVICE_ACTIVE, not CLOSED
    # (menu closes after service completes or is cancelled)
    assert menu.get_state() == "SERVICE_ACTIVE"
    assert menu.get_active_service() == ServiceType.REFUEL


def test_menu_tracks_active_service(menu):
    """Test menu tracks the active service type."""
    # Setup
    menu._handle_service_availability(
        Message(
            sender="test",
            recipients=["menu"],
            topic="ground.services.available",
            data={
                "at_parking": True,
                "available_services": ["refuel", "pushback"],
            },
        )
    )
    menu.open()

    # Initially no active service
    assert menu.get_active_service() is None

    # Select refuel
    menu.select_option("1")

    # Should have active service
    assert menu.get_active_service() == ServiceType.REFUEL


def test_menu_get_state(menu):
    """Test get_state returns correct state."""
    assert menu.get_state() == "CLOSED"

    # Open menu
    menu._handle_service_availability(
        Message(
            sender="test",
            recipients=["menu"],
            topic="ground.services.available",
            data={
                "at_parking": True,
                "available_services": ["refuel"],
            },
        )
    )
    menu.open()

    assert menu.get_state() == "SERVICE_SELECTION"

    # Select service
    menu.select_option("1")

    assert menu.get_state() == "SERVICE_ACTIVE"

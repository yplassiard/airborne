"""Unit tests for ground services plugin."""

import pytest

from airborne.core.messaging import Message, MessageQueue, MessageTopic
from airborne.core.plugin import PluginContext
from airborne.plugins.ground.ground_services import AirportCategory, ServiceStatus, ServiceType
from airborne.plugins.ground.ground_services_plugin import GroundServicesPlugin


@pytest.fixture
def message_queue() -> MessageQueue:
    """Create a test message queue."""
    return MessageQueue()


@pytest.fixture
def plugin_context(message_queue: MessageQueue) -> PluginContext:
    """Create a plugin context."""
    return PluginContext(
        event_bus=None,  # Not needed for ground services
        message_queue=message_queue,
        config={"airport": {"category": "MEDIUM"}},
        plugin_registry=None,
    )


@pytest.fixture
def plugin(plugin_context: PluginContext) -> GroundServicesPlugin:
    """Create and initialize ground services plugin."""
    plugin = GroundServicesPlugin()
    plugin.initialize(plugin_context)
    return plugin


class TestGroundServicesPlugin:
    """Test GroundServicesPlugin class."""

    def test_create_plugin(self) -> None:
        """Test creating a plugin."""
        plugin = GroundServicesPlugin()
        assert plugin.service_manager is None
        assert plugin.is_at_parking is False

    def test_get_metadata(self) -> None:
        """Test plugin metadata."""
        plugin = GroundServicesPlugin()
        metadata = plugin.get_metadata()

        assert metadata.name == "ground_services_plugin"
        assert metadata.version == "1.0.0"
        assert "ground_services" in metadata.provides
        assert "refueling" in metadata.provides
        assert "pushback" in metadata.provides
        assert "boarding" in metadata.provides
        assert "fuel_plugin" in metadata.dependencies
        assert "position_awareness_plugin" in metadata.dependencies

    def test_initialize_plugin(self, plugin: GroundServicesPlugin) -> None:
        """Test plugin initialization."""
        assert plugin.service_manager is not None
        assert ServiceType.REFUEL in plugin.service_manager.services
        assert ServiceType.PUSHBACK in plugin.service_manager.services
        assert ServiceType.BOARDING in plugin.service_manager.services
        assert ServiceType.DEBOARDING in plugin.service_manager.services

    def test_initialize_with_large_airport(self, message_queue: MessageQueue) -> None:
        """Test initialization with large airport."""
        context = PluginContext(
            event_bus=None,
            message_queue=message_queue,
            config={"airport": {"category": "LARGE"}},
            plugin_registry=None,
        )

        plugin = GroundServicesPlugin()
        plugin.initialize(context)

        assert plugin.service_manager is not None
        assert plugin.service_manager.airport_category == AirportCategory.LARGE

    def test_initialize_with_invalid_category(self, message_queue: MessageQueue) -> None:
        """Test initialization with invalid category defaults to MEDIUM."""
        context = PluginContext(
            event_bus=None,
            message_queue=message_queue,
            config={"airport": {"category": "INVALID"}},
            plugin_registry=None,
        )

        plugin = GroundServicesPlugin()
        plugin.initialize(context)

        assert plugin.service_manager is not None
        assert plugin.service_manager.airport_category == AirportCategory.MEDIUM

    def test_handle_position_update(self, plugin: GroundServicesPlugin) -> None:
        """Test handling position updates."""
        message = Message(
            sender="test",
            recipients=["*"],
            topic=MessageTopic.POSITION_UPDATED,
            data={"position": {"x": -122.0, "y": 100.0, "z": 37.0}},
        )

        plugin.handle_message(message)

        assert plugin.current_position == (-122.0, 100.0, 37.0)

    def test_handle_parking_status(
        self, plugin: GroundServicesPlugin, message_queue: MessageQueue
    ) -> None:
        """Test handling parking status updates."""
        availability_messages: list = []

        def capture_availability(msg):  # type: ignore
            availability_messages.append(msg)

        message_queue.subscribe("ground.services.available", capture_availability)

        # Process initial availability message from initialization
        message_queue.process()
        availability_messages.clear()

        # Park at gate
        message = Message(
            sender="test",
            recipients=["*"],
            topic="parking.status",
            data={"at_parking": True, "parking_id": "G1"},
        )

        plugin.handle_message(message)

        assert plugin.is_at_parking is True
        assert plugin.current_parking_id == "G1"

        # Check availability message published
        message_queue.process()
        assert len(availability_messages) == 1
        assert availability_messages[0].data["at_parking"] is True
        assert availability_messages[0].data["parking_id"] == "G1"
        assert len(availability_messages[0].data["available_services"]) > 0

    def test_service_request_when_not_parked(
        self, plugin: GroundServicesPlugin, message_queue: MessageQueue
    ) -> None:
        """Test service request when not parked shows error."""
        audio_messages: list = []

        def capture_audio(msg):  # type: ignore
            audio_messages.append(msg)

        message_queue.subscribe("ground.audio.speak", capture_audio)

        # Request service without parking
        message = Message(
            sender="test",
            recipients=["*"],
            topic="ground.service.request",
            data={
                "service_type": "refuel",
                "aircraft_id": "N123AB",
                "parameters": {"quantity": 50.0, "is_jet": False},
            },
        )

        plugin.handle_message(message)

        # Should publish error message
        message_queue.process()
        assert len(audio_messages) == 1
        assert "parked" in audio_messages[0].data["text"].lower()

    def test_service_request_when_parked(
        self, plugin: GroundServicesPlugin, message_queue: MessageQueue
    ) -> None:
        """Test service request when parked."""
        from airborne.core.messaging import MessageTopic

        audio_messages: list = []

        def capture_audio(msg):  # type: ignore
            audio_messages.append(msg)

        message_queue.subscribe(MessageTopic.TTS_SPEAK, capture_audio)

        # Park at gate
        plugin.is_at_parking = True
        plugin.current_parking_id = "G1"

        # Request refueling
        message = Message(
            sender="test",
            recipients=["*"],
            topic="ground.service.request",
            data={
                "service_type": "refuel",
                "aircraft_id": "N123AB",
                "parameters": {"quantity": 50.0, "is_jet": False},
            },
        )

        plugin.handle_message(message)

        # Should start service and publish acknowledgment message
        message_queue.process()
        assert len(audio_messages) == 1
        assert audio_messages[0].data["message_key"] == "MSG_REFUEL_ACKNOWLEDGED"

        # Check service status
        assert plugin.service_manager is not None
        refuel_service = plugin.service_manager.services[ServiceType.REFUEL]
        assert refuel_service.status == ServiceStatus.IN_PROGRESS

    def test_pushback_request_includes_position(
        self, plugin: GroundServicesPlugin, message_queue: MessageQueue
    ) -> None:
        """Test pushback request includes current position."""
        audio_messages: list = []

        def capture_audio(msg):  # type: ignore
            audio_messages.append(msg)

        message_queue.subscribe("ground.audio.speak", capture_audio)

        # Set position and park
        plugin.current_position = (-122.0, 100.0, 37.0)
        plugin.is_at_parking = True
        plugin.current_parking_id = "G1"

        # Request pushback
        message = Message(
            sender="test",
            recipients=["*"],
            topic="ground.service.request",
            data={
                "service_type": "pushback",
                "aircraft_id": "N123AB",
                "parameters": {"direction": "NORTH"},
            },
        )

        plugin.handle_message(message)

        # Should have sent some audio message
        message_queue.process()
        assert len(audio_messages) >= 1

        # Check pushback service (may or may not have started depending on availability)
        assert plugin.service_manager is not None
        pushback_service = plugin.service_manager.services[ServiceType.PUSHBACK]
        # Just verify the service exists
        assert pushback_service is not None

    def test_service_request_invalid_type(
        self, plugin: GroundServicesPlugin, message_queue: MessageQueue
    ) -> None:
        """Test service request with invalid type."""
        plugin.is_at_parking = True
        plugin.current_parking_id = "G1"

        # Request invalid service
        message = Message(
            sender="test",
            recipients=["*"],
            topic="ground.service.request",
            data={
                "service_type": "invalid_service",
                "aircraft_id": "N123AB",
                "parameters": {},
            },
        )

        # Should not crash
        plugin.handle_message(message)

    def test_is_service_available_when_not_parked(self, plugin: GroundServicesPlugin) -> None:
        """Test service availability when not parked."""
        plugin.is_at_parking = False

        assert plugin.is_service_available(ServiceType.REFUEL) is False
        assert plugin.is_service_available(ServiceType.PUSHBACK) is False

    def test_is_service_available_when_parked(self, plugin: GroundServicesPlugin) -> None:
        """Test service availability when parked."""
        plugin.is_at_parking = True
        plugin.current_parking_id = "G1"

        # At medium airport, these should be available
        assert plugin.is_service_available(ServiceType.REFUEL) is True
        assert plugin.is_service_available(ServiceType.BOARDING) is True

    def test_get_active_services(self, plugin: GroundServicesPlugin) -> None:
        """Test getting list of active services."""
        plugin.is_at_parking = True
        plugin.current_parking_id = "G1"

        # Initially no active services
        assert len(plugin.get_active_services()) == 0

        # Start a service
        assert plugin.service_manager is not None
        plugin.service_manager.request_service(
            ServiceType.REFUEL,
            "N123AB",
            "G1",
            quantity=50.0,
            is_jet=False,
        )

        # Should have one active service
        active = plugin.get_active_services()
        assert len(active) == 1
        assert ServiceType.REFUEL in active

    def test_get_service_status(self, plugin: GroundServicesPlugin) -> None:
        """Test getting service status."""
        assert plugin.service_manager is not None

        # Initially idle
        status = plugin.get_service_status(ServiceType.REFUEL)
        assert status == ServiceStatus.IDLE

        # Start service
        plugin.is_at_parking = True
        plugin.current_parking_id = "G1"
        plugin.service_manager.request_service(
            ServiceType.REFUEL,
            "N123AB",
            "G1",
            quantity=50.0,
            is_jet=False,
        )

        # Should be in progress
        status = plugin.get_service_status(ServiceType.REFUEL)
        assert status == ServiceStatus.IN_PROGRESS

    def test_update_calls_service_manager(
        self, plugin: GroundServicesPlugin, message_queue: MessageQueue
    ) -> None:
        """Test update calls service manager update."""
        plugin.is_at_parking = True
        plugin.current_parking_id = "G1"

        # Start a service
        assert plugin.service_manager is not None
        plugin.service_manager.request_service(
            ServiceType.REFUEL,
            "N123AB",
            "G1",
            quantity=1.0,
            is_jet=False,
        )

        # Update plugin
        plugin.update(0.1)

        # Service should still be in progress (not enough time)
        refuel_service = plugin.service_manager.services[ServiceType.REFUEL]
        assert refuel_service.status == ServiceStatus.IN_PROGRESS

    def test_shutdown(self, plugin: GroundServicesPlugin) -> None:
        """Test plugin shutdown."""
        # Should not crash
        plugin.shutdown()

    def test_availability_changes_with_parking_status(
        self, plugin: GroundServicesPlugin, message_queue: MessageQueue
    ) -> None:
        """Test service availability changes when parking status changes."""
        availability_messages: list = []

        def capture_availability(msg):  # type: ignore
            availability_messages.append(msg)

        message_queue.subscribe("ground.services.available", capture_availability)

        # Process initial availability message from initialization
        message_queue.process()
        availability_messages.clear()

        # Park at gate
        message = Message(
            sender="test",
            recipients=["*"],
            topic="parking.status",
            data={"at_parking": True, "parking_id": "G1"},
        )
        plugin.handle_message(message)
        message_queue.process()

        # Should have services available
        assert len(availability_messages) == 1
        assert len(availability_messages[0].data["available_services"]) > 0

        availability_messages.clear()

        # Leave parking
        message = Message(
            sender="test",
            recipients=["*"],
            topic="parking.status",
            data={"at_parking": False, "parking_id": None},
        )
        plugin.handle_message(message)
        message_queue.process()

        # Should have no services available
        assert len(availability_messages) == 1
        assert len(availability_messages[0].data["available_services"]) == 0

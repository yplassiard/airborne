"""Tests for physics plugin."""

from unittest.mock import Mock

import pytest

from airborne.core.event_bus import EventBus
from airborne.core.messaging import Message, MessageTopic
from airborne.core.plugin import PluginContext, PluginType
from airborne.plugins.core.physics_plugin import PhysicsPlugin


class TestPhysicsPluginMetadata:
    """Test physics plugin metadata."""

    def test_get_metadata(self) -> None:
        """Test getting plugin metadata."""
        plugin = PhysicsPlugin()
        metadata = plugin.get_metadata()

        assert metadata.name == "physics_plugin"
        assert metadata.version == "1.0.0"
        assert metadata.plugin_type == PluginType.CORE
        assert "flight_model" in metadata.provides
        assert "collision_detector" in metadata.provides
        assert metadata.optional is False
        assert metadata.update_priority == 10  # Early update


class TestPhysicsPluginInitialization:
    """Test physics plugin initialization."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def message_queue(self) -> Mock:
        """Create mock message queue."""
        queue = Mock()
        queue.subscribe = Mock()
        queue.publish = Mock()
        queue.unsubscribe = Mock()
        return queue

    @pytest.fixture
    def registry(self) -> Mock:
        """Create mock registry."""
        reg = Mock()
        reg.register = Mock()
        reg.unregister = Mock()
        return reg

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: Mock, registry: Mock) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={
                "physics": {
                    "flight_model": {
                        "type": "simple_6dof",
                        "wing_area_sqft": 174.0,
                        "weight_lbs": 2400.0,
                        "max_thrust_lbs": 180.0,
                    }
                }
            },
            plugin_registry=registry,
        )

    def test_initialize(self, context: PluginContext) -> None:
        """Test physics plugin initialization."""
        plugin = PhysicsPlugin()
        plugin.initialize(context)

        assert plugin.context == context
        assert plugin.flight_model is not None
        assert plugin.collision_detector is not None
        assert plugin.ground_physics is not None

        # Should register three components (flight_model, collision_detector, ground_physics)
        assert context.plugin_registry.register.call_count == 3

        # Should subscribe to four topics (control inputs, terrain, parking_brake, engine_state)
        assert context.message_queue.subscribe.call_count == 4


class TestPhysicsPluginControlInput:
    """Test physics plugin control input handling."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def message_queue(self) -> Mock:
        """Create mock message queue."""
        queue = Mock()
        queue.subscribe = Mock()
        queue.publish = Mock()
        return queue

    @pytest.fixture
    def registry(self) -> Mock:
        """Create mock registry."""
        return Mock()

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: Mock, registry: Mock) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={
                "physics": {
                    "flight_model": {
                        "wing_area_sqft": 174.0,
                        "weight_lbs": 2400.0,
                        "max_thrust_lbs": 180.0,
                    }
                }
            },
            plugin_registry=registry,
        )

    @pytest.fixture
    def plugin(self, context: PluginContext) -> PhysicsPlugin:
        """Create initialized physics plugin."""
        plugin = PhysicsPlugin()
        plugin.initialize(context)
        return plugin

    def test_handle_control_input(self, plugin: PhysicsPlugin) -> None:
        """Test handling control input messages."""
        message = Message(
            sender="input",
            recipients=["*"],
            topic=MessageTopic.CONTROL_INPUT,
            data={
                "pitch": 0.5,
                "roll": -0.3,
                "yaw": 0.1,
                "throttle": 0.8,
                "flaps": 0.0,
                "brakes": 0.0,
                "gear": 1.0,
            },
        )

        plugin.handle_message(message)

        assert plugin.control_inputs.pitch == 0.5
        assert plugin.control_inputs.roll == -0.3
        assert plugin.control_inputs.yaw == 0.1
        assert plugin.control_inputs.throttle == 0.8

    def test_handle_partial_control_input(self, plugin: PhysicsPlugin) -> None:
        """Test handling partial control input (only some axes)."""
        # Set initial values
        plugin.control_inputs.pitch = 0.0
        plugin.control_inputs.throttle = 0.5

        message = Message(
            sender="input",
            recipients=["*"],
            topic=MessageTopic.CONTROL_INPUT,
            data={"pitch": 1.0},  # Only update pitch
        )

        plugin.handle_message(message)

        assert plugin.control_inputs.pitch == 1.0
        assert plugin.control_inputs.throttle == 0.5  # Unchanged


class TestPhysicsPluginUpdate:
    """Test physics plugin update behavior."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def message_queue(self) -> Mock:
        """Create mock message queue."""
        queue = Mock()
        queue.subscribe = Mock()
        queue.publish = Mock()
        return queue

    @pytest.fixture
    def registry(self) -> Mock:
        """Create mock registry."""
        return Mock()

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: Mock, registry: Mock) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={
                "physics": {
                    "flight_model": {
                        "wing_area_sqft": 174.0,
                        "weight_lbs": 2400.0,
                        "max_thrust_lbs": 180.0,
                    }
                }
            },
            plugin_registry=registry,
        )

    @pytest.fixture
    def plugin(self, context: PluginContext) -> PhysicsPlugin:
        """Create initialized physics plugin."""
        plugin = PhysicsPlugin()
        plugin.initialize(context)
        return plugin

    def test_update_publishes_position(self, plugin: PhysicsPlugin) -> None:
        """Test that update publishes position message."""
        plugin.update(0.016)

        # Should publish position update
        plugin.context.message_queue.publish.assert_called()

        # Check message content
        call_args = plugin.context.message_queue.publish.call_args
        message = call_args[0][0]

        assert isinstance(message, Message)
        assert message.topic == MessageTopic.POSITION_UPDATED
        assert "position" in message.data
        assert "velocity" in message.data
        assert "rotation" in message.data


class TestPhysicsPluginTerrainHandling:
    """Test physics plugin terrain handling."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def message_queue(self) -> Mock:
        """Create mock message queue."""
        queue = Mock()
        queue.subscribe = Mock()
        queue.publish = Mock()
        return queue

    @pytest.fixture
    def registry(self) -> Mock:
        """Create mock registry."""
        return Mock()

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: Mock, registry: Mock) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={
                "physics": {
                    "flight_model": {
                        "wing_area_sqft": 174.0,
                        "weight_lbs": 2400.0,
                        "max_thrust_lbs": 180.0,
                    }
                }
            },
            plugin_registry=registry,
        )

    @pytest.fixture
    def plugin(self, context: PluginContext) -> PhysicsPlugin:
        """Create initialized physics plugin."""
        plugin = PhysicsPlugin()
        plugin.initialize(context)
        return plugin

    def test_handle_terrain_update(self, plugin: PhysicsPlugin) -> None:
        """Test handling terrain elevation update."""
        message = Message(
            sender="terrain",
            recipients=["*"],
            topic=MessageTopic.TERRAIN_UPDATED,
            data={"elevation": 1500.0},
        )

        plugin.handle_message(message)

        assert plugin._terrain_elevation == 1500.0


class TestPhysicsPluginShutdown:
    """Test physics plugin shutdown."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def message_queue(self) -> Mock:
        """Create mock message queue."""
        queue = Mock()
        queue.subscribe = Mock()
        queue.publish = Mock()
        queue.unsubscribe = Mock()
        return queue

    @pytest.fixture
    def registry(self) -> Mock:
        """Create mock registry."""
        reg = Mock()
        reg.register = Mock()
        reg.unregister = Mock()
        return reg

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: Mock, registry: Mock) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={
                "physics": {
                    "flight_model": {
                        "wing_area_sqft": 174.0,
                        "weight_lbs": 2400.0,
                        "max_thrust_lbs": 180.0,
                    }
                }
            },
            plugin_registry=registry,
        )

    @pytest.fixture
    def plugin(self, context: PluginContext) -> PhysicsPlugin:
        """Create initialized physics plugin."""
        plugin = PhysicsPlugin()
        plugin.initialize(context)
        return plugin

    def test_shutdown(self, plugin: PhysicsPlugin) -> None:
        """Test physics plugin shutdown."""
        plugin.shutdown()

        # Should unsubscribe from four topics (control inputs, terrain, parking_brake, engine_state)
        assert plugin.context.message_queue.unsubscribe.call_count == 4

        # Should unregister three components (flight_model, collision_detector, ground_physics)
        assert plugin.context.plugin_registry.unregister.call_count == 3

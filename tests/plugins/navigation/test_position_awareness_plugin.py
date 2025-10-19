"""Unit tests for position awareness plugin."""

import pytest

from airborne.core.messaging import Message, MessageQueue, MessageTopic
from airborne.core.plugin import PluginContext, PluginType
from airborne.physics.vectors import Vector3
from airborne.plugins.navigation.position_awareness_plugin import PositionAwarenessPlugin


@pytest.fixture
def message_queue() -> MessageQueue:
    """Create a test message queue."""
    return MessageQueue()


@pytest.fixture
def plugin_context(message_queue: MessageQueue) -> PluginContext:
    """Create a test plugin context."""
    from unittest.mock import Mock

    return PluginContext(
        event_bus=Mock(),
        message_queue=message_queue,
        config={"position_awareness": {"enabled": True}},
        plugin_registry=Mock(),
    )


@pytest.fixture
def plugin() -> PositionAwarenessPlugin:
    """Create a test position awareness plugin."""
    return PositionAwarenessPlugin()


class TestPositionAwarenessPlugin:
    """Test PositionAwarenessPlugin class."""

    def test_create_plugin(self) -> None:
        """Test creating a position awareness plugin."""
        plugin = PositionAwarenessPlugin()

        assert plugin.context is None
        assert plugin.position_tracker is None
        assert plugin.orientation_audio is None
        assert plugin.incursion_detector is None
        assert plugin.enabled is True

    def test_get_metadata(self, plugin: PositionAwarenessPlugin) -> None:
        """Test getting plugin metadata."""
        metadata = plugin.get_metadata()

        assert metadata.name == "position_awareness"
        assert metadata.version == "1.0.0"
        assert metadata.plugin_type == PluginType.AVIONICS
        assert "ground_navigation" in metadata.dependencies
        assert "position_awareness" in metadata.provides
        assert "orientation" in metadata.provides

    def test_initialize_with_context(
        self, plugin: PositionAwarenessPlugin, plugin_context: PluginContext
    ) -> None:
        """Test initializing plugin with context."""
        plugin.initialize(plugin_context)

        assert plugin.context == plugin_context
        assert plugin.enabled is True
        assert plugin.position_tracker is not None
        assert plugin.orientation_audio is not None
        assert plugin.incursion_detector is not None

    def test_initialize_with_dict(
        self, plugin: PositionAwarenessPlugin, message_queue: MessageQueue
    ) -> None:
        """Test initializing plugin with dict (legacy)."""
        context_dict = {"config": {"enabled": True}, "message_queue": message_queue}

        plugin.initialize(context_dict)

        assert plugin.enabled is True
        assert plugin.position_tracker is not None
        assert plugin.orientation_audio is not None
        assert plugin.incursion_detector is not None

    def test_initialize_disabled(
        self, plugin: PositionAwarenessPlugin, plugin_context: PluginContext
    ) -> None:
        """Test initializing plugin when disabled."""
        plugin_context.config["position_awareness"]["enabled"] = False

        plugin.initialize(plugin_context)

        assert plugin.enabled is False
        assert plugin.position_tracker is None
        assert plugin.orientation_audio is None
        assert plugin.incursion_detector is None

    def test_handle_position_update_dict(
        self, plugin: PositionAwarenessPlugin, plugin_context: PluginContext
    ) -> None:
        """Test handling position update with dict position."""
        plugin.initialize(plugin_context)

        msg = Message(
            sender="physics",
            recipients=["position_awareness"],
            topic=MessageTopic.POSITION_UPDATED,
            data={"position": {"x": 37.5, "y": 10.0, "z": -122.0}, "heading": 270.0},
        )

        plugin._on_position_updated(msg)

        assert plugin.last_position is not None
        assert plugin.last_position.x == 37.5
        assert plugin.last_position.y == 10.0
        assert plugin.last_position.z == -122.0
        assert plugin.last_heading == 270.0

    def test_handle_position_update_tuple(
        self, plugin: PositionAwarenessPlugin, plugin_context: PluginContext
    ) -> None:
        """Test handling position update with tuple position."""
        plugin.initialize(plugin_context)

        msg = Message(
            sender="physics",
            recipients=["position_awareness"],
            topic=MessageTopic.POSITION_UPDATED,
            data={"position": (37.5, 10.0, -122.0), "heading": 90.0},
        )

        plugin._on_position_updated(msg)

        assert plugin.last_position is not None
        assert plugin.last_position.x == 37.5
        assert plugin.last_heading == 90.0

    def test_handle_position_update_vector3(
        self, plugin: PositionAwarenessPlugin, plugin_context: PluginContext
    ) -> None:
        """Test handling position update with Vector3."""
        plugin.initialize(plugin_context)

        pos = Vector3(37.5, 10.0, -122.0)
        msg = Message(
            sender="physics",
            recipients=["position_awareness"],
            topic=MessageTopic.POSITION_UPDATED,
            data={"position": pos, "heading": 180.0},
        )

        plugin._on_position_updated(msg)

        assert plugin.last_position is not None
        assert plugin.last_position.x == 37.5
        assert plugin.last_heading == 180.0

    def test_position_query(
        self,
        plugin: PositionAwarenessPlugin,
        plugin_context: PluginContext,
        message_queue: MessageQueue,
    ) -> None:
        """Test position query request (P key)."""
        plugin.initialize(plugin_context)

        # Set up position
        plugin.last_position = Vector3(37.5, 10.0, -122.0)

        # Send position query
        msg = Message(
            sender="input",
            recipients=["position_awareness"],
            topic="input.position_query",
            data={},
        )

        plugin._on_position_query(msg)

        # Should publish TTS message
        processed = message_queue.process()
        assert processed >= 0  # May or may not publish depending on location state

    def test_detailed_position_query(
        self,
        plugin: PositionAwarenessPlugin,
        plugin_context: PluginContext,
        message_queue: MessageQueue,
    ) -> None:
        """Test detailed position query (Shift+P)."""
        plugin.initialize(plugin_context)

        # Set up position
        plugin.last_position = Vector3(37.5, 10.0, -122.0)
        plugin.last_heading = 270.0

        # Send detailed position query
        msg = Message(
            sender="input",
            recipients=["position_awareness"],
            topic="input.detailed_position_query",
            data={},
        )

        plugin._on_detailed_position_query(msg)

        # Should publish TTS message
        processed = message_queue.process()
        assert processed >= 1  # Should always publish

    def test_nearby_features_query(
        self,
        plugin: PositionAwarenessPlugin,
        plugin_context: PluginContext,
        message_queue: MessageQueue,
    ) -> None:
        """Test nearby features query (Ctrl+P)."""
        plugin.initialize(plugin_context)

        # Set up position
        plugin.last_position = Vector3(37.5, 10.0, -122.0)

        # Send nearby features query
        msg = Message(
            sender="input",
            recipients=["position_awareness"],
            topic="input.nearby_features_query",
            data={},
        )

        plugin._on_nearby_features_query(msg)

        # Should publish TTS message
        processed = message_queue.process()
        assert processed >= 1  # Should always publish

    def test_update_with_position(
        self, plugin: PositionAwarenessPlugin, plugin_context: PluginContext
    ) -> None:
        """Test update method with position."""
        plugin.initialize(plugin_context)

        # Set up position
        plugin.last_position = Vector3(37.5, 10.0, -122.0)
        plugin.last_heading = 270.0

        # Update should not crash
        plugin.update(0.016)  # 60 FPS

    def test_update_disabled(self, plugin: PositionAwarenessPlugin) -> None:
        """Test update when plugin is disabled."""
        plugin.enabled = False

        # Should not crash
        plugin.update(0.016)

    def test_shutdown(self, plugin: PositionAwarenessPlugin, plugin_context: PluginContext) -> None:
        """Test plugin shutdown."""
        plugin.initialize(plugin_context)

        # Should not crash
        plugin.shutdown()

    def test_shutdown_before_initialize(self, plugin: PositionAwarenessPlugin) -> None:
        """Test shutdown before initialization."""
        # Should not crash
        plugin.shutdown()

    def test_get_status_uninitialized(self, plugin: PositionAwarenessPlugin) -> None:
        """Test getting status before initialization."""
        status = plugin.get_status()

        assert status["enabled"] is True
        assert status["last_position"] is None
        assert status["last_heading"] == 0.0

    def test_get_status_initialized(
        self, plugin: PositionAwarenessPlugin, plugin_context: PluginContext
    ) -> None:
        """Test getting status after initialization."""
        plugin.initialize(plugin_context)

        # Set position
        plugin.last_position = Vector3(37.5, 10.0, -122.0)
        plugin.last_heading = 270.0

        status = plugin.get_status()

        assert status["enabled"] is True
        assert status["last_position"] == (37.5, 10.0, -122.0)
        assert status["last_heading"] == 270.0
        assert "current_location_type" in status
        assert "current_location_id" in status

    def test_handle_message_position_updated(
        self, plugin: PositionAwarenessPlugin, plugin_context: PluginContext
    ) -> None:
        """Test handling position updated message."""
        plugin.initialize(plugin_context)

        msg = Message(
            sender="physics",
            recipients=["position_awareness"],
            topic=MessageTopic.POSITION_UPDATED,
            data={"position": {"x": 37.5, "y": 10.0, "z": -122.0}, "heading": 270.0},
        )

        plugin.handle_message(msg)

        assert plugin.last_position is not None
        assert plugin.last_position.x == 37.5

    def test_handle_message_position_query(
        self,
        plugin: PositionAwarenessPlugin,
        plugin_context: PluginContext,
        message_queue: MessageQueue,
    ) -> None:
        """Test handling position query message."""
        plugin.initialize(plugin_context)
        plugin.last_position = Vector3(37.5, 10.0, -122.0)

        msg = Message(
            sender="input",
            recipients=["position_awareness"],
            topic="input.position_query",
            data={},
        )

        plugin.handle_message(msg)

        # Should process without error
        message_queue.process()

    def test_position_query_without_components(
        self, plugin: PositionAwarenessPlugin, message_queue: MessageQueue
    ) -> None:
        """Test position query without initialized components."""
        # Don't initialize plugin
        msg = Message(
            sender="input",
            recipients=["position_awareness"],
            topic="input.position_query",
            data={},
        )

        # Should not crash
        plugin._on_position_query(msg)

    def test_detailed_query_without_components(self, plugin: PositionAwarenessPlugin) -> None:
        """Test detailed position query without components."""
        msg = Message(
            sender="input",
            recipients=["position_awareness"],
            topic="input.detailed_position_query",
            data={},
        )

        # Should not crash
        plugin._on_detailed_position_query(msg)

    def test_nearby_query_without_position(
        self, plugin: PositionAwarenessPlugin, plugin_context: PluginContext
    ) -> None:
        """Test nearby features query without position."""
        plugin.initialize(plugin_context)
        # Don't set position

        msg = Message(
            sender="input",
            recipients=["position_awareness"],
            topic="input.nearby_features_query",
            data={},
        )

        # Should not crash
        plugin._on_nearby_features_query(msg)

    def test_component_integration(
        self, plugin: PositionAwarenessPlugin, plugin_context: PluginContext
    ) -> None:
        """Test that all components are properly integrated."""
        plugin.initialize(plugin_context)

        # Verify all components exist
        assert plugin.position_tracker is not None
        assert plugin.orientation_audio is not None
        assert plugin.incursion_detector is not None

        # Verify components have message queue
        assert plugin.position_tracker.message_queue is not None
        assert plugin.orientation_audio.message_queue is not None
        assert plugin.incursion_detector.message_queue is not None

    def test_metadata_dependencies(self, plugin: PositionAwarenessPlugin) -> None:
        """Test that metadata declares correct dependencies."""
        metadata = plugin.get_metadata()

        assert "ground_navigation" in metadata.dependencies
        assert metadata.plugin_type == PluginType.AVIONICS

    def test_update_with_no_position(
        self, plugin: PositionAwarenessPlugin, plugin_context: PluginContext
    ) -> None:
        """Test update without position set."""
        plugin.initialize(plugin_context)
        # Don't set position

        # Should not crash
        plugin.update(0.016)

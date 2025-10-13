"""Tests for terrain plugin."""

from unittest.mock import Mock

import pytest

from airborne.core.event_bus import EventBus
from airborne.core.messaging import Message, MessageTopic
from airborne.core.plugin import PluginContext, PluginType
from airborne.physics.vectors import Vector3
from airborne.plugins.terrain.terrain_plugin import TerrainPlugin


class TestTerrainPluginMetadata:
    """Test terrain plugin metadata."""

    def test_get_metadata(self) -> None:
        """Test getting plugin metadata."""
        plugin = TerrainPlugin()
        metadata = plugin.get_metadata()

        assert metadata.name == "terrain_plugin"
        assert metadata.version == "1.0.0"
        assert metadata.plugin_type == PluginType.CORE
        assert "elevation_service" in metadata.provides
        assert "osm_provider" in metadata.provides
        assert "terrain_collision_detector" in metadata.provides
        assert metadata.optional is False
        assert metadata.update_priority == 15


class TestTerrainPluginInitialization:
    """Test terrain plugin initialization."""

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
        reg.get = Mock(side_effect=KeyError("Not found"))
        return reg

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: Mock, registry: Mock) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={
                "terrain": {
                    "providers": ["simple_flat_earth"],
                    "collision_thresholds": {
                        "warning_ft": 500.0,
                        "caution_ft": 200.0,
                        "critical_ft": 100.0,
                    },
                }
            },
            plugin_registry=registry,
        )

    def test_initialize(self, context: PluginContext) -> None:
        """Test terrain plugin initialization."""
        plugin = TerrainPlugin()
        plugin.initialize(context)

        assert plugin.context == context
        assert plugin.elevation_service is not None
        assert plugin.osm_provider is not None
        assert plugin.collision_detector is not None

        # Should register 3 components
        assert context.plugin_registry.register.call_count == 3

        # Should subscribe to position updates
        assert context.message_queue.subscribe.call_count == 1

    def test_initialize_with_srtm(
        self, event_bus: EventBus, message_queue: Mock, registry: Mock
    ) -> None:
        """Test initialization with SRTM provider."""
        context = PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={"terrain": {"providers": ["srtm"], "srtm_fallback": True}},
            plugin_registry=registry,
        )

        plugin = TerrainPlugin()
        plugin.initialize(context)

        assert plugin.elevation_service is not None
        # Should have SRTM provider added


class TestTerrainPluginPositionUpdates:
    """Test terrain plugin position update handling."""

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
        reg.get = Mock(side_effect=KeyError("Not found"))
        return reg

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: Mock, registry: Mock) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={"terrain": {"providers": ["simple_flat_earth"]}},
            plugin_registry=registry,
        )

    @pytest.fixture
    def plugin(self, context: PluginContext) -> TerrainPlugin:
        """Create and initialize terrain plugin."""
        plugin = TerrainPlugin()
        plugin.initialize(context)
        return plugin

    def test_handle_position_update(self, plugin: TerrainPlugin) -> None:
        """Test handling position update message."""
        message = Message(
            sender="physics",
            recipients=["*"],
            topic=MessageTopic.POSITION_UPDATED,
            data={
                "position": {"x": -122.4194, "y": 100.0, "z": 37.7749},
                "velocity": {"x": 50.0, "y": 0.0, "z": 0.0},
            },
        )

        plugin.handle_message(message)

        assert plugin._current_position is not None
        assert plugin._current_position.x == -122.4194
        assert plugin._current_position.y == 100.0
        assert plugin._current_position.z == 37.7749
        assert plugin._current_altitude == 100.0

    def test_update_publishes_terrain_elevation(self, plugin: TerrainPlugin) -> None:
        """Test that update publishes terrain elevation."""
        # Set position
        plugin._current_position = Vector3(-122.4194, 100.0, 37.7749)

        # Update
        plugin.update(0.016)

        # Should publish terrain update
        assert plugin.context.message_queue.publish.called


class TestTerrainPluginElevationQueries:
    """Test terrain plugin elevation queries."""

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
        reg.get = Mock(side_effect=KeyError("Not found"))
        return reg

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: Mock, registry: Mock) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={"terrain": {"providers": ["simple_flat_earth"]}},
            plugin_registry=registry,
        )

    @pytest.fixture
    def plugin(self, context: PluginContext) -> TerrainPlugin:
        """Create and initialize terrain plugin."""
        plugin = TerrainPlugin()
        plugin.initialize(context)
        return plugin

    def test_get_elevation_at(self, plugin: TerrainPlugin) -> None:
        """Test getting elevation at coordinates."""
        elevation = plugin.get_elevation_at(37.7749, -122.4194)

        assert elevation >= 0.0  # SimpleFlatEarthProvider returns >= 0

    def test_get_features_near(self, plugin: TerrainPlugin) -> None:
        """Test getting features near position."""
        position = Vector3(-122.4194, 0, 37.7749)
        features = plugin.get_features_near(position, radius_nm=50)

        # OSM provider has built-in features
        assert isinstance(features, list)

    def test_check_terrain_collision(self, plugin: TerrainPlugin) -> None:
        """Test checking terrain collision."""
        position = Vector3(-122.4194, 0, 37.7749)
        result = plugin.check_terrain_collision(position, altitude_msl=1000.0)

        assert result is not None
        assert hasattr(result, "is_colliding")
        assert result.is_colliding is False  # At 1000m, should be safe


class TestTerrainPluginConfigChanges:
    """Test terrain plugin configuration changes."""

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
        reg.get = Mock(side_effect=KeyError("Not found"))
        return reg

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: Mock, registry: Mock) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={"terrain": {"providers": ["simple_flat_earth"]}},
            plugin_registry=registry,
        )

    @pytest.fixture
    def plugin(self, context: PluginContext) -> TerrainPlugin:
        """Create and initialize terrain plugin."""
        plugin = TerrainPlugin()
        plugin.initialize(context)
        return plugin

    def test_on_config_changed(self, plugin: TerrainPlugin) -> None:
        """Test handling configuration changes."""
        new_config = {
            "terrain": {
                "collision_thresholds": {
                    "warning_ft": 1000.0,
                    "caution_ft": 500.0,
                    "critical_ft": 200.0,
                }
            }
        }

        plugin.on_config_changed(new_config)

        # Thresholds should be updated
        assert plugin.collision_detector.warning_threshold_ft == 1000.0
        assert plugin.collision_detector.caution_threshold_ft == 500.0
        assert plugin.collision_detector.critical_threshold_ft == 200.0


class TestTerrainPluginShutdown:
    """Test terrain plugin shutdown."""

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
        reg.get = Mock(side_effect=KeyError("Not found"))
        return reg

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: Mock, registry: Mock) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={"terrain": {"providers": ["simple_flat_earth"]}},
            plugin_registry=registry,
        )

    @pytest.fixture
    def plugin(self, context: PluginContext) -> TerrainPlugin:
        """Create and initialize terrain plugin."""
        plugin = TerrainPlugin()
        plugin.initialize(context)
        return plugin

    def test_shutdown(self, plugin: TerrainPlugin) -> None:
        """Test plugin shutdown."""
        plugin.shutdown()

        # Should unsubscribe from messages
        assert plugin.context.message_queue.unsubscribe.called

        # Should unregister components
        assert plugin.context.plugin_registry.unregister.call_count == 3


class TestTerrainPluginIntegration:
    """Test terrain plugin integration scenarios."""

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

        # Simulate physics plugin with collision detector
        physics_collision_detector = Mock()
        physics_collision_detector.elevation_service = None
        reg.get = Mock(return_value=physics_collision_detector)
        return reg

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: Mock, registry: Mock) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={"terrain": {"providers": ["simple_flat_earth"]}},
            plugin_registry=registry,
        )

    def test_updates_physics_collision_detector(self, context: PluginContext) -> None:
        """Test that terrain plugin updates physics collision detector."""
        plugin = TerrainPlugin()
        plugin.initialize(context)

        # Should have updated physics collision detector
        physics_detector = context.plugin_registry.get("collision_detector")
        assert physics_detector.elevation_service is not None

    def test_full_update_cycle(self, context: PluginContext) -> None:
        """Test full update cycle with position updates."""
        plugin = TerrainPlugin()
        plugin.initialize(context)

        # Send position update
        position_msg = Message(
            sender="physics",
            recipients=["*"],
            topic=MessageTopic.POSITION_UPDATED,
            data={
                "position": {"x": -122.4194, "y": 500.0, "z": 37.7749},
                "velocity": {"x": 50.0, "y": 0.0, "z": 0.0},
            },
        )
        plugin.handle_message(position_msg)

        # Update plugin
        plugin.update(0.016)

        # Should publish terrain update
        assert context.message_queue.publish.called

        # Check published message
        call_args = context.message_queue.publish.call_args
        message = call_args[0][0]
        assert message.topic == MessageTopic.TERRAIN_UPDATED
        assert "elevation" in message.data

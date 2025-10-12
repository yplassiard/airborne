"""Tests for the plugin system."""

import pytest

from airborne.core.plugin import (
    IPlugin,
    PluginContext,
    PluginInfo,
    PluginMetadata,
    PluginState,
    PluginType,
)


class TestPluginMetadata:
    """Test suite for PluginMetadata."""

    def test_metadata_creation(self) -> None:
        """Test creating plugin metadata with all fields."""
        metadata = PluginMetadata(
            name="test_plugin",
            version="1.0.0",
            author="Test Author",
            plugin_type=PluginType.CORE,
            dependencies=["dep1", "dep2"],
            provides=["service1"],
            optional=False,
            update_priority=50,
            requires_physics=True,
            requires_network=False,
            url="https://example.com",
            description="Test plugin",
        )

        assert metadata.name == "test_plugin"
        assert metadata.version == "1.0.0"
        assert metadata.author == "Test Author"
        assert metadata.plugin_type == PluginType.CORE
        assert metadata.dependencies == ["dep1", "dep2"]
        assert metadata.provides == ["service1"]
        assert metadata.optional is False
        assert metadata.update_priority == 50
        assert metadata.requires_physics is True
        assert metadata.requires_network is False
        assert metadata.url == "https://example.com"
        assert metadata.description == "Test plugin"

    def test_metadata_validation_empty_name(self) -> None:
        """Test that empty name raises error."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            PluginMetadata(
                name="",
                version="1.0.0",
                author="Test Author",
                plugin_type=PluginType.CORE,
            )

    def test_metadata_validation_empty_version(self) -> None:
        """Test that empty version raises error."""
        with pytest.raises(ValueError, match="version cannot be empty"):
            PluginMetadata(
                name="test",
                version="",
                author="Test Author",
                plugin_type=PluginType.CORE,
            )

    def test_metadata_validation_empty_author(self) -> None:
        """Test that empty author raises error."""
        with pytest.raises(ValueError, match="author cannot be empty"):
            PluginMetadata(
                name="test",
                version="1.0.0",
                author="",
                plugin_type=PluginType.CORE,
            )

    def test_metadata_validation_priority_range(self) -> None:
        """Test that priority must be in valid range."""
        with pytest.raises(ValueError, match="priority must be between"):
            PluginMetadata(
                name="test",
                version="1.0.0",
                author="Test Author",
                plugin_type=PluginType.CORE,
                update_priority=1001,
            )

    def test_metadata_defaults(self) -> None:
        """Test metadata default values."""
        metadata = PluginMetadata(
            name="test", version="1.0.0", author="Test", plugin_type=PluginType.CORE
        )

        assert metadata.dependencies == []
        assert metadata.provides == []
        assert metadata.optional is False
        assert metadata.update_priority == 100
        assert metadata.requires_physics is True
        assert metadata.requires_network is False
        assert metadata.config_schema is None
        assert metadata.url is None
        assert metadata.description is None


class SimpleTestPlugin(IPlugin):
    """Simple test plugin implementation."""

    def __init__(self) -> None:
        """Initialize test plugin."""
        self.initialized = False
        self.updated = False
        self.shut_down = False
        self.messages_received = []

    def get_metadata(self) -> PluginMetadata:
        """Return test metadata."""
        return PluginMetadata(
            name="simple_test",
            version="1.0.0",
            author="Test Suite",
            plugin_type=PluginType.CORE,
            description="Simple test plugin",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize plugin."""
        self.initialized = True
        self.context = context

    def update(self, dt: float) -> None:
        """Update plugin."""
        self.updated = True
        self.last_dt = dt

    def shutdown(self) -> None:
        """Shutdown plugin."""
        self.shut_down = True

    def handle_message(self, message: object) -> None:
        """Handle message."""
        self.messages_received.append(message)


class TestPlugin:
    """Test suite for IPlugin interface."""

    def test_plugin_lifecycle(self) -> None:
        """Test basic plugin lifecycle."""
        plugin = SimpleTestPlugin()
        metadata = plugin.get_metadata()

        assert metadata.name == "simple_test"
        assert not plugin.initialized

        # Initialize
        context = PluginContext(event_bus=None, message_queue=None, config={}, plugin_registry=None)
        plugin.initialize(context)
        assert plugin.initialized

        # Update
        plugin.update(0.016)
        assert plugin.updated
        assert plugin.last_dt == 0.016

        # Handle message
        plugin.handle_message("test_message")
        assert len(plugin.messages_received) == 1

        # Shutdown
        plugin.shutdown()
        assert plugin.shut_down

    def test_plugin_on_error_default(self) -> None:
        """Test default error handling."""
        plugin = SimpleTestPlugin()
        # Should not raise
        plugin.on_error(ValueError("test error"))

    def test_plugin_on_config_changed_default(self) -> None:
        """Test default config change handling."""
        plugin = SimpleTestPlugin()
        # Should not raise
        plugin.on_config_changed({"new": "config"})


class TestPluginInfo:
    """Test suite for PluginInfo."""

    def test_plugin_info_creation(self) -> None:
        """Test creating plugin info."""
        plugin = SimpleTestPlugin()
        metadata = plugin.get_metadata()

        info = PluginInfo(plugin=plugin, metadata=metadata, state=PluginState.LOADED)

        assert info.plugin == plugin
        assert info.metadata == metadata
        assert info.state == PluginState.LOADED
        assert info.error is None

    def test_plugin_info_with_error(self) -> None:
        """Test plugin info with error."""
        plugin = SimpleTestPlugin()
        metadata = plugin.get_metadata()
        error = RuntimeError("Test error")

        info = PluginInfo(plugin=plugin, metadata=metadata, state=PluginState.ERROR, error=error)

        assert info.state == PluginState.ERROR
        assert info.error == error


class TestPluginTypes:
    """Test plugin type enum."""

    def test_plugin_types_exist(self) -> None:
        """Test that all plugin types are defined."""
        assert PluginType.CORE.value == "core"
        assert PluginType.AIRCRAFT_SYSTEM.value == "aircraft"
        assert PluginType.WORLD.value == "world"
        assert PluginType.CABIN.value == "cabin"
        assert PluginType.AVIONICS.value == "avionics"
        assert PluginType.NETWORK.value == "network"


class TestPluginStates:
    """Test plugin state enum."""

    def test_plugin_states_exist(self) -> None:
        """Test that all plugin states are defined."""
        assert PluginState.UNLOADED
        assert PluginState.LOADING
        assert PluginState.LOADED
        assert PluginState.RUNNING
        assert PluginState.ERROR
        assert PluginState.UNLOADING
        assert PluginState.UNLOADED_AFTER_RUN

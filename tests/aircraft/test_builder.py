"""Tests for Aircraft Builder."""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from airborne.aircraft.aircraft import Aircraft
from airborne.aircraft.builder import AircraftBuilder
from airborne.core.event_bus import EventBus
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType
from airborne.core.plugin_loader import PluginLoader


class DummyPlugin(IPlugin):
    """Dummy plugin for testing."""

    def __init__(self, name: str = "dummy") -> None:
        """Initialize dummy plugin."""
        self.name = name

    def get_metadata(self) -> PluginMetadata:
        """Get metadata."""
        return PluginMetadata(
            name=self.name,
            version="1.0.0",
            author="Test",
            plugin_type=PluginType.AIRCRAFT_SYSTEM,
            dependencies=[],
            provides=[],
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize plugin."""

    def update(self, dt: float) -> None:
        """Update plugin."""

    def shutdown(self) -> None:
        """Shutdown plugin."""

    def handle_message(self, message: Mock) -> None:
        """Handle message."""


class TestAircraftBuilderConfig:
    """Test aircraft builder configuration loading."""

    def test_load_config(self) -> None:
        """Test loading YAML configuration."""
        yaml_content = """
aircraft:
  name: "Test Aircraft"
  icao_code: "TEST"

  plugins:
    - plugin: "test_plugin"
      instance_id: "test"
      config:
        value: 42
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = Path(f.name)

        try:
            config = AircraftBuilder.load_config(temp_path)

            assert "aircraft" in config
            assert config["aircraft"]["name"] == "Test Aircraft"
            assert config["aircraft"]["icao_code"] == "TEST"
        finally:
            temp_path.unlink()

    def test_load_nonexistent_config_raises_error(self) -> None:
        """Test loading nonexistent config raises error."""
        with pytest.raises(FileNotFoundError):
            AircraftBuilder.load_config("nonexistent.yaml")

    def test_load_invalid_yaml_raises_error(self) -> None:
        """Test loading invalid YAML raises error."""
        yaml_content = """
aircraft:
  name: "Test"
  invalid: [unclosed list
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="Invalid YAML"):
                AircraftBuilder.load_config(temp_path)
        finally:
            temp_path.unlink()


class TestAircraftBuilderBuild:
    """Test aircraft builder build functionality."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def message_queue(self) -> Mock:
        """Create mock message queue."""
        return Mock()

    @pytest.fixture
    def registry(self) -> Mock:
        """Create mock registry."""
        return Mock()

    @pytest.fixture
    def context(
        self, event_bus: EventBus, message_queue: Mock, registry: Mock
    ) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={},
            plugin_registry=registry,
        )

    @pytest.fixture
    def plugin_loader(self) -> Mock:
        """Create mock plugin loader."""
        loader = Mock(spec=PluginLoader)

        def load_plugin_side_effect(name: str, context: PluginContext) -> IPlugin:
            """Side effect for load_plugin."""
            return DummyPlugin(name)

        loader.load_plugin.side_effect = load_plugin_side_effect
        return loader

    @pytest.fixture
    def builder(self, plugin_loader: Mock, context: PluginContext) -> AircraftBuilder:
        """Create aircraft builder."""
        return AircraftBuilder(plugin_loader, context)

    def test_build_simple_aircraft(self, builder: AircraftBuilder) -> None:
        """Test building a simple aircraft."""
        yaml_content = """
aircraft:
  name: "Test Aircraft"
  icao_code: "TEST"

  plugins:
    - plugin: "test_plugin"
      instance_id: "engine"
      config:
        max_power: 180
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = Path(f.name)

        try:
            aircraft = builder.build(temp_path)

            assert isinstance(aircraft, Aircraft)
            assert aircraft.name == "Test Aircraft"
            assert aircraft.metadata["icao_code"] == "TEST"
            assert aircraft.has_system("engine")
        finally:
            temp_path.unlink()

    def test_build_aircraft_with_multiple_systems(self, builder: AircraftBuilder) -> None:
        """Test building aircraft with multiple systems."""
        yaml_content = """
aircraft:
  name: "Multi-System Aircraft"

  plugins:
    - plugin: "engine_plugin"
      instance_id: "engine"
      config: {}

    - plugin: "fuel_plugin"
      instance_id: "fuel"
      config: {}

    - plugin: "electrical_plugin"
      instance_id: "electrical"
      config: {}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = Path(f.name)

        try:
            aircraft = builder.build(temp_path)

            assert aircraft.has_system("engine")
            assert aircraft.has_system("fuel")
            assert aircraft.has_system("electrical")
            assert len(aircraft.get_all_systems()) == 3
        finally:
            temp_path.unlink()

    def test_build_nonexistent_file_raises_error(self, builder: AircraftBuilder) -> None:
        """Test building from nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            builder.build("nonexistent.yaml")

    def test_build_invalid_config_raises_error(self, builder: AircraftBuilder) -> None:
        """Test building with invalid config raises error."""
        yaml_content = """
not_aircraft:
  name: "Invalid"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="Invalid aircraft config"):
                builder.build(temp_path)
        finally:
            temp_path.unlink()

    def test_build_aircraft_with_no_plugins(self, builder: AircraftBuilder) -> None:
        """Test building aircraft with no plugins."""
        yaml_content = """
aircraft:
  name: "Empty Aircraft"
  plugins: []
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = Path(f.name)

        try:
            aircraft = builder.build(temp_path)

            assert aircraft.name == "Empty Aircraft"
            assert len(aircraft.get_all_systems()) == 0
        finally:
            temp_path.unlink()

    def test_build_passes_plugin_config_to_context(
        self, builder: AircraftBuilder, plugin_loader: Mock
    ) -> None:
        """Test that plugin-specific config is passed to plugin context."""
        yaml_content = """
aircraft:
  name: "Test Aircraft"

  plugins:
    - plugin: "test_plugin"
      instance_id: "engine"
      config:
        max_power_hp: 180
        max_rpm: 2700
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = Path(f.name)

        try:
            builder.build(temp_path)

            # Check that load_plugin was called
            plugin_loader.load_plugin.assert_called_once()

            # Check that plugin context contains the config
            call_args = plugin_loader.load_plugin.call_args
            passed_context = call_args[0][1]
            assert "max_power_hp" in passed_context.config
            assert passed_context.config["max_power_hp"] == 180
        finally:
            temp_path.unlink()

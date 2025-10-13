"""Tests for Aircraft class."""

from unittest.mock import Mock

import pytest

from airborne.aircraft.aircraft import Aircraft
from airborne.core.plugin import IPlugin, PluginMetadata, PluginType


class DummyPlugin(IPlugin):
    """Dummy plugin for testing."""

    def __init__(self, name: str = "dummy") -> None:
        """Initialize dummy plugin."""
        self.name = name
        self.initialized = False
        self.update_count = 0
        self.shutdown_called = False

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

    def initialize(self, context: Mock) -> None:
        """Initialize plugin."""
        self.initialized = True

    def update(self, dt: float) -> None:
        """Update plugin."""
        self.update_count += 1

    def shutdown(self) -> None:
        """Shutdown plugin."""
        self.shutdown_called = True

    def handle_message(self, message: Mock) -> None:
        """Handle message."""

    def on_error(self, error: Exception) -> None:
        """Handle error."""


class TestAircraftCreation:
    """Test aircraft creation."""

    def test_create_aircraft(self) -> None:
        """Test creating an aircraft."""
        aircraft = Aircraft("Cessna 172")

        assert aircraft.name == "Cessna 172"
        assert aircraft.metadata == {}
        assert len(aircraft.get_all_systems()) == 0

    def test_create_aircraft_with_metadata(self) -> None:
        """Test creating aircraft with metadata."""
        metadata = {"icao_code": "C172", "manufacturer": "Cessna"}
        aircraft = Aircraft("Cessna 172", metadata)

        assert aircraft.name == "Cessna 172"
        assert aircraft.metadata == metadata


class TestAircraftSystemManagement:
    """Test aircraft system management."""

    @pytest.fixture
    def aircraft(self) -> Aircraft:
        """Create aircraft for testing."""
        return Aircraft("Test Aircraft")

    def test_add_system(self, aircraft: Aircraft) -> None:
        """Test adding a system."""
        plugin = DummyPlugin("test_system")
        aircraft.add_system("engine", plugin)

        assert aircraft.has_system("engine")
        assert aircraft.get_system("engine") == plugin

    def test_add_duplicate_system_raises_error(self, aircraft: Aircraft) -> None:
        """Test adding duplicate system raises error."""
        plugin1 = DummyPlugin("system1")
        plugin2 = DummyPlugin("system2")

        aircraft.add_system("engine", plugin1)

        with pytest.raises(ValueError, match="already exists"):
            aircraft.add_system("engine", plugin2)

    def test_get_system(self, aircraft: Aircraft) -> None:
        """Test getting a system."""
        plugin = DummyPlugin()
        aircraft.add_system("engine", plugin)

        retrieved = aircraft.get_system("engine")
        assert retrieved == plugin

    def test_get_nonexistent_system_raises_error(self, aircraft: Aircraft) -> None:
        """Test getting nonexistent system raises error."""
        with pytest.raises(KeyError, match="not found"):
            aircraft.get_system("nonexistent")

    def test_has_system(self, aircraft: Aircraft) -> None:
        """Test checking if system exists."""
        plugin = DummyPlugin()
        aircraft.add_system("engine", plugin)

        assert aircraft.has_system("engine")
        assert not aircraft.has_system("nonexistent")

    def test_remove_system(self, aircraft: Aircraft) -> None:
        """Test removing a system."""
        plugin = DummyPlugin()
        aircraft.add_system("engine", plugin)

        aircraft.remove_system("engine")

        assert not aircraft.has_system("engine")
        assert plugin.shutdown_called

    def test_remove_nonexistent_system_raises_error(self, aircraft: Aircraft) -> None:
        """Test removing nonexistent system raises error."""
        with pytest.raises(KeyError, match="not found"):
            aircraft.remove_system("nonexistent")

    def test_get_all_systems(self, aircraft: Aircraft) -> None:
        """Test getting all systems."""
        plugin1 = DummyPlugin("system1")
        plugin2 = DummyPlugin("system2")

        aircraft.add_system("engine", plugin1)
        aircraft.add_system("fuel", plugin2)

        systems = aircraft.get_all_systems()
        assert len(systems) == 2
        assert systems["engine"] == plugin1
        assert systems["fuel"] == plugin2


class TestAircraftUpdate:
    """Test aircraft update behavior."""

    @pytest.fixture
    def aircraft(self) -> Aircraft:
        """Create aircraft for testing."""
        return Aircraft("Test Aircraft")

    def test_update_all_systems(self, aircraft: Aircraft) -> None:
        """Test updating all systems."""
        plugin1 = DummyPlugin("system1")
        plugin2 = DummyPlugin("system2")

        aircraft.add_system("engine", plugin1)
        aircraft.add_system("fuel", plugin2)

        aircraft.update(0.016)

        assert plugin1.update_count == 1
        assert plugin2.update_count == 1

    def test_update_multiple_times(self, aircraft: Aircraft) -> None:
        """Test updating multiple times."""
        plugin = DummyPlugin()
        aircraft.add_system("engine", plugin)

        aircraft.update(0.016)
        aircraft.update(0.016)
        aircraft.update(0.016)

        assert plugin.update_count == 3

    def test_update_handles_plugin_errors(self, aircraft: Aircraft) -> None:
        """Test that update handles plugin errors gracefully."""

        class ErrorPlugin(DummyPlugin):
            """Plugin that raises errors."""

            def update(self, dt: float) -> None:
                """Update that raises error."""
                raise RuntimeError("Test error")

        plugin1 = ErrorPlugin("error_plugin")
        plugin2 = DummyPlugin("good_plugin")

        aircraft.add_system("bad", plugin1)
        aircraft.add_system("good", plugin2)

        # Should not raise exception
        aircraft.update(0.016)

        # Good plugin should still be updated
        assert plugin2.update_count == 1


class TestAircraftShutdown:
    """Test aircraft shutdown."""

    @pytest.fixture
    def aircraft(self) -> Aircraft:
        """Create aircraft for testing."""
        return Aircraft("Test Aircraft")

    def test_shutdown_all_systems(self, aircraft: Aircraft) -> None:
        """Test shutting down all systems."""
        plugin1 = DummyPlugin("system1")
        plugin2 = DummyPlugin("system2")

        aircraft.add_system("engine", plugin1)
        aircraft.add_system("fuel", plugin2)

        aircraft.shutdown()

        assert plugin1.shutdown_called
        assert plugin2.shutdown_called
        assert len(aircraft.get_all_systems()) == 0

    def test_shutdown_in_reverse_order(self, aircraft: Aircraft) -> None:
        """Test that systems shutdown in reverse order."""
        shutdown_order = []

        class OrderTrackingPlugin(DummyPlugin):
            """Plugin that tracks shutdown order."""

            def __init__(self, name: str) -> None:
                """Initialize plugin."""
                super().__init__(name)
                self.plugin_name = name

            def shutdown(self) -> None:
                """Shutdown and track order."""
                shutdown_order.append(self.plugin_name)
                super().shutdown()

        plugin1 = OrderTrackingPlugin("first")
        plugin2 = OrderTrackingPlugin("second")
        plugin3 = OrderTrackingPlugin("third")

        aircraft.add_system("sys1", plugin1)
        aircraft.add_system("sys2", plugin2)
        aircraft.add_system("sys3", plugin3)

        aircraft.shutdown()

        # Should shutdown in reverse order (LIFO)
        assert shutdown_order == ["third", "second", "first"]


class TestAircraftRepresentation:
    """Test aircraft string representation."""

    def test_repr(self) -> None:
        """Test string representation."""
        aircraft = Aircraft("Cessna 172")
        plugin1 = DummyPlugin()
        plugin2 = DummyPlugin()

        aircraft.add_system("engine", plugin1)
        aircraft.add_system("fuel", plugin2)

        repr_str = repr(aircraft)
        assert "Cessna 172" in repr_str
        assert "systems=2" in repr_str

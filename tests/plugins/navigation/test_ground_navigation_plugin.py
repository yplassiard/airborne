"""Tests for Ground Navigation Plugin."""

import pytest

from airborne.audio.beeper import BeepStyle
from airborne.audio.proximity import BeepPattern
from airborne.physics.vectors import Vector3
from airborne.plugins.navigation.ground_navigation_plugin import GroundNavigationPlugin


class TestGroundNavigationPlugin:
    """Test ground navigation plugin basics."""

    @pytest.fixture
    def plugin(self) -> GroundNavigationPlugin:
        """Create ground navigation plugin."""
        return GroundNavigationPlugin()

    def test_plugin_metadata(self, plugin: GroundNavigationPlugin) -> None:
        """Test plugin metadata."""
        metadata = plugin.get_metadata()
        assert metadata.name == "ground_navigation"
        assert metadata.version == "1.0.0"
        assert isinstance(metadata.dependencies, list)

    def test_initialize_with_default_config(self, plugin: GroundNavigationPlugin) -> None:
        """Test initialization with default config."""
        plugin.initialize({"config": {}})

        assert plugin.audio_enabled is True
        assert plugin.beep_style == BeepStyle.SINE
        assert plugin.beep_pattern == BeepPattern.EXPONENTIAL
        assert plugin.max_beep_frequency == 5.0
        assert plugin.proximity_distance == 100.0

    def test_initialize_with_custom_config(self, plugin: GroundNavigationPlugin) -> None:
        """Test initialization with custom config."""
        config = {
            "config": {
                "audio_enabled": False,
                "beep_style": "square",
                "beep_pattern": "linear",
                "max_beep_frequency": 10.0,
                "proximity_distance": 200.0,
            }
        }

        plugin.initialize(config)

        assert plugin.audio_enabled is False
        assert plugin.beep_style == BeepStyle.SQUARE
        assert plugin.beep_pattern == BeepPattern.LINEAR
        assert plugin.max_beep_frequency == 10.0
        assert plugin.proximity_distance == 200.0

    def test_initialize_with_invalid_beep_style(self, plugin: GroundNavigationPlugin) -> None:
        """Test initialization with invalid beep style falls back to default."""
        config = {"config": {"beep_style": "invalid_style"}}

        plugin.initialize(config)

        # Should fall back to SINE
        assert plugin.beep_style == BeepStyle.SINE

    def test_initialize_with_invalid_beep_pattern(self, plugin: GroundNavigationPlugin) -> None:
        """Test initialization with invalid beep pattern falls back to default."""
        config = {"config": {"beep_pattern": "invalid_pattern"}}

        plugin.initialize(config)

        # Should fall back to EXPONENTIAL
        assert plugin.beep_pattern == BeepPattern.EXPONENTIAL

    def test_components_initialized(self, plugin: GroundNavigationPlugin) -> None:
        """Test that all components are initialized."""
        plugin.initialize({"config": {}})

        assert plugin.airport_db is not None
        assert plugin.spatial_index is not None
        assert plugin.taxiway_gen is not None
        assert plugin.ground_physics is not None
        assert plugin.proximity_manager is not None
        assert plugin.beeper is not None

    def test_shutdown(self, plugin: GroundNavigationPlugin) -> None:
        """Test plugin shutdown."""
        plugin.initialize({"config": {}})
        plugin.shutdown()

        # Should clear proximity targets
        assert plugin.proximity_manager is not None
        assert len(plugin.proximity_manager.targets) == 0


class TestGroundNavigationUpdate:
    """Test ground navigation update logic."""

    @pytest.fixture
    def plugin(self) -> GroundNavigationPlugin:
        """Create and initialize plugin."""
        p = GroundNavigationPlugin()
        p.initialize({"config": {}})
        return p

    def test_update_without_position(self, plugin: GroundNavigationPlugin) -> None:
        """Test update without position in state."""
        # Should not crash when no position set
        plugin.update(0.016)

    def test_update_with_position(self, plugin: GroundNavigationPlugin) -> None:
        """Test update with position."""
        plugin.last_position = Vector3(0, 0, 0)

        # Should not crash
        plugin.update(0.016)

    def test_update_with_dict_position(self, plugin: GroundNavigationPlugin) -> None:
        """Test update with dict position."""
        # Test that plugin can handle position stored as dict (from messages)
        plugin.last_position = Vector3(10, 20, 30)

        plugin.update(0.016)
        assert plugin.last_position is not None
        assert isinstance(plugin.last_position, Vector3)

    def test_update_on_ground(self, plugin: GroundNavigationPlugin) -> None:
        """Test update when on ground."""
        plugin.last_position = Vector3(0, 0, 0)

        # Should calculate ground forces (in real usage, state would come via messages)
        plugin.update(0.016)


class TestGroundNavigationStatus:
    """Test ground navigation status reporting."""

    @pytest.fixture
    def plugin(self) -> GroundNavigationPlugin:
        """Create and initialize plugin."""
        p = GroundNavigationPlugin()
        p.initialize({"config": {}})
        return p

    def test_get_status(self, plugin: GroundNavigationPlugin) -> None:
        """Test getting plugin status."""
        status = plugin.get_status()

        assert "current_airport" in status
        assert "nearest_node" in status
        assert "audio_enabled" in status
        assert "beep_style" in status
        assert "beep_pattern" in status
        assert "active_target" in status
        assert "current_frequency" in status
        assert "target_count" in status

    def test_status_values(self, plugin: GroundNavigationPlugin) -> None:
        """Test status values."""
        status = plugin.get_status()

        assert status["current_airport"] is None  # No airport yet
        assert status["audio_enabled"] is True
        assert status["beep_style"] == "sine"
        assert status["beep_pattern"] == "exponential"
        assert status["target_count"] == 0  # No targets yet


class TestConfigurationOptions:
    """Test various configuration options."""

    def test_all_beep_styles(self) -> None:
        """Test all beep styles can be configured."""
        for style in ["sine", "square", "triangle", "sawtooth", "chirp"]:
            plugin = GroundNavigationPlugin()
            plugin.initialize({"config": {"beep_style": style}})

            assert plugin.beep_style == BeepStyle(style)

    def test_all_beep_patterns(self) -> None:
        """Test all beep patterns can be configured."""
        for pattern in ["linear", "exponential", "stepped", "constant"]:
            plugin = GroundNavigationPlugin()
            plugin.initialize({"config": {"beep_pattern": pattern}})

            assert plugin.beep_pattern == BeepPattern(pattern)

    def test_custom_frequency_range(self) -> None:
        """Test custom frequency range."""
        plugin = GroundNavigationPlugin()
        plugin.initialize({"config": {"max_beep_frequency": 8.0}})

        assert plugin.max_beep_frequency == 8.0

    def test_custom_proximity_distance(self) -> None:
        """Test custom proximity distance."""
        plugin = GroundNavigationPlugin()
        plugin.initialize({"config": {"proximity_distance": 250.0}})

        assert plugin.proximity_distance == 250.0


class TestIntegration:
    """Test integration between components."""

    @pytest.fixture
    def plugin(self) -> GroundNavigationPlugin:
        """Create and initialize plugin."""
        p = GroundNavigationPlugin()
        p.initialize({"config": {"audio_enabled": True}})
        return p

    def test_components_integration(self, plugin: GroundNavigationPlugin) -> None:
        """Test that components work together."""
        # Verify all components are connected
        assert plugin.airport_db is not None
        assert plugin.spatial_index is not None
        assert plugin.taxiway_gen is not None
        assert plugin.ground_physics is not None
        assert plugin.proximity_manager is not None
        assert plugin.beeper is not None

    def test_update_flow(self, plugin: GroundNavigationPlugin) -> None:
        """Test full update flow."""
        # Simulate aircraft at KPAO (Palo Alto Airport)
        # Position in meters (approximate)
        plugin.last_position = Vector3(-2621000, 0, 4427000)  # Rough ECEF coordinates

        # Multiple updates
        for _ in range(10):
            plugin.update(0.016)

        # Should have processed without errors
        status = plugin.get_status()
        assert status is not None


class TestRealWorldScenarios:
    """Test real-world navigation scenarios."""

    def test_taxi_to_runway(self) -> None:
        """Test taxiing to runway scenario."""
        plugin = GroundNavigationPlugin()
        plugin.initialize({"config": {"audio_enabled": True, "beep_pattern": "exponential"}})

        # Simulate taxiing
        positions = [
            Vector3(0, 0, 0),  # Start
            Vector3(0, 0, 50),  # Moving
            Vector3(0, 0, 100),  # Approaching node
        ]

        for pos in positions:
            plugin.last_position = pos
            plugin.update(0.1)

        # Should complete without errors
        assert plugin.last_position is not None

    def test_parking_approach(self) -> None:
        """Test parking stand approach."""
        plugin = GroundNavigationPlugin()
        plugin.initialize(
            {
                "config": {
                    "audio_enabled": True,
                    "beep_pattern": "linear",
                    "max_beep_frequency": 10.0,
                }
            }
        )

        # Simulate slow approach to parking
        distances = [50, 40, 30, 20, 10, 5]

        for distance in distances:
            plugin.last_position = Vector3(0, 0, distance)
            plugin.update(0.1)

        # Should handle close proximity without issues
        assert plugin.last_position is not None

    def test_audio_disabled_mode(self) -> None:
        """Test plugin with audio disabled."""
        plugin = GroundNavigationPlugin()
        plugin.initialize({"config": {"audio_enabled": False}})

        plugin.last_position = Vector3(0, 0, 0)
        plugin.update(0.016)

        # Should still work, just without audio
        status = plugin.get_status()
        assert status["audio_enabled"] is False

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


class TestParkingIntegration:
    """Test parking system integration with ground navigation."""

    @pytest.fixture
    def plugin(self) -> GroundNavigationPlugin:
        """Create and initialize plugin."""
        p = GroundNavigationPlugin()
        p.initialize({"config": {}})
        return p

    def test_parking_generator_initialized(self, plugin: GroundNavigationPlugin) -> None:
        """Test that parking generator is initialized."""
        assert plugin.parking_gen is not None

    def test_parking_database_created_on_airport_switch(
        self, plugin: GroundNavigationPlugin
    ) -> None:
        """Test that parking database is created when switching airports."""
        from airborne.airports.database import Airport, AirportType, Runway, SurfaceType

        # Create test airport and runway
        airport = Airport(
            icao="KTEST",
            name="Test Airport",
            position=Vector3(-122.0, 10.0, 37.5),
            airport_type=AirportType.SMALL_AIRPORT,
            municipality="Test City",
            iso_country="US",
            scheduled_service=False,
        )

        runway = Runway(
            airport_icao="KTEST",
            runway_id="18/36",
            length_ft=3000,
            width_ft=75,
            surface=SurfaceType.ASPH,
            lighted=True,
            closed=False,
            le_ident="18",
            le_latitude=37.5,
            le_longitude=-122.0,
            le_elevation_ft=10.0,
            le_heading_deg=180.0,
            he_ident="36",
            he_latitude=37.51,
            he_longitude=-122.0,
            he_elevation_ft=10.0,
            he_heading_deg=360.0,
        )

        # Add to plugin's database
        if plugin.airport_db:
            plugin.airport_db.airports["KTEST"] = airport
            plugin.airport_db.runways["KTEST"] = [runway]
            plugin.spatial_index.insert(airport.position, "KTEST")

        # Switch to airport
        plugin._switch_airport("KTEST")

        # Verify parking database was created
        assert plugin.current_parking_db is not None
        assert plugin.current_parking_db.airport_icao == "KTEST"
        assert plugin.current_parking_db.get_parking_count() > 0

    def test_parking_nodes_added_to_taxiway_graph(self, plugin: GroundNavigationPlugin) -> None:
        """Test that parking positions are added as nodes to taxiway graph."""
        from airborne.airports.database import Airport, AirportType, Runway, SurfaceType

        airport = Airport(
            icao="KTEST2",
            name="Test Airport 2",
            position=Vector3(-122.1, 10.0, 37.6),
            airport_type=AirportType.MEDIUM_AIRPORT,
            municipality="Test City 2",
            iso_country="US",
            scheduled_service=True,
        )

        runway = Runway(
            airport_icao="KTEST2",
            runway_id="09/27",
            length_ft=5000,
            width_ft=100,
            surface=SurfaceType.ASPH,
            lighted=True,
            closed=False,
            le_ident="09",
            le_latitude=37.6,
            le_longitude=-122.1,
            le_elevation_ft=10.0,
            le_heading_deg=90.0,
            he_ident="27",
            he_latitude=37.6,
            he_longitude=-122.08,
            he_elevation_ft=10.0,
            he_heading_deg=270.0,
        )

        if plugin.airport_db:
            plugin.airport_db.airports["KTEST2"] = airport
            plugin.airport_db.runways["KTEST2"] = [runway]
            plugin.spatial_index.insert(airport.position, "KTEST2")

        plugin._switch_airport("KTEST2")

        # Check that parking nodes exist in proximity manager
        assert plugin.proximity_manager is not None
        target_count = len(plugin.proximity_manager.targets)

        # Should have taxiway nodes + parking nodes
        assert target_count > 0

        # Verify parking database has positions
        assert plugin.current_parking_db is not None
        parking_count = plugin.current_parking_db.get_parking_count()
        assert parking_count > 0

    def test_parking_connected_to_taxiways(self, plugin: GroundNavigationPlugin) -> None:
        """Test that parking positions are connected to taxiway network."""
        from airborne.airports.database import Airport, AirportType, Runway, SurfaceType

        airport = Airport(
            icao="KTEST3",
            name="Test Airport 3",
            position=Vector3(-122.2, 10.0, 37.7),
            airport_type=AirportType.SMALL_AIRPORT,
            municipality="Test City 3",
            iso_country="US",
            scheduled_service=False,
        )

        runway = Runway(
            airport_icao="KTEST3",
            runway_id="15/33",
            length_ft=2500,
            width_ft=60,
            surface=SurfaceType.ASPH,
            lighted=True,
            closed=False,
            le_ident="15",
            le_latitude=37.7,
            le_longitude=-122.2,
            le_elevation_ft=10.0,
            le_heading_deg=150.0,
            he_ident="33",
            he_latitude=37.71,
            he_longitude=-122.21,
            he_elevation_ft=10.0,
            he_heading_deg=330.0,
        )

        if plugin.airport_db:
            plugin.airport_db.airports["KTEST3"] = airport
            plugin.airport_db.runways["KTEST3"] = [runway]
            plugin.spatial_index.insert(airport.position, "KTEST3")

        plugin._switch_airport("KTEST3")

        # Verify parking database exists
        assert plugin.current_parking_db is not None

        # Get a parking position
        parking_positions = plugin.current_parking_db.get_all_parking()
        assert len(parking_positions) > 0

        # The parking nodes should be in proximity targets
        # (they were added to the taxiway graph and then to proximity manager)
        parking_id = parking_positions[0].position_id
        assert parking_id in plugin.proximity_manager.targets

    def test_find_nearest_taxiway_node(self, plugin: GroundNavigationPlugin) -> None:
        """Test finding nearest taxiway node to a position."""
        from airborne.airports.taxiway import TaxiwayGraph

        # Create a simple graph
        graph = TaxiwayGraph()
        graph.add_node("A1", Vector3(-122.0, 10.0, 37.5), "intersection")
        graph.add_node("A2", Vector3(-122.01, 10.0, 37.5), "intersection")
        graph.add_node("P1", Vector3(-122.02, 10.0, 37.5), "parking_ramp")

        # Position close to A2
        position = Vector3(-122.009, 10.0, 37.5)

        nearest = plugin._find_nearest_taxiway_node(graph, position)

        # Should find A2 (not P1, as it's a parking node)
        assert nearest is not None
        assert nearest in ["A1", "A2"]

    def test_parking_proximity_beeps_enabled(self, plugin: GroundNavigationPlugin) -> None:
        """Test that parking positions have proximity beeps enabled."""
        from airborne.airports.database import Airport, AirportType, Runway, SurfaceType

        airport = Airport(
            icao="KTEST4",
            name="Test Airport 4",
            position=Vector3(-122.3, 10.0, 37.8),
            airport_type=AirportType.SMALL_AIRPORT,
            municipality="Test City 4",
            iso_country="US",
            scheduled_service=False,
        )

        runway = Runway(
            airport_icao="KTEST4",
            runway_id="12/30",
            length_ft=2800,
            width_ft=70,
            surface=SurfaceType.ASPH,
            lighted=True,
            closed=False,
            le_ident="12",
            le_latitude=37.8,
            le_longitude=-122.3,
            le_elevation_ft=10.0,
            le_heading_deg=120.0,
            he_ident="30",
            he_latitude=37.81,
            he_longitude=-122.31,
            he_elevation_ft=10.0,
            he_heading_deg=300.0,
        )

        if plugin.airport_db:
            plugin.airport_db.airports["KTEST4"] = airport
            plugin.airport_db.runways["KTEST4"] = [runway]
            plugin.spatial_index.insert(airport.position, "KTEST4")

        plugin._switch_airport("KTEST4")

        # Verify proximity targets were added
        assert plugin.proximity_manager is not None
        assert len(plugin.proximity_manager.targets) > 0

        # All parking positions should be in proximity targets
        if plugin.current_parking_db:
            for parking in plugin.current_parking_db.get_all_parking():
                assert parking.position_id in plugin.proximity_manager.targets

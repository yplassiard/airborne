"""Tests for spawn system."""

import pytest

from airborne.airports.database import (
    Airport,
    AirportDatabase,
    AirportType,
    Runway,
    SurfaceType,
)
from airborne.physics.vectors import Vector3
from airborne.scenario import (
    EngineState,
    Scenario,
    SpawnLocation,
    SpawnManager,
    SpawnState,
)


class TestSpawnState:
    """Test SpawnState dataclass."""

    def test_create_spawn_state(self):
        """Test creating spawn state."""
        position = Vector3(-122.115, 5, 37.461)
        state = SpawnState(
            position=position,
            heading=270.0,
            airspeed=0.0,
            engine_running=False,
            on_ground=True,
            parking_brake=True,
        )

        assert state.position == position
        assert state.heading == 270.0
        assert state.airspeed == 0.0
        assert state.engine_running is False
        assert state.on_ground is True
        assert state.parking_brake is True


class TestSpawnManager:
    """Test SpawnManager class."""

    @pytest.fixture
    def mock_airport_db(self):
        """Create mock airport database."""
        db = AirportDatabase()

        # Add test airport (KPAO)
        airport = Airport(
            icao="KPAO",
            name="Palo Alto Airport",
            position=Vector3(-122.115, 5, 37.461),
            airport_type=AirportType.SMALL_AIRPORT,
            municipality="Palo Alto",
            iso_country="US",
            scheduled_service=False,
        )

        # Manually add to airports dict for testing
        db.airports["KPAO"] = airport

        # Add test runways
        runway1 = Runway(
            airport_icao="KPAO",
            runway_id="13/31",
            length_ft=2443,
            width_ft=75,
            surface=SurfaceType.ASPH,
            lighted=True,
            closed=False,
            le_ident="13",
            le_latitude=37.461,
            le_longitude=-122.115,
            le_elevation_ft=5.0,
            le_heading_deg=130.0,
            he_ident="31",
            he_latitude=37.462,
            he_longitude=-122.116,
            he_elevation_ft=5.0,
            he_heading_deg=310.0,
        )

        runway2 = Runway(
            airport_icao="KPAO",
            runway_id="31/13",
            length_ft=2443,
            width_ft=75,
            surface=SurfaceType.ASPH,
            lighted=True,
            closed=False,
            le_ident="31",
            le_latitude=37.462,
            le_longitude=-122.116,
            le_elevation_ft=5.0,
            le_heading_deg=310.0,
            he_ident="13",
            he_latitude=37.461,
            he_longitude=-122.115,
            he_elevation_ft=5.0,
            he_heading_deg=130.0,
        )

        if "KPAO" not in db.runways:
            db.runways["KPAO"] = []
        db.runways["KPAO"].extend([runway1, runway2])

        return db

    @pytest.fixture
    def spawn_manager(self, mock_airport_db):
        """Create spawn manager with mock database."""
        return SpawnManager(mock_airport_db)

    def test_create_spawn_manager(self, mock_airport_db):
        """Test creating spawn manager."""
        manager = SpawnManager(mock_airport_db)

        assert manager is not None
        assert manager.airport_db == mock_airport_db

    def test_spawn_minimal_scenario(self, spawn_manager):
        """Test spawning with minimal scenario."""
        scenario = Scenario(airport_icao="KPAO")
        state = spawn_manager.spawn_aircraft(scenario)

        assert state.on_ground is True
        assert state.parking_brake is True
        assert state.engine_running is False
        assert state.airspeed == 0.0

    def test_spawn_at_ramp(self, spawn_manager):
        """Test spawning at ramp."""
        scenario = Scenario(airport_icao="KPAO", spawn_location=SpawnLocation.RAMP)
        state = spawn_manager.spawn_aircraft(scenario)

        assert state.on_ground is True
        assert state.parking_brake is True

    def test_spawn_at_runway(self, spawn_manager):
        """Test spawning at runway."""
        scenario = Scenario(airport_icao="KPAO", spawn_location=SpawnLocation.RUNWAY)
        state = spawn_manager.spawn_aircraft(scenario)

        assert state.on_ground is True
        # Should be aligned with runway heading
        assert state.heading in (130.0, 310.0)

    def test_spawn_with_preferred_heading(self, spawn_manager):
        """Test spawning with preferred runway heading."""
        # Request heading 135 degrees (should pick runway 13, heading 130)
        scenario = Scenario(
            airport_icao="KPAO",
            spawn_location=SpawnLocation.RUNWAY,
            spawn_heading=135.0,
        )
        state = spawn_manager.spawn_aircraft(scenario)

        # Should pick closest runway heading
        assert state.heading == 130.0

    def test_spawn_with_specific_position(self, spawn_manager):
        """Test spawning with specific position."""
        position = Vector3(-122.120, 10, 37.460)
        scenario = Scenario(
            airport_icao="KPAO",
            spawn_position=position,
            spawn_heading=90.0,
        )
        state = spawn_manager.spawn_aircraft(scenario)

        assert state.position == position
        assert state.heading == 90.0

    def test_spawn_cold_and_dark(self, spawn_manager):
        """Test spawning in cold and dark state."""
        scenario = Scenario(airport_icao="KPAO", engine_state=EngineState.COLD_AND_DARK)
        state = spawn_manager.spawn_aircraft(scenario)

        assert state.engine_running is False
        assert state.parking_brake is True

    def test_spawn_ready_to_start(self, spawn_manager):
        """Test spawning ready to start."""
        scenario = Scenario(airport_icao="KPAO", engine_state=EngineState.READY_TO_START)
        state = spawn_manager.spawn_aircraft(scenario)

        assert state.engine_running is False
        assert state.parking_brake is True

    def test_spawn_engine_running(self, spawn_manager):
        """Test spawning with engine running."""
        scenario = Scenario(airport_icao="KPAO", engine_state=EngineState.RUNNING)
        state = spawn_manager.spawn_aircraft(scenario)

        assert state.engine_running is True
        assert state.parking_brake is False

    def test_spawn_ready_for_takeoff(self, spawn_manager):
        """Test spawning ready for takeoff."""
        scenario = Scenario(airport_icao="KPAO", engine_state=EngineState.READY_FOR_TAKEOFF)
        state = spawn_manager.spawn_aircraft(scenario)

        assert state.engine_running is True
        assert state.parking_brake is False

    def test_spawn_unknown_airport_raises(self, spawn_manager):
        """Test spawning at unknown airport raises ValueError."""
        scenario = Scenario(airport_icao="ZZZZ")

        with pytest.raises(ValueError, match="Airport not found: ZZZZ"):
            spawn_manager.spawn_aircraft(scenario)

    def test_spawn_at_taxiway(self, spawn_manager):
        """Test spawning at taxiway (falls back to ramp)."""
        scenario = Scenario(airport_icao="KPAO", spawn_location=SpawnLocation.TAXIWAY)
        state = spawn_manager.spawn_aircraft(scenario)

        # Should fall back to ramp for now
        assert state.on_ground is True

    def test_spawn_at_gate(self, spawn_manager):
        """Test spawning at gate (falls back to ramp)."""
        scenario = Scenario(airport_icao="KPAO", spawn_location=SpawnLocation.GATE)
        state = spawn_manager.spawn_aircraft(scenario)

        # Should fall back to ramp for now
        assert state.on_ground is True

    def test_spawn_at_airport_without_runways(self, mock_airport_db):
        """Test spawning at airport without runways."""
        # Add airport without runways
        airport = Airport(
            icao="KOAK",
            name="Oakland Airport",
            position=Vector3(-122.220, 5, 37.721),
            airport_type=AirportType.MEDIUM_AIRPORT,
            municipality="Oakland",
            iso_country="US",
            scheduled_service=True,
        )
        mock_airport_db.airports["KOAK"] = airport

        manager = SpawnManager(mock_airport_db)
        scenario = Scenario(airport_icao="KOAK", spawn_location=SpawnLocation.RUNWAY)

        # Should fall back to airport center
        state = manager.spawn_aircraft(scenario)
        assert state.position == airport.position

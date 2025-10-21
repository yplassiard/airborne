"""Tests for scenario system."""

import pytest

from airborne.physics.vectors import Vector3
from airborne.scenario import EngineState, Scenario, ScenarioBuilder, SpawnLocation


class TestSpawnLocation:
    """Test SpawnLocation enum."""

    def test_spawn_location_values(self):
        """Test spawn location enum values."""
        assert SpawnLocation.RAMP.value == "ramp"
        assert SpawnLocation.RUNWAY.value == "runway"
        assert SpawnLocation.TAXIWAY.value == "taxiway"
        assert SpawnLocation.GATE.value == "gate"


class TestEngineState:
    """Test EngineState enum."""

    def test_engine_state_values(self):
        """Test engine state enum values."""
        assert EngineState.COLD_AND_DARK.value == "cold_and_dark"
        assert EngineState.READY_TO_START.value == "ready_to_start"
        assert EngineState.RUNNING.value == "running"
        assert EngineState.READY_FOR_TAKEOFF.value == "ready_for_takeoff"


class TestScenario:
    """Test Scenario dataclass."""

    def test_create_minimal_scenario(self):
        """Test creating scenario with minimal parameters."""
        scenario = Scenario(airport_icao="KPAO")

        assert scenario.airport_icao == "KPAO"
        assert scenario.spawn_location == SpawnLocation.RAMP
        assert scenario.aircraft_type == "cessna172"
        assert scenario.engine_state == EngineState.COLD_AND_DARK

    def test_create_full_scenario(self):
        """Test creating scenario with all parameters."""
        position = Vector3(-122.115, 5, 37.461)
        scenario = Scenario(
            airport_icao="KPAO",
            spawn_location=SpawnLocation.RUNWAY,
            spawn_position=position,
            spawn_heading=270.0,
            aircraft_type="cessna172",
            engine_state=EngineState.READY_FOR_TAKEOFF,
            fuel_percentage=75.0,
            payload_percentage=30.0,
            time_of_day=14,
            weather_preset="clear",
            callsign="N12345",
        )

        assert scenario.airport_icao == "KPAO"
        assert scenario.spawn_location == SpawnLocation.RUNWAY
        assert scenario.spawn_position == position
        assert scenario.spawn_heading == 270.0
        assert scenario.aircraft_type == "cessna172"
        assert scenario.engine_state == EngineState.READY_FOR_TAKEOFF
        assert scenario.fuel_percentage == 75.0
        assert scenario.payload_percentage == 30.0
        assert scenario.time_of_day == 14
        assert scenario.weather_preset == "clear"
        assert scenario.callsign == "N12345"


class TestScenarioBuilder:
    """Test ScenarioBuilder class."""

    def test_create_builder(self):
        """Test creating scenario builder."""
        builder = ScenarioBuilder()

        assert builder is not None

    def test_build_minimal_scenario(self):
        """Test building scenario with minimal config."""
        scenario = ScenarioBuilder().with_airport("KPAO").build()

        assert scenario.airport_icao == "KPAO"
        assert scenario.spawn_location == SpawnLocation.RAMP
        assert scenario.engine_state == EngineState.COLD_AND_DARK

    def test_build_without_airport_raises(self):
        """Test building without airport raises ValueError."""
        builder = ScenarioBuilder()

        with pytest.raises(ValueError, match="Airport ICAO code is required"):
            builder.build()

    def test_with_airport(self):
        """Test setting airport."""
        scenario = ScenarioBuilder().with_airport("kpao").build()

        # Should uppercase the ICAO code
        assert scenario.airport_icao == "KPAO"

    def test_with_spawn_location(self):
        """Test setting spawn location."""
        scenario = (
            ScenarioBuilder().with_airport("KPAO").with_spawn_location(SpawnLocation.RUNWAY).build()
        )

        assert scenario.spawn_location == SpawnLocation.RUNWAY

    def test_with_spawn_position(self):
        """Test setting spawn position."""
        position = Vector3(-122.115, 5, 37.461)
        scenario = ScenarioBuilder().with_airport("KPAO").with_spawn_position(position).build()

        assert scenario.spawn_position == position

    def test_with_spawn_heading(self):
        """Test setting spawn heading."""
        scenario = ScenarioBuilder().with_airport("KPAO").with_spawn_heading(270.0).build()

        assert scenario.spawn_heading == 270.0

    def test_with_spawn_heading_wraps(self):
        """Test spawn heading wraps around 360."""
        scenario = ScenarioBuilder().with_airport("KPAO").with_spawn_heading(450.0).build()

        assert scenario.spawn_heading == 90.0

    def test_with_aircraft(self):
        """Test setting aircraft type."""
        scenario = ScenarioBuilder().with_airport("KPAO").with_aircraft("boeing737").build()

        assert scenario.aircraft_type == "boeing737"

    def test_with_engine_state(self):
        """Test setting engine state."""
        scenario = (
            ScenarioBuilder().with_airport("KPAO").with_engine_state(EngineState.RUNNING).build()
        )

        assert scenario.engine_state == EngineState.RUNNING

    def test_with_fuel(self):
        """Test setting fuel percentage."""
        scenario = ScenarioBuilder().with_airport("KPAO").with_fuel(50.0).build()

        assert scenario.fuel_percentage == 50.0

    def test_with_fuel_clamps_min(self):
        """Test fuel percentage clamps to 0."""
        scenario = ScenarioBuilder().with_airport("KPAO").with_fuel(-10.0).build()

        assert scenario.fuel_percentage == 0.0

    def test_with_fuel_clamps_max(self):
        """Test fuel percentage clamps to 100."""
        scenario = ScenarioBuilder().with_airport("KPAO").with_fuel(150.0).build()

        assert scenario.fuel_percentage == 100.0

    def test_with_payload(self):
        """Test setting payload percentage."""
        scenario = ScenarioBuilder().with_airport("KPAO").with_payload(75.0).build()

        assert scenario.payload_percentage == 75.0

    def test_with_payload_clamps(self):
        """Test payload percentage clamps to 0-100."""
        scenario1 = ScenarioBuilder().with_airport("KPAO").with_payload(-10.0).build()
        scenario2 = ScenarioBuilder().with_airport("KPAO").with_payload(150.0).build()

        assert scenario1.payload_percentage == 0.0
        assert scenario2.payload_percentage == 100.0

    def test_with_time_of_day(self):
        """Test setting time of day."""
        scenario = ScenarioBuilder().with_airport("KPAO").with_time_of_day(18).build()

        assert scenario.time_of_day == 18

    def test_with_time_of_day_wraps(self):
        """Test time of day wraps around 24."""
        scenario = ScenarioBuilder().with_airport("KPAO").with_time_of_day(26).build()

        assert scenario.time_of_day == 2

    def test_with_weather(self):
        """Test setting weather preset."""
        scenario = ScenarioBuilder().with_airport("KPAO").with_weather("thunderstorm").build()

        assert scenario.weather_preset == "thunderstorm"

    def test_with_callsign(self):
        """Test setting callsign."""
        scenario = ScenarioBuilder().with_airport("KPAO").with_callsign("N12345").build()

        assert scenario.callsign == "N12345"

    def test_method_chaining(self):
        """Test fluent API method chaining."""
        scenario = (
            ScenarioBuilder()
            .with_airport("KPAO")
            .with_spawn_location(SpawnLocation.RUNWAY)
            .with_spawn_heading(90.0)
            .with_aircraft("cessna172")
            .with_engine_state(EngineState.READY_FOR_TAKEOFF)
            .with_fuel(100.0)
            .with_payload(50.0)
            .with_time_of_day(12)
            .with_weather("clear")
            .with_callsign("N12345")
            .build()
        )

        assert scenario.airport_icao == "KPAO"
        assert scenario.spawn_location == SpawnLocation.RUNWAY
        assert scenario.spawn_heading == 90.0
        assert scenario.aircraft_type == "cessna172"
        assert scenario.engine_state == EngineState.READY_FOR_TAKEOFF
        assert scenario.fuel_percentage == 100.0
        assert scenario.payload_percentage == 50.0
        assert scenario.time_of_day == 12
        assert scenario.weather_preset == "clear"
        assert scenario.callsign == "N12345"

    def test_from_airport_static_method(self):
        """Test creating scenario from airport ICAO."""
        scenario = ScenarioBuilder.from_airport("KPAO")

        assert scenario.airport_icao == "KPAO"
        assert scenario.spawn_location == SpawnLocation.RAMP
        assert scenario.engine_state == EngineState.COLD_AND_DARK

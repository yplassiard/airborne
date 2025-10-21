"""Integration tests for flight planning system.

Tests the integration between flight plan, callsign, route, and scenario systems.
"""

from airborne.aviation import CallsignGenerator
from airborne.navigation import (
    FlightPlan,
    FlightRules,
    OpenFlightsProvider,
)
from airborne.scenario import ScenarioBuilder, SpawnLocation


class TestFlightPlanningIntegration:
    """Test integration of flight planning components."""

    def test_complete_flight_setup(self):
        """Test creating complete flight setup with all systems."""
        # Generate callsign
        callsign_gen = CallsignGenerator()
        callsign = callsign_gen.generate_ga_callsign("N")

        # Create scenario at departure airport
        scenario = (
            ScenarioBuilder()
            .with_airport("KPAO")
            .with_spawn_location(SpawnLocation.RAMP)
            .with_callsign(callsign.full)
            .build()
        )

        # Create flight plan
        flight_plan = FlightPlan(
            callsign=callsign.full,
            aircraft_type="C172",
            departure="KPAO",
            arrival="KSFO",
            flight_rules=FlightRules.VFR,
        )

        # Verify all systems work together
        assert scenario.airport_icao == flight_plan.departure
        assert scenario.callsign == flight_plan.callsign
        # Flight plan should have required fields
        assert flight_plan.callsign
        assert flight_plan.departure
        assert flight_plan.arrival

    def test_callsign_and_scenario(self):
        """Test callsign generation and scenario creation."""
        # Generate GA callsign
        callsign_gen = CallsignGenerator()
        callsign = callsign_gen.generate_ga_callsign("N")

        # Create scenario
        scenario = (
            ScenarioBuilder()
            .with_airport("KSFO")
            .with_callsign(callsign.full)
            .build()
        )

        assert scenario.callsign == callsign.full
        assert callsign.full.startswith("N")

    def test_route_database_availability(self):
        """Test that route database is available."""
        provider = OpenFlightsProvider()

        # Should have loaded routes
        assert provider.get_route_count() > 0

        # Should have major airports
        airports = provider.get_airports_with_routes()
        assert len(airports) > 0

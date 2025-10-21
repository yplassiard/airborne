"""Tests for flight plan system."""

import pytest

from airborne.airports import Airport, AirportType
from airborne.navigation.flight_plan import (
    AircraftPerformance,
    AltitudeConstraint,
    EnhancedWaypoint,
    FlightPlan,
    FlightPlanManager,
    FlightRules,
    FlightType,
    SpeedConstraint,
)
from airborne.navigation.navdata import Navaid, NavaidType, NavDatabase
from airborne.physics.vectors import Vector3


class TestEnums:
    """Test enum types."""

    def test_flight_rules(self):
        """Test FlightRules enum."""
        assert FlightRules.VFR.value == "VFR"
        assert FlightRules.IFR.value == "IFR"
        assert FlightRules.SVFR.value == "SVFR"

    def test_flight_type(self):
        """Test FlightType enum."""
        assert FlightType.GENERAL_AVIATION.value == "general_aviation"
        assert FlightType.AIRLINE.value == "airline"
        assert FlightType.CARGO.value == "cargo"

    def test_altitude_constraint(self):
        """Test AltitudeConstraint enum."""
        assert AltitudeConstraint.AT.value == "at"
        assert AltitudeConstraint.AT_OR_ABOVE.value == "at_or_above"
        assert AltitudeConstraint.AT_OR_BELOW.value == "at_or_below"
        assert AltitudeConstraint.BETWEEN.value == "between"

    def test_speed_constraint(self):
        """Test SpeedConstraint enum."""
        assert SpeedConstraint.AT.value == "at"
        assert SpeedConstraint.AT_OR_ABOVE.value == "at_or_above"
        assert SpeedConstraint.AT_OR_BELOW.value == "at_or_below"


class TestEnhancedWaypoint:
    """Test EnhancedWaypoint class."""

    def test_create_waypoint(self):
        """Test creating an enhanced waypoint."""
        navaid = Navaid(
            identifier="SFO",
            name="San Francisco VOR",
            type=NavaidType.VOR,
            position=Vector3(-122.3790, 13, 37.6213),
        )

        waypoint = EnhancedWaypoint(
            navaid=navaid,
            altitude_ft=3000,
            altitude_constraint=AltitudeConstraint.AT,
            speed_kts=120,
            speed_constraint=SpeedConstraint.AT_OR_BELOW,
            flyby=True,
        )

        assert waypoint.navaid == navaid
        assert waypoint.altitude_ft == 3000
        assert waypoint.altitude_constraint == AltitudeConstraint.AT
        assert waypoint.speed_kts == 120
        assert waypoint.speed_constraint == SpeedConstraint.AT_OR_BELOW
        assert waypoint.flyby is True

    def test_waypoint_defaults(self):
        """Test waypoint with default values."""
        navaid = Navaid(
            identifier="TEST",
            name="Test Waypoint",
            type=NavaidType.WAYPOINT,
            position=Vector3(-122.0, 0, 37.0),
        )

        waypoint = EnhancedWaypoint(navaid=navaid)

        assert waypoint.altitude_ft is None
        assert waypoint.altitude_constraint is None
        assert waypoint.speed_kts is None
        assert waypoint.speed_constraint is None
        assert waypoint.flyby is True
        assert waypoint.name_override is None

    def test_get_name_with_override(self):
        """Test getting name with override."""
        navaid = Navaid(
            identifier="SFO",
            name="San Francisco VOR",
            type=NavaidType.VOR,
            position=Vector3(-122.3790, 13, 37.6213),
        )

        waypoint = EnhancedWaypoint(navaid=navaid, name_override="Custom Name")

        assert waypoint.get_name() == "Custom Name"

    def test_get_name_without_override(self):
        """Test getting name without override."""
        navaid = Navaid(
            identifier="SFO",
            name="San Francisco VOR",
            type=NavaidType.VOR,
            position=Vector3(-122.3790, 13, 37.6213),
        )

        waypoint = EnhancedWaypoint(navaid=navaid)

        assert waypoint.get_name() == "SFO"

    def test_get_position(self):
        """Test getting waypoint position."""
        position = Vector3(-122.3790, 13, 37.6213)
        navaid = Navaid(
            identifier="SFO",
            name="San Francisco VOR",
            type=NavaidType.VOR,
            position=position,
        )

        waypoint = EnhancedWaypoint(navaid=navaid)

        assert waypoint.get_position() == position

    def test_between_constraint(self):
        """Test waypoint with BETWEEN altitude constraint."""
        navaid = Navaid(
            identifier="TEST",
            name="Test",
            type=NavaidType.WAYPOINT,
            position=Vector3(-122.0, 0, 37.0),
        )

        waypoint = EnhancedWaypoint(
            navaid=navaid,
            altitude_ft=5000,
            altitude_constraint=AltitudeConstraint.BETWEEN,
            min_altitude_ft=4000,
            max_altitude_ft=6000,
        )

        assert waypoint.altitude_constraint == AltitudeConstraint.BETWEEN
        assert waypoint.min_altitude_ft == 4000
        assert waypoint.max_altitude_ft == 6000


class TestFlightPlan:
    """Test FlightPlan class."""

    @pytest.fixture
    def sample_airports(self):
        """Create sample airports for testing."""
        kpao = Airport(
            icao="KPAO",
            name="Palo Alto Airport",
            position=Vector3(-122.1150, 0, 37.4613),
            airport_type=AirportType.SMALL_AIRPORT,
            municipality="Palo Alto",
            iso_country="US",
            scheduled_service=False,
        )

        ksfo = Airport(
            icao="KSFO",
            name="San Francisco International",
            position=Vector3(-122.3750, 0, 37.6190),
            airport_type=AirportType.LARGE_AIRPORT,
            municipality="San Francisco",
            iso_country="US",
            scheduled_service=True,
        )

        return kpao, ksfo

    def test_create_flight_plan(self, sample_airports):
        """Test creating a basic flight plan."""
        kpao, ksfo = sample_airports

        plan = FlightPlan(
            callsign="N12345",
            aircraft_type="C172",
            departure=kpao,
            arrival=ksfo,
            cruise_altitude_ft=3500,
            flight_rules=FlightRules.VFR,
        )

        assert plan.callsign == "N12345"
        assert plan.aircraft_type == "C172"
        assert plan.departure.icao == "KPAO"
        assert plan.arrival.icao == "KSFO"
        assert plan.cruise_altitude_ft == 3500
        assert plan.flight_rules == FlightRules.VFR

    def test_flight_plan_defaults(self, sample_airports):
        """Test flight plan with default values."""
        kpao, ksfo = sample_airports

        plan = FlightPlan(
            callsign="N12345",
            aircraft_type="C172",
            departure=kpao,
            arrival=ksfo,
        )

        assert plan.cruise_altitude_ft == 3500
        assert plan.route_string == "DCT"
        assert plan.flight_rules == FlightRules.VFR
        assert plan.flight_type == FlightType.GENERAL_AVIATION
        assert plan.current_waypoint_index == 0
        assert plan.is_filed_with_atc is False
        assert len(plan.route) == 0

    def test_get_current_waypoint(self, sample_airports):
        """Test getting current waypoint."""
        kpao, ksfo = sample_airports

        navaid1 = Navaid(
            identifier="KPAO",
            name="Palo Alto",
            type=NavaidType.AIRPORT,
            position=kpao.position,
        )
        navaid2 = Navaid(
            identifier="KSFO",
            name="San Francisco",
            type=NavaidType.AIRPORT,
            position=ksfo.position,
        )

        wp1 = EnhancedWaypoint(navaid=navaid1)
        wp2 = EnhancedWaypoint(navaid=navaid2)

        plan = FlightPlan(
            callsign="N12345",
            aircraft_type="C172",
            departure=kpao,
            arrival=ksfo,
            route=[wp1, wp2],
        )

        current = plan.get_current_waypoint()
        assert current == wp1

    def test_get_current_waypoint_empty_route(self, sample_airports):
        """Test getting current waypoint from empty route."""
        kpao, ksfo = sample_airports

        plan = FlightPlan(callsign="N12345", aircraft_type="C172", departure=kpao, arrival=ksfo)

        current = plan.get_current_waypoint()
        assert current is None

    def test_advance_waypoint(self, sample_airports):
        """Test advancing to next waypoint."""
        kpao, ksfo = sample_airports

        navaid1 = Navaid(
            identifier="WP1",
            name="Waypoint 1",
            type=NavaidType.WAYPOINT,
            position=Vector3(-122.0, 0, 37.0),
        )
        navaid2 = Navaid(
            identifier="WP2",
            name="Waypoint 2",
            type=NavaidType.WAYPOINT,
            position=Vector3(-122.0, 0, 37.5),
        )

        wp1 = EnhancedWaypoint(navaid=navaid1)
        wp2 = EnhancedWaypoint(navaid=navaid2)

        plan = FlightPlan(
            callsign="N12345",
            aircraft_type="C172",
            departure=kpao,
            arrival=ksfo,
            route=[wp1, wp2],
        )

        assert plan.current_waypoint_index == 0
        advanced = plan.advance_waypoint()
        assert advanced is True
        assert plan.current_waypoint_index == 1

    def test_advance_waypoint_at_end(self, sample_airports):
        """Test advancing waypoint when at end of route."""
        kpao, ksfo = sample_airports

        navaid = Navaid(
            identifier="WP1",
            name="Waypoint 1",
            type=NavaidType.WAYPOINT,
            position=Vector3(-122.0, 0, 37.0),
        )

        wp = EnhancedWaypoint(navaid=navaid)

        plan = FlightPlan(
            callsign="N12345",
            aircraft_type="C172",
            departure=kpao,
            arrival=ksfo,
            route=[wp],
        )

        advanced = plan.advance_waypoint()
        assert advanced is False
        assert plan.current_waypoint_index == 0

    def test_is_complete(self, sample_airports):
        """Test checking if flight plan is complete."""
        kpao, ksfo = sample_airports

        navaid = Navaid(
            identifier="WP1",
            name="Waypoint 1",
            type=NavaidType.WAYPOINT,
            position=Vector3(-122.0, 0, 37.0),
        )

        wp = EnhancedWaypoint(navaid=navaid)

        plan = FlightPlan(
            callsign="N12345",
            aircraft_type="C172",
            departure=kpao,
            arrival=ksfo,
            route=[wp],
        )

        assert plan.is_complete() is False

        plan.current_waypoint_index = 1
        assert plan.is_complete() is True

    def test_get_total_distance_nm(self, sample_airports):
        """Test calculating total route distance."""
        kpao, ksfo = sample_airports

        navaid1 = Navaid(
            identifier="KPAO",
            name="Palo Alto",
            type=NavaidType.AIRPORT,
            position=kpao.position,
        )
        navaid2 = Navaid(
            identifier="KSFO",
            name="San Francisco",
            type=NavaidType.AIRPORT,
            position=ksfo.position,
        )

        wp1 = EnhancedWaypoint(navaid=navaid1)
        wp2 = EnhancedWaypoint(navaid=navaid2)

        plan = FlightPlan(
            callsign="N12345",
            aircraft_type="C172",
            departure=kpao,
            arrival=ksfo,
            route=[wp1, wp2],
        )

        distance = plan.get_total_distance_nm()
        # KPAO to KSFO is approximately 10-16 NM
        assert 10 <= distance <= 16

    def test_get_total_distance_empty_route(self, sample_airports):
        """Test distance calculation for empty route."""
        kpao, ksfo = sample_airports

        plan = FlightPlan(callsign="N12345", aircraft_type="C172", departure=kpao, arrival=ksfo)

        distance = plan.get_total_distance_nm()
        assert distance == 0.0


class TestAircraftPerformance:
    """Test AircraftPerformance class."""

    def test_create_performance(self):
        """Test creating aircraft performance."""
        perf = AircraftPerformance(
            cruise_speed_kts=120,
            climb_rate_fpm=700,
            descent_rate_fpm=500,
            fuel_flow_gph=8.5,
            taxi_fuel_gal=1.0,
            reserve_fuel_gal=5.0,
        )

        assert perf.cruise_speed_kts == 120
        assert perf.climb_rate_fpm == 700
        assert perf.descent_rate_fpm == 500
        assert perf.fuel_flow_gph == 8.5
        assert perf.taxi_fuel_gal == 1.0
        assert perf.reserve_fuel_gal == 5.0

    def test_performance_defaults(self):
        """Test performance with default values."""
        perf = AircraftPerformance()

        assert perf.cruise_speed_kts == 120.0
        assert perf.climb_rate_fpm == 700.0
        assert perf.descent_rate_fpm == 500.0
        assert perf.fuel_flow_gph == 8.5
        assert perf.taxi_fuel_gal == 1.0
        assert perf.reserve_fuel_gal == 5.0


class TestFlightPlanManager:
    """Test FlightPlanManager class."""

    @pytest.fixture
    def nav_db(self):
        """Create navigation database for testing."""
        return NavDatabase()

    @pytest.fixture
    def sample_airports(self):
        """Create sample airports for testing."""
        kpao = Airport(
            icao="KPAO",
            name="Palo Alto Airport",
            position=Vector3(-122.1150, 2.1, 37.4613),  # 2.1m elevation
            airport_type=AirportType.SMALL_AIRPORT,
            municipality="Palo Alto",
            iso_country="US",
            scheduled_service=False,
        )

        ksfo = Airport(
            icao="KSFO",
            name="San Francisco International",
            position=Vector3(-122.3750, 4.0, 37.6190),  # 4.0m elevation
            airport_type=AirportType.LARGE_AIRPORT,
            municipality="San Francisco",
            iso_country="US",
            scheduled_service=True,
        )

        return kpao, ksfo

    def test_create_manager(self, nav_db):
        """Test creating flight plan manager."""
        manager = FlightPlanManager(nav_db)

        assert manager.nav_db == nav_db

    def test_create_direct_route(self, nav_db, sample_airports):
        """Test creating a direct route."""
        manager = FlightPlanManager(nav_db)
        kpao, ksfo = sample_airports

        plan = manager.create_direct_route(kpao, ksfo, 3500, "C172", "N12345")

        assert plan.callsign == "N12345"
        assert plan.aircraft_type == "C172"
        assert plan.departure.icao == "KPAO"
        assert plan.arrival.icao == "KSFO"
        assert plan.cruise_altitude_ft == 3500
        assert plan.route_string == "DCT"
        assert plan.flight_rules == FlightRules.VFR
        assert len(plan.route) == 2
        assert plan.route[0].navaid.identifier == "KPAO"
        assert plan.route[1].navaid.identifier == "KSFO"

    def test_calculate_performance(self, nav_db, sample_airports):
        """Test calculating flight plan performance."""
        manager = FlightPlanManager(nav_db)
        kpao, ksfo = sample_airports

        plan = manager.create_direct_route(kpao, ksfo, 3500, "C172")
        perf = AircraftPerformance(
            cruise_speed_kts=120,
            climb_rate_fpm=700,
            descent_rate_fpm=500,
            fuel_flow_gph=8.5,
            taxi_fuel_gal=1.0,
            reserve_fuel_gal=5.0,
        )

        plan = manager.calculate_performance(plan, perf)

        # Check that performance was calculated
        assert plan.estimated_time_enroute_min > 0
        assert plan.estimated_fuel_required_gal > 0

        # Rough sanity checks (10-16 NM at 120 kts = ~5-8 min cruise)
        # Plus climb/descent time
        assert plan.estimated_time_enroute_min > 5
        assert plan.estimated_time_enroute_min < 30

        # Fuel should include taxi + reserve + flight time
        assert plan.estimated_fuel_required_gal > 6  # At least taxi + reserve

    def test_validate_route_valid(self, nav_db, sample_airports):
        """Test validating a valid flight plan."""
        manager = FlightPlanManager(nav_db)
        kpao, ksfo = sample_airports

        plan = manager.create_direct_route(kpao, ksfo, 3500, "C172")
        errors = manager.validate_route(plan)

        assert len(errors) == 0

    def test_validate_route_no_waypoints(self, nav_db, sample_airports):
        """Test validating plan with no waypoints."""
        manager = FlightPlanManager(nav_db)
        kpao, ksfo = sample_airports

        plan = FlightPlan(callsign="N12345", aircraft_type="C172", departure=kpao, arrival=ksfo)

        errors = manager.validate_route(plan)

        assert len(errors) > 0
        assert any("no waypoints" in err.lower() for err in errors)

    def test_validate_route_single_waypoint(self, nav_db, sample_airports):
        """Test validating plan with only one waypoint."""
        manager = FlightPlanManager(nav_db)
        kpao, ksfo = sample_airports

        navaid = Navaid(
            identifier="TEST",
            name="Test",
            type=NavaidType.WAYPOINT,
            position=Vector3(-122.0, 0, 37.0),
        )
        wp = EnhancedWaypoint(navaid=navaid)

        plan = FlightPlan(
            callsign="N12345",
            aircraft_type="C172",
            departure=kpao,
            arrival=ksfo,
            route=[wp],
        )

        errors = manager.validate_route(plan)

        assert len(errors) > 0
        assert any("at least 2" in err.lower() for err in errors)

    def test_validate_route_negative_altitude(self, nav_db, sample_airports):
        """Test validating plan with negative cruise altitude."""
        manager = FlightPlanManager(nav_db)
        kpao, ksfo = sample_airports

        plan = manager.create_direct_route(kpao, ksfo, -1000, "C172")
        errors = manager.validate_route(plan)

        assert len(errors) > 0
        assert any("negative" in err.lower() for err in errors)

    def test_validate_route_excessive_altitude(self, nav_db, sample_airports):
        """Test validating plan with excessive altitude."""
        manager = FlightPlanManager(nav_db)
        kpao, ksfo = sample_airports

        plan = manager.create_direct_route(kpao, ksfo, 70000, "C172")
        errors = manager.validate_route(plan)

        assert len(errors) > 0
        assert any("exceeds maximum" in err.lower() for err in errors)

    def test_validate_route_duplicate_waypoints(self, nav_db, sample_airports):
        """Test validating plan with duplicate consecutive waypoints."""
        manager = FlightPlanManager(nav_db)
        kpao, ksfo = sample_airports

        navaid = Navaid(
            identifier="TEST",
            name="Test",
            type=NavaidType.WAYPOINT,
            position=Vector3(-122.0, 0, 37.0),
        )

        wp1 = EnhancedWaypoint(navaid=navaid)
        wp2 = EnhancedWaypoint(navaid=navaid)  # Duplicate

        plan = FlightPlan(
            callsign="N12345",
            aircraft_type="C172",
            departure=kpao,
            arrival=ksfo,
            route=[wp1, wp2],
            cruise_altitude_ft=3500,
        )

        errors = manager.validate_route(plan)

        assert len(errors) > 0
        assert any("duplicate" in err.lower() for err in errors)

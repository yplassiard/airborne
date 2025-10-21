"""Flight plan management system.

This module provides comprehensive flight planning with route management,
performance calculations, and altitude/speed constraints.

Typical usage:
    from airborne.navigation import FlightPlanManager

    manager = FlightPlanManager(nav_db, airport_db)
    plan = manager.create_direct_route(
        departure=kpao,
        arrival=ksfo,
        cruise_alt_ft=3500,
        aircraft_type="C172"
    )
"""

import logging
from dataclasses import dataclass, field
from enum import Enum

from airborne.airports import Airport
from airborne.navigation.navdata import Navaid, NavaidType, NavDatabase
from airborne.physics.vectors import Vector3

logger = logging.getLogger(__name__)


class FlightRules(Enum):
    """Flight rules type.

    Attributes:
        VFR: Visual Flight Rules
        IFR: Instrument Flight Rules
        SVFR: Special VFR
    """

    VFR = "VFR"
    IFR = "IFR"
    SVFR = "SVFR"


class FlightType(Enum):
    """Flight type classification.

    Attributes:
        GENERAL_AVIATION: General aviation flight
        AIRLINE: Scheduled airline flight
        CARGO: Cargo flight
        MILITARY: Military flight
        TRAINING: Training flight
    """

    GENERAL_AVIATION = "general_aviation"
    AIRLINE = "airline"
    CARGO = "cargo"
    MILITARY = "military"
    TRAINING = "training"


class AltitudeConstraint(Enum):
    """Altitude constraint type at waypoint.

    Attributes:
        AT: Must be at exact altitude
        AT_OR_ABOVE: Must be at or above altitude
        AT_OR_BELOW: Must be at or below altitude
        BETWEEN: Must be between min and max altitude
    """

    AT = "at"
    AT_OR_ABOVE = "at_or_above"
    AT_OR_BELOW = "at_or_below"
    BETWEEN = "between"


class SpeedConstraint(Enum):
    """Speed constraint type at waypoint.

    Attributes:
        AT: Must be at exact speed
        AT_OR_ABOVE: Must be at or above speed
        AT_OR_BELOW: Must be at or below speed
    """

    AT = "at"
    AT_OR_ABOVE = "at_or_above"
    AT_OR_BELOW = "at_or_below"


@dataclass
class EnhancedWaypoint:
    """Enhanced waypoint with constraints and metadata.

    Extends basic waypoint with altitude/speed constraints and
    flyby/flyover information for precision navigation.

    Attributes:
        navaid: Reference to navaid (VOR, waypoint, airport, etc.)
        altitude_ft: Target altitude in feet MSL
        altitude_constraint: Type of altitude constraint
        speed_kts: Target speed in knots
        speed_constraint: Type of speed constraint
        flyby: True for flyby turn, False for flyover
        name_override: Override display name (optional)
        min_altitude_ft: Minimum altitude for BETWEEN constraint
        max_altitude_ft: Maximum altitude for BETWEEN constraint

    Examples:
        >>> waypoint = EnhancedWaypoint(
        ...     navaid=sfo_vor,
        ...     altitude_ft=3000,
        ...     altitude_constraint=AltitudeConstraint.AT,
        ...     speed_kts=120,
        ...     flyby=True
        ... )
    """

    navaid: Navaid
    altitude_ft: float | None = None
    altitude_constraint: AltitudeConstraint | None = None
    speed_kts: float | None = None
    speed_constraint: SpeedConstraint | None = None
    flyby: bool = True
    name_override: str | None = None
    min_altitude_ft: float | None = None
    max_altitude_ft: float | None = None

    def get_name(self) -> str:
        """Get waypoint display name.

        Returns:
            Override name if set, otherwise navaid identifier
        """
        return self.name_override if self.name_override else self.navaid.identifier

    def get_position(self) -> Vector3:
        """Get waypoint position.

        Returns:
            Position vector from navaid
        """
        return self.navaid.position


@dataclass
class FlightPlan:
    """Complete flight plan with metadata and route.

    Comprehensive flight plan including departure/arrival airports,
    route waypoints, performance data, and flight rules.

    Attributes:
        callsign: Aircraft callsign
        aircraft_type: Aircraft type code (e.g., "C172", "B738")
        departure: Departure airport
        arrival: Arrival airport
        alternate: Alternate airport (optional)
        route: List of enhanced waypoints defining the route
        cruise_altitude_ft: Planned cruise altitude in feet MSL
        route_string: Route description string (e.g., "DCT SFO V25 OAK DCT")
        sid: Standard Instrument Departure name (optional)
        star: Standard Terminal Arrival Route name (optional)
        estimated_time_enroute_min: Estimated time in minutes
        estimated_fuel_required_gal: Estimated fuel in gallons
        flight_rules: VFR or IFR
        flight_type: Type of flight operation
        remarks: Free text remarks
        current_waypoint_index: Index of current active waypoint
        is_filed_with_atc: Whether plan is filed with ATC

    Examples:
        >>> plan = FlightPlan(
        ...     callsign="N12345",
        ...     aircraft_type="C172",
        ...     departure=kpao,
        ...     arrival=ksfo,
        ...     route=[waypoint1, waypoint2],
        ...     cruise_altitude_ft=3500,
        ...     flight_rules=FlightRules.VFR
        ... )
    """

    callsign: str
    aircraft_type: str
    departure: Airport
    arrival: Airport
    route: list[EnhancedWaypoint] = field(default_factory=list)
    cruise_altitude_ft: float = 3500
    alternate: Airport | None = None
    route_string: str = "DCT"
    sid: str | None = None
    star: str | None = None
    estimated_time_enroute_min: float = 0.0
    estimated_fuel_required_gal: float = 0.0
    flight_rules: FlightRules = FlightRules.VFR
    flight_type: FlightType = FlightType.GENERAL_AVIATION
    remarks: str = ""
    current_waypoint_index: int = 0
    is_filed_with_atc: bool = False

    def get_current_waypoint(self) -> EnhancedWaypoint | None:
        """Get current active waypoint.

        Returns:
            Current waypoint or None if complete
        """
        if 0 <= self.current_waypoint_index < len(self.route):
            return self.route[self.current_waypoint_index]
        return None

    def advance_waypoint(self) -> bool:
        """Advance to next waypoint.

        Returns:
            True if advanced, False if at end of flight plan
        """
        if self.current_waypoint_index < len(self.route) - 1:
            self.current_waypoint_index += 1
            return True
        return False

    def is_complete(self) -> bool:
        """Check if flight plan is complete.

        Returns:
            True if all waypoints passed
        """
        return self.current_waypoint_index >= len(self.route)

    def get_total_distance_nm(self) -> float:
        """Calculate total route distance.

        Returns:
            Total distance in nautical miles
        """
        if len(self.route) < 2:
            return 0.0

        total_distance = 0.0
        for i in range(len(self.route) - 1):
            pos1 = self.route[i].get_position()
            pos2 = self.route[i + 1].get_position()
            total_distance += NavDatabase._haversine_distance_nm(pos1, pos2)

        return total_distance


@dataclass
class AircraftPerformance:
    """Aircraft performance parameters for flight planning.

    Attributes:
        cruise_speed_kts: Cruise speed in knots TAS
        climb_rate_fpm: Climb rate in feet per minute
        descent_rate_fpm: Descent rate in feet per minute
        fuel_flow_gph: Fuel flow in gallons per hour
        taxi_fuel_gal: Fuel for taxi operations
        reserve_fuel_gal: Reserve fuel requirement

    Examples:
        >>> c172_perf = AircraftPerformance(
        ...     cruise_speed_kts=120,
        ...     climb_rate_fpm=700,
        ...     fuel_flow_gph=8.5
        ... )
    """

    cruise_speed_kts: float = 120.0
    climb_rate_fpm: float = 700.0
    descent_rate_fpm: float = 500.0
    fuel_flow_gph: float = 8.5
    taxi_fuel_gal: float = 1.0
    reserve_fuel_gal: float = 5.0


class FlightPlanManager:
    """Flight plan creation and management.

    Provides methods for creating, validating, and calculating
    performance for flight plans.

    Attributes:
        nav_db: Navigation database for waypoint lookups

    Examples:
        >>> manager = FlightPlanManager(nav_db)
        >>> plan = manager.create_direct_route(kpao, ksfo, 3500, "C172")
    """

    def __init__(self, nav_db: NavDatabase) -> None:
        """Initialize flight plan manager.

        Args:
            nav_db: Navigation database instance
        """
        self.nav_db = nav_db
        logger.info("Initialized flight plan manager")

    def create_direct_route(
        self,
        departure: Airport,
        arrival: Airport,
        cruise_alt_ft: float,
        aircraft_type: str,
        callsign: str = "N12345",
    ) -> FlightPlan:
        """Create a direct route between two airports.

        Args:
            departure: Departure airport
            arrival: Arrival airport
            cruise_alt_ft: Cruise altitude in feet MSL
            aircraft_type: Aircraft type code
            callsign: Aircraft callsign

        Returns:
            FlightPlan with direct route

        Examples:
            >>> plan = manager.create_direct_route(kpao, ksfo, 3500, "C172")
        """
        # Create navaids from airports
        dep_navaid = Navaid(
            identifier=departure.icao,
            name=departure.name,
            type=NavaidType.AIRPORT,
            position=departure.position,
        )

        arr_navaid = Navaid(
            identifier=arrival.icao,
            name=arrival.name,
            type=NavaidType.AIRPORT,
            position=arrival.position,
        )

        # Create waypoints
        dep_waypoint = EnhancedWaypoint(
            navaid=dep_navaid,
            altitude_ft=departure.position.y * 3.28084,  # Convert m to ft
            speed_kts=0,
            flyby=False,
        )

        arr_waypoint = EnhancedWaypoint(
            navaid=arr_navaid,
            altitude_ft=arrival.position.y * 3.28084,  # Convert m to ft
            speed_kts=80,
            flyby=False,
        )

        route = [dep_waypoint, arr_waypoint]

        plan = FlightPlan(
            callsign=callsign,
            aircraft_type=aircraft_type,
            departure=departure,
            arrival=arrival,
            route=route,
            cruise_altitude_ft=cruise_alt_ft,
            route_string="DCT",
            flight_rules=FlightRules.VFR,
        )

        logger.info(
            f"Created direct route: {departure.icao} -> {arrival.icao} "
            f"({plan.get_total_distance_nm():.1f} NM)"
        )

        return plan

    def calculate_performance(
        self, plan: FlightPlan, aircraft_perf: AircraftPerformance
    ) -> FlightPlan:
        """Calculate performance data for flight plan.

        Updates the flight plan with estimated time and fuel based on
        aircraft performance parameters.

        Args:
            plan: Flight plan to calculate
            aircraft_perf: Aircraft performance data

        Returns:
            Updated flight plan with performance data

        Examples:
            >>> plan = manager.calculate_performance(plan, c172_perf)
        """
        distance_nm = plan.get_total_distance_nm()

        # Calculate time enroute (simple cruise calculation)
        # Time = Distance / Speed (in hours), convert to minutes
        time_hours = distance_nm / aircraft_perf.cruise_speed_kts
        time_minutes = time_hours * 60

        # Add climb/descent time (rough estimate)
        climb_time_min = plan.cruise_altitude_ft / aircraft_perf.climb_rate_fpm
        descent_time_min = plan.cruise_altitude_ft / aircraft_perf.descent_rate_fpm

        total_time_min = time_minutes + climb_time_min + descent_time_min

        # Calculate fuel (Time * Fuel Flow + Taxi + Reserve)
        fuel_gal = (
            (total_time_min / 60) * aircraft_perf.fuel_flow_gph
            + aircraft_perf.taxi_fuel_gal
            + aircraft_perf.reserve_fuel_gal
        )

        plan.estimated_time_enroute_min = total_time_min
        plan.estimated_fuel_required_gal = fuel_gal

        logger.info(f"Performance calculated: {total_time_min:.1f} min, {fuel_gal:.1f} gal")

        return plan

    def validate_route(self, plan: FlightPlan) -> list[str]:
        """Validate flight plan route.

        Args:
            plan: Flight plan to validate

        Returns:
            List of validation error messages (empty if valid)

        Examples:
            >>> errors = manager.validate_route(plan)
            >>> if not errors:
            ...     print("Route is valid")
        """
        errors = []

        if not plan.route:
            errors.append("Route has no waypoints")

        if len(plan.route) < 2:
            errors.append("Route must have at least 2 waypoints")

        if plan.cruise_altitude_ft < 0:
            errors.append("Cruise altitude cannot be negative")

        if plan.cruise_altitude_ft > 60000:
            errors.append("Cruise altitude exceeds maximum (60,000 ft)")

        # Check for duplicate consecutive waypoints
        for i in range(len(plan.route) - 1):
            if plan.route[i].navaid.identifier == plan.route[i + 1].navaid.identifier:
                errors.append(f"Duplicate consecutive waypoint: {plan.route[i].navaid.identifier}")

        return errors

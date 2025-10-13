"""Traffic pattern generation for realistic AI traffic."""

import math
import random

from airborne.physics.vectors import Vector3
from airborne.plugins.traffic.ai_aircraft import AIAircraft, FlightPhase, FlightPlan, Waypoint


class TrafficGenerator:
    """Generates AI traffic for airports.

    Creates realistic traffic patterns including departures, arrivals,
    and pattern work around airports.
    """

    def __init__(self) -> None:
        """Initialize traffic generator."""
        self._aircraft_counter = 0

    def generate_departure(
        self,
        airport_position: Vector3,
        runway_heading: float,
        airport_elevation_ft: float = 0.0,
    ) -> AIAircraft:
        """Generate departing aircraft.

        Args:
            airport_position: Airport reference position
            runway_heading: Runway heading in degrees
            airport_elevation_ft: Airport elevation in feet MSL

        Returns:
            AIAircraft configured for departure
        """
        self._aircraft_counter += 1
        callsign = f"AI{self._aircraft_counter:04d}"

        # Start on runway, ready for takeoff
        aircraft = AIAircraft(
            callsign=callsign,
            aircraft_type=random.choice(["C172", "C182", "PA28", "BE36"]),
            position=airport_position,
            heading=runway_heading,
            altitude_ft=airport_elevation_ft,
            airspeed_kts=0.0,
            on_ground=True,
            flight_phase=FlightPhase.TAKEOFF,
        )

        # Create departure flight plan
        waypoints = []

        # Climb out on runway heading to 1500 ft
        climb_distance = 3.0  # 3 NM
        climb_pos = self._project_position(airport_position, runway_heading, climb_distance * 6076)
        waypoints.append(
            Waypoint(
                position=Vector3(climb_pos.x, airport_elevation_ft + 1500, climb_pos.z),
                altitude_ft=airport_elevation_ft + 1500,
                speed_kts=80,
                name="CLIMB1",
            )
        )

        # Turn to random heading and continue climb
        cruise_heading = (runway_heading + random.uniform(-45, 45)) % 360
        cruise_distance = 10.0  # 10 NM
        cruise_pos = self._project_position(climb_pos, cruise_heading, cruise_distance * 6076)
        waypoints.append(
            Waypoint(
                position=Vector3(cruise_pos.x, airport_elevation_ft + 3500, cruise_pos.z),
                altitude_ft=airport_elevation_ft + 3500,
                speed_kts=120,
                name="CRUISE1",
            )
        )

        aircraft.flight_plan = FlightPlan(waypoints=waypoints)
        return aircraft

    def generate_arrival(
        self,
        airport_position: Vector3,
        runway_heading: float,
        airport_elevation_ft: float = 0.0,
        entry_distance_nm: float = 10.0,
    ) -> AIAircraft:
        """Generate arriving aircraft.

        Args:
            airport_position: Airport reference position
            runway_heading: Runway heading in degrees
            airport_elevation_ft: Airport elevation in feet MSL
            entry_distance_nm: Distance from airport at which aircraft enters

        Returns:
            AIAircraft configured for arrival
        """
        self._aircraft_counter += 1
        callsign = f"AI{self._aircraft_counter:04d}"

        # Start at entry point, opposite direction of runway
        entry_heading = (runway_heading + 180) % 360
        entry_pos = self._project_position(
            airport_position, entry_heading, entry_distance_nm * 6076
        )

        aircraft = AIAircraft(
            callsign=callsign,
            aircraft_type=random.choice(["C172", "C182", "PA28", "BE36"]),
            position=Vector3(entry_pos.x, airport_elevation_ft + 2500, entry_pos.z),
            heading=runway_heading,  # Already turned toward airport
            altitude_ft=airport_elevation_ft + 2500,
            airspeed_kts=100,
            on_ground=False,
            flight_phase=FlightPhase.APPROACH,
        )

        # Create arrival flight plan
        waypoints = []

        # Descend to pattern altitude (1500 ft AGL)
        mid_distance = entry_distance_nm / 2
        mid_pos = self._project_position(airport_position, entry_heading, mid_distance * 6076)
        waypoints.append(
            Waypoint(
                position=Vector3(mid_pos.x, airport_elevation_ft + 1500, mid_pos.z),
                altitude_ft=airport_elevation_ft + 1500,
                speed_kts=90,
                name="DOWNWIND",
            )
        )

        # Final approach
        final_distance = 3.0  # 3 NM final
        final_pos = self._project_position(airport_position, entry_heading, final_distance * 6076)
        waypoints.append(
            Waypoint(
                position=Vector3(final_pos.x, airport_elevation_ft + 500, final_pos.z),
                altitude_ft=airport_elevation_ft + 500,
                speed_kts=70,
                name="FINAL",
            )
        )

        # Runway threshold
        waypoints.append(
            Waypoint(
                position=Vector3(airport_position.x, airport_elevation_ft, airport_position.z),
                altitude_ft=airport_elevation_ft,
                speed_kts=60,
                name="THRESHOLD",
            )
        )

        aircraft.flight_plan = FlightPlan(waypoints=waypoints)
        return aircraft

    def generate_pattern_traffic(
        self,
        airport_position: Vector3,
        runway_heading: float,
        airport_elevation_ft: float = 0.0,
        count: int = 3,
    ) -> list[AIAircraft]:
        """Generate aircraft doing pattern work.

        Args:
            airport_position: Airport reference position
            runway_heading: Runway heading in degrees
            airport_elevation_ft: Airport elevation in feet MSL
            count: Number of aircraft to generate

        Returns:
            List of AIAircraft in the pattern
        """
        aircraft_list = []
        pattern_altitude = airport_elevation_ft + 1000  # Pattern at 1000 ft AGL

        for i in range(count):
            self._aircraft_counter += 1
            callsign = f"AI{self._aircraft_counter:04d}"

            # Distribute aircraft around the pattern
            leg = i % 4  # 0=downwind, 1=base, 2=final, 3=crosswind

            if leg == 0:  # Downwind
                heading = (runway_heading + 180) % 360
                offset = 0.5  # 0.5 NM abeam runway
                pos = self._project_position(airport_position, runway_heading + 90, offset * 6076)
                pos = self._project_position(pos, heading, 1.0 * 6076)
            elif leg == 1:  # Base
                heading = (runway_heading + 90) % 360
                pos = self._project_position(airport_position, heading, 1.5 * 6076)
            elif leg == 2:  # Final
                heading = runway_heading
                pos = self._project_position(airport_position, runway_heading + 180, 2.0 * 6076)
            else:  # Crosswind
                heading = (runway_heading + 90) % 360
                pos = self._project_position(airport_position, runway_heading, 0.5 * 6076)

            aircraft = AIAircraft(
                callsign=callsign,
                aircraft_type="C172",
                position=Vector3(pos.x, pattern_altitude, pos.z),
                heading=heading,
                altitude_ft=pattern_altitude,
                airspeed_kts=80,
                on_ground=False,
                flight_phase=FlightPhase.PATTERN,
            )

            # Create pattern flight plan (one complete circuit)
            waypoints = self._create_pattern_waypoints(
                airport_position, runway_heading, pattern_altitude
            )
            aircraft.flight_plan = FlightPlan(waypoints=waypoints)

            aircraft_list.append(aircraft)

        return aircraft_list

    def _create_pattern_waypoints(
        self, airport_position: Vector3, runway_heading: float, pattern_altitude: float
    ) -> list[Waypoint]:
        """Create waypoints for standard traffic pattern."""
        waypoints = []

        # Upwind (departure end of runway)
        upwind_pos = self._project_position(airport_position, runway_heading, 0.5 * 6076)
        waypoints.append(
            Waypoint(
                position=Vector3(upwind_pos.x, pattern_altitude, upwind_pos.z),
                altitude_ft=pattern_altitude,
                speed_kts=80,
                name="UPWIND",
            )
        )

        # Crosswind turn
        crosswind_heading = (runway_heading + 90) % 360
        crosswind_pos = self._project_position(upwind_pos, crosswind_heading, 0.5 * 6076)
        waypoints.append(
            Waypoint(
                position=Vector3(crosswind_pos.x, pattern_altitude, crosswind_pos.z),
                altitude_ft=pattern_altitude,
                speed_kts=80,
                name="CROSSWIND",
            )
        )

        # Downwind
        downwind_heading = (runway_heading + 180) % 360
        downwind_pos = self._project_position(crosswind_pos, downwind_heading, 1.5 * 6076)
        waypoints.append(
            Waypoint(
                position=Vector3(downwind_pos.x, pattern_altitude, downwind_pos.z),
                altitude_ft=pattern_altitude,
                speed_kts=80,
                name="DOWNWIND",
            )
        )

        # Base turn
        base_heading = (runway_heading + 270) % 360
        base_pos = self._project_position(downwind_pos, base_heading, 0.5 * 6076)
        waypoints.append(
            Waypoint(
                position=Vector3(base_pos.x, pattern_altitude - 200, base_pos.z),
                altitude_ft=pattern_altitude - 200,
                speed_kts=75,
                name="BASE",
            )
        )

        # Final
        final_pos = self._project_position(airport_position, runway_heading + 180, 1.0 * 6076)
        waypoints.append(
            Waypoint(
                position=Vector3(final_pos.x, pattern_altitude - 500, final_pos.z),
                altitude_ft=pattern_altitude - 500,
                speed_kts=70,
                name="FINAL",
            )
        )

        # Threshold
        waypoints.append(
            Waypoint(
                position=airport_position,
                altitude_ft=pattern_altitude - 1000,
                speed_kts=60,
                name="THRESHOLD",
            )
        )

        return waypoints

    @staticmethod
    def _project_position(
        start_pos: Vector3, heading_deg: float, distance_meters: float
    ) -> Vector3:
        """Project a position from a starting point.

        Args:
            start_pos: Starting position
            heading_deg: Heading in degrees (0 = north)
            distance_meters: Distance to project in meters

        Returns:
            New position
        """
        heading_rad = math.radians(heading_deg)
        dx = distance_meters * math.sin(heading_rad)
        dz = distance_meters * math.cos(heading_rad)

        return Vector3(start_pos.x + dx, start_pos.y, start_pos.z + dz)

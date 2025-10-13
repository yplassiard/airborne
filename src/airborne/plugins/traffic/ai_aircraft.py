"""AI Aircraft entities for traffic simulation."""

import math
import random
from dataclasses import dataclass, field
from enum import Enum

from airborne.physics.vectors import Vector3


class FlightPhase(Enum):
    """Flight phases for AI aircraft."""

    TAXI = "taxi"
    TAKEOFF = "takeoff"
    CLIMB = "climb"
    CRUISE = "cruise"
    DESCENT = "descent"
    APPROACH = "approach"
    LANDING = "landing"
    PATTERN = "pattern"


@dataclass
class Waypoint:
    """Navigation waypoint.

    Attributes:
        position: 3D position (lat/lon/alt in Vector3)
        altitude_ft: Target altitude at waypoint in feet
        speed_kts: Target speed at waypoint in knots
        name: Optional waypoint name
    """

    position: Vector3
    altitude_ft: float
    speed_kts: float
    name: str = ""


@dataclass
class FlightPlan:
    """Flight plan with waypoints.

    Attributes:
        waypoints: List of waypoints to follow
        current_waypoint_index: Index of current target waypoint
    """

    waypoints: list[Waypoint] = field(default_factory=list)
    current_waypoint_index: int = 0

    def get_current_waypoint(self) -> Waypoint | None:
        """Get current target waypoint."""
        if 0 <= self.current_waypoint_index < len(self.waypoints):
            return self.waypoints[self.current_waypoint_index]
        return None

    def advance_waypoint(self) -> bool:
        """Advance to next waypoint.

        Returns:
            True if advanced, False if at end of flight plan
        """
        if self.current_waypoint_index < len(self.waypoints) - 1:
            self.current_waypoint_index += 1
            return True
        return False

    def is_complete(self) -> bool:
        """Check if flight plan is complete."""
        return self.current_waypoint_index >= len(self.waypoints)


@dataclass
class AIAircraft:
    """AI aircraft entity with flight dynamics.

    Attributes:
        callsign: Aircraft callsign (e.g., "N12345")
        aircraft_type: Type of aircraft (e.g., "C172", "B738")
        position: Current 3D position
        velocity: Current velocity vector
        heading: Current heading in degrees (0-360)
        altitude_ft: Current altitude in feet MSL
        vertical_speed_fpm: Current vertical speed in feet per minute
        airspeed_kts: Current airspeed in knots
        flight_plan: Flight plan to follow
        flight_phase: Current phase of flight
        on_ground: Whether aircraft is on ground
    """

    callsign: str
    aircraft_type: str
    position: Vector3
    velocity: Vector3 = field(default_factory=lambda: Vector3(0, 0, 0))
    heading: float = 0.0
    altitude_ft: float = 0.0
    vertical_speed_fpm: float = 0.0
    airspeed_kts: float = 0.0
    flight_plan: FlightPlan = field(default_factory=FlightPlan)
    flight_phase: FlightPhase = FlightPhase.CRUISE
    on_ground: bool = False

    # Performance characteristics
    cruise_speed_kts: float = 120.0
    climb_rate_fpm: float = 700.0
    descent_rate_fpm: float = 500.0
    turn_rate_deg_sec: float = 3.0
    acceleration_kts_sec: float = 2.0

    def update(self, dt: float) -> None:
        """Update AI aircraft state.

        Args:
            dt: Time delta in seconds
        """
        if self.on_ground:
            return

        # Follow flight plan if available
        if self.flight_plan and not self.flight_plan.is_complete():
            self._follow_flight_plan(dt)

        # Update position based on velocity
        self._update_position(dt)

    def _follow_flight_plan(self, dt: float) -> None:
        """Follow the flight plan to next waypoint."""
        waypoint = self.flight_plan.get_current_waypoint()
        if not waypoint:
            return

        # Calculate vector to waypoint
        dx = waypoint.position.x - self.position.x
        dz = waypoint.position.z - self.position.z
        distance_nm = math.sqrt(dx**2 + dz**2) / 6076.0  # Convert to nautical miles

        # Calculate desired heading
        desired_heading = math.degrees(math.atan2(dx, dz)) % 360

        # Turn towards desired heading
        heading_error = (desired_heading - self.heading + 180) % 360 - 180
        max_turn = self.turn_rate_deg_sec * dt
        if abs(heading_error) < max_turn:
            self.heading = desired_heading
        else:
            self.heading += max_turn if heading_error > 0 else -max_turn
        self.heading = self.heading % 360

        # Manage altitude
        altitude_error = waypoint.altitude_ft - self.altitude_ft
        if abs(altitude_error) > 100:  # More than 100 ft error
            if altitude_error > 0:
                # Climb
                self.vertical_speed_fpm = min(self.climb_rate_fpm, altitude_error / (dt / 60))
            else:
                # Descend
                self.vertical_speed_fpm = max(-self.descent_rate_fpm, altitude_error / (dt / 60))
        else:
            # Level off
            self.vertical_speed_fpm = 0.0

        # Manage speed
        speed_error = waypoint.speed_kts - self.airspeed_kts
        max_accel = self.acceleration_kts_sec * dt
        if abs(speed_error) < max_accel:
            self.airspeed_kts = waypoint.speed_kts
        else:
            self.airspeed_kts += max_accel if speed_error > 0 else -max_accel

        # Check if waypoint reached (within 0.5 NM)
        if distance_nm < 0.5:
            self.flight_plan.advance_waypoint()

    def _update_position(self, dt: float) -> None:
        """Update position based on current velocity and heading."""
        # Convert airspeed and heading to velocity components
        # Heading is relative to north (z-axis)
        speed_mps = self.airspeed_kts * 0.514444  # knots to m/s

        heading_rad = math.radians(self.heading)
        vx = speed_mps * math.sin(heading_rad)
        vz = speed_mps * math.cos(heading_rad)
        vy = self.vertical_speed_fpm * 0.00508  # fpm to m/s

        self.velocity = Vector3(vx, vy, vz)

        # Update position
        self.position = Vector3(
            self.position.x + self.velocity.x * dt,
            self.position.y + self.velocity.y * dt,
            self.position.z + self.velocity.z * dt,
        )

        # Update altitude
        self.altitude_ft += self.vertical_speed_fpm * (dt / 60)

    def get_distance_to(self, other_position: Vector3) -> float:
        """Calculate distance to another position in nautical miles.

        Args:
            other_position: Position to calculate distance to

        Returns:
            Distance in nautical miles
        """
        return self.position.distance_to(other_position) / 6076.0

    def get_closure_rate(self, other: "AIAircraft") -> float:
        """Calculate closure rate with another aircraft in knots.

        Args:
            other: Other aircraft

        Returns:
            Closure rate in knots (positive = closing, negative = opening)
        """
        # Vector from other to self
        dx = self.position.x - other.position.x
        dy = self.position.y - other.position.y
        dz = self.position.z - other.position.z
        distance = math.sqrt(dx**2 + dy**2 + dz**2)

        if distance < 0.1:  # Avoid division by zero
            return 0.0

        # Relative velocity
        dvx = self.velocity.x - other.velocity.x
        dvy = self.velocity.y - other.velocity.y
        dvz = self.velocity.z - other.velocity.z

        # Closure rate = dot product of relative velocity and position vector
        closure_rate_mps = (dvx * dx + dvy * dy + dvz * dvz) / distance
        return closure_rate_mps * 1.94384  # m/s to knots

    @staticmethod
    def create_random(
        callsign: str, position: Vector3, aircraft_type: str = "C172"
    ) -> "AIAircraft":
        """Create a random AI aircraft.

        Args:
            callsign: Aircraft callsign
            position: Starting position
            aircraft_type: Type of aircraft

        Returns:
            New AIAircraft instance
        """
        return AIAircraft(
            callsign=callsign,
            aircraft_type=aircraft_type,
            position=position,
            heading=random.uniform(0, 360),
            altitude_ft=random.uniform(1000, 10000),
            airspeed_kts=random.uniform(80, 150),
            cruise_speed_kts=120 + random.uniform(-20, 20),
            climb_rate_fpm=700 + random.uniform(-100, 100),
            descent_rate_fpm=500 + random.uniform(-100, 100),
        )

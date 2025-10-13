"""Ground physics for aircraft on taxiways and runways.

Provides friction, steering, and braking physics for ground operations.
Integrates with the flight model to handle ground contact and taxi operations.

Typical usage:
    from airborne.physics.ground_physics import GroundPhysics

    ground = GroundPhysics()
    forces = ground.calculate_ground_forces(state, inputs, on_ground=True)
"""

import logging
import math
from dataclasses import dataclass

from airborne.physics.vectors import Vector3

logger = logging.getLogger(__name__)


@dataclass
class GroundContact:
    """Ground contact state for an aircraft.

    Attributes:
        on_ground: True if aircraft is on ground
        gear_compression: Gear compression ratio (0.0 = no compression, 1.0 = full)
        surface_type: Type of surface (asphalt, concrete, grass, dirt)
        ground_speed_mps: Ground speed in meters per second
        heading_deg: Aircraft heading in degrees
        ground_friction: Friction coefficient for current surface
    """

    on_ground: bool = False
    gear_compression: float = 0.0
    surface_type: str = "asphalt"
    ground_speed_mps: float = 0.0
    heading_deg: float = 0.0
    ground_friction: float = 0.8


class GroundForces:
    """Forces acting on aircraft during ground operations.

    Attributes:
        friction_force: Friction force opposing motion (N)
        rolling_resistance: Rolling resistance force (N)
        steering_force: Lateral force from nosewheel steering (N)
        brake_force: Braking force from wheel brakes (N)
        total_force: Total ground force vector (N)
    """

    def __init__(self) -> None:
        """Initialize ground forces."""
        self.friction_force = Vector3(0, 0, 0)
        self.rolling_resistance = Vector3(0, 0, 0)
        self.steering_force = Vector3(0, 0, 0)
        self.brake_force = Vector3(0, 0, 0)
        self.total_force = Vector3(0, 0, 0)


class GroundPhysics:
    """Ground physics simulation for aircraft.

    Handles friction, steering, braking, and rolling resistance during
    ground operations (taxi, takeoff roll, landing rollout).

    Examples:
        >>> ground = GroundPhysics()
        >>> contact = GroundContact(on_ground=True, ground_speed_mps=10.0)
        >>> forces = ground.calculate_ground_forces(contact, rudder=0.5, brake=0.0)
        >>> print(f"Steering force: {forces.steering_force.magnitude():.1f} N")
    """

    # Surface friction coefficients
    FRICTION_COEFFICIENTS = {
        "asphalt": 0.8,
        "concrete": 0.85,
        "grass": 0.4,
        "dirt": 0.5,
        "gravel": 0.6,
        "snow": 0.3,
        "ice": 0.1,
        "water": 0.2,
        "unknown": 0.7,
    }

    # Rolling resistance coefficients (dimensionless)
    ROLLING_RESISTANCE = {
        "asphalt": 0.02,
        "concrete": 0.015,
        "grass": 0.08,
        "dirt": 0.10,
        "gravel": 0.06,
        "snow": 0.05,
        "ice": 0.02,
        "water": 0.04,
        "unknown": 0.03,
    }

    def __init__(
        self,
        mass_kg: float = 1000.0,
        max_brake_force_n: float = 15000.0,
        max_steering_angle_deg: float = 60.0,
    ) -> None:
        """Initialize ground physics.

        Args:
            mass_kg: Aircraft mass in kilograms
            max_brake_force_n: Maximum braking force in Newtons
            max_steering_angle_deg: Maximum nosewheel steering angle in degrees
        """
        self.mass_kg = mass_kg
        self.max_brake_force_n = max_brake_force_n
        self.max_steering_angle_deg = max_steering_angle_deg

    def calculate_ground_forces(
        self,
        contact: GroundContact,
        rudder_input: float = 0.0,
        brake_input: float = 0.0,
        velocity: Vector3 | None = None,
    ) -> GroundForces:
        """Calculate all ground forces acting on aircraft.

        Args:
            contact: Ground contact state
            rudder_input: Rudder/nosewheel steering input (-1.0 to 1.0)
            brake_input: Brake input (0.0 to 1.0)
            velocity: Aircraft velocity vector (m/s), optional

        Returns:
            GroundForces with all calculated forces

        Examples:
            >>> ground = GroundPhysics(mass_kg=1000)
            >>> contact = GroundContact(on_ground=True, ground_speed_mps=20)
            >>> forces = ground.calculate_ground_forces(contact, brake=0.5)
        """
        forces = GroundForces()

        if not contact.on_ground:
            return forces

        # Use provided velocity or create from ground speed and heading
        if velocity is None:
            heading_rad = math.radians(contact.heading_deg)
            velocity = Vector3(
                contact.ground_speed_mps * math.sin(heading_rad),
                0,
                contact.ground_speed_mps * math.cos(heading_rad),
            )

        speed = velocity.magnitude()

        # Calculate friction force (opposes motion)
        if speed > 0.01:
            friction_coef = self._get_friction_coefficient(contact.surface_type)
            normal_force = self.mass_kg * 9.81 * contact.gear_compression

            friction_magnitude = friction_coef * normal_force
            friction_direction = velocity.normalized() * -1

            forces.friction_force = friction_direction * friction_magnitude

        # Calculate rolling resistance (always opposes motion)
        if speed > 0.01:
            rolling_coef = self._get_rolling_resistance(contact.surface_type)
            normal_force = self.mass_kg * 9.81 * contact.gear_compression

            rolling_magnitude = rolling_coef * normal_force
            rolling_direction = velocity.normalized() * -1

            forces.rolling_resistance = rolling_direction * rolling_magnitude

        # Calculate steering force (lateral force from nosewheel)
        if abs(rudder_input) > 0.01 and speed > 0.5:
            steering_angle_rad = math.radians(rudder_input * self.max_steering_angle_deg)

            # Steering effectiveness decreases with speed
            speed_factor = max(0.1, 1.0 - (speed / 50.0))  # Less effective at high speed

            # Lateral force proportional to steering angle and speed
            lateral_force = self.mass_kg * 9.81 * 0.3 * math.sin(steering_angle_rad) * speed_factor

            # Direction perpendicular to velocity
            if velocity.magnitude() > 0.01:
                forward = velocity.normalized()
                right = Vector3(forward.z, 0, -forward.x)  # 90° right
                forces.steering_force = right * lateral_force * rudder_input

        # Calculate brake force (opposes motion)
        if brake_input > 0.01 and speed > 0.01:
            brake_magnitude = brake_input * self.max_brake_force_n * contact.gear_compression
            brake_direction = velocity.normalized() * -1

            forces.brake_force = brake_direction * brake_magnitude

        # Calculate total force
        forces.total_force = (
            forces.friction_force
            + forces.rolling_resistance
            + forces.steering_force
            + forces.brake_force
        )

        return forces

    def calculate_turning_radius(
        self,
        ground_speed_mps: float,
        steering_angle_deg: float,
        wheelbase_m: float = 3.0,
    ) -> float:
        """Calculate turning radius for given speed and steering angle.

        Uses Ackermann steering geometry approximation.

        Args:
            ground_speed_mps: Ground speed in m/s
            steering_angle_deg: Nosewheel steering angle in degrees
            wheelbase_m: Distance between main gear and nose gear in meters

        Returns:
            Turning radius in meters (positive = right turn)

        Examples:
            >>> ground = GroundPhysics()
            >>> radius = ground.calculate_turning_radius(10, 30, wheelbase_m=3)
            >>> print(f"Turning radius: {radius:.1f} m")
        """
        if abs(steering_angle_deg) < 0.1:
            return float("inf")  # Straight line

        steering_rad = math.radians(steering_angle_deg)
        radius = wheelbase_m / math.tan(abs(steering_rad))

        return radius if steering_angle_deg > 0 else -radius

    def calculate_stopping_distance(
        self,
        initial_speed_mps: float,
        brake_efficiency: float = 1.0,
        surface_type: str = "asphalt",
    ) -> float:
        """Calculate stopping distance for given conditions.

        Uses simplified physics: d = v²/(2μg)

        Args:
            initial_speed_mps: Initial ground speed in m/s
            brake_efficiency: Brake efficiency (0.0 to 1.0)
            surface_type: Surface type (asphalt, grass, etc.)

        Returns:
            Stopping distance in meters

        Examples:
            >>> ground = GroundPhysics()
            >>> dist = ground.calculate_stopping_distance(50, brake_efficiency=0.8)
            >>> print(f"Stopping distance: {dist:.1f} m")
        """
        if initial_speed_mps <= 0:
            return 0.0

        friction = self._get_friction_coefficient(surface_type)
        deceleration = friction * 9.81 * brake_efficiency

        # d = v² / (2a)
        distance = (initial_speed_mps**2) / (2 * deceleration)

        return distance

    def is_safe_taxi_speed(
        self,
        ground_speed_mps: float,
        surface_type: str = "asphalt",
        max_taxi_speed_mps: float = 10.0,
    ) -> bool:
        """Check if current ground speed is safe for taxiing.

        Args:
            ground_speed_mps: Current ground speed in m/s
            surface_type: Surface type
            max_taxi_speed_mps: Maximum safe taxi speed in m/s (default ~20 kt)

        Returns:
            True if speed is safe for taxi operations

        Examples:
            >>> ground = GroundPhysics()
            >>> safe = ground.is_safe_taxi_speed(5.0)  # ~10 knots
            >>> print(f"Safe to taxi: {safe}")
        """
        return ground_speed_mps <= max_taxi_speed_mps

    def _get_friction_coefficient(self, surface_type: str) -> float:
        """Get friction coefficient for surface type.

        Args:
            surface_type: Surface type name

        Returns:
            Friction coefficient (dimensionless)
        """
        return self.FRICTION_COEFFICIENTS.get(surface_type.lower(), 0.7)

    def _get_rolling_resistance(self, surface_type: str) -> float:
        """Get rolling resistance coefficient for surface type.

        Args:
            surface_type: Surface type name

        Returns:
            Rolling resistance coefficient (dimensionless)
        """
        return self.ROLLING_RESISTANCE.get(surface_type.lower(), 0.03)

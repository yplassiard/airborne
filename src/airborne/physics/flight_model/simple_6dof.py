"""Simple 6-degree-of-freedom flight model with optimized physics.

This module provides a basic but realistic flight model that balances
accuracy with performance. It's optimized for real-time simulation at 60Hz.

Performance optimizations:
- Cached trigonometric values
- In-place vector operations
- Minimal allocations per frame
- Fast approximations where appropriate

Typical usage example:
    from airborne.physics.flight_model.simple_6dof import Simple6DOFFlightModel

    model = Simple6DOFFlightModel()
    model.initialize(config)
    state = model.update(dt=0.016, inputs=ControlInputs(throttle=0.8))
"""

import math
from typing import TYPE_CHECKING

from airborne.core.logging_system import get_logger
from airborne.physics.flight_model.base import (
    AircraftState,
    ControlInputs,
    FlightForces,
    IFlightModel,
)
from airborne.physics.vectors import Vector3

if TYPE_CHECKING:
    from airborne.systems.propeller.base import IPropeller

logger = get_logger(__name__)

# Constants for performance
GRAVITY = 9.81  # m/s²
AIR_DENSITY_SEA_LEVEL = 1.225  # kg/m³
DEGREES_TO_RADIANS = math.pi / 180.0
RADIANS_TO_DEGREES = 180.0 / math.pi


class Simple6DOFFlightModel(IFlightModel):
    """Simple 6-degree-of-freedom flight model.

    Implements basic aerodynamics with lift, drag, thrust, and weight.
    Optimized for real-time performance with minimal per-frame allocations.

    Physics model:
    - Lift = 0.5 * ρ * v² * S * CL
    - Drag = 0.5 * ρ * v² * S * CD
    - Thrust = throttle * max_thrust
    - Weight = mass * gravity

    Examples:
        >>> config = {
        ...     "wing_area_sqft": 174.0,
        ...     "weight_lbs": 2400.0,
        ...     "max_thrust_lbs": 300.0,
        ... }
        >>> model = Simple6DOFFlightModel()
        >>> model.initialize(config)
    """

    def __init__(self) -> None:
        """Initialize the flight model (not configured yet)."""
        # Aircraft parameters (set in initialize())
        self.wing_area = 0.0  # m²
        self.empty_mass = 0.0  # kg
        self.max_thrust = 0.0  # N (fallback if no propeller)
        self.drag_coefficient = 0.027  # Typical for light aircraft
        self.lift_coefficient_slope = 0.1  # CL per degree AOA
        self.max_fuel = 100.0  # kg

        # Propeller model (optional - if present, overrides max_thrust)
        self.propeller: IPropeller | None = None
        self.engine_power_hp = 0.0  # Current engine power (from ENGINE_STATE)
        self.engine_rpm = 0.0  # Current engine RPM (from ENGINE_STATE)

        # Current state
        self.state = AircraftState()
        self.forces = FlightForces()

        # External forces (wind, collisions)
        self.external_force = Vector3.zero()

        # Cached values for performance
        self._cos_pitch = 1.0
        self._sin_pitch = 0.0
        self._cos_roll = 1.0
        self._sin_roll = 0.0
        self._cos_yaw = 1.0
        self._sin_yaw = 0.0
        self._trig_dirty = True

        # Performance counters
        self._updates = 0

    def initialize(self, config: dict) -> None:
        """Initialize flight model from configuration.

        Args:
            config: Configuration with keys:
                - wing_area_sqft: Wing area in square feet
                - weight_lbs: Empty weight in pounds
                - max_thrust_lbs: Maximum thrust in pounds
                - drag_coefficient: Drag coefficient (optional, default: 0.027)
                - fuel_capacity_lbs: Fuel capacity in pounds (optional)

        Raises:
            ValueError: If required parameters missing.
        """
        # Convert imperial to metric for internal calculations
        if "wing_area_sqft" not in config:
            raise ValueError("wing_area_sqft required")
        if "weight_lbs" not in config:
            raise ValueError("weight_lbs required")
        if "max_thrust_lbs" not in config:
            raise ValueError("max_thrust_lbs required")

        # Convert to metric
        self.wing_area = config["wing_area_sqft"] * 0.092903  # sqft to m²
        self.empty_mass = config["weight_lbs"] * 0.453592  # lbs to kg
        self.max_thrust = config["max_thrust_lbs"] * 4.44822  # lbf to N

        # Optional parameters
        self.drag_coefficient = config.get("drag_coefficient", 0.027)
        fuel_capacity_lbs = config.get("fuel_capacity_lbs", 220.0)
        self.max_fuel = fuel_capacity_lbs * 0.453592

        # Initialize state
        self.state.mass = self.empty_mass + self.max_fuel
        self.state.fuel = self.max_fuel

        logger.info(
            "Initialized 6DOF model: wing_area=%.2fm², mass=%.1fkg, thrust=%.0fN",
            self.wing_area,
            self.state.mass,
            self.max_thrust,
        )

    def update(self, dt: float, inputs: ControlInputs) -> AircraftState:
        """Update physics for one time step.

        Optimized for 60Hz updates with minimal allocations.

        Args:
            dt: Time step in seconds.
            inputs: Control inputs.

        Returns:
            Updated state (reference to internal state).
        """
        self._updates += 1

        # Update cached trig values if rotation changed
        if self._trig_dirty:
            self._update_cached_trig()

        # Calculate forces (updates self.forces in-place)
        self._calculate_forces(inputs)

        # Apply external forces
        if self.external_force.magnitude_squared() > 0.001:
            self.forces.total = self.forces.total + self.external_force
            # Decay external forces
            self.external_force = self.external_force * 0.9

        # Update acceleration: F = ma => a = F/m
        self.state.acceleration = self.forces.total / self.state.mass

        # Integrate velocity: v = v + a*dt
        self.state.velocity = self.state.velocity + self.state.acceleration * dt
        self.state.mark_velocity_dirty()

        # Integrate position: p = p + v*dt
        self.state.position = self.state.position + self.state.velocity * dt

        # Update rotation based on inputs (simplified)
        self._update_rotation(dt, inputs)

        # Ground collision check (simple altitude check)
        if self.state.position.y <= 0.0:
            self.state.position.y = 0.0
            self.state.velocity.y = max(0.0, self.state.velocity.y)
            self.state.on_ground = True
        else:
            self.state.on_ground = False

        # Consume fuel (simplified)
        fuel_flow = inputs.throttle * 0.01 * dt  # kg/s at full throttle
        self.state.fuel = max(0.0, self.state.fuel - fuel_flow)
        self.state.mass = self.empty_mass + self.state.fuel

        return self.state

    def _calculate_forces(self, inputs: ControlInputs) -> None:
        """Calculate aerodynamic and propulsive forces.

        Updates self.forces in-place for efficiency.

        Args:
            inputs: Control inputs.
        """
        airspeed = self.state.get_airspeed()

        # Dynamic pressure: q = 0.5 * ρ * v²
        # Pre-compute for reuse
        q = 0.5 * AIR_DENSITY_SEA_LEVEL * airspeed * airspeed

        # --- Lift ---
        # Simplified: Lift acts upward in body frame
        # CL depends on angle of attack (approximated by pitch)
        angle_of_attack = self.state.get_pitch()  # radians
        cl = self.lift_coefficient_slope * (angle_of_attack * RADIANS_TO_DEGREES)
        lift_magnitude = q * self.wing_area * cl

        # Lift direction: perpendicular to velocity
        # Simplified: assume lift acts upward in world frame
        self.forces.lift = Vector3(0.0, lift_magnitude, 0.0)

        # --- Drag ---
        # Drag opposes velocity
        drag_magnitude = q * self.wing_area * self.drag_coefficient
        if airspeed > 0.1:
            # Drag in opposite direction of velocity
            velocity_normalized = self.state.velocity.normalized()
            self.forces.drag = velocity_normalized * (-drag_magnitude)
        else:
            self.forces.drag = Vector3.zero()

        # --- Thrust ---
        # Calculate thrust from propeller model if available, otherwise use simple model
        if self.propeller and self.engine_power_hp > 0:
            # Use propeller model for realistic thrust
            thrust_magnitude = self.propeller.calculate_thrust(
                power_hp=self.engine_power_hp,
                rpm=self.engine_rpm,
                airspeed_mps=airspeed,
                air_density_kgm3=AIR_DENSITY_SEA_LEVEL,
            )
            # Debug logging every 60 frames (~1 second at 60 FPS)
            if hasattr(self, '_thrust_log_counter'):
                self._thrust_log_counter += 1
            else:
                self._thrust_log_counter = 0

            if self._thrust_log_counter % 60 == 0:
                logger.debug(
                    f"Propeller thrust: {thrust_magnitude:.1f}N from {self.engine_power_hp:.1f}HP "
                    f"@ {self.engine_rpm:.0f}RPM, airspeed={airspeed:.1f}m/s"
                )
        else:
            # Fallback: Simple thrust model based on throttle
            thrust_magnitude = inputs.throttle * self.max_thrust

        # Apply thrust in forward direction
        if airspeed > 0.1:
            velocity_normalized = self.state.velocity.normalized()
            self.forces.thrust = velocity_normalized * thrust_magnitude
        else:
            # At zero speed, thrust in forward direction (yaw)
            thrust_x = thrust_magnitude * self._cos_yaw
            thrust_z = thrust_magnitude * self._sin_yaw
            self.forces.thrust = Vector3(thrust_x, 0.0, thrust_z)

        # --- Weight ---
        # Weight always acts downward
        self.forces.weight = Vector3(0.0, -self.state.mass * GRAVITY, 0.0)

        # --- Total Force ---
        self.forces.calculate_total()

    def _update_rotation(self, dt: float, inputs: ControlInputs) -> None:
        """Update aircraft rotation based on inputs.

        Simplified rotational dynamics for performance.

        Args:
            dt: Time step.
            inputs: Control inputs.
        """
        # Rotational response rates (rad/s per unit input)
        pitch_rate = 1.0  # rad/s
        roll_rate = 2.0  # rad/s
        yaw_rate = 0.5  # rad/s

        # Update angular velocity based on inputs
        self.state.angular_velocity = Vector3(
            inputs.pitch * pitch_rate, inputs.roll * roll_rate, inputs.yaw * yaw_rate
        )

        # Integrate rotation
        rotation_delta = self.state.angular_velocity * dt
        self.state.rotation = self.state.rotation + rotation_delta

        # Normalize angles to -π to π
        self.state.rotation.x = self._normalize_angle(self.state.rotation.x)
        self.state.rotation.y = self._normalize_angle(self.state.rotation.y)
        self.state.rotation.z = self._normalize_angle(self.state.rotation.z)

        self._trig_dirty = True

    def _normalize_angle(self, angle: float) -> float:
        """Normalize angle to -π to π range.

        Args:
            angle: Angle in radians.

        Returns:
            Normalized angle.
        """
        while angle > math.pi:
            angle -= 2.0 * math.pi
        while angle < -math.pi:
            angle += 2.0 * math.pi
        return angle

    def _update_cached_trig(self) -> None:
        """Update cached trigonometric values.

        Called only when rotation changes to avoid redundant calculations.
        """
        self._cos_pitch = math.cos(self.state.rotation.x)
        self._sin_pitch = math.sin(self.state.rotation.x)
        self._cos_roll = math.cos(self.state.rotation.y)
        self._sin_roll = math.sin(self.state.rotation.y)
        self._cos_yaw = math.cos(self.state.rotation.z)
        self._sin_yaw = math.sin(self.state.rotation.z)
        self._trig_dirty = False

    def get_state(self) -> AircraftState:
        """Get current aircraft state.

        Returns:
            Reference to internal state (efficient, no copy).
        """
        return self.state

    def reset(self, initial_state: AircraftState) -> None:
        """Reset to a new state.

        Args:
            initial_state: New state.
        """
        self.state = initial_state
        self.external_force = Vector3.zero()
        self._trig_dirty = True
        self._updates = 0
        logger.debug("Reset flight model to new state")

    def apply_force(self, force: Vector3, position: Vector3) -> None:
        """Apply external force.

        Args:
            force: Force vector in Newtons.
            position: Position (currently ignored - simplified model).
        """
        # Accumulate external forces
        self.external_force = self.external_force + force

    def get_forces(self) -> FlightForces:
        """Get current forces.

        Returns:
            Current flight forces.
        """
        return self.forces

    def get_update_count(self) -> int:
        """Get number of updates performed.

        Returns:
            Update counter (for performance monitoring).
        """
        return self._updates

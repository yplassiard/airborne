"""Weight-shift (pendular) flight model for ULM Class 2 trikes.

This module implements the physics of weight-shift controlled aircraft,
commonly known as trikes or flex-wing microlights. These aircraft use
pilot weight shift to control pitch and roll instead of conventional
control surfaces.

ULM Class 2 characteristics:
- Weight-shift control (bar pressure)
- Flexible wing (hang glider-derived)
- No control surfaces on wing
- Pendular stability (wing and trike rotate relative to each other)
- Different flight dynamics than 3-axis aircraft

The wing and trike assembly form a pendulum - control is achieved by
moving the control bar, which shifts the pilot/trike weight relative
to the wing's center of pressure.

Examples:
    >>> model = WeightShiftFlightModel()
    >>> model.initialize(config)
    >>> # Note: pitch/roll inputs represent bar pressure, not surface deflection
    >>> inputs = ControlInputs(pitch=0.3, roll=-0.2, throttle=0.7)
    >>> state = model.update(dt=0.016, inputs=inputs)
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

# Constants
GRAVITY = 9.81  # m/s²
AIR_DENSITY_SEA_LEVEL = 1.225  # kg/m³
DEGREES_TO_RADIANS = math.pi / 180.0
RADIANS_TO_DEGREES = 180.0 / math.pi


class WeightShiftFlightModel(IFlightModel):
    """Weight-shift control flight model for pendular trikes.

    This model simulates the unique flight characteristics of trikes:
    - Pendular suspension: Wing and trike connected at hang point
    - Weight-shift control: Moving CG relative to wing
    - Flexible wing aerodynamics
    - Speed stability: Trims to specific airspeed
    - Different stall characteristics

    Control philosophy:
    - Push bar forward (pitch input positive) = nose down, speed up
    - Pull bar back (pitch input negative) = nose up, slow down
    - Shift bar left (roll input negative) = left turn
    - Shift bar right (roll input positive) = right turn

    The wing has inherent speed stability - it naturally returns
    to a trimmed airspeed when the bar is released.

    Examples:
        >>> config = {
        ...     "wing_area_sqft": 180.0,
        ...     "weight_lbs": 550.0,
        ...     "wing_span_m": 10.0,
        ...     "hang_point_height_m": 1.2,
        ... }
        >>> model = WeightShiftFlightModel()
        >>> model.initialize(config)
    """

    def __init__(self) -> None:
        """Initialize weight-shift flight model."""
        # Wing parameters
        self.wing_area = 0.0  # m²
        self.wing_span = 10.0  # m
        self.empty_mass = 0.0  # kg
        self.max_fuel = 30.0  # kg (small tank)

        # Pendulum geometry
        self.hang_point_height = 1.2  # m (wing-trike pivot height)
        self.pilot_arm = 0.5  # m (pilot CG offset from hang point)

        # Aerodynamic coefficients (flex wing)
        self.cl_0 = 0.50  # Higher base CL (curved wing)
        self.cl_alpha = 0.08  # Lower lift slope (flexible wing)
        self.cl_max = 1.4  # Lower max CL than rigid wing
        self.stall_aoa_deg = 20.0  # Higher stall AOA (flex wing)
        self.drag_coefficient = 0.06  # Higher drag (exposed pilot, struts)

        # Speed stability
        self.trim_airspeed = 25.0  # m/s (~50 kt) - natural trim speed
        self.speed_stability = 0.5  # Restoring force coefficient

        # Control authority
        self.pitch_authority = 0.3  # Bar pitch effectiveness
        self.roll_authority = 0.25  # Bar roll effectiveness

        # Pendulum dynamics
        self.pendulum_frequency = 0.8  # Hz - natural swing frequency
        self.pendulum_damping = 0.4  # Damping coefficient

        # Propeller
        self.propeller: IPropeller | None = None
        self.engine_power_hp = 0.0
        self.engine_rpm = 0.0
        self.max_thrust = 0.0  # N (fallback)

        # State
        self.state = AircraftState()
        self.forces = FlightForces()
        self.external_force = Vector3.zero()

        # Trike-specific state
        self.trike_pitch_offset = 0.0  # Relative pitch of trike to wing (rad)
        self.trike_roll_offset = 0.0  # Relative roll of trike to wing (rad)

        # Cached trig
        self._cos_pitch = 1.0
        self._sin_pitch = 0.0
        self._cos_roll = 1.0
        self._sin_roll = 0.0
        self._cos_yaw = 1.0
        self._sin_yaw = 0.0
        self._trig_dirty = True

        # Diagnostics
        self._updates = 0
        self.lift_coefficient = 0.0
        self.drag_coefficient_total = 0.0
        self.angle_of_attack_deg = 0.0

        # Oswald efficiency (lower for flex wing)
        self.oswald_efficiency = 0.6

    def initialize(self, config: dict) -> None:
        """Initialize flight model from configuration.

        Args:
            config: Configuration dictionary with:
                - wing_area_sqft: Wing area in square feet
                - weight_lbs: Total weight in pounds
                - wing_span_m: Wing span in meters
                - hang_point_height_m: Hang point height
                - trim_airspeed_kt: Natural trim speed
                - Other aerodynamic coefficients (optional)

        Raises:
            ValueError: If required parameters missing.
        """
        if "wing_area_sqft" not in config:
            raise ValueError("wing_area_sqft required")
        if "weight_lbs" not in config:
            raise ValueError("weight_lbs required")

        # Convert to metric
        self.wing_area = config["wing_area_sqft"] * 0.092903
        self.empty_mass = config["weight_lbs"] * 0.453592

        # Optional parameters
        self.wing_span = config.get("wing_span_m", 10.0)
        self.hang_point_height = config.get("hang_point_height_m", 1.2)
        self.pilot_arm = config.get("pilot_arm_m", 0.5)

        # Aerodynamics
        self.cl_0 = config.get("cl_0", 0.50)
        self.cl_alpha = config.get("cl_alpha", 0.08)
        self.cl_max = config.get("cl_max", 1.4)
        self.stall_aoa_deg = config.get("stall_aoa_deg", 20.0)
        self.drag_coefficient = config.get("drag_coefficient", 0.06)

        # Speed stability
        trim_kt = config.get("trim_airspeed_kt", 50.0)
        self.trim_airspeed = trim_kt * 0.514444  # kt to m/s
        self.speed_stability = config.get("speed_stability", 0.5)

        # Control
        self.pitch_authority = config.get("pitch_authority", 0.3)
        self.roll_authority = config.get("roll_authority", 0.25)

        # Pendulum
        self.pendulum_frequency = config.get("pendulum_frequency", 0.8)
        self.pendulum_damping = config.get("pendulum_damping", 0.4)

        # Oswald efficiency (can be overridden)
        self.oswald_efficiency = config.get("oswald_efficiency", 0.6)

        # Thrust fallback
        max_thrust_lbs = config.get("max_thrust_lbs", 200.0)
        self.max_thrust = max_thrust_lbs * 4.44822

        # Fuel
        fuel_capacity_lbs = config.get("fuel_capacity_lbs", 66.0)
        self.max_fuel = fuel_capacity_lbs * 0.453592

        # Initialize state
        self.state.mass = self.empty_mass + self.max_fuel
        self.state.fuel = self.max_fuel

        logger.info(
            "Initialized Weight-Shift model: wing_area=%.2fm², mass=%.1fkg, "
            "trim_speed=%.1fm/s, span=%.1fm",
            self.wing_area,
            self.state.mass,
            self.trim_airspeed,
            self.wing_span,
        )

    def update(self, dt: float, inputs: ControlInputs) -> AircraftState:
        """Update physics for one time step.

        For weight-shift aircraft:
        - pitch input = bar fore/aft (positive = push = speed up)
        - roll input = bar lateral (positive = right turn)

        Args:
            dt: Time step in seconds.
            inputs: Control inputs (interpreted as bar position).

        Returns:
            Updated state.
        """
        self._updates += 1

        if self._trig_dirty:
            self._update_cached_trig()

        # Update pendulum dynamics (trike swing relative to wing)
        self._update_pendulum(dt, inputs)

        # Calculate forces
        self._calculate_forces(inputs)

        # Apply external forces
        if self.external_force.magnitude_squared() > 0.001:
            self.forces.total = self.forces.total + self.external_force
        self.external_force = Vector3.zero()

        # Update acceleration
        self.state.acceleration = self.forces.total / self.state.mass

        # Integrate velocity
        self.state.velocity = self.state.velocity + self.state.acceleration * dt
        self.state.mark_velocity_dirty()

        # Integrate position
        self.state.position = self.state.position + self.state.velocity * dt

        # Update wing rotation (different from trike rotation)
        self._update_wing_rotation(dt, inputs)

        # Ground collision
        if self.state.position.y <= 0.0:
            self.state.position.y = 0.0
            if self.state.velocity.y < 0.0:
                self.state.velocity.y = 0.0
            self.state.on_ground = True
        else:
            self.state.on_ground = False

        # Fuel consumption
        fuel_flow = inputs.throttle * 0.006 * dt  # Lower for small engine
        self.state.fuel = max(0.0, self.state.fuel - fuel_flow)
        self.state.mass = self.empty_mass + self.state.fuel

        return self.state

    def _update_pendulum(self, dt: float, inputs: ControlInputs) -> None:
        """Update pendulum dynamics.

        The trike swings beneath the wing like a pendulum.
        Pilot weight shift changes the relative position, which
        changes the aerodynamic forces on the wing.

        Args:
            dt: Time step.
            inputs: Control inputs (bar position).
        """
        # Natural frequency of pendulum
        omega = 2.0 * math.pi * self.pendulum_frequency

        # Target offset from bar position
        target_pitch_offset = inputs.pitch * self.pitch_authority
        target_roll_offset = inputs.roll * self.roll_authority

        # Spring-damper dynamics
        # Pitch pendulum
        pitch_error = target_pitch_offset - self.trike_pitch_offset
        pitch_accel = omega**2 * pitch_error - 2 * self.pendulum_damping * omega * pitch_error
        self.trike_pitch_offset += pitch_accel * dt

        # Roll pendulum
        roll_error = target_roll_offset - self.trike_roll_offset
        roll_accel = omega**2 * roll_error - 2 * self.pendulum_damping * omega * roll_error
        self.trike_roll_offset += roll_accel * dt

        # Clamp to physical limits
        max_offset = 0.4  # radians (~23°)
        self.trike_pitch_offset = max(-max_offset, min(max_offset, self.trike_pitch_offset))
        self.trike_roll_offset = max(-max_offset, min(max_offset, self.trike_roll_offset))

    def _calculate_angle_of_attack(self) -> float:
        """Calculate angle of attack for flex wing.

        The effective AOA includes both the wing's pitch angle
        and the trike's offset from the hang point.
        """
        pitch = self.state.get_pitch()
        velocity = self.state.velocity

        velocity_horizontal = math.sqrt(velocity.x**2 + velocity.z**2)

        if velocity_horizontal < 0.1:
            # Include trike offset effect
            return pitch + self.trike_pitch_offset

        flight_path_angle = math.atan2(velocity.y, velocity_horizontal)
        aoa = pitch - flight_path_angle

        # Trike offset changes effective AOA
        # Push forward = nose down = higher AOA (counterintuitive but correct)
        aoa -= self.trike_pitch_offset * 0.5

        return aoa

    def _calculate_lift_coefficient(self, aoa_rad: float) -> float:
        """Calculate lift coefficient for flex wing.

        Flex wings have different characteristics:
        - Higher base CL (billowed profile)
        - Gentler stall (wing deforms)
        - Lower lift slope (flexible)
        """
        aoa_deg = aoa_rad * RADIANS_TO_DEGREES

        if aoa_deg < self.stall_aoa_deg:
            cl = self.cl_0 + self.cl_alpha * aoa_deg
            cl = min(cl, self.cl_max)
        else:
            # Flex wing has gentler stall
            stall_excess = aoa_deg - self.stall_aoa_deg
            cl = self.cl_max * math.exp(-0.03 * stall_excess)
            cl = max(cl, 0.3)

        if aoa_deg < -5.0:
            cl = self.cl_0 + self.cl_alpha * aoa_deg
            cl = max(cl, -0.8)

        return cl

    def _calculate_forces(self, inputs: ControlInputs) -> None:
        """Calculate all forces for weight-shift aircraft."""
        airspeed = self.state.get_airspeed()
        q = 0.5 * AIR_DENSITY_SEA_LEVEL * airspeed * airspeed

        # Calculate AOA
        aoa = self._calculate_angle_of_attack()
        self.angle_of_attack_deg = aoa * RADIANS_TO_DEGREES

        # Lift
        cl = self._calculate_lift_coefficient(aoa)
        self.lift_coefficient = cl
        lift_magnitude = q * self.wing_area * cl

        # Lift direction
        velocity_mag_sq = self.state.velocity.magnitude_squared()
        if velocity_mag_sq > 0.01:
            velocity_normalized = self.state.velocity.normalized()
            world_up = Vector3(0.0, 1.0, 0.0)
            right = velocity_normalized.cross(world_up)

            if right.magnitude_squared() > 0.001:
                right = right.normalized()
                lift_direction = right.cross(velocity_normalized).normalized()
                self.forces.lift = lift_direction * lift_magnitude
            else:
                self.forces.lift = Vector3(0.0, lift_magnitude * 0.1, 0.0)
        else:
            self.forces.lift = Vector3.zero()

        # Drag - higher for trike (exposed pilot, struts)
        cd_parasite = self.drag_coefficient

        # Induced drag using actual geometry
        aspect_ratio = self.get_aspect_ratio()
        cd_induced = (cl * cl) / (math.pi * self.oswald_efficiency * aspect_ratio)
        cd_total = cd_parasite + cd_induced

        # Stall drag
        if abs(self.angle_of_attack_deg) > self.stall_aoa_deg:
            cd_total += 0.3 * (
                1.0 - math.exp(-0.05 * (abs(self.angle_of_attack_deg) - self.stall_aoa_deg))
            )

        # Store for glide ratio calculation
        self.drag_coefficient_total = cd_total

        drag_magnitude = q * self.wing_area * cd_total

        if velocity_mag_sq > 0.01:
            velocity_normalized = self.state.velocity.normalized()
            self.forces.drag = velocity_normalized * (-drag_magnitude)
        else:
            self.forces.drag = Vector3.zero()

        # Thrust (usually pusher configuration)
        if self.propeller and self.engine_power_hp > 0:
            thrust_magnitude = self.propeller.calculate_thrust(
                power_hp=self.engine_power_hp,
                rpm=self.engine_rpm,
                airspeed_mps=airspeed,
                air_density_kgm3=AIR_DENSITY_SEA_LEVEL,
            )
        else:
            thrust_magnitude = inputs.throttle * self.max_thrust

        # Thrust along aircraft axis
        thrust_x = thrust_magnitude * self._sin_yaw
        thrust_z = thrust_magnitude * self._cos_yaw
        self.forces.thrust = Vector3(thrust_x, 0.0, thrust_z)

        # Weight
        self.forces.weight = Vector3(0.0, -self.state.mass * GRAVITY, 0.0)

        # Total
        self.forces.calculate_total()

        # Speed stability (trim force)
        # Flex wings naturally return to trim speed
        if airspeed > 1.0 and not self.state.on_ground:
            speed_error = (airspeed - self.trim_airspeed) / self.trim_airspeed
            trim_force = -speed_error * self.speed_stability * self.state.mass * GRAVITY
            # Apply as pitching moment equivalent
            pitch_correction = Vector3(0.0, trim_force * 0.1, 0.0)
            self.forces.total = self.forces.total + pitch_correction

    def _update_wing_rotation(self, dt: float, inputs: ControlInputs) -> None:
        """Update wing rotation.

        For weight-shift, the wing's rotation is influenced by:
        - Aerodynamic forces
        - Trike pendulum position
        - Speed stability
        """
        airspeed = self.state.get_airspeed()

        # Pitch
        # Weight shift creates pitching moment
        # Trike forward = nose down = pitch negative
        pitch_moment = -self.trike_pitch_offset * self.state.mass * GRAVITY * self.hang_point_height

        # Speed stability - wing tries to return to trim
        if airspeed > 1.0:
            speed_ratio = airspeed / self.trim_airspeed
            trim_pitch_rate = (1.0 - speed_ratio) * 0.1  # Faster = nose up tendency
            pitch_moment += trim_pitch_rate * self.state.mass * GRAVITY * self.pilot_arm

        pitch_inertia = 200.0  # kg⋅m²
        pitch_accel = pitch_moment / pitch_inertia

        # Damping
        pitch_rate = self.state.angular_velocity.x
        pitch_damping = -5.0 * pitch_rate
        pitch_accel += pitch_damping

        # Roll
        # Weight shift creates rolling moment
        roll_moment = self.trike_roll_offset * self.state.mass * GRAVITY * self.hang_point_height

        roll_inertia = 150.0
        roll_accel = roll_moment / roll_inertia

        # Roll-yaw coupling (trikes turn by rolling)
        roll_rate = self.state.angular_velocity.y
        roll_damping = -4.0 * roll_rate
        roll_accel += roll_damping

        # Yaw - follows from roll (no rudder)
        yaw_accel = 0.0
        if abs(roll_rate) > 0.01:
            # Bank angle creates yaw rate (coordinated turn)
            bank_angle = self.state.get_roll()
            if airspeed > 5.0:
                yaw_rate_target = GRAVITY * math.tan(bank_angle) / airspeed
                yaw_error = yaw_rate_target - self.state.angular_velocity.z
                yaw_accel = yaw_error * 2.0

        yaw_damping = -3.0 * self.state.angular_velocity.z
        yaw_accel += yaw_damping

        # Update angular velocity
        self.state.angular_velocity.x += pitch_accel * dt
        self.state.angular_velocity.y += roll_accel * dt
        self.state.angular_velocity.z += yaw_accel * dt

        # Integrate rotation
        self.state.rotation.x += self.state.angular_velocity.x * dt
        self.state.rotation.y += self.state.angular_velocity.y * dt
        self.state.rotation.z += self.state.angular_velocity.z * dt

        # Normalize
        self.state.rotation.x = self._normalize_angle(self.state.rotation.x)
        self.state.rotation.y = self._normalize_angle(self.state.rotation.y)
        self.state.rotation.z = self._normalize_angle(self.state.rotation.z)

        # Ground constraints
        if self.state.on_ground:
            # Level on ground
            if abs(self.state.rotation.x) > 0.1:
                self.state.rotation.x *= 0.9
            if abs(self.state.rotation.y) > 0.15:
                self.state.rotation.y *= 0.9
            self.state.angular_velocity.x *= 0.8
            self.state.angular_velocity.y *= 0.8

        self._trig_dirty = True

    def _normalize_angle(self, angle: float) -> float:
        """Normalize angle to -π to π."""
        while angle > math.pi:
            angle -= 2.0 * math.pi
        while angle < -math.pi:
            angle += 2.0 * math.pi
        return angle

    def _update_cached_trig(self) -> None:
        """Update cached trig values."""
        self._cos_pitch = math.cos(self.state.rotation.x)
        self._sin_pitch = math.sin(self.state.rotation.x)
        self._cos_roll = math.cos(self.state.rotation.y)
        self._sin_roll = math.sin(self.state.rotation.y)
        self._cos_yaw = math.cos(self.state.rotation.z)
        self._sin_yaw = math.sin(self.state.rotation.z)
        self._trig_dirty = False

    def get_state(self) -> AircraftState:
        """Get current state."""
        return self.state

    def reset(self, initial_state: AircraftState) -> None:
        """Reset to new state."""
        self.state = initial_state
        self.external_force = Vector3.zero()
        self.trike_pitch_offset = 0.0
        self.trike_roll_offset = 0.0
        self._trig_dirty = True
        self._updates = 0
        logger.debug("Reset weight-shift flight model")

    def apply_force(self, force: Vector3, position: Vector3) -> None:
        """Apply external force."""
        self.external_force = self.external_force + force

    def get_forces(self) -> FlightForces:
        """Get current forces."""
        return self.forces

    def get_update_count(self) -> int:
        """Get update count."""
        return self._updates

    def get_trike_offsets(self) -> tuple[float, float]:
        """Get current trike offset angles.

        Returns:
            Tuple of (pitch_offset_rad, roll_offset_rad).
        """
        return (self.trike_pitch_offset, self.trike_roll_offset)

    def get_aspect_ratio(self) -> float:
        """Calculate wing aspect ratio from geometry.

        Aspect ratio = span² / wing_area

        Returns:
            Wing aspect ratio.
        """
        if self.wing_area > 0:
            return self.wing_span**2 / self.wing_area
        return 5.5  # Fallback default for flex wing

    def get_glide_ratio(self) -> float:
        """Get current glide ratio (L/D) based on current flight conditions.

        The glide ratio is the ratio of lift to drag, which determines
        how far the aircraft can glide per unit of altitude lost.

        Note: Trikes typically have lower glide ratios (6:1 to 8:1) due to
        higher parasite drag from exposed pilot and trike structure.

        Returns:
            Current glide ratio (L/D). Returns 0 if drag is zero.
        """
        if self.drag_coefficient_total > 0.001:
            return self.lift_coefficient / self.drag_coefficient_total
        return 0.0

    def get_best_glide_ratio(self) -> float:
        """Calculate best (maximum) glide ratio for this aircraft.

        Best L/D occurs at the CL where induced drag equals parasite drag.
        For a parabolic drag polar: L/D_max = 1 / (2 * sqrt(Cd0 * π * e * AR))

        Flex wing trikes typically achieve 6:1 to 8:1 due to:
        - Higher parasite drag (exposed pilot, struts, trike)
        - Lower Oswald efficiency (flexible wing)
        - Lower aspect ratio

        Returns:
            Best glide ratio (L/D_max).
        """
        aspect_ratio = self.get_aspect_ratio()
        cd0 = self.drag_coefficient

        # L/D_max formula for parabolic drag polar
        k = 1.0 / (math.pi * self.oswald_efficiency * aspect_ratio)
        ld_max = 1.0 / (2.0 * math.sqrt(cd0 * k))

        return ld_max

    def get_best_glide_cl(self) -> float:
        """Calculate CL for best glide ratio.

        Returns:
            Lift coefficient at best L/D.
        """
        aspect_ratio = self.get_aspect_ratio()
        cd0 = self.drag_coefficient

        # CL for best L/D: CL = sqrt(Cd0 * π * e * AR)
        cl_best = math.sqrt(cd0 * math.pi * self.oswald_efficiency * aspect_ratio)

        return cl_best

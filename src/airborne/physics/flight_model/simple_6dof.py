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
    from airborne.terrain.elevation_service import ElevationService

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

        # Aerodynamic coefficients (aircraft-specific, set in initialize())
        # These values determine lift characteristics and should come from aircraft config
        self.cl_0 = 0.30  # Zero-AOA lift coefficient (due to wing camber)
        self.cl_alpha = 0.105  # Lift curve slope per degree AOA
        self.cl_max = 1.6  # Maximum lift coefficient (clean configuration)
        self.stall_aoa_deg = 17.0  # Stall angle of attack in degrees
        self.cl_flap_delta = 0.5  # CL increase per unit flap deflection (0-1)
        self.cl_max_flaps = 2.1  # Maximum CL with full flaps

        # Wing geometry for glide ratio calculation
        self.wing_span = 11.0  # m (default for C172)
        self.aspect_ratio = 7.4  # Wing aspect ratio (b²/S)
        self.oswald_efficiency = 0.7  # Oswald efficiency factor

        # Stability and damping coefficients (configurable)
        self.pitch_damping_coefficient = (
            -25.0
        )  # Cmq - pitch rate damping (increased for keyboard control)
        self.roll_damping_coefficient = -8.0  # Clp - roll rate damping
        self.yaw_damping_coefficient = -6.0  # Cnr - yaw rate damping

        # Propeller model (optional - if present, overrides max_thrust)
        self.propeller: IPropeller | None = None
        self.engine_power_hp = 0.0  # Current engine power (from ENGINE_STATE)
        self.engine_rpm = 0.0  # Current engine RPM (from ENGINE_STATE)

        # Terrain elevation service (optional - if present, uses terrain for ground detection)
        self.elevation_service: ElevationService | None = None

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

        # Force components (for telemetry)
        self.drag_parasite_n = 0.0
        self.drag_induced_n = 0.0
        self.lift_coefficient = 0.0
        self.drag_coefficient_total = 0.0
        self.angle_of_attack_deg = 0.0

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

        # Stability and damping parameters (optional, with defaults optimized for keyboard control)
        self.pitch_damping_coefficient = config.get("pitch_damping_coefficient", -25.0)
        self.roll_damping_coefficient = config.get("roll_damping_coefficient", -8.0)
        self.yaw_damping_coefficient = config.get("yaw_damping_coefficient", -6.0)

        # Aerodynamic coefficients (aircraft-specific)
        # These determine lift characteristics and vary by airfoil, wing design, etc.
        self.cl_0 = config.get("cl_0", 0.30)  # Zero-AOA lift (NACA 2412 ≈ 0.25-0.30)
        self.cl_alpha = config.get("cl_alpha", 0.105)  # Lift slope per degree (typical 0.09-0.11)
        self.cl_max = config.get("cl_max", 1.6)  # Max CL clean config
        self.stall_aoa_deg = config.get("stall_aoa_deg", 17.0)  # Stall AOA in degrees
        self.cl_flap_delta = config.get("cl_flap_delta", 0.5)  # CL increase per unit flap (0-1)
        self.cl_max_flaps = config.get("cl_max_flaps", 2.1)  # Max CL with full flaps

        # Wing geometry for glide ratio
        self.wing_span = config.get("wing_span_m", 11.0)  # Default for C172
        self.aspect_ratio = config.get("aspect_ratio", None)  # Will calculate if not provided
        self.oswald_efficiency = config.get("oswald_efficiency", 0.7)

        # Calculate aspect ratio from geometry if not provided
        if self.aspect_ratio is None:
            self.aspect_ratio = self.get_aspect_ratio()

        # Initialize state
        self.state.mass = self.empty_mass + self.max_fuel
        self.state.fuel = self.max_fuel

        logger.info(
            "Initialized 6DOF model: wing_area=%.2fm², mass=%.1fkg, thrust=%.0fN, Cmq=%.1f",
            self.wing_area,
            self.state.mass,
            self.max_thrust,
            self.pitch_damping_coefficient,
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

        # Apply external forces (including ground forces)
        if self.external_force.magnitude_squared() > 0.001:
            self.forces.total = self.forces.total + self.external_force

        # Clear external forces after integration (they must be reapplied each frame)
        self.external_force = Vector3.zero()

        # Update acceleration: F = ma => a = F/m
        self.state.acceleration = self.forces.total / self.state.mass

        # Integrate velocity: v = v + a*dt
        self.state.velocity = self.state.velocity + self.state.acceleration * dt
        self.state.mark_velocity_dirty()

        # Integrate position: p = p + v*dt
        self.state.position = self.state.position + self.state.velocity * dt

        # Update rotation based on inputs (simplified)
        self._update_rotation(dt, inputs)

        # Ground collision check (terrain-aware)
        # Get terrain elevation at current position
        terrain_elevation = 0.0
        if self.elevation_service:
            try:
                terrain_elevation = self.elevation_service.get_elevation(
                    self.state.latitude, self.state.longitude
                )
            except Exception:
                terrain_elevation = 0.0  # Fallback to sea level

        # Update terrain state
        self.state.terrain_elevation_m = terrain_elevation
        self.state.agl_altitude_m = self.state.position.y - terrain_elevation

        # Ground contact check using terrain elevation
        if self.state.position.y <= terrain_elevation:
            self.state.position.y = terrain_elevation
            # Only clamp downward velocity (don't prevent upward velocity for takeoff)
            # Allow aircraft to build upward velocity when lift > weight
            if self.state.velocity.y < 0.0:
                self.state.velocity.y = 0.0
            self.state.on_ground = True
            self.state.agl_altitude_m = 0.0

            # DIAGNOSTIC: Log when we hit ground
            if not hasattr(self, "_ground_hit_logged"):
                logger.info(
                    f"[FLIGHT_MODEL] Aircraft hit ground: position.y={self.state.position.y:.2f}m, "
                    f"terrain={terrain_elevation:.2f}m, setting on_ground=True"
                )
                self._ground_hit_logged = True
        else:
            self.state.on_ground = False
            if hasattr(self, "_ground_hit_logged"):
                delattr(self, "_ground_hit_logged")  # Reset for next ground contact

        # Consume fuel (simplified)
        fuel_flow = inputs.throttle * 0.01 * dt  # kg/s at full throttle
        self.state.fuel = max(0.0, self.state.fuel - fuel_flow)
        self.state.mass = self.empty_mass + self.state.fuel

        return self.state

    def _calculate_angle_of_attack(self) -> float:
        """Calculate angle of attack from velocity and pitch.

        AOA is the angle between the aircraft's longitudinal axis and the velocity vector.
        This is different from pitch angle, which is relative to the horizon.

        AOA = pitch - flight_path_angle

        Returns:
            Angle of attack in radians.
        """
        pitch = self.state.get_pitch()  # radians
        velocity = self.state.velocity

        # Calculate flight path angle (gamma)
        # gamma = arctan(vertical_velocity / horizontal_velocity)
        velocity_horizontal = math.sqrt(velocity.x**2 + velocity.z**2)

        # At very low speeds, AOA approximates pitch (no significant flight path)
        if velocity_horizontal < 0.1:  # m/s
            return pitch

        # Flight path angle (positive = climbing)
        flight_path_angle = math.atan2(velocity.y, velocity_horizontal)

        # AOA = pitch - flight path angle
        angle_of_attack = pitch - flight_path_angle

        return angle_of_attack

    def _calculate_lift_coefficient(
        self, angle_of_attack_rad: float, flap_position: float = 0.0
    ) -> float:
        """Calculate lift coefficient with realistic stall behavior and flap effects.

        Uses configurable aerodynamic parameters that vary by aircraft:
        - Linear region: CL increases with AOA up to stall angle
        - Stall region: CL drops dramatically above stall AOA
        - Post-stall: Reduced lift with exponential decay
        - Flaps: Increase CL_0 and reduce stall AOA

        Args:
            angle_of_attack_rad: Angle of attack in radians
            flap_position: Flap deflection (0.0 = retracted, 1.0 = fully extended)

        Returns:
            Lift coefficient (dimensionless)

        Note:
            Parameters come from aircraft config (self.cl_0, self.cl_alpha, etc.)
            For C172: stalls at ~17° AOA clean, ~15° with full flaps, max CL ≈ 1.6-2.1
        """
        aoa_deg = angle_of_attack_rad * RADIANS_TO_DEGREES

        # Use aircraft-specific aerodynamic parameters (set in initialize())
        # Flaps increase CL_0 and max CL, but reduce stall AOA
        cl_0_effective = self.cl_0 + self.cl_flap_delta * flap_position
        max_cl_effective = self.cl_max + (self.cl_max_flaps - self.cl_max) * flap_position
        # Flaps reduce stall AOA (about 2° reduction at full flaps)
        stall_aoa_effective = self.stall_aoa_deg - 2.0 * flap_position

        if aoa_deg < stall_aoa_effective:
            # Pre-stall linear region
            cl = cl_0_effective + self.cl_alpha * aoa_deg
            # Cap at max CL to avoid overshoot
            cl = min(cl, max_cl_effective)
        else:
            # Post-stall: CL drops with exponential decay
            stall_excess = aoa_deg - stall_aoa_effective
            # Exponential decay model: CL drops quickly after stall
            cl = max_cl_effective * math.exp(-0.05 * stall_excess)
            # Floor at minimum post-stall CL
            cl = max(cl, 0.4)

        # Handle negative AOA (inverted flight / negative CL)
        if aoa_deg < -5.0:
            # Symmetric airfoil behavior at negative AOA
            cl = cl_0_effective + self.cl_alpha * aoa_deg
            cl = max(cl, -1.0)  # Floor at -1.0

        return cl

    def _calculate_drag_coefficient(self, cl: float, angle_of_attack_rad: float) -> float:
        """Calculate total drag coefficient with stall-induced drag.

        Includes:
        - Parasite drag (CD_0): Skin friction, form drag
        - Induced drag (CD_i): Due to lift generation
        - Stall drag: Additional drag in post-stall regime

        Args:
            cl: Lift coefficient
            angle_of_attack_rad: Angle of attack in radians

        Returns:
            Drag coefficient (dimensionless)

        Note:
            Drag increases dramatically in stall due to flow separation
        """
        aoa_deg = angle_of_attack_rad * RADIANS_TO_DEGREES

        # Use aircraft-specific parameters
        cd_parasite = self.drag_coefficient

        # Induced drag: CD_i = CL² / (π * e * AR)
        cd_induced = (cl * cl) / (math.pi * self.oswald_efficiency * self.aspect_ratio)

        # Stall drag: Additional drag above stall AOA
        cd_stall = 0.0
        if abs(aoa_deg) > self.stall_aoa_deg:
            # Drag increases dramatically in stall
            stall_excess = abs(aoa_deg) - self.stall_aoa_deg
            # Use 1 - exp(-x) for smooth onset of stall drag
            cd_stall = 0.5 * (1.0 - math.exp(-0.1 * stall_excess))

        total_cd = cd_parasite + cd_induced + cd_stall

        # Store for glide ratio calculation
        self.drag_coefficient_total = total_cd

        return total_cd

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
        # Lift depends on angle of attack with realistic stall behavior
        angle_of_attack = self._calculate_angle_of_attack()  # radians

        # Calculate lift coefficient using realistic stall model with flap effects
        cl = self._calculate_lift_coefficient(angle_of_attack, inputs.flaps)
        lift_magnitude = q * self.wing_area * cl

        # DEBUG: Log lift calculation details every 60 frames (~1 second)
        if self._updates % 60 == 0:
            logger.debug(
                f"[LIFT CALC] airspeed={airspeed:.1f}m/s q={q:.1f}Pa wing_area={self.wing_area:.2f}m² AOA={angle_of_attack * RADIANS_TO_DEGREES:.2f}° CL_slope={self.lift_coefficient_slope:.3f} CL={cl:.3f} lift_mag={lift_magnitude:.1f}N mass={self.state.mass:.1f}kg weight={self.state.mass * GRAVITY:.1f}N"
            )

        # Lift direction: perpendicular to velocity vector
        # This prevents runaway climb by ensuring lift doesn't add to vertical velocity
        velocity_mag_sq = self.state.velocity.magnitude_squared()
        if velocity_mag_sq > 0.01:  # velocity magnitude > 0.1 m/s
            velocity_normalized = self.state.velocity.normalized()

            # Calculate lift direction perpendicular to velocity
            # Use cross product: right = velocity × world_up, lift = right × velocity
            world_up = Vector3(0.0, 1.0, 0.0)
            right = velocity_normalized.cross(world_up)

            # Check if velocity is not purely vertical
            if right.magnitude_squared() > 0.001:
                right = right.normalized()
                # Lift perpendicular to velocity, in the "up" direction relative to flight path
                lift_direction = right.cross(velocity_normalized).normalized()
                self.forces.lift = lift_direction * lift_magnitude
            else:
                # Velocity is nearly vertical (straight up/down)
                # In this case, lift acts in aircraft's pitch direction
                # For simplicity, use minimal lift in this edge case
                self.forces.lift = Vector3(0.0, lift_magnitude * 0.1, 0.0)
        else:
            # At very low speeds, lift is negligible
            self.forces.lift = Vector3.zero()

        # --- Drag ---
        # Calculate total drag coefficient with stall effects
        # cl is already calculated above in lift calculation
        cd = self._calculate_drag_coefficient(cl, angle_of_attack)
        drag_magnitude = q * self.wing_area * cd

        # Store components for telemetry (break down for analysis)
        cd_induced = (cl * cl) / (math.pi * self.aspect_ratio * self.oswald_efficiency)

        self.drag_parasite_n = q * self.wing_area * self.drag_coefficient
        self.drag_induced_n = q * self.wing_area * cd_induced
        self.lift_coefficient = cl
        self.angle_of_attack_deg = angle_of_attack * RADIANS_TO_DEGREES

        velocity_mag_sq_drag = self.state.velocity.magnitude_squared()
        if velocity_mag_sq_drag > 0.01:  # velocity magnitude > 0.1 m/s
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
        else:
            # Fallback: Simple thrust model based on throttle
            thrust_magnitude = inputs.throttle * self.max_thrust

        # Apply thrust in forward direction (based on aircraft heading, NOT velocity!)
        # Coordinate system: +Z is forward (north), +X is right (east)
        # Yaw = 0 means facing north (+Z direction)
        # NOTE: Thrust is always applied in the direction the aircraft is pointing,
        # regardless of velocity direction (unlike drag which opposes velocity)
        thrust_x = thrust_magnitude * self._sin_yaw  # East component
        thrust_z = thrust_magnitude * self._cos_yaw  # North component
        self.forces.thrust = Vector3(thrust_x, 0.0, thrust_z)

        # --- Weight ---
        # Weight always acts downward
        self.forces.weight = Vector3(0.0, -self.state.mass * GRAVITY, 0.0)

        # --- Total Force ---
        self.forces.calculate_total()

        # DEBUG: Log force calculations at high speeds
        if airspeed > 50.0:  # 50 m/s ~= 97 knots
            thrust_mag = self.forces.thrust.magnitude()
            drag_mag = self.forces.drag.magnitude()
            total_mag = self.forces.total.magnitude()
            logger.warning(
                f"[FORCE DEBUG] spd={airspeed:.1f}m/s ({airspeed * 1.94384:.1f}kt) "
                f"thrust_vec={self.forces.thrust} thrust_mag={thrust_mag:.0f}N "
                f"drag_vec={self.forces.drag} drag_mag={drag_mag:.0f}N "
                f"total_vec={self.forces.total} total_mag={total_mag:.0f}N"
            )

    def _update_rotation(self, dt: float, inputs: ControlInputs) -> None:
        """Update aircraft rotation based on inputs, trim, and stability.

        Includes:
        - Control surface inputs (elevator, aileron, rudder)
        - Trim effects (aerodynamic moments from trim tabs)
        - Aerodynamic stability (tendency to return to trimmed condition)
        - Ground constraints (prevents nose-over on ground)

        Args:
            dt: Time step.
            inputs: Control inputs.
        """
        airspeed = self.state.get_airspeed()

        # Ground pitch constraints for tricycle gear aircraft
        # On ground, pitch is constrained by landing gear geometry
        # Cessna 172: nose gear prevents pitch below ~-5°, tail strike at ~+15°
        GROUND_PITCH_MIN_RAD = -5.0 * DEGREES_TO_RADIANS  # Nose gear limit
        GROUND_PITCH_MAX_RAD = 15.0 * DEGREES_TO_RADIANS  # Tail strike limit
        GROUND_PITCH_NEUTRAL_RAD = 2.0 * DEGREES_TO_RADIANS  # Resting pitch on ground

        # === PITCH CONTROL (Moment-Based Physics) ===

        # Cessna 172 physical parameters
        chord = 1.5  # Mean aerodynamic chord (m)
        pitch_inertia = 1500.0  # Pitch moment of inertia (kg⋅m²)

        # Dynamic pressure
        q = 0.5 * AIR_DENSITY_SEA_LEVEL * airspeed * airspeed

        # Calculate angle of attack for stability moment
        angle_of_attack = self._calculate_angle_of_attack()

        # Elevator creates pitching moment: M = q * S * c * Cm_delta_e * delta_e
        # Cm_delta_e ≈ -0.4 per radian for C172 (negative = nose down with positive deflection)
        # But our convention is positive pitch input = nose up, so we negate
        elevator_effectiveness = 0.4  # |Cm_delta_e| per radian of elevator deflection (reduced from 1.2 to prevent runaway)
        elevator_moment = q * self.wing_area * chord * elevator_effectiveness * inputs.pitch  # N⋅m

        # Trim tab creates pitching moment
        trim_effectiveness = (
            0.15  # Trim has less authority than elevator (increased from 0.1 for better authority)
        )
        trim_moment = q * self.wing_area * chord * trim_effectiveness * self.state.pitch_trim  # N⋅m

        # Aerodynamic stability: Cm_alpha (pitch stiffness)
        # Aircraft naturally wants to return to equilibrium AOA
        # Cm_alpha < 0 means stable (nose-down moment when AOA increases)
        stability_derivative = -0.35  # Cm_alpha (per radian) - realistic for Cessna 172

        # Calculate equilibrium AOA (where aircraft naturally flies)
        # For C172, this is around 2-4° depending on speed and configuration
        equilibrium_aoa = 0.035  # ~2° (radians) - better for cruise at 75-100 kts

        # Stability moment opposes deviation from equilibrium AOA
        aoa_error = angle_of_attack - equilibrium_aoa
        stability_moment = q * self.wing_area * chord * stability_derivative * aoa_error  # N⋅m

        # Pitch damping: Cmq (resists pitch rate changes)
        # Creates moment proportional to pitch rate
        # This is the key to altitude stability - resists rapid pitch changes
        pitch_rate = self.state.angular_velocity.x  # Current pitch rate (rad/s)
        damping_moment = (
            0.5
            * AIR_DENSITY_SEA_LEVEL
            * airspeed
            * self.wing_area
            * chord
            * chord
            * self.pitch_damping_coefficient
            * pitch_rate
        )  # N⋅m

        # Total pitching moment
        total_pitch_moment = (
            elevator_moment + trim_moment + stability_moment + damping_moment
        )  # N⋅m

        # Angular acceleration = Moment / Inertia
        pitch_acceleration = total_pitch_moment / pitch_inertia  # rad/s²

        # === ROLL CONTROL (Simplified) ===

        roll_inertia = 1000.0  # Roll moment of inertia (kg⋅m²)
        aileron_effectiveness = 0.15  # Roll moment coefficient
        aileron_moment = q * self.wing_area * chord * aileron_effectiveness * inputs.roll

        # Roll damping
        roll_rate = self.state.angular_velocity.y
        roll_damping_moment = (
            0.5
            * AIR_DENSITY_SEA_LEVEL
            * airspeed
            * self.wing_area
            * chord
            * chord
            * self.roll_damping_coefficient
            * roll_rate
        )

        total_roll_moment = aileron_moment + roll_damping_moment
        roll_acceleration = total_roll_moment / roll_inertia

        # === YAW CONTROL (Simplified) ===

        yaw_inertia = 2000.0  # Yaw moment of inertia (kg⋅m²)
        rudder_effectiveness = 0.10  # Yaw moment coefficient
        rudder_moment = q * self.wing_area * chord * rudder_effectiveness * inputs.yaw

        # Yaw damping
        yaw_rate = self.state.angular_velocity.z
        yaw_damping_moment = (
            0.5
            * AIR_DENSITY_SEA_LEVEL
            * airspeed
            * self.wing_area
            * chord
            * chord
            * self.yaw_damping_coefficient
            * yaw_rate
        )

        total_yaw_moment = rudder_moment + yaw_damping_moment
        yaw_acceleration = total_yaw_moment / yaw_inertia

        # === UPDATE ANGULAR VELOCITY ===

        # Integrate angular accelerations into angular velocity
        # velocity += acceleration * dt
        # Damping is now included in the moment calculations above
        angular_accel_delta = Vector3(
            pitch_acceleration * dt, roll_acceleration * dt, yaw_acceleration * dt
        )
        self.state.angular_velocity = self.state.angular_velocity + angular_accel_delta

        # === INTEGRATE ROTATION ===

        rotation_delta = self.state.angular_velocity * dt
        self.state.rotation = self.state.rotation + rotation_delta

        # Normalize angles to -π to π
        self.state.rotation.x = self._normalize_angle(self.state.rotation.x)
        self.state.rotation.y = self._normalize_angle(self.state.rotation.y)
        self.state.rotation.z = self._normalize_angle(self.state.rotation.z)

        # === GROUND PITCH CONSTRAINTS ===
        # When on ground, constrain pitch to prevent unrealistic nose-over
        # The landing gear geometry limits how far the aircraft can pitch
        if self.state.on_ground:
            current_pitch = self.state.rotation.x

            # When stationary on ground (low airspeed), add ground contact physics
            # This simulates the landing gear's natural settling behavior
            # Without this, pitch drifts because aerodynamic damping is zero at zero airspeed
            GROUND_STATIONARY_THRESHOLD = 5.0  # m/s - below this, apply ground settling
            if airspeed < GROUND_STATIONARY_THRESHOLD:
                # Ground spring: pull pitch towards neutral resting position
                # This simulates the landing gear geometry settling the aircraft
                pitch_error = current_pitch - GROUND_PITCH_NEUTRAL_RAD
                ground_spring_stiffness = 2.0  # rad/s² per radian of error
                ground_damping = 3.0  # 1/s - damping coefficient

                # Spring acceleration towards neutral
                spring_accel = -ground_spring_stiffness * pitch_error

                # Damping acceleration (opposes velocity)
                damping_accel = -ground_damping * self.state.angular_velocity.x

                # Apply ground settling acceleration
                ground_pitch_accel = spring_accel + damping_accel
                self.state.angular_velocity.x += ground_pitch_accel * dt

                # Also zero out roll angular velocity on ground when stationary
                # Aircraft should settle wings-level
                roll_damping = 3.0
                self.state.angular_velocity.y -= roll_damping * self.state.angular_velocity.y * dt

            # Clamp pitch to ground limits
            if current_pitch < GROUND_PITCH_MIN_RAD:
                self.state.rotation.x = GROUND_PITCH_MIN_RAD
                # Stop pitch rate if trying to pitch further down
                if self.state.angular_velocity.x < 0:
                    self.state.angular_velocity.x = 0.0
            elif current_pitch > GROUND_PITCH_MAX_RAD:
                self.state.rotation.x = GROUND_PITCH_MAX_RAD
                # Stop pitch rate if trying to pitch further up
                if self.state.angular_velocity.x > 0:
                    self.state.angular_velocity.x = 0.0

            # Also constrain roll on ground (wings level, max ~5° due to gear)
            GROUND_ROLL_MAX_RAD = 5.0 * DEGREES_TO_RADIANS
            if abs(self.state.rotation.y) > GROUND_ROLL_MAX_RAD:
                self.state.rotation.y = (
                    GROUND_ROLL_MAX_RAD if self.state.rotation.y > 0 else -GROUND_ROLL_MAX_RAD
                )
                # Stop roll rate
                if (self.state.rotation.y > 0 and self.state.angular_velocity.y > 0) or (
                    self.state.rotation.y < 0 and self.state.angular_velocity.y < 0
                ):
                    self.state.angular_velocity.y = 0.0

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

    def set_elevation_service(self, elevation_service: "ElevationService") -> None:
        """Set the terrain elevation service for ground detection.

        Args:
            elevation_service: ElevationService for terrain queries.
        """
        self.elevation_service = elevation_service
        logger.info("Flight model: terrain elevation service connected")

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

    def get_aspect_ratio(self) -> float:
        """Calculate wing aspect ratio from geometry.

        Aspect ratio = span² / wing_area

        For GA aircraft like C172, typical values are 7-8.
        Higher aspect ratio = better glide ratio but less maneuverable.

        Returns:
            Wing aspect ratio.
        """
        if self.wing_area > 0:
            return self.wing_span**2 / self.wing_area
        return 7.4  # Fallback default (C172)

    def get_glide_ratio(self) -> float:
        """Get current glide ratio (L/D) based on current flight conditions.

        The glide ratio is the ratio of lift to drag, which determines
        how far the aircraft can glide per unit of altitude lost.

        For a Cessna 172: best glide is approximately 9:1 at 65 KIAS.
        For a Piper Cherokee: approximately 10:1.

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

        Typical values:
        - Cessna 172: 9:1
        - Piper Cherokee: 10:1
        - Mooney M20: 12:1
        - Sailplane: 40:1 to 60:1

        Returns:
            Best glide ratio (L/D_max).
        """
        cd0 = self.drag_coefficient

        # L/D_max formula for parabolic drag polar
        k = 1.0 / (math.pi * self.oswald_efficiency * self.aspect_ratio)
        ld_max = 1.0 / (2.0 * math.sqrt(cd0 * k))

        return ld_max

    def get_best_glide_cl(self) -> float:
        """Calculate CL for best glide ratio.

        This is the lift coefficient at which the aircraft achieves
        maximum glide distance per altitude lost.

        Returns:
            Lift coefficient at best L/D.
        """
        cd0 = self.drag_coefficient

        # CL for best L/D: CL = sqrt(Cd0 * π * e * AR)
        cl_best = math.sqrt(cd0 * math.pi * self.oswald_efficiency * self.aspect_ratio)

        return cl_best

    def get_best_glide_speed_mps(self) -> float:
        """Calculate best glide speed in meters per second.

        Best glide speed is the airspeed at which the aircraft achieves
        maximum glide ratio. It varies with aircraft weight.

        V_bg = sqrt(2 * W / (ρ * S * CL_best))

        Returns:
            Best glide speed in m/s.
        """
        cl_best = self.get_best_glide_cl()

        if cl_best > 0 and self.wing_area > 0:
            v_bg = math.sqrt(
                (2.0 * self.state.mass * GRAVITY)
                / (AIR_DENSITY_SEA_LEVEL * self.wing_area * cl_best)
            )
            return v_bg
        return 0.0

    def get_best_glide_speed_kts(self) -> float:
        """Calculate best glide speed in knots.

        Returns:
            Best glide speed in knots.
        """
        return self.get_best_glide_speed_mps() * 1.94384

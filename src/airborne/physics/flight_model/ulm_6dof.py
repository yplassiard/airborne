"""ULM (Ultralight) 6-degree-of-freedom flight model.

This module provides a flight model optimized for ultralight aircraft (ULM Class 3).
It extends the Simple6DOF model with characteristics specific to ultralights:
- Lower wing loading (more responsive to gusts and control inputs)
- Higher control sensitivity
- Lower mass and inertia
- Support for high-lift devices (slats, flaperons)
- Enhanced ground handling for light aircraft

Typical usage example:
    from airborne.physics.flight_model.ulm_6dof import ULM6DOFFlightModel

    model = ULM6DOFFlightModel()
    model.initialize(config)
    state = model.update(dt=0.016, inputs=ControlInputs(throttle=0.8))
"""

import math
from typing import TYPE_CHECKING, Protocol

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


class ISlats(Protocol):
    """Interface for automatic slat systems."""

    def get_slat_position(self) -> float:
        """Get current slat deployment position (0.0 = retracted, 1.0 = fully deployed)."""
        ...

    def update(self, angle_of_attack_deg: float, airspeed_mps: float, dt: float) -> None:
        """Update slat position based on flight conditions."""
        ...


class IFlaperons(Protocol):
    """Interface for flaperon systems (combined flap/aileron)."""

    def get_flap_component(self) -> float:
        """Get current flap deflection component (0.0 to 1.0)."""
        ...

    def get_roll_authority(self) -> float:
        """Get roll authority multiplier based on current flap setting."""
        ...

    def update(self, flap_command: float, roll_command: float, dt: float) -> None:
        """Update flaperon position based on commands."""
        ...


class ULM6DOFFlightModel(IFlightModel):
    """6-DOF flight model optimized for ULM Class 3 (multiaxis) ultralights.

    Key differences from standard GA aircraft:
    - Lower wing loading: More responsive, more gust-sensitive
    - Higher control sensitivity: Lighter control forces
    - STOL capability: Support for leading-edge slats and flaperons
    - Lower inertia: Faster rotation rates
    - Enhanced stall characteristics: Gentler stall behavior with slats

    The model supports optional aerodynamic systems:
    - Automatic slats (deploy based on AOA)
    - Flaperons (combined flap/aileron surfaces)

    Examples:
        >>> config = {
        ...     "wing_area_sqft": 130.0,  # CH701 wing area
        ...     "weight_lbs": 992.0,      # Max takeoff weight
        ...     "max_thrust_lbs": 100.0,
        ...     "has_slats": True,
        ...     "has_flaperons": True,
        ... }
        >>> model = ULM6DOFFlightModel()
        >>> model.initialize(config)
    """

    def __init__(self) -> None:
        """Initialize the ULM flight model."""
        # Aircraft parameters (set in initialize())
        self.wing_area = 0.0  # m²
        self.empty_mass = 0.0  # kg
        self.max_thrust = 0.0  # N (fallback if no propeller)
        self.drag_coefficient = 0.035  # Higher for ultralights (struts, wires)
        self.max_fuel = 50.0  # kg (smaller fuel capacity)

        # ULM-specific aerodynamic coefficients
        # Generally more cambered airfoils for STOL performance
        self.cl_0 = 0.35  # Higher zero-AOA lift (more camber)
        self.cl_alpha = 0.11  # Lift curve slope per degree
        self.cl_max = 1.8  # Higher max CL (STOL wing design)
        self.stall_aoa_deg = 15.0  # Lower stall AOA (typical for high-lift sections)
        self.cl_flap_delta = 0.6  # Strong flap effect
        self.cl_max_flaps = 2.5  # Very high CL with flaps (STOL)

        # Wing geometry for aspect ratio calculation
        self.wing_span = 8.0  # m (default, set in initialize)

        # Slat effects (when deployed)
        self.cl_slat_bonus = 0.4  # Additional CL from slats
        self.stall_aoa_slat_bonus = 8.0  # AOA extension from slats (degrees)

        # Stability and damping - ULMs are lighter, less damped
        self.pitch_damping_coefficient = -15.0  # Less damping than GA (lighter)
        self.roll_damping_coefficient = -5.0
        self.yaw_damping_coefficient = -4.0

        # ULM-specific inertia (much lower than GA aircraft)
        self.pitch_inertia = 300.0  # kg⋅m² (vs 1500 for C172)
        self.roll_inertia = 200.0  # kg⋅m²
        self.yaw_inertia = 400.0  # kg⋅m²

        # Control effectiveness (higher for lighter aircraft)
        self.elevator_effectiveness = 0.6  # Higher than GA
        self.aileron_effectiveness = 0.25
        self.rudder_effectiveness = 0.15

        # Propeller model (optional)
        self.propeller: IPropeller | None = None
        self.engine_power_hp = 0.0
        self.engine_rpm = 0.0

        # Optional aerodynamic systems
        self.slats: ISlats | None = None
        self.flaperons: IFlaperons | None = None
        self.has_slats = False
        self.has_flaperons = False

        # Internal slat state (if no external system)
        self._internal_slat_position = 0.0

        # Current state
        self.state = AircraftState()
        self.forces = FlightForces()

        # External forces
        self.external_force = Vector3.zero()

        # Cached trig values
        self._cos_pitch = 1.0
        self._sin_pitch = 0.0
        self._cos_roll = 1.0
        self._sin_roll = 0.0
        self._cos_yaw = 1.0
        self._sin_yaw = 0.0
        self._trig_dirty = True

        # Diagnostics
        self._updates = 0
        self.drag_parasite_n = 0.0
        self.drag_induced_n = 0.0
        self.lift_coefficient = 0.0
        self.drag_coefficient_total = 0.0
        self.angle_of_attack_deg = 0.0
        self.current_slat_position = 0.0

        # Oswald efficiency factor (for induced drag calculation)
        self.oswald_efficiency = 0.75  # Good efficiency with simple wing

    def initialize(self, config: dict) -> None:
        """Initialize flight model from configuration.

        Args:
            config: Configuration with keys:
                - wing_area_sqft: Wing area in square feet
                - weight_lbs: Empty weight in pounds
                - max_thrust_lbs: Maximum thrust in pounds
                - drag_coefficient: Drag coefficient (optional)
                - has_slats: Whether aircraft has automatic slats
                - has_flaperons: Whether aircraft has flaperons
                - slat_deploy_aoa_deg: AOA at which slats deploy (optional)
                - Various aerodynamic coefficients (optional)

        Raises:
            ValueError: If required parameters missing.
        """
        if "wing_area_sqft" not in config:
            raise ValueError("wing_area_sqft required")
        if "weight_lbs" not in config:
            raise ValueError("weight_lbs required")
        if "max_thrust_lbs" not in config:
            raise ValueError("max_thrust_lbs required")

        # Convert to metric
        self.wing_area = config["wing_area_sqft"] * 0.092903
        self.empty_mass = config["weight_lbs"] * 0.453592
        self.max_thrust = config["max_thrust_lbs"] * 4.44822

        # Optional parameters with ULM-appropriate defaults
        self.drag_coefficient = config.get("drag_coefficient", 0.035)
        fuel_capacity_lbs = config.get("fuel_capacity_lbs", 110.0)  # Smaller tanks
        self.max_fuel = fuel_capacity_lbs * 0.453592

        # Damping coefficients
        self.pitch_damping_coefficient = config.get("pitch_damping_coefficient", -15.0)
        self.roll_damping_coefficient = config.get("roll_damping_coefficient", -5.0)
        self.yaw_damping_coefficient = config.get("yaw_damping_coefficient", -4.0)

        # Inertia values (can be overridden per aircraft)
        self.pitch_inertia = config.get("pitch_inertia", 300.0)
        self.roll_inertia = config.get("roll_inertia", 200.0)
        self.yaw_inertia = config.get("yaw_inertia", 400.0)

        # Control effectiveness
        self.elevator_effectiveness = config.get("elevator_effectiveness", 0.6)
        self.aileron_effectiveness = config.get("aileron_effectiveness", 0.25)
        self.rudder_effectiveness = config.get("rudder_effectiveness", 0.15)

        # Aerodynamic coefficients
        self.cl_0 = config.get("cl_0", 0.35)
        self.cl_alpha = config.get("cl_alpha", 0.11)
        self.cl_max = config.get("cl_max", 1.8)
        self.stall_aoa_deg = config.get("stall_aoa_deg", 15.0)
        self.cl_flap_delta = config.get("cl_flap_delta", 0.6)
        self.cl_max_flaps = config.get("cl_max_flaps", 2.5)

        # Wing geometry
        self.wing_span = config.get("wing_span_m", 8.0)
        self.oswald_efficiency = config.get("oswald_efficiency", 0.75)

        # Slat configuration
        self.has_slats = config.get("has_slats", False)
        self.cl_slat_bonus = config.get("cl_slat_bonus", 0.4)
        self.stall_aoa_slat_bonus = config.get("stall_aoa_slat_bonus", 8.0)
        self._slat_deploy_aoa_deg = config.get("slat_deploy_aoa_deg", 8.0)

        # Flaperon configuration
        self.has_flaperons = config.get("has_flaperons", False)

        # Initialize state
        self.state.mass = self.empty_mass + self.max_fuel
        self.state.fuel = self.max_fuel

        logger.info(
            "Initialized ULM 6DOF model: wing_area=%.2fm², mass=%.1fkg, slats=%s, flaperons=%s",
            self.wing_area,
            self.state.mass,
            self.has_slats,
            self.has_flaperons,
        )

    def update(self, dt: float, inputs: ControlInputs) -> AircraftState:
        """Update physics for one time step.

        Args:
            dt: Time step in seconds.
            inputs: Control inputs.

        Returns:
            Updated state.
        """
        self._updates += 1

        # Update cached trig if needed
        if self._trig_dirty:
            self._update_cached_trig()

        # Update automatic slats (if enabled)
        if self.has_slats:
            self._update_automatic_slats(dt)

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

        # Update rotation
        self._update_rotation(dt, inputs)

        # Ground collision
        if self.state.position.y <= 0.0:
            self.state.position.y = 0.0
            if self.state.velocity.y < 0.0:
                self.state.velocity.y = 0.0
            self.state.on_ground = True
        else:
            self.state.on_ground = False

        # Consume fuel
        fuel_flow = inputs.throttle * 0.008 * dt  # Lower consumption for Rotax
        self.state.fuel = max(0.0, self.state.fuel - fuel_flow)
        self.state.mass = self.empty_mass + self.state.fuel

        return self.state

    def _update_automatic_slats(self, dt: float) -> None:
        """Update automatic leading-edge slats based on AOA.

        Automatic slats deploy progressively as AOA increases,
        providing additional lift and delaying stall.
        """
        if self.slats:
            # Use external slat system
            aoa_deg = self.angle_of_attack_deg
            airspeed = self.state.get_airspeed()
            self.slats.update(aoa_deg, airspeed, dt)
            self.current_slat_position = self.slats.get_slat_position()
        else:
            # Internal slat simulation
            aoa_deg = self._calculate_angle_of_attack() * RADIANS_TO_DEGREES

            # Slats deploy progressively from deploy_aoa to deploy_aoa + 5°
            deploy_start = self._slat_deploy_aoa_deg
            deploy_full = deploy_start + 5.0

            if aoa_deg < deploy_start:
                target_position = 0.0
            elif aoa_deg > deploy_full:
                target_position = 1.0
            else:
                target_position = (aoa_deg - deploy_start) / (deploy_full - deploy_start)

            # Smooth slat movement (aerodynamic deployment, ~0.5s full travel)
            slat_rate = 2.0  # Full deploy in 0.5s
            if self._internal_slat_position < target_position:
                self._internal_slat_position = min(
                    target_position, self._internal_slat_position + slat_rate * dt
                )
            else:
                self._internal_slat_position = max(
                    target_position, self._internal_slat_position - slat_rate * dt
                )

            self.current_slat_position = self._internal_slat_position

    def _calculate_angle_of_attack(self) -> float:
        """Calculate angle of attack from velocity and pitch."""
        pitch = self.state.get_pitch()
        velocity = self.state.velocity

        velocity_horizontal = math.sqrt(velocity.x**2 + velocity.z**2)

        if velocity_horizontal < 0.1:
            return pitch

        flight_path_angle = math.atan2(velocity.y, velocity_horizontal)
        return pitch - flight_path_angle

    def _calculate_lift_coefficient(
        self, angle_of_attack_rad: float, flap_position: float = 0.0
    ) -> float:
        """Calculate lift coefficient with slat and flap effects.

        ULM-specific features:
        - Higher base CL (more cambered airfoils)
        - Slat bonus (increased CL_max and stall AOA when deployed)
        - Strong flap effects for STOL

        Args:
            angle_of_attack_rad: AOA in radians.
            flap_position: Flap deflection (0.0 to 1.0).

        Returns:
            Lift coefficient.
        """
        aoa_deg = angle_of_attack_rad * RADIANS_TO_DEGREES

        # Base coefficients with flap effects
        cl_0_effective = self.cl_0 + self.cl_flap_delta * flap_position
        max_cl_effective = self.cl_max + (self.cl_max_flaps - self.cl_max) * flap_position
        stall_aoa_effective = self.stall_aoa_deg - 2.0 * flap_position

        # Add slat effects
        if self.has_slats and self.current_slat_position > 0.01:
            slat_effect = self.current_slat_position
            max_cl_effective += self.cl_slat_bonus * slat_effect
            stall_aoa_effective += self.stall_aoa_slat_bonus * slat_effect

        # Calculate CL
        if aoa_deg < stall_aoa_effective:
            cl = cl_0_effective + self.cl_alpha * aoa_deg
            cl = min(cl, max_cl_effective)
        else:
            # Post-stall with gentler decay (slats help)
            stall_excess = aoa_deg - stall_aoa_effective
            decay_rate = 0.04 if self.has_slats else 0.05
            cl = max_cl_effective * math.exp(-decay_rate * stall_excess)
            cl = max(cl, 0.3)

        # Handle negative AOA
        if aoa_deg < -5.0:
            cl = cl_0_effective + self.cl_alpha * aoa_deg
            cl = max(cl, -1.0)

        return cl

    def _calculate_drag_coefficient(self, cl: float, angle_of_attack_rad: float) -> float:
        """Calculate drag coefficient for ULM.

        ULMs typically have higher parasite drag (struts, wires, open cockpit)
        but good induced drag (efficient high-lift wing designs).
        """
        aoa_deg = angle_of_attack_rad * RADIANS_TO_DEGREES

        # ULM drag parameters
        cd_parasite = self.drag_coefficient

        # Calculate aspect ratio from actual geometry
        aspect_ratio = self.get_aspect_ratio()

        # Induced drag (using Oswald efficiency)
        cd_induced = (cl * cl) / (math.pi * self.oswald_efficiency * aspect_ratio)

        # Slat drag (when deployed)
        cd_slat = 0.0
        if self.has_slats and self.current_slat_position > 0.01:
            cd_slat = 0.015 * self.current_slat_position  # Small drag penalty

        # Stall drag
        cd_stall = 0.0
        effective_stall_aoa = self.stall_aoa_deg
        if self.has_slats:
            effective_stall_aoa += self.stall_aoa_slat_bonus * self.current_slat_position

        if abs(aoa_deg) > effective_stall_aoa:
            stall_excess = abs(aoa_deg) - effective_stall_aoa
            cd_stall = 0.4 * (1.0 - math.exp(-0.1 * stall_excess))

        cd_total = cd_parasite + cd_induced + cd_slat + cd_stall
        self.drag_coefficient_total = cd_total
        return cd_total

    def _calculate_forces(self, inputs: ControlInputs) -> None:
        """Calculate all forces acting on the aircraft."""
        airspeed = self.state.get_airspeed()
        q = 0.5 * AIR_DENSITY_SEA_LEVEL * airspeed * airspeed

        # Calculate AOA
        angle_of_attack = self._calculate_angle_of_attack()
        self.angle_of_attack_deg = angle_of_attack * RADIANS_TO_DEGREES

        # Get effective flap position (from flaperons if available)
        flap_position = inputs.flaps
        if self.has_flaperons and self.flaperons:
            flap_position = self.flaperons.get_flap_component()

        # Lift
        cl = self._calculate_lift_coefficient(angle_of_attack, flap_position)
        self.lift_coefficient = cl
        lift_magnitude = q * self.wing_area * cl

        # Lift direction (perpendicular to velocity)
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

        # Drag
        cd = self._calculate_drag_coefficient(cl, angle_of_attack)
        drag_magnitude = q * self.wing_area * cd

        # Store for diagnostics
        self.drag_parasite_n = q * self.wing_area * self.drag_coefficient
        self.drag_induced_n = drag_magnitude - self.drag_parasite_n

        if velocity_mag_sq > 0.01:
            velocity_normalized = self.state.velocity.normalized()
            self.forces.drag = velocity_normalized * (-drag_magnitude)
        else:
            self.forces.drag = Vector3.zero()

        # Thrust
        if self.propeller and self.engine_power_hp > 0:
            thrust_magnitude = self.propeller.calculate_thrust(
                power_hp=self.engine_power_hp,
                rpm=self.engine_rpm,
                airspeed_mps=airspeed,
                air_density_kgm3=AIR_DENSITY_SEA_LEVEL,
            )
        else:
            thrust_magnitude = inputs.throttle * self.max_thrust

        thrust_x = thrust_magnitude * self._sin_yaw
        thrust_z = thrust_magnitude * self._cos_yaw
        self.forces.thrust = Vector3(thrust_x, 0.0, thrust_z)

        # Weight
        self.forces.weight = Vector3(0.0, -self.state.mass * GRAVITY, 0.0)

        # Total
        self.forces.calculate_total()

    def _update_rotation(self, dt: float, inputs: ControlInputs) -> None:
        """Update aircraft rotation with ULM-specific characteristics.

        ULMs have:
        - Lower inertia (faster response)
        - Higher control effectiveness
        - Less damping
        """
        airspeed = self.state.get_airspeed()
        chord = 1.2  # Typical ULM mean chord (m)
        q = 0.5 * AIR_DENSITY_SEA_LEVEL * airspeed * airspeed

        # Ground constraints
        GROUND_PITCH_MIN_RAD = -5.0 * DEGREES_TO_RADIANS
        GROUND_PITCH_MAX_RAD = 12.0 * DEGREES_TO_RADIANS  # Lower tail for ULM
        GROUND_PITCH_NEUTRAL_RAD = 3.0 * DEGREES_TO_RADIANS  # Slightly nose-up

        # === PITCH ===
        angle_of_attack = self._calculate_angle_of_attack()

        elevator_moment = q * self.wing_area * chord * self.elevator_effectiveness * inputs.pitch
        trim_moment = q * self.wing_area * chord * 0.2 * self.state.pitch_trim

        stability_derivative = -0.30
        equilibrium_aoa = 0.05  # ~3° for ULM
        aoa_error = angle_of_attack - equilibrium_aoa
        stability_moment = q * self.wing_area * chord * stability_derivative * aoa_error

        pitch_rate = self.state.angular_velocity.x
        damping_moment = (
            0.5
            * AIR_DENSITY_SEA_LEVEL
            * airspeed
            * self.wing_area
            * chord
            * chord
            * self.pitch_damping_coefficient
            * pitch_rate
        )

        total_pitch_moment = elevator_moment + trim_moment + stability_moment + damping_moment
        pitch_acceleration = total_pitch_moment / self.pitch_inertia

        # === ROLL ===
        roll_effectiveness = self.aileron_effectiveness
        if self.has_flaperons and self.flaperons:
            roll_effectiveness *= self.flaperons.get_roll_authority()

        aileron_moment = q * self.wing_area * chord * roll_effectiveness * inputs.roll
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
        roll_acceleration = total_roll_moment / self.roll_inertia

        # === YAW ===
        rudder_moment = q * self.wing_area * chord * self.rudder_effectiveness * inputs.yaw
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
        yaw_acceleration = total_yaw_moment / self.yaw_inertia

        # === UPDATE ===
        angular_accel_delta = Vector3(
            pitch_acceleration * dt, roll_acceleration * dt, yaw_acceleration * dt
        )
        self.state.angular_velocity = self.state.angular_velocity + angular_accel_delta
        rotation_delta = self.state.angular_velocity * dt
        self.state.rotation = self.state.rotation + rotation_delta

        # Normalize angles
        self.state.rotation.x = self._normalize_angle(self.state.rotation.x)
        self.state.rotation.y = self._normalize_angle(self.state.rotation.y)
        self.state.rotation.z = self._normalize_angle(self.state.rotation.z)

        # Ground constraints
        if self.state.on_ground:
            current_pitch = self.state.rotation.x

            GROUND_STATIONARY_THRESHOLD = 5.0
            if airspeed < GROUND_STATIONARY_THRESHOLD:
                pitch_error = current_pitch - GROUND_PITCH_NEUTRAL_RAD
                ground_spring_stiffness = 3.0  # Stiffer for light aircraft
                ground_damping = 4.0

                spring_accel = -ground_spring_stiffness * pitch_error
                damping_accel = -ground_damping * self.state.angular_velocity.x
                self.state.angular_velocity.x += (spring_accel + damping_accel) * dt

                roll_damping = 4.0
                self.state.angular_velocity.y -= roll_damping * self.state.angular_velocity.y * dt

            if current_pitch < GROUND_PITCH_MIN_RAD:
                self.state.rotation.x = GROUND_PITCH_MIN_RAD
                if self.state.angular_velocity.x < 0:
                    self.state.angular_velocity.x = 0.0
            elif current_pitch > GROUND_PITCH_MAX_RAD:
                self.state.rotation.x = GROUND_PITCH_MAX_RAD
                if self.state.angular_velocity.x > 0:
                    self.state.angular_velocity.x = 0.0

            GROUND_ROLL_MAX_RAD = 8.0 * DEGREES_TO_RADIANS  # More roll allowed (lighter)
            if abs(self.state.rotation.y) > GROUND_ROLL_MAX_RAD:
                self.state.rotation.y = (
                    GROUND_ROLL_MAX_RAD if self.state.rotation.y > 0 else -GROUND_ROLL_MAX_RAD
                )
                if (self.state.rotation.y > 0 and self.state.angular_velocity.y > 0) or (
                    self.state.rotation.y < 0 and self.state.angular_velocity.y < 0
                ):
                    self.state.angular_velocity.y = 0.0

        self._trig_dirty = True

    def _normalize_angle(self, angle: float) -> float:
        """Normalize angle to -π to π range."""
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
        """Get current aircraft state."""
        return self.state

    def reset(self, initial_state: AircraftState) -> None:
        """Reset to a new state."""
        self.state = initial_state
        self.external_force = Vector3.zero()
        self._trig_dirty = True
        self._updates = 0
        self._internal_slat_position = 0.0
        self.current_slat_position = 0.0
        logger.debug("Reset ULM flight model to new state")

    def apply_force(self, force: Vector3, position: Vector3) -> None:
        """Apply external force."""
        self.external_force = self.external_force + force

    def get_forces(self) -> FlightForces:
        """Get current forces."""
        return self.forces

    def get_update_count(self) -> int:
        """Get number of updates performed."""
        return self._updates

    def set_slats_system(self, slats: ISlats) -> None:
        """Attach an external slats system.

        Args:
            slats: Slats system implementing ISlats interface.
        """
        self.slats = slats
        self.has_slats = True
        logger.info("External slats system attached to ULM flight model")

    def set_flaperons_system(self, flaperons: IFlaperons) -> None:
        """Attach an external flaperons system.

        Args:
            flaperons: Flaperons system implementing IFlaperons interface.
        """
        self.flaperons = flaperons
        self.has_flaperons = True
        logger.info("External flaperons system attached to ULM flight model")

    def get_aspect_ratio(self) -> float:
        """Calculate wing aspect ratio from geometry.

        Aspect ratio = span² / wing_area

        Returns:
            Wing aspect ratio.
        """
        if self.wing_area > 0:
            return self.wing_span**2 / self.wing_area
        return 6.5  # Fallback default

    def get_glide_ratio(self) -> float:
        """Get current glide ratio (L/D) based on current flight conditions.

        The glide ratio is the ratio of lift to drag, which determines
        how far the aircraft can glide per unit of altitude lost.

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

        This is the theoretical maximum glide ratio in clean configuration.

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

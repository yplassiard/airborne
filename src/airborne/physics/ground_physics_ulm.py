"""Enhanced ground physics for ultralight aircraft.

This module extends the base ground physics with characteristics specific
to light aircraft (ULM, LSA):
- Crosswind weathervaning (light aircraft pivot into wind)
- Taildragger handling (CH701 can be taildragger or tricycle)
- Ground effect enhancement (lower wing = stronger ground effect)
- Bounce/porpoise modeling for light landings
- Reduced braking effectiveness (smaller brakes)

Light aircraft are particularly sensitive to:
- Crosswind during taxi, takeoff, and landing
- Gusty conditions
- Uneven surfaces (grass strips)
"""

import math
from dataclasses import dataclass

from airborne.core.logging_system import get_logger
from airborne.physics.ground_physics import GroundContact, GroundForces, GroundPhysics
from airborne.physics.vectors import Vector3

logger = get_logger(__name__)


@dataclass
class WindConditions:
    """Wind conditions affecting ground operations.

    Attributes:
        speed_mps: Wind speed in meters per second.
        direction_deg: Wind direction in degrees (where wind is FROM).
        gust_speed_mps: Maximum gust speed.
        turbulence_intensity: Turbulence intensity (0.0 to 1.0).
    """

    speed_mps: float = 0.0
    direction_deg: float = 0.0
    gust_speed_mps: float = 0.0
    turbulence_intensity: float = 0.0


@dataclass
class TaildragConfig:
    """Configuration for taildragger ground handling.

    Attributes:
        is_taildragger: True if aircraft is taildragger configuration.
        tailwheel_locked: True if tailwheel is locked (steerable = unlocked).
        prop_clearance_m: Propeller ground clearance in meters.
        cg_height_m: CG height above ground.
        wheelbase_m: Distance from tailwheel to main gear.
    """

    is_taildragger: bool = False
    tailwheel_locked: bool = False
    prop_clearance_m: float = 0.3
    cg_height_m: float = 1.0
    wheelbase_m: float = 4.0


class ULMGroundPhysics(GroundPhysics):
    """Enhanced ground physics for ultralight aircraft.

    Extends base ground physics with:
    - Crosswind weathervaning
    - Taildragger dynamics
    - Light aircraft sensitivity to wind/gusts
    - Ground effect modeling

    Light aircraft (300-600 kg) are significantly affected by wind
    during ground operations. A 15 kt crosswind can make taxi
    challenging and requires careful control input.

    Examples:
        >>> ground = ULMGroundPhysics(mass_kg=450)
        >>> wind = WindConditions(speed_mps=8.0, direction_deg=270)
        >>> ground.set_wind(wind)
        >>> contact = GroundContact(on_ground=True, ground_speed_mps=5.0)
        >>> forces = ground.calculate_ground_forces(contact, rudder=0.2)
    """

    def __init__(
        self,
        mass_kg: float = 450.0,
        max_brake_force_n: float = 3000.0,  # Smaller brakes than GA
        max_steering_angle_deg: float = 45.0,  # Less steering authority
        wing_span_m: float = 8.0,
        wing_area_m2: float = 12.0,
        taildragger_config: TaildragConfig | None = None,
    ) -> None:
        """Initialize ULM ground physics.

        Args:
            mass_kg: Aircraft mass in kilograms.
            max_brake_force_n: Maximum braking force (smaller for ULM).
            max_steering_angle_deg: Maximum nosewheel steering angle.
            wing_span_m: Wing span for ground effect calculation.
            wing_area_m2: Wing area for weathervaning calculation.
            taildragger_config: Taildragger configuration (None = tricycle).
        """
        super().__init__(mass_kg, max_brake_force_n, max_steering_angle_deg)

        self.wing_span = wing_span_m
        self.wing_area = wing_area_m2
        self.taildragger = taildragger_config or TaildragConfig()

        # Wind state
        self.wind = WindConditions()

        # ULM-specific parameters
        self.weathervane_sensitivity = 0.3  # Higher = more weathervaning
        self.gust_sensitivity = 0.5  # Higher = more gust response

    def set_wind(self, wind: WindConditions) -> None:
        """Set wind conditions.

        Args:
            wind: Current wind conditions.
        """
        self.wind = wind

    def calculate_ground_forces(
        self,
        contact: GroundContact,
        rudder_input: float = 0.0,
        brake_input: float = 0.0,
        velocity: Vector3 | None = None,
        aircraft_heading_deg: float = 0.0,
    ) -> GroundForces:
        """Calculate ground forces with ULM-specific effects.

        Adds crosswind weathervaning and taildragger effects to base forces.

        Args:
            contact: Ground contact state.
            rudder_input: Rudder/steering input (-1.0 to 1.0).
            brake_input: Brake input (0.0 to 1.0).
            velocity: Aircraft velocity vector.
            aircraft_heading_deg: Aircraft heading for weathervane calculation.

        Returns:
            GroundForces with all forces including weathervaning.
        """
        # Get base ground forces
        forces = super().calculate_ground_forces(contact, rudder_input, brake_input, velocity)

        if not contact.on_ground:
            return forces

        # Add weathervane force (crosswind effect)
        weathervane_force = self._calculate_weathervane_force(aircraft_heading_deg)
        forces.total_force = forces.total_force + weathervane_force

        # Add taildragger-specific forces
        if self.taildragger.is_taildragger:
            taildragger_force = self._calculate_taildragger_forces(contact, rudder_input, velocity)
            forces.total_force = forces.total_force + taildragger_force

        return forces

    def _calculate_weathervane_force(self, aircraft_heading_deg: float) -> Vector3:
        """Calculate weathervaning force from crosswind.

        Light aircraft naturally pivot into the wind due to the
        vertical fin acting as a weathervane. This effect is stronger
        at low speeds where aerodynamic forces dominate.

        Args:
            aircraft_heading_deg: Current aircraft heading.

        Returns:
            Lateral force vector from weathervaning.
        """
        if self.wind.speed_mps < 0.5:
            return Vector3.zero()

        # Calculate relative wind angle (crosswind component)
        relative_wind_deg = self.wind.direction_deg - aircraft_heading_deg

        # Normalize to -180 to 180
        while relative_wind_deg > 180:
            relative_wind_deg -= 360
        while relative_wind_deg < -180:
            relative_wind_deg += 360

        # Crosswind force is maximum at 90° relative wind
        crosswind_angle_rad = math.radians(relative_wind_deg)
        crosswind_component = math.sin(crosswind_angle_rad)

        # Weathervane moment creates yawing force
        # Force proportional to: wind² × wing_area × sin(angle)
        q = 0.5 * 1.225 * self.wind.speed_mps**2
        weathervane_force = q * self.wing_area * crosswind_component * self.weathervane_sensitivity

        # Add gust effect (random variation)
        if self.wind.gust_speed_mps > self.wind.speed_mps:
            gust_factor = 1.0 + self.gust_sensitivity * (
                self.wind.gust_speed_mps / self.wind.speed_mps - 1.0
            )
            weathervane_force *= gust_factor

        # Convert to world coordinates (lateral force)
        heading_rad = math.radians(aircraft_heading_deg)
        force_x = weathervane_force * math.cos(heading_rad)
        force_z = -weathervane_force * math.sin(heading_rad)

        return Vector3(force_x, 0.0, force_z)

    def _calculate_taildragger_forces(
        self,
        contact: GroundContact,
        rudder_input: float,
        velocity: Vector3 | None,
    ) -> Vector3:
        """Calculate taildragger-specific ground forces.

        Taildraggers have different handling characteristics:
        - Unstable on ground (CG behind main gear)
        - Tendency to ground loop at high speed
        - Better rough field performance
        - Harder to control in crosswind

        Args:
            contact: Ground contact state.
            rudder_input: Rudder/tailwheel input.
            velocity: Aircraft velocity.

        Returns:
            Additional force from taildragger dynamics.
        """
        if velocity is None:
            return Vector3.zero()

        speed = velocity.magnitude()

        # Ground loop tendency at high speed
        # Taildraggers are inherently unstable - any yaw creates
        # more yaw due to CG behind main gear pivot point
        if speed > 5.0:  # Above ~10 kt
            # Calculate sideslip
            if speed > 0.1:
                heading_component = velocity.z / speed
                sideslip = math.asin(max(-1, min(1, velocity.x / speed)))

                # Destabilizing force proportional to sideslip and speed²
                destabilizing_factor = 0.1 * self.mass_kg * speed * math.sin(sideslip)

                # Force pushes tail out (amplifies yaw)
                return Vector3(destabilizing_factor, 0.0, 0.0)

        # Tailwheel steering at low speed
        if speed < 15.0 and not self.taildragger.tailwheel_locked:
            # Tailwheel steering is effective at low speed
            steering_force = rudder_input * 0.3 * self.mass_kg * 9.81
            heading_rad = math.radians(contact.heading_deg)

            # Lateral force
            force_x = steering_force * math.cos(heading_rad)
            force_z = -steering_force * math.sin(heading_rad)

            return Vector3(force_x, 0.0, force_z)

        return Vector3.zero()

    def calculate_ground_effect(self, height_agl_m: float, cl: float) -> float:
        """Calculate ground effect lift multiplier.

        Ground effect increases lift when flying close to the ground.
        The effect is stronger for:
        - Lower wings (ULM often have high wings, less effect)
        - Larger aspect ratio
        - Lower height above ground

        Args:
            height_agl_m: Height above ground in meters.
            cl: Current lift coefficient.

        Returns:
            Lift multiplier (1.0 = no effect, >1.0 = increased lift).
        """
        if height_agl_m <= 0 or height_agl_m > self.wing_span:
            # Too high or on ground - no ground effect
            return 1.0

        # Height to span ratio
        h_b_ratio = height_agl_m / self.wing_span

        # Ground effect formula (empirical)
        # Lift increase = 1 + (1 - h/b)² for h/b < 1
        if h_b_ratio < 1.0:
            ground_effect_factor = 1.0 + (1.0 - h_b_ratio) ** 2 * 0.15

            # Induced drag reduction (30% reduction at h/b = 0.1)
            # This is already factored into effective lift increase

            return ground_effect_factor

        return 1.0

    def calculate_crosswind_limit(
        self,
        max_demonstrated_crosswind_kt: float = 12.0,
    ) -> float:
        """Calculate current crosswind component vs limit.

        Args:
            max_demonstrated_crosswind_kt: Maximum demonstrated crosswind.

        Returns:
            Ratio of current crosswind to limit (>1.0 = exceeds limit).
        """
        if self.wind.speed_mps < 0.1:
            return 0.0

        # Current crosswind in knots (assuming worst case 90° crosswind)
        crosswind_kt = self.wind.speed_mps * 1.94384

        # With gusts
        if self.wind.gust_speed_mps > self.wind.speed_mps:
            crosswind_kt = self.wind.gust_speed_mps * 1.94384

        return crosswind_kt / max_demonstrated_crosswind_kt

    def get_taxi_difficulty(
        self,
        surface_type: str = "asphalt",
    ) -> str:
        """Assess taxi difficulty based on conditions.

        Returns:
            Difficulty assessment: "easy", "moderate", "challenging", "dangerous"
        """
        difficulty_score = 0.0

        # Wind factor
        wind_kt = self.wind.speed_mps * 1.94384
        if wind_kt > 5:
            difficulty_score += 0.2
        if wind_kt > 10:
            difficulty_score += 0.3
        if wind_kt > 15:
            difficulty_score += 0.3

        # Gust factor
        if self.wind.gust_speed_mps > self.wind.speed_mps * 1.3:
            difficulty_score += 0.2

        # Surface factor
        if surface_type in ("grass", "dirt"):
            difficulty_score += 0.1
        if surface_type in ("gravel", "snow"):
            difficulty_score += 0.2

        # Taildragger factor
        if self.taildragger.is_taildragger:
            difficulty_score += 0.2

        if difficulty_score < 0.2:
            return "easy"
        elif difficulty_score < 0.5:
            return "moderate"
        elif difficulty_score < 0.8:
            return "challenging"
        else:
            return "dangerous"

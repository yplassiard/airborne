"""Aircraft performance calculator for takeoff and climb performance.

This module calculates takeoff distances, climb rates, and other performance
metrics based on weight, power, atmospheric conditions, and configuration.
"""

import math
from dataclasses import dataclass

from airborne.core.logging_system import get_logger
from airborne.systems.performance.vspeeds import VSpeedCalculator, VSpeeds

logger = get_logger(__name__)


@dataclass
class TakeoffPerformance:
    """Takeoff performance results.

    Attributes:
        ground_roll_ft: Distance to liftoff (ft)
        distance_50ft: Distance to clear 50 ft obstacle (ft)
        rotation_speed_kias: Rotation speed (KIAS)
        liftoff_speed_kias: Liftoff speed (KIAS)
        time_to_liftoff_sec: Time from brake release to liftoff (sec)
    """

    ground_roll_ft: float
    distance_50ft: float
    rotation_speed_kias: float
    liftoff_speed_kias: float
    time_to_liftoff_sec: float


class PerformanceCalculator:
    """Calculate aircraft performance parameters.

    Handles takeoff distances, climb performance, and other weight-dependent
    performance calculations.

    Examples:
        >>> calc = PerformanceCalculator(config)
        >>> takeoff = calc.calculate_takeoff_distance(
        ...     weight_lbs=2550.0, headwind_kts=0.0, runway_surface="paved"
        ... )
        >>> print(f"Ground roll: {takeoff.ground_roll_ft:.0f} ft")
        Ground roll: 960 ft
    """

    def __init__(self, config: dict):
        """Initialize performance calculator.

        Args:
            config: Performance configuration dictionary with:
                - reference_weight_lbs: Reference weight for POH data
                - wing_area_sqft: Wing area
                - cl_max_clean: Max lift coefficient (clean)
                - cl_max_landing: Max lift coefficient (landing)
                - vspeeds_reference: Reference V-speeds dict
                - takeoff_reference: Reference takeoff performance dict
                - max_power_hp: Maximum engine power
        """
        self.config = config

        # V-speed calculator
        ref_weight = config.get("reference_weight_lbs", 2550.0)
        ref_vstall = config.get("vspeeds_reference", {}).get("V_S", 47.0)
        cl_max_clean = config.get("cl_max_clean", 1.4)
        cl_max_landing = config.get("cl_max_landing", 2.0)

        self.vspeed_calc = VSpeedCalculator(
            reference_weight=ref_weight,
            reference_vstall=ref_vstall,
            cl_max_clean=cl_max_clean,
            cl_max_landing=cl_max_landing,
        )

        # Reference performance data
        self.reference_weight = ref_weight
        self.wing_area_sqft = config.get("wing_area_sqft", 174.0)
        self.max_power_hp = config.get("max_power_hp", 180.0)

        # Reference takeoff data (from POH)
        takeoff_ref = config.get("takeoff_reference", {})
        self.ref_ground_roll_ft = takeoff_ref.get("ground_roll_ft", 960.0)
        self.ref_distance_50ft = takeoff_ref.get("distance_50ft", 1685.0)
        self.ref_climb_rate_fpm = takeoff_ref.get("climb_rate_fpm", 730.0)

        logger.info(
            f"PerformanceCalculator initialized: ref_weight={ref_weight:.0f} lbs, "
            f"ref_ground_roll={self.ref_ground_roll_ft:.0f} ft"
        )

    def calculate_vspeeds(self, weight_lbs: float, density_altitude_ft: float = 0.0) -> VSpeeds:
        """Calculate V-speeds for current weight.

        Args:
            weight_lbs: Current aircraft weight (lbs)
            density_altitude_ft: Density altitude (ft)

        Returns:
            VSpeeds object with all calculated speeds
        """
        return self.vspeed_calc.calculate_vspeeds(weight_lbs, density_altitude_ft)

    def calculate_takeoff_distance(
        self,
        weight_lbs: float,
        headwind_kts: float = 0.0,
        runway_surface: str = "paved",
        density_altitude_ft: float = 0.0,
        flap_setting: int = 0,
    ) -> TakeoffPerformance:
        """Calculate takeoff distances.

        Uses simplified performance model based on:
        - Weight ratio correction (primary factor)
        - Headwind/tailwind correction
        - Runway surface friction
        - Density altitude (affects power and lift)

        Args:
            weight_lbs: Current aircraft weight (lbs)
            headwind_kts: Headwind component (positive) or tailwind (negative)
            runway_surface: "paved", "grass_short", "grass_long"
            density_altitude_ft: Density altitude (ft)
            flap_setting: Flap deflection (0, 10, 20, 30 degrees)

        Returns:
            TakeoffPerformance with calculated distances

        Note:
            Simplified model - real calculations are more complex with
            ground effect, propeller wash, pilot technique, etc.
        """
        # Calculate V-speeds
        vspeeds = self.calculate_vspeeds(weight_lbs, density_altitude_ft)
        v_r = vspeeds.v_r  # Rotation speed
        v_liftoff = v_r * 1.05  # Liftoff slightly above rotation

        # Weight ratio correction (primary factor)
        # Ground roll distance scales with weight^2 approximately
        weight_ratio = weight_lbs / self.reference_weight
        ground_roll = self.ref_ground_roll_ft * (weight_ratio**1.5)

        # Headwind/tailwind correction
        # Every 10 kts headwind reduces distance by ~10%
        if headwind_kts != 0:
            # Simplified: wind affects liftoff speed requirement
            # Headwind reduces ground speed needed, tailwind increases it
            wind_factor = 1.0 - (headwind_kts / v_liftoff) * 0.8
            ground_roll *= wind_factor**2

        # Runway surface correction
        surface_factors = {
            "paved": 1.0,
            "grass_short": 1.15,  # +15% for short grass
            "grass_long": 1.25,  # +25% for long grass
            "gravel": 1.10,  # +10% for gravel
        }
        surface_factor = surface_factors.get(runway_surface, 1.0)
        ground_roll *= surface_factor

        # Density altitude correction (affects power and lift)
        # Increases distance by ~3% per 1000 ft
        if density_altitude_ft > 0:
            da_factor = 1.0 + (density_altitude_ft / 1000.0) * 0.03
            ground_roll *= da_factor

        # Flap correction (flaps reduce takeoff distance)
        if flap_setting > 0:
            # Typical: 10° flaps reduce distance by 10-15%
            flap_factor = 1.0 - (flap_setting / 30.0) * 0.15
            ground_roll = max(ground_roll * flap_factor, ground_roll * 0.85)

        # Distance to clear 50 ft obstacle
        # Approximation: ~1.75× ground roll for light aircraft
        distance_50ft = ground_roll * 1.75

        # Time to liftoff (simplified)
        # Assume constant acceleration: t = 2d / v_avg
        v_avg_kts = v_liftoff / 2.0
        v_avg_fps = v_avg_kts * 1.68781  # Convert KIAS to ft/s
        time_to_liftoff = (2.0 * ground_roll) / v_avg_fps if v_avg_fps > 0 else 0.0

        takeoff_perf = TakeoffPerformance(
            ground_roll_ft=ground_roll,
            distance_50ft=distance_50ft,
            rotation_speed_kias=v_r,
            liftoff_speed_kias=v_liftoff,
            time_to_liftoff_sec=time_to_liftoff,
        )

        logger.debug(
            f"Takeoff at {weight_lbs:.0f} lbs: ground_roll={ground_roll:.0f} ft, "
            f"V_R={v_r:.1f} KIAS, headwind={headwind_kts:.0f} kts"
        )

        return takeoff_perf

    def calculate_climb_rate(
        self,
        weight_lbs: float,
        density_altitude_ft: float = 0.0,
        airspeed_kias: float | None = None,
    ) -> float:
        """Calculate rate of climb.

        Args:
            weight_lbs: Current aircraft weight (lbs)
            density_altitude_ft: Density altitude (ft)
            airspeed_kias: Climb airspeed (None = use V_Y)

        Returns:
            Climb rate in feet per minute (fpm)

        Note:
            Simplified model based on excess power:
            Rate of climb = (Excess Power) / Weight
        """
        # Use V_Y if airspeed not specified
        if airspeed_kias is None:
            vspeeds = self.calculate_vspeeds(weight_lbs, density_altitude_ft)
            airspeed_kias = vspeeds.v_y

        # Weight ratio correction
        weight_ratio = weight_lbs / self.reference_weight

        # Climb rate decreases with weight (less excess power)
        # Rough approximation: ROC ∝ (Power / Weight)
        climb_rate: float = self.ref_climb_rate_fpm / weight_ratio

        # Density altitude correction (reduces power)
        if density_altitude_ft > 0:
            # Power decreases ~3% per 1000 ft
            da_factor = 1.0 - (density_altitude_ft / 1000.0) * 0.03
            climb_rate *= da_factor

        logger.debug(
            f"Climb rate at {weight_lbs:.0f} lbs, DA={density_altitude_ft:.0f} ft: "
            f"{climb_rate:.0f} fpm"
        )

        return climb_rate

    def get_performance_summary(self, weight_lbs: float, headwind_kts: float = 0.0) -> dict:
        """Get comprehensive performance summary.

        Args:
            weight_lbs: Current aircraft weight (lbs)
            headwind_kts: Headwind component (kts)

        Returns:
            Dictionary with performance data:
                - vspeeds: VSpeeds object
                - takeoff: TakeoffPerformance object
                - climb_rate_fpm: Climb rate
                - weight_lbs: Input weight
        """
        vspeeds = self.calculate_vspeeds(weight_lbs)
        takeoff = self.calculate_takeoff_distance(weight_lbs, headwind_kts)
        climb_rate = self.calculate_climb_rate(weight_lbs)

        return {
            "weight_lbs": weight_lbs,
            "vspeeds": vspeeds,
            "takeoff": takeoff,
            "climb_rate_fpm": climb_rate,
        }

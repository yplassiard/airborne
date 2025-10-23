"""V-speed calculations for aircraft performance.

This module calculates various V-speeds (stall, rotation, climb) based on
aircraft weight, configuration, and atmospheric conditions.
"""

import math
from dataclasses import dataclass

from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


@dataclass
class VSpeeds:
    """Container for calculated V-speeds.

    All speeds in KIAS (Knots Indicated Airspeed).

    Attributes:
        v_s: Stall speed (clean configuration)
        v_so: Stall speed (landing configuration with full flaps)
        v_r: Rotation speed (takeoff)
        v_x: Best angle of climb speed
        v_y: Best rate of climb speed
        v_2: Safe climb speed (multi-engine, one engine out)
    """

    v_s: float  # Stall speed clean (KIAS)
    v_so: float  # Stall speed landing config (KIAS)
    v_r: float  # Rotation speed (KIAS)
    v_x: float  # Best angle of climb (KIAS)
    v_y: float  # Best rate of climb (KIAS)
    v_2: float  # Safe climb speed (KIAS)


class VSpeedCalculator:
    """Calculate V-speeds based on weight and configuration.

    V-speeds are weight-dependent and follow the relationship:
    V_new = V_ref × sqrt(W_new / W_ref)

    Examples:
        >>> calc = VSpeedCalculator(reference_weight=2550.0, reference_vstall=47.0)
        >>> speeds = calc.calculate_vspeeds(weight_lbs=2000.0)
        >>> print(f"V_stall: {speeds.v_s:.1f} KIAS")
        V_stall: 41.4 KIAS
    """

    def __init__(
        self,
        reference_weight: float,
        reference_vstall: float,
        cl_max_clean: float = 1.4,
        cl_max_landing: float = 2.0,
    ):
        """Initialize V-speed calculator.

        Args:
            reference_weight: Reference weight for POH data (lbs)
            reference_vstall: Stall speed at reference weight (KIAS)
            cl_max_clean: Maximum lift coefficient (clean config)
            cl_max_landing: Maximum lift coefficient (landing config, full flaps)
        """
        self.reference_weight = reference_weight
        self.reference_vstall = reference_vstall
        self.cl_max_clean = cl_max_clean
        self.cl_max_landing = cl_max_landing

        logger.info(
            f"VSpeedCalculator initialized: ref_weight={reference_weight:.0f} lbs, "
            f"ref_vstall={reference_vstall:.1f} KIAS"
        )

    def calculate_vstall(self, weight_lbs: float, density_altitude_ft: float = 0.0) -> float:
        """Calculate stall speed for given weight.

        V_stall = V_ref × sqrt(W / W_ref) × sqrt(ρ_ref / ρ)

        Args:
            weight_lbs: Current aircraft weight (lbs)
            density_altitude_ft: Density altitude (ft), affects air density

        Returns:
            Stall speed in KIAS

        Note:
            Indicated airspeed accounts for density changes automatically,
            so density altitude correction is minimal for IAS.
        """
        # Weight correction (primary factor)
        weight_ratio = weight_lbs / self.reference_weight
        vstall = self.reference_vstall * math.sqrt(weight_ratio)

        # Density altitude has minimal effect on IAS (vs TAS)
        # For simplicity, we'll ignore it for IAS calculations

        return vstall

    def calculate_vstall_landing(self, weight_lbs: float) -> float:
        """Calculate stall speed in landing configuration (full flaps).

        Landing config has lower stall speed due to higher CL_max.

        Args:
            weight_lbs: Current aircraft weight (lbs)

        Returns:
            Landing stall speed in KIAS
        """
        # Clean stall speed
        vs_clean = self.calculate_vstall(weight_lbs)

        # Landing stall speed is lower due to flaps
        # V_so = V_s × sqrt(CL_max_clean / CL_max_landing)
        cl_ratio = math.sqrt(self.cl_max_clean / self.cl_max_landing)
        vs_landing = vs_clean * cl_ratio

        return vs_landing

    def calculate_vspeeds(self, weight_lbs: float, density_altitude_ft: float = 0.0) -> VSpeeds:
        """Calculate all V-speeds for current weight.

        V-speed relationships (typical for light aircraft):
        - V_SO: Stall speed landing config (lower due to flaps)
        - V_S: Stall speed clean
        - V_R: 1.1 × V_S (rotation speed)
        - V_X: 1.25 × V_S (best angle of climb)
        - V_Y: 1.5 × V_S (best rate of climb)
        - V_2: 1.2 × V_S (safe climb speed, multi-engine)

        Args:
            weight_lbs: Current aircraft weight (lbs)
            density_altitude_ft: Density altitude (ft)

        Returns:
            VSpeeds object with all calculated speeds

        Examples:
            >>> calc = VSpeedCalculator(2550.0, 47.0)
            >>> speeds = calc.calculate_vspeeds(2550.0)
            >>> speeds.v_r
            51.7
        """
        # Calculate stall speeds
        v_s = self.calculate_vstall(weight_lbs, density_altitude_ft)
        v_so = self.calculate_vstall_landing(weight_lbs)

        # Derive other speeds from stall speed
        v_r = v_s * 1.1  # Rotation speed (10% above stall)
        v_x = v_s * 1.25  # Best angle of climb
        v_y = v_s * 1.5  # Best rate of climb
        v_2 = v_s * 1.2  # Safe climb speed

        vspeeds = VSpeeds(v_s=v_s, v_so=v_so, v_r=v_r, v_x=v_x, v_y=v_y, v_2=v_2)

        logger.debug(
            f"V-speeds at {weight_lbs:.0f} lbs: V_S={v_s:.1f}, V_R={v_r:.1f}, "
            f"V_X={v_x:.1f}, V_Y={v_y:.1f} KIAS"
        )

        return vspeeds

    def calculate_vspeed_for_config(self, weight_lbs: float, flap_setting: int = 0) -> float:
        """Calculate stall speed for specific flap configuration.

        Args:
            weight_lbs: Current aircraft weight (lbs)
            flap_setting: Flap deflection (0=clean, 10, 20, 30=full)

        Returns:
            Stall speed in KIAS for configuration

        Note:
            Simplified model: interpolates between clean and landing CL_max.
        """
        # Clean config
        if flap_setting == 0:
            return self.calculate_vstall(weight_lbs)

        # Landing config (full flaps)
        if flap_setting >= 30:
            return self.calculate_vstall_landing(weight_lbs)

        # Intermediate flap settings: interpolate CL_max
        # flap_setting: 10° → 1/3 benefit, 20° → 2/3 benefit
        flap_fraction = flap_setting / 30.0  # Normalize to 0-1
        cl_max_current = (
            self.cl_max_clean + (self.cl_max_landing - self.cl_max_clean) * flap_fraction
        )

        # Calculate stall speed for this CL_max
        vs_clean = self.calculate_vstall(weight_lbs)
        cl_ratio = math.sqrt(self.cl_max_clean / cl_max_current)
        vs_config = vs_clean * cl_ratio

        return vs_config

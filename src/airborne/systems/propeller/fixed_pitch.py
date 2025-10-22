"""Fixed-pitch propeller model.

This module implements a fixed-pitch propeller suitable for light aircraft
like the Cessna 172. Fixed-pitch props have a blade angle that cannot be
adjusted in flight, so efficiency varies significantly with airspeed.
"""

import math

from airborne.core.logging_system import get_logger
from airborne.systems.propeller.base import IPropeller

logger = get_logger(__name__)


class FixedPitchPropeller(IPropeller):
    """Fixed-pitch propeller model for piston aircraft.

    Models a propeller with fixed blade pitch angle, typical of light aircraft.
    Efficiency varies with advance ratio - optimal at one specific speed,
    less efficient at low/high speeds.

    Physics model:
    - Advance ratio: J = v / (n × D) where v=airspeed, n=rps, D=diameter
    - Static thrust (v≈0): T = sqrt(η × P × ρ × A)
    - Dynamic thrust (v>0): T = (η × P) / v
    - Efficiency η varies with J (peaks at cruise, drops at static/high speed)

    Examples:
        Cessna 172 propeller (75" diameter, climb pitch):
        >>> prop = FixedPitchPropeller(
        ...     diameter_m=1.905,
        ...     pitch_ratio=0.6,
        ...     efficiency_static=0.50,
        ...     efficiency_cruise=0.80
        ... )
        >>> # Static thrust (full power, v=0)
        >>> thrust = prop.calculate_thrust(
        ...     power_hp=180,
        ...     rpm=2700,
        ...     airspeed_mps=0.0,
        ...     air_density_kgm3=1.225
        ... )
        >>> print(f"Static thrust: {thrust:.0f} N")  # ~785 N (176 lbf)
    """

    def __init__(
        self,
        diameter_m: float,
        pitch_ratio: float = 0.6,
        efficiency_static: float = 0.50,
        efficiency_cruise: float = 0.80,
        cruise_advance_ratio: float = 0.6,
    ):
        """Initialize fixed-pitch propeller.

        Args:
            diameter_m: Propeller diameter in meters.
            pitch_ratio: Propeller pitch / diameter ratio (typical: 0.5-0.7).
            efficiency_static: Efficiency at zero airspeed (typical: 0.45-0.55).
            efficiency_cruise: Peak efficiency at cruise speed (typical: 0.75-0.85).
            cruise_advance_ratio: Advance ratio where efficiency peaks (typical: 0.5-0.7).

        Note:
            Pitch ratio determines optimal operating speed. Higher pitch = faster cruise,
            lower static thrust. Climb props use lower pitch (~0.5), cruise props higher (~0.7).
        """
        self.diameter = diameter_m
        self.pitch_ratio = pitch_ratio
        self.efficiency_static = efficiency_static
        self.efficiency_cruise = efficiency_cruise
        self.cruise_advance_ratio = cruise_advance_ratio

        # Derived properties
        self.disc_area = math.pi * (diameter_m / 2.0) ** 2

        logger.info(
            f"FixedPitchPropeller initialized: D={diameter_m:.3f}m, "
            f"pitch_ratio={pitch_ratio:.2f}, "
            f"η_static={efficiency_static:.2f}, η_cruise={efficiency_cruise:.2f}"
        )

    def calculate_thrust(
        self,
        power_hp: float,
        rpm: float,
        airspeed_mps: float,
        air_density_kgm3: float,
    ) -> float:
        """Calculate thrust force in Newtons.

        Uses different formulas for static (v≈0) vs dynamic (v>0) conditions:
        - Static: T = sqrt(η_static × P × ρ × A) - momentum theory
        - Dynamic: T = (η × P) / v - power-velocity relationship

        Args:
            power_hp: Engine power output in horsepower.
            rpm: Engine/propeller RPM.
            airspeed_mps: True airspeed in meters per second.
            air_density_kgm3: Air density in kg/m³.

        Returns:
            Thrust force in Newtons.

        Note:
            Returns 0 if power or RPM is zero (engine not running).
        """
        # No thrust if engine not running
        if power_hp <= 0.0 or rpm <= 0.0:
            return 0.0

        # Convert horsepower to watts
        power_watts = power_hp * 745.7

        # Get propeller efficiency for current conditions
        efficiency = self.get_efficiency(airspeed_mps, rpm)

        # Calculate thrust based on airspeed regime
        if airspeed_mps < 1.0:
            # Static or very low speed: use thrust coefficient method
            # More accurate than simple momentum theory
            # T = C_T × ρ × n² × D⁴
            # Where C_T (thrust coefficient) ≈ 0.08-0.12 for fixed-pitch props

            # Calculate rotations per second
            rps = rpm / 60.0

            # Thrust coefficient varies with pitch and efficiency
            # Higher pitch = higher C_T, higher efficiency = higher C_T
            c_t = 0.06 + (self.pitch_ratio - 0.5) * 0.1 + efficiency * 0.04
            c_t = max(0.04, min(0.15, c_t))  # Clamp to realistic range

            # Calculate static thrust
            thrust = c_t * air_density_kgm3 * (rps**2) * (self.diameter**4)
        else:
            # Dynamic thrust: use power-velocity relationship
            # T = (η × P) / v
            # As speed increases, thrust decreases for given power
            thrust = (efficiency * power_watts) / airspeed_mps

        return thrust

    def get_efficiency(self, airspeed_mps: float, rpm: float) -> float:
        """Get current propeller efficiency based on advance ratio.

        Efficiency curve for fixed-pitch propeller:
        - Low J (static, takeoff): Low efficiency (~0.50)
        - Optimal J (cruise): Peak efficiency (~0.80)
        - High J (high speed): Decreasing efficiency (prop stalling)

        Args:
            airspeed_mps: True airspeed in meters per second.
            rpm: Engine/propeller RPM.

        Returns:
            Propeller efficiency as fraction (0.0 to 1.0).

        Note:
            Uses simplified parabolic efficiency curve. Real propellers have
            complex efficiency maps based on blade design, Mach number, etc.
        """
        # No efficiency if not spinning
        if rpm <= 0.0:
            return 0.0

        # Calculate advance ratio: J = v / (n × D)
        # n = revolutions per second, D = diameter
        rps = rpm / 60.0
        advance_ratio = airspeed_mps / (rps * self.diameter) if rps > 0 else 0.0

        # Efficiency curve (simplified parabolic model)
        # Peaks at cruise_advance_ratio, drops off at low/high J
        if advance_ratio < 0.1:
            # Static or very low speed
            efficiency = self.efficiency_static
        elif advance_ratio < self.cruise_advance_ratio:
            # Accelerating to cruise - efficiency increases
            # Linear interpolation from static to cruise
            t = advance_ratio / self.cruise_advance_ratio
            efficiency = (
                self.efficiency_static + (self.efficiency_cruise - self.efficiency_static) * t
            )
        elif advance_ratio < self.cruise_advance_ratio * 1.5:
            # Near cruise - maintain peak efficiency
            efficiency = self.efficiency_cruise
        else:
            # High speed - prop begins to stall, efficiency drops
            # Quadratic falloff
            excess = advance_ratio - (self.cruise_advance_ratio * 1.5)
            falloff = min(0.5, excess * 0.3)  # Max 50% reduction
            efficiency = self.efficiency_cruise - falloff

        # Clamp to valid range
        return max(0.0, min(1.0, efficiency))

    def get_advance_ratio(self, airspeed_mps: float, rpm: float) -> float:
        """Get current advance ratio J = v / (n × D).

        Args:
            airspeed_mps: True airspeed in meters per second.
            rpm: Engine/propeller RPM.

        Returns:
            Advance ratio (dimensionless).

        Note:
            Advance ratio determines operating regime:
            - J < 0.2: Takeoff/climb
            - J = 0.5-0.7: Cruise
            - J > 1.0: High speed (propeller stalling)
        """
        if rpm <= 0:
            return 0.0

        rps = rpm / 60.0
        return airspeed_mps / (rps * self.diameter)

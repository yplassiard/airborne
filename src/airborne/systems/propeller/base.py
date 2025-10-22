"""Base interface for propeller models.

This module defines the interface that all propeller models must implement.
Propellers convert engine power to thrust, with efficiency varying based on
airspeed, RPM, and blade design.
"""

from abc import ABC, abstractmethod


class IPropeller(ABC):
    """Interface for propeller thrust calculation.

    Different propeller types (fixed-pitch, constant-speed, turbofan) implement
    this interface to provide thrust based on engine power and flight conditions.

    The propeller model accounts for:
    - Advance ratio (v / (n × D)) - ratio of forward speed to prop tip speed
    - Propeller efficiency - varies with advance ratio and blade design
    - Air density effects - thrust decreases with altitude
    - Static vs dynamic thrust - different formulas for v=0 vs v>0
    """

    @abstractmethod
    def calculate_thrust(
        self,
        power_hp: float,
        rpm: float,
        airspeed_mps: float,
        air_density_kgm3: float,
    ) -> float:
        """Calculate thrust force in Newtons.

        Args:
            power_hp: Engine power output in horsepower.
            rpm: Engine/propeller RPM (revolutions per minute).
            airspeed_mps: True airspeed in meters per second.
            air_density_kgm3: Air density in kg/m³.

        Returns:
            Thrust force in Newtons.

        Note:
            Implementation should handle v=0 (static thrust) as a special case,
            using momentum theory rather than power/velocity formula.
        """
        pass

    @abstractmethod
    def get_efficiency(self, airspeed_mps: float, rpm: float) -> float:
        """Get current propeller efficiency (0.0 to 1.0).

        Args:
            airspeed_mps: True airspeed in meters per second.
            rpm: Engine/propeller RPM.

        Returns:
            Propeller efficiency as a fraction (0.0 = no thrust, 1.0 = ideal).

        Note:
            Efficiency typically peaks at cruise speed and drops at low/high speeds.
        """
        pass

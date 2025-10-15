"""Base classes for aircraft engines.

This module defines abstract interfaces for engines that can be implemented
differently for various engine types (piston, turbine, electric).

Typical usage:
    class MyEngine(IEngine):
        def initialize(self, config: dict) -> None:
            # Initialize engine parameters
            pass

        def update(self, dt: float, controls: EngineControls,
                   electrical_available: bool, fuel_available: float) -> None:
            # Calculate RPM, power output, fuel consumption
            pass
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class EngineType(Enum):
    """Engine types.

    Different engine types have vastly different operating characteristics,
    power curves, fuel consumption, and control requirements.
    """

    PISTON_NATURALLY_ASPIRATED = "piston_naturally_aspirated"  # Cessna 172
    PISTON_TURBOCHARGED = "piston_turbocharged"  # Cessna 210
    PISTON_SUPERCHARGED = "piston_supercharged"  # WWII fighters
    TURBOPROP = "turboprop"  # Cessna Caravan, King Air
    TURBOFAN = "turbofan"  # Boeing 737, A320
    TURBOJET = "turbojet"  # Early jets, military
    ELECTRIC = "electric"  # Future electric aircraft


class EngineIgnitionType(Enum):
    """Ignition system types.

    Different ignition systems have different electrical requirements
    and failure modes.
    """

    MAGNETO = "magneto"  # Self-powered magneto (piston engines, no electrical needed)
    ELECTRONIC = "electronic"  # Electronic ignition (modern pistons, requires electrical)
    FADEC = "fadec"  # Full Authority Digital Engine Control (jets, fly-by-wire)


@dataclass
class EngineState:
    """Current engine state.

    Published via messages every frame so other systems (physics, instruments,
    audio) can monitor engine operation.

    Attributes:
        engine_type: Type of engine
        running: Whether engine is currently running
        power_output_hp: Power output in horsepower (or thrust_lbs for jets)
        fuel_flow_gph: Current fuel consumption in gallons per hour
        temperature_c: Primary temperature (EGT, ITT, or oil temp)

        # Piston-specific attributes
        rpm: Engine revolutions per minute
        manifold_pressure_inhg: Manifold pressure in inches of mercury
        oil_pressure_psi: Oil pressure in PSI
        oil_temperature_c: Oil temperature in celsius
        cylinder_head_temp_c: Cylinder head temperature

        # Turbine-specific attributes
        n1_percent: Low-pressure spool speed (% of max)
        n2_percent: High-pressure spool speed (% of max)
        itt_c: Inter-turbine temperature in celsius
        epr: Engine Pressure Ratio

        # Status
        starter_engaged: Whether starter motor is engaged
        warnings: List of warning codes (OVERSPEED, OVERTEMP, LOW_OIL_PRESSURE)
        failures: List of failure codes (ENGINE_FAILURE, ENGINE_FIRE, SEIZED)
    """

    # Common to all engines
    engine_type: EngineType
    running: bool
    power_output_hp: float  # Or thrust_lbs for jets
    fuel_flow_gph: float
    temperature_c: float

    # Piston-specific (None for turbines)
    rpm: float | None = None
    manifold_pressure_inhg: float | None = None
    oil_pressure_psi: float | None = None
    oil_temperature_c: float | None = None
    cylinder_head_temp_c: float | None = None

    # Turbine-specific (None for pistons)
    n1_percent: float | None = None  # Low-pressure spool
    n2_percent: float | None = None  # High-pressure spool
    itt_c: float | None = None  # Inter-turbine temperature
    epr: float | None = None  # Engine Pressure Ratio

    # Status
    starter_engaged: bool = False
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


@dataclass
class EngineControls:
    """Engine control inputs.

    Different engine types use different subsets of these controls.

    Attributes:
        # Common controls
        throttle: Throttle position (0.0 = idle, 1.0 = full power)
        mixture: Mixture control (0.0 = cutoff, 1.0 = full rich, piston only)

        # Piston-specific controls
        magneto_left: Left magneto switch (on/off)
        magneto_right: Right magneto switch (on/off)
        starter: Starter motor engaged
        carburetor_heat: Carburetor heat on/off
        propeller_rpm: Propeller RPM control for constant-speed prop (0.0-1.0)

        # Turbine-specific controls
        ignition: Ignition system on/off
        fuel_cutoff: Fuel cutoff lever (emergency shutdown)
        reverse_thrust: Thrust reverser deployed (landing only)
    """

    # Common controls
    throttle: float = 0.0  # 0.0 = idle, 1.0 = full power
    mixture: float = 1.0  # 0.0 = cutoff, 1.0 = full rich (piston only)

    # Piston-specific
    magneto_left: bool = False
    magneto_right: bool = False
    starter: bool = False
    carburetor_heat: bool = False
    propeller_rpm: float = 1.0  # For constant-speed prop

    # Turbine-specific
    ignition: bool = False
    fuel_cutoff: bool = False
    reverse_thrust: bool = False


class IEngine(ABC):
    """Abstract base class for aircraft engines.

    Different engine types implement this interface with varying complexity:
    - Piston engines: RPM, manifold pressure, magnetos, mixture
    - Turboprop engines: N1/N2, ITT, FADEC, beta range
    - Turbofan engines: N1/N2, EPR, thrust reversers, dual-spool physics

    Example implementations:
        - SimplePistonEngine: Cessna 172 (Lycoming O-360)
        - TurbochargedPistonEngine: Cessna 210 (Continental TSIO-520)
        - TurbopropEngine: Cessna Caravan (Pratt & Whitney PT6A)
        - TurbofanEngine: Boeing 737 (CFM56)
    """

    @abstractmethod
    def initialize(self, config: dict) -> None:
        """Initialize engine from configuration.

        Args:
            config: Configuration dictionary with engine specifications,
                performance characteristics, and limits.

        Example config (piston):
            {
                "engine_type": "piston_naturally_aspirated",
                "max_power_hp": 180,
                "max_rpm": 2700,
                "idle_rpm": 600,
                "displacement_liters": 5.9,
                "fuel_consumption_max_gph": 9.5
            }

        Example config (turbofan):
            {
                "engine_type": "turbofan",
                "max_thrust_lbs": 27300,
                "bypass_ratio": 5.1,
                "max_n1": 100.0,
                "max_n2": 100.0,
                "max_itt_c": 950.0
            }
        """
        pass

    @abstractmethod
    def update(
        self,
        dt: float,
        controls: EngineControls,
        electrical_available: bool,
        fuel_available: float,
    ) -> None:
        """Update engine state.

        Called every frame to update engine operation based on controls,
        available resources, and time.

        Args:
            dt: Delta time in seconds since last update
            controls: Current engine control positions
            electrical_available: Whether electrical power is available
                (for starter motor, FADEC, electronic ignition)
            fuel_available: Available fuel flow in gallons per hour
                (0.0 if fuel exhausted or selector OFF)

        Note:
            If fuel_available is 0.0, engine MUST die immediately (no grace period).
            If electrical not available and starter engaged, starter won't turn.
        """
        pass

    @abstractmethod
    def get_state(self) -> EngineState:
        """Get current engine state.

        Returns:
            EngineState with current RPM, power, temperatures, warnings, failures
        """
        pass

    @abstractmethod
    def get_thrust_force(self) -> float:
        """Get thrust force in pounds for physics calculations.

        For piston engines, converts horsepower to thrust based on propeller.
        For jet engines, returns direct thrust output.

        Returns:
            Thrust force in pounds (lbf)
        """
        pass

    @abstractmethod
    def can_start(self) -> bool:
        """Check if engine can start based on current conditions.

        Checks:
        - Fuel available
        - Ignition system active (magnetos ON or FADEC powered)
        - Starter motor has electrical power (if needed)
        - No critical failures

        Returns:
            True if engine can start, False otherwise
        """
        pass

    @abstractmethod
    def simulate_failure(self, failure_type: str) -> None:
        """Simulate engine failure for training scenarios.

        Args:
            failure_type: Type of failure to simulate:
                - "oil_pressure": Loss of oil pressure
                - "overheat": Engine overheating
                - "seizure": Engine seized (catastrophic)
                - "fire": Engine fire
                - "fuel_contamination": Water in fuel
                - "magneto_left": Left magneto failure
                - "magneto_right": Right magneto failure

        Note:
            This is for training/testing only. Real failures occur naturally
            from operating conditions (over-RPM, overtemp, oil starvation).
        """
        pass

    @abstractmethod
    def get_fuel_consumption_rate(self) -> float:
        """Get current fuel consumption rate.

        Returns:
            Fuel flow rate in gallons per hour
        """
        pass

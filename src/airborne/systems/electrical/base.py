"""Base classes for aircraft electrical systems.

This module defines abstract interfaces for electrical systems that can be
implemented differently for various aircraft types.

Typical usage:
    class MyElectricalSystem(IElectricalSystem):
        def initialize(self, config: dict) -> None:
            # Initialize battery, alternator, buses from config
            pass

        def update(self, dt: float, engine_rpm: float) -> None:
            # Calculate battery discharge/charge, bus voltages
            pass
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class BatteryType(Enum):
    """Battery chemistry types.

    Different aircraft use different battery technologies with varying
    characteristics (voltage curves, weight, temperature sensitivity).
    """

    LEAD_ACID = "lead_acid"  # Cessna 172, older aircraft (12V/24V)
    NICAD = "nicad"  # Some jets (28V)
    LITHIUM_ION = "lithium_ion"  # Modern aircraft (lighter, better performance)


class PowerSource(Enum):
    """Power generation sources.

    Aircraft can have multiple power sources for redundancy and different
    operating conditions (ground, flight, emergency).
    """

    BATTERY = "battery"  # Primary battery
    ALTERNATOR = "alternator"  # Belt-driven alternator (piston engines)
    GENERATOR = "generator"  # Engine-driven generator (turbine engines)
    APU_GENERATOR = "apu_generator"  # Auxiliary Power Unit generator (jets)
    EXTERNAL_POWER = "external_power"  # Ground power cart
    RAT = "rat"  # Ram Air Turbine (emergency power from windmilling turbine)


@dataclass
class ElectricalLoad:
    """Electrical load definition.

    Represents a single electrical consumer (light, pump, avionics, etc.)
    connected to the electrical system.

    Attributes:
        name: Load identifier (e.g., "nav_lights", "starter_motor")
        current_draw_amps: Current consumption in amperes when enabled
        essential: Whether this load is on essential/emergency bus
        enabled: Current state (on/off)
        min_voltage: Minimum voltage required for operation
    """

    name: str
    current_draw_amps: float
    essential: bool = False
    enabled: bool = False
    min_voltage: float = 10.0


@dataclass
class ElectricalBus:
    """Electrical bus (power distribution).

    Represents a power distribution bus that feeds multiple loads.
    Aircraft can have multiple buses (main, essential, avionics) with
    different power sources and priorities.

    Attributes:
        name: Bus identifier (e.g., "main_bus", "essential_bus")
        voltage_nominal: Nominal bus voltage (12V, 28V, etc.)
        voltage_current: Current measured bus voltage
        loads: List of electrical loads connected to this bus
        power_sources: List of power sources feeding this bus
    """

    name: str
    voltage_nominal: float
    voltage_current: float
    loads: list[ElectricalLoad] = field(default_factory=list)
    power_sources: list[PowerSource] = field(default_factory=list)


@dataclass
class ElectricalState:
    """Current electrical system state.

    This state is published via messages every frame so other systems
    can check power availability, voltage levels, and warnings.

    Attributes:
        buses: Dictionary of bus_name -> ElectricalBus
        battery_voltage: Current battery terminal voltage
        battery_soc_percent: State of charge (0-100%)
        battery_current_amps: Current flow (positive=charging, negative=discharging)
        alternator_output_amps: Current alternator/generator output
        total_load_amps: Total current draw from all enabled loads
        power_sources_available: List of currently active power sources
        warnings: List of warning codes (LOW_VOLTAGE, ALTERNATOR_FAILURE, etc.)
        failures: List of failure codes (BATTERY_DEAD, BUS_FAILURE, etc.)
    """

    buses: dict[str, ElectricalBus]
    battery_voltage: float
    battery_soc_percent: float
    battery_current_amps: float
    alternator_output_amps: float
    total_load_amps: float
    power_sources_available: list[PowerSource]
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


class IElectricalSystem(ABC):
    """Abstract base class for aircraft electrical systems.

    Different aircraft implement this interface with varying complexity:
    - Simple aircraft (Cessna 172): Single 12V battery, one alternator, one bus
    - Complex aircraft (Boeing 737): Dual 28V systems, multiple generators, bus ties
    - Advanced aircraft (A320): Complex bus logic, automatic load shedding, RAT

    Example implementations:
        - Simple12VElectricalSystem: Cessna 172
        - Simple28VElectricalSystem: Cessna 210
        - DualBus28VElectricalSystem: Boeing 737
        - AdvancedElectricalSystem: Airbus A320
    """

    @abstractmethod
    def initialize(self, config: dict) -> None:
        """Initialize electrical system from configuration.

        Args:
            config: Configuration dictionary with battery specs, alternator
                specs, bus configuration, and electrical loads.

        Example config:
            {
                "battery": {
                    "type": "lead_acid",
                    "voltage_nominal": 12.6,
                    "capacity_ah": 35.0
                },
                "alternator": {
                    "max_amps": 60.0,
                    "voltage_regulated": 14.0,
                    "rpm_threshold": 800
                },
                "loads": {
                    "starter_motor": {"amps": 150.0, "essential": True},
                    "nav_lights": {"amps": 1.5, "essential": False}
                }
            }
        """
        pass

    @abstractmethod
    def update(self, dt: float, engine_rpm: float) -> None:
        """Update electrical system state.

        Called every frame to update battery charge/discharge, alternator output,
        bus voltages, and load states.

        Args:
            dt: Delta time in seconds since last update
            engine_rpm: Engine RPM (drives alternator/generator, 0 if engine off)
        """
        pass

    @abstractmethod
    def get_state(self) -> ElectricalState:
        """Get current electrical system state.

        Returns:
            ElectricalState with current voltages, currents, warnings, failures
        """
        pass

    @abstractmethod
    def set_load_enabled(self, load_name: str, enabled: bool) -> bool:
        """Enable or disable an electrical load.

        Args:
            load_name: Name of load (e.g., "nav_lights", "fuel_pump")
            enabled: True to enable load, False to disable

        Returns:
            True if successful, False if load not found or bus has failed
        """
        pass

    @abstractmethod
    def get_bus_voltage(self, bus_name: str) -> float:
        """Get voltage of a specific bus.

        Args:
            bus_name: Name of bus (e.g., "main_bus", "essential_bus")

        Returns:
            Current bus voltage in volts, 0.0 if bus has failed
        """
        pass

    @abstractmethod
    def can_draw_current(self, amps: float) -> bool:
        """Check if system can supply requested current.

        Used by high-draw systems (starter motor) to check if enough
        power is available before attempting to draw current.

        Args:
            amps: Requested current in amperes

        Returns:
            True if system can supply current, False if would cause brownout/failure
        """
        pass

    @abstractmethod
    def simulate_failure(self, failure_type: str) -> None:
        """Simulate electrical failure for training scenarios.

        Args:
            failure_type: Type of failure to simulate:
                - "alternator": Alternator/generator failure
                - "battery": Battery failure (internal short, dead cell)
                - "bus": Specific bus failure
                - "overload": Electrical overload condition

        Note:
            This is for training/testing only. Real failures occur naturally
            from system conditions (overload, overheating, etc.)
        """
        pass

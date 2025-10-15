"""Base classes for aircraft fuel systems.

This module defines abstract interfaces for fuel systems that can be
implemented differently for various aircraft types and fuel configurations.

Typical usage:
    class MyFuelSystem(IFuelSystem):
        def initialize(self, config: dict) -> None:
            # Create tanks, set fuel type, configure selector
            pass

        def update(self, dt: float, fuel_flow_gph: float) -> None:
            # Consume fuel from selected tanks
            pass
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class FuelType(Enum):
    """Fuel types used in aviation.

    Different fuel types have different weights, energy content, and
    engine compatibility.
    """

    AVGAS_100LL = "avgas_100ll"  # 6.0 lbs/gal, blue color, piston engines
    JET_A = "jet_a"  # 6.7 lbs/gal, kerosene-based, turbine engines
    JET_A1 = "jet_a1"  # 6.7 lbs/gal, international variant, lower freeze point
    MOGAS = "mogas"  # 6.0 lbs/gal, automotive gasoline (some piston engines)


class FuelSelectorPosition(Enum):
    """Fuel selector valve positions.

    Different aircraft have different selector configurations based on
    tank arrangement and fuel system design.
    """

    OFF = "off"  # No fuel flow (used for engine shutdown, safety)
    LEFT = "left"  # Draw from left tank only
    RIGHT = "right"  # Draw from right tank only
    BOTH = "both"  # Draw from both left/right tanks (Cessna 172)
    CROSSFEED = "crossfeed"  # Cross-feed between tanks (multi-engine jets)
    CENTER = "center"  # Draw from center tank (multi-tank aircraft)
    ALL = "all"  # Draw from all tanks (some aircraft)


@dataclass
class FuelTank:
    """Fuel tank definition.

    Represents a single fuel tank with capacity, current quantity, and
    position (for center of gravity calculations).

    Attributes:
        name: Tank identifier (e.g., "left_main", "right_main", "center")
        capacity_total: Total tank capacity including unusable fuel (gallons)
        capacity_usable: Usable fuel capacity (gallons)
        current_quantity: Current fuel quantity (gallons)
        fuel_type: Type of fuel in this tank
        position: Tank position in aircraft coordinates (x, y, z) in feet
    """

    name: str
    capacity_total: float
    capacity_usable: float
    current_quantity: float
    fuel_type: FuelType
    position: tuple[float, float, float]  # (x, y, z) in aircraft frame


@dataclass
class FuelState:
    """Current fuel system state.

    This state is published via messages every frame so other systems
    (engine, physics, instruments) can monitor fuel status.

    Attributes:
        tanks: Dictionary of tank_name -> FuelTank
        total_quantity_gallons: Total fuel across all tanks
        total_usable_gallons: Total usable fuel (excluding unusable)
        total_weight_lbs: Total fuel weight for CG calculation
        fuel_selector_position: Current selector valve position
        fuel_flow_rate_gph: Current fuel consumption rate
        fuel_pressure_psi: Fuel pressure at engine (for engine feed)
        fuel_temperature_c: Fuel temperature in celsius
        center_of_gravity_shift: CG change due to fuel distribution (x, y, z)
        warnings: List of warning codes (LOW_FUEL, FUEL_IMBALANCE, etc.)
        failures: List of failure codes (FUEL_EXHAUSTED, PUMP_FAILURE, etc.)
        time_remaining_minutes: Estimated time remaining at current consumption
    """

    tanks: dict[str, FuelTank]
    total_quantity_gallons: float
    total_usable_gallons: float
    total_weight_lbs: float
    fuel_selector_position: FuelSelectorPosition
    fuel_flow_rate_gph: float
    fuel_pressure_psi: float
    fuel_temperature_c: float
    center_of_gravity_shift: tuple[float, float, float]
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    time_remaining_minutes: float | None = None


class IFuelSystem(ABC):
    """Abstract base class for aircraft fuel systems.

    Different aircraft implement this interface with varying complexity:
    - Simple aircraft (Cessna 172): Gravity-feed, two wing tanks, simple selector
    - Complex aircraft (Boeing 737): Multiple tanks, transfer pumps, auto management
    - Advanced aircraft (A320): FQMS with automatic fuel balancing

    Example implementations:
        - SimpleGravityFuelSystem: Cessna 172
        - FuelInjectionSystem: Cessna 182, Cessna 210
        - JetFuelSystem: Boeing 737
        - FQMS: Airbus A320 (Fuel Quantity Management System)
    """

    @abstractmethod
    def initialize(self, config: dict) -> None:
        """Initialize fuel system from configuration.

        Args:
            config: Configuration dictionary with tank specs, fuel type,
                selector positions, and pump configuration.

        Example config:
            {
                "tanks": {
                    "left": {
                        "capacity_total": 28.0,
                        "capacity_usable": 26.0,
                        "fuel_type": "avgas_100ll",
                        "position": [-5.0, 0.0, -8.0]
                    },
                    "right": {
                        "capacity_total": 28.0,
                        "capacity_usable": 26.0,
                        "fuel_type": "avgas_100ll",
                        "position": [-5.0, 0.0, 8.0]
                    }
                },
                "selector_positions": ["OFF", "LEFT", "RIGHT", "BOTH"],
                "fuel_pump_required": false
            }
        """
        pass

    @abstractmethod
    def update(self, dt: float, fuel_flow_gph: float) -> None:
        """Update fuel system state.

        Called every frame to consume fuel based on engine demand and
        update fuel quantities, CG shift, warnings.

        Args:
            dt: Delta time in seconds since last update
            fuel_flow_gph: Current fuel consumption rate in gallons per hour
                (from engine, 0.0 if engine not running)
        """
        pass

    @abstractmethod
    def get_state(self) -> FuelState:
        """Get current fuel system state.

        Returns:
            FuelState with current fuel quantities, selector position,
            warnings, and failures
        """
        pass

    @abstractmethod
    def set_selector_position(self, position: FuelSelectorPosition) -> bool:
        """Set fuel selector valve position.

        Args:
            position: Desired selector valve position

        Returns:
            True if position is valid for this aircraft, False if position
            not supported (e.g., some aircraft don't have "BOTH" position)
        """
        pass

    @abstractmethod
    def get_available_fuel_flow(self) -> float:
        """Get available fuel flow rate to engine.

        Calculates maximum fuel flow available based on:
        - Selector position
        - Fuel quantity in selected tanks
        - Pump operation (if required)
        - Fuel pressure

        Returns:
            Maximum available fuel flow in gallons per hour.
            Returns 0.0 if selector is OFF, tanks empty, or pump failed.

        Note:
            Engine will die if this returns 0.0 (no grace period, realistic failure).
        """
        pass

    @abstractmethod
    def set_pump_enabled(self, pump_name: str, enabled: bool) -> bool:
        """Enable or disable fuel pump.

        Some aircraft have electric boost pumps for:
        - Engine start
        - High altitude operation
        - Emergency backup

        Args:
            pump_name: Pump identifier (e.g., "left_boost", "right_boost")
            enabled: True to enable pump, False to disable

        Returns:
            True if successful, False if pump not found or insufficient
            electrical power available
        """
        pass

    @abstractmethod
    def refuel(self, tank_name: str, gallons: float) -> bool:
        """Add fuel to a tank (ground refueling operation).

        Args:
            tank_name: Tank to refuel (e.g., "left", "right", "center")
            gallons: Amount of fuel to add

        Returns:
            True if successful, False if tank not found or would overflow
            tank capacity
        """
        pass

    @abstractmethod
    def get_fuel_weight_distribution(self) -> dict[str, float]:
        """Get fuel weight per tank for CG calculation.

        Used by physics system to calculate aircraft weight and balance.

        Returns:
            Dictionary mapping tank_name -> weight_lbs
        """
        pass

    @abstractmethod
    def drain_tank(self, tank_name: str, gallons: float) -> float:
        """Drain fuel from a tank (maintenance, sampling, emergency dump).

        Args:
            tank_name: Tank to drain from
            gallons: Amount to drain (negative = drain all)

        Returns:
            Actual amount drained in gallons
        """
        pass

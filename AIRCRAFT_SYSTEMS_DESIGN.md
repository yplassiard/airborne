# Aircraft Systems Integration Design - Modular Architecture

## Executive Summary

This document outlines a **comprehensive, modular, and realistic** aircraft systems architecture for AirBorne. The design uses abstract base classes and plugin patterns to allow reusability across different aircraft types (Cessna 172, Boeing 737, jets, turboprops, etc.) while maintaining realistic behavior with **no forgiveness for pilot error**.

## Design Philosophy

### Core Principles

1. **Realism**: No forgiveness, realistic failure modes, actual consequences
2. **Modularity**: Base interfaces allow different implementations per aircraft type
3. **Configurability**: YAML-driven system specifications
4. **Extensibility**: Easy to add new aircraft with different systems
5. **Educational**: Post-crash analysis explains why the failure occurred

### Failure Philosophy

**NO Forgiving Behaviors**:
- ❌ Battery too low? Starter won't turn over. Period.
- ❌ Fuel exhausted? Engine quits immediately.
- ❌ Magnetos off? No ignition, engine won't start.
- ❌ Over-speed engine? Physical damage, reduced power or failure.
- ❌ Land gear-up? Aircraft damaged/destroyed.
- ❌ Run out of fuel? Deadstick landing or crash.

**Death/Failure Analysis**:
When aircraft is destroyed or flight ends in failure, generate detailed report:
```
=== FLIGHT FAILURE ANALYSIS ===

Failure Type: ENGINE FAILURE FOLLOWED BY FORCED LANDING
Time: 14:23:45 UTC
Location: 37.4219° N, 122.0847° W (3.2 NM SW of KPAO)
Altitude at Failure: 2,400 ft MSL
Airspeed at Failure: 95 knots

PRIMARY CAUSE: Fuel Exhaustion
- Left tank: 0.0 gallons (exhausted at 14:22:10)
- Right tank: 0.0 gallons (exhausted at 14:22:15)
- Fuel selector: BOTH
- Total flight time: 3 hours 14 minutes
- Last low fuel warning: 14:08:32 (15 minutes before exhaustion)
- Warning ignored: Pilot continued flight

SECONDARY FACTORS:
- Engine continued running for 5 seconds after fuel exhaustion (fuel in lines)
- Propeller windmilled during descent
- Pilot attempted restart (unsuccessful - no fuel)

AIRCRAFT STATE AT IMPACT:
- Ground speed: 45 knots
- Descent rate: 800 ft/min
- Configuration: Gear up, flaps up
- Attitude: Nose low, 15° right bank

IMPACT ANALYSIS:
- Impact force: 8.2 G (FATAL)
- Gear was retracted at impact (would have absorbed some energy)
- Terrain: Open field (good choice, but too fast)

LESSONS:
1. Monitor fuel gauges continuously
2. Land with 30-minute reserve minimum
3. Respond to low fuel warnings immediately
4. Deploy landing gear for forced landing (reduces impact force)
5. Flare more aggressively to reduce descent rate

Flight time: 3:14:32
Survival: UNSURVIVABLE
```

### Modularity for Multiple Aircraft

**Problem**: Different aircraft have different systems:
- Cessna 172: 12V electrical, gravity-feed fuel, piston engine
- Cessna 182: 28V electrical, fuel injection, constant-speed prop
- Boeing 737: 28V dual electrical, hydraulics, turbofan engines, APU
- Airbus A320: Fly-by-wire, FADEC, fuel management computers

**Solution**: Abstract base classes with aircraft-specific implementations.

---

## Architecture: Abstract Base Classes

### 1. Base Electrical System Interface

```python
# File: src/airborne/systems/electrical/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List


class BatteryType(Enum):
    """Battery chemistry types."""
    LEAD_ACID = "lead_acid"          # Cessna 172, older aircraft
    NICAD = "nicad"                   # Some jets
    LITHIUM_ION = "lithium_ion"      # Modern aircraft


class PowerSource(Enum):
    """Power generation sources."""
    BATTERY = "battery"
    ALTERNATOR = "alternator"         # Piston engines
    GENERATOR = "generator"           # Turbine engines
    APU_GENERATOR = "apu_generator"   # Auxiliary Power Unit
    EXTERNAL_POWER = "external_power" # Ground power
    RAT = "rat"                       # Ram Air Turbine (emergency)


@dataclass
class ElectricalLoad:
    """Electrical load definition.

    Attributes:
        name: Load name (e.g., "nav_lights", "starter_motor")
        current_draw_amps: Current draw in amperes
        essential: Whether this load is on essential bus
        enabled: Current state (on/off)
        min_voltage: Minimum voltage required to operate
    """
    name: str
    current_draw_amps: float
    essential: bool = False
    enabled: bool = False
    min_voltage: float = 10.0


@dataclass
class ElectricalBus:
    """Electrical bus (power distribution).

    Attributes:
        name: Bus name (e.g., "main_bus", "essential_bus", "avionics_bus")
        voltage_nominal: Nominal bus voltage
        voltage_current: Current bus voltage
        loads: Loads connected to this bus
        power_sources: Sources feeding this bus
    """
    name: str
    voltage_nominal: float
    voltage_current: float
    loads: List[ElectricalLoad]
    power_sources: List[PowerSource]


@dataclass
class ElectricalState:
    """Current electrical system state.

    Published via messages every frame for other systems.
    """
    buses: Dict[str, ElectricalBus]
    battery_voltage: float
    battery_soc_percent: float  # State of charge
    battery_current_amps: float  # Positive = charging, negative = discharging
    alternator_output_amps: float
    total_load_amps: float
    power_sources_available: List[PowerSource]
    warnings: List[str]  # "LOW_VOLTAGE", "ALTERNATOR_FAILURE", etc.
    failures: List[str]  # "BATTERY_DEAD", "BUS_FAILURE", etc.


class IElectricalSystem(ABC):
    """Abstract base class for aircraft electrical systems.

    Different aircraft implement this interface:
    - Cessna 172: Simple12VElectricalSystem
    - Cessna 210: Simple28VElectricalSystem
    - Boeing 737: DualBus28VElectricalSystem
    - Airbus A320: AdvancedElectricalSystem (with complex bus logic)
    """

    @abstractmethod
    def initialize(self, config: Dict) -> None:
        """Initialize electrical system from config."""
        pass

    @abstractmethod
    def update(self, dt: float, engine_rpm: float) -> None:
        """Update electrical system state.

        Args:
            dt: Delta time in seconds
            engine_rpm: Engine RPM (drives alternator/generator)
        """
        pass

    @abstractmethod
    def get_state(self) -> ElectricalState:
        """Get current electrical state."""
        pass

    @abstractmethod
    def set_load_enabled(self, load_name: str, enabled: bool) -> bool:
        """Enable/disable an electrical load.

        Args:
            load_name: Name of load (e.g., "nav_lights")
            enabled: True to enable, False to disable

        Returns:
            True if successful, False if load not found or bus failed
        """
        pass

    @abstractmethod
    def get_bus_voltage(self, bus_name: str) -> float:
        """Get voltage of specific bus.

        Args:
            bus_name: Name of bus (e.g., "main_bus")

        Returns:
            Current bus voltage, 0.0 if bus failed
        """
        pass

    @abstractmethod
    def can_draw_current(self, amps: float) -> bool:
        """Check if system can supply requested current.

        Args:
            amps: Requested current in amperes

        Returns:
            True if available, False if would overload
        """
        pass

    @abstractmethod
    def simulate_failure(self, failure_type: str) -> None:
        """Simulate electrical failure for training.

        Args:
            failure_type: "alternator", "battery", "bus", etc.
        """
        pass
```

### 2. Base Fuel System Interface

```python
# File: src/airborne/systems/fuel/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class FuelType(Enum):
    """Fuel types."""
    AVGAS_100LL = "avgas_100ll"  # 6.0 lbs/gal, piston engines
    JET_A = "jet_a"               # 6.7 lbs/gal, turbine engines
    JET_A1 = "jet_a1"             # 6.7 lbs/gal, international
    MOGAS = "mogas"               # 6.0 lbs/gal, automotive gas (some pistons)


class FuelSelectorPosition(Enum):
    """Fuel selector valve positions."""
    OFF = "off"
    LEFT = "left"
    RIGHT = "right"
    BOTH = "both"
    CROSSFEED = "crossfeed"  # Jets
    CENTER = "center"         # Multi-tank aircraft
    ALL = "all"


@dataclass
class FuelTank:
    """Fuel tank definition.

    Attributes:
        name: Tank name (e.g., "left_main", "right_main", "center", "tip")
        capacity_total: Total tank capacity (gallons)
        capacity_usable: Usable fuel capacity (gallons)
        current_quantity: Current fuel quantity (gallons)
        fuel_type: Type of fuel
        position: Tank position (affects CG calculation)
    """
    name: str
    capacity_total: float
    capacity_usable: float
    current_quantity: float
    fuel_type: FuelType
    position: tuple[float, float, float]  # (x, y, z) in aircraft coordinates


@dataclass
class FuelState:
    """Current fuel system state.

    Published via messages every frame.
    """
    tanks: Dict[str, FuelTank]
    total_quantity_gallons: float
    total_usable_gallons: float
    total_weight_lbs: float
    fuel_selector_position: FuelSelectorPosition
    fuel_flow_rate_gph: float  # Current consumption rate
    fuel_pressure_psi: float
    fuel_temperature_c: float
    center_of_gravity_shift: tuple[float, float, float]  # CG change due to fuel
    warnings: List[str]  # "LOW_FUEL", "FUEL_IMBALANCE", etc.
    failures: List[str]  # "FUEL_EXHAUSTED", "FUEL_PUMP_FAILURE", etc.
    time_remaining_minutes: Optional[float]  # At current consumption rate


class IFuelSystem(ABC):
    """Abstract base class for aircraft fuel systems.

    Different aircraft implementations:
    - Cessna 172: Simple gravity-feed dual tanks
    - Cessna 210: Fuel injection system with electric pump
    - Boeing 737: Multi-tank system with transfer pumps
    - Airbus A320: FQMS (Fuel Quantity Management System) with automatic transfer
    """

    @abstractmethod
    def initialize(self, config: Dict) -> None:
        """Initialize fuel system from config."""
        pass

    @abstractmethod
    def update(self, dt: float, fuel_flow_gph: float) -> None:
        """Update fuel system state.

        Args:
            dt: Delta time in seconds
            fuel_flow_gph: Current fuel consumption in gallons per hour
        """
        pass

    @abstractmethod
    def get_state(self) -> FuelState:
        """Get current fuel state."""
        pass

    @abstractmethod
    def set_selector_position(self, position: FuelSelectorPosition) -> bool:
        """Set fuel selector valve position.

        Args:
            position: Desired selector position

        Returns:
            True if successful, False if invalid position for this aircraft
        """
        pass

    @abstractmethod
    def get_available_fuel_flow(self) -> float:
        """Get available fuel flow rate.

        Returns:
            Available fuel flow in gallons per hour.
            Returns 0.0 if selector OFF or tanks empty.
        """
        pass

    @abstractmethod
    def set_pump_enabled(self, pump_name: str, enabled: bool) -> bool:
        """Enable/disable fuel pump (if aircraft has electric pumps).

        Args:
            pump_name: Pump name (e.g., "left_boost", "right_boost")
            enabled: True to enable

        Returns:
            True if successful, False if pump not found or no power
        """
        pass

    @abstractmethod
    def refuel(self, tank_name: str, gallons: float) -> bool:
        """Add fuel to tank (ground refueling).

        Args:
            tank_name: Tank to refuel
            gallons: Amount to add

        Returns:
            True if successful, False if tank not found or overfill
        """
        pass

    @abstractmethod
    def get_fuel_weight_distribution(self) -> Dict[str, float]:
        """Get fuel weight per tank (for CG calculation).

        Returns:
            Dict of tank_name -> weight_lbs
        """
        pass


```

### 3. Base Engine Interface

```python
# File: src/airborne/systems/engines/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


class EngineType(Enum):
    """Engine types."""
    PISTON_NATURALLY_ASPIRATED = "piston_naturally_aspirated"
    PISTON_TURBOCHARGED = "piston_turbocharged"
    PISTON_SUPERCHARGED = "piston_supercharged"
    TURBOPROP = "turboprop"
    TURBOFAN = "turbofan"
    TURBOJET = "turbojet"


class EngineIgnitionType(Enum):
    """Ignition system types."""
    MAGNETO = "magneto"        # Piston engines (self-powered)
    ELECTRONIC = "electronic"  # Modern piston engines (requires electrical)
    FADEC = "fadec"            # Full Authority Digital Engine Control (jets)


@dataclass
class EngineState:
    """Current engine state.

    Published via messages every frame.
    """
    # Common to all engines
    engine_type: EngineType
    running: bool
    power_output_hp: float  # Or thrust_lbs for jets
    fuel_flow_gph: float
    temperature_c: float  # EGT, ITT, or oil temp depending on engine

    # Piston-specific
    rpm: Optional[float] = None
    manifold_pressure_inhg: Optional[float] = None
    oil_pressure_psi: Optional[float] = None
    oil_temperature_c: Optional[float] = None
    cylinder_head_temp_c: Optional[float] = None

    # Turbine-specific
    n1_percent: Optional[float] = None  # Low-pressure spool
    n2_percent: Optional[float] = None  # High-pressure spool
    itt_c: Optional[float] = None       # Inter-turbine temperature
    epr: Optional[float] = None         # Engine Pressure Ratio

    # Status
    starter_engaged: bool = False
    warnings: list[str] = None  # "OVERSPEED", "OVERTEMP", "LOW_OIL_PRESSURE"
    failures: list[str] = None  # "ENGINE_FAILURE", "ENGINE_FIRE", "SEIZED"

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
        if self.failures is None:
            self.failures = []


@dataclass
class EngineControls:
    """Engine control inputs."""
    # Common
    throttle: float = 0.0  # 0.0 = idle, 1.0 = full power
    mixture: float = 1.0   # 0.0 = cutoff, 1.0 = full rich (piston only)

    # Piston-specific
    magneto_left: bool = False
    magneto_right: bool = False
    starter: bool = False
    carburetor_heat: bool = False
    propeller_rpm: float = 1.0  # Constant-speed prop (0.0-1.0)

    # Turbine-specific
    ignition: bool = False
    fuel_cutoff: bool = False
    reverse_thrust: bool = False


class IEngine(ABC):
    """Abstract base class for aircraft engines.

    Different implementations:
    - SimplePistonEngine: Cessna 172 (Lycoming O-360)
    - TurbochargedPistonEngine: Cessna 210
    - TurbopropEngine: Cessna Caravan (PT6A)
    - TurbofanEngine: Boeing 737 (CFM56)
    """

    @abstractmethod
    def initialize(self, config: Dict) -> None:
        """Initialize engine from config."""
        pass

    @abstractmethod
    def update(self, dt: float, controls: EngineControls,
               electrical_available: bool, fuel_available: float) -> None:
        """Update engine state.

        Args:
            dt: Delta time in seconds
            controls: Engine control inputs
            electrical_available: Whether electrical power available for starter
            fuel_available: Available fuel flow in GPH (0.0 if no fuel)
        """
        pass

    @abstractmethod
    def get_state(self) -> EngineState:
        """Get current engine state."""
        pass

    @abstractmethod
    def get_thrust_force(self) -> float:
        """Get thrust force in pounds.

        Returns:
            Thrust force for physics calculations.
        """
        pass

    @abstractmethod
    def simulate_failure(self, failure_type: str) -> None:
        """Simulate engine failure for training.

        Args:
            failure_type: "oil_pressure", "overheat", "seizure", "fire", etc.
        """
        pass
```

---

## Concrete Implementations

### Cessna 172: Simple12VElectricalSystem

```python
# File: src/airborne/systems/electrical/simple_12v.py

class Simple12VElectricalSystem(IElectricalSystem):
    """
    Simple 12V electrical system for Cessna 172.

    Components:
    - 12V 35Ah lead-acid battery
    - 60A belt-driven alternator
    - Single main bus
    - No redundancy

    Realistic behavior:
    - Battery voltage: 12.6V (full) → 10.5V (dead)
    - Starter requires 11.0V minimum (150A draw)
    - Alternator requires 800+ RPM
    - Battery can die completely (not forgiving)
    """

    def __init__(self):
        # Battery model
        self.battery_capacity_ah = 35.0
        self.battery_current_ah = 35.0  # Start full
        self.battery_voltage = 12.6
        self.battery_internal_resistance = 0.05  # Ohms

        # Alternator model
        self.alternator_max_amps = 60.0
        self.alternator_voltage_regulated = 14.0
        self.alternator_rpm_threshold = 800

        # Main bus
        self.main_bus = ElectricalBus(
            name="main_bus",
            voltage_nominal=12.0,
            voltage_current=12.6,
            loads=[],
            power_sources=[]
        )

        # Electrical loads (realistic Cessna 172 values)
        self.loads = {
            "master_relay": ElectricalLoad("master_relay", 0.1, essential=True),
            "starter_motor": ElectricalLoad("starter_motor", 150.0, essential=True),
            "fuel_pump": ElectricalLoad("fuel_pump", 5.0, essential=False),
            "nav_lights": ElectricalLoad("nav_lights", 1.5, essential=False),
            "beacon": ElectricalLoad("beacon", 2.0, essential=False),
            "strobe": ElectricalLoad("strobe", 3.0, essential=False),
            "taxi_light": ElectricalLoad("taxi_light", 4.0, essential=False),
            "landing_light": ElectricalLoad("landing_light", 8.0, essential=False),
            "avionics": ElectricalLoad("avionics", 10.0, essential=False),
        }

        # Failure tracking
        self.alternator_failed = False

    def update(self, dt: float, engine_rpm: float) -> None:
        """Update electrical system."""

        # Calculate total load
        total_load_amps = sum(
            load.current_draw_amps
            for load in self.loads.values()
            if load.enabled
        )

        # Alternator output
        alternator_output = 0.0
        if not self.alternator_failed and engine_rpm > self.alternator_rpm_threshold:
            # Alternator can supply up to max amps at regulated voltage
            alternator_output = min(self.alternator_max_amps, total_load_amps)

        # Net battery current (positive = charging, negative = discharging)
        net_current = alternator_output - total_load_amps

        # Update battery state of charge
        ah_change = (net_current / 3600.0) * dt  # Convert amps to amp-hours
        self.battery_current_ah += ah_change

        # Battery capacity limits
        self.battery_current_ah = max(0.0, min(self.battery_capacity_ah,
                                                 self.battery_current_ah))

        # Calculate battery voltage (lead-acid discharge curve)
        soc = self.battery_current_ah / self.battery_capacity_ah
        if soc > 0.75:
            self.battery_voltage = 12.2 + (soc - 0.75) * 1.6  # 12.2V to 12.6V
        elif soc > 0.25:
            self.battery_voltage = 11.8 + (soc - 0.25) * 0.8  # 11.8V to 12.2V
        elif soc > 0.0:
            self.battery_voltage = 10.5 + (soc) * 5.2         # 10.5V to 11.8V
        else:
            self.battery_voltage = 0.0  # Completely dead

        # Bus voltage
        if alternator_output > 0:
            # Alternator feeding bus (regulated voltage)
            self.main_bus.voltage_current = self.alternator_voltage_regulated
        else:
            # Battery feeding bus (voltage drop due to load)
            voltage_drop = total_load_amps * self.battery_internal_resistance
            self.main_bus.voltage_current = max(0.0, self.battery_voltage - voltage_drop)

        # Disable loads if voltage too low
        if self.main_bus.voltage_current < 10.0:
            for load in self.loads.values():
                if load.current_draw_amps > 5.0:  # Heavy loads fail first
                    load.enabled = False

    def can_draw_current(self, amps: float) -> bool:
        """Check if requested current is available."""
        # Calculate if battery can provide this current
        voltage_drop = amps * self.battery_internal_resistance
        resulting_voltage = self.battery_voltage - voltage_drop
        return resulting_voltage > 10.0  # Minimum bus voltage
```

### Cessna 172: SimpleGravityFuelSystem

```python
# File: src/airborne/systems/fuel/simple_gravity.py

class SimpleGravityFuelSystem(IFuelSystem):
    """
    Simple gravity-feed fuel system for Cessna 172.

    Features:
    - Two wing tanks (26 gal usable each)
    - Gravity feed (no pumps required at low altitude)
    - Optional electric boost pump
    - Fuel selector: OFF/LEFT/RIGHT/BOTH
    - AVGAS 100LL (6.0 lbs/gallon)

    Realistic behavior:
    - Engine dies immediately when fuel exhausted (no grace period)
    - Selector must be on correct tank or BOTH
    - Fuel weight affects aircraft CG and performance
    """

    def __init__(self):
        self.tanks = {
            "left": FuelTank(
                name="left",
                capacity_total=28.0,
                capacity_usable=26.0,
                current_quantity=26.0,  # Start full
                fuel_type=FuelType.AVGAS_100LL,
                position=(-5.0, 0.0, -8.0)  # Left wing
            ),
            "right": FuelTank(
                name="right",
                capacity_total=28.0,
                capacity_usable=26.0,
                current_quantity=26.0,  # Start full
                fuel_type=FuelType.AVGAS_100LL,
                position=(-5.0, 0.0, 8.0)  # Right wing
            ),
        }

        self.selector_position = FuelSelectorPosition.BOTH
        self.fuel_pump_enabled = False
        self.lbs_per_gallon = 6.0  # AVGAS 100LL

    def update(self, dt: float, fuel_flow_gph: float) -> None:
        """Update fuel consumption."""

        # Determine which tanks to draw from
        if self.selector_position == FuelSelectorPosition.OFF:
            return  # No fuel flow

        # Convert GPH to gallons per second
        fuel_consumed_gps = fuel_flow_gph / 3600.0
        fuel_consumed = fuel_consumed_gps * dt

        # Draw from tanks based on selector
        if self.selector_position == FuelSelectorPosition.BOTH:
            # Draw equally from both tanks
            left_draw = fuel_consumed / 2.0
            right_draw = fuel_consumed / 2.0

            # Consume from left
            self.tanks["left"].current_quantity -= left_draw
            if self.tanks["left"].current_quantity < 0:
                # Left tank exhausted, take remainder from right
                right_draw += abs(self.tanks["left"].current_quantity)
                self.tanks["left"].current_quantity = 0.0

            # Consume from right
            self.tanks["right"].current_quantity -= right_draw
            if self.tanks["right"].current_quantity < 0:
                self.tanks["right"].current_quantity = 0.0

        elif self.selector_position == FuelSelectorPosition.LEFT:
            self.tanks["left"].current_quantity -= fuel_consumed
            if self.tanks["left"].current_quantity < 0:
                self.tanks["left"].current_quantity = 0.0

        elif self.selector_position == FuelSelectorPosition.RIGHT:
            self.tanks["right"].current_quantity -= fuel_consumed
            if self.tanks["right"].current_quantity < 0:
                self.tanks["right"].current_quantity = 0.0

    def get_available_fuel_flow(self) -> float:
        """Get available fuel flow.

        Returns:
            Maximum available fuel flow in GPH.
            Returns 0.0 if selector OFF or tanks empty.
        """
        if self.selector_position == FuelSelectorPosition.OFF:
            return 0.0

        # Check usable fuel in selected tanks
        usable_fuel = 0.0

        if self.selector_position == FuelSelectorPosition.BOTH:
            # Both tanks must have usable fuel (above 2 gallons unusable)
            left_usable = max(0.0, self.tanks["left"].current_quantity - 2.0)
            right_usable = max(0.0, self.tanks["right"].current_quantity - 2.0)
            usable_fuel = left_usable + right_usable

        elif self.selector_position == FuelSelectorPosition.LEFT:
            usable_fuel = max(0.0, self.tanks["left"].current_quantity - 2.0)

        elif self.selector_position == FuelSelectorPosition.RIGHT:
            usable_fuel = max(0.0, self.tanks["right"].current_quantity - 2.0)

        # If no usable fuel, return 0 (engine will die)
        if usable_fuel <= 0.0:
            return 0.0

        # Gravity feed can supply ~15 GPH max (more than engine needs)
        return 15.0
```

---

## Failure Analysis System

```python
# File: src/airborne/systems/failure_analyzer.py

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional


class FailureType(Enum):
    """Types of flight failures."""
    FUEL_EXHAUSTION = "fuel_exhaustion"
    ENGINE_FAILURE = "engine_failure"
    ELECTRICAL_FAILURE = "electrical_failure"
    CONTROLLED_FLIGHT_INTO_TERRAIN = "cfit"
    STALL_SPIN = "stall_spin"
    OVERSPEED = "overspeed"
    STRUCTURAL_FAILURE = "structural_failure"
    HARD_LANDING = "hard_landing"
    GEAR_UP_LANDING = "gear_up_landing"
    RUNWAY_OVERRUN = "runway_overrun"


class SurvivabilityLevel(Enum):
    """Impact survivability levels."""
    UNSURVIVABLE = "unsurvivable"      # > 20 G or catastrophic
    LIKELY_FATAL = "likely_fatal"      # 10-20 G
    SERIOUS_INJURY = "serious_injury"  # 5-10 G
    MINOR_INJURY = "minor_injury"      # 2-5 G
    SURVIVABLE = "survivable"          # < 2 G


@dataclass
class FailureSnapshot:
    """Snapshot of aircraft state at time of failure."""
    time: datetime
    position: tuple[float, float, float]  # lat, lon, alt
    velocity: tuple[float, float, float]  # x, y, z
    airspeed_knots: float
    ground_speed_knots: float
    vertical_speed_fpm: float
    heading: float
    pitch: float
    roll: float
    engine_state: dict
    electrical_state: dict
    fuel_state: dict
    control_inputs: dict


@dataclass
class FailureAnalysis:
    """Complete failure analysis report."""
    failure_type: FailureType
    primary_cause: str
    contributing_factors: List[str]
    failure_snapshot: FailureSnapshot
    impact_snapshot: FailureSnapshot
    impact_force_g: float
    survivability: SurvivabilityLevel
    lessons_learned: List[str]
    timeline: List[tuple[float, str]]  # (time_offset, event_description)
    flight_duration: float  # seconds


class FailureAnalyzer:
    """Analyzes flight failures and generates detailed reports."""

    def __init__(self):
        self.event_timeline: List[tuple[float, str]] = []
        self.warnings_given: List[tuple[float, str]] = []
        self.flight_start_time: Optional[datetime] = None

    def record_event(self, time: float, event: str) -> None:
        """Record event in timeline."""
        self.event_timeline.append((time, event))

    def record_warning(self, time: float, warning: str) -> None:
        """Record warning given to pilot."""
        self.warnings_given.append((time, warning))

    def analyze_failure(self, failure_snapshot: FailureSnapshot,
                       impact_snapshot: FailureSnapshot) -> FailureAnalysis:
        """Generate detailed failure analysis."""

        # Determine failure type
        failure_type = self._determine_failure_type(failure_snapshot, impact_snapshot)

        # Primary cause
        primary_cause = self._determine_primary_cause(failure_type, failure_snapshot)

        # Contributing factors
        factors = self._analyze_contributing_factors(failure_snapshot, impact_snapshot)

        # Impact force and survivability
        impact_g = self._calculate_impact_force(impact_snapshot)
        survivability = self._assess_survivability(impact_g, impact_snapshot)

        # Lessons learned
        lessons = self._generate_lessons(failure_type, failure_snapshot,
                                         impact_snapshot, self.warnings_given)

        return FailureAnalysis(
            failure_type=failure_type,
            primary_cause=primary_cause,
            contributing_factors=factors,
            failure_snapshot=failure_snapshot,
            impact_snapshot=impact_snapshot,
            impact_force_g=impact_g,
            survivability=survivability,
            lessons_learned=lessons,
            timeline=self.event_timeline,
            flight_duration=impact_snapshot.time - self.flight_start_time
        )

    def _determine_failure_type(self, failure_snapshot, impact_snapshot) -> FailureType:
        """Determine primary failure type from state."""

        # Check fuel exhaustion
        fuel = failure_snapshot.fuel_state
        if fuel["total_usable_gallons"] <= 0.0:
            return FailureType.FUEL_EXHAUSTION

        # Check engine failure
        engine = failure_snapshot.engine_state
        if not engine["running"] and failure_snapshot.position[2] > 100:  # AGL > 100ft
            return FailureType.ENGINE_FAILURE

        # Check CFIT
        if impact_snapshot.vertical_speed_fpm < -500 and \
           impact_snapshot.pitch > -10:  # Controlled descent into terrain
            return FailureType.CONTROLLED_FLIGHT_INTO_TERRAIN

        # Check stall/spin
        if impact_snapshot.airspeed_knots < 45 and \
           abs(impact_snapshot.roll) > 30:
            return FailureType.STALL_SPIN

        # Check hard landing
        if abs(impact_snapshot.vertical_speed_fpm) > 600:
            return FailureType.HARD_LANDING

        # Default
        return FailureType.ENGINE_FAILURE

    def _determine_primary_cause(self, failure_type: FailureType,
                                 snapshot: FailureSnapshot) -> str:
        """Generate human-readable primary cause."""

        if failure_type == FailureType.FUEL_EXHAUSTION:
            return "Fuel Exhaustion - All tanks empty"

        elif failure_type == FailureType.ENGINE_FAILURE:
            engine = snapshot.engine_state
            if engine.get("oil_pressure_psi", 0) < 10:
                return "Engine Failure - Loss of oil pressure"
            elif engine.get("oil_temperature_c", 0) > 120:
                return "Engine Failure - Engine overheated"
            else:
                return "Engine Failure - Unknown mechanical failure"

        elif failure_type == FailureType.CFIT:
            return "Controlled Flight Into Terrain - Spatial disorientation or navigation error"

        elif failure_type == FailureType.STALL_SPIN:
            return "Aerodynamic Stall/Spin - Airspeed below stall speed"

        return str(failure_type.value)

    def _analyze_contributing_factors(self, failure_snapshot,
                                      impact_snapshot) -> List[str]:
        """Identify contributing factors."""
        factors = []

        # Check if warnings were ignored
        if len(self.warnings_given) > 0:
            factors.append(f"Pilot ignored {len(self.warnings_given)} warning(s)")

        # Fuel management
        fuel = failure_snapshot.fuel_state
        if fuel["total_usable_gallons"] < 5.0:
            factors.append("Low fuel state before failure")

        # Night/IMC conditions (simplified)
        # In real implementation, check time of day, weather

        # Configuration
        if not impact_snapshot.control_inputs.get("gear", True):
            factors.append("Landing gear retracted at impact")

        return factors

    def _calculate_impact_force(self, impact_snapshot: FailureSnapshot) -> float:
        """Calculate impact G-force."""
        # Simplified: based on vertical speed
        # Real: would use velocity change and time
        vs_fps = impact_snapshot.vertical_speed_fpm / 60.0  # ft/s

        # Assume deceleration over 0.1 seconds (hard impact)
        deceleration_fps2 = abs(vs_fps) / 0.1
        g_force = deceleration_fps2 / 32.2  # Convert to Gs

        return g_force

    def _assess_survivability(self, impact_g: float,
                             impact_snapshot: FailureSnapshot) -> SurvivabilityLevel:
        """Assess impact survivability."""

        if impact_g > 20.0:
            return SurvivabilityLevel.UNSURVIVABLE
        elif impact_g > 10.0:
            return SurvivabilityLevel.LIKELY_FATAL
        elif impact_g > 5.0:
            return SurvivabilityLevel.SERIOUS_INJURY
        elif impact_g > 2.0:
            return SurvivabilityLevel.MINOR_INJURY
        else:
            return SurvivabilityLevel.SURVIVABLE

    def _generate_lessons(self, failure_type: FailureType,
                         failure_snapshot: FailureSnapshot,
                         impact_snapshot: FailureSnapshot,
                         warnings: List[tuple[float, str]]) -> List[str]:
        """Generate lessons learned."""
        lessons = []

        if failure_type == FailureType.FUEL_EXHAUSTION:
            lessons.append("Always monitor fuel gauges and plan with 30-minute reserve")
            lessons.append("Respond immediately to low fuel warnings")
            lessons.append("Land at nearest suitable airport when fuel low")
            if len(warnings) > 0:
                lessons.append(f"You received {len(warnings)} warning(s) - DO NOT ignore warnings")

        elif failure_type == FailureType.ENGINE_FAILURE:
            lessons.append("Maintain best glide speed (65 knots for Cessna 172)")
            lessons.append("Pick suitable landing site immediately")
            lessons.append("Attempt engine restart only if altitude permits")
            lessons.append("Declare emergency on 121.5 MHz")

        if abs(impact_snapshot.vertical_speed_fpm) > 600:
            lessons.append("Flare more aggressively to reduce descent rate")

        if not impact_snapshot.control_inputs.get("gear", True):
            lessons.append("Deploy landing gear for forced landing (absorbs energy)")

        return lessons

    def generate_report(self, analysis: FailureAnalysis) -> str:
        """Generate human-readable failure report."""

        report = []
        report.append("=" * 60)
        report.append("FLIGHT FAILURE ANALYSIS")
        report.append("=" * 60)
        report.append("")

        # Failure type
        report.append(f"Failure Type: {analysis.failure_type.value.upper()}")
        report.append(f"Primary Cause: {analysis.primary_cause}")
        report.append("")

        # Time and location
        fs = analysis.failure_snapshot
        report.append(f"Time of Failure: {fs.time}")
        report.append(f"Location: {fs.position[0]:.4f}° N, {fs.position[1]:.4f}° W")
        report.append(f"Altitude at Failure: {fs.position[2]:.0f} ft MSL")
        report.append(f"Airspeed: {fs.airspeed_knots:.0f} knots")
        report.append("")

        # Contributing factors
        if analysis.contributing_factors:
            report.append("Contributing Factors:")
            for factor in analysis.contributing_factors:
                report.append(f"  - {factor}")
            report.append("")

        # Impact
        imp = analysis.impact_snapshot
        report.append("Impact State:")
        report.append(f"  Ground speed: {imp.ground_speed_knots:.0f} knots")
        report.append(f"  Descent rate: {imp.vertical_speed_fpm:.0f} ft/min")
        report.append(f"  Attitude: Pitch {imp.pitch:.0f}°, Roll {imp.roll:.0f}°")
        report.append(f"  Impact force: {analysis.impact_force_g:.1f} G")
        report.append(f"  Survivability: {analysis.survivability.value.upper()}")
        report.append("")

        # Lessons
        report.append("Lessons Learned:")
        for i, lesson in enumerate(analysis.lessons_learned, 1):
            report.append(f"  {i}. {lesson}")
        report.append("")

        # Flight duration
        minutes = int(analysis.flight_duration / 60)
        seconds = int(analysis.flight_duration % 60)
        report.append(f"Total Flight Time: {minutes}:{seconds:02d}")
        report.append("")

        report.append("=" * 60)

        return "\n".join(report)
```

---

## Plugin Structure

### Directory Structure

```
src/airborne/systems/
├── __init__.py
├── electrical/
│   ├── __init__.py
│   ├── base.py              # IElectricalSystem interface
│   ├── simple_12v.py        # Cessna 172
│   ├── simple_28v.py        # Cessna 210, older jets
│   ├── dual_bus_28v.py      # Boeing 737
│   └── advanced_bus.py      # Airbus A320
├── fuel/
│   ├── __init__.py
│   ├── base.py              # IFuelSystem interface
│   ├── simple_gravity.py    # Cessna 172
│   ├── fuel_injection.py    # Cessna 182, 210
│   ├── jet_fuel_system.py   # Boeing 737
│   └── fqms.py              # Airbus A320 (Fuel Quantity Management)
├── engines/
│   ├── __init__.py
│   ├── base.py              # IEngine interface
│   ├── piston_simple.py     # Cessna 172 (Lycoming O-360)
│   ├── piston_turbo.py      # Cessna 210 (Continental TSIO-520)
│   ├── turboprop.py         # Cessna Caravan (Pratt & Whitney PT6A)
│   └── turbofan.py          # Boeing 737 (CFM56)
├── lighting/
│   ├── __init__.py
│   ├── base.py
│   └── standard_lights.py
└── failure_analyzer.py

src/airborne/plugins/systems/
├── __init__.py
├── electrical_plugin.py     # Wrapper that uses systems.electrical
├── fuel_plugin.py           # Wrapper that uses systems.fuel
└── lighting_plugin.py       # Wrapper that uses systems.lighting
```

### Plugin Configuration

Each aircraft specifies which system implementations to use:

```yaml
# config/aircraft/cessna172.yaml
aircraft:
  name: "Cessna 172 Skyhawk"

  plugins:
    - plugin: "electrical_plugin"
      instance_id: "electrical"
      config:
        implementation: "simple_12v"  # Uses Simple12VElectricalSystem
        battery:
          type: "lead_acid"
          voltage_nominal: 12.6
          capacity_ah: 35.0
        alternator:
          max_amps: 60.0
          voltage_regulated: 14.0

    - plugin: "fuel_plugin"
      instance_id: "fuel"
      config:
        implementation: "simple_gravity"  # Uses SimpleGravityFuelSystem
        tanks:
          left: {capacity_usable: 26.0, position: [-5.0, 0.0, -8.0]}
          right: {capacity_usable: 26.0, position: [-5.0, 0.0, 8.0]}
        fuel_type: "avgas_100ll"

    - plugin: "engine_plugin"
      instance_id: "engine"
      config:
        implementation: "piston_simple"  # Uses SimplePistonEngine
        max_power_hp: 160
        displacement_liters: 5.9

# config/aircraft/boeing737.yaml
aircraft:
  name: "Boeing 737-800"

  plugins:
    - plugin: "electrical_plugin"
      instance_id: "electrical"
      config:
        implementation: "dual_bus_28v"  # Different implementation!
        # ... 737-specific config

    - plugin: "fuel_plugin"
      instance_id: "fuel"
      config:
        implementation: "jet_fuel_system"  # Different implementation!
        # ... 737-specific config
```

---

## Implementation Plan

### Phase 1: Base Interfaces (2-3 hours) ✅ COMPLETED
1. ✅ Create `systems/electrical/base.py` - IElectricalSystem interface
2. ✅ Create `systems/fuel/base.py` - IFuelSystem interface
3. ✅ Create `systems/engines/base.py` - IEngine interface (extend existing)
4. ✅ Create `systems/failure_analyzer.py` - Failure analysis system

**Status**: All base interfaces created with complete documentation, type hints, and abstract methods. Code passes Ruff formatting/linting and mypy type checking.

### Phase 2: Cessna 172 Implementations (4-5 hours) ✅ COMPLETED
5. ✅ Implement `Simple12VElectricalSystem`
6. ✅ Implement `SimpleGravityFuelSystem`
7. ✅ Implement `StandardLightingSystem`
8. ⚠️ Update `SimplePistonEngine` to use new interfaces (deferred to Phase 3)

**Status**: All Cessna 172 system implementations complete with 15 comprehensive tests. Code passes all quality checks.

### Phase 3: Plugin Wrappers (2-3 hours) ✅ COMPLETED
9. ✅ Create `ElectricalPlugin` (wraps IElectricalSystem implementations)
10. ✅ Create `FuelPlugin` (wraps IFuelSystem implementations)
11. ✅ Create `LightingPlugin`
12. ⚠️ Update engine plugin to require electrical + fuel (deferred to Phase 4)

**Status**: All plugin wrappers created. Plugins integrate systems with messaging, handle control inputs, publish state/warnings/failures. Code passes all quality checks.

### Phase 4: Integration (2-3 hours)
13. Wire control panel messages to system plugins
14. Update physics plugin for thrust + fuel weight
15. Add failure detection and crash analysis
16. Add audio feedback for system states

### Phase 5: Testing (3-4 hours)
17. Test normal flight operations
18. Test failure scenarios (fuel exhaustion, battery dead, etc.)
19. Test crash analysis reports
20. Tune realism values

**Total: 13-18 hours (2-3 hours completed)**

---

## Success Criteria

### Realism (No Forgiveness) ✅
- Battery voltage < 11.0V: Starter won't turn (hard failure)
- Fuel exhausted: Engine quits immediately (no grace period)
- Magnetos off: No ignition, engine won't start
- Fuel selector OFF: Immediate fuel starvation
- Dead battery: Complete electrical failure
- Hard landing > 600 fpm: Aircraft damaged/destroyed

### Modularity ✅
- Abstract interfaces allow different implementations
- Easy to add Boeing 737 with different systems
- Configuration-driven system selection
- Code reuse across aircraft types

### Post-Crash Analysis ✅
- Detailed failure report generated
- Primary cause identification
- Contributing factors analysis
- Impact force calculation
- Survivability assessment
- Lessons learned
- Timeline of events
- Warning history (were warnings ignored?)

---

## Example Failure Report

```
============================================================
FLIGHT FAILURE ANALYSIS
============================================================

Failure Type: FUEL_EXHAUSTION
Primary Cause: Fuel Exhaustion - All tanks empty

Time of Failure: 2025-10-15 14:23:45 UTC
Location: 37.4219° N, 122.0847° W
Altitude at Failure: 2,400 ft MSL
Airspeed: 95 knots

Contributing Factors:
  - Pilot ignored 3 warning(s)
  - Low fuel state before failure
  - Landing gear retracted at impact

Impact State:
  Ground speed: 45 knots
  Descent rate: 800 ft/min
  Attitude: Pitch -5°, Roll 15°
  Impact force: 8.2 G
  Survivability: LIKELY_FATAL

Lessons Learned:
  1. Always monitor fuel gauges and plan with 30-minute reserve
  2. Respond immediately to low fuel warnings
  3. Land at nearest suitable airport when fuel low
  4. You received 3 warning(s) - DO NOT ignore warnings
  5. Flare more aggressively to reduce descent rate
  6. Deploy landing gear for forced landing (absorbs energy)

Total Flight Time: 3:14:32

============================================================
```

This design provides **maximum realism, modularity, and educational value** while remaining extensible for future aircraft.

Ready to start implementation?

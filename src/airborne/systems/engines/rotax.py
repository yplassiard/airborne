"""Rotax engine implementations for ultralight aircraft.

This module implements Rotax aircraft engines commonly used in ULM/LSA:
- Rotax 912 series (4-stroke, 80-100 HP) - Most popular
- Rotax 582 (2-stroke, 65 HP) - Legacy ULM engine
- Rotax 914 (turbocharged 912, 115 HP)

Rotax engines have unique characteristics:
- Reduction gearbox (2.43:1 or 2.27:1 ratio)
- Liquid-cooled cylinder heads
- Dual electronic ignition (912) or CDI (582)
- Lower fuel consumption than Continental/Lycoming
- MOGAS compatible (91 octane unleaded)
"""

from dataclasses import dataclass
from enum import Enum

from airborne.core.logging_system import get_logger
from airborne.systems.engines.base import EngineControls, EngineState, EngineType, IEngine

logger = get_logger(__name__)


class RotaxModel(Enum):
    """Rotax engine models."""

    ROTAX_582 = "582"  # 2-stroke, 65 HP
    ROTAX_912_UL = "912ul"  # 4-stroke, 80 HP
    ROTAX_912_ULS = "912uls"  # 4-stroke, 100 HP (most common)
    ROTAX_912_IS = "912is"  # Fuel injected, 100 HP
    ROTAX_914_UL = "914ul"  # Turbocharged, 115 HP


@dataclass
class RotaxEngineConfig:
    """Configuration for Rotax engines."""

    model: RotaxModel = RotaxModel.ROTAX_912_ULS
    max_power_hp: float = 100.0
    max_rpm: float = 5800.0  # Engine RPM (before gearbox)
    max_continuous_rpm: float = 5500.0
    idle_rpm: float = 1400.0
    reduction_ratio: float = 2.43  # Gearbox reduction ratio
    cylinders: int = 4
    displacement_cc: float = 1352.0  # 1352cc for 912
    fuel_consumption_max_lph: float = 25.0  # Liters per hour
    fuel_consumption_cruise_lph: float = 18.0
    fuel_consumption_idle_lph: float = 4.0
    coolant_temp_normal_c: float = 90.0  # Liquid cooled
    coolant_temp_max_c: float = 120.0
    oil_temp_normal_c: float = 90.0
    oil_temp_max_c: float = 130.0
    oil_pressure_idle_bar: float = 2.0
    oil_pressure_max_bar: float = 7.0
    egt_max_c: float = 880.0  # Exhaust gas temperature
    is_two_stroke: bool = False
    uses_choke: bool = False  # 912 uses enrichment circuit
    has_electric_fuel_pump: bool = True
    starter_current_amps: float = 80.0  # Lower than Lycoming
    min_start_voltage: float = 11.5


class RotaxEngine(IEngine):
    """Rotax aircraft engine implementation.

    Models the Rotax 912/914 series 4-stroke engines and 582 2-stroke.
    These engines are the standard powerplant for ULM/LSA aircraft worldwide.

    Key differences from Continental/Lycoming:
    - Reduction gearbox: Engine RPM ≠ prop RPM
    - Liquid cooling: Better thermal management
    - Dual electronic ignition: No magnetos
    - Lower fuel consumption: More efficient
    - Higher redline RPM: 5800 vs 2700

    The 912 series uses:
    - Dual redundant electronic ignition (no magnetos)
    - Liquid-cooled cylinder heads with air-cooled cylinders
    - Integrated reduction gearbox (2.43:1 standard)
    - Mechanical fuel pump (electric pump for priming only)

    Examples:
        >>> engine = RotaxEngine()
        >>> engine.initialize({
        ...     "model": "912uls",
        ...     "max_power_hp": 100,
        ... })
        >>> controls = EngineControls(throttle=0.75, mixture=1.0)
        >>> engine.update(0.016, controls, True, 25.0)
    """

    def __init__(self) -> None:
        """Initialize Rotax engine."""
        self.config = RotaxEngineConfig()

        # Engine state
        self.engine_rpm = 0.0  # Engine RPM (before gearbox)
        self.prop_rpm = 0.0  # Propeller RPM (after gearbox)
        self.power_hp = 0.0
        self.fuel_flow_lph = 0.0  # Liters per hour
        self.coolant_temp_c = 20.0  # Ambient
        self.oil_temp_c = 20.0
        self.oil_pressure_bar = 0.0
        self.egt_c = 20.0
        self.running = False
        self.starting = False

        # Failure state
        self.failed = False
        self.failure_type: str | None = None

        # Internal state
        self._warmup_factor = 0.0
        self._accumulated_running_time = 0.0

    def initialize(self, config: dict) -> None:
        """Initialize engine from configuration.

        Args:
            config: Engine configuration dictionary.
        """
        # Parse model
        model_str = config.get("model", "912uls").lower()
        model_map = {
            "582": RotaxModel.ROTAX_582,
            "912ul": RotaxModel.ROTAX_912_UL,
            "912uls": RotaxModel.ROTAX_912_ULS,
            "912is": RotaxModel.ROTAX_912_IS,
            "914ul": RotaxModel.ROTAX_914_UL,
        }
        self.config.model = model_map.get(model_str, RotaxModel.ROTAX_912_ULS)

        # Set model-specific defaults
        if self.config.model == RotaxModel.ROTAX_582:
            self.config.max_power_hp = 65.0
            self.config.max_rpm = 6500.0
            self.config.displacement_cc = 580.0
            self.config.is_two_stroke = True
            self.config.uses_choke = True
            self.config.cylinders = 2
            self.config.fuel_consumption_max_lph = 22.0
        elif self.config.model == RotaxModel.ROTAX_912_UL:
            self.config.max_power_hp = 80.0
            self.config.max_rpm = 5800.0
        elif self.config.model == RotaxModel.ROTAX_912_ULS or self.config.model == RotaxModel.ROTAX_912_IS:
            self.config.max_power_hp = 100.0
            self.config.max_rpm = 5800.0
        elif self.config.model == RotaxModel.ROTAX_914_UL:
            self.config.max_power_hp = 115.0
            self.config.max_rpm = 5800.0
            self.config.max_continuous_rpm = 5500.0

        # Override from config
        if "max_power_hp" in config:
            self.config.max_power_hp = config["max_power_hp"]
        if "max_rpm" in config:
            self.config.max_rpm = config["max_rpm"]
        if "idle_rpm" in config:
            self.config.idle_rpm = config["idle_rpm"]
        if "reduction_ratio" in config:
            self.config.reduction_ratio = config["reduction_ratio"]
        if "fuel_consumption_max_lph" in config:
            self.config.fuel_consumption_max_lph = config["fuel_consumption_max_lph"]

        logger.info(
            "RotaxEngine initialized: %s, %d HP, %d RPM max, %.2f:1 reduction",
            self.config.model.value,
            int(self.config.max_power_hp),
            int(self.config.max_rpm),
            self.config.reduction_ratio,
        )

    def update(
        self,
        dt: float,
        controls: EngineControls,
        electrical_available: bool,
        fuel_available: float,
    ) -> None:
        """Update engine state.

        Args:
            dt: Delta time in seconds.
            controls: Engine control inputs.
            electrical_available: Whether electrical power is available.
            fuel_available: Available fuel flow in gallons per hour.
        """
        if self.failed:
            self._update_failed_engine(dt)
            return

        # Convert GPH to LPH for internal calculations
        fuel_available_lph = fuel_available * 3.785

        # Check for fuel starvation
        if fuel_available_lph <= 0.0 and self.running:
            logger.warning("Rotax: Fuel starvation - engine shutdown")
            self.running = False
            self.starting = False
            self.engine_rpm = max(0.0, self.engine_rpm - 1000.0 * dt)
            self.fuel_flow_lph = 0.0
            self.power_hp = 0.0
            return

        # Starter logic
        if controls.starter and electrical_available and not self.running:
            self.starting = True
            # Rotax starter cranks faster than Lycoming
            target_crank_rpm = 400.0
            self.engine_rpm = min(target_crank_rpm, self.engine_rpm + 800.0 * dt)

            # Check start conditions
            if self._can_start_engine(controls, fuel_available_lph):
                if self.engine_rpm >= 300.0:
                    self.running = True
                    self.starting = False
                    logger.info("Rotax engine started at %.0f RPM", self.engine_rpm)
        else:
            self.starting = False

        # Running engine
        if self.running:
            self._update_running_engine(dt, controls, fuel_available_lph)
        else:
            # Engine off - wind down
            self.engine_rpm = max(0.0, self.engine_rpm - 500.0 * dt)
            self.fuel_flow_lph = 0.0
            self.power_hp = 0.0

        # Update prop RPM (after gearbox)
        self.prop_rpm = self.engine_rpm / self.config.reduction_ratio

        # Update temperatures
        self._update_temperatures(dt)

        # Update oil pressure
        self._update_oil_pressure()

    def _can_start_engine(self, controls: EngineControls, fuel_available_lph: float) -> bool:
        """Check if engine can start.

        Rotax 912 series uses dual electronic ignition, not magnetos.
        The magneto switches on the panel actually control the dual
        independent ignition systems.
        """
        # Need at least one ignition circuit
        if not (controls.magneto_left or controls.magneto_right):
            return False

        # Need fuel
        if fuel_available_lph <= 0.0:
            return False

        # Need reasonable mixture
        if controls.mixture < 0.2:
            return False

        # Cold start with 2-stroke needs choke/enrichment
        if self.config.is_two_stroke and self._warmup_factor < 0.2:
            # 582 needs more enrichment when cold
            if controls.mixture < 0.8:
                return False

        return True

    def _update_running_engine(
        self, dt: float, controls: EngineControls, fuel_available_lph: float
    ) -> None:
        """Update running engine parameters."""
        # Check ignition - need at least one circuit
        if not (controls.magneto_left or controls.magneto_right):
            logger.warning("Rotax: Both ignition circuits off - engine shutdown")
            self.running = False
            return

        # Calculate target RPM based on throttle
        target_rpm = (
            self.config.idle_rpm + (self.config.max_rpm - self.config.idle_rpm) * controls.throttle
        )

        # RPM response (Rotax has lighter rotating mass, faster response)
        rpm_rate = 1200.0  # RPM per second
        if self.engine_rpm < target_rpm:
            self.engine_rpm = min(target_rpm, self.engine_rpm + rpm_rate * dt)
        else:
            self.engine_rpm = max(target_rpm, self.engine_rpm - rpm_rate * 1.5 * dt)

        # Calculate power
        self._calculate_power(controls)

        # Calculate fuel consumption
        self._calculate_fuel_consumption(controls, fuel_available_lph)

        # Warmup
        self._warmup_factor = min(1.0, self._warmup_factor + 0.03 * dt)
        self._accumulated_running_time += dt

        # Check for over-RPM (redline)
        if self.engine_rpm > self.config.max_rpm * 1.05:
            logger.warning(
                "Rotax: Over-RPM %.0f (max %.0f)",
                self.engine_rpm,
                self.config.max_rpm,
            )
            # Potential damage at sustained over-RPM

    def _calculate_power(self, controls: EngineControls) -> None:
        """Calculate engine power output."""
        rpm_factor = self.engine_rpm / self.config.max_rpm

        # Throttle factor (Rotax has better idle power curve)
        idle_factor = self.config.idle_rpm / self.config.max_rpm
        throttle_factor = max(idle_factor, controls.throttle)

        # Mixture factor
        # Rotax is less sensitive to mixture than carbureted engines
        mixture_factor = 1.0
        if controls.mixture < 0.4:
            mixture_factor = controls.mixture * 2.0
        elif controls.mixture > 0.95:
            mixture_factor = 0.98  # Slight rich penalty

        # Single ignition penalty (running on one circuit)
        ignition_factor = 1.0
        if not (controls.magneto_left and controls.magneto_right):
            ignition_factor = 0.96  # ~4% power loss on single ignition

        # Warmup factor
        warmup_factor = 0.8 + 0.2 * self._warmup_factor

        # Calculate power
        self.power_hp = (
            self.config.max_power_hp
            * rpm_factor
            * throttle_factor
            * mixture_factor
            * ignition_factor
            * warmup_factor
        )

    def _calculate_fuel_consumption(
        self, controls: EngineControls, fuel_available_lph: float
    ) -> None:
        """Calculate fuel consumption."""
        power_factor = self.power_hp / self.config.max_power_hp

        # Rotax is more fuel efficient than traditional engines
        target_flow = (
            self.config.fuel_consumption_idle_lph
            + (self.config.fuel_consumption_max_lph - self.config.fuel_consumption_idle_lph)
            * power_factor
        )

        # Mixture adjustment
        mixture_multiplier = 0.6 + 0.4 * controls.mixture
        target_flow *= mixture_multiplier

        # 2-stroke uses more fuel at low power (oil in fuel)
        if self.config.is_two_stroke:
            target_flow *= 1.1

        # Clamp to available
        self.fuel_flow_lph = min(target_flow, fuel_available_lph)

        # If not enough fuel, reduce power
        if fuel_available_lph < target_flow and target_flow > 0:
            ratio = fuel_available_lph / target_flow
            self.power_hp *= ratio

    def _update_temperatures(self, dt: float) -> None:
        """Update engine temperatures."""
        power_factor = self.power_hp / self.config.max_power_hp if self.running else 0.0

        # Coolant temperature (liquid cooled - stabilizes faster)
        if self.running:
            target_coolant = 50.0 + 50.0 * power_factor  # 50-100°C
            coolant_rate = 5.0  # °C per second
        else:
            target_coolant = 20.0  # Ambient
            coolant_rate = 2.0

        if self.coolant_temp_c < target_coolant:
            self.coolant_temp_c = min(target_coolant, self.coolant_temp_c + coolant_rate * dt)
        else:
            self.coolant_temp_c = max(target_coolant, self.coolant_temp_c - coolant_rate * 0.5 * dt)

        # Oil temperature
        if self.running:
            target_oil = 40.0 + 60.0 * power_factor  # 40-100°C
            oil_rate = 3.0
        else:
            target_oil = 20.0
            oil_rate = 1.5

        if self.oil_temp_c < target_oil:
            self.oil_temp_c = min(target_oil, self.oil_temp_c + oil_rate * dt)
        else:
            self.oil_temp_c = max(target_oil, self.oil_temp_c - oil_rate * 0.5 * dt)

        # EGT (exhaust gas temperature)
        if self.running:
            target_egt = 300.0 + 450.0 * power_factor  # 300-750°C
        else:
            target_egt = 20.0

        egt_rate = 20.0 if self.running else 10.0
        if self.egt_c < target_egt:
            self.egt_c = min(target_egt, self.egt_c + egt_rate * dt)
        else:
            self.egt_c = max(target_egt, self.egt_c - egt_rate * 0.5 * dt)

    def _update_oil_pressure(self) -> None:
        """Update oil pressure."""
        if not self.running:
            self.oil_pressure_bar = 0.0
            return

        rpm_factor = self.engine_rpm / self.config.max_rpm

        # Base pressure increases with RPM
        base_pressure = (
            self.config.oil_pressure_idle_bar
            + (self.config.oil_pressure_max_bar - self.config.oil_pressure_idle_bar) * rpm_factor
        )

        # Hot oil = lower pressure
        temp_factor = 1.0
        if self.oil_temp_c > 100.0:
            temp_factor = 0.85
        elif self.oil_temp_c < 50.0:
            temp_factor = 1.15

        self.oil_pressure_bar = base_pressure * temp_factor

    def _update_failed_engine(self, dt: float) -> None:
        """Update failed engine state."""
        self.running = False
        self.starting = False
        self.engine_rpm = max(0.0, self.engine_rpm - 400.0 * dt)
        self.prop_rpm = self.engine_rpm / self.config.reduction_ratio
        self.fuel_flow_lph = 0.0
        self.power_hp = 0.0
        self.oil_pressure_bar = 0.0

        # Cool down
        self.coolant_temp_c = max(20.0, self.coolant_temp_c - 5.0 * dt)
        self.oil_temp_c = max(20.0, self.oil_temp_c - 3.0 * dt)
        self.egt_c = max(20.0, self.egt_c - 15.0 * dt)

    def get_state(self) -> EngineState:
        """Get current engine state."""
        warnings = []
        failures = []

        # Check warnings
        if self.running:
            if self.coolant_temp_c > self.config.coolant_temp_max_c:
                warnings.append("HIGH COOLANT TEMP")
            if self.oil_temp_c > self.config.oil_temp_max_c:
                warnings.append("HIGH OIL TEMP")
            if self.oil_pressure_bar < self.config.oil_pressure_idle_bar * 0.8:
                warnings.append("LOW OIL PRESSURE")
            if self.egt_c > self.config.egt_max_c:
                warnings.append("HIGH EGT")
            if self.engine_rpm > self.config.max_rpm:
                warnings.append("OVER RPM")

        if self.failed and self.failure_type:
            failures.append(self.failure_type)

        # Convert LPH to GPH for standard interface
        fuel_flow_gph = self.fuel_flow_lph / 3.785

        return EngineState(
            engine_type=EngineType.PISTON_NATURALLY_ASPIRATED,
            running=self.running,
            power_output_hp=self.power_hp,
            fuel_flow_gph=fuel_flow_gph,
            temperature_c=self.coolant_temp_c,
            rpm=self.engine_rpm,
            manifold_pressure_inhg=None,  # Not applicable for Rotax
            oil_pressure_psi=self.oil_pressure_bar * 14.5038,  # Convert bar to PSI
            oil_temperature_c=self.oil_temp_c,
            cylinder_head_temp_c=self.coolant_temp_c,  # Use coolant as proxy
            starter_engaged=self.starting,
            warnings=warnings,
            failures=failures,
        )

    def get_thrust_force(self) -> float:
        """Get thrust force in pounds."""
        if not self.running:
            return 0.0

        # Static thrust approximation
        return 2.3 * self.power_hp  # Slightly lower than Lycoming (smaller prop)

    def can_start(self) -> bool:
        """Check if engine can start."""
        return not self.failed and not self.running

    def simulate_failure(self, failure_type: str) -> None:
        """Simulate engine failure."""
        self.failed = True
        self.failure_type = failure_type
        self.running = False
        logger.warning("Rotax engine failure simulated: %s", failure_type)

    def get_fuel_consumption_rate(self) -> float:
        """Get fuel consumption in GPH."""
        return self.fuel_flow_lph / 3.785

    def get_prop_rpm(self) -> float:
        """Get propeller RPM (after gearbox).

        Returns:
            Propeller RPM.
        """
        return self.prop_rpm

    def get_engine_rpm(self) -> float:
        """Get engine RPM (before gearbox).

        Returns:
            Engine RPM.
        """
        return self.engine_rpm

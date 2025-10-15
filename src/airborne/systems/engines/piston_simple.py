"""Simple piston engine implementation for Cessna 172.

Implements Lycoming O-360-A4M naturally aspirated 4-cylinder engine.

Realistic behavior:
- Requires battery voltage for starter (11.0V minimum)
- Requires fuel flow from fuel system (dies immediately if zero)
- Starter draws 150A from electrical system
- Engine starts only with starter + fuel + magnetos
- Power output depends on throttle, mixture, and RPM
- Realistic fuel consumption based on power setting
"""

from dataclasses import dataclass

from airborne.core.logging_system import get_logger
from airborne.systems.engines.base import EngineControls, EngineState, EngineType, IEngine

logger = get_logger(__name__)


@dataclass
class SimplePistonEngineConfig:
    """Configuration for simple piston engine."""

    displacement_liters: float = 5.9  # Lycoming O-360
    cylinders: int = 4
    max_rpm: float = 2700.0
    max_horsepower: float = 180.0
    idle_rpm: float = 650.0
    starter_rpm_threshold: float = 200.0  # RPM at which engine can catch
    fuel_flow_max_gph: float = 12.0  # Max fuel flow at full power
    fuel_flow_idle_gph: float = 1.5  # Fuel flow at idle
    oil_capacity_quarts: float = 8.0
    min_oil_pressure_idle_psi: float = 25.0
    max_oil_pressure_psi: float = 60.0
    min_oil_temp_f: float = 100.0  # Below this, engine won't start well
    max_oil_temp_f: float = 245.0  # Above this, damage occurs
    max_cht_f: float = 500.0  # Max cylinder head temperature


class SimplePistonEngine(IEngine):
    """Simple piston engine for Cessna 172 (Lycoming O-360).

    Models a naturally aspirated 4-cylinder piston engine with realistic
    startup, operation, and failure modes. No forgiveness: requires proper
    electrical power, fuel flow, and magneto settings to operate.

    Key features:
    - Starter requires 11.0V+ and draws 150A
    - Engine dies immediately when fuel flow drops to 0.0
    - Magnetos must be ON for ignition
    - Realistic power output curve based on throttle/mixture/RPM
    - Fuel consumption varies with power setting
    - Oil temperature and pressure modeling
    """

    def __init__(self) -> None:
        """Initialize simple piston engine."""
        self.config = SimplePistonEngineConfig()

        # Engine state
        self.rpm = 0.0
        self.manifold_pressure = 29.92  # Inches Hg (sea level)
        self.fuel_flow_gph = 0.0
        self.oil_pressure_psi = 0.0
        self.oil_temp_f = 70.0  # Ambient temperature
        self.cht_f = 70.0  # Cylinder head temperature
        self.horsepower = 0.0
        self.running = False
        self.starting = False

        # Failures
        self.failed = False
        self.failure_type: str | None = None

        # Internal state
        self._accumulated_fuel_gal = 0.0  # For consumption tracking
        self._warmup_factor = 0.0  # 0.0 (cold) to 1.0 (warm)

    def initialize(self, config: dict) -> None:
        """Initialize engine from config.

        Args:
            config: Engine configuration dictionary.
        """
        # Override default config if provided
        if "displacement_liters" in config:
            self.config.displacement_liters = config["displacement_liters"]
        if "cylinders" in config:
            self.config.cylinders = config["cylinders"]
        if "max_rpm" in config:
            self.config.max_rpm = config["max_rpm"]
        if "max_horsepower" in config:
            self.config.max_horsepower = config["max_horsepower"]
        if "idle_rpm" in config:
            self.config.idle_rpm = config["idle_rpm"]

        logger.info(
            "SimplePistonEngine initialized: %d cylinders, %.1f L, %d HP",
            self.config.cylinders,
            self.config.displacement_liters,
            int(self.config.max_horsepower),
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
            controls: Engine control inputs (throttle, mixture, starter, magnetos).
            electrical_available: Whether electrical power available for starter.
            fuel_available: Available fuel flow in GPH (0.0 if no fuel).
        """
        if self.failed:
            self._update_failed_engine(dt)
            return

        # Check for instant failures
        if fuel_available <= 0.0 and self.running:
            # Engine dies immediately when fuel exhausted (NO FORGIVENESS)
            logger.warning("Engine fuel starvation - immediate shutdown")
            self.running = False
            self.starting = False
            self.rpm = max(0.0, self.rpm - 500.0 * dt)  # Windmill down
            self.fuel_flow_gph = 0.0
            self.horsepower = 0.0
            return

        # Starter logic
        if controls.starter and electrical_available and not self.running:
            self.starting = True
            # Starter cranks engine
            target_rpm = 200.0  # Starter cranks at ~200 RPM
            self.rpm = min(target_rpm, self.rpm + 400.0 * dt)

            # Engine can catch and start if conditions met
            can_start = self._can_start_engine(controls, fuel_available)
            if can_start and self.rpm >= self.config.starter_rpm_threshold:
                self.running = True
                self.starting = False
                logger.info("Engine started at %.0f RPM", self.rpm)
        else:
            self.starting = False

        # Running engine logic
        if self.running:
            self._update_running_engine(dt, controls, fuel_available)
        else:
            # Engine off or windmilling
            self.rpm = max(0.0, self.rpm - 300.0 * dt)  # Wind down
            self.fuel_flow_gph = 0.0
            self.horsepower = 0.0

        # Update temperatures
        self._update_temperatures(dt)

        # Update oil pressure (depends on RPM and oil temp)
        self._update_oil_pressure()

    def get_state(self) -> EngineState:
        """Get current engine state.

        Returns:
            Current engine state with all parameters.
        """
        warnings_list = []
        warning_str = self._get_warnings()
        if warning_str:
            warnings_list.append(warning_str)

        failures_list = []
        if self.failed and self.failure_type:
            failures_list.append(self.failure_type)

        # Convert Fahrenheit to Celsius for oil temp and CHT
        oil_temp_c = (self.oil_temp_f - 32) * 5 / 9
        cht_c = (self.cht_f - 32) * 5 / 9

        return EngineState(
            engine_type=EngineType.PISTON_NATURALLY_ASPIRATED,
            running=self.running,
            power_output_hp=self.horsepower,
            fuel_flow_gph=self.fuel_flow_gph,
            temperature_c=oil_temp_c,  # Primary temperature
            rpm=self.rpm,
            manifold_pressure_inhg=self.manifold_pressure,
            oil_pressure_psi=self.oil_pressure_psi,
            oil_temperature_c=oil_temp_c,
            cylinder_head_temp_c=cht_c,
            n1_percent=None,  # Not applicable for piston
            n2_percent=None,  # Not applicable for piston
            itt_c=None,  # Not applicable for piston
            epr=None,  # Not applicable for piston
            starter_engaged=self.starting,
            warnings=warnings_list,
            failures=failures_list,
        )

    def get_thrust_force(self) -> float:
        """Get thrust force in pounds.

        Returns:
            Thrust force for physics calculations.
        """
        return self._calculate_thrust()

    def can_start(self) -> bool:
        """Check if engine can start.

        Returns:
            True if engine can potentially start (doesn't guarantee it will).
        """
        return not self.failed and not self.running

    def get_fuel_consumption_rate(self) -> float:
        """Get current fuel consumption rate.

        Returns:
            Fuel flow rate in gallons per hour.
        """
        return self.fuel_flow_gph

    def simulate_failure(self, failure_type: str) -> None:
        """Simulate engine failure for training.

        Args:
            failure_type: Type of failure to simulate.
                "oil_pressure" - Loss of oil pressure
                "overheat" - Overheating
                "seizure" - Engine seizure
                "fire" - Engine fire
                "magneto" - Magneto failure
        """
        self.failed = True
        self.failure_type = failure_type
        self.running = False
        logger.warning("Engine failure simulated: %s", failure_type)

    def _can_start_engine(self, controls: EngineControls, fuel_available: float) -> bool:
        """Check if engine can start given current conditions.

        Args:
            controls: Engine controls.
            fuel_available: Available fuel flow in GPH.

        Returns:
            True if engine can start.
        """
        # Need at least one magneto on
        if not (controls.magneto_left or controls.magneto_right):
            return False

        # Need fuel
        if fuel_available <= 0.0:
            return False

        # Need reasonable mixture (not full lean)
        if controls.mixture < 0.1:
            return False

        # Cold engine needs more throttle (priming effect)
        return not (self._warmup_factor < 0.3 and controls.throttle < 0.1)

    def _update_running_engine(
        self, dt: float, controls: EngineControls, fuel_available: float
    ) -> None:
        """Update running engine parameters.

        Args:
            dt: Delta time in seconds.
            controls: Engine controls.
            fuel_available: Available fuel flow in GPH.
        """
        # Check magnetos - engine dies if both off (NO FORGIVENESS)
        if not (controls.magneto_left or controls.magneto_right):
            logger.warning("Both magnetos off - engine shutdown")
            self.running = False
            return

        # Target RPM based on throttle
        target_rpm = (
            self.config.idle_rpm + (self.config.max_rpm - self.config.idle_rpm) * controls.throttle
        )

        # RPM response (inertia)
        rpm_rate = 500.0  # RPM per second
        if self.rpm < target_rpm:
            self.rpm = min(target_rpm, self.rpm + rpm_rate * dt)
        else:
            self.rpm = max(target_rpm, self.rpm - rpm_rate * dt)

        # Calculate power output
        self._calculate_power(controls)

        # Calculate fuel consumption
        self._calculate_fuel_consumption(controls, fuel_available)

        # Warm up engine
        self._warmup_factor = min(1.0, self._warmup_factor + 0.05 * dt)

    def _calculate_power(self, controls: EngineControls) -> None:
        """Calculate engine power output.

        Args:
            controls: Engine controls.
        """
        # Power depends on RPM and throttle
        rpm_factor = self.rpm / self.config.max_rpm
        throttle_factor = controls.throttle

        # Mixture adjustment (too rich or too lean reduces power)
        mixture_factor = 1.0
        if controls.mixture < 0.5:  # Too lean
            mixture_factor = controls.mixture * 2.0
        elif controls.mixture > 0.9:  # Too rich
            mixture_factor = 1.0 - (controls.mixture - 0.9) * 2.0

        # Warmup penalty (cold engine makes less power)
        warmup_penalty = 0.7 + 0.3 * self._warmup_factor

        # Calculate horsepower
        self.horsepower = (
            self.config.max_horsepower
            * rpm_factor
            * throttle_factor
            * mixture_factor
            * warmup_penalty
        )

        # Manifold pressure (throttle controlled)
        self.manifold_pressure = 10.0 + 19.92 * controls.throttle  # 10-29.92 inHg

    def _calculate_fuel_consumption(self, controls: EngineControls, fuel_available: float) -> None:
        """Calculate fuel consumption rate.

        Args:
            controls: Engine controls.
            fuel_available: Available fuel flow in GPH.
        """
        # Base fuel flow on power output
        power_factor = self.horsepower / self.config.max_horsepower

        # Fuel flow increases with power
        target_fuel_flow = (
            self.config.fuel_flow_idle_gph
            + (self.config.fuel_flow_max_gph - self.config.fuel_flow_idle_gph) * power_factor
        )

        # Mixture adjustment (rich = more fuel)
        mixture_multiplier = 0.5 + 0.5 * controls.mixture

        target_fuel_flow *= mixture_multiplier

        # Clamp to available fuel
        self.fuel_flow_gph = min(target_fuel_flow, fuel_available)

        # If we can't get enough fuel, engine performance suffers
        if fuel_available < target_fuel_flow:
            # Reduce power proportionally
            fuel_ratio = fuel_available / target_fuel_flow if target_fuel_flow > 0 else 0.0
            self.horsepower *= fuel_ratio

    def _calculate_thrust(self) -> float:
        """Calculate thrust force from propeller.

        Returns:
            Thrust in pounds.
        """
        if not self.running:
            return 0.0

        # Simple thrust model: thrust = horsepower * efficiency / velocity
        # At zero airspeed (static), use simplified formula
        # Typical propeller efficiency: 0.8
        # Thrust (lbs) ≈ horsepower * 375 * efficiency / velocity
        # At static (takeoff), velocity is low, so thrust is high
        # Simplified: static thrust ≈ 2.5 * horsepower for small aircraft
        static_thrust = 2.5 * self.horsepower

        # TODO: Factor in airspeed when available (thrust decreases with speed)
        return static_thrust

    def _update_temperatures(self, dt: float) -> None:
        """Update engine temperatures.

        Args:
            dt: Delta time in seconds.
        """
        # Target temperatures based on power output
        power_factor = self.horsepower / self.config.max_horsepower

        # Oil temperature rises with power
        target_oil_temp = 70.0 + 150.0 * power_factor  # 70-220°F
        if self.oil_temp_f < target_oil_temp:
            self.oil_temp_f = min(target_oil_temp, self.oil_temp_f + 20.0 * dt)
        else:
            self.oil_temp_f = max(target_oil_temp, self.oil_temp_f - 10.0 * dt)

        # CHT temperature
        target_cht = 70.0 + 350.0 * power_factor  # 70-420°F
        if self.cht_f < target_cht:
            self.cht_f = min(target_cht, self.cht_f + 30.0 * dt)
        else:
            self.cht_f = max(target_cht, self.cht_f - 15.0 * dt)

    def _update_oil_pressure(self) -> None:
        """Update oil pressure based on RPM and oil temperature."""
        if not self.running:
            self.oil_pressure_psi = 0.0
            return

        # Oil pressure increases with RPM
        rpm_factor = self.rpm / self.config.max_rpm

        # Cold oil = higher pressure, hot oil = lower pressure
        temp_factor = 1.0
        if self.oil_temp_f < 150.0:
            temp_factor = 1.3  # Cold oil, higher pressure
        elif self.oil_temp_f > 220.0:
            temp_factor = 0.8  # Hot oil, lower pressure

        # Calculate oil pressure
        base_pressure = (
            self.config.min_oil_pressure_idle_psi
            + (self.config.max_oil_pressure_psi - self.config.min_oil_pressure_idle_psi)
            * rpm_factor
        )

        self.oil_pressure_psi = base_pressure * temp_factor

    def _get_warnings(self) -> str:
        """Get current engine warnings.

        Returns:
            Warning string or empty string if no warnings.
        """
        warnings = []

        if self.running:
            # Oil pressure low
            if self.oil_pressure_psi < self.config.min_oil_pressure_idle_psi:
                warnings.append("LOW OIL PRESSURE")

            # Oil temp high
            if self.oil_temp_f > self.config.max_oil_temp_f:
                warnings.append("HIGH OIL TEMP")

            # CHT high
            if self.cht_f > self.config.max_cht_f:
                warnings.append("HIGH CHT")

        return ", ".join(warnings) if warnings else ""

    def _update_failed_engine(self, dt: float) -> None:
        """Update failed engine (windmill down).

        Args:
            dt: Delta time in seconds.
        """
        self.running = False
        self.starting = False
        self.rpm = max(0.0, self.rpm - 200.0 * dt)
        self.fuel_flow_gph = 0.0
        self.horsepower = 0.0
        self.oil_pressure_psi = 0.0

        # Temperatures decay
        self.oil_temp_f = max(70.0, self.oil_temp_f - 10.0 * dt)
        self.cht_f = max(70.0, self.cht_f - 15.0 * dt)

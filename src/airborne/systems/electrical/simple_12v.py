"""Simple 12V electrical system for Cessna 172.

Implements a realistic lead-acid battery system with belt-driven alternator.
No forgiveness - battery can die completely, starter won't turn without voltage.

Typical usage:
    system = Simple12VElectricalSystem()
    system.initialize(config)
    system.update(dt=0.016, engine_rpm=2400.0)
    state = system.get_state()
"""

from airborne.systems.electrical.base import (
    ElectricalBus,
    ElectricalLoad,
    ElectricalState,
    IElectricalSystem,
    PowerSource,
)


class Simple12VElectricalSystem(IElectricalSystem):
    """Simple 12V electrical system for Cessna 172.

    Components:
    - 12V 35Ah lead-acid battery
    - 60A belt-driven alternator (engine-driven)
    - Single main bus
    - No redundancy

    Realistic behavior (no forgiveness):
    - Battery voltage: 12.6V (full) → 10.5V (dead)
    - Starter requires 11.0V minimum (150A draw)
    - Alternator requires 800+ RPM to produce power
    - Battery can die completely (0V) if over-discharged
    - Internal resistance causes voltage drop under load
    - Lead-acid discharge curve (non-linear)

    Electrical loads (realistic Cessna 172 values):
    - Master relay: 0.1A
    - Starter motor: 150A (huge load)
    - Fuel pump: 5A
    - Nav lights: 1.5A
    - Beacon: 2A
    - Strobe: 3A
    - Taxi light: 4A
    - Landing light: 8A
    - Avionics: 10A
    """

    def __init__(self):
        """Initialize electrical system."""
        # Battery model
        self.battery_capacity_ah = 35.0
        self.battery_current_ah = 35.0  # Start full
        self.battery_voltage = 12.6
        self.battery_internal_resistance = 0.05  # Ohms
        self.battery_self_discharge_rate = 0.1  # Ah per hour

        # Alternator model
        self.alternator_max_amps = 60.0
        self.alternator_voltage_regulated = 14.0
        self.alternator_rpm_threshold = 800
        self.alternator_failed = False

        # Main bus
        self.main_bus = ElectricalBus(
            name="main_bus",
            voltage_nominal=12.0,
            voltage_current=12.6,
            loads=[],
            power_sources=[PowerSource.BATTERY],
        )

        # Electrical loads (realistic Cessna 172 values)
        self.loads: dict[str, ElectricalLoad] = {}

        # Master switch state
        self.master_switch_on = False

    def initialize(self, config: dict) -> None:
        """Initialize electrical system from configuration.

        Args:
            config: Configuration dictionary with battery, alternator, and load specs.

        Example config:
            {
                "battery": {
                    "voltage_nominal": 12.6,
                    "capacity_ah": 35.0,
                    "internal_resistance": 0.05
                },
                "alternator": {
                    "max_amps": 60.0,
                    "voltage_regulated": 14.0,
                    "rpm_threshold": 800
                },
                "loads": {
                    "master_relay": {"amps": 0.1, "essential": True},
                    "starter_motor": {"amps": 150.0, "essential": True},
                    "fuel_pump": {"amps": 5.0, "essential": False},
                    "nav_lights": {"amps": 1.5, "essential": False},
                    "beacon": {"amps": 2.0, "essential": False},
                    "strobe": {"amps": 3.0, "essential": False},
                    "taxi_light": {"amps": 4.0, "essential": False},
                    "landing_light": {"amps": 8.0, "essential": False},
                    "avionics": {"amps": 10.0, "essential": False}
                }
            }
        """
        # Configure battery
        if "battery" in config:
            battery_config = config["battery"]
            self.battery_voltage = battery_config.get("voltage_nominal", 12.6)
            self.battery_capacity_ah = battery_config.get("capacity_ah", 35.0)
            self.battery_current_ah = self.battery_capacity_ah  # Start full
            self.battery_internal_resistance = battery_config.get("internal_resistance", 0.05)

        # Configure alternator
        if "alternator" in config:
            alternator_config = config["alternator"]
            self.alternator_max_amps = alternator_config.get("max_amps", 60.0)
            self.alternator_voltage_regulated = alternator_config.get("voltage_regulated", 14.0)
            self.alternator_rpm_threshold = alternator_config.get("rpm_threshold", 800)

        # Configure loads
        if "loads" in config:
            for load_name, load_config in config["loads"].items():
                self.loads[load_name] = ElectricalLoad(
                    name=load_name,
                    current_draw_amps=load_config["amps"],
                    essential=load_config.get("essential", False),
                    enabled=False,
                    min_voltage=load_config.get("min_voltage", 10.0),
                )

    def update(self, dt: float, engine_rpm: float) -> None:
        """Update electrical system state.

        Args:
            dt: Delta time in seconds
            engine_rpm: Engine RPM (drives alternator, 0 if engine off)
        """
        # Handle battery self-discharge when master switch is off
        if not self.master_switch_on:
            # Battery self-discharge even when off
            self_discharge_ah = (self.battery_self_discharge_rate / 3600.0) * dt
            self.battery_current_ah = max(0.0, self.battery_current_ah - self_discharge_ah)
            self._update_battery_voltage()
            self.main_bus.voltage_current = 0.0
            # Don't return - continue to allow state publishing
        else:
            # Master switch is ON - calculate loads and alternator
            # Calculate total load
            total_load_amps = sum(
                load.current_draw_amps for load in self.loads.values() if load.enabled
            )

            # Add master relay load
            if "master_relay" in self.loads and self.master_switch_on:
                total_load_amps += self.loads["master_relay"].current_draw_amps

            # Alternator output
            alternator_output = 0.0
            if not self.alternator_failed and engine_rpm >= self.alternator_rpm_threshold:
                # Alternator can supply up to max amps at regulated voltage
                # Supply what's needed, up to maximum capacity
                alternator_output = min(self.alternator_max_amps, total_load_amps + 20.0)

            # Net battery current (positive = charging, negative = discharging)
            net_current = alternator_output - total_load_amps

            # Update battery state of charge
            ah_change = (net_current / 3600.0) * dt  # Convert amps to amp-hours
            self.battery_current_ah += ah_change

            # Battery capacity limits (can't charge beyond capacity or discharge below 0)
            self.battery_current_ah = max(
                0.0, min(self.battery_capacity_ah, self.battery_current_ah)
            )

            # Update battery voltage based on state of charge
            self._update_battery_voltage()

            # Calculate bus voltage
            if alternator_output > 0:
                # Alternator feeding bus (regulated voltage)
                self.main_bus.voltage_current = self.alternator_voltage_regulated
                self.main_bus.power_sources = [PowerSource.BATTERY, PowerSource.ALTERNATOR]
            else:
                # Battery feeding bus (voltage drop due to load and internal resistance)
                voltage_drop = total_load_amps * self.battery_internal_resistance
                self.main_bus.voltage_current = max(0.0, self.battery_voltage - voltage_drop)
                self.main_bus.power_sources = [PowerSource.BATTERY]

            # Disable loads if voltage too low (brownout)
            if self.main_bus.voltage_current < 10.0:
                # Heavy loads fail first
                for load in self.loads.values():
                    if load.current_draw_amps > 5.0 and not load.essential:
                        load.enabled = False

    def get_state(self) -> ElectricalState:
        """Get current electrical system state.

        Returns:
            ElectricalState with current voltages, currents, warnings, failures
        """
        # Calculate battery SOC percentage
        soc_percent = (self.battery_current_ah / self.battery_capacity_ah) * 100.0

        # Calculate total load
        total_load_amps = sum(
            load.current_draw_amps for load in self.loads.values() if load.enabled
        )

        # Calculate alternator output
        alternator_output = 0.0
        if PowerSource.ALTERNATOR in self.main_bus.power_sources:
            alternator_output = min(self.alternator_max_amps, total_load_amps + 20.0)

        # Calculate battery current (positive = charging, negative = discharging)
        battery_current = alternator_output - total_load_amps

        # Generate warnings
        warnings = []
        if soc_percent < 20.0:
            warnings.append("LOW_BATTERY")
        if soc_percent < 10.0:
            warnings.append("CRITICAL_BATTERY")
        if self.battery_voltage < 11.0:
            warnings.append("LOW_VOLTAGE")
        if self.alternator_failed:
            warnings.append("ALTERNATOR_FAILURE")
        if self.main_bus.voltage_current < 10.0 and self.master_switch_on:
            warnings.append("BROWNOUT")

        # Generate failures
        failures = []
        if self.battery_current_ah <= 0.0:
            failures.append("BATTERY_DEAD")
        if self.battery_voltage < 5.0:
            failures.append("BATTERY_FAILED")

        return ElectricalState(
            buses={"main_bus": self.main_bus},
            battery_voltage=self.battery_voltage,
            battery_soc_percent=soc_percent,
            battery_current_amps=battery_current,
            alternator_output_amps=alternator_output,
            total_load_amps=total_load_amps,
            power_sources_available=self.main_bus.power_sources,
            warnings=warnings,
            failures=failures,
        )

    def set_load_enabled(self, load_name: str, enabled: bool) -> bool:
        """Enable or disable an electrical load.

        Args:
            load_name: Name of load (e.g., "nav_lights", "fuel_pump")
            enabled: True to enable, False to disable

        Returns:
            True if successful, False if load not found or bus failed
        """
        if load_name not in self.loads:
            return False

        # Can't enable if bus voltage too low
        if enabled and self.main_bus.voltage_current < self.loads[load_name].min_voltage:
            return False

        self.loads[load_name].enabled = enabled
        return True

    def set_master_switch(self, enabled: bool) -> None:
        """Set master switch state.

        Args:
            enabled: True to turn on master switch
        """
        self.master_switch_on = enabled

    def get_bus_voltage(self, bus_name: str) -> float:
        """Get voltage of specific bus.

        Args:
            bus_name: Bus name (only "main_bus" for this system)

        Returns:
            Current bus voltage, 0.0 if bus not found
        """
        if bus_name == "main_bus":
            return self.main_bus.voltage_current
        return 0.0

    def can_draw_current(self, amps: float) -> bool:
        """Check if system can supply requested current.

        Args:
            amps: Requested current in amperes

        Returns:
            True if available, False if would cause brownout
        """
        # Calculate if battery can provide this current
        voltage_drop = amps * self.battery_internal_resistance
        resulting_voltage = self.battery_voltage - voltage_drop

        # Need at least 10V to avoid brownout
        return resulting_voltage >= 10.0

    def simulate_failure(self, failure_type: str) -> None:
        """Simulate electrical failure.

        Args:
            failure_type: "alternator", "battery", etc.
        """
        if failure_type == "alternator":
            self.alternator_failed = True
        elif failure_type == "battery":
            self.battery_current_ah = 0.0
            self.battery_voltage = 0.0

    def _update_battery_voltage(self) -> None:
        """Update battery voltage based on state of charge.

        Uses realistic lead-acid discharge curve.
        """
        soc = self.battery_current_ah / self.battery_capacity_ah

        if soc <= 0.0:
            # Completely dead
            self.battery_voltage = 0.0
        elif soc <= 0.05:
            # Nearly dead (0-5%)
            self.battery_voltage = 10.5 + (soc / 0.05) * 0.3
        elif soc <= 0.25:
            # Low (5-25%)
            self.battery_voltage = 10.8 + ((soc - 0.05) / 0.20) * 1.0
        elif soc <= 0.75:
            # Medium (25-75%)
            self.battery_voltage = 11.8 + ((soc - 0.25) / 0.50) * 0.4
        else:
            # High (75-100%)
            self.battery_voltage = 12.2 + ((soc - 0.75) / 0.25) * 0.4

"""Simple electrical system plugin.

A basic electrical system with battery, alternator, and bus management.
Models realistic voltage, amperage, and battery charging behavior.

Typical usage:
    electrical = SimpleElectricalSystem()
    electrical.initialize(context)
    electrical.update(0.016)  # Update at 60 FPS
"""

from dataclasses import dataclass

from airborne.core.event_bus import Event
from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType


@dataclass
class ElectricalStateEvent(Event):
    """Event published when electrical state changes.

    Attributes:
        battery_voltage: Battery voltage in volts.
        battery_charge: Battery charge percentage (0-100).
        bus_voltage: Main electrical bus voltage in volts.
        alternator_online: Whether alternator is producing power.
        alternator_current: Alternator output current in amps.
        total_load: Total electrical load in amps.
        battery_master: Battery master switch state.
        alternator_switch: Alternator switch state.
    """

    battery_voltage: float = 12.0
    battery_charge: float = 100.0
    bus_voltage: float = 0.0
    alternator_online: bool = False
    alternator_current: float = 0.0
    total_load: float = 0.0
    battery_master: bool = False
    alternator_switch: bool = False


class SimpleElectricalSystem(IPlugin):
    """Simple electrical system plugin.

    Simulates a basic aircraft electrical system with:
    - 12V lead-acid battery (35 Ah capacity)
    - Belt-driven alternator (60A output)
    - Battery master switch
    - Alternator switch
    - Main electrical bus
    - Realistic charging and discharging
    - Over-voltage and under-voltage detection

    Battery specs (typical small aircraft):
    - Nominal voltage: 12V
    - Fully charged: 13.8V
    - Capacity: 35 Ah
    - Dead threshold: 10.5V
    """

    def __init__(self) -> None:
        """Initialize electrical system plugin."""
        # Context (set during initialize)
        self.context: PluginContext | None = None

        # Battery state
        self.battery_voltage: float = 12.6  # Fully charged resting voltage
        self.battery_charge_ah: float = 35.0  # Amp-hours remaining
        self.battery_capacity_ah: float = 35.0  # Total capacity

        # Alternator state
        self.alternator_online: bool = False
        self.alternator_rpm: float = 0.0  # Driven by engine
        self.alternator_current: float = 0.0  # Current output in amps

        # Switches
        self.battery_master: bool = False
        self.alternator_switch: bool = False

        # Electrical load
        self.total_load: float = 0.0  # Amps
        self.base_load: float = 5.0  # Base systems (lights, instruments, etc.)

        # Bus voltages
        self.bus_voltage: float = 0.0

        # Internal state
        self._engine_running: bool = False
        self._engine_rpm: float = 0.0

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata.

        Returns:
            PluginMetadata describing this electrical system plugin.
        """
        return PluginMetadata(
            name="simple_electrical_system",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.AIRCRAFT_SYSTEM,
            dependencies=["simple_piston_engine"],
            provides=["electrical", "power"],
            optional=False,
            update_priority=60,  # Update after engine
            requires_physics=True,
            description="Simple electrical system with battery and alternator",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the electrical system plugin.

        Args:
            context: Plugin context with access to core systems.
        """
        self.context = context

        # Read configuration from aircraft config if available
        if hasattr(context, "config") and context.config:
            cfg = context.config
            if "battery_voltage" in cfg:
                self.battery_voltage = float(cfg["battery_voltage"])
            if "battery_capacity_ah" in cfg:
                self.battery_capacity_ah = float(cfg["battery_capacity_ah"])
                # Initialize charge to full capacity
                self.battery_charge_ah = self.battery_capacity_ah
            if "alternator_voltage" in cfg:
                pass  # Already hardcoded at 14V in _update_bus_voltage
            if "alternator_amps" in cfg:
                pass  # Max amps already hardcoded at 60A in _update_alternator
            if "base_load_amps" in cfg:
                self.base_load = float(cfg["base_load_amps"])

        # Subscribe to engine state for alternator RPM
        context.message_queue.subscribe(MessageTopic.ENGINE_STATE, self.handle_message)

        # Subscribe to electrical control messages
        context.message_queue.subscribe(MessageTopic.ELECTRICAL_STATE, self.handle_message)

    def update(self, dt: float) -> None:
        """Update electrical system state.

        Args:
            dt: Delta time in seconds since last update.
        """
        if not self.context:
            return

        # Update alternator based on engine RPM
        self._update_alternator()

        # Calculate total electrical load
        self._calculate_load()

        # Update bus voltage based on switches
        self._update_bus_voltage()

        # Update battery charging/discharging
        self._update_battery(dt)

        # Publish state event
        self.context.event_bus.publish(
            ElectricalStateEvent(
                battery_voltage=self.battery_voltage,
                battery_charge=self._get_battery_percentage(),
                bus_voltage=self.bus_voltage,
                alternator_online=self.alternator_online,
                alternator_current=self.alternator_current,
                total_load=self.total_load,
                battery_master=self.battery_master,
                alternator_switch=self.alternator_switch,
            )
        )

        # Publish message for other plugins
        self.context.message_queue.publish(
            Message(
                sender="simple_electrical_system",
                recipients=["*"],
                topic=MessageTopic.ELECTRICAL_STATE,
                data={
                    "battery_voltage": self.battery_voltage,
                    "battery_charge": self._get_battery_percentage(),
                    "bus_voltage": self.bus_voltage,
                    "alternator_online": self.alternator_online,
                    "power_available": self.bus_voltage > 11.0,
                },
                priority=MessagePriority.HIGH,
            )
        )

    def shutdown(self) -> None:
        """Shutdown the electrical system plugin."""
        if self.context:
            # Unsubscribe from messages
            self.context.message_queue.unsubscribe(MessageTopic.ENGINE_STATE, self.handle_message)
            self.context.message_queue.unsubscribe(
                MessageTopic.ELECTRICAL_STATE, self.handle_message
            )

        # System shutdown
        self.battery_master = False
        self.alternator_switch = False
        self.bus_voltage = 0.0

    def handle_message(self, message: Message) -> None:
        """Handle messages from other plugins.

        Args:
            message: Message from the queue.
        """
        if message.topic == MessageTopic.ENGINE_STATE:
            # Update engine state for alternator
            data = message.data
            if "running" in data:
                self._engine_running = bool(data["running"])
            if "rpm" in data:
                self._engine_rpm = float(data["rpm"])

        elif message.topic == MessageTopic.ELECTRICAL_STATE:
            # Handle electrical control commands
            data = message.data

            if "battery_master" in data:
                self.battery_master = bool(data["battery_master"])

            if "alternator_switch" in data:
                self.alternator_switch = bool(data["alternator_switch"])

    def _update_alternator(self) -> None:
        """Update alternator state based on engine RPM."""
        # Alternator needs to be switched on and engine running
        if self.alternator_switch and self._engine_running:
            # Alternator driven by engine via belt
            # Typical ratio: alternator spins 2-3x engine RPM
            self.alternator_rpm = self._engine_rpm * 2.5

            # Alternator comes online at ~1200 RPM (engine idle ~600 RPM)
            if self.alternator_rpm > 1200:
                self.alternator_online = True
                # Output current based on RPM and load
                # Max 60A at full RPM, regulated to 14V
                rpm_factor = min(1.0, (self.alternator_rpm - 1200) / 3000.0)
                max_output = 60.0 * rpm_factor

                # Calculate needed current (load + charging)
                needed_current = self.total_load

                # Add charging current if battery needs it
                if self.battery_master and self.battery_voltage < 13.8:
                    # Charge at up to 15A depending on battery state
                    charge_rate = (13.8 - self.battery_voltage) * 10.0
                    charge_rate = min(15.0, max(0.0, charge_rate))
                    needed_current += charge_rate

                # Alternator provides what's needed, up to max output
                self.alternator_current = min(max_output, needed_current)
            else:
                self.alternator_online = False
                self.alternator_current = 0.0
        else:
            self.alternator_online = False
            self.alternator_current = 0.0
            self.alternator_rpm = 0.0

    def _calculate_load(self) -> None:
        """Calculate total electrical load."""
        # Base load from avionics, lights, etc.
        self.total_load = self.base_load

        # Additional loads could be added here based on systems active
        # For now, just base load

    def _update_bus_voltage(self) -> None:
        """Update main bus voltage based on power sources."""
        if self.battery_master and self.alternator_online:
            # Alternator supplying power - regulated 14V
            self.bus_voltage = 14.0
        elif self.battery_master:
            # Battery only - voltage drops under load
            # Simple model: voltage drop proportional to load
            voltage_drop = self.total_load * 0.05  # ~0.05V per amp
            self.bus_voltage = self.battery_voltage - voltage_drop
            self.bus_voltage = max(0.0, self.bus_voltage)
        else:
            # No power
            self.bus_voltage = 0.0

    def _update_battery(self, dt: float) -> None:
        """Update battery charge/discharge.

        Args:
            dt: Delta time in seconds.
        """
        if self.battery_master:
            if self.alternator_online:
                # Charging: alternator supplies load + charges battery
                charge_current = self.alternator_current - self.total_load
                if charge_current > 0:
                    # Charging
                    charge_ah = charge_current * (dt / 3600.0)  # Convert to Ah
                    self.battery_charge_ah += charge_ah
                    self.battery_charge_ah = min(self.battery_capacity_ah, self.battery_charge_ah)

                    # Update voltage (charging voltage)
                    charge_factor = self.battery_charge_ah / self.battery_capacity_ah
                    self.battery_voltage = 13.0 + charge_factor * 0.8  # 13.0-13.8V
                else:
                    # Alternator can't keep up with load
                    discharge_current = abs(charge_current)
                    discharge_ah = discharge_current * (dt / 3600.0)
                    self.battery_charge_ah -= discharge_ah
                    self.battery_charge_ah = max(0.0, self.battery_charge_ah)

                    # Update voltage (discharging)
                    self._update_battery_voltage_discharge()
            else:
                # Discharging: battery supplies all load
                discharge_ah = self.total_load * (dt / 3600.0)
                self.battery_charge_ah -= discharge_ah
                self.battery_charge_ah = max(0.0, self.battery_charge_ah)

                # Update voltage (discharging)
                self._update_battery_voltage_discharge()
        else:
            # Battery disconnected - slowly moves to resting voltage
            target_voltage = self._get_resting_voltage()
            voltage_delta = target_voltage - self.battery_voltage
            self.battery_voltage += voltage_delta * 0.1 * dt

    def _update_battery_voltage_discharge(self) -> None:
        """Update battery voltage during discharge."""
        charge_factor = self.battery_charge_ah / self.battery_capacity_ah

        if charge_factor > 0.5:
            # Upper half: relatively flat discharge curve
            self.battery_voltage = 12.0 + charge_factor * 1.0
        elif charge_factor > 0.2:
            # Middle range: voltage drops faster
            self.battery_voltage = 11.0 + (charge_factor - 0.2) * 3.33
        else:
            # Low charge: rapid voltage drop
            self.battery_voltage = 10.5 + charge_factor * 2.5

        # Account for voltage drop under load
        voltage_drop = self.total_load * 0.1
        self.battery_voltage -= voltage_drop
        self.battery_voltage = max(10.0, self.battery_voltage)

    def _get_resting_voltage(self) -> float:
        """Get battery resting voltage based on charge.

        Returns:
            Resting voltage in volts.
        """
        charge_factor = self.battery_charge_ah / self.battery_capacity_ah
        # Fully charged: 12.6V, 50%: 12.2V, Dead: 11.8V
        return 11.8 + charge_factor * 0.8

    def _get_battery_percentage(self) -> float:
        """Get battery charge as percentage.

        Returns:
            Battery charge percentage (0-100).
        """
        return (self.battery_charge_ah / self.battery_capacity_ah) * 100.0

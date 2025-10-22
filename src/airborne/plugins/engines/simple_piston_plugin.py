"""Simple piston engine plugin.

A basic piston engine model with starter, magnetos, and mixture control.
Suitable for small single-engine aircraft like Cessna 172.

Typical usage:
    engine = SimplePistonEngine()
    engine.initialize(context)
    engine.update(0.016)  # Update at 60 FPS
"""

from dataclasses import dataclass

from airborne.core.event_bus import Event
from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType

logger = get_logger(__name__)


@dataclass
class EngineStateEvent(Event):
    """Event published when engine state changes.

    Attributes:
        rpm: Engine revolutions per minute.
        manifold_pressure: Manifold pressure in inches of mercury.
        oil_temp: Oil temperature in degrees Celsius.
        oil_pressure: Oil pressure in PSI.
        fuel_flow: Fuel flow in gallons per hour.
        running: Whether engine is running.
        starter_engaged: Whether starter motor is engaged.
    """

    rpm: float = 0.0
    manifold_pressure: float = 0.0
    oil_temp: float = 0.0
    oil_pressure: float = 0.0
    fuel_flow: float = 0.0
    running: bool = False
    starter_engaged: bool = False


class SimplePistonEngine(IPlugin):
    """Simple piston engine plugin.

    Simulates a basic 4-cylinder piston engine with:
    - Electric starter motor
    - Dual magnetos
    - Mixture control
    - Basic thermodynamics (oil temp, CHT)
    - Realistic startup and shutdown behavior

    Engine specs (based on Lycoming O-320):
    - Max RPM: 2700
    - Idle RPM: 600
    - Max power: 160 HP
    - Displacement: 320 cubic inches
    """

    def __init__(self) -> None:
        """Initialize engine plugin."""
        # Context (set during initialize)
        self.context: PluginContext | None = None

        # Engine state
        self.rpm: float = 0.0
        self.manifold_pressure: float = 29.92  # Sea level pressure
        self.oil_temp: float = 20.0  # Celsius
        self.oil_pressure: float = 0.0  # PSI
        self.fuel_flow: float = 0.0  # GPH
        self.running: bool = False

        # Controls
        self.magneto_left: bool = False
        self.magneto_right: bool = False
        self.mixture: float = 1.0  # 0.0 = lean, 1.0 = rich
        self.throttle: float = 0.0  # 0.0 = idle, 1.0 = full
        self.starter_engaged: bool = False

        # Configurable starter requirements (set during initialize)
        self.starter_min_voltage: float = 11.0  # Minimum voltage to engage starter
        self.starter_current_draw: float = 150.0  # Current draw in amps
        self.requires_fuel: bool = True  # Whether fuel is required to start
        self.requires_magnetos: bool = True  # Whether magnetos are required to start

        # Engine parameters (set during initialize)
        self.idle_rpm: float = 600.0  # Idle RPM
        self.max_rpm: float = 2700.0  # Maximum RPM

        # Electrical state (from electrical system messages)
        self._electrical_voltage: float = 0.0
        self._electrical_available: bool = False
        self._fuel_available: bool = False

        # Internal state
        self._time_since_start: float = 0.0
        self._starter_time: float = 0.0
        self._combustion_energy: float = 0.0

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata.

        Returns:
            PluginMetadata describing this engine plugin.
        """
        return PluginMetadata(
            name="simple_piston_engine",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.AIRCRAFT_SYSTEM,
            dependencies=[],
            provides=["engine", "propulsion"],
            optional=False,
            update_priority=50,  # Update early (engines are high priority)
            requires_physics=True,
            description="Simple piston engine for small aircraft",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the engine plugin.

        Args:
            context: Plugin context with access to core systems.
        """
        self.context = context

        # Read starter requirements configuration from aircraft config if available
        if hasattr(context, "config") and context.config:
            cfg = context.config
            if "starter_min_voltage" in cfg:
                self.starter_min_voltage = float(cfg["starter_min_voltage"])
            if "starter_current_draw" in cfg:
                self.starter_current_draw = float(cfg["starter_current_draw"])
            if "requires_fuel" in cfg:
                self.requires_fuel = bool(cfg["requires_fuel"])
            if "requires_magnetos" in cfg:
                self.requires_magnetos = bool(cfg["requires_magnetos"])
            if "idle_rpm" in cfg:
                self.idle_rpm = float(cfg["idle_rpm"])
            if "max_rpm" in cfg:
                self.max_rpm = float(cfg["max_rpm"])

        # Subscribe to control messages
        context.message_queue.subscribe(MessageTopic.ENGINE_STATE, self.handle_message)

        # Subscribe to control input messages from InputManager (for throttle)
        context.message_queue.subscribe(MessageTopic.CONTROL_INPUT, self.handle_message)

        # Subscribe to electrical state messages (to check if starter can engage)
        context.message_queue.subscribe(MessageTopic.ELECTRICAL_STATE, self.handle_message)

        # Subscribe to fuel state messages (to check if fuel is available)
        context.message_queue.subscribe(MessageTopic.FUEL_STATE, self.handle_message)

        # Subscribe to control panel messages (custom topics)
        context.message_queue.subscribe("engine.magnetos", self.handle_message)
        context.message_queue.subscribe("engine.starter", self.handle_message)
        context.message_queue.subscribe("engine.mixture", self.handle_message)
        context.message_queue.subscribe("engine.throttle", self.handle_message)

    def update(self, dt: float) -> None:
        """Update engine state.

        Args:
            dt: Delta time in seconds since last update.
        """
        if not self.context:
            return

        # Update internal timers
        if self.running:
            self._time_since_start += dt
        if self.starter_engaged:
            self._starter_time += dt

        # Simulate engine behavior
        self._update_combustion(dt)
        self._update_rpm(dt)
        self._update_temperatures(dt)
        self._update_pressures()
        self._update_fuel_flow()

        # Publish state event
        self.context.event_bus.publish(
            EngineStateEvent(
                rpm=self.rpm,
                manifold_pressure=self.manifold_pressure,
                oil_temp=self.oil_temp,
                oil_pressure=self.oil_pressure,
                fuel_flow=self.fuel_flow,
                running=self.running,
                starter_engaged=self.starter_engaged,
            )
        )

        # Publish message for other plugins
        self.context.message_queue.publish(
            Message(
                sender="simple_piston_engine",
                recipients=["*"],
                topic=MessageTopic.ENGINE_STATE,
                data={
                    "rpm": self.rpm,
                    "manifold_pressure": self.manifold_pressure,
                    "oil_temp": self.oil_temp,
                    "oil_pressure": self.oil_pressure,
                    "fuel_flow": self.fuel_flow,
                    "running": self.running,
                    "power_hp": self._calculate_power(),
                },
                priority=MessagePriority.HIGH,
            )
        )

    def shutdown(self) -> None:
        """Shutdown the engine plugin."""
        if self.context:
            # Unsubscribe from messages
            self.context.message_queue.unsubscribe(MessageTopic.ENGINE_STATE, self.handle_message)
            self.context.message_queue.unsubscribe(MessageTopic.CONTROL_INPUT, self.handle_message)
            self.context.message_queue.unsubscribe(
                MessageTopic.ELECTRICAL_STATE, self.handle_message
            )
            self.context.message_queue.unsubscribe(MessageTopic.FUEL_STATE, self.handle_message)

            # Unsubscribe from control panel messages
            self.context.message_queue.unsubscribe("engine.magnetos", self.handle_message)
            self.context.message_queue.unsubscribe("engine.starter", self.handle_message)
            self.context.message_queue.unsubscribe("engine.mixture", self.handle_message)
            self.context.message_queue.unsubscribe("engine.throttle", self.handle_message)

        # Engine shutdown
        self.running = False
        self.rpm = 0.0

    def handle_message(self, message: Message) -> None:
        """Handle messages from other plugins.

        Args:
            message: Message from the queue.
        """
        if message.topic == MessageTopic.ENGINE_STATE:
            # Handle engine control commands
            data = message.data

            if "starter" in data:
                self.starter_engaged = bool(data["starter"])

            if "magneto_left" in data:
                self.magneto_left = bool(data["magneto_left"])

            if "magneto_right" in data:
                self.magneto_right = bool(data["magneto_right"])

            if "mixture" in data:
                old_mixture = self.mixture
                self.mixture = max(0.0, min(1.0, float(data["mixture"])))
                if abs(old_mixture - self.mixture) > 0.01:
                    logger.debug(
                        "Engine: Mixture changed from %.3f to %.3f (via ENGINE_STATE message)",
                        old_mixture,
                        self.mixture,
                    )

            if "throttle" in data:
                old_throttle = self.throttle
                self.throttle = max(0.0, min(1.0, float(data["throttle"])))
                if abs(old_throttle - self.throttle) > 0.01:
                    logger.debug(
                        "Engine: Throttle changed from %.3f to %.3f (via ENGINE_STATE message)",
                        old_throttle,
                        self.throttle,
                    )

        elif message.topic == MessageTopic.CONTROL_INPUT:
            # Handle control inputs from InputManager (for throttle)
            data = message.data
            if "throttle" in data:
                old_throttle = self.throttle
                self.throttle = max(0.0, min(1.0, float(data["throttle"])))
                if abs(old_throttle - self.throttle) > 0.01:
                    logger.debug(
                        "Engine: Throttle changed from %.3f to %.3f (via CONTROL_INPUT from InputManager)",
                        old_throttle,
                        self.throttle,
                    )

        elif message.topic == MessageTopic.ELECTRICAL_STATE:
            # Update electrical state from electrical system
            data = message.data
            if "bus_voltage" in data:
                self._electrical_voltage = float(data["bus_voltage"])
                # Check if we have enough voltage for starter
                self._electrical_available = self._electrical_voltage >= self.starter_min_voltage

        elif message.topic == MessageTopic.FUEL_STATE:
            # Update fuel availability from fuel system
            data = message.data
            if "fuel_available" in data:
                self._fuel_available = bool(data["fuel_available"])

        elif message.topic == "engine.magnetos":
            # Handle magneto switch from panel control
            # Panel sends: {"state": "BOTH", "state_index": 3}
            # States: [OFF, R, L, BOTH, START]
            data = message.data
            if "state_index" in data:
                state_index = int(data["state_index"])
                # Map state_index to magneto positions
                if state_index == 0:  # OFF
                    self.magneto_left = False
                    self.magneto_right = False
                    self.starter_engaged = False
                elif state_index == 1:  # R
                    self.magneto_left = False
                    self.magneto_right = True
                    self.starter_engaged = False
                elif state_index == 2:  # L
                    self.magneto_left = True
                    self.magneto_right = False
                    self.starter_engaged = False
                elif state_index == 3:  # BOTH
                    self.magneto_left = True
                    self.magneto_right = True
                    self.starter_engaged = False
                elif state_index == 4:  # START
                    self.magneto_left = True
                    self.magneto_right = True
                    self.starter_engaged = True

        elif message.topic == "engine.mixture":
            # Handle mixture lever from panel control
            # Panel sends: {"state": "RICH", "state_index": 2}
            # States: [IDLE_CUTOFF, LEAN, RICH]
            data = message.data
            if "state_index" in data:
                state_index = int(data["state_index"])
                # Map state_index to mixture values (0.0 to 1.0)
                if state_index == 0:  # IDLE_CUTOFF
                    self.mixture = 0.0
                elif state_index == 1:  # LEAN
                    self.mixture = 0.5
                elif state_index == 2:  # RICH
                    self.mixture = 1.0

        elif message.topic == "engine.starter":
            # Handle starter button from panel control
            # Panel sends: {"action": "pressed"}
            data = message.data
            if "action" in data and data["action"] == "pressed":
                self.starter_engaged = True

        elif message.topic == "engine.throttle":
            # Handle throttle lever from panel control
            # Panel sends: {"value": 50.0, "min_value": 0.0, "max_value": 100.0}
            data = message.data
            if "value" in data:
                # Normalize from 0-100 to 0.0-1.0
                old_throttle = self.throttle
                throttle_pct = float(data["value"])
                self.throttle = max(0.0, min(1.0, throttle_pct / 100.0))
                if abs(old_throttle - self.throttle) > 0.01:
                    logger.debug(
                        "Engine: Throttle changed from %.3f to %.3f (via engine.throttle panel message, %.1f%%)",
                        old_throttle,
                        self.throttle,
                        throttle_pct,
                    )

    def _update_combustion(self, dt: float) -> None:
        """Update combustion process.

        Args:
            dt: Delta time in seconds.
        """
        # Check if engine can run - using configurable requirements

        # Ignition check (configurable via requires_magnetos)
        if self.requires_magnetos:
            has_ignition = self.magneto_left or self.magneto_right
        else:
            has_ignition = True  # Some engines don't require magnetos

        # Fuel check (configurable via requires_fuel)
        if self.requires_fuel:
            has_fuel = self.mixture > 0.1 and self._fuel_available
        else:
            has_fuel = True  # Some engines don't require fuel (e.g., electric motors)

        # Starter check with electrical power requirement
        # Engine can run if:
        # 1. RPM is high enough that engine is spinning (from inertia or combustion)
        # 2. OR starter is actively engaged with electrical power
        can_start = self.rpm > 100  # Engine is spinning, can continue combusting
        if not can_start and self.starter_engaged:
            # Starter is engaged - check if we have electrical power
            if self._electrical_available:
                can_start = True  # Starter can crank with sufficient voltage
            # else: Starter engaged but no power - engine won't crank

        if has_ignition and has_fuel and can_start:
            # Engine is running or starting
            if not self.running and self.rpm > 400:
                self.running = True

            # Calculate combustion efficiency based on mixture
            # Best mixture is around 0.8 (slightly rich)
            mixture_efficiency = 1.0 - abs(self.mixture - 0.8) * 0.5
            mixture_efficiency = max(0.0, min(1.0, mixture_efficiency))

            # Target combustion energy based on throttle and mixture
            # During startup with starter, provide base combustion to help engine catch
            if self.starter_engaged and not self.running:
                base_combustion = 50.0  # Base energy during cranking
                target_energy = base_combustion + self.throttle * mixture_efficiency * 100.0
            else:
                # Engine needs minimum combustion energy to maintain idle RPM
                # Use same ratio as RPM: idle_rpm / max_rpm
                idle_energy_ratio = self.idle_rpm / self.max_rpm  # ~0.22 for 600/2700
                min_idle_energy = idle_energy_ratio * 100.0  # ~22 energy units at idle
                target_energy = max(min_idle_energy, self.throttle * mixture_efficiency * 100.0)

            # Smooth transition
            energy_rate = 200.0  # Energy change rate
            energy_delta = target_energy - self._combustion_energy
            max_change = energy_rate * dt
            self._combustion_energy += max(-max_change, min(max_change, energy_delta))
        else:
            # Engine is stopping
            if self.running and self.rpm < 200:
                self.running = False

            # Decay combustion energy
            self._combustion_energy -= 50.0 * dt
            self._combustion_energy = max(0.0, self._combustion_energy)

    def _update_rpm(self, dt: float) -> None:
        """Update engine RPM.

        Args:
            dt: Delta time in seconds.
        """
        # Calculate target RPM
        if self.running:
            # Running: RPM based on throttle and combustion
            # Need combustion energy to maintain RPM
            if self._combustion_energy > 10.0:
                target_rpm = self.idle_rpm + (self.max_rpm - self.idle_rpm) * self.throttle
            else:
                # Not enough combustion, engine dying
                target_rpm = self._combustion_energy * 20.0
        elif self.starter_engaged:
            # Starter cranking
            target_rpm = 200.0 + self._combustion_energy * 5.0
        else:
            # Engine off
            target_rpm = 0.0

        # Smooth RPM change (simulate inertia)
        rpm_rate = 500.0  # RPM change rate
        if self.rpm < target_rpm:
            # Accelerating
            rpm_rate = 800.0
        else:
            # Decelerating
            rpm_rate = 300.0

        rpm_delta = target_rpm - self.rpm
        max_change = rpm_rate * dt
        self.rpm += max(-max_change, min(max_change, rpm_delta))
        self.rpm = max(0.0, self.rpm)

    def _update_temperatures(self, dt: float) -> None:
        """Update engine temperatures.

        Args:
            dt: Delta time in seconds.
        """
        # Oil temp increases with RPM and combustion
        ambient_temp = 20.0  # Celsius
        target_temp = ambient_temp

        if self.running:
            # Running engine heats up
            rpm_factor = self.rpm / 2700.0
            combustion_factor = self._combustion_energy / 100.0
            target_temp = ambient_temp + 60.0 * rpm_factor + 20.0 * combustion_factor

        # Smooth temperature change
        temp_rate = 2.0  # Degrees per second
        temp_delta = target_temp - self.oil_temp
        max_change = temp_rate * dt
        self.oil_temp += max(-max_change, min(max_change, temp_delta))

    def _update_pressures(self) -> None:
        """Update engine pressures."""
        # Oil pressure increases with RPM
        if self.rpm > 200:
            # Pressure builds when spinning
            rpm_factor = min(1.0, self.rpm / 1000.0)
            self.oil_pressure = 20.0 + 40.0 * rpm_factor
        else:
            # No pressure when not spinning
            self.oil_pressure = 0.0

        # Manifold pressure (simplified - should be based on atmospheric and throttle)
        # Full throttle = atmospheric pressure
        # Closed throttle = vacuum (lower pressure)
        atmospheric = 29.92  # inches Hg at sea level
        if self.running:
            # Running engine creates vacuum
            vacuum = (1.0 - self.throttle) * 15.0
            self.manifold_pressure = atmospheric - vacuum
        else:
            # Engine off = atmospheric pressure
            self.manifold_pressure = atmospheric

    def _update_fuel_flow(self) -> None:
        """Update fuel flow rate."""
        if self.running:
            # Fuel flow based on RPM and mixture
            # Typical O-320: 8 GPH at cruise (2400 RPM)
            rpm_factor = self.rpm / 2700.0
            mixture_factor = self.mixture
            self.fuel_flow = 3.0 + 6.0 * rpm_factor * mixture_factor
        else:
            self.fuel_flow = 0.0

    def _calculate_power(self) -> float:
        """Calculate engine power output.

        Returns:
            Power in horsepower.
        """
        if not self.running:
            return 0.0

        # Max power: 160 HP at 2700 RPM
        max_power = 160.0
        rpm_factor = min(1.0, self.rpm / 2700.0)
        throttle_factor = self.throttle

        # Mixture affects power (too lean or too rich reduces power)
        mixture_efficiency = 1.0 - abs(self.mixture - 0.8) * 0.3
        mixture_efficiency = max(0.5, min(1.0, mixture_efficiency))

        power = max_power * rpm_factor * throttle_factor * mixture_efficiency
        return max(0.0, power)

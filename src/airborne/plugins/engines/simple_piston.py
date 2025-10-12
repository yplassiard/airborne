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
from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType


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

        # Subscribe to input events for engine controls
        # (In a real implementation, we'd subscribe to key bindings for
        # magnetos, mixture, etc. For now, we'll respond to messages only)

        # Subscribe to control messages
        context.message_queue.subscribe(MessageTopic.ENGINE_STATE, self.handle_message)

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
                self.mixture = max(0.0, min(1.0, float(data["mixture"])))

            if "throttle" in data:
                self.throttle = max(0.0, min(1.0, float(data["throttle"])))

    def _update_combustion(self, dt: float) -> None:
        """Update combustion process.

        Args:
            dt: Delta time in seconds.
        """
        # Check if engine can run
        has_ignition = self.magneto_left or self.magneto_right
        has_fuel = self.mixture > 0.1
        has_starter_or_rpm = self.starter_engaged or self.rpm > 300

        if has_ignition and has_fuel and has_starter_or_rpm:
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
                target_energy = self.throttle * mixture_efficiency * 100.0

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
                idle_rpm = 600.0
                max_rpm = 2700.0
                target_rpm = idle_rpm + (max_rpm - idle_rpm) * self.throttle
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

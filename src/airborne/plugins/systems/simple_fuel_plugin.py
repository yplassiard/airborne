"""Simple fuel system plugin.

A basic fuel system with tanks, pumps, and consumption tracking.
Models realistic fuel flow, pump operation, and gravity feed.

Typical usage:
    fuel = SimpleFuelSystem()
    fuel.initialize(context)
    fuel.update(0.016)  # Update at 60 FPS
"""

from dataclasses import dataclass

from airborne.core.event_bus import Event
from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType


@dataclass
class FuelStateEvent(Event):
    """Event published when fuel state changes.

    Attributes:
        left_tank_quantity: Left tank fuel in gallons.
        right_tank_quantity: Right tank fuel in gallons.
        total_quantity: Total fuel in gallons.
        fuel_flow: Current fuel flow rate in GPH.
        fuel_pressure: Fuel pressure in PSI.
        left_pump_on: Left fuel pump state.
        right_pump_on: Right fuel pump state.
        fuel_selector: Selected tank ('left', 'right', 'both', 'off').
    """

    left_tank_quantity: float = 0.0
    right_tank_quantity: float = 0.0
    total_quantity: float = 0.0
    fuel_flow: float = 0.0
    fuel_pressure: float = 0.0
    left_pump_on: bool = False
    right_pump_on: bool = False
    fuel_selector: str = "both"


class SimpleFuelSystem(IPlugin):
    """Simple fuel system plugin.

    Simulates a basic aircraft fuel system with:
    - Two wing tanks (left/right, 26 gallons each)
    - Electric fuel pumps
    - Gravity feed capability
    - Fuel selector valve (left/right/both/off)
    - Fuel pressure monitoring
    - Consumption tracking based on engine demand

    Fuel specs (typical Cessna 172):
    - Total capacity: 52 gallons (26 per tank)
    - Usable fuel: 48 gallons
    - Fuel type: 100LL Avgas (6 lbs/gallon)
    - System pressure: 3-5 PSI
    """

    def __init__(self) -> None:
        """Initialize fuel system plugin."""
        # Context (set during initialize)
        self.context: PluginContext | None = None

        # Fuel tanks
        self.left_tank_capacity: float = 26.0  # Gallons
        self.right_tank_capacity: float = 26.0
        self.left_tank_quantity: float = 26.0  # Start full
        self.right_tank_quantity: float = 26.0
        self.unusable_fuel: float = 2.0  # Per tank

        # Fuel selector
        self.fuel_selector: str = "both"  # off, left, right, both

        # Pumps
        self.left_pump_on: bool = False
        self.right_pump_on: bool = False

        # Fuel pressure
        self.fuel_pressure: float = 0.0  # PSI

        # Fuel flow
        self.fuel_flow: float = 0.0  # Gallons per hour

        # Internal state
        self._engine_fuel_demand: float = 0.0  # GPH from engine

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata.

        Returns:
            PluginMetadata describing this fuel system plugin.
        """
        return PluginMetadata(
            name="simple_fuel_system",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.AIRCRAFT_SYSTEM,
            dependencies=["simple_piston_engine"],
            provides=["fuel"],
            optional=False,
            update_priority=55,  # Update between engine and electrical
            requires_physics=True,
            description="Simple fuel system with tanks and pumps",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the fuel system plugin.

        Args:
            context: Plugin context with access to core systems.
        """
        self.context = context

        # Read configuration from aircraft config if available
        if hasattr(context, "config") and context.config:
            cfg = context.config
            if "left_tank_capacity" in cfg:
                self.left_tank_capacity = float(cfg["left_tank_capacity"])
                # Initialize quantity to full capacity
                self.left_tank_quantity = self.left_tank_capacity
            if "right_tank_capacity" in cfg:
                self.right_tank_capacity = float(cfg["right_tank_capacity"])
                # Initialize quantity to full capacity
                self.right_tank_quantity = self.right_tank_capacity
            if "unusable_fuel" in cfg:
                self.unusable_fuel = float(cfg["unusable_fuel"])
            if "fuel_selector" in cfg:
                self.fuel_selector = str(cfg["fuel_selector"])

        # Subscribe to engine state for fuel consumption
        context.message_queue.subscribe(MessageTopic.ENGINE_STATE, self.handle_message)

        # Subscribe to fuel control messages
        context.message_queue.subscribe(MessageTopic.FUEL_STATE, self.handle_message)

        # Publish initial state immediately after initialization
        self._publish_state()

    def update(self, dt: float) -> None:
        """Update fuel system state.

        Args:
            dt: Delta time in seconds since last update.
        """
        if not self.context:
            return

        # Update fuel pressure based on pumps and tanks
        self._update_fuel_pressure()

        # Calculate fuel flow (match engine demand if available)
        self._calculate_fuel_flow()

        # Consume fuel from selected tanks
        self._consume_fuel(dt)

        # Publish state
        self._publish_state()

    def _publish_state(self) -> None:
        """Publish current fuel state to event bus and message queue."""
        if not self.context:
            return

        # Publish state event
        self.context.event_bus.publish(
            FuelStateEvent(
                left_tank_quantity=self.left_tank_quantity,
                right_tank_quantity=self.right_tank_quantity,
                total_quantity=self._get_total_fuel(),
                fuel_flow=self.fuel_flow,
                fuel_pressure=self.fuel_pressure,
                left_pump_on=self.left_pump_on,
                right_pump_on=self.right_pump_on,
                fuel_selector=self.fuel_selector,
            )
        )

        # Publish message for other plugins
        self.context.message_queue.publish(
            Message(
                sender="simple_fuel_system",
                recipients=["*"],
                topic=MessageTopic.FUEL_STATE,
                data={
                    "total_fuel": self._get_total_fuel(),
                    "fuel_flow": self.fuel_flow,
                    "fuel_pressure": self.fuel_pressure,
                    "fuel_available": self._is_fuel_available(),
                },
                priority=MessagePriority.HIGH,
            )
        )

    def shutdown(self) -> None:
        """Shutdown the fuel system plugin."""
        if self.context:
            # Unsubscribe from messages
            self.context.message_queue.unsubscribe(MessageTopic.ENGINE_STATE, self.handle_message)
            self.context.message_queue.unsubscribe(MessageTopic.FUEL_STATE, self.handle_message)

        # System shutdown - close selector
        self.fuel_selector = "off"
        self.left_pump_on = False
        self.right_pump_on = False
        self.fuel_pressure = 0.0

    def handle_message(self, message: Message) -> None:
        """Handle messages from other plugins.

        Args:
            message: Message from the queue.
        """
        if message.topic == MessageTopic.ENGINE_STATE:
            # Update engine fuel demand
            data = message.data
            if "fuel_flow" in data:
                self._engine_fuel_demand = float(data["fuel_flow"])

        elif message.topic == MessageTopic.FUEL_STATE:
            # Handle fuel control commands
            data = message.data

            if "fuel_selector" in data:
                selector = str(data["fuel_selector"]).lower()
                if selector in ["off", "left", "right", "both"]:
                    self.fuel_selector = selector

            if "left_pump" in data:
                self.left_pump_on = bool(data["left_pump"])

            if "right_pump" in data:
                self.right_pump_on = bool(data["right_pump"])

    def _update_fuel_pressure(self) -> None:
        """Update fuel pressure based on pumps and fuel availability."""
        # Check if fuel is available in selected tanks
        fuel_available = self._is_fuel_available()

        if not fuel_available:
            # No fuel available
            self.fuel_pressure = 0.0
            return

        # Pressure depends on pumps and gravity
        if self.fuel_selector == "off":
            self.fuel_pressure = 0.0
        elif self.left_pump_on or self.right_pump_on:
            # Pump pressure: 4-5 PSI
            self.fuel_pressure = 4.5
        else:
            # Gravity feed only: 2-3 PSI (lower than pump pressure)
            self.fuel_pressure = 2.5

    def _calculate_fuel_flow(self) -> None:
        """Calculate fuel flow rate."""
        if self.fuel_selector == "off" or not self._is_fuel_available():
            self.fuel_flow = 0.0
        else:
            # Flow matches engine demand if fuel available
            self.fuel_flow = self._engine_fuel_demand

    def _consume_fuel(self, dt: float) -> None:
        """Consume fuel from selected tanks.

        Args:
            dt: Delta time in seconds.
        """
        if self.fuel_flow <= 0.0:
            return

        # Convert flow rate to gallons consumed this frame
        gallons_consumed = self.fuel_flow * (dt / 3600.0)

        if self.fuel_selector == "left":
            # Consume from left tank only
            self.left_tank_quantity -= gallons_consumed
            self.left_tank_quantity = max(0.0, self.left_tank_quantity)

        elif self.fuel_selector == "right":
            # Consume from right tank only
            self.right_tank_quantity -= gallons_consumed
            self.right_tank_quantity = max(0.0, self.right_tank_quantity)

        elif self.fuel_selector == "both":
            # Consume equally from both tanks
            left_consumption = gallons_consumed / 2.0
            right_consumption = gallons_consumed / 2.0

            self.left_tank_quantity -= left_consumption
            self.right_tank_quantity -= right_consumption

            self.left_tank_quantity = max(0.0, self.left_tank_quantity)
            self.right_tank_quantity = max(0.0, self.right_tank_quantity)

    def _is_fuel_available(self) -> bool:
        """Check if fuel is available in selected tanks.

        Returns:
            True if usable fuel is available in selected tanks.
        """
        if self.fuel_selector == "off":
            return False

        if self.fuel_selector == "left":
            return self.left_tank_quantity > self.unusable_fuel

        if self.fuel_selector == "right":
            return self.right_tank_quantity > self.unusable_fuel

        if self.fuel_selector == "both":
            # At least one tank must have usable fuel
            left_usable = self.left_tank_quantity > self.unusable_fuel
            right_usable = self.right_tank_quantity > self.unusable_fuel
            return left_usable or right_usable

        return False

    def _get_total_fuel(self) -> float:
        """Get total fuel quantity.

        Returns:
            Total fuel in both tanks (gallons).
        """
        return self.left_tank_quantity + self.right_tank_quantity

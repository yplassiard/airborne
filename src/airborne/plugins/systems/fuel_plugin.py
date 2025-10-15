"""Fuel system plugin wrapper.

Wraps IFuelSystem implementations and integrates with the plugin system.
Handles fuel selector and pump controls, publishes fuel state.

Typical usage:
    Plugin is loaded automatically by plugin loader based on aircraft config.
"""

from typing import Any

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType
from airborne.systems.fuel.base import FuelSelectorPosition, IFuelSystem
from airborne.systems.fuel.simple_gravity import SimpleGravityFuelSystem

logger = get_logger(__name__)


class FuelPlugin(IPlugin):
    """Fuel system plugin.

    Wraps an IFuelSystem implementation and provides plugin integration.
    Receives control messages (selector, pumps) and publishes fuel state.
    Monitors engine fuel consumption and updates tank quantities.

    The specific implementation (Gravity, FuelInjection, etc.) is selected
    via configuration based on aircraft type.
    """

    def __init__(self):
        """Initialize fuel plugin."""
        self.context: PluginContext | None = None
        self.fuel_system: IFuelSystem | None = None
        self.current_fuel_flow_gph = 0.0

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata.

        Returns:
            PluginMetadata describing this fuel plugin.
        """
        return PluginMetadata(
            name="fuel_plugin",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.AIRCRAFT_SYSTEM,
            dependencies=[],
            provides=["fuel_system"],
            optional=False,
            update_priority=25,  # Update after electrical
            requires_physics=False,
            description="Fuel system with tanks, selector, and consumption",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the fuel plugin.

        Args:
            context: Plugin context with access to core systems.
        """
        self.context = context

        # Get fuel config
        fuel_config = context.config.get("fuel", {})
        implementation = fuel_config.get("implementation", "simple_gravity")

        # Create appropriate fuel system implementation
        if implementation == "simple_gravity":
            self.fuel_system = SimpleGravityFuelSystem()
        else:
            logger.warning("Unknown fuel implementation: %s, using simple_gravity", implementation)
            self.fuel_system = SimpleGravityFuelSystem()

        # Initialize fuel system
        self.fuel_system.initialize(fuel_config)

        # Subscribe to control and engine messages - panel-specific topics
        context.message_queue.subscribe("fuel.selector", self.handle_message)
        context.message_queue.subscribe("fuel.shutoff", self.handle_message)
        context.message_queue.subscribe("fuel.pump", self.handle_message)
        context.message_queue.subscribe(MessageTopic.ENGINE_STATE, self.handle_message)

        # Register component
        if context.plugin_registry:
            context.plugin_registry.register("fuel_system", self.fuel_system)

        logger.info("Fuel plugin initialized with %s", implementation)

    def update(self, dt: float) -> None:
        """Update fuel system.

        Args:
            dt: Delta time in seconds since last update.
        """
        if not self.fuel_system or not self.context:
            return

        # Update fuel system with current consumption rate
        self.fuel_system.update(dt, self.current_fuel_flow_gph)

        # Get current state
        state = self.fuel_system.get_state()

        # Publish fuel state for other systems
        self.context.message_queue.publish(
            Message(
                sender="fuel_plugin",
                recipients=["*"],
                topic=MessageTopic.SYSTEM_STATE,
                data={
                    "system": "fuel",
                    "total_quantity_gallons": state.total_quantity_gallons,
                    "total_usable_gallons": state.total_usable_gallons,
                    "total_weight_lbs": state.total_weight_lbs,
                    "fuel_selector_position": state.fuel_selector_position.value,
                    "fuel_flow_rate_gph": state.fuel_flow_rate_gph,
                    "fuel_pressure_psi": state.fuel_pressure_psi,
                    "time_remaining_minutes": state.time_remaining_minutes,
                    "available_fuel_flow_gph": self.fuel_system.get_available_fuel_flow(),
                    "warnings": state.warnings,
                    "failures": state.failures,
                },
                priority=MessagePriority.NORMAL,
            )
        )

        # Publish warnings/failures
        for warning in state.warnings:
            self.context.message_queue.publish(
                Message(
                    sender="fuel_plugin",
                    recipients=["*"],
                    topic=MessageTopic.WARNING,
                    data={"system": "fuel", "warning": warning},
                    priority=MessagePriority.HIGH,
                )
            )

        for failure in state.failures:
            self.context.message_queue.publish(
                Message(
                    sender="fuel_plugin",
                    recipients=["*"],
                    topic=MessageTopic.FAILURE,
                    data={"system": "fuel", "failure": failure},
                    priority=MessagePriority.CRITICAL,
                )
            )

    def shutdown(self) -> None:
        """Shutdown the fuel plugin."""
        if self.context:
            # Unsubscribe from messages
            self.context.message_queue.unsubscribe("fuel.selector", self.handle_message)
            self.context.message_queue.unsubscribe("fuel.shutoff", self.handle_message)
            self.context.message_queue.unsubscribe("fuel.pump", self.handle_message)
            self.context.message_queue.unsubscribe(MessageTopic.ENGINE_STATE, self.handle_message)

            # Unregister component
            if self.context.plugin_registry:
                self.context.plugin_registry.unregister("fuel_system")

        logger.info("Fuel plugin shutdown")

    def handle_message(self, message: Message) -> None:
        """Handle messages from other plugins.

        Args:
            message: Message from the queue.
        """
        if not self.fuel_system:
            return

        if message.topic == MessageTopic.ENGINE_STATE:
            # Update current fuel flow from engine
            data = message.data
            self.current_fuel_flow_gph = data.get("fuel_flow", 0.0)

        elif message.topic == "fuel.selector":
            # Fuel selector valve
            state = message.data.get("state", "OFF")
            try:
                position = FuelSelectorPosition[state.upper()]
                self.fuel_system.set_selector_position(position)
            except (KeyError, AttributeError):
                logger.warning("Invalid fuel selector position: %s", state)

        elif message.topic == "fuel.shutoff":
            # Fuel shutoff valve - set selector to OFF when closed
            state = message.data.get("state", "CLOSED")
            if state == "CLOSED":
                self.fuel_system.set_selector_position(FuelSelectorPosition.OFF)

        elif message.topic == "fuel.pump":
            # Electric fuel pump
            state = message.data.get("state", "OFF")
            enabled = state == "ON"
            # Assume boost pump name based on aircraft config
            self.fuel_system.set_pump_enabled("boost_pump", enabled)

    def on_config_changed(self, config: dict[str, Any]) -> None:
        """Handle configuration changes.

        Args:
            config: New configuration dictionary.
        """
        logger.info("Fuel plugin configuration updated")

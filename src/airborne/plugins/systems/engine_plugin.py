"""Engine system plugin wrapper.

Wraps IEngine implementations and integrates with electrical and fuel systems.

Typical usage:
    Plugin is loaded automatically by plugin loader based on aircraft config.
"""

from typing import Any

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType
from airborne.systems.engines.base import EngineControls, IEngine
from airborne.systems.engines.piston_simple import SimplePistonEngine

logger = get_logger(__name__)


class EnginePlugin(IPlugin):
    """Engine system plugin.

    Wraps an IEngine implementation and provides plugin integration.
    Receives control messages (throttle, mixture, starter, magnetos) and
    monitors electrical and fuel availability. Publishes engine state.

    The specific implementation (SimplePiston, Turboprop, etc.) is selected
    via configuration based on aircraft type.
    """

    def __init__(self) -> None:
        """Initialize engine plugin."""
        self.context: PluginContext | None = None
        self.engine: IEngine | None = None

        # Track dependencies
        self.electrical_available = False
        self.fuel_available_gph = 0.0

        # Current controls
        self.controls = EngineControls(
            throttle=0.0,
            mixture=0.5,
            magneto_left=False,
            magneto_right=False,
            starter=False,
            carburetor_heat=False,
            propeller_rpm=1.0,
            ignition=False,
            fuel_cutoff=False,
            reverse_thrust=False,
        )

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata.

        Returns:
            PluginMetadata describing this engine plugin.
        """
        return PluginMetadata(
            name="engine_plugin",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.AIRCRAFT_SYSTEM,
            dependencies=["electrical_plugin", "fuel_plugin"],
            provides=["engine"],
            optional=False,
            update_priority=35,  # Update after electrical and fuel
            requires_physics=False,
            description="Aircraft engine with realistic startup and operation",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the engine plugin.

        Args:
            context: Plugin context with access to core systems.
        """
        self.context = context

        # Get engine config
        engine_config = context.config.get("engine", {})
        implementation = engine_config.get("implementation", "piston_simple")

        # Create appropriate engine implementation
        if implementation == "piston_simple":
            self.engine = SimplePistonEngine()
        else:
            logger.warning("Unknown engine implementation: %s, using piston_simple", implementation)
            self.engine = SimplePistonEngine()

        # Initialize engine
        self.engine.initialize(engine_config)

        # Subscribe to control and system state messages - panel-specific topics
        context.message_queue.subscribe("engine.mixture", self.handle_message)
        context.message_queue.subscribe("engine.carb_heat", self.handle_message)
        context.message_queue.subscribe("engine.throttle", self.handle_message)
        context.message_queue.subscribe("engine.primer", self.handle_message)
        context.message_queue.subscribe("engine.magnetos", self.handle_message)
        context.message_queue.subscribe("engine.starter", self.handle_message)
        context.message_queue.subscribe(MessageTopic.SYSTEM_STATE, self.handle_message)

        # Register component
        if context.plugin_registry:
            context.plugin_registry.register("engine", self.engine)

        logger.info("Engine plugin initialized with %s", implementation)

    def update(self, dt: float) -> None:
        """Update engine system.

        Args:
            dt: Delta time in seconds since last update.
        """
        if not self.engine or not self.context:
            return

        # Update engine with current controls and dependencies
        self.engine.update(dt, self.controls, self.electrical_available, self.fuel_available_gph)

        # Get current state
        state = self.engine.get_state()

        # Publish engine state for other systems
        self.context.message_queue.publish(
            Message(
                sender="engine_plugin",
                recipients=["*"],
                topic=MessageTopic.ENGINE_STATE,
                data={
                    "running": state.running,
                    "rpm": state.rpm or 0.0,
                    "manifold_pressure": state.manifold_pressure_inhg or 0.0,
                    "fuel_flow": state.fuel_flow_gph,
                    "oil_pressure": state.oil_pressure_psi or 0.0,
                    "oil_temp": state.oil_temperature_c or 0.0,
                    "horsepower": state.power_output_hp,
                },
                priority=MessagePriority.NORMAL,
            )
        )

        # Publish warnings
        if state.warnings:
            for warning in state.warnings:
                if warning:  # Skip empty strings
                    self.context.message_queue.publish(
                        Message(
                            sender="engine_plugin",
                            recipients=["*"],
                            topic=MessageTopic.WARNING,
                            data={"system": "engine", "warning": warning},
                            priority=MessagePriority.HIGH,
                        )
                    )

        # Publish failures
        if state.failures:
            for failure in state.failures:
                self.context.message_queue.publish(
                    Message(
                        sender="engine_plugin",
                        recipients=["*"],
                        topic=MessageTopic.FAILURE,
                        data={"system": "engine", "failure": failure},
                        priority=MessagePriority.CRITICAL,
                    )
                )

    def shutdown(self) -> None:
        """Shutdown the engine plugin."""
        if self.context:
            # Unsubscribe from messages
            self.context.message_queue.unsubscribe("engine.mixture", self.handle_message)
            self.context.message_queue.unsubscribe("engine.carb_heat", self.handle_message)
            self.context.message_queue.unsubscribe("engine.throttle", self.handle_message)
            self.context.message_queue.unsubscribe("engine.primer", self.handle_message)
            self.context.message_queue.unsubscribe("engine.magnetos", self.handle_message)
            self.context.message_queue.unsubscribe("engine.starter", self.handle_message)
            self.context.message_queue.unsubscribe(MessageTopic.SYSTEM_STATE, self.handle_message)

            # Unregister component
            if self.context.plugin_registry:
                self.context.plugin_registry.unregister("engine")

        logger.info("Engine plugin shutdown")

    def handle_message(self, message: Message) -> None:
        """Handle messages from other plugins.

        Args:
            message: Message from the queue.
        """
        if not self.engine:
            return

        if message.topic == MessageTopic.SYSTEM_STATE:
            # Monitor electrical and fuel systems
            data = message.data
            system = data.get("system")

            if system == "electrical":
                # Check if we have enough voltage for starter
                bus_voltage = data.get("bus_voltage", 0.0)
                self.electrical_available = bus_voltage >= 11.0  # Starter needs 11.0V minimum

            elif system == "fuel":
                # Get available fuel flow
                self.fuel_available_gph = data.get("available_fuel_flow_gph", 0.0)

        elif message.topic == "engine.throttle":
            # Throttle lever (0-100%)
            value = message.data.get("value", 0.0)
            self.controls.throttle = value / 100.0  # Normalize to 0.0-1.0

        elif message.topic == "engine.mixture":
            # Mixture lever: IDLE_CUTOFF, LEAN, RICH
            state = message.data.get("state", "IDLE_CUTOFF")
            if state == "IDLE_CUTOFF":
                self.controls.mixture = 0.0
            elif state == "LEAN":
                self.controls.mixture = 0.5
            elif state == "RICH":
                self.controls.mixture = 1.0

        elif message.topic == "engine.carb_heat":
            # Carburetor heat: COLD, HOT
            state = message.data.get("state", "COLD")
            self.controls.carburetor_heat = state == "HOT"

        elif message.topic == "engine.magnetos":
            # Magneto switch: OFF, R, L, BOTH, START
            state = message.data.get("state", "OFF")
            if state == "OFF":
                self.controls.magneto_left = False
                self.controls.magneto_right = False
                self.controls.starter = False
            elif state == "R":
                self.controls.magneto_left = False
                self.controls.magneto_right = True
                self.controls.starter = False
            elif state == "L":
                self.controls.magneto_left = True
                self.controls.magneto_right = False
                self.controls.starter = False
            elif state == "BOTH":
                self.controls.magneto_left = True
                self.controls.magneto_right = True
                self.controls.starter = False
            elif state == "START":
                self.controls.magneto_left = True
                self.controls.magneto_right = True
                self.controls.starter = True

        elif message.topic == "engine.starter":
            # Starter button (momentary)
            action = message.data.get("action")
            if action == "pressed":
                # Momentary starter engagement
                self.controls.starter = True

        elif message.topic == "engine.primer":
            # Primer pump (momentary) - not directly modeled in simple engine
            # In real aircraft, this enriches mixture for cold starts
            pass

    def on_config_changed(self, config: dict[str, Any]) -> None:
        """Handle configuration changes.

        Args:
            config: New configuration dictionary.
        """
        logger.info("Engine plugin configuration updated")

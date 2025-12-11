"""Rotax engine system plugin.

Wraps the RotaxEngine implementation for use with ULM/LSA aircraft.
"""

from typing import Any

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType
from airborne.systems.engines.base import EngineControls
from airborne.systems.engines.rotax import RotaxEngine

logger = get_logger(__name__)


class RotaxEnginePlugin(IPlugin):
    """Rotax engine system plugin.

    Integrates Rotax 912/914/582 engines with the plugin system.
    Handles the unique characteristics of Rotax engines:
    - Reduction gearbox (publishes both engine and prop RPM)
    - Dual electronic ignition
    - Liquid cooling temperature monitoring
    """

    def __init__(self) -> None:
        """Initialize Rotax engine plugin."""
        self.context: PluginContext | None = None
        self.engine: RotaxEngine | None = None

        # Dependencies
        self.electrical_available = False
        self.fuel_available_gph = 0.0

        # Controls
        self.controls = EngineControls(
            throttle=0.0,
            mixture=1.0,  # Rotax runs best full rich
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
        """Return plugin metadata."""
        return PluginMetadata(
            name="rotax_engine_plugin",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.AIRCRAFT_SYSTEM,
            dependencies=["electrical_plugin", "fuel_plugin"],
            provides=["engine", "rotax_engine"],
            optional=False,
            update_priority=35,
            requires_physics=False,
            description="Rotax aircraft engine for ULM/LSA",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the Rotax engine plugin.

        Args:
            context: Plugin context.
        """
        self.context = context

        # Get engine config
        engine_config = context.config.get("engine", {})

        # Create engine
        self.engine = RotaxEngine()
        self.engine.initialize(engine_config)

        # Subscribe to messages
        context.message_queue.subscribe("engine.mixture", self.handle_message)
        context.message_queue.subscribe("engine.throttle", self.handle_message)
        context.message_queue.subscribe("engine.magnetos", self.handle_message)
        context.message_queue.subscribe("engine.starter", self.handle_message)
        context.message_queue.subscribe(MessageTopic.SYSTEM_STATE, self.handle_message)

        # Register
        if context.plugin_registry:
            context.plugin_registry.register("engine", self.engine)
            context.plugin_registry.register("rotax_engine", self.engine)

        logger.info("Rotax engine plugin initialized")

    def update(self, dt: float) -> None:
        """Update engine system.

        Args:
            dt: Delta time in seconds.
        """
        if not self.engine or not self.context:
            return

        # Update engine
        self.engine.update(dt, self.controls, self.electrical_available, self.fuel_available_gph)

        # Get state
        state = self.engine.get_state()

        # Publish engine state with Rotax-specific data
        self.context.message_queue.publish(
            Message(
                sender="rotax_engine_plugin",
                recipients=["*"],
                topic=MessageTopic.ENGINE_STATE,
                data={
                    "running": state.running,
                    "rpm": state.rpm or 0.0,  # Engine RPM
                    "prop_rpm": self.engine.get_prop_rpm(),  # Prop RPM (after gearbox)
                    "fuel_flow": state.fuel_flow_gph,
                    "oil_pressure": state.oil_pressure_psi or 0.0,
                    "oil_temp": state.oil_temperature_c or 0.0,
                    "coolant_temp": state.temperature_c,  # Coolant temp
                    "horsepower": state.power_output_hp,
                    "engine_type": "rotax",
                },
                priority=MessagePriority.NORMAL,
            )
        )

        # Publish warnings
        if state.warnings:
            for warning in state.warnings:
                if warning:
                    self.context.message_queue.publish(
                        Message(
                            sender="rotax_engine_plugin",
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
                        sender="rotax_engine_plugin",
                        recipients=["*"],
                        topic=MessageTopic.FAILURE,
                        data={"system": "engine", "failure": failure},
                        priority=MessagePriority.CRITICAL,
                    )
                )

    def shutdown(self) -> None:
        """Shutdown plugin."""
        if self.context:
            self.context.message_queue.unsubscribe("engine.mixture", self.handle_message)
            self.context.message_queue.unsubscribe("engine.throttle", self.handle_message)
            self.context.message_queue.unsubscribe("engine.magnetos", self.handle_message)
            self.context.message_queue.unsubscribe("engine.starter", self.handle_message)
            self.context.message_queue.unsubscribe(MessageTopic.SYSTEM_STATE, self.handle_message)

            if self.context.plugin_registry:
                self.context.plugin_registry.unregister("engine")
                self.context.plugin_registry.unregister("rotax_engine")

        logger.info("Rotax engine plugin shutdown")

    def handle_message(self, message: Message) -> None:
        """Handle messages.

        Args:
            message: Incoming message.
        """
        if not self.engine:
            return

        if message.topic == MessageTopic.SYSTEM_STATE:
            data = message.data
            system = data.get("system")

            if system == "electrical":
                bus_voltage = data.get("bus_voltage", 0.0)
                self.electrical_available = bus_voltage >= 11.5  # Rotax needs slightly higher

            elif system == "fuel":
                self.fuel_available_gph = data.get("available_fuel_flow_gph", 0.0)

        elif message.topic == "engine.throttle":
            value = message.data.get("value", 0.0)
            self.controls.throttle = value / 100.0

        elif message.topic == "engine.mixture":
            state = message.data.get("state", "RICH")
            # Rotax typically runs full rich
            if state == "IDLE_CUTOFF":
                self.controls.mixture = 0.0
            elif state == "LEAN":
                self.controls.mixture = 0.7
            elif state == "RICH":
                self.controls.mixture = 1.0

        elif message.topic == "engine.magnetos":
            # On Rotax, these control dual ignition systems
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
            action = message.data.get("action")
            if action == "pressed":
                self.controls.starter = True

    def on_config_changed(self, config: dict[str, Any]) -> None:
        """Handle configuration changes.

        Args:
            config: New configuration.
        """
        logger.info("Rotax engine plugin configuration updated")

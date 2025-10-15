"""Electrical system plugin wrapper.

Wraps IElectricalSystem implementations and integrates with the plugin system.
Handles messages from control panels and publishes electrical state.

Typical usage:
    Plugin is loaded automatically by plugin loader based on aircraft config.
"""

from typing import Any

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType
from airborne.systems.electrical.base import IElectricalSystem
from airborne.systems.electrical.simple_12v import Simple12VElectricalSystem

logger = get_logger(__name__)


class ElectricalPlugin(IPlugin):
    """Electrical system plugin.

    Wraps an IElectricalSystem implementation and provides plugin integration.
    Receives control messages (switch states) and publishes electrical state.

    The specific implementation (Simple12V, Dual28V, etc.) is selected via
    configuration based on aircraft type.
    """

    def __init__(self):
        """Initialize electrical plugin."""
        self.context: PluginContext | None = None
        self.electrical_system: IElectricalSystem | None = None
        self.engine_rpm = 0.0

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata.

        Returns:
            PluginMetadata describing this electrical plugin.
        """
        return PluginMetadata(
            name="electrical_plugin",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.AIRCRAFT_SYSTEM,
            dependencies=[],
            provides=["electrical_system"],
            optional=False,
            update_priority=20,  # Update after physics but before other systems
            requires_physics=False,
            description="Electrical system with battery, alternator, and buses",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the electrical plugin.

        Args:
            context: Plugin context with access to core systems.
        """
        self.context = context

        # Get electrical config
        electrical_config = context.config.get("electrical", {})
        implementation = electrical_config.get("implementation", "simple_12v")

        # Create appropriate electrical system implementation
        if implementation == "simple_12v":
            self.electrical_system = Simple12VElectricalSystem()
        else:
            logger.warning(
                "Unknown electrical implementation: %s, using simple_12v", implementation
            )
            self.electrical_system = Simple12VElectricalSystem()

        # Initialize electrical system
        self.electrical_system.initialize(electrical_config)

        # Subscribe to control messages - panel-specific topics
        context.message_queue.subscribe("electrical.master_switch", self.handle_message)
        context.message_queue.subscribe("electrical.avionics_master", self.handle_message)
        context.message_queue.subscribe("electrical.beacon", self.handle_message)
        context.message_queue.subscribe("electrical.nav_lights", self.handle_message)
        context.message_queue.subscribe("electrical.strobe", self.handle_message)
        context.message_queue.subscribe("electrical.taxi_light", self.handle_message)
        context.message_queue.subscribe("electrical.landing_light", self.handle_message)
        context.message_queue.subscribe("electrical.pitot_heat", self.handle_message)

        # Subscribe to engine state for alternator
        context.message_queue.subscribe(MessageTopic.ENGINE_STATE, self.handle_message)

        # Register component
        if context.plugin_registry:
            context.plugin_registry.register("electrical_system", self.electrical_system)

        logger.info("Electrical plugin initialized with %s", implementation)

    def update(self, dt: float) -> None:
        """Update electrical system.

        Args:
            dt: Delta time in seconds since last update.
        """
        if not self.electrical_system or not self.context:
            return

        # Update electrical system with engine RPM
        self.electrical_system.update(dt, self.engine_rpm)

        # Get current state
        state = self.electrical_system.get_state()

        # Publish electrical state for other systems
        self.context.message_queue.publish(
            Message(
                sender="electrical_plugin",
                recipients=["*"],
                topic=MessageTopic.SYSTEM_STATE,
                data={
                    "system": "electrical",
                    "battery_voltage": state.battery_voltage,
                    "battery_soc_percent": state.battery_soc_percent,
                    "battery_current_amps": state.battery_current_amps,
                    "alternator_output_amps": state.alternator_output_amps,
                    "total_load_amps": state.total_load_amps,
                    "bus_voltage": state.buses["main_bus"].voltage_current
                    if "main_bus" in state.buses
                    else 0.0,
                    "warnings": state.warnings,
                    "failures": state.failures,
                },
                priority=MessagePriority.NORMAL,
            )
        )

        # Publish warnings/failures as separate messages
        for warning in state.warnings:
            self.context.message_queue.publish(
                Message(
                    sender="electrical_plugin",
                    recipients=["*"],
                    topic=MessageTopic.WARNING,
                    data={"system": "electrical", "warning": warning},
                    priority=MessagePriority.HIGH,
                )
            )

        for failure in state.failures:
            self.context.message_queue.publish(
                Message(
                    sender="electrical_plugin",
                    recipients=["*"],
                    topic=MessageTopic.FAILURE,
                    data={"system": "electrical", "failure": failure},
                    priority=MessagePriority.CRITICAL,
                )
            )

    def shutdown(self) -> None:
        """Shutdown the electrical plugin."""
        if self.context:
            # Unsubscribe from messages
            self.context.message_queue.unsubscribe("electrical.master_switch", self.handle_message)
            self.context.message_queue.unsubscribe(
                "electrical.avionics_master", self.handle_message
            )
            self.context.message_queue.unsubscribe("electrical.beacon", self.handle_message)
            self.context.message_queue.unsubscribe("electrical.nav_lights", self.handle_message)
            self.context.message_queue.unsubscribe("electrical.strobe", self.handle_message)
            self.context.message_queue.unsubscribe("electrical.taxi_light", self.handle_message)
            self.context.message_queue.unsubscribe("electrical.landing_light", self.handle_message)
            self.context.message_queue.unsubscribe("electrical.pitot_heat", self.handle_message)
            self.context.message_queue.unsubscribe(MessageTopic.ENGINE_STATE, self.handle_message)

            # Unregister component
            if self.context.plugin_registry:
                self.context.plugin_registry.unregister("electrical_system")

        logger.info("Electrical plugin shutdown")

    def handle_message(self, message: Message) -> None:
        """Handle messages from other plugins.

        Args:
            message: Message from the queue.
        """
        if not self.electrical_system:
            return

        if message.topic == MessageTopic.ENGINE_STATE:
            # Update engine RPM for alternator
            data = message.data
            self.engine_rpm = data.get("rpm", 0.0)

        elif message.topic == "electrical.master_switch":
            # Master switch control
            state = message.data.get("state", "OFF")
            enabled = state == "ON"
            if hasattr(self.electrical_system, "set_master_switch"):
                self.electrical_system.set_master_switch(enabled)

        elif message.topic in [
            "electrical.avionics_master",
            "electrical.beacon",
            "electrical.nav_lights",
            "electrical.strobe",
            "electrical.taxi_light",
            "electrical.landing_light",
            "electrical.pitot_heat",
        ]:
            # Map topic to load name
            topic_to_load = {
                "electrical.avionics_master": "avionics",
                "electrical.beacon": "beacon",
                "electrical.nav_lights": "nav_lights",
                "electrical.strobe": "strobe",
                "electrical.taxi_light": "taxi_light",
                "electrical.landing_light": "landing_light",
                "electrical.pitot_heat": "pitot_heat",
            }
            load_name = topic_to_load.get(message.topic)
            if load_name:
                state = message.data.get("state", "OFF")
                enabled = state == "ON"
                self.electrical_system.set_load_enabled(load_name, enabled)

    def on_config_changed(self, config: dict[str, Any]) -> None:
        """Handle configuration changes.

        Args:
            config: New configuration dictionary.
        """
        # Could reinitialize electrical system with new config if needed
        logger.info("Electrical plugin configuration updated")

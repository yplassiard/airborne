"""Lighting system plugin wrapper.

Wraps lighting system and integrates with electrical and control systems.

Typical usage:
    Plugin is loaded automatically by plugin loader based on aircraft config.
"""

from typing import Any

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType
from airborne.systems.lighting.standard import StandardLightingSystem

logger = get_logger(__name__)


class LightingPlugin(IPlugin):
    """Lighting system plugin.

    Manages aircraft exterior lights with voltage-dependent brightness.
    Receives control messages (light switches) and monitors bus voltage.
    """

    def __init__(self):
        """Initialize lighting plugin."""
        self.context: PluginContext | None = None
        self.lighting_system = StandardLightingSystem()
        self.bus_voltage = 0.0

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata.

        Returns:
            PluginMetadata describing this lighting plugin.
        """
        return PluginMetadata(
            name="lighting_plugin",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.AIRCRAFT_SYSTEM,
            dependencies=["electrical_plugin"],
            provides=["lighting_system"],
            optional=False,
            update_priority=30,  # Update after electrical
            requires_physics=False,
            description="Aircraft lighting system with voltage-dependent brightness",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the lighting plugin.

        Args:
            context: Plugin context with access to core systems.
        """
        self.context = context

        # Get lighting config
        lighting_config = context.config.get("lighting", {})

        # Initialize lighting system
        self.lighting_system.initialize(lighting_config)

        # Subscribe to control and electrical messages
        context.message_queue.subscribe(MessageTopic.CONTROL_INPUT, self.handle_message)
        context.message_queue.subscribe(MessageTopic.SYSTEM_STATE, self.handle_message)

        # Register component
        if context.plugin_registry:
            context.plugin_registry.register("lighting_system", self.lighting_system)

        logger.info("Lighting plugin initialized")

    def update(self, dt: float) -> None:
        """Update lighting system.

        Args:
            dt: Delta time in seconds since last update.
        """
        if not self.context:
            return

        # Update lighting system with current bus voltage
        self.lighting_system.update(dt, self.bus_voltage)

        # Publish lighting state
        all_states = self.lighting_system.get_all_states()
        self.context.message_queue.publish(
            Message(
                sender="lighting_plugin",
                recipients=["*"],
                topic=MessageTopic.SYSTEM_STATE,
                data={
                    "system": "lighting",
                    "lights": {
                        name: {
                            "enabled": state.enabled,
                            "brightness": state.brightness,
                            "power_draw_amps": state.power_draw_amps if state.enabled else 0.0,
                        }
                        for name, state in all_states.items()
                    },
                    "total_power_draw": self.lighting_system.get_total_power_draw(),
                },
                priority=MessagePriority.LOW,
            )
        )

    def shutdown(self) -> None:
        """Shutdown the lighting plugin."""
        if self.context:
            # Unsubscribe from messages
            self.context.message_queue.unsubscribe(MessageTopic.CONTROL_INPUT, self.handle_message)
            self.context.message_queue.unsubscribe(MessageTopic.SYSTEM_STATE, self.handle_message)

            # Unregister component
            if self.context.plugin_registry:
                self.context.plugin_registry.unregister("lighting_system")

        logger.info("Lighting plugin shutdown")

    def handle_message(self, message: Message) -> None:
        """Handle messages from other plugins.

        Args:
            message: Message from the queue.
        """
        if message.topic == MessageTopic.SYSTEM_STATE:
            # Monitor electrical system for bus voltage
            data = message.data
            if data.get("system") == "electrical":
                self.bus_voltage = data.get("bus_voltage", 0.0)

        elif message.topic == MessageTopic.CONTROL_INPUT:
            # Handle lighting control inputs
            data = message.data
            control_type = data.get("control_type")

            if control_type == "lighting":
                light_name = data.get("light_name")
                if light_name:
                    enabled = bool(data.get("enabled", False))
                    self.lighting_system.set_light_enabled(light_name, enabled)

    def on_config_changed(self, config: dict[str, Any]) -> None:
        """Handle configuration changes.

        Args:
            config: New configuration dictionary.
        """
        logger.info("Lighting plugin configuration updated")

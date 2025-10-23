"""Weight and balance plugin.

This plugin manages dynamic weight calculation and publishes weight updates
to the physics system. Weight changes with fuel consumption, passenger loading, etc.
"""

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType
from airborne.systems.weight_balance import WeightBalanceSystem

logger = get_logger(__name__)


class WeightBalancePlugin(IPlugin):
    """Plugin for dynamic weight and balance management.

    Responsibilities:
    - Track all weight stations (fuel, passengers, cargo)
    - Calculate total weight and CG position
    - Publish weight updates to physics system
    - Subscribe to fuel state changes
    - Provide W&B status to other systems

    The plugin provides:
    - weight_balance_system: WeightBalanceSystem instance
    """

    def __init__(self) -> None:
        """Initialize weight and balance plugin."""
        self.context: PluginContext | None = None
        self.wb_system: WeightBalanceSystem | None = None

        # Tracking variables
        self._last_published_weight = 0.0
        self._last_published_cg = 0.0
        self._update_interval = 1.0  # Publish updates every 1 second
        self._time_since_update = 0.0

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata.

        Returns:
            PluginMetadata describing this W&B plugin.
        """
        return PluginMetadata(
            name="weight_balance_plugin",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.AIRCRAFT_SYSTEM,
            dependencies=[],
            provides=["weight_balance_system"],
            optional=False,
            update_priority=40,  # Update after fuel system (30)
            requires_physics=False,
            description="Dynamic weight and balance calculation",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the weight and balance plugin.

        Args:
            context: Plugin context with access to core systems.
        """
        self.context = context

        # Get weight & balance config from aircraft config
        aircraft_config = context.config.get("aircraft", {})
        wb_config = aircraft_config.get("weight_balance", {})

        if not wb_config:
            logger.warning("No weight_balance config found, using defaults")
            # Create minimal default config
            wb_config = {
                "empty_weight": 1600.0,
                "empty_moment": 136000.0,
                "max_gross_weight": 2550.0,
                "cg_limits": {"forward": 82.9, "aft": 95.5},
                "stations": {},
            }

        # Create weight & balance system
        self.wb_system = WeightBalanceSystem(wb_config)

        # Register system in registry
        if context.plugin_registry:
            context.plugin_registry.register("weight_balance_system", self.wb_system)

        # Subscribe to fuel state updates
        context.message_queue.subscribe(MessageTopic.FUEL_STATE, self.handle_message)

        # Publish initial weight
        self._publish_weight_update()

        logger.info("Weight & balance plugin initialized")

    def update(self, dt: float) -> None:
        """Update weight and balance calculations.

        Args:
            dt: Delta time in seconds since last update.
        """
        if not self.wb_system or not self.context:
            return

        self._time_since_update += dt

        # Publish updates periodically (every 1 second)
        if self._time_since_update >= self._update_interval:
            self._publish_weight_update()
            self._time_since_update = 0.0

    def shutdown(self) -> None:
        """Shutdown the weight and balance plugin."""
        if self.context:
            # Unsubscribe from messages
            self.context.message_queue.unsubscribe(MessageTopic.FUEL_STATE, self.handle_message)

            # Unregister system
            if self.context.plugin_registry:
                self.context.plugin_registry.unregister("weight_balance_system")

        logger.info("Weight & balance plugin shutdown")

    def handle_message(self, message: Message) -> None:
        """Handle messages from other plugins.

        Args:
            message: Message from the queue.
        """
        if message.topic == MessageTopic.FUEL_STATE:
            # Update fuel weight when fuel state changes
            self._update_fuel_weight(message.data)

    def _update_fuel_weight(self, fuel_data: dict) -> None:
        """Update fuel station weights from fuel system data.

        Args:
            fuel_data: Fuel state data with tank quantities.
        """
        if not self.wb_system:
            return

        # Fuel weight calculation: gallons × lbs/gallon
        lbs_per_gallon = 6.0  # Avgas 100LL

        # Update fuel stations based on tank data
        # Map tank names to station names
        tank_to_station = {
            "left_tank": "fuel_left",
            "right_tank": "fuel_right",
            "main_tank": "fuel_main",
        }

        for tank_name, station_name in tank_to_station.items():
            if tank_name in fuel_data:
                gallons = float(fuel_data[tank_name])
                weight_lbs = gallons * lbs_per_gallon
                self.wb_system.update_station_weight(station_name, weight_lbs)

        # Also handle single "fuel_quantity_total" if present
        if "fuel_quantity_total" in fuel_data:
            total_gallons = float(fuel_data["fuel_quantity_total"])
            total_weight = total_gallons * lbs_per_gallon

            # If we have a single main fuel station, update it
            if "fuel_main" in self.wb_system.stations:
                self.wb_system.update_station_weight("fuel_main", total_weight)

    def _publish_weight_update(self) -> None:
        """Publish weight update to physics system."""
        if not self.wb_system or not self.context:
            return

        total_weight = self.wb_system.calculate_total_weight()
        cg = self.wb_system.calculate_cg()
        within_limits, status_msg = self.wb_system.is_within_limits()

        # Only publish if weight changed significantly (>1 lb)
        if abs(total_weight - self._last_published_weight) < 1.0:
            return

        # Publish weight update message
        self.context.message_queue.publish(
            Message(
                sender="weight_balance_plugin",
                recipients=["*"],
                topic="weight_balance.updated",
                data={
                    "total_weight_lbs": total_weight,
                    "cg_position_in": cg,
                    "within_limits": within_limits,
                    "status": status_msg,
                    "breakdown": self.wb_system.get_weight_breakdown(),
                },
                priority=MessagePriority.NORMAL,
            )
        )

        self._last_published_weight = total_weight
        self._last_published_cg = cg

        logger.debug(f'Weight update: {total_weight:.0f} lbs, CG={cg:.1f}", {status_msg}')

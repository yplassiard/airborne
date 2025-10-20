"""Weight and Balance Plugin for AirBorne flight simulator.

Tracks aircraft weight and center of gravity (CG), updating performance
characteristics based on fuel, passengers, and cargo loading.

Typical usage:
    The weight and balance plugin is loaded automatically and integrates
    with ground services to track weight changes during refueling and boarding.
"""

import logging
from dataclasses import dataclass

from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType

logger = logging.getLogger(__name__)


@dataclass
class WeightStation:
    """Represents a weight station (fuel tank, passenger seat, cargo bay).

    Attributes:
        name: Station identifier (e.g., "main_tank", "pilot", "cargo").
        weight: Current weight in pounds.
        arm: Distance from reference datum in inches.
        max_weight: Maximum allowable weight for this station.
    """

    name: str
    weight: float
    arm: float
    max_weight: float


class WeightBalancePlugin(IPlugin):
    """Weight and balance plugin for aircraft weight and CG tracking.

    Monitors aircraft loading (fuel, passengers, cargo) and calculates:
    - Total weight
    - Center of gravity (CG)
    - Performance adjustments (takeoff speed, climb rate, fuel flow)

    Components provided:
    - weight_balance_manager: WeightBalanceManager instance for weight tracking
    """

    def __init__(self) -> None:
        """Initialize weight and balance plugin."""
        self.context: PluginContext | None = None
        self.empty_weight: float = 0.0  # Empty aircraft weight (lbs)
        self.empty_moment: float = 0.0  # Empty aircraft moment (lb-in)
        self.stations: dict[str, WeightStation] = {}
        self.total_weight: float = 0.0
        self.total_moment: float = 0.0
        self.cg_position: float = 0.0  # CG in inches from datum
        self.max_gross_weight: float = 0.0

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return PluginMetadata(
            name="weight_balance_plugin",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.AIRCRAFT_SYSTEM,
            dependencies=[],
            provides=["weight_balance"],
            optional=False,
            update_priority=40,  # After fuel/systems, before physics
            requires_physics=False,
            description="Aircraft weight and balance tracking with performance updates",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the weight and balance plugin."""
        self.context = context

        # Load aircraft weight configuration
        aircraft_config = context.config.get("aircraft", {})
        weight_config = aircraft_config.get("weight_balance", {})

        self.empty_weight = weight_config.get("empty_weight", 1500.0)
        self.empty_moment = weight_config.get("empty_moment", 135000.0)
        self.max_gross_weight = weight_config.get("max_gross_weight", 2550.0)

        # Initialize weight stations
        self._initialize_stations(weight_config)

        # Calculate initial weight and CG
        self._recalculate()

        # Subscribe to messages
        context.message_queue.subscribe("fuel.state", self.handle_message)
        context.message_queue.subscribe("fuel.add", self.handle_message)
        context.message_queue.subscribe("ground.service.complete", self.handle_message)
        context.message_queue.subscribe("cabin.boarding.progress", self.handle_message)

        # Register in component registry
        if context.plugin_registry:
            context.plugin_registry.register("weight_balance_manager", self)

        logger.info(
            "Weight and balance initialized: empty=%.1f lbs, CG=%.1f in, max gross=%.1f lbs",
            self.empty_weight,
            self.cg_position,
            self.max_gross_weight,
        )

    def _initialize_stations(self, weight_config: dict) -> None:
        """Initialize weight stations from configuration.

        Args:
            weight_config: Weight configuration from aircraft YAML.
        """
        stations_config = weight_config.get("stations", {})

        # Fuel tanks
        fuel_tanks = stations_config.get("fuel_tanks", [])
        for tank in fuel_tanks:
            self.stations[tank["name"]] = WeightStation(
                name=tank["name"],
                weight=tank.get("initial_weight", 0.0),
                arm=tank["arm"],
                max_weight=tank["max_weight"],
            )

        # Passenger seats
        seats = stations_config.get("seats", [])
        for seat in seats:
            self.stations[seat["name"]] = WeightStation(
                name=seat["name"],
                weight=seat.get("initial_weight", 0.0),
                arm=seat["arm"],
                max_weight=seat["max_weight"],
            )

        # Cargo bays
        cargo_bays = stations_config.get("cargo", [])
        for bay in cargo_bays:
            self.stations[bay["name"]] = WeightStation(
                name=bay["name"],
                weight=bay.get("initial_weight", 0.0),
                arm=bay["arm"],
                max_weight=bay["max_weight"],
            )

        logger.info("Initialized %d weight stations", len(self.stations))

    def update(self, dt: float) -> None:
        """Update weight and balance (no continuous updates needed).

        Args:
            dt: Time delta since last update (seconds).
        """
        # Weight and balance calculations are event-driven, not time-based
        pass

    def shutdown(self) -> None:
        """Shutdown the weight and balance plugin."""
        if self.context:
            # Unsubscribe from messages
            self.context.message_queue.unsubscribe("fuel.state", self.handle_message)
            self.context.message_queue.unsubscribe("fuel.add", self.handle_message)
            self.context.message_queue.unsubscribe("ground.service.complete", self.handle_message)
            self.context.message_queue.unsubscribe("cabin.boarding.progress", self.handle_message)

            # Unregister components
            if self.context.plugin_registry:
                self.context.plugin_registry.unregister("weight_balance_manager")

        logger.info("Weight and balance plugin shutdown")

    def handle_message(self, message: Message) -> None:
        """Handle messages from other plugins.

        Args:
            message: Message to process.
        """
        if not self.context:
            return

        if message.topic == "fuel.state" or message.topic == "fuel.add":
            # Update fuel weight
            self._handle_fuel_update(message)

        elif message.topic == "ground.service.complete":
            # Handle completed ground service (boarding, cargo loading)
            self._handle_service_complete(message)

        elif message.topic == MessageTopic.BOARDING_PROGRESS:
            # Update passenger weight during boarding
            self._handle_boarding_progress(message)

    def _handle_fuel_update(self, message: Message) -> None:
        """Handle fuel quantity update.

        Args:
            message: Fuel update message.
        """
        fuel_quantity_gal = message.data.get("quantity", 0.0)
        # Avgas weighs approximately 6 lbs/gallon
        fuel_weight_lbs = fuel_quantity_gal * 6.0

        # Update main fuel tank (simplified - could track multiple tanks)
        if "main_tank" in self.stations:
            old_weight = self.stations["main_tank"].weight
            self.stations["main_tank"].weight = fuel_weight_lbs

            logger.debug("Fuel weight updated: %.1f lbs → %.1f lbs", old_weight, fuel_weight_lbs)

            # Recalculate weight and CG
            self._recalculate()

            # Publish performance update
            self._publish_performance_update()

    def _handle_service_complete(self, message: Message) -> None:
        """Handle ground service completion (boarding, cargo).

        Args:
            message: Service completion message.
        """
        service_type = message.data.get("service_type", "")

        if service_type == "boarding":
            # Update passenger weight (assume 170 lbs per passenger + 30 lbs baggage)
            passengers = message.data.get("passengers", 0)
            total_passenger_weight = passengers * 200.0  # 170 + 30 lbs

            # Distribute weight across passenger stations
            self._distribute_passenger_weight(total_passenger_weight, passengers)

        elif service_type == "cargo":
            # Update cargo weight
            cargo_weight = message.data.get("cargo_weight", 0.0)
            if "cargo_bay" in self.stations:
                self.stations["cargo_bay"].weight = cargo_weight

        # Recalculate weight and CG
        self._recalculate()

        # Publish performance update
        self._publish_performance_update()

    def _handle_boarding_progress(self, message: Message) -> None:
        """Handle boarding progress updates.

        Args:
            message: Boarding progress message.
        """
        passengers_boarded = message.data.get("passengers_boarded", 0)
        total_passenger_weight = passengers_boarded * 200.0

        # Distribute weight across passenger stations
        self._distribute_passenger_weight(total_passenger_weight, passengers_boarded)

        # Recalculate weight and CG
        self._recalculate()

    def _distribute_passenger_weight(self, total_weight: float, passenger_count: int) -> None:
        """Distribute passenger weight across seat stations.

        Args:
            total_weight: Total passenger + baggage weight (lbs).
            passenger_count: Number of passengers.
        """
        # Find all passenger seat stations
        seat_stations = [s for name, s in self.stations.items() if name.startswith("seat_")]

        if not seat_stations:
            logger.warning("No seat stations found for passenger weight distribution")
            return

        # Distribute evenly across occupied seats only
        weight_per_passenger = total_weight / passenger_count if passenger_count > 0 else 0.0

        for i, seat in enumerate(seat_stations):
            if i < passenger_count:
                seat.weight = weight_per_passenger
            else:
                seat.weight = 0.0

    def _recalculate(self) -> None:
        """Recalculate total weight, moment, and CG position."""
        # Start with empty aircraft
        total_weight = self.empty_weight
        total_moment = self.empty_moment

        # Add all loaded stations
        for station in self.stations.values():
            total_weight += station.weight
            total_moment += station.weight * station.arm

        # Calculate CG
        self.total_weight = total_weight
        self.total_moment = total_moment
        self.cg_position = total_moment / total_weight if total_weight > 0 else 0.0

        logger.debug(
            "Weight recalculated: total=%.1f lbs, CG=%.1f in, moment=%.1f lb-in",
            self.total_weight,
            self.cg_position,
            self.total_moment,
        )

        # Check weight limits
        if self.total_weight > self.max_gross_weight:
            logger.warning(
                "Aircraft overweight: %.1f lbs (max %.1f lbs)",
                self.total_weight,
                self.max_gross_weight,
            )

    def _publish_performance_update(self) -> None:
        """Publish performance update based on current weight."""
        if not self.context:
            return

        # Calculate performance factors
        # Use standard loaded weight (empty + pilot + full fuel) as reference
        standard_weight = self.empty_weight + 200.0 + (52.0 * 6.0)  # ~2112 lbs for C172
        weight_ratio = self.total_weight / standard_weight if standard_weight > 0 else 1.0

        # Heavier aircraft need:
        # - Higher takeoff speed (Vr increases with sqrt(weight))
        # - Lower climb rate (less excess power)
        # - Higher fuel consumption (more power needed)
        vr_factor = weight_ratio**0.5  # Square root relationship
        climb_rate_factor = 2.0 - weight_ratio  # Linear decrease
        fuel_flow_factor = weight_ratio  # Linear increase

        self.context.message_queue.publish(
            Message(
                sender="weight_balance_plugin",
                recipients=["*"],
                topic="aircraft.performance.update",
                data={
                    "total_weight": self.total_weight,
                    "cg_position": self.cg_position,
                    "weight_ratio": weight_ratio,
                    "vr_factor": vr_factor,
                    "climb_rate_factor": climb_rate_factor,
                    "fuel_flow_factor": fuel_flow_factor,
                    "overweight": self.total_weight > self.max_gross_weight,
                },
                priority=MessagePriority.NORMAL,
            )
        )

        logger.info(
            "Performance updated: weight=%.1f lbs, Vr factor=%.2f, climb factor=%.2f",
            self.total_weight,
            vr_factor,
            climb_rate_factor,
        )

    def get_total_weight(self) -> float:
        """Get current total aircraft weight.

        Returns:
            Total weight in pounds.
        """
        return self.total_weight

    def get_cg_position(self) -> float:
        """Get current center of gravity position.

        Returns:
            CG position in inches from datum.
        """
        return self.cg_position

    def is_within_limits(self) -> bool:
        """Check if aircraft is within weight and balance limits.

        Returns:
            True if within limits, False otherwise.
        """
        # Check weight limit
        if self.total_weight > self.max_gross_weight:
            return False

        # TODO: Check CG limits (requires forward/aft CG limits from config)

        return True

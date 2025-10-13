"""AI Traffic management plugin."""

from airborne.core.messaging import Message, MessagePriority, MessageQueue, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType
from airborne.physics.vectors import Vector3
from airborne.plugins.traffic.ai_aircraft import AIAircraft
from airborne.plugins.traffic.traffic_patterns import TrafficGenerator


class AITrafficPlugin(IPlugin):
    """Manages AI traffic in the simulation.

    Spawns, updates, and removes AI aircraft. Broadcasts traffic
    information to other plugins (e.g., TCAS).
    """

    def __init__(self) -> None:
        """Initialize AI traffic plugin."""
        self._context: PluginContext | None = None
        self._message_queue: MessageQueue | None = None

        self._traffic_generator = TrafficGenerator()
        self._aircraft: dict[str, AIAircraft] = {}

        # Player aircraft position (to manage traffic spawning)
        self._player_position = Vector3(0, 0, 0)

        # Traffic parameters
        self._max_traffic_count = 10
        self._spawn_distance_nm = 15.0  # Spawn traffic within 15 NM
        self._despawn_distance_nm = 20.0  # Remove traffic beyond 20 NM
        self._update_interval = 0.1  # Broadcast traffic every 0.1s
        self._time_since_broadcast = 0.0

        # Spawning control
        self._time_since_last_spawn = 0.0
        self._spawn_interval = 30.0  # Spawn new traffic every 30 seconds
        self._traffic_enabled = True

    def get_metadata(self) -> PluginMetadata:
        """Get plugin metadata."""
        return PluginMetadata(
            name="ai_traffic",
            version="1.0.0",
            author="AirBorne",
            plugin_type=PluginType.WORLD,
            description="AI traffic generation and management",
            dependencies=[],
            provides=["ai_traffic"],
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize plugin with context."""
        self._context = context
        self._message_queue = context.message_queue

        # Subscribe to position updates
        if self._message_queue:
            self._message_queue.subscribe(MessageTopic.POSITION_UPDATED, self.handle_message)

        # Load configuration
        if context.config:
            traffic_config = context.config.get("traffic", {})
            self._max_traffic_count = traffic_config.get("max_count", 10)
            self._spawn_distance_nm = traffic_config.get("spawn_distance_nm", 15.0)
            self._despawn_distance_nm = traffic_config.get("despawn_distance_nm", 20.0)
            self._traffic_enabled = traffic_config.get("enabled", True)

    def update(self, dt: float) -> None:
        """Update AI traffic.

        Args:
            dt: Time delta in seconds
        """
        if not self._traffic_enabled:
            return

        # Update all AI aircraft
        for aircraft in list(self._aircraft.values()):
            aircraft.update(dt)

            # Remove aircraft that are too far away
            distance_nm = aircraft.get_distance_to(self._player_position)
            if distance_nm > self._despawn_distance_nm:
                del self._aircraft[aircraft.callsign]

        # Spawn new traffic periodically
        self._time_since_last_spawn += dt
        if self._time_since_last_spawn >= self._spawn_interval:
            self._time_since_last_spawn = 0.0
            self._spawn_traffic()

        # Broadcast traffic updates
        self._time_since_broadcast += dt
        if self._time_since_broadcast >= self._update_interval:
            self._time_since_broadcast = 0.0
            self._broadcast_traffic()

    def shutdown(self) -> None:
        """Shutdown plugin."""
        if self._message_queue:
            self._message_queue.unsubscribe(MessageTopic.POSITION_UPDATED, self.handle_message)

        self._aircraft.clear()

    def handle_message(self, message: Message) -> None:
        """Handle incoming messages.

        Args:
            message: Message to handle
        """
        if message.topic == MessageTopic.POSITION_UPDATED:
            self._handle_position_update(message)

    def _handle_position_update(self, message: Message) -> None:
        """Handle player position update."""
        data = message.data
        if data and "position" in data:
            self._player_position = data["position"]

    def _spawn_traffic(self) -> None:
        """Spawn new AI traffic near player."""
        # Don't spawn if already at max
        if len(self._aircraft) >= self._max_traffic_count:
            return

        # Spawn random traffic near player
        # For now, just spawn departing or arriving aircraft
        import random

        traffic_type = random.choice(["departure", "arrival", "pattern"])

        # Random runway heading
        runway_heading = random.uniform(0, 360)

        if traffic_type == "departure":
            aircraft = self._traffic_generator.generate_departure(
                airport_position=self._player_position,
                runway_heading=runway_heading,
                airport_elevation_ft=0.0,
            )
            self._aircraft[aircraft.callsign] = aircraft

        elif traffic_type == "arrival":
            aircraft = self._traffic_generator.generate_arrival(
                airport_position=self._player_position,
                runway_heading=runway_heading,
                airport_elevation_ft=0.0,
                entry_distance_nm=self._spawn_distance_nm,
            )
            self._aircraft[aircraft.callsign] = aircraft

        else:  # pattern
            pattern_aircraft = self._traffic_generator.generate_pattern_traffic(
                airport_position=self._player_position,
                runway_heading=runway_heading,
                airport_elevation_ft=0.0,
                count=1,
            )
            if pattern_aircraft:
                aircraft = pattern_aircraft[0]
                self._aircraft[aircraft.callsign] = aircraft

    def _broadcast_traffic(self) -> None:
        """Broadcast traffic updates to other plugins."""
        if not self._message_queue:
            return

        # Create list of all traffic
        traffic_list = list(self._aircraft.values())

        # Publish traffic update
        self._message_queue.publish(
            Message(
                sender="ai_traffic",
                recipients=["*"],
                topic=MessageTopic.TRAFFIC_UPDATE,
                data={"traffic": traffic_list, "count": len(traffic_list)},
                priority=MessagePriority.NORMAL,
            )
        )

    def add_aircraft(self, aircraft: AIAircraft) -> None:
        """Manually add an AI aircraft.

        Args:
            aircraft: Aircraft to add
        """
        self._aircraft[aircraft.callsign] = aircraft

    def remove_aircraft(self, callsign: str) -> None:
        """Remove an AI aircraft.

        Args:
            callsign: Callsign of aircraft to remove
        """
        if callsign in self._aircraft:
            del self._aircraft[callsign]

    def get_aircraft(self, callsign: str) -> AIAircraft | None:
        """Get an AI aircraft by callsign.

        Args:
            callsign: Aircraft callsign

        Returns:
            AIAircraft or None if not found
        """
        return self._aircraft.get(callsign)

    def get_all_aircraft(self) -> dict[str, AIAircraft]:
        """Get all AI aircraft.

        Returns:
            Dictionary of all aircraft by callsign
        """
        return self._aircraft.copy()

    def get_aircraft_count(self) -> int:
        """Get current number of AI aircraft.

        Returns:
            Number of active AI aircraft
        """
        return len(self._aircraft)

    def clear_all_aircraft(self) -> None:
        """Remove all AI aircraft."""
        self._aircraft.clear()

    def set_traffic_enabled(self, enabled: bool) -> None:
        """Enable or disable AI traffic.

        Args:
            enabled: True to enable, False to disable
        """
        self._traffic_enabled = enabled
        if not enabled:
            self.clear_all_aircraft()

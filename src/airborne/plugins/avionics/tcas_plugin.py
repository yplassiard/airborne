"""TCAS (Traffic Collision Avoidance System) plugin."""

from dataclasses import dataclass
from enum import Enum

from airborne.core.messaging import Message, MessagePriority, MessageQueue, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType
from airborne.physics.vectors import Vector3
from airborne.plugins.traffic.ai_aircraft import AIAircraft


class AlertLevel(Enum):
    """TCAS alert levels."""

    NONE = "none"
    TA = "traffic_advisory"  # Traffic Advisory (20-48 seconds)
    RA = "resolution_advisory"  # Resolution Advisory (15-35 seconds)


class RAType(Enum):
    """Resolution Advisory types."""

    CLIMB = "climb"
    DESCEND = "descend"
    MONITOR_VERTICAL_SPEED = "monitor_vertical_speed"
    MAINTAIN_VERTICAL_SPEED = "maintain_vertical_speed"


@dataclass
class TrafficTarget:
    """Nearby traffic target tracked by TCAS.

    Attributes:
        callsign: Target aircraft callsign
        position: Target position
        velocity: Target velocity vector
        altitude_ft: Target altitude in feet
        vertical_speed_fpm: Target vertical speed in feet per minute
        closure_rate_kts: Closure rate in knots (positive = closing)
        distance_nm: Distance in nautical miles
        time_to_cpa: Time to closest point of approach in seconds
        altitude_separation_ft: Vertical separation in feet
        alert_level: Current alert level for this target
        ra_type: Resolution advisory type if RA is active
    """

    callsign: str
    position: Vector3
    velocity: Vector3
    altitude_ft: float
    vertical_speed_fpm: float
    closure_rate_kts: float
    distance_nm: float
    time_to_cpa: float
    altitude_separation_ft: float
    alert_level: AlertLevel = AlertLevel.NONE
    ra_type: RAType | None = None


class TCASPlugin(IPlugin):
    """TCAS collision avoidance system.

    Monitors nearby traffic and issues Traffic Advisories (TA) and
    Resolution Advisories (RA) to prevent mid-air collisions.

    Alert Logic:
        - TA: 20-48 seconds to collision, aural "Traffic, traffic"
        - RA: 15-35 seconds to collision, aural "Climb, climb" or "Descend, descend"
    """

    def __init__(self) -> None:
        """Initialize TCAS plugin."""
        self._context: PluginContext | None = None
        self._message_queue: MessageQueue | None = None

        self._enabled = True
        self._powered = False

        # Own aircraft state
        self._own_position = Vector3(0, 0, 0)
        self._own_altitude_ft = 0.0
        self._own_vertical_speed_fpm = 0.0

        # Traffic targets
        self._targets: dict[str, TrafficTarget] = {}

        # Alert state
        self._current_alert_level = AlertLevel.NONE
        self._active_ra: RAType | None = None
        self._last_audio_time = 0.0
        self._time_accumulator = 0.0

        # TCAS parameters
        self._ta_time_threshold_sec = 20.0  # TA at 20-48 seconds
        self._ra_time_threshold_sec = 15.0  # RA at 15-35 seconds
        self._horizontal_protection_nm = 0.5  # 0.5 NM horizontal protection
        self._vertical_protection_ft = 600.0  # 600 ft vertical protection
        self._audio_repeat_interval = 5.0  # Repeat alerts every 5 seconds

    def get_metadata(self) -> PluginMetadata:
        """Get plugin metadata."""
        return PluginMetadata(
            name="tcas",
            version="1.0.0",
            author="AirBorne",
            plugin_type=PluginType.AVIONICS,
            description="TCAS traffic collision avoidance system",
            dependencies=["electrical"],
            provides=["tcas"],
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize plugin with context."""
        self._context = context
        self._message_queue = context.message_queue

        # Subscribe to messages
        if self._message_queue:
            self._message_queue.subscribe(MessageTopic.POSITION_UPDATED, self.handle_message)
            self._message_queue.subscribe(MessageTopic.TRAFFIC_UPDATE, self.handle_message)
            self._message_queue.subscribe(MessageTopic.ELECTRICAL_STATE, self.handle_message)

    def update(self, dt: float) -> None:
        """Update TCAS state.

        Args:
            dt: Time delta in seconds
        """
        if not self._enabled or not self._powered:
            return

        self._time_accumulator += dt

        # Analyze threats
        self._analyze_traffic()

        # Issue alerts if needed
        self._issue_alerts()

    def shutdown(self) -> None:
        """Shutdown plugin."""
        if self._message_queue:
            self._message_queue.unsubscribe(MessageTopic.POSITION_UPDATED, self.handle_message)
            self._message_queue.unsubscribe(MessageTopic.TRAFFIC_UPDATE, self.handle_message)
            self._message_queue.unsubscribe(MessageTopic.ELECTRICAL_STATE, self.handle_message)

    def handle_message(self, message: Message) -> None:
        """Handle incoming messages.

        Args:
            message: Message to handle
        """
        if message.topic == MessageTopic.POSITION_UPDATED:
            self._handle_position_update(message)
        elif message.topic == MessageTopic.TRAFFIC_UPDATE:
            self._handle_traffic_update(message)
        elif message.topic == MessageTopic.ELECTRICAL_STATE:
            self._handle_electrical_state(message)

    def _handle_position_update(self, message: Message) -> None:
        """Handle position update from own aircraft."""
        data = message.data
        if data and "position" in data:
            self._own_position = data["position"]
            self._own_altitude_ft = data.get("altitude_ft", 0.0)
            self._own_vertical_speed_fpm = data.get("vertical_speed_fpm", 0.0)

    def _handle_traffic_update(self, message: Message) -> None:
        """Handle traffic update from AI traffic plugin."""
        data = message.data
        if not data or "traffic" not in data:
            return

        # Update tracked targets
        self._targets.clear()

        for aircraft_data in data["traffic"]:
            if isinstance(aircraft_data, AIAircraft):
                target = self._create_target_from_aircraft(aircraft_data)
                if target:
                    self._targets[target.callsign] = target

    def _handle_electrical_state(self, message: Message) -> None:
        """Handle electrical state updates."""
        data = message.data
        if data:
            bus_voltage = data.get("bus_voltage", 0.0)
            self._powered = bus_voltage > 20.0  # Need at least 20V

    def _create_target_from_aircraft(self, aircraft: AIAircraft) -> TrafficTarget | None:
        """Create traffic target from AI aircraft.

        Args:
            aircraft: AI aircraft

        Returns:
            TrafficTarget or None if too far away
        """
        # Calculate distance
        distance_m = self._own_position.distance_to(aircraft.position)
        distance_nm = distance_m / 6076.0

        # Ignore traffic beyond 10 NM
        if distance_nm > 10.0:
            return None

        # Calculate closure rate and time to CPA
        dx = aircraft.position.x - self._own_position.x
        dy = aircraft.position.y - self._own_position.y
        dz = aircraft.position.z - self._own_position.z

        # Relative velocity (simplified - assumes own velocity is in aircraft data)
        dvx = aircraft.velocity.x
        dvy = aircraft.velocity.y
        dvz = aircraft.velocity.z

        # Closure rate = rate of change of distance
        # If distance is decreasing, closure rate is positive
        if distance_m > 0.1:
            closure_rate_mps = -(dvx * dx + dvy * dy + dvz * dz) / distance_m
        else:
            closure_rate_mps = 0.0

        closure_rate_kts = closure_rate_mps * 1.94384  # m/s to knots

        # Time to closest point of approach (simplified)
        time_to_cpa = distance_m / closure_rate_mps if closure_rate_mps > 0 else float("inf")

        # Altitude separation
        altitude_separation_ft = abs(aircraft.altitude_ft - self._own_altitude_ft)

        return TrafficTarget(
            callsign=aircraft.callsign,
            position=aircraft.position,
            velocity=aircraft.velocity,
            altitude_ft=aircraft.altitude_ft,
            vertical_speed_fpm=aircraft.vertical_speed_fpm,
            closure_rate_kts=closure_rate_kts,
            distance_nm=distance_nm,
            time_to_cpa=time_to_cpa,
            altitude_separation_ft=altitude_separation_ft,
        )

    def _analyze_traffic(self) -> None:
        """Analyze traffic and determine threat levels."""
        highest_threat = AlertLevel.NONE
        ra_type = None

        for target in self._targets.values():
            # Reset alert level
            target.alert_level = AlertLevel.NONE
            target.ra_type = None

            # Check if within protection zone
            if target.distance_nm > self._horizontal_protection_nm * 2:
                continue

            # Check vertical separation
            if target.altitude_separation_ft > self._vertical_protection_ft * 2:
                continue

            # Determine alert level based on time to CPA
            if target.time_to_cpa < self._ra_time_threshold_sec:
                # Resolution Advisory
                target.alert_level = AlertLevel.RA

                # Determine RA type based on relative vertical speed
                vertical_separation = target.altitude_ft - self._own_altitude_ft

                if vertical_separation > 0:
                    # Target is above - descend
                    target.ra_type = RAType.DESCEND
                else:
                    # Target is below - climb
                    target.ra_type = RAType.CLIMB

                if target.alert_level.value > highest_threat.value:
                    highest_threat = target.alert_level
                    ra_type = target.ra_type

            elif target.time_to_cpa < self._ta_time_threshold_sec:
                # Traffic Advisory
                target.alert_level = AlertLevel.TA

                if target.alert_level.value > highest_threat.value:
                    highest_threat = target.alert_level

        # Update system-wide alert state
        self._current_alert_level = highest_threat
        self._active_ra = ra_type

    def _issue_alerts(self) -> None:
        """Issue audio alerts for traffic conflicts."""
        if self._current_alert_level == AlertLevel.NONE:
            return

        # Rate limit audio alerts
        if self._time_accumulator - self._last_audio_time < self._audio_repeat_interval:
            return

        self._last_audio_time = self._time_accumulator

        # Publish alert message
        if self._message_queue:
            if self._current_alert_level == AlertLevel.TA:
                # Traffic Advisory
                self._message_queue.publish(
                    Message(
                        sender="tcas",
                        recipients=["*"],
                        topic=MessageTopic.TCAS_ALERT,
                        data={"alert_type": "TA", "message": "Traffic, traffic"},
                        priority=MessagePriority.HIGH,
                    )
                )

            elif self._current_alert_level == AlertLevel.RA:
                # Resolution Advisory
                if self._active_ra == RAType.CLIMB:
                    message_text = "Climb, climb"
                elif self._active_ra == RAType.DESCEND:
                    message_text = "Descend, descend"
                else:
                    message_text = "Monitor vertical speed"

                self._message_queue.publish(
                    Message(
                        sender="tcas",
                        recipients=["*"],
                        topic=MessageTopic.TCAS_ALERT,
                        data={
                            "alert_type": "RA",
                            "ra_type": self._active_ra.value if self._active_ra else None,
                            "message": message_text,
                        },
                        priority=MessagePriority.CRITICAL,
                    )
                )

    def get_targets(self) -> dict[str, TrafficTarget]:
        """Get all tracked traffic targets.

        Returns:
            Dictionary of targets by callsign
        """
        return self._targets.copy()

    def get_current_alert_level(self) -> AlertLevel:
        """Get current system alert level.

        Returns:
            Current alert level
        """
        return self._current_alert_level

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable TCAS.

        Args:
            enabled: True to enable, False to disable
        """
        self._enabled = enabled

"""Runway incursion detection for AirBorne.

This module provides runway incursion detection to prevent unauthorized
runway entries. Issues graduated warnings (caution, warning, alert) based
on proximity to runway and clearance state.

Typical usage:
    from airborne.plugins.navigation.runway_incursion import RunwayIncursionDetector

    detector = RunwayIncursionDetector(message_queue, runways)
    detector.subscribe_to_events()
    detector.update(aircraft_position, heading, timestamp)
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum

from airborne.airports.database import Runway
from airborne.core.messaging import Message, MessagePriority, MessageQueue, MessageTopic
from airborne.physics.vectors import Vector3

logger = logging.getLogger(__name__)


class IncursionLevel(Enum):
    """Runway incursion warning levels.

    Attributes:
        NONE: No warning, aircraft not near runway or has clearance
        CAUTION: Aircraft within 50m of runway without clearance
        WARNING: Aircraft within 20m of runway without clearance
        ALERT: Aircraft crossed hold-short line without clearance

    Examples:
        >>> level = IncursionLevel.WARNING
        >>> level.value
        'warning'
    """

    NONE = "none"
    CAUTION = "caution"
    WARNING = "warning"
    ALERT = "alert"


@dataclass
class RunwayProximity:
    """Tracks aircraft proximity to a specific runway.

    Attributes:
        runway: Runway object
        distance_m: Current distance to runway centerline in meters
        last_warning_level: Last warning level issued
        last_warning_time: Timestamp of last warning

    Examples:
        >>> prox = RunwayProximity(runway, 30.0, IncursionLevel.CAUTION, time.time())
    """

    runway: Runway
    distance_m: float
    last_warning_level: IncursionLevel = IncursionLevel.NONE
    last_warning_time: float = 0.0


class RunwayIncursionDetector:
    """Detects and warns about potential runway incursions.

    Monitors aircraft position relative to runways and issues graduated
    warnings when approaching without clearance. Integrates with ATC
    clearance system to suppress warnings when cleared.

    Attributes:
        message_queue: Queue for publishing warning messages
        runways: List of runways at current airport
        cleared_runways: Set of runway IDs aircraft is cleared for
        proximity_data: Dict of runway proximity data
        warning_cooldown: Minimum seconds between duplicate warnings

    Examples:
        >>> detector = RunwayIncursionDetector(message_queue, runways)
        >>> detector.subscribe_to_events()
        >>> detector.update(position, heading, timestamp)
    """

    def __init__(
        self,
        message_queue: MessageQueue | None = None,
        runways: list[Runway] | None = None,
        warning_cooldown: float = 3.0,
    ) -> None:
        """Initialize runway incursion detector.

        Args:
            message_queue: Message queue for publishing warnings
            runways: List of runways to monitor
            warning_cooldown: Minimum seconds between duplicate warnings
        """
        self.message_queue = message_queue
        self.runways = runways or []
        self.warning_cooldown = warning_cooldown

        # Clearance tracking
        self.cleared_runways: set[str] = set()

        # Proximity tracking
        self.proximity_data: dict[str, RunwayProximity] = {}

        logger.info(
            "RunwayIncursionDetector initialized (%d runways, cooldown=%.1fs)",
            len(self.runways),
            warning_cooldown,
        )

    def subscribe_to_events(self) -> None:
        """Subscribe to ATC clearance events.

        Must be called after initialization to receive clearance updates.
        """
        if not self.message_queue:
            logger.warning("Cannot subscribe to events: no message queue")
            return

        # Subscribe to ATC clearance messages
        self.message_queue.subscribe("atc.clearance.takeoff", self._on_clearance_granted)
        self.message_queue.subscribe("atc.clearance.landing", self._on_clearance_granted)
        self.message_queue.subscribe("atc.clearance.crossing", self._on_clearance_granted)
        self.message_queue.subscribe("atc.clearance.revoked", self._on_clearance_revoked)

        logger.info("Subscribed to ATC clearance events")

    def unsubscribe_from_events(self) -> None:
        """Unsubscribe from ATC clearance events."""
        if not self.message_queue:
            return

        self.message_queue.unsubscribe("atc.clearance.takeoff", self._on_clearance_granted)
        self.message_queue.unsubscribe("atc.clearance.landing", self._on_clearance_granted)
        self.message_queue.unsubscribe("atc.clearance.crossing", self._on_clearance_granted)
        self.message_queue.unsubscribe("atc.clearance.revoked", self._on_clearance_revoked)

        logger.info("Unsubscribed from ATC clearance events")

    def update(  # pylint: disable=unused-argument
        self, position: Vector3, heading: float, timestamp: float = 0.0
    ) -> None:
        """Update incursion detection with current aircraft state.

        Args:
            position: Current aircraft position (lat, alt, lon)
            heading: Current magnetic heading in degrees (reserved for future use)
            timestamp: Current simulation time (default: time.time())

        Examples:
            >>> detector.update(Vector3(-122.0, 10.0, 37.5), 270.0, time.time())
        """
        if timestamp == 0.0:
            timestamp = time.time()

        # Check proximity to each runway
        for runway in self.runways:
            # Calculate distance to runway centerline
            distance = self._calculate_runway_distance(position, runway)

            # Get or create proximity data
            runway_key = f"{runway.le_ident}/{runway.he_ident}"
            if runway_key not in self.proximity_data:
                self.proximity_data[runway_key] = RunwayProximity(
                    runway=runway,
                    distance_m=distance,
                )
            else:
                self.proximity_data[runway_key].distance_m = distance

            # Determine warning level
            warning_level = self._determine_warning_level(runway_key, distance)

            # Issue warning if needed
            if warning_level != IncursionLevel.NONE:
                self._issue_warning(runway_key, warning_level, distance, timestamp)

    def grant_clearance(self, runway_id: str) -> None:
        """Grant clearance for a specific runway.

        Args:
            runway_id: Runway identifier (e.g., "31", "09L")

        Examples:
            >>> detector.grant_clearance("31")
        """
        self.cleared_runways.add(runway_id)
        logger.info("Granted clearance for runway %s", runway_id)

    def revoke_clearance(self, runway_id: str | None = None) -> None:
        """Revoke clearance for a specific runway or all runways.

        Args:
            runway_id: Runway identifier, or None to revoke all clearances

        Examples:
            >>> detector.revoke_clearance("31")
            >>> detector.revoke_clearance()  # Clear all
        """
        if runway_id is None:
            self.cleared_runways.clear()
            logger.info("Revoked all runway clearances")
        else:
            self.cleared_runways.discard(runway_id)
            logger.info("Revoked clearance for runway %s", runway_id)

    def is_cleared(self, runway_id: str) -> bool:
        """Check if aircraft is cleared for a specific runway.

        Args:
            runway_id: Runway identifier

        Returns:
            True if cleared, False otherwise

        Examples:
            >>> detector.grant_clearance("31")
            >>> detector.is_cleared("31")
            True
        """
        return runway_id in self.cleared_runways

    def get_nearest_runway(self, position: Vector3) -> tuple[Runway | None, float]:
        """Find nearest runway to position.

        Args:
            position: Aircraft position (lat, alt, lon)

        Returns:
            Tuple of (nearest runway, distance in meters), or (None, inf)

        Examples:
            >>> runway, distance = detector.get_nearest_runway(position)
        """
        nearest_runway = None
        min_distance = float("inf")

        for runway in self.runways:
            distance = self._calculate_runway_distance(position, runway)
            if distance < min_distance:
                min_distance = distance
                nearest_runway = runway

        return nearest_runway, min_distance

    def _calculate_runway_distance(self, position: Vector3, runway: Runway) -> float:
        """Calculate perpendicular distance from position to runway centerline.

        Args:
            position: Aircraft position (lat, alt, lon)
            runway: Runway object

        Returns:
            Distance to runway centerline in meters
        """
        # Extract position coordinates
        lat = position.x
        lon = position.z

        # Runway endpoints
        le_lat, le_lon = runway.le_latitude, runway.le_longitude
        he_lat, he_lon = runway.he_latitude, runway.he_longitude

        # Calculate distance to runway line segment
        return self._point_to_segment_distance(lat, lon, le_lat, le_lon, he_lat, he_lon)

    def _point_to_segment_distance(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
        self, px: float, py: float, x1: float, y1: float, x2: float, y2: float
    ) -> float:
        """Calculate distance from point to line segment.

        Uses projection to find closest point on segment, then calculates
        distance. Converts lat/lon differences to approximate meters.

        Args:
            px, py: Point coordinates (lat, lon)
            x1, y1: Segment start (lat, lon)
            x2, y2: Segment end (lat, lon)

        Returns:
            Distance in meters
        """
        # Vector from start to end of segment
        dx = x2 - x1
        dy = y2 - y1

        # Segment length squared
        segment_length_sq = dx * dx + dy * dy

        if segment_length_sq == 0:
            # Segment is a point
            diff_x = px - x1
            diff_y = py - y1
            return float((diff_x * diff_x + diff_y * diff_y) ** 0.5) * 111000.0

        # Project point onto segment line
        # t = ((px - x1) * dx + (py - y1) * dy) / segment_length_sq
        t = ((px - x1) * dx + (py - y1) * dy) / segment_length_sq
        t = max(0.0, min(1.0, t))  # Clamp to [0, 1]

        # Find closest point on segment
        closest_x = x1 + t * dx
        closest_y = y1 + t * dy

        # Calculate distance to closest point
        diff_x = px - closest_x
        diff_y = py - closest_y

        # Convert to meters (approximate)
        distance_degrees = (diff_x * diff_x + diff_y * diff_y) ** 0.5
        return float(distance_degrees * 111000.0)

    def _determine_warning_level(self, runway_key: str, distance_m: float) -> IncursionLevel:
        """Determine warning level based on distance and clearance.

        Args:
            runway_key: Runway identifier key
            distance_m: Distance to runway in meters

        Returns:
            Warning level
        """
        # Extract runway ID from key (e.g., "09L/27R" -> "09L" or "27R")
        runway_ids = runway_key.split("/")

        # Check if cleared for either end of runway
        is_cleared = any(rid in self.cleared_runways for rid in runway_ids)

        if is_cleared:
            return IncursionLevel.NONE

        # Graduated warnings based on proximity
        if distance_m <= 0.0:
            return IncursionLevel.ALERT  # Crossed hold-short line
        if distance_m <= 20.0:
            return IncursionLevel.WARNING  # Within 20m
        if distance_m <= 50.0:
            return IncursionLevel.CAUTION  # Within 50m

        return IncursionLevel.NONE

    def _issue_warning(
        self, runway_key: str, level: IncursionLevel, distance_m: float, timestamp: float
    ) -> None:
        """Issue runway incursion warning.

        Args:
            runway_key: Runway identifier key
            level: Warning level
            distance_m: Distance to runway
            timestamp: Current time
        """
        prox = self.proximity_data[runway_key]

        # Check cooldown and if we need to issue warning
        time_since_last = timestamp - prox.last_warning_time
        if time_since_last < self.warning_cooldown and level == prox.last_warning_level:
            return

        # Update warning state
        prox.last_warning_level = level
        prox.last_warning_time = timestamp

        # Generate warning message
        message_text = self._generate_warning_message(runway_key, level, distance_m)

        # Publish warning
        if self.message_queue:
            # Determine priority
            priority = MessagePriority.NORMAL
            if level == IncursionLevel.WARNING:
                priority = MessagePriority.HIGH
            elif level == IncursionLevel.ALERT:
                priority = MessagePriority.CRITICAL

            warning_msg = Message(
                sender="runway_incursion",
                recipients=["audio_plugin"],
                topic=MessageTopic.TTS_SPEAK,
                data={
                    "text": message_text,
                    "voice": "cockpit",
                    "interrupt": level == IncursionLevel.ALERT,
                },
                priority=priority,
            )

            self.message_queue.publish(warning_msg)
            logger.warning(
                "Issued %s warning for runway %s at %.1fm", level.value, runway_key, distance_m
            )

    def _generate_warning_message(  # pylint: disable=unused-argument
        self, runway_key: str, level: IncursionLevel, distance_m: float
    ) -> str:
        """Generate warning message text.

        Args:
            runway_key: Runway identifier key
            level: Warning level
            distance_m: Distance to runway (reserved for future distance-specific messages)

        Returns:
            Warning message text
        """
        # Extract first runway ID
        runway_id = runway_key.split("/")[0]

        if level == IncursionLevel.CAUTION:
            return f"Caution, approaching runway {runway_id}"
        if level == IncursionLevel.WARNING:
            return f"Warning, hold short runway {runway_id}"
        if level == IncursionLevel.ALERT:
            return f"Alert! Runway incursion, runway {runway_id}"

        return f"Runway {runway_id} ahead"

    def _on_clearance_granted(self, msg: Message) -> None:
        """Handle clearance granted message.

        Args:
            msg: Clearance message
        """
        runway_id = msg.data.get("runway_id", "")
        if runway_id:
            self.grant_clearance(runway_id)

    def _on_clearance_revoked(self, msg: Message) -> None:
        """Handle clearance revoked message.

        Args:
            msg: Revocation message
        """
        runway_id = msg.data.get("runway_id", None)
        self.revoke_clearance(runway_id)

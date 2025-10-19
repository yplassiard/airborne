"""Position Awareness Plugin for AirBorne.

Integrates position tracking, orientation audio, and runway incursion detection
to provide comprehensive situational awareness on the ground.

Typical usage:
    In aircraft YAML:
        plugins:
          - name: position_awareness
            config:
              enabled: true
"""

import logging
import time
from typing import Any

from airborne.airports.taxiway import TaxiwayGraph
from airborne.audio.orientation import OrientationAudioManager
from airborne.core.messaging import Message, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType
from airborne.physics.vectors import Vector3
from airborne.plugins.navigation.position_tracker import PositionTracker
from airborne.plugins.navigation.runway_incursion import RunwayIncursionDetector

logger = logging.getLogger(__name__)


class PositionAwarenessPlugin(IPlugin):
    """Position awareness plugin with audio cues and safety warnings.

    Provides:
    - Real-time position tracking on taxiways/runways/parking
    - Audio announcements when entering new areas
    - Runway incursion detection and warnings
    - Manual position query (P key)

    Examples:
        In aircraft YAML:
            plugins:
              - name: position_awareness
                config:
                  enabled: true
    """

    def __init__(self) -> None:
        """Initialize position awareness plugin."""
        super().__init__()

        # Context
        self.context: PluginContext | None = None

        # Components
        self.position_tracker: PositionTracker | None = None
        self.orientation_audio: OrientationAudioManager | None = None
        self.incursion_detector: RunwayIncursionDetector | None = None

        # State
        self.last_position: Vector3 | None = None
        self.last_heading: float = 0.0
        self.enabled = True

        logger.info("Position Awareness Plugin initialized")

    def get_metadata(self) -> PluginMetadata:
        """Get plugin metadata.

        Returns:
            Plugin metadata with name, version, type, and dependencies
        """
        return PluginMetadata(
            name="position_awareness",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.AVIONICS,
            dependencies=["ground_navigation"],
            provides=["position_awareness", "orientation"],
        )

    def initialize(self, context: PluginContext | dict[str, Any]) -> None:
        """Initialize the plugin.

        Args:
            context: Plugin context with configuration
        """
        # Support both PluginContext and dict for backward compatibility with tests
        if isinstance(context, dict):
            config = context.get("config", {})
            message_queue = context.get("message_queue")
        else:
            self.context = context
            config = context.config.get("position_awareness", {})
            message_queue = context.message_queue

        # Load configuration
        self.enabled = config.get("enabled", True)

        if not self.enabled:
            logger.info("Position Awareness Plugin disabled by config")
            return

        # Initialize components
        # Note: PositionTracker needs a TaxiwayGraph (will be empty initially,
        # populated later by ground_navigation plugin)
        empty_graph = TaxiwayGraph()
        self.position_tracker = PositionTracker(empty_graph, message_queue)
        self.orientation_audio = OrientationAudioManager(message_queue)
        self.incursion_detector = RunwayIncursionDetector(message_queue)

        # Subscribe to position updates
        if self.context:
            self.context.message_queue.subscribe(
                MessageTopic.POSITION_UPDATED, self._on_position_updated
            )
            self.context.message_queue.subscribe("input.position_query", self._on_position_query)
            self.context.message_queue.subscribe(
                "input.detailed_position_query", self._on_detailed_position_query
            )
            self.context.message_queue.subscribe(
                "input.nearby_features_query", self._on_nearby_features_query
            )

        # Subscribe components to events
        if self.orientation_audio:
            self.orientation_audio.subscribe_to_events()

        if self.incursion_detector:
            self.incursion_detector.subscribe_to_events()

        logger.info("Position Awareness Plugin initialized (enabled=%s)", self.enabled)

    def update(self, dt: float) -> None:
        """Update position awareness.

        Args:
            dt: Time since last update (seconds)
        """
        if not self.enabled:
            return

        # Update position tracker
        if self.position_tracker and self.last_position:
            self.position_tracker.update(self.last_position, self.last_heading, time.time())

        # Update runway incursion detector
        if self.incursion_detector and self.last_position:
            self.incursion_detector.update(self.last_position, self.last_heading, time.time())

    def shutdown(self) -> None:
        """Shutdown the plugin."""
        if self.context:
            # Unsubscribe from messages
            self.context.message_queue.unsubscribe(
                MessageTopic.POSITION_UPDATED, self._on_position_updated
            )
            self.context.message_queue.unsubscribe("input.position_query", self._on_position_query)
            self.context.message_queue.unsubscribe(
                "input.detailed_position_query", self._on_detailed_position_query
            )
            self.context.message_queue.unsubscribe(
                "input.nearby_features_query", self._on_nearby_features_query
            )

        # Unsubscribe components
        if self.orientation_audio:
            self.orientation_audio.unsubscribe_from_events()

        if self.incursion_detector:
            self.incursion_detector.unsubscribe_from_events()

        logger.info("Position Awareness Plugin shutdown")

    def handle_message(self, message: Message) -> None:
        """Handle plugin messages.

        Args:
            message: Message from plugin system
        """
        if message.topic == MessageTopic.POSITION_UPDATED:
            self._on_position_updated(message)
        elif message.topic == "input.position_query":
            self._on_position_query(message)
        elif message.topic == "input.detailed_position_query":
            self._on_detailed_position_query(message)
        elif message.topic == "input.nearby_features_query":
            self._on_nearby_features_query(message)

    def _on_position_updated(self, message: Message) -> None:
        """Handle position update message.

        Args:
            message: Position update message
        """
        data = message.data
        if "position" in data:
            pos = data["position"]
            if isinstance(pos, dict):
                self.last_position = Vector3(
                    pos.get("x", 0.0), pos.get("y", 0.0), pos.get("z", 0.0)
                )
            elif isinstance(pos, (tuple, list)) and len(pos) >= 3:
                self.last_position = Vector3(float(pos[0]), float(pos[1]), float(pos[2]))
            elif isinstance(pos, Vector3):
                self.last_position = pos

        if "heading" in data:
            self.last_heading = float(data["heading"])

    def _on_position_query(self, _message: Message) -> None:
        """Handle position query request (P key).

        Args:
            _message: Position query message (unused)
        """
        if not self.position_tracker or not self.orientation_audio:
            logger.warning("Position query failed: components not initialized")
            return

        # Get current location
        location_type, location_id = self.position_tracker.get_current_location()

        # Announce position
        self.orientation_audio.announce_current_position(
            location_type, location_id, self.last_position
        )

        logger.info("Position query: %s at %s", location_type.value, location_id)

    def _on_detailed_position_query(self, _message: Message) -> None:
        """Handle detailed position query (Shift+P).

        Args:
            _message: Detailed position query message (unused)
        """
        if not self.position_tracker or not self.orientation_audio or not self.context:
            logger.warning("Detailed position query failed: components not initialized")
            return

        # Get current location
        location_type, location_id = self.position_tracker.get_current_location()

        # Get additional details
        nearest_taxiway = self.position_tracker.get_nearest_taxiway()
        distance_to_next = self.position_tracker.get_distance_to_next_intersection()

        # Build detailed message
        details = [f"{location_type.value} {location_id}"]

        if nearest_taxiway and nearest_taxiway != location_id:
            details.append(f"nearest taxiway {nearest_taxiway}")

        if distance_to_next < 1000.0:
            details.append(f"{int(distance_to_next)} meters to next intersection")

        if self.last_heading:
            details.append(f"heading {int(self.last_heading)} degrees")

        message_text = ", ".join(details)

        # Publish TTS message
        self.context.message_queue.publish(
            Message(
                sender="position_awareness",
                recipients=["audio_plugin"],
                topic=MessageTopic.TTS_SPEAK,
                data={"text": message_text, "voice": "cockpit", "interrupt": False},
            )
        )

        logger.info("Detailed position query: %s", message_text)

    def _on_nearby_features_query(self, _message: Message) -> None:
        """Handle nearby features query (Ctrl+P).

        Args:
            _message: Nearby features query message (unused)
        """
        if not self.position_tracker or not self.context:
            logger.warning("Nearby features query failed: components not initialized")
            return

        if not self.last_position:
            logger.warning("Nearby features query failed: no position available")
            return

        # Get position history to find nearby features
        # This is a simplified implementation - in real usage would query taxiway graph
        message_text = "Nearby features query not yet fully implemented"

        # Publish TTS message
        self.context.message_queue.publish(
            Message(
                sender="position_awareness",
                recipients=["audio_plugin"],
                topic=MessageTopic.TTS_SPEAK,
                data={"text": message_text, "voice": "cockpit", "interrupt": False},
            )
        )

        logger.info("Nearby features query")

    def get_status(self) -> dict[str, Any]:
        """Get plugin status.

        Returns:
            Status dictionary with current position info
        """
        status: dict[str, Any] = {
            "enabled": self.enabled,
            "last_position": (
                (self.last_position.x, self.last_position.y, self.last_position.z)
                if self.last_position
                else None
            ),
            "last_heading": self.last_heading,
        }

        if self.position_tracker:
            location_type, location_id = self.position_tracker.get_current_location()
            status["current_location_type"] = location_type.value
            status["current_location_id"] = location_id
            status["nearest_taxiway"] = self.position_tracker.get_nearest_taxiway()

        if self.incursion_detector:
            nearest_runway, distance = self.incursion_detector.get_nearest_runway(
                self.last_position or Vector3(0, 0, 0)
            )
            status["nearest_runway"] = nearest_runway.runway_id if nearest_runway else None
            status["runway_distance_m"] = distance

        return status

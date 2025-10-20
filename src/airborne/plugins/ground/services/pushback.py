"""Pushback service for AirBorne ground operations.

This module provides aircraft pushback service with realistic timing,
audio coordination, and position updates for gate departures.

Typical usage:
    from airborne.plugins.ground.services.pushback import PushbackService

    service = PushbackService(message_queue)
    request = ServiceRequest(
        service_type=ServiceType.PUSHBACK,
        aircraft_id="N123AB",
        parking_id="G1",
        timestamp=time.time(),
        parameters={"direction": "NORTH", "heading": 360}
    )
    service.start(request)
"""

import logging
import math
import time
from enum import Enum

from airborne.core.messaging import Message, MessageQueue
from airborne.physics.vectors import Vector3
from airborne.plugins.ground.ground_services import (
    GroundService,
    ServiceRequest,
    ServiceStatus,
    ServiceType,
)

logger = logging.getLogger(__name__)


class PushbackDirection(Enum):
    """Pushback direction options.

    Attributes:
        NORTH: Push back toward north (heading 360/0)
        SOUTH: Push back toward south (heading 180)
        EAST: Push back toward east (heading 90)
        WEST: Push back toward west (heading 270)
        TO_TAXIWAY: Push back to nearest taxiway (auto-calculated)

    Examples:
        >>> direction = PushbackDirection.NORTH
        >>> direction.value
        'north'
    """

    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"
    TO_TAXIWAY = "to_taxiway"

    def to_heading(self) -> float:
        """Convert direction to magnetic heading.

        Returns:
            Heading in degrees (0-360)

        Examples:
            >>> PushbackDirection.NORTH.to_heading()
            360.0
            >>> PushbackDirection.EAST.to_heading()
            90.0
        """
        headings = {
            PushbackDirection.NORTH: 360.0,
            PushbackDirection.EAST: 90.0,
            PushbackDirection.SOUTH: 180.0,
            PushbackDirection.WEST: 270.0,
            PushbackDirection.TO_TAXIWAY: 0.0,  # Will be calculated
        }
        return headings[self]


class PushbackPhase(Enum):
    """Pushback service phases.

    Attributes:
        WAITING_BRAKE_RELEASE: Waiting for pilot to release parking brake
        PUSHING_BACK: Actively pushing aircraft backward
        COMPLETE: Pushback finished

    Examples:
        >>> phase = PushbackPhase.PUSHING_BACK
        >>> phase == PushbackPhase.COMPLETE
        False
    """

    WAITING_BRAKE_RELEASE = "waiting_brake_release"
    PUSHING_BACK = "pushing_back"
    COMPLETE = "complete"


class PushbackService(GroundService):
    """Aircraft pushback service.

    Provides realistic pushback simulation with:
    - Direction selection (cardinal directions or to taxiway)
    - Brake release coordination
    - Position updates during pushback (30 seconds, ~50m)
    - Audio coordination at each stage
    - Integration with position tracking

    Attributes:
        pushback_phase: Current phase of pushback operation
        pushback_direction: Direction to push back
        target_heading: Heading to push toward (degrees)
        pushback_distance: Distance to push back (meters)
        pushback_duration: Duration of pushback (seconds)
        start_position: Starting position before pushback
        target_position: Target position after pushback
        phase_start_time: Time when current phase started
        last_update_time: Time of last update

    Examples:
        >>> service = PushbackService(message_queue)
        >>> request = ServiceRequest(
        ...     service_type=ServiceType.PUSHBACK,
        ...     aircraft_id="N123AB",
        ...     parking_id="G1",
        ...     timestamp=time.time(),
        ...     parameters={"direction": "NORTH"}
        ... )
        >>> service.start(request)
        True
        >>> service.pushback_phase
        <PushbackPhase.WAITING_BRAKE_RELEASE: 'waiting_brake_release'>
    """

    def __init__(self, message_queue: MessageQueue | None = None) -> None:
        """Initialize pushback service.

        Args:
            message_queue: Optional message queue for publishing events
        """
        super().__init__(ServiceType.PUSHBACK, message_queue)

        # Pushback state
        self.pushback_phase = PushbackPhase.WAITING_BRAKE_RELEASE
        self.pushback_direction: PushbackDirection | None = None
        self.target_heading: float = 0.0
        self.pushback_distance: float = 50.0  # meters
        self.pushback_duration: float = 30.0  # seconds
        self.start_position: Vector3 | None = None
        self.target_position: Vector3 | None = None
        self.phase_start_time: float = 0.0
        self.last_update_time: float = 0.0

    def start(self, request: ServiceRequest) -> bool:
        """Start pushback service.

        Args:
            request: Service request with parameters:
                - direction: Direction to push (NORTH, SOUTH, EAST, WEST, TO_TAXIWAY)
                - heading: Optional specific heading (overrides direction)
                - distance: Optional pushback distance in meters (default 50m)
                - current_position: Current aircraft position (lat, lon, alt)
                - parking_brake: Parking brake state (True/False)

        Returns:
            True if service started successfully, False otherwise

        Examples:
            >>> service = PushbackService()
            >>> request = ServiceRequest(
            ...     service_type=ServiceType.PUSHBACK,
            ...     aircraft_id="N123AB",
            ...     parking_id="G1",
            ...     timestamp=time.time(),
            ...     parameters={"direction": "NORTH"}
            ... )
            >>> service.start(request)
            True
        """
        self.request = request
        self.status = ServiceStatus.IN_PROGRESS
        self.start_time = time.time()
        self.phase_start_time = self.start_time
        self.last_update_time = self.start_time

        # Parse parameters
        params = request.parameters or {}
        direction_str = params.get("direction", "TO_TAXIWAY")
        heading = params.get("heading")
        distance = params.get("distance", 50.0)
        position_dict = params.get("current_position", {"x": 0.0, "y": 0.0, "z": 0.0})

        # Parse direction
        try:
            self.pushback_direction = PushbackDirection(direction_str.lower())
        except (ValueError, AttributeError):
            logger.warning("Invalid pushback direction '%s', using TO_TAXIWAY", direction_str)
            self.pushback_direction = PushbackDirection.TO_TAXIWAY

        # Determine target heading
        if heading is not None:
            self.target_heading = float(heading)
        else:
            self.target_heading = self.pushback_direction.to_heading()

        # Set pushback parameters
        self.pushback_distance = float(distance)
        self.pushback_duration = 30.0  # Fixed duration for now

        # Calculate total duration (waiting + pushback)
        self.estimated_duration = 60.0 + self.pushback_duration  # Max 60s wait + 30s pushback

        # Store start position
        if isinstance(position_dict, dict):
            self.start_position = Vector3(
                position_dict.get("x", 0.0),
                position_dict.get("y", 0.0),
                position_dict.get("z", 0.0),
            )
        elif isinstance(position_dict, Vector3):
            self.start_position = position_dict
        else:
            self.start_position = Vector3(0.0, 0.0, 0.0)

        # Calculate target position (move backward along heading)
        self.target_position = self._calculate_target_position()

        # Start in waiting for brake release phase
        self.pushback_phase = PushbackPhase.WAITING_BRAKE_RELEASE

        # Publish status update
        self._publish_status_update()

        # Publish audio message
        self._publish_audio_message_key("MSG_PUSHBACK_ACKNOWLEDGED", voice="tug")

        logger.info(
            "Pushback started: %s, direction=%s, heading=%.0f°, distance=%.0fm",
            request.aircraft_id,
            self.pushback_direction.value if self.pushback_direction else "unknown",
            self.target_heading,
            self.pushback_distance,
        )

        return True

    def update(self, dt: float) -> None:
        """Update pushback service state.

        Args:
            dt: Time since last update (seconds)
        """
        if self.status != ServiceStatus.IN_PROGRESS:
            return

        current_time = time.time()
        phase_elapsed = current_time - self.phase_start_time

        # State machine for pushback phases
        if self.pushback_phase == PushbackPhase.WAITING_BRAKE_RELEASE:
            # Check if we've been waiting too long (timeout after 60 seconds)
            if phase_elapsed >= 60.0:
                # Auto-proceed for testing purposes
                self._transition_to_pushing_back()

        elif self.pushback_phase == PushbackPhase.PUSHING_BACK:
            # Calculate pushback progress
            progress = min(1.0, phase_elapsed / self.pushback_duration)

            # Publish position updates
            if self.start_position and self.target_position:
                current_position = self._interpolate_position(progress)
                self._publish_position_update(current_position)

            # Check if complete
            if progress >= 1.0:
                self._transition_to_complete()

        elif self.pushback_phase == PushbackPhase.COMPLETE:
            # Service complete
            self.status = ServiceStatus.COMPLETE
            self._publish_status_update()

        self.last_update_time = current_time

    def release_parking_brake(self) -> None:
        """Signal that parking brake has been released.

        Called by external system when pilot releases parking brake.
        """
        if self.pushback_phase == PushbackPhase.WAITING_BRAKE_RELEASE:
            self._transition_to_pushing_back()

    def _transition_to_pushing_back(self) -> None:
        """Transition to pushing back phase."""
        self.pushback_phase = PushbackPhase.PUSHING_BACK
        self.phase_start_time = time.time()

        # Publish audio message
        self._publish_audio_message_key("MSG_PUSHBACK_STARTING", voice="tug")

        logger.info("Pushback: started pushing back")

    def _transition_to_complete(self) -> None:
        """Transition to complete phase."""
        self.pushback_phase = PushbackPhase.COMPLETE

        # Publish final position
        if self.target_position:
            self._publish_position_update(self.target_position)

        # Publish pushback complete event
        if self.message_queue and self.request:
            self.message_queue.publish(
                Message(
                    sender="pushback_service",
                    recipients=["all"],
                    topic="ground.pushback.complete",
                    data={
                        "aircraft_id": self.request.aircraft_id,
                        "final_position": {
                            "x": self.target_position.x if self.target_position else 0.0,
                            "y": self.target_position.y if self.target_position else 0.0,
                            "z": self.target_position.z if self.target_position else 0.0,
                        },
                        "heading": self.target_heading,
                    },
                )
            )

        # Publish audio message
        self._publish_audio_message_key("MSG_PUSHBACK_COMPLETE", voice="tug")

        logger.info("Pushback: complete")

    def _calculate_target_position(self) -> Vector3:
        """Calculate target position after pushback.

        Returns:
            Target position (Vector3)
        """
        if not self.start_position:
            return Vector3(0.0, 0.0, 0.0)

        # Convert heading to radians (aviation heading: 0° = north, clockwise)
        # But we need to push backward, so add 180°
        backward_heading = (self.target_heading + 180.0) % 360.0
        heading_rad = math.radians(backward_heading)

        # Calculate displacement in meters
        # Approximate conversion: 1 degree latitude ≈ 111,000 meters
        # Longitude varies with latitude, but we'll use a simple approximation
        dlat = (self.pushback_distance * math.cos(heading_rad)) / 111000.0
        dlon = (self.pushback_distance * math.sin(heading_rad)) / (
            111000.0 * math.cos(math.radians(self.start_position.z))
        )

        # Calculate target position
        target = Vector3(
            self.start_position.x + dlon,  # longitude (x)
            self.start_position.y,  # altitude (y)
            self.start_position.z + dlat,  # latitude (z)
        )

        return target

    def _interpolate_position(self, progress: float) -> Vector3:
        """Interpolate position during pushback.

        Args:
            progress: Progress from 0.0 to 1.0

        Returns:
            Current interpolated position
        """
        if not self.start_position or not self.target_position:
            return Vector3(0.0, 0.0, 0.0)

        # Linear interpolation
        return Vector3(
            self.start_position.x + (self.target_position.x - self.start_position.x) * progress,
            self.start_position.y + (self.target_position.y - self.start_position.y) * progress,
            self.start_position.z + (self.target_position.z - self.start_position.z) * progress,
        )

    def _publish_audio_message(self, text: str) -> None:
        """Publish audio message for TTS (legacy method).

        Args:
            text: Message text to speak
        """
        if not self.message_queue or not self.request:
            return

        self.message_queue.publish(
            Message(
                sender="pushback_service",
                recipients=["audio"],
                topic="ground.audio.speak",
                data={
                    "text": text,
                    "voice": "ground",  # Ground crew voice
                    "priority": "normal",
                },
            )
        )

    def _publish_audio_message_key(self, message_key: str, voice: str = "tug") -> None:
        """Publish pre-recorded audio message.

        Args:
            message_key: Message key (e.g., "MSG_PUSHBACK_ACKNOWLEDGED")
            voice: Voice type (tug, refuel, boarding, ops)
        """
        if not self.message_queue or not self.request:
            return

        from airborne.core.messaging import MessagePriority, MessageTopic

        self.message_queue.publish(
            Message(
                sender="pushback_service",
                recipients=["audio"],
                topic=MessageTopic.TTS_SPEAK,
                data={
                    "message_key": message_key,
                    "voice": voice,
                    "interrupt": True,
                },
                priority=MessagePriority.HIGH,
            )
        )

    def _publish_position_update(self, position: Vector3) -> None:
        """Publish aircraft position update.

        Args:
            position: New aircraft position
        """
        if not self.message_queue or not self.request:
            return

        self.message_queue.publish(
            Message(
                sender="pushback_service",
                recipients=["position_tracker", "physics"],
                topic="aircraft.position.update",
                data={
                    "aircraft_id": self.request.aircraft_id,
                    "position": {"x": position.x, "y": position.y, "z": position.z},
                    "heading": self.target_heading,
                },
            )
        )

    def get_progress(self) -> float:
        """Get pushback progress.

        Returns:
            Progress as percentage (0.0 to 1.0)

        Examples:
            >>> service = PushbackService()
            >>> service.pushback_phase = PushbackPhase.PUSHING_BACK
            >>> service.phase_start_time = time.time() - 15.0
            >>> service.pushback_duration = 30.0
            >>> service.get_progress()
            0.75
        """
        if self.status != ServiceStatus.IN_PROGRESS:
            return 0.0 if self.status == ServiceStatus.IDLE else 1.0

        # Calculate progress based on current phase
        if self.pushback_phase == PushbackPhase.WAITING_BRAKE_RELEASE:
            # Progress during wait (0% to 30%)
            # This is indeterminate, so just show 10%
            return 0.1

        elif self.pushback_phase == PushbackPhase.PUSHING_BACK:
            # Progress during pushback (30% to 100%)
            elapsed = time.time() - self.phase_start_time
            pushback_progress = min(1.0, elapsed / self.pushback_duration)
            return 0.3 + 0.7 * pushback_progress

        else:  # COMPLETE
            return 1.0

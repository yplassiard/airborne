"""Boarding and deboarding services for AirBorne ground operations.

This module provides passenger boarding and deboarding services with
realistic timing and audio feedback.
"""

import logging
import time

from airborne.core.messaging import Message, MessageQueue
from airborne.plugins.ground.ground_services import (
    GroundService,
    ServiceRequest,
    ServiceStatus,
    ServiceType,
)

logger = logging.getLogger(__name__)


class BoardingService(GroundService):
    """Passenger boarding service.

    Simulates realistic passenger boarding with timing based on aircraft
    size and passenger count.
    """

    def __init__(self, message_queue: MessageQueue | None = None) -> None:
        """Initialize boarding service."""
        super().__init__(ServiceType.BOARDING, message_queue)
        self.passenger_count: int = 0
        self.passengers_boarded: int = 0
        self.boarding_rate: float = 3.0  # seconds per passenger
        self.last_update_time: float = 0.0
        self.last_progress_announcement: float = 0.0

    def start(self, request: ServiceRequest) -> bool:
        """Start boarding service.

        Args:
            request: Service request with parameters:
                - passenger_count: Number of passengers to board
                - is_jet: True for jet aircraft (slower boarding)
        """
        self.request = request
        self.status = ServiceStatus.IN_PROGRESS
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.last_progress_announcement = 0.0

        params = request.parameters or {}
        self.passenger_count = params.get("passenger_count", 50)
        is_jet = params.get("is_jet", False)

        # Set boarding rate (seconds per passenger)
        self.boarding_rate = 3.0 if is_jet else 1.0  # Faster for GA

        self.estimated_duration = self.passenger_count * self.boarding_rate
        self.passengers_boarded = 0

        self._publish_status_update()
        self._publish_audio_message(f"Boarding started, {self.passenger_count} passengers")

        logger.info(
            "Boarding started: %s, %d passengers, duration=%.1fs",
            request.aircraft_id,
            self.passenger_count,
            self.estimated_duration,
        )

        return True

    def update(self, dt: float) -> None:
        """Update boarding service state."""
        if self.status != ServiceStatus.IN_PROGRESS:
            return

        current_time = time.time()
        time_elapsed = current_time - self.last_update_time

        # Calculate passengers boarded
        passengers_delta = int(time_elapsed / self.boarding_rate)
        if passengers_delta > 0:
            self.passengers_boarded = min(
                self.passengers_boarded + passengers_delta, self.passenger_count
            )
            self.last_update_time = current_time

        # Check for progress announcements (every 25%)
        progress = self.get_progress()
        if progress >= self.last_progress_announcement + 0.25 and progress < 1.0:
            self.last_progress_announcement = int(progress / 0.25) * 0.25
            percent = int(self.last_progress_announcement * 100)
            self._publish_audio_message(f"Boarding {percent}% complete")

        # Check if complete
        if self.passengers_boarded >= self.passenger_count:
            self.status = ServiceStatus.COMPLETE
            self._publish_status_update()
            self._publish_audio_message("Boarding complete, all passengers aboard, doors closed and armed")
            logger.info("Boarding complete: %d passengers", self.passengers_boarded)

    def get_progress(self) -> float:
        """Get boarding progress (0.0 to 1.0)."""
        if self.status != ServiceStatus.IN_PROGRESS or self.passenger_count == 0:
            return 0.0 if self.status == ServiceStatus.IDLE else 1.0
        return min(1.0, self.passengers_boarded / self.passenger_count)

    def _publish_audio_message(self, text: str) -> None:
        """Publish audio message."""
        if not self.message_queue or not self.request:
            return
        self.message_queue.publish(
            Message(
                sender="boarding_service",
                recipients=["audio"],
                topic="ground.audio.speak",
                data={"text": text, "voice": "ground", "priority": "normal"},
            )
        )


class DeboardingService(GroundService):
    """Passenger deboarding service."""

    def __init__(self, message_queue: MessageQueue | None = None) -> None:
        """Initialize deboarding service."""
        super().__init__(ServiceType.DEBOARDING, message_queue)
        self.passenger_count: int = 0
        self.passengers_deboarded: int = 0
        self.deboarding_rate: float = 2.0  # Faster than boarding
        self.last_update_time: float = 0.0

    def start(self, request: ServiceRequest) -> bool:
        """Start deboarding service."""
        self.request = request
        self.status = ServiceStatus.IN_PROGRESS
        self.start_time = time.time()
        self.last_update_time = self.start_time

        params = request.parameters or {}
        self.passenger_count = params.get("passenger_count", 50)
        is_jet = params.get("is_jet", False)

        # Deboarding is faster than boarding
        self.deboarding_rate = 2.0 if is_jet else 0.5

        self.estimated_duration = self.passenger_count * self.deboarding_rate
        self.passengers_deboarded = 0

        self._publish_status_update()
        self._publish_audio_message("Deboarding started")

        logger.info(
            "Deboarding started: %s, %d passengers",
            request.aircraft_id,
            self.passenger_count,
        )

        return True

    def update(self, dt: float) -> None:
        """Update deboarding service state."""
        if self.status != ServiceStatus.IN_PROGRESS:
            return

        current_time = time.time()
        time_elapsed = current_time - self.last_update_time

        # Calculate passengers deboarded
        passengers_delta = int(time_elapsed / self.deboarding_rate)
        if passengers_delta > 0:
            self.passengers_deboarded = min(
                self.passengers_deboarded + passengers_delta, self.passenger_count
            )
            self.last_update_time = current_time

        # Check if complete
        if self.passengers_deboarded >= self.passenger_count:
            self.status = ServiceStatus.COMPLETE
            self._publish_status_update()
            self._publish_audio_message("Deboarding complete, all passengers deplaned")
            logger.info("Deboarding complete: %d passengers", self.passengers_deboarded)

    def get_progress(self) -> float:
        """Get deboarding progress (0.0 to 1.0)."""
        if self.status != ServiceStatus.IN_PROGRESS or self.passenger_count == 0:
            return 0.0 if self.status == ServiceStatus.IDLE else 1.0
        return min(1.0, self.passengers_deboarded / self.passenger_count)

    def _publish_audio_message(self, text: str) -> None:
        """Publish audio message."""
        if not self.message_queue or not self.request:
            return
        self.message_queue.publish(
            Message(
                sender="deboarding_service",
                recipients=["audio"],
                topic="ground.audio.speak",
                data={"text": text, "voice": "ground", "priority": "normal"},
            )
        )

"""Refueling service for AirBorne ground operations.

This module provides aircraft refueling service with realistic timing,
audio feedback, and fuel system integration.

Typical usage:
    from airborne.plugins.ground.services.refueling import RefuelingService

    service = RefuelingService(message_queue)
    request = ServiceRequest(
        service_type=ServiceType.REFUEL,
        aircraft_id="N123AB",
        parking_id="G1",
        timestamp=time.time(),
        parameters={"quantity": 50.0, "is_jet": False}
    )
    service.start(request)
"""

import logging
import random
import time
from enum import Enum

from airborne.core.messaging import Message, MessageQueue
from airborne.plugins.ground.ground_services import (
    GroundService,
    ServiceRequest,
    ServiceStatus,
    ServiceType,
)

logger = logging.getLogger(__name__)


class RefuelingPhase(Enum):
    """Refueling service phases.

    Attributes:
        DISPATCHING: Fuel truck is being dispatched (30-60s delay)
        CONNECTING: Fuel truck connecting hoses
        REFUELING: Actively refueling aircraft
        COMPLETE: Refueling finished

    Examples:
        >>> phase = RefuelingPhase.REFUELING
        >>> phase == RefuelingPhase.COMPLETE
        False
    """

    DISPATCHING = "dispatching"
    CONNECTING = "connecting"
    REFUELING = "refueling"
    COMPLETE = "complete"


class RefuelingService(GroundService):
    """Aircraft refueling service.

    Provides realistic refueling simulation with:
    - Fuel truck dispatch (30-60s delay)
    - Refueling rate based on aircraft type (10 gal/min GA, 100 gal/min jets)
    - Audio feedback at each stage
    - Fuel system integration via messages

    Attributes:
        refueling_phase: Current phase of refueling operation
        truck_dispatch_time: Time for truck to arrive (seconds)
        fuel_to_add: Amount of fuel to add (gallons)
        fuel_added: Amount of fuel added so far (gallons)
        refueling_rate: Gallons per second
        phase_start_time: Time when current phase started
        last_update_time: Time of last update

    Examples:
        >>> service = RefuelingService(message_queue)
        >>> request = ServiceRequest(
        ...     service_type=ServiceType.REFUEL,
        ...     aircraft_id="N123AB",
        ...     parking_id="G1",
        ...     timestamp=time.time(),
        ...     parameters={"quantity": 50.0, "is_jet": False}
        ... )
        >>> service.start(request)
        True
        >>> service.refueling_phase
        <RefuelingPhase.DISPATCHING: 'dispatching'>
    """

    def __init__(self, message_queue: MessageQueue | None = None) -> None:
        """Initialize refueling service.

        Args:
            message_queue: Optional message queue for publishing events
        """
        super().__init__(ServiceType.REFUEL, message_queue)

        # Refueling state
        self.refueling_phase = RefuelingPhase.DISPATCHING
        self.truck_dispatch_time: float = 45.0  # seconds
        self.fuel_to_add: float = 0.0
        self.fuel_added: float = 0.0
        self.refueling_rate: float = 0.0  # gallons per second
        self.phase_start_time: float = 0.0
        self.last_update_time: float = 0.0

    def start(self, request: ServiceRequest) -> bool:
        """Start refueling service.

        Args:
            request: Service request with parameters:
                - quantity: Gallons to add, or -1 for "full tanks"
                - is_jet: True for jet aircraft, False for GA
                - current_fuel: Current fuel quantity (gallons)
                - max_fuel: Maximum fuel capacity (gallons)

        Returns:
            True if service started successfully, False otherwise

        Examples:
            >>> service = RefuelingService()
            >>> request = ServiceRequest(
            ...     service_type=ServiceType.REFUEL,
            ...     aircraft_id="N123AB",
            ...     parking_id="G1",
            ...     timestamp=time.time(),
            ...     parameters={"quantity": 50.0, "is_jet": False}
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
        quantity = params.get("quantity", -1.0)
        is_jet = params.get("is_jet", False)
        current_fuel = params.get("current_fuel", 0.0)
        max_fuel = params.get("max_fuel", 50.0)

        # Calculate fuel to add
        if quantity < 0:  # "Full tanks"
            self.fuel_to_add = max_fuel - current_fuel
        else:
            self.fuel_to_add = min(quantity, max_fuel - current_fuel)

        # Set refueling rate (gallons per second)
        if is_jet:
            self.refueling_rate = 100.0 / 60.0  # 100 gal/min = 1.67 gal/sec
        else:
            self.refueling_rate = 10.0 / 60.0  # 10 gal/min = 0.167 gal/sec

        # Random truck dispatch time (30-60 seconds)
        self.truck_dispatch_time = random.uniform(30.0, 60.0)

        # Calculate total duration
        refueling_time = self.fuel_to_add / self.refueling_rate if self.refueling_rate > 0 else 0
        connection_time = 5.0  # 5 seconds to connect
        self.estimated_duration = self.truck_dispatch_time + connection_time + refueling_time

        # Start in dispatching phase
        self.refueling_phase = RefuelingPhase.DISPATCHING
        self.fuel_added = 0.0

        # Publish status update
        self._publish_status_update()

        # Publish audio message: "Fuel truck dispatched"
        self._publish_audio_message_key("MSG_REFUEL_ACKNOWLEDGED", voice="refuel")

        logger.info(
            "Refueling started: %s, %.1f gallons, rate=%.2f gal/sec, ETA=%.1fs",
            request.aircraft_id,
            self.fuel_to_add,
            self.refueling_rate,
            self.estimated_duration,
        )

        return True

    def update(self, dt: float) -> None:
        """Update refueling service state.

        Args:
            dt: Time since last update (seconds)
        """
        if self.status != ServiceStatus.IN_PROGRESS:
            return

        current_time = time.time()
        phase_elapsed = current_time - self.phase_start_time

        # State machine for refueling phases
        if self.refueling_phase == RefuelingPhase.DISPATCHING:
            # Wait for truck to arrive
            if phase_elapsed >= self.truck_dispatch_time:
                self._transition_to_connecting()

        elif self.refueling_phase == RefuelingPhase.CONNECTING:
            # Wait for connection (5 seconds)
            if phase_elapsed >= 5.0:
                self._transition_to_refueling()

        elif self.refueling_phase == RefuelingPhase.REFUELING:
            # Add fuel over time
            time_delta = current_time - self.last_update_time
            fuel_delta = self.refueling_rate * time_delta

            self.fuel_added += fuel_delta

            # Publish fuel update
            if self.request:
                self._publish_fuel_update(self.fuel_added)

            # Check if complete
            if self.fuel_added >= self.fuel_to_add:
                self._transition_to_complete()

        elif self.refueling_phase == RefuelingPhase.COMPLETE:
            # Service complete
            self.status = ServiceStatus.COMPLETE
            self._publish_status_update()

        self.last_update_time = current_time

    def _transition_to_connecting(self) -> None:
        """Transition to connecting phase."""
        self.refueling_phase = RefuelingPhase.CONNECTING
        self.phase_start_time = time.time()

        # Publish audio message
        self._publish_audio_message_key("MSG_REFUEL_STARTING", voice="refuel")

        logger.info("Refueling: truck arrived, connecting hoses")

    def _transition_to_refueling(self) -> None:
        """Transition to refueling phase."""
        self.refueling_phase = RefuelingPhase.REFUELING
        self.phase_start_time = time.time()

        # Publish audio message
        self._publish_audio_message_key("MSG_REFUEL_IN_PROGRESS", voice="refuel")

        logger.info("Refueling: started pumping fuel")

    def _transition_to_complete(self) -> None:
        """Transition to complete phase."""
        self.refueling_phase = RefuelingPhase.COMPLETE

        # Publish audio message
        self._publish_audio_message_key("MSG_REFUEL_COMPLETE", voice="refuel")

        logger.info("Refueling: complete, %.1f gallons added", self.fuel_added)

    def _publish_audio_message(self, text: str) -> None:
        """Publish audio message for TTS (legacy method).

        Args:
            text: Message text to speak
        """
        if not self.message_queue or not self.request:
            return

        self.message_queue.publish(
            Message(
                sender="refueling_service",
                recipients=["audio"],
                topic="ground.audio.speak",
                data={
                    "text": text,
                    "voice": "ground",  # Ground crew voice
                    "priority": "normal",
                },
            )
        )

    def _publish_audio_message_key(self, message_key: str, voice: str = "refuel") -> None:
        """Publish pre-recorded audio message.

        Args:
            message_key: Message key (e.g., "MSG_REFUEL_ACKNOWLEDGED")
            voice: Voice type (refuel, tug, boarding, ops)
        """
        if not self.message_queue or not self.request:
            return

        from airborne.core.messaging import MessagePriority, MessageTopic

        self.message_queue.publish(
            Message(
                sender="refueling_service",
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

    def _publish_fuel_update(self, fuel_added: float) -> None:
        """Publish fuel quantity update.

        Args:
            fuel_added: Amount of fuel added so far (gallons)
        """
        if not self.message_queue or not self.request:
            return

        self.message_queue.publish(
            Message(
                sender="refueling_service",
                recipients=["fuel_system"],
                topic="fuel.add",
                data={
                    "aircraft_id": self.request.aircraft_id,
                    "quantity": fuel_added,
                    "total_added": fuel_added,
                },
            )
        )

    def get_progress(self) -> float:
        """Get refueling progress.

        Returns:
            Progress as percentage (0.0 to 1.0)

        Examples:
            >>> service = RefuelingService()
            >>> service.fuel_to_add = 100.0
            >>> service.fuel_added = 50.0
            >>> service.refueling_phase = RefuelingPhase.REFUELING
            >>> service.get_progress()
            0.5
        """
        if self.status != ServiceStatus.IN_PROGRESS:
            return 0.0 if self.status == ServiceStatus.IDLE else 1.0

        # Calculate progress based on current phase
        if self.refueling_phase == RefuelingPhase.DISPATCHING:
            # Progress during dispatch (0% to 20%)
            elapsed = time.time() - self.phase_start_time
            return min(0.2, 0.2 * elapsed / self.truck_dispatch_time)

        elif self.refueling_phase == RefuelingPhase.CONNECTING:
            # Progress during connection (20% to 25%)
            return 0.2 + 0.05

        elif self.refueling_phase == RefuelingPhase.REFUELING:
            # Progress during refueling (25% to 100%)
            if self.fuel_to_add > 0:
                fuel_progress = self.fuel_added / self.fuel_to_add
                return 0.25 + 0.75 * min(1.0, fuel_progress)
            return 0.25

        else:  # COMPLETE
            return 1.0

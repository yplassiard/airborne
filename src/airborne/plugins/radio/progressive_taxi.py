"""Progressive taxi system for realistic ATC taxi clearances.

This module implements progressive taxi, where ATC issues taxi clearances
in segments rather than the entire route at once. This is more realistic
and helps prevent runway incursions at complex airports.

Typical usage:
    manager = ProgressiveTaxiManager(message_queue, airport_data)
    manager.issue_initial_clearance(aircraft_id, parking, runway)
    # As aircraft moves, manager issues next segment clearances
"""

import logging
from dataclasses import dataclass

from airborne.core.messaging import Message, MessagePriority, MessageQueue, MessageTopic

logger = logging.getLogger(__name__)


@dataclass
class TaxiSegment:
    """Represents a segment of a taxi route.

    Attributes:
        from_node: Starting taxiway/parking node ID.
        to_node: Ending taxiway/parking node ID.
        taxiway: Taxiway identifier (e.g., "Alpha", "Bravo").
        instruction: ATC instruction for this segment.
        is_runway_crossing: Whether this segment crosses an active runway.
        hold_short: Node ID where aircraft should hold short.
    """

    from_node: str
    to_node: str
    taxiway: str
    instruction: str
    is_runway_crossing: bool = False
    hold_short: str | None = None


@dataclass
class TaxiClearance:
    """Active taxi clearance for an aircraft.

    Attributes:
        aircraft_id: Aircraft identifier.
        segments: List of taxi segments.
        current_segment_index: Index of current segment.
        destination_runway: Destination runway identifier.
        is_complete: Whether clearance is complete (at destination).
    """

    aircraft_id: str
    segments: list[TaxiSegment]
    current_segment_index: int
    destination_runway: str
    is_complete: bool = False


class ProgressiveTaxiManager:
    """Manages progressive taxi clearances for aircraft.

    Issues taxi clearances in segments, monitoring aircraft position
    and issuing next instructions as waypoints are reached.
    """

    def __init__(self, message_queue: MessageQueue) -> None:
        """Initialize progressive taxi manager.

        Args:
            message_queue: Message queue for publishing clearances.
        """
        self.message_queue = message_queue
        self.active_clearances: dict[str, TaxiClearance] = {}

        # Subscribe to position updates
        message_queue.subscribe(MessageTopic.POSITION_UPDATED, self._handle_position_update)

        logger.info("Progressive taxi manager initialized")

    def issue_initial_clearance(
        self,
        aircraft_id: str,
        parking_id: str,
        destination_runway: str,
        taxi_route: list[str] | None = None,
    ) -> None:
        """Issue initial taxi clearance to aircraft.

        Args:
            aircraft_id: Aircraft identifier (e.g., "N123AB").
            parking_id: Current parking position.
            destination_runway: Destination runway (e.g., "31").
            taxi_route: Optional pre-computed taxi route. If None, will generate simple route.
        """
        # Build taxi segments
        segments = self._build_segments(parking_id, destination_runway, taxi_route)

        if not segments:
            logger.warning(
                "No taxi route found for %s from %s to runway %s",
                aircraft_id,
                parking_id,
                destination_runway,
            )
            return

        # Create clearance
        clearance = TaxiClearance(
            aircraft_id=aircraft_id,
            segments=segments,
            current_segment_index=0,
            destination_runway=destination_runway,
        )

        self.active_clearances[aircraft_id] = clearance

        # Issue initial instruction (first segment only)
        self._issue_segment_clearance(clearance, 0)

        logger.info(
            "Initial taxi clearance issued to %s: %d segments to runway %s",
            aircraft_id,
            len(segments),
            destination_runway,
        )

    def _build_segments(
        self,
        parking_id: str,
        destination_runway: str,
        taxi_route: list[str] | None = None,
    ) -> list[TaxiSegment]:
        """Build taxi segments from parking to runway.

        Args:
            parking_id: Starting parking position.
            destination_runway: Destination runway.
            taxi_route: Optional pre-computed route (list of taxiway names).

        Returns:
            List of TaxiSegment objects.
        """
        segments = []

        # If no route provided, create simple default route
        # In a real implementation, this would query the airport database
        if not taxi_route:
            taxi_route = ["Alpha"]  # Default simple route

        # Build segments from route
        # Segment 1: Parking to first taxiway
        segments.append(
            TaxiSegment(
                from_node=parking_id,
                to_node="taxiway_alpha_entry",
                taxiway="Alpha",
                instruction=f"Taxi to runway {destination_runway} via Alpha",
                hold_short=f"runway_{destination_runway}",
            )
        )

        # Additional segments for complex routes
        for i, taxiway in enumerate(taxi_route[1:], start=1):
            prev_taxiway = taxi_route[i - 1]
            segments.append(
                TaxiSegment(
                    from_node=f"taxiway_{prev_taxiway.lower()}_exit",
                    to_node=f"taxiway_{taxiway.lower()}_entry",
                    taxiway=taxiway,
                    instruction=f"Continue taxi via {taxiway}",
                    is_runway_crossing=False,
                )
            )

        # Final segment: Hold short of runway
        segments.append(
            TaxiSegment(
                from_node=f"taxiway_{taxi_route[-1].lower()}_exit",
                to_node=f"runway_{destination_runway}_hold_short",
                taxiway=taxi_route[-1],
                instruction=f"Hold short runway {destination_runway} at {taxi_route[-1]}",
                hold_short=f"runway_{destination_runway}",
            )
        )

        return segments

    def _issue_segment_clearance(self, clearance: TaxiClearance, segment_index: int) -> None:
        """Issue clearance for a specific segment.

        Args:
            clearance: Active taxi clearance.
            segment_index: Index of segment to issue.
        """
        if segment_index >= len(clearance.segments):
            # All segments complete
            self._issue_final_instruction(clearance)
            return

        segment = clearance.segments[segment_index]

        # Publish ATC message
        self.message_queue.publish(
            Message(
                sender="progressive_taxi_manager",
                recipients=["atc_manager", "audio"],
                topic=MessageTopic.ATC_MESSAGE,
                data={
                    "aircraft_id": clearance.aircraft_id,
                    "controller": "ground",
                    "message": segment.instruction,
                    "message_key": self._get_message_key(segment),
                    "hold_short": segment.hold_short,
                    "is_clearance": True,
                },
                priority=MessagePriority.HIGH,
            )
        )

        logger.info(
            "Segment %d/%d issued to %s: %s",
            segment_index + 1,
            len(clearance.segments),
            clearance.aircraft_id,
            segment.instruction,
        )

    def _issue_final_instruction(self, clearance: TaxiClearance) -> None:
        """Issue final instruction to contact tower.

        Args:
            clearance: Active taxi clearance.
        """
        instruction = f"Hold short runway {clearance.destination_runway}, contact tower 118.5"

        self.message_queue.publish(
            Message(
                sender="progressive_taxi_manager",
                recipients=["atc_manager", "audio"],
                topic=MessageTopic.ATC_MESSAGE,
                data={
                    "aircraft_id": clearance.aircraft_id,
                    "controller": "ground",
                    "message": instruction,
                    "message_key": "MSG_GROUND_CONTACT_TOWER",
                    "is_clearance": True,
                },
                priority=MessagePriority.HIGH,
            )
        )

        clearance.is_complete = True

        logger.info("Final instruction issued to %s: %s", clearance.aircraft_id, instruction)

    def _get_message_key(self, segment: TaxiSegment) -> str:
        """Get pre-recorded message key for segment.

        Args:
            segment: Taxi segment.

        Returns:
            Message key for TTS playback.
        """
        if segment.hold_short:
            return "MSG_GROUND_TAXI_HOLD_SHORT"
        elif segment.is_runway_crossing:
            return "MSG_GROUND_CROSS_RUNWAY"
        else:
            return "MSG_GROUND_TAXI_VIA"

    def _handle_position_update(self, message: Message) -> None:
        """Handle aircraft position updates.

        Args:
            message: Position update message.
        """
        aircraft_id = message.data.get("aircraft_id")
        if not aircraft_id or aircraft_id not in self.active_clearances:
            return

        clearance = self.active_clearances[aircraft_id]

        # Check if aircraft reached next waypoint
        current_taxiway = message.data.get("on_taxiway")

        if not current_taxiway:
            return

        # Advance to next segment if on expected taxiway
        current_segment = clearance.segments[clearance.current_segment_index]

        if current_taxiway.lower() in current_segment.taxiway.lower():
            # Check if should advance to next segment
            distance_to_end = message.data.get("distance_to_waypoint", 0.0)

            # Issue next instruction when approaching segment end (within 100m)
            if (
                distance_to_end < 100.0
                and clearance.current_segment_index < len(clearance.segments) - 1
            ):
                clearance.current_segment_index += 1
                self._issue_segment_clearance(clearance, clearance.current_segment_index)

    def cancel_clearance(self, aircraft_id: str) -> None:
        """Cancel active taxi clearance.

        Args:
            aircraft_id: Aircraft identifier.
        """
        if aircraft_id in self.active_clearances:
            del self.active_clearances[aircraft_id]
            logger.info("Taxi clearance cancelled for %s", aircraft_id)

    def get_active_clearance(self, aircraft_id: str) -> TaxiClearance | None:
        """Get active clearance for aircraft.

        Args:
            aircraft_id: Aircraft identifier.

        Returns:
            Active clearance, or None if no clearance exists.
        """
        return self.active_clearances.get(aircraft_id)

    def get_active_aircraft(self) -> list[str]:
        """Get list of aircraft with active clearances.

        Returns:
            List of aircraft IDs.
        """
        return list(self.active_clearances.keys())

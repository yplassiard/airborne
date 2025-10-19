"""Parking assignment management for airport ground operations.

This module provides intelligent parking assignment based on aircraft size,
flight type, and parking availability. It manages parking occupancy and
generates appropriate parking clearances.

Typical usage:
    from airborne.airports.parking_assignment import ParkingAssignmentManager, FlightType
    from airborne.airports.parking import AircraftSizeCategory

    manager = ParkingAssignmentManager(parking_db)
    assignment = manager.request_parking(
        aircraft_size=AircraftSizeCategory.SMALL,
        flight_type=FlightType.GENERAL_AVIATION,
        callsign="N123AB"
    )
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from airborne.airports.parking import (
    AircraftSizeCategory,
    ParkingDatabase,
    ParkingStatus,
    ParkingType,
)

logger = logging.getLogger(__name__)


class FlightType(Enum):
    """Type of flight operation.

    Used to determine appropriate parking assignment preferences.
    """

    GENERAL_AVIATION = "general_aviation"  # Private/GA flights
    COMMERCIAL = "commercial"  # Scheduled airline flights
    CARGO = "cargo"  # Cargo flights
    CHARTER = "charter"  # Charter flights


@dataclass
class ParkingAssignment:
    """A parking assignment for an aircraft.

    Attributes:
        aircraft_callsign: Aircraft callsign (e.g., "N123AB", "UAL123")
        position_id: Assigned parking position ID (e.g., "G1", "R5")
        assigned_time: When the assignment was made
        flight_type: Type of flight operation
        aircraft_size: Size category of aircraft

    Examples:
        >>> assignment = ParkingAssignment(
        ...     aircraft_callsign="N123AB",
        ...     position_id="R1",
        ...     assigned_time=datetime.now(),
        ...     flight_type=FlightType.GENERAL_AVIATION,
        ...     aircraft_size=AircraftSizeCategory.SMALL
        ... )
    """

    aircraft_callsign: str
    position_id: str
    assigned_time: datetime
    flight_type: FlightType
    aircraft_size: AircraftSizeCategory


class ParkingAssignmentManager:
    """Manages parking assignments at an airport.

    Intelligently assigns parking positions based on aircraft characteristics,
    flight type, and parking availability. Tracks occupancy and handles
    parking clearances.

    Attributes:
        parking_db: Parking database for the airport
        assignments: Dictionary of active assignments by callsign

    Examples:
        >>> db = ParkingDatabase("KPAO")
        >>> db.add_parking_position("R1", ParkingType.RAMP, Vector3(0,0,0),
        ...                          AircraftSizeCategory.SMALL, 90.0)
        >>> manager = ParkingAssignmentManager(db)
        >>> assignment = manager.request_parking(
        ...     aircraft_size=AircraftSizeCategory.SMALL,
        ...     flight_type=FlightType.GENERAL_AVIATION,
        ...     callsign="N123AB"
        ... )
        >>> assignment.position_id
        'R1'
    """

    def __init__(self, parking_db: ParkingDatabase) -> None:
        """Initialize parking assignment manager.

        Args:
            parking_db: Parking database for this airport
        """
        self.parking_db = parking_db
        self.assignments: dict[str, ParkingAssignment] = {}
        logger.info("Parking assignment manager initialized for %s", parking_db.airport_icao)

    def request_parking(
        self,
        aircraft_size: AircraftSizeCategory,
        flight_type: FlightType,
        callsign: str,
    ) -> ParkingAssignment | None:
        """Request parking assignment for an aircraft.

        Assigns parking based on aircraft size and flight type preferences:
        - Commercial/Charter flights prefer gates (if available)
        - GA flights prefer ramps/tie-downs
        - Cargo flights prefer stands or ramps
        - Falls back to any available parking if preferred type unavailable

        Args:
            aircraft_size: Size category of aircraft
            flight_type: Type of flight operation
            callsign: Aircraft callsign

        Returns:
            ParkingAssignment if parking available, None if no parking available

        Raises:
            ValueError: If callsign already has an active assignment

        Examples:
            >>> manager = ParkingAssignmentManager(parking_db)
            >>> assignment = manager.request_parking(
            ...     AircraftSizeCategory.SMALL,
            ...     FlightType.GENERAL_AVIATION,
            ...     "N123AB"
            ... )
            >>> assignment.position_id
            'R1'
        """
        # Check if callsign already has assignment
        if callsign in self.assignments:
            raise ValueError(f"Aircraft {callsign} already has parking assignment")

        # Determine preferred parking types based on flight type
        preferred_types = self._get_preferred_parking_types(flight_type, aircraft_size)

        # Try to find parking in order of preference
        parking_position = None
        for parking_type in preferred_types:
            available = self.parking_db.get_available_parking(aircraft_size, parking_type)
            if available:
                parking_position = available[0]  # Take first available
                break

        # If no preferred parking, try any available parking
        if parking_position is None:
            available = self.parking_db.get_available_parking(aircraft_size)
            if available:
                parking_position = available[0]
            else:
                logger.warning(
                    "No parking available for %s (size=%s, type=%s)",
                    callsign,
                    aircraft_size.value,
                    flight_type.value,
                )
                return None

        # Occupy the parking position
        self.parking_db.occupy_parking(parking_position.position_id, callsign)

        # Create assignment
        assignment = ParkingAssignment(
            aircraft_callsign=callsign,
            position_id=parking_position.position_id,
            assigned_time=datetime.now(),
            flight_type=flight_type,
            aircraft_size=aircraft_size,
        )

        self.assignments[callsign] = assignment

        logger.info(
            "Assigned parking %s to %s (size=%s, type=%s)",
            parking_position.position_id,
            callsign,
            aircraft_size.value,
            flight_type.value,
        )

        return assignment

    def release_parking(self, callsign: str) -> None:
        """Release parking assignment for an aircraft.

        Marks the parking position as available and removes the assignment.

        Args:
            callsign: Aircraft callsign

        Raises:
            KeyError: If callsign has no active assignment

        Examples:
            >>> manager.request_parking(AircraftSizeCategory.SMALL,
            ...                         FlightType.GENERAL_AVIATION, "N123AB")
            >>> manager.release_parking("N123AB")
        """
        if callsign not in self.assignments:
            raise KeyError(f"No parking assignment found for {callsign}")

        assignment = self.assignments[callsign]

        # Release the parking position in database
        self.parking_db.release_parking(assignment.position_id)

        # Remove assignment
        del self.assignments[callsign]

        logger.info("Released parking %s for %s", assignment.position_id, callsign)

    def get_parking_status(self, position_id: str) -> ParkingStatus:
        """Get status of a parking position.

        Args:
            position_id: Parking position ID

        Returns:
            Current status of the parking position

        Raises:
            KeyError: If position_id not found

        Examples:
            >>> status = manager.get_parking_status("R1")
            >>> status == ParkingStatus.AVAILABLE
            True
        """
        parking = self.parking_db.get_parking_position(position_id)
        if parking is None:
            raise KeyError(f"Parking position {position_id} not found")

        return parking.status

    def get_assignment(self, callsign: str) -> ParkingAssignment | None:
        """Get parking assignment for an aircraft.

        Args:
            callsign: Aircraft callsign

        Returns:
            ParkingAssignment if exists, None otherwise

        Examples:
            >>> assignment = manager.get_assignment("N123AB")
            >>> assignment.position_id
            'R1'
        """
        return self.assignments.get(callsign)

    def get_all_assignments(self) -> list[ParkingAssignment]:
        """Get all active parking assignments.

        Returns:
            List of all active assignments

        Examples:
            >>> assignments = manager.get_all_assignments()
            >>> len(assignments)
            3
        """
        return list(self.assignments.values())

    def _get_preferred_parking_types(
        self, flight_type: FlightType, aircraft_size: AircraftSizeCategory
    ) -> list[ParkingType]:
        """Determine preferred parking types for flight.

        Args:
            flight_type: Type of flight operation
            aircraft_size: Size category of aircraft

        Returns:
            List of parking types in order of preference

        Examples:
            >>> manager._get_preferred_parking_types(
            ...     FlightType.GENERAL_AVIATION,
            ...     AircraftSizeCategory.SMALL
            ... )
            [ParkingType.RAMP, ParkingType.TIE_DOWN, ParkingType.STAND, ParkingType.GATE]
        """
        if flight_type == FlightType.GENERAL_AVIATION:
            # GA prefers ramps and tie-downs
            if aircraft_size == AircraftSizeCategory.SMALL:
                return [
                    ParkingType.TIE_DOWN,
                    ParkingType.RAMP,
                    ParkingType.STAND,
                    ParkingType.GATE,
                ]
            else:
                return [
                    ParkingType.RAMP,
                    ParkingType.STAND,
                    ParkingType.GATE,
                    ParkingType.TIE_DOWN,
                ]

        elif flight_type == FlightType.COMMERCIAL:
            # Commercial prefers gates
            return [ParkingType.GATE, ParkingType.STAND, ParkingType.RAMP, ParkingType.TIE_DOWN]

        elif flight_type == FlightType.CARGO:
            # Cargo prefers stands and ramps (no jetways needed)
            return [ParkingType.STAND, ParkingType.RAMP, ParkingType.GATE, ParkingType.TIE_DOWN]

        elif flight_type == FlightType.CHARTER:
            # Charter prefers gates but can use stands
            return [ParkingType.GATE, ParkingType.STAND, ParkingType.RAMP, ParkingType.TIE_DOWN]

        # Default fallback
        return [ParkingType.GATE, ParkingType.STAND, ParkingType.RAMP, ParkingType.TIE_DOWN]

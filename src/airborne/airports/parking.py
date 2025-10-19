"""Parking position database for airport ground operations.

This module provides data structures and management for parking positions,
gates, stands, and ramp areas at airports. Supports realistic parking
assignment based on aircraft size and airport facilities.

Typical usage:
    from airborne.airports.parking import ParkingDatabase, ParkingType, AircraftSizeCategory

    db = ParkingDatabase(airport_icao="KPAO")
    db.add_parking_position(
        position_id="R1",
        parking_type=ParkingType.RAMP,
        position=Vector3(-122.0, 2.1, 37.5),
        size_category=AircraftSizeCategory.SMALL,
        heading=90.0
    )

    available = db.get_available_parking(AircraftSizeCategory.SMALL)
"""

import logging
from dataclasses import dataclass, field
from enum import Enum

from airborne.physics.vectors import Vector3

logger = logging.getLogger(__name__)


class ParkingType(Enum):
    """Type of parking position.

    Different parking types offer different services and are used
    by different aircraft categories.
    """

    GATE = "gate"  # Terminal gate with jetway
    STAND = "stand"  # Remote stand (bus required)
    RAMP = "ramp"  # General aviation ramp parking
    TIE_DOWN = "tie_down"  # Tie-down spot for small GA aircraft


class AircraftSizeCategory(Enum):
    """Aircraft size categories for parking assignment.

    Used to match aircraft to appropriate parking positions.
    """

    SMALL = "small"  # Single-engine GA (C172, PA28)
    MEDIUM = "medium"  # Twin-engine GA, regional jets (C340, CRJ)
    LARGE = "large"  # Narrowbody jets (B737, A320)
    XLARGE = "xlarge"  # Widebody jets (B777, A380)


class ParkingStatus(Enum):
    """Status of a parking position."""

    AVAILABLE = "available"
    OCCUPIED = "occupied"
    RESERVED = "reserved"
    OUT_OF_SERVICE = "out_of_service"


@dataclass
class ParkingAmenities:
    """Amenities available at a parking position.

    Attributes:
        fuel_available: Fuel services available at this position
        gpu_available: Ground power unit available
        jetway_available: Jetway/airbridge available
        pushback_required: Pushback tug required to exit
        hangar_available: Hangar storage available
    """

    fuel_available: bool = False
    gpu_available: bool = False
    jetway_available: bool = False
    pushback_required: bool = False
    hangar_available: bool = False


@dataclass
class ParkingPosition:
    """A parking position at an airport.

    Represents a gate, stand, ramp, or tie-down spot where aircraft
    can park. Includes position, orientation, size restrictions, and
    available services.

    Attributes:
        position_id: Unique identifier (e.g., "G1", "R5", "A3")
        parking_type: Type of parking (gate, stand, ramp, tie-down)
        position: Geographic position (x=lon, y=elev, z=lat)
        size_category: Maximum aircraft size that can use this spot
        heading: Parking heading in degrees (0-360)
        amenities: Services available at this position
        status: Current availability status
        occupied_by: Callsign of aircraft currently parked (if occupied)

    Examples:
        >>> pos = ParkingPosition(
        ...     position_id="G1",
        ...     parking_type=ParkingType.GATE,
        ...     position=Vector3(-122.0, 2.1, 37.5),
        ...     size_category=AircraftSizeCategory.LARGE,
        ...     heading=270.0,
        ...     amenities=ParkingAmenities(jetway_available=True, gpu_available=True)
        ... )
        >>> pos.is_available()
        True
    """

    position_id: str
    parking_type: ParkingType
    position: Vector3
    size_category: AircraftSizeCategory
    heading: float
    amenities: ParkingAmenities = field(default_factory=ParkingAmenities)
    status: ParkingStatus = ParkingStatus.AVAILABLE
    occupied_by: str | None = None

    def is_available(self) -> bool:
        """Check if parking position is available.

        Returns:
            True if position is available for assignment
        """
        return self.status == ParkingStatus.AVAILABLE

    def can_accommodate(self, aircraft_size: AircraftSizeCategory) -> bool:
        """Check if position can accommodate an aircraft of given size.

        Args:
            aircraft_size: Size category of aircraft

        Returns:
            True if aircraft can fit in this parking position

        Examples:
            >>> pos = ParkingPosition(
            ...     position_id="G1", parking_type=ParkingType.GATE,
            ...     position=Vector3(0, 0, 0), size_category=AircraftSizeCategory.LARGE,
            ...     heading=0.0
            ... )
            >>> pos.can_accommodate(AircraftSizeCategory.SMALL)
            True
            >>> pos.can_accommodate(AircraftSizeCategory.XLARGE)
            False
        """
        # Map size categories to numeric values for comparison
        size_order = {
            AircraftSizeCategory.SMALL: 1,
            AircraftSizeCategory.MEDIUM: 2,
            AircraftSizeCategory.LARGE: 3,
            AircraftSizeCategory.XLARGE: 4,
        }

        return size_order[aircraft_size] <= size_order[self.size_category]

    def occupy(self, callsign: str) -> None:
        """Mark position as occupied by an aircraft.

        Args:
            callsign: Aircraft callsign

        Raises:
            ValueError: If position is not available
        """
        if not self.is_available():
            raise ValueError(f"Parking position {self.position_id} is not available")

        self.status = ParkingStatus.OCCUPIED
        self.occupied_by = callsign
        logger.info("Parking %s occupied by %s", self.position_id, callsign)

    def release(self) -> None:
        """Release the parking position (make it available).

        Examples:
            >>> pos = ParkingPosition("G1", ParkingType.GATE, Vector3(0,0,0),
            ...                       AircraftSizeCategory.LARGE, 0.0)
            >>> pos.occupy("N123AB")
            >>> pos.release()
            >>> pos.is_available()
            True
        """
        self.status = ParkingStatus.AVAILABLE
        self.occupied_by = None
        logger.info("Parking %s released", self.position_id)


class ParkingDatabase:
    """Database of parking positions at an airport.

    Manages all parking positions (gates, stands, ramps, tie-downs) at
    a single airport. Provides queries for available parking, filtering
    by size and type.

    Attributes:
        airport_icao: ICAO code of the airport
        positions: Dictionary of parking positions by ID

    Examples:
        >>> db = ParkingDatabase("KPAO")
        >>> db.add_parking_position("R1", ParkingType.RAMP, Vector3(0,0,0),
        ...                          AircraftSizeCategory.SMALL, 90.0)
        >>> len(db.get_all_parking())
        1
        >>> available = db.get_available_parking(AircraftSizeCategory.SMALL)
        >>> len(available)
        1
    """

    def __init__(self, airport_icao: str) -> None:
        """Initialize parking database for an airport.

        Args:
            airport_icao: Airport ICAO code (e.g., "KPAO")
        """
        self.airport_icao = airport_icao
        self.positions: dict[str, ParkingPosition] = {}
        logger.info("Parking database initialized for %s", airport_icao)

    def add_parking_position(
        self,
        position_id: str,
        parking_type: ParkingType,
        position: Vector3,
        size_category: AircraftSizeCategory,
        heading: float,
        amenities: ParkingAmenities | None = None,
    ) -> ParkingPosition:
        """Add a parking position to the database.

        Args:
            position_id: Unique identifier
            parking_type: Type of parking
            position: Geographic position
            size_category: Maximum aircraft size
            heading: Parking heading in degrees
            amenities: Available amenities (optional)

        Returns:
            The created ParkingPosition

        Raises:
            ValueError: If position_id already exists
        """
        if position_id in self.positions:
            raise ValueError(f"Parking position {position_id} already exists")

        if amenities is None:
            amenities = ParkingAmenities()

        parking = ParkingPosition(
            position_id=position_id,
            parking_type=parking_type,
            position=position,
            size_category=size_category,
            heading=heading,
            amenities=amenities,
        )

        self.positions[position_id] = parking
        logger.debug(
            "Added parking %s: type=%s, size=%s at (%.6f, %.6f)",
            position_id,
            parking_type.value,
            size_category.value,
            position.x,
            position.z,
        )

        return parking

    def remove_parking_position(self, position_id: str) -> None:
        """Remove a parking position from the database.

        Args:
            position_id: Position identifier to remove

        Raises:
            KeyError: If position_id does not exist
        """
        if position_id not in self.positions:
            raise KeyError(f"Parking position {position_id} not found")

        del self.positions[position_id]
        logger.info("Removed parking %s", position_id)

    def get_parking_position(self, position_id: str) -> ParkingPosition | None:
        """Get a parking position by ID.

        Args:
            position_id: Position identifier

        Returns:
            ParkingPosition if found, None otherwise
        """
        return self.positions.get(position_id)

    def get_all_parking(self) -> list[ParkingPosition]:
        """Get all parking positions.

        Returns:
            List of all parking positions
        """
        return list(self.positions.values())

    def get_available_parking(
        self,
        aircraft_size: AircraftSizeCategory,
        parking_type: ParkingType | None = None,
    ) -> list[ParkingPosition]:
        """Get available parking positions for an aircraft size.

        Args:
            aircraft_size: Required aircraft size
            parking_type: Optional filter by parking type

        Returns:
            List of available parking positions that can accommodate the aircraft

        Examples:
            >>> db = ParkingDatabase("KPAO")
            >>> db.add_parking_position("R1", ParkingType.RAMP, Vector3(0,0,0),
            ...                          AircraftSizeCategory.SMALL, 90.0)
            >>> db.add_parking_position("G1", ParkingType.GATE, Vector3(0,0,0),
            ...                          AircraftSizeCategory.LARGE, 270.0)
            >>> available = db.get_available_parking(AircraftSizeCategory.SMALL,
            ...                                       ParkingType.RAMP)
            >>> len(available)
            1
        """
        available = []

        for parking in self.positions.values():
            # Check if available
            if not parking.is_available():
                continue

            # Check if can accommodate aircraft size
            if not parking.can_accommodate(aircraft_size):
                continue

            # Check parking type filter
            if parking_type is not None and parking.parking_type != parking_type:
                continue

            available.append(parking)

        logger.debug(
            "Found %d available parking positions for size=%s, type=%s",
            len(available),
            aircraft_size.value,
            parking_type.value if parking_type else "any",
        )

        return available

    def get_parking_count(self) -> int:
        """Get total number of parking positions.

        Returns:
            Total parking position count
        """
        return len(self.positions)

    def get_parking_by_type(self, parking_type: ParkingType) -> list[ParkingPosition]:
        """Get all parking positions of a specific type.

        Args:
            parking_type: Type of parking to filter

        Returns:
            List of parking positions of the specified type
        """
        return [p for p in self.positions.values() if p.parking_type == parking_type]

    def occupy_parking(self, position_id: str, callsign: str) -> None:
        """Occupy a parking position.

        Args:
            position_id: Position to occupy
            callsign: Aircraft callsign

        Raises:
            KeyError: If position not found
            ValueError: If position not available
        """
        parking = self.get_parking_position(position_id)
        if parking is None:
            raise KeyError(f"Parking position {position_id} not found")

        parking.occupy(callsign)

    def release_parking(self, position_id: str) -> None:
        """Release a parking position.

        Args:
            position_id: Position to release

        Raises:
            KeyError: If position not found
        """
        parking = self.get_parking_position(position_id)
        if parking is None:
            raise KeyError(f"Parking position {position_id} not found")

        parking.release()

    def clear_all_parking(self) -> None:
        """Remove all parking positions from the database."""
        self.positions.clear()
        logger.info("Cleared all parking positions for %s", self.airport_icao)

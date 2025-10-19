"""Procedural parking position generator for airports.

Generates realistic parking layouts based on airport size and runway configuration.
Automatically creates gates, stands, ramps, and tie-downs appropriate for
each airport category.

Typical usage:
    from airborne.airports.parking_generator import ParkingGenerator
    from airborne.airports.classifier import AirportCategory

    generator = ParkingGenerator()
    parking_db = generator.generate(airport, runways, category)
"""

import logging
import math

from airborne.airports.classifier import AirportCategory
from airborne.airports.database import Airport, Runway
from airborne.airports.parking import (
    AircraftSizeCategory,
    ParkingAmenities,
    ParkingDatabase,
    ParkingType,
)
from airborne.physics.vectors import Vector3

logger = logging.getLogger(__name__)


class ParkingGenerator:
    """Generates parking positions based on airport size and configuration.

    Creates realistic parking layouts for airports of all sizes,
    from small GA fields with tie-downs to major hubs with hundreds
    of gates and stands.

    Examples:
        >>> generator = ParkingGenerator()
        >>> db = generator.generate(airport, runways, AirportCategory.MEDIUM)
        >>> print(f"Generated {db.get_parking_count()} parking positions")
    """

    def __init__(self) -> None:
        """Initialize parking generator."""
        pass

    def generate(
        self, airport: Airport, runways: list[Runway], category: AirportCategory
    ) -> ParkingDatabase:
        """Generate parking positions for an airport.

        Args:
            airport: Airport data
            runways: List of runways
            category: Airport size category

        Returns:
            ParkingDatabase populated with generated parking positions

        Examples:
            >>> db = generator.generate(kpao_airport, kpao_runways, AirportCategory.SMALL)
            >>> tie_downs = db.get_parking_by_type(ParkingType.TIE_DOWN)
            >>> len(tie_downs) > 0
            True
        """
        db = ParkingDatabase(airport.icao)

        # Generate based on category
        if category == AirportCategory.SMALL:
            self._generate_small_airport(db, airport, runways)
        elif category == AirportCategory.MEDIUM:
            self._generate_medium_airport(db, airport, runways)
        elif category == AirportCategory.LARGE:
            self._generate_large_airport(db, airport, runways)
        elif category == AirportCategory.XL:
            self._generate_xl_airport(db, airport, runways)

        logger.info(
            "Generated %d parking positions for %s (%s)",
            db.get_parking_count(),
            airport.icao,
            category.value,
        )

        return db

    def _generate_small_airport(
        self, db: ParkingDatabase, airport: Airport, runways: list[Runway]
    ) -> None:
        """Generate parking for small airport.

        Creates 2-10 tie-down spots along the runway.

        Args:
            db: Parking database to populate
            airport: Airport data
            runways: List of runways
        """
        if not runways:
            logger.warning("No runways for %s, cannot generate parking", airport.icao)
            return

        # Use main runway
        main_runway = runways[0]

        # Place tie-downs parallel to runway, offset to the side
        num_tie_downs = 5
        spacing = 50.0  # meters between tie-downs

        # Get runway centerline position (approximate)
        runway_pos = airport.position

        # Offset to the side (assume 90° from runway heading)
        offset_distance = 100.0  # meters from runway centerline
        offset_heading = (main_runway.le_heading_deg + 90.0) % 360.0

        # Calculate offset position
        offset_x = offset_distance * math.sin(math.radians(offset_heading)) / 111000.0
        offset_z = offset_distance * math.cos(math.radians(offset_heading)) / 111000.0

        base_position = Vector3(runway_pos.x + offset_x, runway_pos.y, runway_pos.z + offset_z)

        # Generate tie-downs along a line parallel to runway
        runway_heading_rad = math.radians(main_runway.le_heading_deg)
        dx_per_spot = spacing * math.sin(runway_heading_rad) / 111000.0
        dz_per_spot = spacing * math.cos(runway_heading_rad) / 111000.0

        for i in range(num_tie_downs):
            position = Vector3(
                base_position.x + dx_per_spot * i,
                base_position.y,
                base_position.z + dz_per_spot * i,
            )

            amenities = ParkingAmenities(fuel_available=True)

            db.add_parking_position(
                position_id=f"T{i + 1}",
                parking_type=ParkingType.TIE_DOWN,
                position=position,
                size_category=AircraftSizeCategory.SMALL,
                heading=main_runway.le_heading_deg,
                amenities=amenities,
            )

        logger.debug(
            "Generated %d tie-down spots for small airport %s",
            num_tie_downs,
            airport.icao,
        )

    def _generate_medium_airport(
        self, db: ParkingDatabase, airport: Airport, runways: list[Runway]
    ) -> None:
        """Generate parking for medium airport.

        Creates 5-20 ramp positions in organized rows.

        Args:
            db: Parking database to populate
            airport: Airport data
            runways: List of runways
        """
        if not runways:
            logger.warning("No runways for %s, cannot generate parking", airport.icao)
            return

        main_runway = runways[0]

        # Create apron with ramp parking in rows
        num_ramps = 12
        ramps_per_row = 4
        spacing_lateral = 60.0  # meters between spots in a row
        spacing_rows = 80.0  # meters between rows

        # Position apron area offset from runway
        offset_distance = 150.0  # meters from runway
        offset_heading = (main_runway.le_heading_deg + 90.0) % 360.0

        offset_x = offset_distance * math.sin(math.radians(offset_heading)) / 111000.0
        offset_z = offset_distance * math.cos(math.radians(offset_heading)) / 111000.0

        base_position = Vector3(
            airport.position.x + offset_x,
            airport.position.y,
            airport.position.z + offset_z,
        )

        # Create rows of parking
        row_count = 0
        for i in range(num_ramps):
            row = i // ramps_per_row
            col = i % ramps_per_row

            # Calculate position in grid
            runway_heading_rad = math.radians(main_runway.le_heading_deg)

            # Lateral offset (along runway direction)
            lateral_offset = col * spacing_lateral
            dx_lateral = lateral_offset * math.sin(runway_heading_rad) / 111000.0
            dz_lateral = lateral_offset * math.cos(runway_heading_rad) / 111000.0

            # Row offset (perpendicular to runway)
            row_offset = row * spacing_rows
            row_heading_rad = math.radians(offset_heading)
            dx_row = row_offset * math.sin(row_heading_rad) / 111000.0
            dz_row = row_offset * math.cos(row_heading_rad) / 111000.0

            position = Vector3(
                base_position.x + dx_lateral + dx_row,
                base_position.y,
                base_position.z + dz_lateral + dz_row,
            )

            # Parking faces perpendicular to runway (into apron)
            parking_heading = (main_runway.le_heading_deg + 180.0) % 360.0

            amenities = ParkingAmenities(fuel_available=True, gpu_available=True)

            db.add_parking_position(
                position_id=f"R{i + 1}",
                parking_type=ParkingType.RAMP,
                position=position,
                size_category=AircraftSizeCategory.MEDIUM,
                heading=parking_heading,
                amenities=amenities,
            )

            row_count = max(row_count, row + 1)

        logger.debug(
            "Generated %d ramp positions in %d rows for medium airport %s",
            num_ramps,
            row_count,
            airport.icao,
        )

    def _generate_large_airport(
        self, db: ParkingDatabase, airport: Airport, runways: list[Runway]
    ) -> None:
        """Generate parking for large airport.

        Creates 10-30 gates plus remote stands.

        Args:
            db: Parking database to populate
            airport: Airport data
            runways: List of runways
        """
        if not runways:
            logger.warning("No runways for %s, cannot generate parking", airport.icao)
            return

        main_runway = runways[0]

        # Terminal gates
        num_gates = 15
        gate_spacing = 80.0  # meters between gates

        # Position terminal area
        terminal_distance = 200.0  # meters from runway
        terminal_heading = (main_runway.le_heading_deg + 90.0) % 360.0

        offset_x = terminal_distance * math.sin(math.radians(terminal_heading)) / 111000.0
        offset_z = terminal_distance * math.cos(math.radians(terminal_heading)) / 111000.0

        terminal_position = Vector3(
            airport.position.x + offset_x,
            airport.position.y,
            airport.position.z + offset_z,
        )

        # Generate gates along terminal
        runway_heading_rad = math.radians(main_runway.le_heading_deg)

        for i in range(num_gates):
            lateral_offset = i * gate_spacing
            dx = lateral_offset * math.sin(runway_heading_rad) / 111000.0
            dz = lateral_offset * math.cos(runway_heading_rad) / 111000.0

            position = Vector3(
                terminal_position.x + dx, terminal_position.y, terminal_position.z + dz
            )

            # Gates face toward terminal (perpendicular to runway alignment)
            gate_heading = (main_runway.le_heading_deg + 180.0) % 360.0

            amenities = ParkingAmenities(
                jetway_available=True,
                gpu_available=True,
                pushback_required=True,
            )

            db.add_parking_position(
                position_id=f"G{i + 1}",
                parking_type=ParkingType.GATE,
                position=position,
                size_category=AircraftSizeCategory.LARGE,
                heading=gate_heading,
                amenities=amenities,
            )

        # Remote stands for overflow
        num_stands = 8
        stand_spacing = 100.0  # meters between stands

        # Position stands further from terminal
        stand_distance = terminal_distance + 150.0
        stand_offset_x = stand_distance * math.sin(math.radians(terminal_heading)) / 111000.0
        stand_offset_z = stand_distance * math.cos(math.radians(terminal_heading)) / 111000.0

        stand_base = Vector3(
            airport.position.x + stand_offset_x,
            airport.position.y,
            airport.position.z + stand_offset_z,
        )

        for i in range(num_stands):
            lateral_offset = i * stand_spacing
            dx = lateral_offset * math.sin(runway_heading_rad) / 111000.0
            dz = lateral_offset * math.cos(runway_heading_rad) / 111000.0

            position = Vector3(stand_base.x + dx, stand_base.y, stand_base.z + dz)

            stand_heading = (main_runway.le_heading_deg + 180.0) % 360.0

            amenities = ParkingAmenities(
                gpu_available=True,
                pushback_required=False,  # Remote stands don't need pushback
            )

            db.add_parking_position(
                position_id=f"S{i + 1}",
                parking_type=ParkingType.STAND,
                position=position,
                size_category=AircraftSizeCategory.LARGE,
                heading=stand_heading,
                amenities=amenities,
            )

        logger.debug(
            "Generated %d gates and %d stands for large airport %s",
            num_gates,
            num_stands,
            airport.icao,
        )

    def _generate_xl_airport(
        self, db: ParkingDatabase, airport: Airport, runways: list[Runway]
    ) -> None:
        """Generate parking for extra large airport (major hub).

        Creates 30-80 gates, multiple remote stands, and cargo areas.

        Args:
            db: Parking database to populate
            airport: Airport data
            runways: List of runways
        """
        if not runways:
            logger.warning("No runways for %s, cannot generate parking", airport.icao)
            return

        main_runway = runways[0]

        # Multiple terminal areas
        num_terminals = 3
        gates_per_terminal = 15
        gate_spacing = 80.0

        # Base terminal position
        terminal_distance = 300.0
        terminal_heading = (main_runway.le_heading_deg + 90.0) % 360.0

        offset_x = terminal_distance * math.sin(math.radians(terminal_heading)) / 111000.0
        offset_z = terminal_distance * math.cos(math.radians(terminal_heading)) / 111000.0

        base_terminal = Vector3(
            airport.position.x + offset_x,
            airport.position.y,
            airport.position.z + offset_z,
        )

        runway_heading_rad = math.radians(main_runway.le_heading_deg)

        gate_counter = 1

        # Generate terminals
        for term in range(num_terminals):
            # Offset each terminal
            terminal_offset = term * gates_per_terminal * gate_spacing * 1.2
            dx_term = terminal_offset * math.sin(runway_heading_rad) / 111000.0
            dz_term = terminal_offset * math.cos(runway_heading_rad) / 111000.0

            terminal_pos = Vector3(
                base_terminal.x + dx_term, base_terminal.y, base_terminal.z + dz_term
            )

            # Generate gates for this terminal
            for i in range(gates_per_terminal):
                lateral_offset = i * gate_spacing
                dx = lateral_offset * math.sin(runway_heading_rad) / 111000.0
                dz = lateral_offset * math.cos(runway_heading_rad) / 111000.0

                position = Vector3(terminal_pos.x + dx, terminal_pos.y, terminal_pos.z + dz)

                gate_heading = (main_runway.le_heading_deg + 180.0) % 360.0

                # Mix of large and xlarge gates (every 3rd gate can handle widebody)
                size_cat = (
                    AircraftSizeCategory.XLARGE
                    if i % 3 == 0
                    else AircraftSizeCategory.LARGE
                )

                amenities = ParkingAmenities(
                    jetway_available=True,
                    gpu_available=True,
                    pushback_required=True,
                )

                db.add_parking_position(
                    position_id=f"G{gate_counter}",
                    parking_type=ParkingType.GATE,
                    position=position,
                    size_category=size_cat,
                    heading=gate_heading,
                    amenities=amenities,
                )

                gate_counter += 1

        # Remote stands (for overflow and cargo)
        num_stands = 20
        stand_spacing = 120.0

        stand_distance = terminal_distance + 200.0
        stand_offset_x = stand_distance * math.sin(math.radians(terminal_heading)) / 111000.0
        stand_offset_z = stand_distance * math.cos(math.radians(terminal_heading)) / 111000.0

        stand_base = Vector3(
            airport.position.x + stand_offset_x,
            airport.position.y,
            airport.position.z + stand_offset_z,
        )

        for i in range(num_stands):
            lateral_offset = i * stand_spacing
            dx = lateral_offset * math.sin(runway_heading_rad) / 111000.0
            dz = lateral_offset * math.cos(runway_heading_rad) / 111000.0

            position = Vector3(stand_base.x + dx, stand_base.y, stand_base.z + dz)

            stand_heading = (main_runway.le_heading_deg + 180.0) % 360.0

            # Mix of sizes for stands
            size_cat = (
                AircraftSizeCategory.XLARGE
                if i % 4 == 0
                else AircraftSizeCategory.LARGE
            )

            amenities = ParkingAmenities(gpu_available=True, pushback_required=False)

            db.add_parking_position(
                position_id=f"S{i + 1}",
                parking_type=ParkingType.STAND,
                position=position,
                size_category=size_cat,
                heading=stand_heading,
                amenities=amenities,
            )

        logger.debug(
            "Generated %d gates and %d stands for XL airport %s",
            gate_counter - 1,
            num_stands,
            airport.icao,
        )

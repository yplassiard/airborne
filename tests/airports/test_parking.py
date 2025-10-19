"""Unit tests for parking position database."""

import pytest

from airborne.airports.parking import (
    AircraftSizeCategory,
    ParkingAmenities,
    ParkingDatabase,
    ParkingPosition,
    ParkingStatus,
    ParkingType,
)
from airborne.physics.vectors import Vector3


class TestParkingAmenities:
    """Test ParkingAmenities dataclass."""

    def test_default_amenities(self) -> None:
        """Test default amenities are all False."""
        amenities = ParkingAmenities()
        assert amenities.fuel_available is False
        assert amenities.gpu_available is False
        assert amenities.jetway_available is False
        assert amenities.pushback_required is False
        assert amenities.hangar_available is False

    def test_custom_amenities(self) -> None:
        """Test creating amenities with custom values."""
        amenities = ParkingAmenities(fuel_available=True, jetway_available=True, gpu_available=True)
        assert amenities.fuel_available is True
        assert amenities.jetway_available is True
        assert amenities.gpu_available is True
        assert amenities.pushback_required is False


class TestParkingPosition:
    """Test ParkingPosition class."""

    def test_create_parking_position(self) -> None:
        """Test creating a parking position."""
        pos = ParkingPosition(
            position_id="G1",
            parking_type=ParkingType.GATE,
            position=Vector3(-122.0, 2.1, 37.5),
            size_category=AircraftSizeCategory.LARGE,
            heading=270.0,
        )

        assert pos.position_id == "G1"
        assert pos.parking_type == ParkingType.GATE
        assert pos.size_category == AircraftSizeCategory.LARGE
        assert pos.heading == 270.0
        assert pos.status == ParkingStatus.AVAILABLE
        assert pos.occupied_by is None

    def test_is_available(self) -> None:
        """Test checking if position is available."""
        pos = ParkingPosition(
            position_id="R1",
            parking_type=ParkingType.RAMP,
            position=Vector3(0, 0, 0),
            size_category=AircraftSizeCategory.SMALL,
            heading=90.0,
        )

        assert pos.is_available() is True

        pos.status = ParkingStatus.OCCUPIED
        assert pos.is_available() is False

        pos.status = ParkingStatus.RESERVED
        assert pos.is_available() is False

        pos.status = ParkingStatus.OUT_OF_SERVICE
        assert pos.is_available() is False

    def test_can_accommodate_smaller_aircraft(self) -> None:
        """Test that large parking can accommodate smaller aircraft."""
        pos = ParkingPosition(
            position_id="G1",
            parking_type=ParkingType.GATE,
            position=Vector3(0, 0, 0),
            size_category=AircraftSizeCategory.LARGE,
            heading=0.0,
        )

        # Large parking can accommodate small, medium, and large
        assert pos.can_accommodate(AircraftSizeCategory.SMALL) is True
        assert pos.can_accommodate(AircraftSizeCategory.MEDIUM) is True
        assert pos.can_accommodate(AircraftSizeCategory.LARGE) is True

        # But not extra large
        assert pos.can_accommodate(AircraftSizeCategory.XLARGE) is False

    def test_can_accommodate_same_size(self) -> None:
        """Test that parking can accommodate same size aircraft."""
        pos = ParkingPosition(
            position_id="R1",
            parking_type=ParkingType.RAMP,
            position=Vector3(0, 0, 0),
            size_category=AircraftSizeCategory.SMALL,
            heading=0.0,
        )

        assert pos.can_accommodate(AircraftSizeCategory.SMALL) is True
        assert pos.can_accommodate(AircraftSizeCategory.MEDIUM) is False

    def test_occupy_available_position(self) -> None:
        """Test occupying an available parking position."""
        pos = ParkingPosition(
            position_id="G1",
            parking_type=ParkingType.GATE,
            position=Vector3(0, 0, 0),
            size_category=AircraftSizeCategory.LARGE,
            heading=0.0,
        )

        pos.occupy("N123AB")

        assert pos.status == ParkingStatus.OCCUPIED
        assert pos.occupied_by == "N123AB"
        assert pos.is_available() is False

    def test_occupy_unavailable_position_raises_error(self) -> None:
        """Test that occupying an unavailable position raises ValueError."""
        pos = ParkingPosition(
            position_id="G1",
            parking_type=ParkingType.GATE,
            position=Vector3(0, 0, 0),
            size_category=AircraftSizeCategory.LARGE,
            heading=0.0,
            status=ParkingStatus.OCCUPIED,
        )

        with pytest.raises(ValueError, match="not available"):
            pos.occupy("N456CD")

    def test_release_position(self) -> None:
        """Test releasing a parking position."""
        pos = ParkingPosition(
            position_id="G1",
            parking_type=ParkingType.GATE,
            position=Vector3(0, 0, 0),
            size_category=AircraftSizeCategory.LARGE,
            heading=0.0,
        )

        pos.occupy("N123AB")
        assert pos.is_available() is False

        pos.release()
        assert pos.status == ParkingStatus.AVAILABLE
        assert pos.occupied_by is None
        assert pos.is_available() is True


class TestParkingDatabase:
    """Test ParkingDatabase class."""

    def test_create_database(self) -> None:
        """Test creating a parking database."""
        db = ParkingDatabase("KPAO")

        assert db.airport_icao == "KPAO"
        assert len(db.positions) == 0

    def test_add_parking_position(self) -> None:
        """Test adding a parking position."""
        db = ParkingDatabase("KPAO")

        pos = db.add_parking_position(
            position_id="R1",
            parking_type=ParkingType.RAMP,
            position=Vector3(-122.0, 2.1, 37.5),
            size_category=AircraftSizeCategory.SMALL,
            heading=90.0,
        )

        assert pos.position_id == "R1"
        assert db.get_parking_count() == 1
        assert db.get_parking_position("R1") == pos

    def test_add_duplicate_position_raises_error(self) -> None:
        """Test that adding duplicate position ID raises ValueError."""
        db = ParkingDatabase("KPAO")

        db.add_parking_position(
            position_id="R1",
            parking_type=ParkingType.RAMP,
            position=Vector3(0, 0, 0),
            size_category=AircraftSizeCategory.SMALL,
            heading=0.0,
        )

        with pytest.raises(ValueError, match="already exists"):
            db.add_parking_position(
                position_id="R1",
                parking_type=ParkingType.GATE,
                position=Vector3(0, 0, 0),
                size_category=AircraftSizeCategory.LARGE,
                heading=0.0,
            )

    def test_add_parking_with_amenities(self) -> None:
        """Test adding parking position with amenities."""
        db = ParkingDatabase("KSFO")

        amenities = ParkingAmenities(jetway_available=True, gpu_available=True)

        pos = db.add_parking_position(
            position_id="G1",
            parking_type=ParkingType.GATE,
            position=Vector3(0, 0, 0),
            size_category=AircraftSizeCategory.LARGE,
            heading=270.0,
            amenities=amenities,
        )

        assert pos.amenities.jetway_available is True
        assert pos.amenities.gpu_available is True

    def test_remove_parking_position(self) -> None:
        """Test removing a parking position."""
        db = ParkingDatabase("KPAO")

        db.add_parking_position(
            position_id="R1",
            parking_type=ParkingType.RAMP,
            position=Vector3(0, 0, 0),
            size_category=AircraftSizeCategory.SMALL,
            heading=0.0,
        )

        assert db.get_parking_count() == 1

        db.remove_parking_position("R1")

        assert db.get_parking_count() == 0
        assert db.get_parking_position("R1") is None

    def test_remove_nonexistent_position_raises_error(self) -> None:
        """Test that removing nonexistent position raises KeyError."""
        db = ParkingDatabase("KPAO")

        with pytest.raises(KeyError, match="not found"):
            db.remove_parking_position("NONEXISTENT")

    def test_get_all_parking(self) -> None:
        """Test getting all parking positions."""
        db = ParkingDatabase("KPAO")

        db.add_parking_position(
            "R1", ParkingType.RAMP, Vector3(0, 0, 0), AircraftSizeCategory.SMALL, 0.0
        )
        db.add_parking_position(
            "R2", ParkingType.RAMP, Vector3(0, 0, 0), AircraftSizeCategory.SMALL, 0.0
        )
        db.add_parking_position(
            "G1", ParkingType.GATE, Vector3(0, 0, 0), AircraftSizeCategory.LARGE, 0.0
        )

        all_parking = db.get_all_parking()
        assert len(all_parking) == 3

    def test_get_available_parking_by_size(self) -> None:
        """Test getting available parking filtered by aircraft size."""
        db = ParkingDatabase("KPAO")

        # Add small parking
        db.add_parking_position(
            "R1", ParkingType.RAMP, Vector3(0, 0, 0), AircraftSizeCategory.SMALL, 0.0
        )

        # Add large parking
        db.add_parking_position(
            "G1", ParkingType.GATE, Vector3(0, 0, 0), AircraftSizeCategory.LARGE, 0.0
        )

        # Small aircraft can use both
        available_small = db.get_available_parking(AircraftSizeCategory.SMALL)
        assert len(available_small) == 2

        # Large aircraft can only use large parking
        available_large = db.get_available_parking(AircraftSizeCategory.LARGE)
        assert len(available_large) == 1
        assert available_large[0].position_id == "G1"

    def test_get_available_parking_by_type(self) -> None:
        """Test getting available parking filtered by parking type."""
        db = ParkingDatabase("KPAO")

        db.add_parking_position(
            "R1", ParkingType.RAMP, Vector3(0, 0, 0), AircraftSizeCategory.SMALL, 0.0
        )
        db.add_parking_position(
            "R2", ParkingType.RAMP, Vector3(0, 0, 0), AircraftSizeCategory.SMALL, 0.0
        )
        db.add_parking_position(
            "G1", ParkingType.GATE, Vector3(0, 0, 0), AircraftSizeCategory.LARGE, 0.0
        )

        # Get only ramps
        available_ramps = db.get_available_parking(AircraftSizeCategory.SMALL, ParkingType.RAMP)
        assert len(available_ramps) == 2

        # Get only gates
        available_gates = db.get_available_parking(AircraftSizeCategory.SMALL, ParkingType.GATE)
        assert len(available_gates) == 1

    def test_get_available_excludes_occupied(self) -> None:
        """Test that get_available_parking excludes occupied positions."""
        db = ParkingDatabase("KPAO")

        db.add_parking_position(
            "R1", ParkingType.RAMP, Vector3(0, 0, 0), AircraftSizeCategory.SMALL, 0.0
        )
        db.add_parking_position(
            "R2", ParkingType.RAMP, Vector3(0, 0, 0), AircraftSizeCategory.SMALL, 0.0
        )

        # Both available initially
        available = db.get_available_parking(AircraftSizeCategory.SMALL)
        assert len(available) == 2

        # Occupy one
        db.occupy_parking("R1", "N123AB")

        # Only one available now
        available = db.get_available_parking(AircraftSizeCategory.SMALL)
        assert len(available) == 1
        assert available[0].position_id == "R2"

    def test_get_parking_by_type(self) -> None:
        """Test getting parking positions by type."""
        db = ParkingDatabase("KPAO")

        db.add_parking_position(
            "R1", ParkingType.RAMP, Vector3(0, 0, 0), AircraftSizeCategory.SMALL, 0.0
        )
        db.add_parking_position(
            "R2", ParkingType.RAMP, Vector3(0, 0, 0), AircraftSizeCategory.SMALL, 0.0
        )
        db.add_parking_position(
            "G1", ParkingType.GATE, Vector3(0, 0, 0), AircraftSizeCategory.LARGE, 0.0
        )
        db.add_parking_position(
            "T1", ParkingType.TIE_DOWN, Vector3(0, 0, 0), AircraftSizeCategory.SMALL, 0.0
        )

        ramps = db.get_parking_by_type(ParkingType.RAMP)
        assert len(ramps) == 2

        gates = db.get_parking_by_type(ParkingType.GATE)
        assert len(gates) == 1

        tie_downs = db.get_parking_by_type(ParkingType.TIE_DOWN)
        assert len(tie_downs) == 1

    def test_occupy_parking(self) -> None:
        """Test occupying a parking position via database method."""
        db = ParkingDatabase("KPAO")

        db.add_parking_position(
            "R1", ParkingType.RAMP, Vector3(0, 0, 0), AircraftSizeCategory.SMALL, 0.0
        )

        db.occupy_parking("R1", "N123AB")

        pos = db.get_parking_position("R1")
        assert pos is not None
        assert pos.status == ParkingStatus.OCCUPIED
        assert pos.occupied_by == "N123AB"

    def test_occupy_nonexistent_parking_raises_error(self) -> None:
        """Test that occupying nonexistent parking raises KeyError."""
        db = ParkingDatabase("KPAO")

        with pytest.raises(KeyError, match="not found"):
            db.occupy_parking("NONEXISTENT", "N123AB")

    def test_release_parking(self) -> None:
        """Test releasing a parking position via database method."""
        db = ParkingDatabase("KPAO")

        db.add_parking_position(
            "R1", ParkingType.RAMP, Vector3(0, 0, 0), AircraftSizeCategory.SMALL, 0.0
        )

        db.occupy_parking("R1", "N123AB")
        db.release_parking("R1")

        pos = db.get_parking_position("R1")
        assert pos is not None
        assert pos.status == ParkingStatus.AVAILABLE
        assert pos.occupied_by is None

    def test_release_nonexistent_parking_raises_error(self) -> None:
        """Test that releasing nonexistent parking raises KeyError."""
        db = ParkingDatabase("KPAO")

        with pytest.raises(KeyError, match="not found"):
            db.release_parking("NONEXISTENT")

    def test_clear_all_parking(self) -> None:
        """Test clearing all parking positions."""
        db = ParkingDatabase("KPAO")

        db.add_parking_position(
            "R1", ParkingType.RAMP, Vector3(0, 0, 0), AircraftSizeCategory.SMALL, 0.0
        )
        db.add_parking_position(
            "R2", ParkingType.RAMP, Vector3(0, 0, 0), AircraftSizeCategory.SMALL, 0.0
        )

        assert db.get_parking_count() == 2

        db.clear_all_parking()

        assert db.get_parking_count() == 0


class TestParkingIntegration:
    """Integration tests for parking system."""

    def test_typical_small_airport_workflow(self) -> None:
        """Test typical workflow at a small airport."""
        # Create database for small airport
        db = ParkingDatabase("KPAO")

        # Add some tie-down spots
        for i in range(1, 6):
            db.add_parking_position(
                position_id=f"T{i}",
                parking_type=ParkingType.TIE_DOWN,
                position=Vector3(-122.0 + i * 0.0001, 2.1, 37.5),
                size_category=AircraftSizeCategory.SMALL,
                heading=90.0,
                amenities=ParkingAmenities(fuel_available=True),
            )

        # Add a few ramp spots
        for i in range(1, 4):
            db.add_parking_position(
                position_id=f"R{i}",
                parking_type=ParkingType.RAMP,
                position=Vector3(-122.0 + i * 0.0001, 2.1, 37.5),
                size_category=AircraftSizeCategory.MEDIUM,
                heading=270.0,
                amenities=ParkingAmenities(fuel_available=True, gpu_available=True),
            )

        # C172 arrives, needs parking
        available = db.get_available_parking(AircraftSizeCategory.SMALL)
        assert len(available) == 8  # 5 tie-downs + 3 ramps

        # Prefer tie-down for small aircraft
        tie_downs = db.get_available_parking(AircraftSizeCategory.SMALL, ParkingType.TIE_DOWN)
        assert len(tie_downs) == 5

        # Park the C172
        parking = tie_downs[0]
        db.occupy_parking(parking.position_id, "N123AB")

        # Now only 7 spots available
        available = db.get_available_parking(AircraftSizeCategory.SMALL)
        assert len(available) == 7

    def test_typical_large_airport_workflow(self) -> None:
        """Test typical workflow at a large airport."""
        # Create database for large airport
        db = ParkingDatabase("KSFO")

        # Add terminal gates
        for i in range(1, 11):
            db.add_parking_position(
                position_id=f"G{i}",
                parking_type=ParkingType.GATE,
                position=Vector3(-122.4 + i * 0.0001, 4.0, 37.6),
                size_category=AircraftSizeCategory.LARGE,
                heading=180.0,
                amenities=ParkingAmenities(
                    jetway_available=True, gpu_available=True, pushback_required=True
                ),
            )

        # Add remote stands
        for i in range(1, 6):
            db.add_parking_position(
                position_id=f"S{i}",
                parking_type=ParkingType.STAND,
                position=Vector3(-122.4 + i * 0.0001, 4.0, 37.6),
                size_category=AircraftSizeCategory.XLARGE,
                heading=90.0,
                amenities=ParkingAmenities(gpu_available=True, pushback_required=True),
            )

        # B737 arrives, needs gate
        gates = db.get_available_parking(AircraftSizeCategory.LARGE, ParkingType.GATE)
        assert len(gates) == 10

        # Assign gate
        gate = gates[0]
        assert gate.amenities.jetway_available is True
        db.occupy_parking(gate.position_id, "UAL123")

        # A380 arrives, needs large stand
        stands = db.get_available_parking(AircraftSizeCategory.XLARGE, ParkingType.STAND)
        assert len(stands) == 5

        stand = stands[0]
        db.occupy_parking(stand.position_id, "BAW456")

        # Now check availability
        available_gates = db.get_available_parking(AircraftSizeCategory.LARGE, ParkingType.GATE)
        assert len(available_gates) == 9

        available_stands = db.get_available_parking(AircraftSizeCategory.XLARGE, ParkingType.STAND)
        assert len(available_stands) == 4

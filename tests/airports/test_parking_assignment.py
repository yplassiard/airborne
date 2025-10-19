"""Unit tests for parking assignment system."""

import pytest

from airborne.airports.parking import (
    AircraftSizeCategory,
    ParkingAmenities,
    ParkingDatabase,
    ParkingStatus,
    ParkingType,
)
from airborne.airports.parking_assignment import (
    FlightType,
    ParkingAssignmentManager,
)
from airborne.physics.vectors import Vector3


@pytest.fixture
def parking_db() -> ParkingDatabase:
    """Create a test parking database."""
    db = ParkingDatabase("KTEST")

    # Add variety of parking types
    # 2 tie-downs (small)
    db.add_parking_position(
        position_id="T1",
        parking_type=ParkingType.TIE_DOWN,
        position=Vector3(-122.0, 10.0, 37.5),
        size_category=AircraftSizeCategory.SMALL,
        heading=90.0,
        amenities=ParkingAmenities(fuel_available=True),
    )
    db.add_parking_position(
        position_id="T2",
        parking_type=ParkingType.TIE_DOWN,
        position=Vector3(-122.001, 10.0, 37.5),
        size_category=AircraftSizeCategory.SMALL,
        heading=90.0,
        amenities=ParkingAmenities(fuel_available=True),
    )

    # 2 ramps (medium)
    db.add_parking_position(
        position_id="R1",
        parking_type=ParkingType.RAMP,
        position=Vector3(-122.002, 10.0, 37.5),
        size_category=AircraftSizeCategory.MEDIUM,
        heading=90.0,
        amenities=ParkingAmenities(fuel_available=True, gpu_available=True),
    )
    db.add_parking_position(
        position_id="R2",
        parking_type=ParkingType.RAMP,
        position=Vector3(-122.003, 10.0, 37.5),
        size_category=AircraftSizeCategory.MEDIUM,
        heading=90.0,
        amenities=ParkingAmenities(fuel_available=True, gpu_available=True),
    )

    # 2 gates (large)
    db.add_parking_position(
        position_id="G1",
        parking_type=ParkingType.GATE,
        position=Vector3(-122.004, 10.0, 37.5),
        size_category=AircraftSizeCategory.LARGE,
        heading=270.0,
        amenities=ParkingAmenities(
            jetway_available=True, gpu_available=True, pushback_required=True
        ),
    )
    db.add_parking_position(
        position_id="G2",
        parking_type=ParkingType.GATE,
        position=Vector3(-122.005, 10.0, 37.5),
        size_category=AircraftSizeCategory.LARGE,
        heading=270.0,
        amenities=ParkingAmenities(
            jetway_available=True, gpu_available=True, pushback_required=True
        ),
    )

    # 2 stands (large)
    db.add_parking_position(
        position_id="S1",
        parking_type=ParkingType.STAND,
        position=Vector3(-122.006, 10.0, 37.5),
        size_category=AircraftSizeCategory.LARGE,
        heading=180.0,
        amenities=ParkingAmenities(gpu_available=True, pushback_required=False),
    )
    db.add_parking_position(
        position_id="S2",
        parking_type=ParkingType.STAND,
        position=Vector3(-122.007, 10.0, 37.5),
        size_category=AircraftSizeCategory.LARGE,
        heading=180.0,
        amenities=ParkingAmenities(gpu_available=True, pushback_required=False),
    )

    return db


@pytest.fixture
def manager(parking_db: ParkingDatabase) -> ParkingAssignmentManager:
    """Create a test parking assignment manager."""
    return ParkingAssignmentManager(parking_db)


class TestParkingAssignmentManager:
    """Test ParkingAssignmentManager class."""

    def test_create_manager(self, parking_db: ParkingDatabase) -> None:
        """Test creating a parking assignment manager."""
        manager = ParkingAssignmentManager(parking_db)
        assert manager is not None
        assert manager.parking_db == parking_db
        assert len(manager.assignments) == 0

    def test_request_parking_ga_small(self, manager: ParkingAssignmentManager) -> None:
        """Test GA small aircraft gets tie-down parking."""
        assignment = manager.request_parking(
            aircraft_size=AircraftSizeCategory.SMALL,
            flight_type=FlightType.GENERAL_AVIATION,
            callsign="N123AB",
        )

        assert assignment is not None
        assert assignment.aircraft_callsign == "N123AB"
        assert assignment.position_id in ["T1", "T2"]  # Should get tie-down
        assert assignment.flight_type == FlightType.GENERAL_AVIATION
        assert assignment.aircraft_size == AircraftSizeCategory.SMALL

    def test_request_parking_commercial_large(self, manager: ParkingAssignmentManager) -> None:
        """Test commercial large aircraft gets gate parking."""
        assignment = manager.request_parking(
            aircraft_size=AircraftSizeCategory.LARGE,
            flight_type=FlightType.COMMERCIAL,
            callsign="UAL123",
        )

        assert assignment is not None
        assert assignment.aircraft_callsign == "UAL123"
        assert assignment.position_id in ["G1", "G2"]  # Should get gate
        assert assignment.flight_type == FlightType.COMMERCIAL

    def test_request_parking_cargo(self, manager: ParkingAssignmentManager) -> None:
        """Test cargo aircraft gets stand parking."""
        assignment = manager.request_parking(
            aircraft_size=AircraftSizeCategory.LARGE,
            flight_type=FlightType.CARGO,
            callsign="FDX456",
        )

        assert assignment is not None
        assert assignment.position_id in ["S1", "S2"]  # Should get stand (cargo prefers stands)

    def test_request_parking_charter(self, manager: ParkingAssignmentManager) -> None:
        """Test charter aircraft gets gate parking."""
        assignment = manager.request_parking(
            aircraft_size=AircraftSizeCategory.LARGE,
            flight_type=FlightType.CHARTER,
            callsign="XYZ789",
        )

        assert assignment is not None
        assert assignment.position_id in ["G1", "G2"]  # Should get gate

    def test_parking_becomes_occupied(self, manager: ParkingAssignmentManager) -> None:
        """Test that assigned parking is marked as occupied."""
        assignment = manager.request_parking(
            AircraftSizeCategory.SMALL, FlightType.GENERAL_AVIATION, "N123AB"
        )

        assert assignment is not None

        # Verify parking is occupied
        status = manager.get_parking_status(assignment.position_id)
        assert status == ParkingStatus.OCCUPIED

        # Verify parking database shows it occupied
        parking = manager.parking_db.get_parking_position(assignment.position_id)
        assert parking is not None
        assert parking.occupied_by == "N123AB"

    def test_release_parking(self, manager: ParkingAssignmentManager) -> None:
        """Test releasing parking assignment."""
        # Request parking
        assignment = manager.request_parking(
            AircraftSizeCategory.SMALL, FlightType.GENERAL_AVIATION, "N123AB"
        )

        assert assignment is not None
        position_id = assignment.position_id

        # Release parking
        manager.release_parking("N123AB")

        # Verify parking is available again
        status = manager.get_parking_status(position_id)
        assert status == ParkingStatus.AVAILABLE

        # Verify assignment removed
        assert manager.get_assignment("N123AB") is None

    def test_release_nonexistent_parking_raises_error(
        self, manager: ParkingAssignmentManager
    ) -> None:
        """Test releasing parking for aircraft without assignment raises error."""
        with pytest.raises(KeyError):
            manager.release_parking("NOEXIST")

    def test_duplicate_assignment_raises_error(self, manager: ParkingAssignmentManager) -> None:
        """Test requesting parking twice for same callsign raises error."""
        manager.request_parking(AircraftSizeCategory.SMALL, FlightType.GENERAL_AVIATION, "N123AB")

        with pytest.raises(ValueError):
            manager.request_parking(
                AircraftSizeCategory.SMALL, FlightType.GENERAL_AVIATION, "N123AB"
            )

    def test_get_assignment(self, manager: ParkingAssignmentManager) -> None:
        """Test getting assignment for an aircraft."""
        original_assignment = manager.request_parking(
            AircraftSizeCategory.SMALL, FlightType.GENERAL_AVIATION, "N123AB"
        )

        retrieved_assignment = manager.get_assignment("N123AB")

        assert retrieved_assignment is not None
        assert retrieved_assignment == original_assignment

    def test_get_nonexistent_assignment_returns_none(
        self, manager: ParkingAssignmentManager
    ) -> None:
        """Test getting assignment for aircraft without one returns None."""
        assignment = manager.get_assignment("NOEXIST")
        assert assignment is None

    def test_get_all_assignments(self, manager: ParkingAssignmentManager) -> None:
        """Test getting all active assignments."""
        # Create multiple assignments
        manager.request_parking(AircraftSizeCategory.SMALL, FlightType.GENERAL_AVIATION, "N123AB")
        manager.request_parking(AircraftSizeCategory.LARGE, FlightType.COMMERCIAL, "UAL123")
        manager.request_parking(AircraftSizeCategory.LARGE, FlightType.CARGO, "FDX456")

        assignments = manager.get_all_assignments()

        assert len(assignments) == 3
        callsigns = {a.aircraft_callsign for a in assignments}
        assert callsigns == {"N123AB", "UAL123", "FDX456"}

    def test_no_parking_available_returns_none(self, manager: ParkingAssignmentManager) -> None:
        """Test that no parking available returns None."""
        # Fill all tie-downs
        manager.request_parking(AircraftSizeCategory.SMALL, FlightType.GENERAL_AVIATION, "N1")
        manager.request_parking(AircraftSizeCategory.SMALL, FlightType.GENERAL_AVIATION, "N2")

        # Fill all ramps
        manager.request_parking(AircraftSizeCategory.SMALL, FlightType.GENERAL_AVIATION, "N3")
        manager.request_parking(AircraftSizeCategory.SMALL, FlightType.GENERAL_AVIATION, "N4")

        # Fill all gates
        manager.request_parking(AircraftSizeCategory.SMALL, FlightType.GENERAL_AVIATION, "N5")
        manager.request_parking(AircraftSizeCategory.SMALL, FlightType.GENERAL_AVIATION, "N6")

        # Fill all stands
        manager.request_parking(AircraftSizeCategory.SMALL, FlightType.GENERAL_AVIATION, "N7")
        manager.request_parking(AircraftSizeCategory.SMALL, FlightType.GENERAL_AVIATION, "N8")

        # Now no parking should be available
        assignment = manager.request_parking(
            AircraftSizeCategory.SMALL, FlightType.GENERAL_AVIATION, "N9"
        )

        assert assignment is None

    def test_fallback_to_any_parking_when_preferred_full(
        self, manager: ParkingAssignmentManager
    ) -> None:
        """Test fallback to any available parking when preferred type is full."""
        # Fill all gates
        manager.request_parking(AircraftSizeCategory.LARGE, FlightType.COMMERCIAL, "UAL1")
        manager.request_parking(AircraftSizeCategory.LARGE, FlightType.COMMERCIAL, "UAL2")

        # Request commercial parking - should fall back to stands
        assignment = manager.request_parking(
            AircraftSizeCategory.LARGE, FlightType.COMMERCIAL, "UAL3"
        )

        assert assignment is not None
        assert assignment.position_id in ["S1", "S2"]  # Should get stand as fallback

    def test_small_aircraft_can_use_large_parking(self, manager: ParkingAssignmentManager) -> None:
        """Test that small aircraft can use larger parking spots."""
        # Fill tie-downs and ramps
        manager.request_parking(AircraftSizeCategory.SMALL, FlightType.GENERAL_AVIATION, "N1")
        manager.request_parking(AircraftSizeCategory.SMALL, FlightType.GENERAL_AVIATION, "N2")
        manager.request_parking(AircraftSizeCategory.SMALL, FlightType.GENERAL_AVIATION, "N3")
        manager.request_parking(AircraftSizeCategory.SMALL, FlightType.GENERAL_AVIATION, "N4")

        # Small aircraft should fall back to gates/stands
        assignment = manager.request_parking(
            AircraftSizeCategory.SMALL, FlightType.GENERAL_AVIATION, "N5"
        )

        assert assignment is not None
        # Should get gate or stand
        assert assignment.position_id in ["G1", "G2", "S1", "S2"]

    def test_large_aircraft_cannot_use_small_parking(
        self, manager: ParkingAssignmentManager
    ) -> None:
        """Test that large aircraft cannot use small parking spots."""
        # Fill all large parking
        manager.request_parking(AircraftSizeCategory.LARGE, FlightType.COMMERCIAL, "UAL1")
        manager.request_parking(AircraftSizeCategory.LARGE, FlightType.COMMERCIAL, "UAL2")
        manager.request_parking(AircraftSizeCategory.LARGE, FlightType.CARGO, "FDX1")
        manager.request_parking(AircraftSizeCategory.LARGE, FlightType.CARGO, "FDX2")

        # Large aircraft should NOT be able to use tie-downs or ramps
        assignment = manager.request_parking(
            AircraftSizeCategory.LARGE, FlightType.COMMERCIAL, "UAL3"
        )

        assert assignment is None  # No parking available

    def test_get_parking_status_nonexistent_raises_error(
        self, manager: ParkingAssignmentManager
    ) -> None:
        """Test getting status for nonexistent parking raises error."""
        with pytest.raises(KeyError):
            manager.get_parking_status("NOEXIST")

    def test_multiple_aircraft_different_sizes(self, manager: ParkingAssignmentManager) -> None:
        """Test assigning parking to multiple aircraft of different sizes."""
        # Small GA aircraft
        a1 = manager.request_parking(
            AircraftSizeCategory.SMALL, FlightType.GENERAL_AVIATION, "N123AB"
        )

        # Medium GA aircraft
        a2 = manager.request_parking(
            AircraftSizeCategory.MEDIUM, FlightType.GENERAL_AVIATION, "N456CD"
        )

        # Large commercial aircraft
        a3 = manager.request_parking(AircraftSizeCategory.LARGE, FlightType.COMMERCIAL, "UAL123")

        assert a1 is not None
        assert a2 is not None
        assert a3 is not None

        # Verify all different positions
        assert a1.position_id != a2.position_id
        assert a2.position_id != a3.position_id
        assert a1.position_id != a3.position_id

        # Small should get tie-down
        assert a1.position_id in ["T1", "T2"]

        # Medium should get ramp
        assert a2.position_id in ["R1", "R2"]

        # Large commercial should get gate
        assert a3.position_id in ["G1", "G2"]

    def test_parking_assignment_has_timestamp(self, manager: ParkingAssignmentManager) -> None:
        """Test that parking assignments include timestamp."""
        assignment = manager.request_parking(
            AircraftSizeCategory.SMALL, FlightType.GENERAL_AVIATION, "N123AB"
        )

        assert assignment is not None
        assert assignment.assigned_time is not None


class TestFlightTypePreferences:
    """Test flight type parking preferences."""

    def test_ga_small_prefers_tiedown(self, manager: ParkingAssignmentManager) -> None:
        """Test GA small aircraft prefers tie-downs."""
        preferred = manager._get_preferred_parking_types(
            FlightType.GENERAL_AVIATION, AircraftSizeCategory.SMALL
        )

        assert preferred[0] == ParkingType.TIE_DOWN

    def test_ga_medium_prefers_ramp(self, manager: ParkingAssignmentManager) -> None:
        """Test GA medium aircraft prefers ramps."""
        preferred = manager._get_preferred_parking_types(
            FlightType.GENERAL_AVIATION, AircraftSizeCategory.MEDIUM
        )

        assert preferred[0] == ParkingType.RAMP

    def test_commercial_prefers_gate(self, manager: ParkingAssignmentManager) -> None:
        """Test commercial flights prefer gates."""
        preferred = manager._get_preferred_parking_types(
            FlightType.COMMERCIAL, AircraftSizeCategory.LARGE
        )

        assert preferred[0] == ParkingType.GATE

    def test_cargo_prefers_stand(self, manager: ParkingAssignmentManager) -> None:
        """Test cargo flights prefer stands."""
        preferred = manager._get_preferred_parking_types(
            FlightType.CARGO, AircraftSizeCategory.LARGE
        )

        assert preferred[0] == ParkingType.STAND

    def test_charter_prefers_gate(self, manager: ParkingAssignmentManager) -> None:
        """Test charter flights prefer gates."""
        preferred = manager._get_preferred_parking_types(
            FlightType.CHARTER, AircraftSizeCategory.LARGE
        )

        assert preferred[0] == ParkingType.GATE

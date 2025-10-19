"""Unit tests for parking position generator."""

import pytest

from airborne.airports.classifier import AirportCategory
from airborne.airports.database import Airport, AirportType, Runway, SurfaceType
from airborne.airports.parking import AircraftSizeCategory, ParkingType
from airborne.airports.parking_generator import ParkingGenerator
from airborne.physics.vectors import Vector3


@pytest.fixture
def small_airport() -> Airport:
    """Create a small test airport."""
    return Airport(
        icao="KPAO",
        name="Palo Alto Airport",
        position=Vector3(-122.115, 2.1, 37.461),
        airport_type=AirportType.SMALL_AIRPORT,
        municipality="Palo Alto",
        iso_country="US",
        scheduled_service=False,
    )


@pytest.fixture
def small_runway() -> Runway:
    """Create a small runway."""
    return Runway(
        airport_icao="KPAO",
        runway_id="13/31",
        length_ft=2443,
        width_ft=75,
        surface=SurfaceType.ASPH,
        lighted=True,
        closed=False,
        le_ident="13",
        le_latitude=37.461,
        le_longitude=-122.115,
        le_elevation_ft=2.1,
        le_heading_deg=130.0,
        he_ident="31",
        he_latitude=37.465,
        he_longitude=-122.120,
        he_elevation_ft=2.1,
        he_heading_deg=310.0,
    )


@pytest.fixture
def medium_airport() -> Airport:
    """Create a medium test airport."""
    return Airport(
        icao="KSJC",
        name="San Jose International",
        position=Vector3(-121.929, 18.3, 37.363),
        airport_type=AirportType.MEDIUM_AIRPORT,
        municipality="San Jose",
        iso_country="US",
        scheduled_service=True,
    )


@pytest.fixture
def medium_runway() -> Runway:
    """Create a medium runway."""
    return Runway(
        airport_icao="KSJC",
        runway_id="12L/30R",
        length_ft=4600,
        width_ft=150,
        surface=SurfaceType.ASPH,
        lighted=True,
        closed=False,
        le_ident="12L",
        le_latitude=37.363,
        le_longitude=-121.929,
        le_elevation_ft=18.3,
        le_heading_deg=120.0,
        he_ident="30R",
        he_latitude=37.368,
        he_longitude=-121.925,
        he_elevation_ft=18.3,
        he_heading_deg=300.0,
    )


@pytest.fixture
def large_airport() -> Airport:
    """Create a large test airport."""
    return Airport(
        icao="KSEA",
        name="Seattle-Tacoma International",
        position=Vector3(-122.309, 128.0, 47.449),
        airport_type=AirportType.LARGE_AIRPORT,
        municipality="Seattle",
        iso_country="US",
        scheduled_service=True,
    )


@pytest.fixture
def large_runway() -> Runway:
    """Create a large runway."""
    return Runway(
        airport_icao="KSEA",
        runway_id="16L/34R",
        length_ft=9426,
        width_ft=150,
        surface=SurfaceType.ASPH,
        lighted=True,
        closed=False,
        le_ident="16L",
        le_latitude=47.449,
        le_longitude=-122.309,
        le_elevation_ft=128.0,
        le_heading_deg=160.0,
        he_ident="34R",
        he_latitude=47.460,
        he_longitude=-122.315,
        he_elevation_ft=128.0,
        he_heading_deg=340.0,
    )


@pytest.fixture
def xl_airport() -> Airport:
    """Create an XL test airport."""
    return Airport(
        icao="KLAX",
        name="Los Angeles International",
        position=Vector3(-118.409, 38.1, 33.943),
        airport_type=AirportType.LARGE_AIRPORT,
        municipality="Los Angeles",
        iso_country="US",
        scheduled_service=True,
    )


@pytest.fixture
def xl_runway() -> Runway:
    """Create an XL runway."""
    return Runway(
        airport_icao="KLAX",
        runway_id="07L/25R",
        length_ft=12091,
        width_ft=200,
        surface=SurfaceType.ASPH,
        lighted=True,
        closed=False,
        le_ident="07L",
        le_latitude=33.943,
        le_longitude=-118.409,
        le_elevation_ft=38.1,
        le_heading_deg=70.0,
        he_ident="25R",
        he_latitude=33.948,
        he_longitude=-118.398,
        he_elevation_ft=38.1,
        he_heading_deg=250.0,
    )


class TestParkingGenerator:
    """Test ParkingGenerator class."""

    def test_create_generator(self) -> None:
        """Test creating a parking generator."""
        generator = ParkingGenerator()
        assert generator is not None

    def test_generate_no_runways_returns_empty(self, small_airport: Airport) -> None:
        """Test generating parking with no runways returns empty database."""
        generator = ParkingGenerator()

        db = generator.generate(small_airport, [], AirportCategory.SMALL)

        assert db.airport_icao == "KPAO"
        assert db.get_parking_count() == 0

    def test_generate_small_airport(self, small_airport: Airport, small_runway: Runway) -> None:
        """Test generating parking for small airport."""
        generator = ParkingGenerator()

        db = generator.generate(small_airport, [small_runway], AirportCategory.SMALL)

        # Should have tie-downs
        assert db.get_parking_count() > 0

        tie_downs = db.get_parking_by_type(ParkingType.TIE_DOWN)
        assert len(tie_downs) == 5  # Default is 5 tie-downs

        # All should be small aircraft
        for parking in tie_downs:
            assert parking.size_category == AircraftSizeCategory.SMALL
            assert parking.amenities.fuel_available is True

    def test_generate_medium_airport(self, medium_airport: Airport, medium_runway: Runway) -> None:
        """Test generating parking for medium airport."""
        generator = ParkingGenerator()

        db = generator.generate(medium_airport, [medium_runway], AirportCategory.MEDIUM)

        # Should have ramp parking
        assert db.get_parking_count() > 0

        ramps = db.get_parking_by_type(ParkingType.RAMP)
        assert len(ramps) == 12  # Default is 12 ramps

        # Should be medium aircraft category
        for parking in ramps:
            assert parking.size_category == AircraftSizeCategory.MEDIUM
            assert parking.amenities.fuel_available is True
            assert parking.amenities.gpu_available is True

    def test_generate_large_airport(self, large_airport: Airport, large_runway: Runway) -> None:
        """Test generating parking for large airport."""
        generator = ParkingGenerator()

        db = generator.generate(large_airport, [large_runway], AirportCategory.LARGE)

        # Should have gates and stands
        assert db.get_parking_count() > 0

        gates = db.get_parking_by_type(ParkingType.GATE)
        assert len(gates) == 15  # Default is 15 gates

        stands = db.get_parking_by_type(ParkingType.STAND)
        assert len(stands) == 8  # Default is 8 stands

        # Gates should have jetways and require pushback
        for gate in gates:
            assert gate.size_category == AircraftSizeCategory.LARGE
            assert gate.amenities.jetway_available is True
            assert gate.amenities.pushback_required is True

        # Stands should not require pushback (remote)
        for stand in stands:
            assert stand.size_category == AircraftSizeCategory.LARGE
            assert stand.amenities.pushback_required is False

    def test_generate_xl_airport(self, xl_airport: Airport, xl_runway: Runway) -> None:
        """Test generating parking for extra large airport."""
        generator = ParkingGenerator()

        db = generator.generate(xl_airport, [xl_runway], AirportCategory.XL)

        # Should have many gates and stands
        assert db.get_parking_count() > 0

        gates = db.get_parking_by_type(ParkingType.GATE)
        assert len(gates) == 45  # 3 terminals * 15 gates

        stands = db.get_parking_by_type(ParkingType.STAND)
        assert len(stands) == 20

        # Should have mix of large and xlarge gates
        large_gates = [g for g in gates if g.size_category == AircraftSizeCategory.LARGE]
        xlarge_gates = [g for g in gates if g.size_category == AircraftSizeCategory.XLARGE]

        assert len(large_gates) > 0
        assert len(xlarge_gates) > 0
        assert len(large_gates) + len(xlarge_gates) == len(gates)

    def test_parking_positions_have_unique_ids(
        self, medium_airport: Airport, medium_runway: Runway
    ) -> None:
        """Test that all generated parking positions have unique IDs."""
        generator = ParkingGenerator()

        db = generator.generate(medium_airport, [medium_runway], AirportCategory.MEDIUM)

        # Get all position IDs
        all_ids = [p.position_id for p in db.get_all_parking()]

        # Check for uniqueness
        assert len(all_ids) == len(set(all_ids))

    def test_parking_positions_have_valid_coordinates(
        self, small_airport: Airport, small_runway: Runway
    ) -> None:
        """Test that generated positions have valid geographic coordinates."""
        generator = ParkingGenerator()

        db = generator.generate(small_airport, [small_runway], AirportCategory.SMALL)

        for parking in db.get_all_parking():
            # Longitude should be valid
            assert -180.0 <= parking.position.x <= 180.0

            # Latitude should be valid
            assert -90.0 <= parking.position.z <= 90.0

            # Elevation should be non-negative (or very close to airport elevation)
            assert abs(parking.position.y - small_airport.position.y) < 100.0

    def test_parking_positions_have_valid_headings(
        self, medium_airport: Airport, medium_runway: Runway
    ) -> None:
        """Test that generated positions have valid headings."""
        generator = ParkingGenerator()

        db = generator.generate(medium_airport, [medium_runway], AirportCategory.MEDIUM)

        for parking in db.get_all_parking():
            # Heading should be 0-360
            assert 0.0 <= parking.heading < 360.0

    def test_small_airport_parking_near_runway(
        self, small_airport: Airport, small_runway: Runway
    ) -> None:
        """Test that small airport parking is positioned near runway."""
        generator = ParkingGenerator()

        db = generator.generate(small_airport, [small_runway], AirportCategory.SMALL)

        # All parking should be relatively close to airport position
        for parking in db.get_all_parking():
            # Calculate rough distance (simplified)
            dx = (parking.position.x - small_airport.position.x) * 111000.0
            dz = (parking.position.z - small_airport.position.z) * 111000.0
            distance = (dx**2 + dz**2) ** 0.5

            # Should be within 500m of airport center for small airport
            assert distance < 500.0

    def test_large_airport_multiple_parking_areas(
        self, large_airport: Airport, large_runway: Runway
    ) -> None:
        """Test that large airports have distinct parking areas."""
        generator = ParkingGenerator()

        db = generator.generate(large_airport, [large_runway], AirportCategory.LARGE)

        gates = db.get_parking_by_type(ParkingType.GATE)
        stands = db.get_parking_by_type(ParkingType.STAND)

        # Calculate rough distance between first gate and first stand
        if gates and stands:
            gate_pos = gates[0].position
            stand_pos = stands[0].position

            dx = (gate_pos.x - stand_pos.x) * 111000.0
            dz = (gate_pos.z - stand_pos.z) * 111000.0
            distance = (dx**2 + dz**2) ** 0.5

            # Gate and stand areas should be separated
            assert distance > 100.0

    def test_all_generated_parking_available_initially(
        self, medium_airport: Airport, medium_runway: Runway
    ) -> None:
        """Test that all generated parking is initially available."""
        generator = ParkingGenerator()

        db = generator.generate(medium_airport, [medium_runway], AirportCategory.MEDIUM)

        for parking in db.get_all_parking():
            assert parking.is_available() is True


class TestParkingIntegrationWithGenerator:
    """Integration tests for parking generation and usage."""

    def test_small_airport_full_workflow(
        self, small_airport: Airport, small_runway: Runway
    ) -> None:
        """Test complete workflow for small airport parking."""
        generator = ParkingGenerator()

        # Generate parking
        db = generator.generate(small_airport, [small_runway], AirportCategory.SMALL)

        # C172 arrives, requests parking
        available = db.get_available_parking(AircraftSizeCategory.SMALL)
        assert len(available) > 0

        # Park at first available
        parking = available[0]
        db.occupy_parking(parking.position_id, "N123AB")

        # Verify occupied
        assert parking.is_available() is False
        assert parking.occupied_by == "N123AB"

        # Verify one less spot available
        available_after = db.get_available_parking(AircraftSizeCategory.SMALL)
        assert len(available_after) == len(available) - 1

    def test_large_airport_size_assignment(
        self, large_airport: Airport, large_runway: Runway
    ) -> None:
        """Test that large airport properly assigns by aircraft size."""
        generator = ParkingGenerator()

        db = generator.generate(large_airport, [large_runway], AirportCategory.LARGE)

        # Small aircraft (C172) can park anywhere
        small_available = db.get_available_parking(AircraftSizeCategory.SMALL)
        assert len(small_available) > 0

        # Large aircraft (B737) needs large parking
        large_available = db.get_available_parking(AircraftSizeCategory.LARGE)
        assert len(large_available) > 0

        # Small aircraft should have more options
        assert len(small_available) >= len(large_available)

    def test_xl_airport_widebody_capability(self, xl_airport: Airport, xl_runway: Runway) -> None:
        """Test that XL airports can accommodate widebody aircraft."""
        generator = ParkingGenerator()

        db = generator.generate(xl_airport, [xl_runway], AirportCategory.XL)

        # Should have parking for extra large aircraft
        xlarge_available = db.get_available_parking(AircraftSizeCategory.XLARGE)
        assert len(xlarge_available) > 0

        # Mix of gates and stands
        xlarge_gates = [p for p in xlarge_available if p.parking_type == ParkingType.GATE]
        xlarge_stands = [p for p in xlarge_available if p.parking_type == ParkingType.STAND]

        # Should have both types available for widebodies
        assert len(xlarge_gates) > 0
        assert len(xlarge_stands) > 0

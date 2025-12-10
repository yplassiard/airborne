"""Tests for runway position detection in AirportDatabase."""

import math
import pytest

from airborne.airports.database import AirportDatabase, Runway, SurfaceType


class TestRunwayDetection:
    """Tests for runway position detection methods."""

    def create_test_runway(self) -> Runway:
        """Create a test runway for unit tests.

        Creates a north-south runway (09/27) at a known location.
        """
        return Runway(
            airport_icao="TEST",
            runway_id="09/27",
            length_ft=5000.0,
            width_ft=100.0,
            surface=SurfaceType.ASPH,
            lighted=True,
            closed=False,
            le_ident="09",
            le_latitude=37.0,
            le_longitude=-122.0,
            le_elevation_ft=0.0,
            le_heading_deg=90.0,  # Pointing east
            he_ident="27",
            he_latitude=37.0,
            he_longitude=-121.985,  # ~1500m east (5000ft runway)
            he_elevation_ft=0.0,
            he_heading_deg=270.0,  # Pointing west
        )

    def test_position_on_runway_center(self):
        """Test detection of position at runway center."""
        db = AirportDatabase()
        runway = self.create_test_runway()
        db.runways["TEST"] = [runway]

        # Center of runway
        center_lat = (runway.le_latitude + runway.he_latitude) / 2
        center_lon = (runway.le_longitude + runway.he_longitude) / 2

        result = db.get_runway_at_position(center_lat, center_lon)

        assert result is not None
        found_runway, end_id = result
        assert found_runway.runway_id == "09/27"

    def test_position_on_runway_near_threshold(self):
        """Test detection near runway threshold."""
        db = AirportDatabase()
        runway = self.create_test_runway()
        db.runways["TEST"] = [runway]

        # Near LE threshold
        result = db.get_runway_at_position(
            runway.le_latitude,
            runway.le_longitude + 0.001,  # Slightly inside runway
        )

        assert result is not None
        found_runway, end_id = result
        assert end_id == "09"  # Closer to LE

    def test_position_off_runway(self):
        """Test detection returns None when off runway."""
        db = AirportDatabase()
        runway = self.create_test_runway()
        db.runways["TEST"] = [runway]

        # Way off to the side
        result = db.get_runway_at_position(
            runway.le_latitude + 0.01,  # ~1km north of runway
            runway.le_longitude,
        )

        assert result is None

    def test_position_slightly_off_runway_within_tolerance(self):
        """Test detection with tolerance for slight offset."""
        db = AirportDatabase()
        runway = self.create_test_runway()
        db.runways["TEST"] = [runway]

        # Center longitude, but 30m north (within 50m default tolerance)
        offset_lat = (runway.le_latitude + runway.he_latitude) / 2 + 0.0003  # ~30m

        result = db.get_runway_at_position(
            offset_lat,
            (runway.le_longitude + runway.he_longitude) / 2,
            tolerance_m=50.0,
        )

        assert result is not None

    def test_get_nearest_runway(self):
        """Test finding nearest runway."""
        db = AirportDatabase()
        runway = self.create_test_runway()
        db.runways["TEST"] = [runway]

        # Position 1nm from runway
        result = db.get_nearest_runway(
            runway.le_latitude + 0.01,  # ~0.6nm north
            runway.le_longitude,
            max_distance_nm=5.0,
        )

        assert result is not None
        found_runway, end_id, distance = result
        assert found_runway.runway_id == "09/27"
        assert distance < 1.0  # Should be less than 1nm

    def test_get_runway_alignment(self):
        """Test runway alignment calculation."""
        db = AirportDatabase()
        runway = self.create_test_runway()
        db.runways["TEST"] = [runway]

        # Position on extended centerline, approaching runway 09
        alignment = db.get_runway_alignment(
            latitude=runway.le_latitude,
            longitude=runway.le_longitude - 0.01,  # 1km west (on approach)
            heading_deg=90.0,  # Heading east towards runway
            runway=runway,
        )

        assert "lateral_deviation_m" in alignment
        assert "heading_deviation_deg" in alignment
        assert "distance_to_threshold_m" in alignment
        assert abs(alignment["lateral_deviation_m"]) < 100  # Should be near centerline
        assert abs(alignment["heading_deviation_deg"]) < 5  # Should be aligned

    def test_bearing_calculation(self):
        """Test bearing calculation utility."""
        # San Francisco to New York should be roughly east-northeast
        bearing = AirportDatabase._calculate_bearing(
            37.7749, -122.4194,  # San Francisco
            40.7128, -74.0060,  # New York
        )

        # Should be roughly 60-80 degrees (ENE)
        assert 50 < bearing < 90


class TestRunwayAlignmentIntegration:
    """Integration tests for runway alignment with real airport data."""

    @pytest.fixture
    def airport_db(self):
        """Create airport database fixture."""
        return AirportDatabase()

    def test_alignment_with_loaded_airport(self, airport_db):
        """Test alignment with a loaded airport."""
        # This test requires network access to X-Plane Gateway
        # Skip if airport can't be loaded
        try:
            if not airport_db.load_airport("KPAO"):
                pytest.skip("Could not load KPAO airport data")
        except Exception:
            pytest.skip("Network access required for airport data")

        runways = airport_db.get_runways("KPAO")
        if not runways:
            pytest.skip("No runway data available")

        runway = runways[0]

        # Calculate alignment from a position
        alignment = airport_db.get_runway_alignment(
            latitude=runway.le_latitude,
            longitude=runway.le_longitude,
            heading_deg=runway.le_heading_deg,
            runway=runway,
        )

        assert alignment is not None
        assert "lateral_deviation_m" in alignment

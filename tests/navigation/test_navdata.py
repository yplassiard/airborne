"""Tests for navigation database."""

import csv

import pytest

from airborne.navigation.navdata import Navaid, NavaidType, NavDatabase
from airborne.physics.vectors import Vector3


class TestNavaidType:
    """Test NavaidType enum."""

    def test_navaid_types_exist(self):
        """Test all expected navaid types exist."""
        assert NavaidType.VOR
        assert NavaidType.NDB
        assert NavaidType.DME
        assert NavaidType.WAYPOINT
        assert NavaidType.FIX
        assert NavaidType.AIRPORT

    def test_navaid_type_values(self):
        """Test navaid type values."""
        assert NavaidType.VOR.value == "VOR"
        assert NavaidType.NDB.value == "NDB"
        assert NavaidType.WAYPOINT.value == "WAYPOINT"


class TestNavaid:
    """Test Navaid class."""

    def test_create_vor(self):
        """Test creating a VOR navaid."""
        position = Vector3(-122.3790, 13, 37.6213)  # x=lon, y=elev, z=lat
        vor = Navaid(
            identifier="SFO",
            name="San Francisco VOR",
            type=NavaidType.VOR,
            position=position,
            frequency=115.8,
            range_nm=40,
        )

        assert vor.identifier == "SFO"
        assert vor.name == "San Francisco VOR"
        assert vor.type == NavaidType.VOR
        assert vor.position == position
        assert vor.frequency == 115.8
        assert vor.range_nm == 40

    def test_create_waypoint_without_frequency(self):
        """Test creating a waypoint without frequency."""
        position = Vector3(-122.5, 0, 37.5)  # x=lon, y=elev, z=lat
        waypoint = Navaid(
            identifier="MODET",
            name="MODET Intersection",
            type=NavaidType.WAYPOINT,
            position=position,
        )

        assert waypoint.identifier == "MODET"
        assert waypoint.type == NavaidType.WAYPOINT
        assert waypoint.frequency is None
        assert waypoint.range_nm == 0.0

    def test_navaid_str_with_frequency(self):
        """Test string representation with frequency."""
        position = Vector3(-122.3790, 13, 37.6213)  # x=lon, y=elev, z=lat
        vor = Navaid(
            identifier="SFO",
            name="San Francisco VOR",
            type=NavaidType.VOR,
            position=position,
            frequency=115.8,
            range_nm=40,
        )

        assert str(vor) == "SFO (VOR 115.80)"

    def test_navaid_str_without_frequency(self):
        """Test string representation without frequency."""
        position = Vector3(-122.5, 0, 37.5)  # x=lon, y=elev, z=lat
        waypoint = Navaid(
            identifier="MODET",
            name="MODET Intersection",
            type=NavaidType.WAYPOINT,
            position=position,
        )

        assert str(waypoint) == "MODET (WAYPOINT)"


class TestNavDatabase:
    """Test NavDatabase class."""

    def test_create_empty_database(self):
        """Test creating an empty database."""
        db = NavDatabase()

        assert db.count() == 0
        assert len(db.navaids) == 0

    def test_add_navaid(self):
        """Test adding a navaid to database."""
        db = NavDatabase()
        position = Vector3(-122.3790, 13, 37.6213)  # x=lon, y=elev, z=lat
        vor = Navaid(
            identifier="SFO",
            name="San Francisco VOR",
            type=NavaidType.VOR,
            position=position,
            frequency=115.8,
            range_nm=40,
        )

        db.add_navaid(vor)

        assert db.count() == 1
        assert "SFO" in db.navaids

    def test_add_duplicate_navaid_replaces(self):
        """Test adding duplicate navaid replaces existing."""
        db = NavDatabase()
        position = Vector3(-122.3790, 13, 37.6213)  # x=lon, y=elev, z=lat

        vor1 = Navaid(
            identifier="SFO",
            name="San Francisco VOR",
            type=NavaidType.VOR,
            position=position,
            frequency=115.8,
        )

        vor2 = Navaid(
            identifier="SFO",
            name="San Francisco VOR Updated",
            type=NavaidType.VOR,
            position=position,
            frequency=115.9,
        )

        db.add_navaid(vor1)
        db.add_navaid(vor2)

        assert db.count() == 1
        assert db.navaids["SFO"].frequency == 115.9
        assert db.navaids["SFO"].name == "San Francisco VOR Updated"

    def test_find_navaid_exists(self):
        """Test finding an existing navaid."""
        db = NavDatabase()
        position = Vector3(-122.3790, 13, 37.6213)  # x=lon, y=elev, z=lat
        vor = Navaid(
            identifier="SFO",
            name="San Francisco VOR",
            type=NavaidType.VOR,
            position=position,
            frequency=115.8,
        )
        db.add_navaid(vor)

        found = db.find_navaid("SFO")

        assert found is not None
        assert found.identifier == "SFO"
        assert found.frequency == 115.8

    def test_find_navaid_not_exists(self):
        """Test finding a non-existent navaid."""
        db = NavDatabase()

        found = db.find_navaid("NOTEXIST")

        assert found is None

    def test_find_navaids_near(self):
        """Test finding navaids within radius."""
        db = NavDatabase()

        # San Francisco VOR (x=lon, y=elev, z=lat)
        sfo = Navaid(
            identifier="SFO",
            name="San Francisco VOR",
            type=NavaidType.VOR,
            position=Vector3(-122.3790, 13, 37.6213),
            frequency=115.8,
        )

        # Oakland VOR (approx 10 NM from SFO)
        oak = Navaid(
            identifier="OAK",
            name="Oakland VOR",
            type=NavaidType.VOR,
            position=Vector3(-122.2211, 6, 37.7219),
            frequency=116.8,
        )

        # Los Angeles VOR (approx 340 NM from SFO)
        lax = Navaid(
            identifier="LAX",
            name="Los Angeles VOR",
            type=NavaidType.VOR,
            position=Vector3(-118.4081, 38, 33.9425),
            frequency=113.6,
        )

        db.add_navaid(sfo)
        db.add_navaid(oak)
        db.add_navaid(lax)

        # Search from SFO position with 50 NM radius
        center = Vector3(-122.3790, 13, 37.6213)
        nearby = db.find_navaids_near(center, radius_nm=50)

        # Should find SFO and OAK, but not LAX
        assert len(nearby) == 2
        identifiers = [n.identifier for n in nearby]
        assert "SFO" in identifiers
        assert "OAK" in identifiers
        assert "LAX" not in identifiers

    def test_find_navaids_near_sorted_by_distance(self):
        """Test that navaids are sorted by distance (closest first)."""
        db = NavDatabase()

        sfo = Navaid(
            identifier="SFO",
            name="San Francisco VOR",
            type=NavaidType.VOR,
            position=Vector3(-122.3790, 13, 37.6213),
        )

        oak = Navaid(
            identifier="OAK",
            name="Oakland VOR",
            type=NavaidType.VOR,
            position=Vector3(-122.2211, 6, 37.7219),
        )

        db.add_navaid(oak)  # Add in reverse order
        db.add_navaid(sfo)

        # Search from SFO position
        center = Vector3(-122.3790, 13, 37.6213)
        nearby = db.find_navaids_near(center, radius_nm=50)

        # SFO should be first (distance ~0), OAK second
        assert nearby[0].identifier == "SFO"
        assert nearby[1].identifier == "OAK"

    def test_find_navaids_near_with_type_filter(self):
        """Test finding navaids with type filter."""
        db = NavDatabase()

        vor = Navaid(
            identifier="SFO",
            name="San Francisco VOR",
            type=NavaidType.VOR,
            position=Vector3(-122.3790, 13, 37.6213),
        )

        ndb = Navaid(
            identifier="SF",
            name="San Francisco NDB",
            type=NavaidType.NDB,
            position=Vector3(-122.3790, 13, 37.6213),
            frequency=332,
        )

        waypoint = Navaid(
            identifier="MODET",
            name="MODET Intersection",
            type=NavaidType.WAYPOINT,
            position=Vector3(-122.4, 0, 37.6),
        )

        db.add_navaid(vor)
        db.add_navaid(ndb)
        db.add_navaid(waypoint)

        # Find only VORs
        center = Vector3(-122.3790, 13, 37.6213)
        vors = db.find_navaids_near(center, radius_nm=50, navaid_type=NavaidType.VOR)

        assert len(vors) == 1
        assert vors[0].identifier == "SFO"

    def test_find_navaids_by_type(self):
        """Test finding all navaids of a specific type."""
        db = NavDatabase()

        vor1 = Navaid(
            identifier="SFO",
            name="San Francisco VOR",
            type=NavaidType.VOR,
            position=Vector3(-122.3790, 13, 37.6213),
        )

        vor2 = Navaid(
            identifier="OAK",
            name="Oakland VOR",
            type=NavaidType.VOR,
            position=Vector3(-122.2211, 6, 37.7219),
        )

        ndb = Navaid(
            identifier="SF",
            name="San Francisco NDB",
            type=NavaidType.NDB,
            position=Vector3(-122.3790, 13, 37.6213),
        )

        db.add_navaid(vor1)
        db.add_navaid(vor2)
        db.add_navaid(ndb)

        vors = db.find_navaids_by_type(NavaidType.VOR)
        ndbs = db.find_navaids_by_type(NavaidType.NDB)

        assert len(vors) == 2
        assert len(ndbs) == 1

    def test_calculate_route_distance_two_points(self):
        """Test calculating distance for two-point route."""
        db = NavDatabase()

        # Palo Alto (KPAO) to San Francisco (KSFO) - approx 10 NM
        # x=lon, y=elev, z=lat
        pao = Navaid(
            identifier="KPAO",
            name="Palo Alto Airport",
            type=NavaidType.AIRPORT,
            position=Vector3(-122.1150, 0, 37.4613),
        )

        sfo = Navaid(
            identifier="KSFO",
            name="San Francisco Airport",
            type=NavaidType.AIRPORT,
            position=Vector3(-122.3750, 0, 37.6190),
        )

        db.add_navaid(pao)
        db.add_navaid(sfo)

        distance = db.calculate_route_distance([pao, sfo])

        # Should be approximately 10-16 nautical miles
        assert 10 <= distance <= 16

    def test_calculate_route_distance_multiple_points(self):
        """Test calculating distance for multi-point route."""
        db = NavDatabase()

        # x=lon, y=elev, z=lat
        p1 = Navaid(
            identifier="P1",
            name="Point 1",
            type=NavaidType.WAYPOINT,
            position=Vector3(-122.0, 0, 37.0),
        )

        p2 = Navaid(
            identifier="P2",
            name="Point 2",
            type=NavaidType.WAYPOINT,
            position=Vector3(-122.0, 0, 38.0),
        )

        p3 = Navaid(
            identifier="P3",
            name="Point 3",
            type=NavaidType.WAYPOINT,
            position=Vector3(-121.0, 0, 38.0),
        )

        distance = db.calculate_route_distance([p1, p2, p3])

        # Each degree of latitude is ~60 NM
        # p1->p2: 1 degree lat = ~60 NM
        # p2->p3: 1 degree lon at 38°N = ~47 NM
        # Total should be ~107 NM
        assert 100 <= distance <= 115

    def test_calculate_route_distance_single_point(self):
        """Test calculating distance for single point (should be 0)."""
        db = NavDatabase()

        navaid = Navaid(
            identifier="TEST",
            name="Test",
            type=NavaidType.WAYPOINT,
            position=Vector3(-122.0, 0, 37.0),
        )

        distance = db.calculate_route_distance([navaid])

        assert distance == 0.0

    def test_calculate_route_distance_empty_list(self):
        """Test calculating distance for empty list (should be 0)."""
        db = NavDatabase()

        distance = db.calculate_route_distance([])

        assert distance == 0.0

    def test_clear_database(self):
        """Test clearing all navaids from database."""
        db = NavDatabase()

        navaid = Navaid(
            identifier="TEST",
            name="Test",
            type=NavaidType.WAYPOINT,
            position=Vector3(-122.0, 0, 37.0),
        )
        db.add_navaid(navaid)

        assert db.count() == 1

        db.clear()

        assert db.count() == 0
        assert len(db.navaids) == 0

    def test_load_from_csv(self, tmp_path):
        """Test loading navaids from CSV file."""
        # Create test CSV file
        csv_file = tmp_path / "navaids.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "identifier",
                    "name",
                    "type",
                    "latitude",
                    "longitude",
                    "elevation_ft",
                    "frequency",
                    "range_nm",
                ]
            )
            writer.writerow(
                ["SFO", "San Francisco VOR", "VOR", "37.6213", "-122.3790", "13", "115.8", "40"]
            )
            writer.writerow(
                ["OAK", "Oakland VOR", "VOR", "37.7219", "-122.2211", "6", "116.8", "40"]
            )
            writer.writerow(
                ["MODET", "MODET Intersection", "WAYPOINT", "37.5", "-122.5", "0", "", "0"]
            )

        db = NavDatabase()
        count = db.load_from_csv(str(csv_file))

        assert count == 3
        assert db.count() == 3

        sfo = db.find_navaid("SFO")
        assert sfo is not None
        assert sfo.name == "San Francisco VOR"
        assert sfo.type == NavaidType.VOR
        assert sfo.frequency == 115.8
        assert sfo.range_nm == 40

        modet = db.find_navaid("MODET")
        assert modet is not None
        assert modet.type == NavaidType.WAYPOINT
        assert modet.frequency is None

    def test_load_from_csv_file_not_found(self, tmp_path):
        """Test loading from non-existent CSV file raises error."""
        db = NavDatabase()

        with pytest.raises(FileNotFoundError):
            db.load_from_csv(str(tmp_path / "nonexistent.csv"))

    def test_load_from_csv_invalid_type_skipped(self, tmp_path):
        """Test that rows with invalid navaid types are skipped."""
        csv_file = tmp_path / "navaids.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "identifier",
                    "name",
                    "type",
                    "latitude",
                    "longitude",
                    "elevation_ft",
                    "frequency",
                    "range_nm",
                ]
            )
            writer.writerow(
                ["SFO", "San Francisco VOR", "VOR", "37.6213", "-122.3790", "13", "115.8", "40"]
            )
            writer.writerow(
                [
                    "BAD",
                    "Bad Navaid",
                    "INVALID_TYPE",
                    "37.0",
                    "-122.0",
                    "0",
                    "",
                    "0",
                ]
            )

        db = NavDatabase()
        count = db.load_from_csv(str(csv_file))

        # Only valid row should be loaded
        assert count == 1
        assert db.count() == 1
        assert db.find_navaid("SFO") is not None
        assert db.find_navaid("BAD") is None

    def test_load_from_csv_invalid_coordinates_skipped(self, tmp_path):
        """Test that rows with invalid coordinates are skipped."""
        csv_file = tmp_path / "navaids.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "identifier",
                    "name",
                    "type",
                    "latitude",
                    "longitude",
                    "elevation_ft",
                    "frequency",
                    "range_nm",
                ]
            )
            writer.writerow(
                ["SFO", "San Francisco VOR", "VOR", "37.6213", "-122.3790", "13", "115.8", "40"]
            )
            writer.writerow(
                ["BAD", "Bad Navaid", "VOR", "not_a_number", "-122.0", "0", "115.0", "40"]
            )

        db = NavDatabase()
        count = db.load_from_csv(str(csv_file))

        # Only valid row should be loaded
        assert count == 1
        assert db.count() == 1

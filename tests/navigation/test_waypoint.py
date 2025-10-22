"""Tests for navigation waypoint."""

from airborne.navigation.waypoint import Waypoint
from airborne.physics.vectors import Vector3


class TestWaypoint:
    """Test Waypoint class."""

    def test_create_waypoint(self):
        """Test creating a waypoint."""
        position = Vector3(37.6213, -122.3790, 0)
        waypoint = Waypoint(position=position, altitude_ft=3000, speed_kts=120, name="KPAO")

        assert waypoint.position == position
        assert waypoint.altitude_ft == 3000
        assert waypoint.speed_kts == 120
        assert waypoint.name == "KPAO"

    def test_waypoint_default_name(self):
        """Test waypoint with default empty name."""
        position = Vector3(37.0, -122.0, 0)
        waypoint = Waypoint(position=position, altitude_ft=5000, speed_kts=150)

        assert waypoint.name == ""

    def test_waypoint_str_with_name(self):
        """Test string representation with name."""
        position = Vector3(37.6213, -122.3790, 0)
        waypoint = Waypoint(position=position, altitude_ft=3000, speed_kts=120, name="KPAO")

        assert str(waypoint) == "KPAO (3000ft, 120kts)"

    def test_waypoint_str_without_name(self):
        """Test string representation without name."""
        position = Vector3(37.0, -122.0, 0)
        waypoint = Waypoint(position=position, altitude_ft=5000, speed_kts=150)

        assert str(waypoint) == "WPT (5000ft, 150kts)"

    def test_waypoint_with_decimal_values(self):
        """Test waypoint with decimal altitude and speed."""
        position = Vector3(37.5, -122.5, 100)
        waypoint = Waypoint(position=position, altitude_ft=3500.5, speed_kts=125.7, name="TEST")

        assert waypoint.altitude_ft == 3500.5
        assert waypoint.speed_kts == 125.7
        assert str(waypoint) == "TEST (3500ft, 126kts)"  # Rounded in str

    def test_waypoint_equality(self):
        """Test waypoint equality comparison."""
        position1 = Vector3(37.0, -122.0, 0)
        position2 = Vector3(37.0, -122.0, 0)

        waypoint1 = Waypoint(position=position1, altitude_ft=3000, speed_kts=120, name="TEST")
        waypoint2 = Waypoint(position=position2, altitude_ft=3000, speed_kts=120, name="TEST")

        assert waypoint1 == waypoint2

    def test_waypoint_inequality(self):
        """Test waypoint inequality comparison."""
        position = Vector3(37.0, -122.0, 0)

        waypoint1 = Waypoint(position=position, altitude_ft=3000, speed_kts=120, name="TEST1")
        waypoint2 = Waypoint(position=position, altitude_ft=3000, speed_kts=120, name="TEST2")

        assert waypoint1 != waypoint2

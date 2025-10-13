"""Tests for traffic pattern generation."""

import pytest

from airborne.physics.vectors import Vector3
from airborne.plugins.traffic.traffic_patterns import TrafficGenerator


@pytest.fixture
def generator():
    """Create traffic generator."""
    return TrafficGenerator()


def test_generate_departure(generator):
    """Test departure generation."""
    airport_pos = Vector3(0, 0, 0)
    runway_heading = 90.0  # East

    aircraft = generator.generate_departure(
        airport_position=airport_pos,
        runway_heading=runway_heading,
        airport_elevation_ft=100,
    )

    assert aircraft.callsign.startswith("AI")
    assert aircraft.position.x == airport_pos.x
    assert aircraft.position.z == airport_pos.z
    assert aircraft.altitude_ft == 100
    assert aircraft.airspeed_kts == 0.0
    assert aircraft.on_ground
    assert aircraft.heading == runway_heading
    assert len(aircraft.flight_plan.waypoints) > 0


def test_generate_arrival(generator):
    """Test arrival generation."""
    airport_pos = Vector3(0, 0, 0)
    runway_heading = 90.0
    entry_distance = 10.0

    aircraft = generator.generate_arrival(
        airport_position=airport_pos,
        runway_heading=runway_heading,
        airport_elevation_ft=100,
        entry_distance_nm=entry_distance,
    )

    assert aircraft.callsign.startswith("AI")
    assert not aircraft.on_ground
    assert aircraft.altitude_ft > 100  # Should start at pattern altitude
    assert aircraft.airspeed_kts > 0
    assert len(aircraft.flight_plan.waypoints) > 0

    # Should be positioned away from airport
    distance = aircraft.get_distance_to(airport_pos)
    assert distance > entry_distance * 0.8  # Allow some tolerance


def test_generate_pattern_traffic(generator):
    """Test pattern traffic generation."""
    airport_pos = Vector3(0, 0, 0)
    runway_heading = 90.0
    count = 3

    aircraft_list = generator.generate_pattern_traffic(
        airport_position=airport_pos,
        runway_heading=runway_heading,
        airport_elevation_ft=100,
        count=count,
    )

    assert len(aircraft_list) == count

    for aircraft in aircraft_list:
        assert aircraft.callsign.startswith("AI")
        assert not aircraft.on_ground
        assert aircraft.altitude_ft > 100  # Pattern altitude
        assert aircraft.airspeed_kts > 0
        assert len(aircraft.flight_plan.waypoints) > 0


def test_pattern_waypoints_structure(generator):
    """Test pattern waypoint structure."""
    airport_pos = Vector3(0, 0, 0)
    runway_heading = 90.0

    aircraft_list = generator.generate_pattern_traffic(
        airport_position=airport_pos,
        runway_heading=runway_heading,
        airport_elevation_ft=100,
        count=1,
    )

    aircraft = aircraft_list[0]
    waypoints = aircraft.flight_plan.waypoints

    # Pattern should have multiple waypoints (upwind, crosswind, downwind, base, final, threshold)
    assert len(waypoints) >= 5

    # Check waypoint names
    waypoint_names = [wp.name for wp in waypoints]
    assert "UPWIND" in waypoint_names or "DOWNWIND" in waypoint_names


def test_multiple_departures_have_unique_callsigns(generator):
    """Test that multiple departures get unique callsigns."""
    airport_pos = Vector3(0, 0, 0)
    runway_heading = 90.0

    aircraft1 = generator.generate_departure(airport_pos, runway_heading)
    aircraft2 = generator.generate_departure(airport_pos, runway_heading)

    assert aircraft1.callsign != aircraft2.callsign


def test_project_position_north(generator):
    """Test position projection northward."""
    start = Vector3(0, 0, 0)
    heading = 0.0  # North
    distance = 1000.0  # meters

    result = generator._project_position(start, heading, distance)

    assert abs(result.x - start.x) < 0.1  # Should not move in x
    assert result.y == start.y  # Should not move in y
    assert abs(result.z - (start.z + distance)) < 0.1  # Should move north


def test_project_position_east(generator):
    """Test position projection eastward."""
    start = Vector3(0, 0, 0)
    heading = 90.0  # East
    distance = 1000.0  # meters

    result = generator._project_position(start, heading, distance)

    assert abs(result.x - (start.x + distance)) < 0.1  # Should move east
    assert result.y == start.y  # Should not move in y
    assert abs(result.z - start.z) < 0.1  # Should not move in z

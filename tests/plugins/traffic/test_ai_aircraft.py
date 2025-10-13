"""Tests for AI aircraft."""

from airborne.physics.vectors import Vector3
from airborne.plugins.traffic.ai_aircraft import (
    AIAircraft,
    FlightPlan,
    Waypoint,
)


def test_waypoint_creation():
    """Test waypoint creation."""
    wp = Waypoint(
        position=Vector3(100, 200, 300),
        altitude_ft=5000,
        speed_kts=120,
        name="TEST",
    )
    assert wp.position.x == 100
    assert wp.altitude_ft == 5000
    assert wp.speed_kts == 120
    assert wp.name == "TEST"


def test_flight_plan_basic():
    """Test basic flight plan operations."""
    fp = FlightPlan(
        waypoints=[
            Waypoint(Vector3(0, 0, 0), 1000, 100),
            Waypoint(Vector3(1000, 1000, 1000), 2000, 120),
        ]
    )

    assert not fp.is_complete()
    assert fp.get_current_waypoint() is not None
    assert fp.get_current_waypoint().altitude_ft == 1000

    assert fp.advance_waypoint()
    assert fp.get_current_waypoint().altitude_ft == 2000

    # Can't advance past end
    assert not fp.advance_waypoint()
    # At last waypoint, but not yet complete (complete = index >= len)
    assert not fp.is_complete()


def test_ai_aircraft_creation():
    """Test AI aircraft creation."""
    aircraft = AIAircraft(
        callsign="TEST123",
        aircraft_type="C172",
        position=Vector3(0, 1000, 0),
        heading=90.0,
        altitude_ft=5000,
        airspeed_kts=100,
    )

    assert aircraft.callsign == "TEST123"
    assert aircraft.aircraft_type == "C172"
    assert aircraft.heading == 90.0
    assert aircraft.altitude_ft == 5000
    assert aircraft.airspeed_kts == 100


def test_ai_aircraft_update_position():
    """Test AI aircraft position updates."""
    aircraft = AIAircraft(
        callsign="TEST123",
        aircraft_type="C172",
        position=Vector3(0, 1000, 0),
        heading=0.0,  # North
        altitude_ft=5000,
        airspeed_kts=100,
        vertical_speed_fpm=0,
    )

    initial_pos = aircraft.position
    aircraft.update(1.0)  # Update 1 second

    # Should have moved north (positive z)
    assert aircraft.position.z > initial_pos.z
    # Should have moved ~51.4 meters (100 kts = 51.4 m/s)
    assert abs(aircraft.position.z - initial_pos.z - 51.4) < 1.0


def test_ai_aircraft_follows_flight_plan():
    """Test AI aircraft following flight plan."""
    # Create aircraft at origin
    aircraft = AIAircraft(
        callsign="TEST123",
        aircraft_type="C172",
        position=Vector3(0, 1000, 0),
        heading=0.0,
        altitude_ft=1000,
        airspeed_kts=100,
    )

    # Create flight plan with waypoint to the north
    waypoint = Waypoint(
        position=Vector3(0, 2000, 6076),  # 1 NM north, 1000 ft higher
        altitude_ft=2000,
        speed_kts=120,
    )
    aircraft.flight_plan = FlightPlan(waypoints=[waypoint])

    # Update for several seconds
    for _ in range(60):  # 60 seconds
        aircraft.update(1.0)

    # Should be climbing
    assert aircraft.altitude_ft > 1000

    # Should be heading north (heading ~0)
    assert abs(aircraft.heading) < 10 or abs(aircraft.heading - 360) < 10


def test_ai_aircraft_distance_calculation():
    """Test distance calculation between aircraft."""
    aircraft1 = AIAircraft(
        callsign="TEST1",
        aircraft_type="C172",
        position=Vector3(0, 1000, 0),
        heading=0,
        altitude_ft=1000,
        airspeed_kts=100,
    )

    # Position 2 at 6076 meters north (1 NM)
    position2 = Vector3(0, 1000, 6076)

    distance = aircraft1.get_distance_to(position2)
    assert abs(distance - 1.0) < 0.01  # Should be ~1 NM


def test_ai_aircraft_closure_rate():
    """Test closure rate calculation."""
    # Aircraft 1 heading north at 100 kts
    aircraft1 = AIAircraft(
        callsign="TEST1",
        aircraft_type="C172",
        position=Vector3(0, 1000, 0),
        heading=0,
        altitude_ft=1000,
        airspeed_kts=100,
        velocity=Vector3(0, 0, 51.4),  # ~100 kts north
    )

    # Aircraft 2 heading south at 100 kts, 10 NM away
    aircraft2 = AIAircraft(
        callsign="TEST2",
        aircraft_type="C172",
        position=Vector3(0, 1000, 60760),  # 10 NM north
        heading=180,
        altitude_ft=1000,
        airspeed_kts=100,
        velocity=Vector3(0, 0, -51.4),  # ~100 kts south
    )

    # Closure rate should be positive (closing)
    closure_rate = aircraft1.get_closure_rate(aircraft2)
    assert closure_rate > 0  # Closing


def test_ai_aircraft_random_creation():
    """Test random aircraft creation."""
    aircraft = AIAircraft.create_random(
        callsign="RANDOM",
        position=Vector3(0, 1000, 0),
        aircraft_type="C172",
    )

    assert aircraft.callsign == "RANDOM"
    assert aircraft.aircraft_type == "C172"
    assert 0 <= aircraft.heading <= 360
    assert 1000 <= aircraft.altitude_ft <= 10000
    assert 80 <= aircraft.airspeed_kts <= 150

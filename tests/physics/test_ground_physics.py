"""Tests for Ground Physics."""

import math

import pytest

from airborne.physics.ground_physics import GroundContact, GroundPhysics
from airborne.physics.vectors import Vector3


class TestGroundPhysicsBasics:
    """Test basic ground physics functionality."""

    @pytest.fixture
    def ground(self) -> GroundPhysics:
        """Create ground physics for testing."""
        return GroundPhysics(mass_kg=1000, max_brake_force_n=15000, max_steering_angle_deg=60)

    def test_no_forces_when_airborne(self, ground: GroundPhysics) -> None:
        """Test that no ground forces when airborne."""
        contact = GroundContact(on_ground=False)
        forces = ground.calculate_ground_forces(contact)

        assert forces.total_force.magnitude() == 0.0

    def test_friction_force_opposes_motion(self, ground: GroundPhysics) -> None:
        """Test that friction opposes direction of motion."""
        contact = GroundContact(
            on_ground=True, gear_compression=1.0, ground_speed_mps=10.0, heading_deg=0
        )

        velocity = Vector3(0, 0, 10)  # Moving north
        forces = ground.calculate_ground_forces(contact, velocity=velocity)

        # Friction should oppose motion (point south)
        assert forces.friction_force.z < 0

    def test_brake_force_opposes_motion(self, ground: GroundPhysics) -> None:
        """Test that braking force opposes motion."""
        contact = GroundContact(
            on_ground=True, gear_compression=1.0, ground_speed_mps=20.0, heading_deg=0
        )

        velocity = Vector3(0, 0, 20)
        forces = ground.calculate_ground_forces(contact, brake_input=0.5, velocity=velocity)

        # Brake force should oppose motion
        assert forces.brake_force.z < 0
        assert forces.brake_force.magnitude() > 0

    def test_no_brake_force_when_stationary(self, ground: GroundPhysics) -> None:
        """Test that no brake force when stationary."""
        contact = GroundContact(
            on_ground=True, gear_compression=1.0, ground_speed_mps=0.0, heading_deg=0
        )

        forces = ground.calculate_ground_forces(contact, brake_input=1.0)

        assert forces.brake_force.magnitude() == 0.0


class TestSurfaceFriction:
    """Test friction on different surfaces."""

    @pytest.fixture
    def ground(self) -> GroundPhysics:
        """Create ground physics for testing."""
        return GroundPhysics(mass_kg=1000)

    def test_asphalt_friction(self, ground: GroundPhysics) -> None:
        """Test friction on asphalt."""
        contact = GroundContact(
            on_ground=True,
            gear_compression=1.0,
            surface_type="asphalt",
            ground_speed_mps=10.0,
        )

        velocity = Vector3(0, 0, 10)
        forces = ground.calculate_ground_forces(contact, velocity=velocity)

        # Asphalt should have good friction
        assert forces.friction_force.magnitude() > 7000  # High friction

    def test_grass_friction(self, ground: GroundPhysics) -> None:
        """Test friction on grass."""
        contact = GroundContact(
            on_ground=True,
            gear_compression=1.0,
            surface_type="grass",
            ground_speed_mps=10.0,
        )

        velocity = Vector3(0, 0, 10)
        forces = ground.calculate_ground_forces(contact, velocity=velocity)

        # Grass should have less friction than asphalt
        assert forces.friction_force.magnitude() > 3000
        assert forces.friction_force.magnitude() < 5000

    def test_ice_friction(self, ground: GroundPhysics) -> None:
        """Test friction on ice."""
        contact = GroundContact(
            on_ground=True,
            gear_compression=1.0,
            surface_type="ice",
            ground_speed_mps=10.0,
        )

        velocity = Vector3(0, 0, 10)
        forces = ground.calculate_ground_forces(contact, velocity=velocity)

        # Ice should have very low friction
        assert forces.friction_force.magnitude() < 1500


class TestSteering:
    """Test nosewheel steering."""

    @pytest.fixture
    def ground(self) -> GroundPhysics:
        """Create ground physics for testing."""
        return GroundPhysics(mass_kg=1000, max_steering_angle_deg=60)

    def test_steering_creates_lateral_force(self, ground: GroundPhysics) -> None:
        """Test that steering creates lateral force."""
        contact = GroundContact(
            on_ground=True, gear_compression=1.0, ground_speed_mps=5.0, heading_deg=0
        )

        # Steer right (positive rudder)
        velocity = Vector3(0, 0, 5)  # Moving north
        forces = ground.calculate_ground_forces(contact, rudder_input=0.5, velocity=velocity)

        # Should have rightward (positive X) steering force
        assert forces.steering_force.x > 0

    def test_no_steering_when_stationary(self, ground: GroundPhysics) -> None:
        """Test that steering doesn't work when stationary."""
        contact = GroundContact(
            on_ground=True, gear_compression=1.0, ground_speed_mps=0.0, heading_deg=0
        )

        forces = ground.calculate_ground_forces(contact, rudder_input=1.0)

        # No lateral force when not moving
        assert forces.steering_force.magnitude() < 0.1

    def test_steering_less_effective_at_high_speed(self, ground: GroundPhysics) -> None:
        """Test that steering is less effective at high speeds."""
        contact_slow = GroundContact(
            on_ground=True, gear_compression=1.0, ground_speed_mps=5.0, heading_deg=0
        )

        contact_fast = GroundContact(
            on_ground=True, gear_compression=1.0, ground_speed_mps=40.0, heading_deg=0
        )

        velocity_slow = Vector3(0, 0, 5)
        velocity_fast = Vector3(0, 0, 40)

        forces_slow = ground.calculate_ground_forces(
            contact_slow, rudder_input=1.0, velocity=velocity_slow
        )
        forces_fast = ground.calculate_ground_forces(
            contact_fast, rudder_input=1.0, velocity=velocity_fast
        )

        # Steering should be less effective at high speed
        assert forces_slow.steering_force.magnitude() > forces_fast.steering_force.magnitude()


class TestTurningRadius:
    """Test turning radius calculations."""

    @pytest.fixture
    def ground(self) -> GroundPhysics:
        """Create ground physics for testing."""
        return GroundPhysics()

    def test_straight_line_infinite_radius(self, ground: GroundPhysics) -> None:
        """Test that straight line has infinite turning radius."""
        radius = ground.calculate_turning_radius(10, 0)
        assert math.isinf(radius)

    def test_right_turn_positive_radius(self, ground: GroundPhysics) -> None:
        """Test that right turn has positive radius."""
        radius = ground.calculate_turning_radius(10, 30)
        assert radius > 0

    def test_left_turn_negative_radius(self, ground: GroundPhysics) -> None:
        """Test that left turn has negative radius."""
        radius = ground.calculate_turning_radius(10, -30)
        assert radius < 0

    def test_sharper_turn_smaller_radius(self, ground: GroundPhysics) -> None:
        """Test that sharper turn has smaller radius."""
        radius_gentle = ground.calculate_turning_radius(10, 15, wheelbase_m=3)
        radius_sharp = ground.calculate_turning_radius(10, 45, wheelbase_m=3)

        assert abs(radius_sharp) < abs(radius_gentle)


class TestStoppingDistance:
    """Test stopping distance calculations."""

    @pytest.fixture
    def ground(self) -> GroundPhysics:
        """Create ground physics for testing."""
        return GroundPhysics()

    def test_zero_speed_zero_distance(self, ground: GroundPhysics) -> None:
        """Test that zero initial speed gives zero stopping distance."""
        distance = ground.calculate_stopping_distance(0)
        assert distance == 0.0

    def test_higher_speed_longer_distance(self, ground: GroundPhysics) -> None:
        """Test that higher speed requires longer stopping distance."""
        dist_slow = ground.calculate_stopping_distance(10)
        dist_fast = ground.calculate_stopping_distance(30)

        assert dist_fast > dist_slow

    def test_better_brakes_shorter_distance(self, ground: GroundPhysics) -> None:
        """Test that better brake efficiency gives shorter stopping distance."""
        dist_poor_brakes = ground.calculate_stopping_distance(20, brake_efficiency=0.5)
        dist_good_brakes = ground.calculate_stopping_distance(20, brake_efficiency=1.0)

        assert dist_good_brakes < dist_poor_brakes

    def test_grass_longer_distance(self, ground: GroundPhysics) -> None:
        """Test that grass requires longer stopping distance than asphalt."""
        dist_asphalt = ground.calculate_stopping_distance(20, surface_type="asphalt")
        dist_grass = ground.calculate_stopping_distance(20, surface_type="grass")

        assert dist_grass > dist_asphalt


class TestTaxiSpeed:
    """Test taxi speed safety checks."""

    @pytest.fixture
    def ground(self) -> GroundPhysics:
        """Create ground physics for testing."""
        return GroundPhysics()

    def test_slow_speed_safe(self, ground: GroundPhysics) -> None:
        """Test that slow speeds are safe for taxi."""
        assert ground.is_safe_taxi_speed(5.0)  # ~10 knots

    def test_high_speed_unsafe(self, ground: GroundPhysics) -> None:
        """Test that high speeds are unsafe for taxi."""
        assert not ground.is_safe_taxi_speed(20.0, max_taxi_speed_mps=10.0)

    def test_zero_speed_safe(self, ground: GroundPhysics) -> None:
        """Test that zero speed is safe."""
        assert ground.is_safe_taxi_speed(0.0)


class TestRealWorldScenarios:
    """Test real-world ground operations scenarios."""

    @pytest.fixture
    def cessna_ground(self) -> GroundPhysics:
        """Create ground physics for Cessna 172."""
        return GroundPhysics(
            mass_kg=1111,  # Cessna 172 max weight
            max_brake_force_n=10000,
            max_steering_angle_deg=60,
        )

    def test_cessna_taxi_turn(self, cessna_ground: GroundPhysics) -> None:
        """Test Cessna 172 taxi turn."""
        # Typical taxi speed: 10 knots = ~5 m/s
        contact = GroundContact(
            on_ground=True,
            gear_compression=0.9,
            surface_type="asphalt",
            ground_speed_mps=5.0,
        )

        velocity = Vector3(0, 0, 5)
        forces = cessna_ground.calculate_ground_forces(contact, rudder_input=0.5, velocity=velocity)

        # Should have steering force
        assert forces.steering_force.magnitude() > 0

        # Total force should be reasonable (friction + rolling + steering)
        assert forces.total_force.magnitude() < 10000

    def test_cessna_landing_rollout(self, cessna_ground: GroundPhysics) -> None:
        """Test Cessna 172 landing rollout with braking."""
        # Landing speed: ~50 knots = ~25 m/s
        contact = GroundContact(
            on_ground=True,
            gear_compression=1.0,
            surface_type="asphalt",
            ground_speed_mps=25.0,
        )

        velocity = Vector3(0, 0, 25)
        forces = cessna_ground.calculate_ground_forces(contact, brake_input=0.7, velocity=velocity)

        # Should have significant braking force
        assert forces.brake_force.magnitude() > 5000

        # Brake force should oppose motion
        assert forces.brake_force.z < 0

    def test_cessna_grass_runway(self, cessna_ground: GroundPhysics) -> None:
        """Test Cessna 172 on grass runway."""
        contact_asphalt = GroundContact(
            on_ground=True,
            gear_compression=1.0,
            surface_type="asphalt",
            ground_speed_mps=10.0,
        )

        contact_grass = GroundContact(
            on_ground=True,
            gear_compression=1.0,
            surface_type="grass",
            ground_speed_mps=10.0,
        )

        velocity = Vector3(0, 0, 10)

        forces_asphalt = cessna_ground.calculate_ground_forces(contact_asphalt, velocity=velocity)
        forces_grass = cessna_ground.calculate_ground_forces(contact_grass, velocity=velocity)

        # Grass should have more rolling resistance
        assert (
            forces_grass.rolling_resistance.magnitude()
            > forces_asphalt.rolling_resistance.magnitude()
        )

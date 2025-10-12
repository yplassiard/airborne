"""Tests for Simple6DOFFlightModel."""

import math

import pytest

from airborne.physics.flight_model.base import AircraftState, ControlInputs
from airborne.physics.flight_model.simple_6dof import Simple6DOFFlightModel
from airborne.physics.vectors import Vector3


class TestSimple6DOFInitialization:
    """Test Simple6DOFFlightModel initialization."""

    def test_initialize_with_required_params(self) -> None:
        """Test initialization with required parameters."""
        model = Simple6DOFFlightModel()
        config = {
            "wing_area_sqft": 174.0,
            "weight_lbs": 2400.0,
            "max_thrust_lbs": 300.0,
        }
        model.initialize(config)

        # Check conversions (imperial to metric)
        assert model.wing_area == pytest.approx(174.0 * 0.092903)
        assert model.empty_mass == pytest.approx(2400.0 * 0.453592)
        assert model.max_thrust == pytest.approx(300.0 * 4.44822)

    def test_initialize_with_optional_params(self) -> None:
        """Test initialization with optional parameters."""
        model = Simple6DOFFlightModel()
        config = {
            "wing_area_sqft": 174.0,
            "weight_lbs": 2400.0,
            "max_thrust_lbs": 300.0,
            "drag_coefficient": 0.03,
            "fuel_capacity_lbs": 200.0,
        }
        model.initialize(config)

        assert model.drag_coefficient == 0.03
        assert model.max_fuel == pytest.approx(200.0 * 0.453592)

    def test_initialize_missing_wing_area(self) -> None:
        """Test initialization fails without wing_area_sqft."""
        model = Simple6DOFFlightModel()
        config = {"weight_lbs": 2400.0, "max_thrust_lbs": 300.0}
        with pytest.raises(ValueError, match="wing_area_sqft required"):
            model.initialize(config)

    def test_initialize_missing_weight(self) -> None:
        """Test initialization fails without weight_lbs."""
        model = Simple6DOFFlightModel()
        config = {"wing_area_sqft": 174.0, "max_thrust_lbs": 300.0}
        with pytest.raises(ValueError, match="weight_lbs required"):
            model.initialize(config)

    def test_initialize_missing_thrust(self) -> None:
        """Test initialization fails without max_thrust_lbs."""
        model = Simple6DOFFlightModel()
        config = {"wing_area_sqft": 174.0, "weight_lbs": 2400.0}
        with pytest.raises(ValueError, match="max_thrust_lbs required"):
            model.initialize(config)

    def test_initial_state_after_initialize(self) -> None:
        """Test initial state is set correctly after initialization."""
        model = Simple6DOFFlightModel()
        config = {
            "wing_area_sqft": 174.0,
            "weight_lbs": 2400.0,
            "max_thrust_lbs": 300.0,
        }
        model.initialize(config)

        state = model.get_state()
        # Mass = empty mass + full fuel
        assert state.mass == pytest.approx(model.empty_mass + model.max_fuel)
        assert state.fuel == pytest.approx(model.max_fuel)


class TestSimple6DOFPhysicsUpdate:
    """Test Simple6DOFFlightModel physics updates."""

    @pytest.fixture
    def model(self) -> Simple6DOFFlightModel:
        """Create and initialize a flight model."""
        model = Simple6DOFFlightModel()
        config = {
            "wing_area_sqft": 174.0,
            "weight_lbs": 2400.0,
            "max_thrust_lbs": 300.0,
        }
        model.initialize(config)
        return model

    def test_update_increments_counter(self, model: Simple6DOFFlightModel) -> None:
        """Test update increments the update counter."""
        initial_count = model.get_update_count()
        inputs = ControlInputs()
        model.update(dt=0.016, inputs=inputs)
        assert model.get_update_count() == initial_count + 1

    def test_gravity_pulls_down(self, model: Simple6DOFFlightModel) -> None:
        """Test gravity causes downward acceleration."""
        # Start at altitude with zero velocity
        initial_state = AircraftState(position=Vector3(0.0, 1000.0, 0.0), velocity=Vector3.zero())
        model.reset(initial_state)

        # Update with no inputs (only gravity)
        inputs = ControlInputs()
        state = model.update(dt=0.016, inputs=inputs)

        # Should have negative Y velocity (falling)
        assert state.velocity.y < 0.0
        # Position should decrease
        assert state.position.y < 1000.0

    def test_thrust_accelerates_forward(self, model: Simple6DOFFlightModel) -> None:
        """Test throttle creates forward thrust."""
        initial_state = AircraftState(
            position=Vector3(0.0, 1000.0, 0.0), velocity=Vector3(10.0, 0.0, 0.0)
        )
        model.reset(initial_state)

        # Apply full throttle
        inputs = ControlInputs(throttle=1.0)
        model.update(dt=0.016, inputs=inputs)

        # Thrust should be positive
        forces = model.get_forces()
        assert forces.thrust.magnitude() > 0.0

    def test_velocity_integration(self, model: Simple6DOFFlightModel) -> None:
        """Test velocity changes during update."""
        initial_state = AircraftState(
            position=Vector3(0.0, 1000.0, 0.0),
            velocity=Vector3(50.0, 0.0, 0.0),
        )
        model.reset(initial_state)
        initial_velocity = Vector3(
            initial_state.velocity.x, initial_state.velocity.y, initial_state.velocity.z
        )

        inputs = ControlInputs()
        dt = 1.0
        state = model.update(dt=dt, inputs=inputs)

        # Velocity should have changed (drag slows it down, gravity pulls down)
        # Check that velocity magnitude or Y component changed
        velocity_changed = (
            abs(state.velocity.magnitude() - initial_velocity.magnitude()) > 0.01
            or abs(state.velocity.y - initial_velocity.y) > 0.01
        )
        assert velocity_changed

    def test_position_integration(self, model: Simple6DOFFlightModel) -> None:
        """Test position changes based on velocity."""
        initial_state = AircraftState(
            position=Vector3(0.0, 1000.0, 0.0), velocity=Vector3(50.0, 0.0, 0.0)
        )
        model.reset(initial_state)
        initial_pos = Vector3(
            initial_state.position.x, initial_state.position.y, initial_state.position.z
        )

        inputs = ControlInputs()
        dt = 1.0
        state = model.update(dt=dt, inputs=inputs)

        # Position should have changed
        position_changed = (
            abs(state.position.x - initial_pos.x) > 0.01
            or abs(state.position.y - initial_pos.y) > 0.01
            or abs(state.position.z - initial_pos.z) > 0.01
        )
        assert position_changed

    def test_fuel_consumption(self, model: Simple6DOFFlightModel) -> None:
        """Test fuel is consumed with throttle."""
        initial_fuel = model.state.fuel

        # Run with full throttle
        inputs = ControlInputs(throttle=1.0)
        for _ in range(10):
            model.update(dt=0.016, inputs=inputs)

        # Fuel should decrease
        assert model.state.fuel < initial_fuel

    def test_fuel_consumption_idle(self, model: Simple6DOFFlightModel) -> None:
        """Test no fuel consumption at idle."""
        initial_fuel = model.state.fuel

        # Run with no throttle
        inputs = ControlInputs(throttle=0.0)
        for _ in range(10):
            model.update(dt=0.016, inputs=inputs)

        # Fuel should not change (or change very little)
        assert model.state.fuel == pytest.approx(initial_fuel, rel=1e-6)

    def test_mass_decreases_with_fuel(self, model: Simple6DOFFlightModel) -> None:
        """Test aircraft mass decreases as fuel burns."""
        initial_mass = model.state.mass

        # Burn fuel
        inputs = ControlInputs(throttle=1.0)
        for _ in range(100):
            model.update(dt=0.1, inputs=inputs)

        # Mass should decrease
        assert model.state.mass < initial_mass
        # Mass should be empty mass + remaining fuel
        assert model.state.mass == pytest.approx(model.empty_mass + model.state.fuel)

    def test_ground_collision_stops_descent(self, model: Simple6DOFFlightModel) -> None:
        """Test ground collision prevents going below Y=0."""
        initial_state = AircraftState(
            position=Vector3(0.0, 1.0, 0.0), velocity=Vector3(0.0, -10.0, 0.0)
        )
        model.reset(initial_state)

        # Update with downward velocity
        inputs = ControlInputs()
        state = model.update(dt=0.2, inputs=inputs)

        # Should be on ground
        assert state.position.y == 0.0
        assert state.on_ground is True
        # Downward velocity should be stopped
        assert state.velocity.y >= 0.0


class TestSimple6DOFForceCalculation:
    """Test force calculation methods."""

    @pytest.fixture
    def model(self) -> Simple6DOFFlightModel:
        """Create and initialize a flight model."""
        model = Simple6DOFFlightModel()
        config = {
            "wing_area_sqft": 174.0,
            "weight_lbs": 2400.0,
            "max_thrust_lbs": 300.0,
        }
        model.initialize(config)
        return model

    def test_weight_force(self, model: Simple6DOFFlightModel) -> None:
        """Test weight force is always downward."""
        inputs = ControlInputs()
        model.update(dt=0.016, inputs=inputs)

        forces = model.get_forces()
        # Weight should point down (negative Y)
        assert forces.weight.y < 0.0
        # Weight magnitude should be mass * gravity
        expected_weight = model.state.mass * 9.81
        assert forces.weight.magnitude() == pytest.approx(expected_weight)

    def test_lift_increases_with_speed(self, model: Simple6DOFFlightModel) -> None:
        """Test lift increases with airspeed."""
        # Test at two different speeds
        state1 = AircraftState(
            position=Vector3(0.0, 1000.0, 0.0),
            velocity=Vector3(20.0, 0.0, 0.0),
            rotation=Vector3(0.1, 0.0, 0.0),  # Small pitch
        )
        model.reset(state1)
        model.update(dt=0.016, inputs=ControlInputs())
        forces1 = model.get_forces()
        lift1 = forces1.lift.magnitude()

        state2 = AircraftState(
            position=Vector3(0.0, 1000.0, 0.0),
            velocity=Vector3(40.0, 0.0, 0.0),  # Double speed
            rotation=Vector3(0.1, 0.0, 0.0),
        )
        model.reset(state2)
        model.update(dt=0.016, inputs=ControlInputs())
        forces2 = model.get_forces()
        lift2 = forces2.lift.magnitude()

        # Lift proportional to v², so doubling speed should ~quadruple lift
        assert lift2 > lift1 * 3.5  # Allow some tolerance

    def test_drag_opposes_velocity(self, model: Simple6DOFFlightModel) -> None:
        """Test drag force opposes velocity direction."""
        state = AircraftState(position=Vector3(0.0, 1000.0, 0.0), velocity=Vector3(50.0, 0.0, 0.0))
        model.reset(state)
        model.update(dt=0.016, inputs=ControlInputs())

        forces = model.get_forces()
        # Drag should have negative X component (opposes +X velocity)
        assert forces.drag.x < 0.0

    def test_thrust_scales_with_throttle(self, model: Simple6DOFFlightModel) -> None:
        """Test thrust is proportional to throttle setting."""
        state = AircraftState(position=Vector3(0.0, 1000.0, 0.0), velocity=Vector3(30.0, 0.0, 0.0))

        # Test 50% throttle
        model.reset(state)
        model.update(dt=0.016, inputs=ControlInputs(throttle=0.5))
        thrust_50 = model.get_forces().thrust.magnitude()

        # Test 100% throttle
        model.reset(state)
        model.update(dt=0.016, inputs=ControlInputs(throttle=1.0))
        thrust_100 = model.get_forces().thrust.magnitude()

        # 100% throttle should produce ~2x thrust
        assert thrust_100 == pytest.approx(thrust_50 * 2.0, rel=0.01)


class TestSimple6DOFRotation:
    """Test rotation and angular velocity updates."""

    @pytest.fixture
    def model(self) -> Simple6DOFFlightModel:
        """Create and initialize a flight model."""
        model = Simple6DOFFlightModel()
        config = {
            "wing_area_sqft": 174.0,
            "weight_lbs": 2400.0,
            "max_thrust_lbs": 300.0,
        }
        model.initialize(config)
        return model

    def test_pitch_input_changes_rotation(self, model: Simple6DOFFlightModel) -> None:
        """Test pitch input changes pitch angle."""
        initial_pitch = model.state.rotation.x

        # Apply positive pitch input
        inputs = ControlInputs(pitch=1.0)
        for _ in range(10):
            model.update(dt=0.016, inputs=inputs)

        # Pitch should increase
        assert model.state.rotation.x > initial_pitch

    def test_roll_input_changes_rotation(self, model: Simple6DOFFlightModel) -> None:
        """Test roll input changes roll angle."""
        initial_roll = model.state.rotation.y

        # Apply positive roll input
        inputs = ControlInputs(roll=1.0)
        for _ in range(10):
            model.update(dt=0.016, inputs=inputs)

        # Roll should change
        assert model.state.rotation.y != initial_roll

    def test_yaw_input_changes_rotation(self, model: Simple6DOFFlightModel) -> None:
        """Test yaw input changes heading."""
        initial_yaw = model.state.rotation.z

        # Apply positive yaw input
        inputs = ControlInputs(yaw=1.0)
        for _ in range(10):
            model.update(dt=0.016, inputs=inputs)

        # Yaw should change
        assert model.state.rotation.z != initial_yaw

    def test_rotation_normalization(self, model: Simple6DOFFlightModel) -> None:
        """Test rotation angles are normalized to -π to π."""
        # Apply large rotation
        inputs = ControlInputs(yaw=1.0)
        for _ in range(1000):
            model.update(dt=0.01, inputs=inputs)

        # All angles should be within -π to π
        assert -math.pi <= model.state.rotation.x <= math.pi
        assert -math.pi <= model.state.rotation.y <= math.pi
        assert -math.pi <= model.state.rotation.z <= math.pi

    def test_angular_velocity_from_inputs(self, model: Simple6DOFFlightModel) -> None:
        """Test angular velocity is set based on control inputs."""
        inputs = ControlInputs(pitch=0.5, roll=-0.3, yaw=0.2)
        model.update(dt=0.016, inputs=inputs)

        # Angular velocity should be non-zero
        assert model.state.angular_velocity != Vector3.zero()


class TestSimple6DOFExternalForces:
    """Test external force application."""

    @pytest.fixture
    def model(self) -> Simple6DOFFlightModel:
        """Create and initialize a flight model."""
        model = Simple6DOFFlightModel()
        config = {
            "wing_area_sqft": 174.0,
            "weight_lbs": 2400.0,
            "max_thrust_lbs": 300.0,
        }
        model.initialize(config)
        return model

    def test_apply_external_force(self, model: Simple6DOFFlightModel) -> None:
        """Test applying external force affects motion."""
        initial_state = AircraftState(
            position=Vector3(0.0, 1000.0, 0.0), velocity=Vector3(50.0, 0.0, 0.0)
        )
        model.reset(initial_state)

        # Apply strong sideways force (wind gust)
        wind_force = Vector3(0.0, 0.0, 1000.0)
        model.apply_force(wind_force, Vector3.zero())

        # Update
        inputs = ControlInputs()
        state = model.update(dt=0.1, inputs=inputs)

        # Should have Z velocity from wind (check for change greater than rounding)
        assert abs(state.velocity.z) > 0.01

    def test_external_force_decay(self, model: Simple6DOFFlightModel) -> None:
        """Test external forces decay over time."""
        # Apply force
        model.apply_force(Vector3(1000.0, 0.0, 0.0), Vector3.zero())

        # Update multiple times
        inputs = ControlInputs()
        for _ in range(10):
            model.update(dt=0.1, inputs=inputs)

        # External force should have decayed
        assert model.external_force.magnitude() < 1000.0


class TestSimple6DOFReset:
    """Test reset functionality."""

    @pytest.fixture
    def model(self) -> Simple6DOFFlightModel:
        """Create and initialize a flight model."""
        model = Simple6DOFFlightModel()
        config = {
            "wing_area_sqft": 174.0,
            "weight_lbs": 2400.0,
            "max_thrust_lbs": 300.0,
        }
        model.initialize(config)
        return model

    def test_reset_changes_state(self, model: Simple6DOFFlightModel) -> None:
        """Test reset changes aircraft state."""
        # Run some updates
        inputs = ControlInputs(throttle=1.0)
        for _ in range(10):
            model.update(dt=0.1, inputs=inputs)

        # Reset to new state
        new_state = AircraftState(
            position=Vector3(1000.0, 2000.0, 3000.0),
            velocity=Vector3(100.0, 0.0, 0.0),
        )
        model.reset(new_state)

        # State should match new state
        state = model.get_state()
        assert state.position == new_state.position
        assert state.velocity == new_state.velocity

    def test_reset_clears_external_forces(self, model: Simple6DOFFlightModel) -> None:
        """Test reset clears external forces."""
        # Apply external force
        model.apply_force(Vector3(1000.0, 0.0, 0.0), Vector3.zero())

        # Reset
        new_state = AircraftState()
        model.reset(new_state)

        # External force should be cleared
        assert model.external_force == Vector3.zero()

    def test_reset_clears_update_counter(self, model: Simple6DOFFlightModel) -> None:
        """Test reset clears update counter."""
        # Run some updates
        inputs = ControlInputs()
        for _ in range(10):
            model.update(dt=0.016, inputs=inputs)

        assert model.get_update_count() > 0

        # Reset
        model.reset(AircraftState())

        # Counter should be reset
        assert model.get_update_count() == 0


class TestSimple6DOFPerformance:
    """Test performance-related functionality."""

    @pytest.fixture
    def model(self) -> Simple6DOFFlightModel:
        """Create and initialize a flight model."""
        model = Simple6DOFFlightModel()
        config = {
            "wing_area_sqft": 174.0,
            "weight_lbs": 2400.0,
            "max_thrust_lbs": 300.0,
        }
        model.initialize(config)
        return model

    def test_cached_trig_values(self, model: Simple6DOFFlightModel) -> None:
        """Test trig values are cached for performance."""
        # Update with rotation
        inputs = ControlInputs(pitch=0.5)
        model.update(dt=0.016, inputs=inputs)

        # Cached values should be set
        assert model._trig_dirty is True  # Set dirty after rotation change

        # Another update should use cached values
        inputs = ControlInputs()
        model.update(dt=0.016, inputs=inputs)

        # After update, trig values are calculated
        assert model._cos_pitch != 0.0 or model._sin_pitch != 0.0

    def test_update_counter_increments(self, model: Simple6DOFFlightModel) -> None:
        """Test update counter for performance monitoring."""
        initial = model.get_update_count()

        # Run updates
        inputs = ControlInputs()
        num_updates = 100
        for _ in range(num_updates):
            model.update(dt=0.016, inputs=inputs)

        # Counter should increment correctly
        assert model.get_update_count() == initial + num_updates

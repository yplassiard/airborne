"""Tests for flight model base classes."""

import pytest

from airborne.physics.flight_model.base import (
    AircraftState,
    ControlInputs,
    FlightForces,
)
from airborne.physics.vectors import Vector3


class TestControlInputs:
    """Test ControlInputs dataclass."""

    def test_default_values(self) -> None:
        """Test default control inputs are all zero/neutral."""
        inputs = ControlInputs()
        assert inputs.pitch == 0.0
        assert inputs.roll == 0.0
        assert inputs.yaw == 0.0
        assert inputs.throttle == 0.0
        assert inputs.flaps == 0.0
        assert inputs.brakes == 0.0
        assert inputs.gear == 1.0  # Default gear down

    def test_custom_values(self) -> None:
        """Test creating inputs with custom values."""
        inputs = ControlInputs(
            pitch=0.5, roll=-0.3, yaw=0.2, throttle=0.8, flaps=0.5, brakes=0.0, gear=0.0
        )
        assert inputs.pitch == 0.5
        assert inputs.roll == -0.3
        assert inputs.yaw == 0.2
        assert inputs.throttle == 0.8
        assert inputs.flaps == 0.5
        assert inputs.brakes == 0.0
        assert inputs.gear == 0.0

    def test_clamp_pitch_above_range(self) -> None:
        """Test pitch is clamped to valid range (above)."""
        inputs = ControlInputs(pitch=2.0)
        assert inputs.pitch == 1.0

    def test_clamp_pitch_below_range(self) -> None:
        """Test pitch is clamped to valid range (below)."""
        inputs = ControlInputs(pitch=-2.0)
        assert inputs.pitch == -1.0

    def test_clamp_roll_above_range(self) -> None:
        """Test roll is clamped to valid range (above)."""
        inputs = ControlInputs(roll=1.5)
        assert inputs.roll == 1.0

    def test_clamp_roll_below_range(self) -> None:
        """Test roll is clamped to valid range (below)."""
        inputs = ControlInputs(roll=-1.5)
        assert inputs.roll == -1.0

    def test_clamp_yaw_range(self) -> None:
        """Test yaw is clamped to valid range."""
        inputs_high = ControlInputs(yaw=2.0)
        inputs_low = ControlInputs(yaw=-2.0)
        assert inputs_high.yaw == 1.0
        assert inputs_low.yaw == -1.0

    def test_clamp_throttle_above_range(self) -> None:
        """Test throttle is clamped to 0.0-1.0 range (above)."""
        inputs = ControlInputs(throttle=1.5)
        assert inputs.throttle == 1.0

    def test_clamp_throttle_below_range(self) -> None:
        """Test throttle is clamped to 0.0-1.0 range (below)."""
        inputs = ControlInputs(throttle=-0.5)
        assert inputs.throttle == 0.0

    def test_clamp_flaps_range(self) -> None:
        """Test flaps are clamped to 0.0-1.0 range."""
        inputs_high = ControlInputs(flaps=2.0)
        inputs_low = ControlInputs(flaps=-0.5)
        assert inputs_high.flaps == 1.0
        assert inputs_low.flaps == 0.0

    def test_clamp_brakes_range(self) -> None:
        """Test brakes are clamped to 0.0-1.0 range."""
        inputs_high = ControlInputs(brakes=1.5)
        inputs_low = ControlInputs(brakes=-0.5)
        assert inputs_high.brakes == 1.0
        assert inputs_low.brakes == 0.0

    def test_clamp_gear_range(self) -> None:
        """Test gear is clamped to 0.0-1.0 range."""
        inputs_high = ControlInputs(gear=2.0)
        inputs_low = ControlInputs(gear=-0.5)
        assert inputs_high.gear == 1.0
        assert inputs_low.gear == 0.0


class TestAircraftState:
    """Test AircraftState dataclass."""

    def test_default_state(self) -> None:
        """Test default aircraft state."""
        state = AircraftState()
        assert state.position == Vector3.zero()
        assert state.velocity == Vector3.zero()
        assert state.acceleration == Vector3.zero()
        assert state.rotation == Vector3.zero()
        assert state.angular_velocity == Vector3.zero()
        assert state.mass == 1000.0
        assert state.fuel == 100.0
        assert state.on_ground is False

    def test_custom_state(self) -> None:
        """Test creating state with custom values."""
        position = Vector3(100.0, 500.0, 200.0)
        velocity = Vector3(50.0, 0.0, 0.0)
        state = AircraftState(
            position=position, velocity=velocity, mass=1200.0, fuel=80.0, on_ground=True
        )
        assert state.position == position
        assert state.velocity == velocity
        assert state.mass == 1200.0
        assert state.fuel == 80.0
        assert state.on_ground is True

    def test_get_altitude(self) -> None:
        """Test getting altitude from position Y."""
        state = AircraftState(position=Vector3(0.0, 1500.0, 0.0))
        assert state.get_altitude() == 1500.0

    def test_get_heading(self) -> None:
        """Test getting heading from rotation Z (yaw)."""
        state = AircraftState(rotation=Vector3(0.0, 0.0, 1.57))
        assert state.get_heading() == pytest.approx(1.57)

    def test_get_pitch(self) -> None:
        """Test getting pitch from rotation X."""
        state = AircraftState(rotation=Vector3(0.5, 0.0, 0.0))
        assert state.get_pitch() == pytest.approx(0.5)

    def test_get_roll(self) -> None:
        """Test getting roll from rotation Y."""
        state = AircraftState(rotation=Vector3(0.0, 0.3, 0.0))
        assert state.get_roll() == pytest.approx(0.3)

    def test_airspeed_calculation(self) -> None:
        """Test airspeed is calculated from velocity magnitude."""
        state = AircraftState(velocity=Vector3(30.0, 40.0, 0.0))
        airspeed = state.get_airspeed()
        assert airspeed == pytest.approx(50.0)  # 3-4-5 triangle

    def test_airspeed_caching(self) -> None:
        """Test airspeed is cached for performance."""
        state = AircraftState(velocity=Vector3(3.0, 4.0, 0.0))
        # First call calculates
        airspeed1 = state.get_airspeed()
        # Second call should return cached value
        airspeed2 = state.get_airspeed()
        assert airspeed1 == airspeed2 == pytest.approx(5.0)

    def test_mark_velocity_dirty(self) -> None:
        """Test marking velocity as dirty recalculates airspeed."""
        state = AircraftState(velocity=Vector3(3.0, 4.0, 0.0))
        # Initial airspeed
        airspeed1 = state.get_airspeed()
        assert airspeed1 == pytest.approx(5.0)

        # Change velocity directly
        state.velocity = Vector3(6.0, 8.0, 0.0)
        state.mark_velocity_dirty()

        # Should recalculate
        airspeed2 = state.get_airspeed()
        assert airspeed2 == pytest.approx(10.0)

    def test_zero_velocity_airspeed(self) -> None:
        """Test airspeed is zero for stationary aircraft."""
        state = AircraftState(velocity=Vector3.zero())
        assert state.get_airspeed() == 0.0


class TestFlightForces:
    """Test FlightForces dataclass."""

    def test_default_forces(self) -> None:
        """Test default forces are all zero."""
        forces = FlightForces()
        assert forces.lift == Vector3.zero()
        assert forces.drag == Vector3.zero()
        assert forces.thrust == Vector3.zero()
        assert forces.weight == Vector3.zero()
        assert forces.total == Vector3.zero()

    def test_custom_forces(self) -> None:
        """Test creating forces with custom values."""
        lift = Vector3(0.0, 1000.0, 0.0)
        drag = Vector3(-100.0, 0.0, 0.0)
        thrust = Vector3(500.0, 0.0, 0.0)
        weight = Vector3(0.0, -1000.0, 0.0)

        forces = FlightForces(lift=lift, drag=drag, thrust=thrust, weight=weight)
        assert forces.lift == lift
        assert forces.drag == drag
        assert forces.thrust == thrust
        assert forces.weight == weight

    def test_calculate_total(self) -> None:
        """Test calculating total force from components."""
        forces = FlightForces(
            lift=Vector3(0.0, 1000.0, 0.0),
            drag=Vector3(-100.0, 0.0, 0.0),
            thrust=Vector3(500.0, 0.0, 0.0),
            weight=Vector3(0.0, -900.0, 0.0),
        )
        forces.calculate_total()
        # Total = (500-100, 1000-900, 0)
        assert forces.total.x == pytest.approx(400.0)
        assert forces.total.y == pytest.approx(100.0)
        assert forces.total.z == pytest.approx(0.0)

    def test_calculate_total_balanced(self) -> None:
        """Test total force when forces are balanced."""
        forces = FlightForces(
            lift=Vector3(0.0, 1000.0, 0.0),
            drag=Vector3(-200.0, 0.0, 0.0),
            thrust=Vector3(200.0, 0.0, 0.0),
            weight=Vector3(0.0, -1000.0, 0.0),
        )
        forces.calculate_total()
        # Forces balance out
        assert forces.total.x == pytest.approx(0.0)
        assert forces.total.y == pytest.approx(0.0)
        assert forces.total.z == pytest.approx(0.0)

    def test_calculate_total_updates_in_place(self) -> None:
        """Test calculate_total updates existing total field."""
        forces = FlightForces(
            lift=Vector3(0.0, 500.0, 0.0),
            drag=Vector3(-50.0, 0.0, 0.0),
            thrust=Vector3(100.0, 0.0, 0.0),
            weight=Vector3(0.0, -500.0, 0.0),
        )
        # Set initial total
        forces.total = Vector3(999.0, 999.0, 999.0)
        # Calculate should overwrite
        forces.calculate_total()
        assert forces.total.x == pytest.approx(50.0)
        assert forces.total.y == pytest.approx(0.0)
        assert forces.total.z == pytest.approx(0.0)

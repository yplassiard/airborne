"""Tests for flaperon systems."""

import pytest

from airborne.systems.aerodynamics.flaperons import (
    FlaperonMode,
    FlaperonState,
    FlaperonSystem,
)


class TestFlaperonSystemInitialization:
    """Test FlaperonSystem initialization."""

    def test_default_initialization(self) -> None:
        """Test flaperons initialize with default parameters."""
        flaperons = FlaperonSystem()

        assert flaperons.max_flap_deg == 40.0
        assert flaperons.max_aileron_deg == 20.0
        assert flaperons.differential_ratio == 1.3
        assert flaperons.get_flap_component() == 0.0

    def test_custom_initialization(self) -> None:
        """Test flaperons initialize with custom parameters."""
        flaperons = FlaperonSystem(
            max_flap_deflection_deg=35.0,
            max_aileron_deflection_deg=25.0,
            differential_ratio=1.5,
            min_roll_authority_at_full_flap=0.4,
        )

        assert flaperons.max_flap_deg == 35.0
        assert flaperons.max_aileron_deg == 25.0
        assert flaperons.differential_ratio == 1.5
        assert flaperons.min_roll_authority == 0.4


class TestFlaperonFlapFunction:
    """Test flaperon flap functionality."""

    @pytest.fixture
    def flaperons(self) -> FlaperonSystem:
        """Create flaperon system."""
        return FlaperonSystem(
            max_flap_deflection_deg=40.0,
            flap_rate_per_second=1.0,  # Fast for testing
        )

    def test_flap_deployment(self, flaperons: FlaperonSystem) -> None:
        """Test flaps deploy when commanded."""
        for _ in range(120):
            flaperons.update(flap_command=1.0, roll_command=0.0, dt=0.016)

        assert flaperons.get_flap_component() > 0.9

    def test_flap_retraction(self, flaperons: FlaperonSystem) -> None:
        """Test flaps retract when commanded."""
        # First deploy
        for _ in range(120):
            flaperons.update(flap_command=1.0, roll_command=0.0, dt=0.016)

        # Then retract
        for _ in range(120):
            flaperons.update(flap_command=0.0, roll_command=0.0, dt=0.016)

        assert flaperons.get_flap_component() < 0.1

    def test_flap_partial_setting(self, flaperons: FlaperonSystem) -> None:
        """Test flaps hold partial setting."""
        for _ in range(120):
            flaperons.update(flap_command=0.5, roll_command=0.0, dt=0.016)

        assert 0.45 < flaperons.get_flap_component() < 0.55

    def test_symmetric_deflection_flaps_only(self, flaperons: FlaperonSystem) -> None:
        """Test both surfaces deflect equally with flaps only."""
        for _ in range(120):
            flaperons.update(flap_command=0.5, roll_command=0.0, dt=0.016)

        left_deg, right_deg = flaperons.get_surface_positions_deg()
        assert left_deg == pytest.approx(right_deg, abs=0.1)


class TestFlaperonRollFunction:
    """Test flaperon aileron/roll functionality."""

    @pytest.fixture
    def flaperons(self) -> FlaperonSystem:
        """Create flaperon system."""
        return FlaperonSystem(
            max_flap_deflection_deg=40.0,
            max_aileron_deflection_deg=20.0,
            differential_ratio=1.3,
            roll_response_rate=20.0,  # Fast for testing
        )

    def test_right_roll_differential(self, flaperons: FlaperonSystem) -> None:
        """Test right roll creates correct differential."""
        for _ in range(30):
            flaperons.update(flap_command=0.0, roll_command=1.0, dt=0.016)

        left_deg, right_deg = flaperons.get_surface_positions_deg()

        # Right roll: left goes up (negative), right goes down (positive)
        assert left_deg < 0.0
        assert right_deg > 0.0

    def test_left_roll_differential(self, flaperons: FlaperonSystem) -> None:
        """Test left roll creates correct differential."""
        for _ in range(30):
            flaperons.update(flap_command=0.0, roll_command=-1.0, dt=0.016)

        left_deg, right_deg = flaperons.get_surface_positions_deg()

        # Left roll: left goes down (positive), right goes up (negative)
        assert left_deg > 0.0
        assert right_deg < 0.0

    def test_differential_asymmetry(self, flaperons: FlaperonSystem) -> None:
        """Test differential ratio creates asymmetric deflection."""
        for _ in range(30):
            flaperons.update(flap_command=0.0, roll_command=1.0, dt=0.016)

        left_deg, right_deg = flaperons.get_surface_positions_deg()

        # Down-going surface (right) should deflect more than up-going (left)
        assert abs(right_deg) > abs(left_deg)


class TestFlaperonRollAuthority:
    """Test roll authority with flap extension."""

    @pytest.fixture
    def flaperons(self) -> FlaperonSystem:
        """Create flaperon system with known roll authority."""
        return FlaperonSystem(
            max_aileron_deflection_deg=20.0,
            min_roll_authority_at_full_flap=0.5,
            flap_rate_per_second=2.0,
        )

    def test_full_roll_authority_flaps_up(self, flaperons: FlaperonSystem) -> None:
        """Test full roll authority with flaps up."""
        assert flaperons.get_roll_authority() == 1.0

    def test_reduced_roll_authority_flaps_down(self, flaperons: FlaperonSystem) -> None:
        """Test reduced roll authority with flaps down."""
        for _ in range(120):
            flaperons.update(flap_command=1.0, roll_command=0.0, dt=0.016)

        assert flaperons.get_roll_authority() == pytest.approx(0.5, rel=0.1)

    def test_roll_authority_linear_decrease(self, flaperons: FlaperonSystem) -> None:
        """Test roll authority decreases linearly with flap."""
        for _ in range(60):
            flaperons.update(flap_command=0.5, roll_command=0.0, dt=0.016)

        # At 50% flaps, authority should be 75% (linear interpolation)
        assert flaperons.get_roll_authority() == pytest.approx(0.75, rel=0.1)

    def test_reduced_roll_deflection_with_flaps(self, flaperons: FlaperonSystem) -> None:
        """Test roll deflection is reduced with flaps extended."""
        # Get roll deflection flaps up
        for _ in range(30):
            flaperons.update(flap_command=0.0, roll_command=1.0, dt=0.016)
        left_up, right_up = flaperons.get_surface_positions_deg()
        flaperons.reset()

        # Get roll deflection flaps down
        for _ in range(120):
            flaperons.update(flap_command=1.0, roll_command=0.0, dt=0.016)
        for _ in range(30):
            flaperons.update(flap_command=1.0, roll_command=1.0, dt=0.016)
        left_down, right_down = flaperons.get_surface_positions_deg()

        # Roll differential should be smaller with flaps down
        roll_diff_up = right_up - left_up
        roll_diff_down = right_down - left_down
        assert roll_diff_down < roll_diff_up


class TestFlaperonCombinedOperation:
    """Test combined flap and roll operation."""

    @pytest.fixture
    def flaperons(self) -> FlaperonSystem:
        """Create flaperon system."""
        return FlaperonSystem(
            max_flap_deflection_deg=40.0,
            max_aileron_deflection_deg=20.0,
            flap_rate_per_second=2.0,
            roll_response_rate=20.0,
        )

    def test_flap_plus_roll(self, flaperons: FlaperonSystem) -> None:
        """Test combined flap and roll commands."""
        for _ in range(120):
            flaperons.update(flap_command=0.5, roll_command=0.5, dt=0.016)

        left_deg, right_deg = flaperons.get_surface_positions_deg()

        # Both should be positive (trailing edge down)
        # but right should be more down due to roll
        assert left_deg > 0.0  # Flap component dominates
        assert right_deg > left_deg  # Roll adds to right side

    def test_surface_limits_not_exceeded(self, flaperons: FlaperonSystem) -> None:
        """Test surface deflection stays within limits."""
        for _ in range(120):
            flaperons.update(flap_command=1.0, roll_command=1.0, dt=0.016)

        left_deg, right_deg = flaperons.get_surface_positions_deg()
        total_max = flaperons.max_flap_deg + flaperons.max_aileron_deg

        assert left_deg <= total_max
        assert right_deg <= total_max
        assert left_deg >= -flaperons.max_aileron_deg
        assert right_deg >= -flaperons.max_aileron_deg


class TestFlaperonModeDetection:
    """Test operating mode detection."""

    @pytest.fixture
    def flaperons(self) -> FlaperonSystem:
        """Create flaperon system."""
        return FlaperonSystem(flap_rate_per_second=2.0)

    def test_cruise_mode(self, flaperons: FlaperonSystem) -> None:
        """Test cruise mode at low flap setting."""
        flaperons.update(flap_command=0.0, roll_command=0.0, dt=0.016)
        state = flaperons.get_state()

        assert state.mode == FlaperonMode.CRUISE

    def test_takeoff_mode(self, flaperons: FlaperonSystem) -> None:
        """Test takeoff mode at mid flap setting."""
        for _ in range(60):
            flaperons.update(flap_command=0.3, roll_command=0.0, dt=0.016)
        state = flaperons.get_state()

        assert state.mode == FlaperonMode.TAKEOFF

    def test_landing_mode(self, flaperons: FlaperonSystem) -> None:
        """Test landing mode at high flap setting."""
        for _ in range(120):
            flaperons.update(flap_command=0.8, roll_command=0.0, dt=0.016)
        state = flaperons.get_state()

        assert state.mode == FlaperonMode.LANDING


class TestFlaperonState:
    """Test flaperon state reporting."""

    def test_state_includes_all_fields(self) -> None:
        """Test state object includes all expected fields."""
        flaperons = FlaperonSystem()
        state = flaperons.get_state()

        assert isinstance(state, FlaperonState)
        assert hasattr(state, "flap_position")
        assert hasattr(state, "left_surface_deg")
        assert hasattr(state, "right_surface_deg")
        assert hasattr(state, "roll_authority")
        assert hasattr(state, "cl_contribution")
        assert hasattr(state, "mode")

    def test_cl_contribution_with_flaps(self) -> None:
        """Test CL contribution increases with flaps."""
        flaperons = FlaperonSystem(
            cl_per_flap_unit=0.6,
            flap_rate_per_second=2.0,
        )

        for _ in range(120):
            flaperons.update(flap_command=1.0, roll_command=0.0, dt=0.016)

        state = flaperons.get_state()
        assert state.cl_contribution == pytest.approx(0.6, rel=0.1)


class TestFlaperonReset:
    """Test flaperon reset functionality."""

    def test_reset_returns_to_neutral(self) -> None:
        """Test reset returns all positions to neutral."""
        flaperons = FlaperonSystem(
            flap_rate_per_second=2.0,
            roll_response_rate=20.0,
        )

        # Apply commands
        for _ in range(120):
            flaperons.update(flap_command=0.8, roll_command=0.5, dt=0.016)

        assert flaperons.get_flap_component() > 0.5

        # Reset
        flaperons.reset()

        assert flaperons.get_flap_component() == 0.0
        left_deg, right_deg = flaperons.get_surface_positions_deg()
        assert left_deg == 0.0
        assert right_deg == 0.0

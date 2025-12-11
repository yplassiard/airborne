"""Tests for automatic slat systems."""

import pytest

from airborne.systems.aerodynamics.slats import AutomaticSlats, SlatsState


class TestAutomaticSlatsInitialization:
    """Test AutomaticSlats initialization."""

    def test_default_initialization(self) -> None:
        """Test slats initialize with default parameters."""
        slats = AutomaticSlats()

        assert slats.deploy_aoa_start == 8.0
        assert slats.deploy_aoa_full == 14.0
        assert slats.max_cl_bonus == 0.45
        assert slats.max_stall_extension == 8.0
        assert slats.get_slat_position() == 0.0

    def test_custom_initialization(self) -> None:
        """Test slats initialize with custom parameters."""
        slats = AutomaticSlats(
            deploy_aoa_start_deg=6.0,
            deploy_aoa_full_deg=12.0,
            max_cl_bonus=0.5,
            max_stall_extension_deg=10.0,
            deploy_rate=3.0,
            retract_rate=2.0,
        )

        assert slats.deploy_aoa_start == 6.0
        assert slats.deploy_aoa_full == 12.0
        assert slats.max_cl_bonus == 0.5
        assert slats.max_stall_extension == 10.0
        assert slats.deploy_rate == 3.0
        assert slats.retract_rate == 2.0


class TestAutomaticSlatsDeployment:
    """Test slat deployment behavior."""

    @pytest.fixture
    def slats(self) -> AutomaticSlats:
        """Create slats with known parameters."""
        return AutomaticSlats(
            deploy_aoa_start_deg=8.0,
            deploy_aoa_full_deg=14.0,
            deploy_rate=2.0,
            retract_rate=1.5,
        )

    def test_slats_retracted_at_low_aoa(self, slats: AutomaticSlats) -> None:
        """Test slats remain retracted at low AOA."""
        for _ in range(60):  # 1 second at 60 fps
            slats.update(angle_of_attack_deg=5.0, airspeed_mps=30.0, dt=0.016)

        assert slats.get_slat_position() == 0.0

    def test_slats_deploy_at_high_aoa(self, slats: AutomaticSlats) -> None:
        """Test slats deploy as AOA increases."""
        for _ in range(120):  # 2 seconds
            slats.update(angle_of_attack_deg=14.0, airspeed_mps=30.0, dt=0.016)

        assert slats.get_slat_position() > 0.9

    def test_slats_progressive_deployment(self, slats: AutomaticSlats) -> None:
        """Test slats deploy progressively with AOA."""
        # At midpoint AOA
        for _ in range(120):
            slats.update(angle_of_attack_deg=11.0, airspeed_mps=30.0, dt=0.016)

        position = slats.get_slat_position()
        assert 0.4 < position < 0.6  # Should be around 50%

    def test_slats_retract_when_aoa_decreases(self, slats: AutomaticSlats) -> None:
        """Test slats retract when AOA decreases."""
        # First deploy
        for _ in range(120):
            slats.update(angle_of_attack_deg=14.0, airspeed_mps=30.0, dt=0.016)

        initial_position = slats.get_slat_position()
        assert initial_position > 0.8

        # Then retract
        for _ in range(200):
            slats.update(angle_of_attack_deg=5.0, airspeed_mps=30.0, dt=0.016)

        assert slats.get_slat_position() < initial_position
        assert slats.get_slat_position() < 0.1

    def test_slats_dont_deploy_at_low_airspeed(self, slats: AutomaticSlats) -> None:
        """Test slats don't deploy without sufficient airspeed."""
        for _ in range(120):
            slats.update(angle_of_attack_deg=14.0, airspeed_mps=5.0, dt=0.016)

        assert slats.get_slat_position() == 0.0


class TestAutomaticSlatsAerodynamics:
    """Test slat aerodynamic effects."""

    @pytest.fixture
    def deployed_slats(self) -> AutomaticSlats:
        """Create fully deployed slats."""
        slats = AutomaticSlats(
            max_cl_bonus=0.45,
            max_stall_extension_deg=8.0,
            max_drag_penalty=0.02,
        )
        # Force full deployment
        for _ in range(120):
            slats.update(angle_of_attack_deg=16.0, airspeed_mps=30.0, dt=0.016)
        return slats

    def test_cl_bonus_proportional_to_position(self, deployed_slats: AutomaticSlats) -> None:
        """Test CL bonus is proportional to slat position."""
        position = deployed_slats.get_slat_position()
        expected_bonus = position * 0.45

        assert deployed_slats.get_cl_bonus() == pytest.approx(expected_bonus, rel=0.01)

    def test_stall_extension_proportional_to_position(self, deployed_slats: AutomaticSlats) -> None:
        """Test stall AOA extension is proportional to position."""
        position = deployed_slats.get_slat_position()
        expected_extension = position * 8.0

        assert deployed_slats.get_stall_aoa_extension() == pytest.approx(
            expected_extension, rel=0.01
        )

    def test_drag_penalty_proportional_to_position(self, deployed_slats: AutomaticSlats) -> None:
        """Test drag penalty is proportional to position."""
        position = deployed_slats.get_slat_position()
        expected_drag = position * 0.02

        assert deployed_slats.get_drag_penalty() == pytest.approx(expected_drag, rel=0.01)

    def test_no_bonus_when_retracted(self) -> None:
        """Test no aero effects when slats retracted."""
        slats = AutomaticSlats()
        # Keep at low AOA
        slats.update(angle_of_attack_deg=5.0, airspeed_mps=30.0, dt=0.016)

        assert slats.get_cl_bonus() == 0.0
        assert slats.get_stall_aoa_extension() == 0.0
        assert slats.get_drag_penalty() == 0.0


class TestAutomaticSlatsState:
    """Test slat state reporting."""

    def test_state_reports_position(self) -> None:
        """Test state includes correct position."""
        slats = AutomaticSlats()

        for _ in range(120):
            slats.update(angle_of_attack_deg=11.0, airspeed_mps=30.0, dt=0.016)

        state = slats.get_state()
        assert isinstance(state, SlatsState)
        assert state.position == slats.get_slat_position()

    def test_state_reports_deploying(self) -> None:
        """Test state reports when deploying."""
        slats = AutomaticSlats()

        # Start deploying
        slats.update(angle_of_attack_deg=14.0, airspeed_mps=30.0, dt=0.016)
        state = slats.get_state()

        assert state.is_deploying is True
        assert state.is_retracting is False

    def test_state_reports_retracting(self) -> None:
        """Test state reports when retracting."""
        slats = AutomaticSlats(deploy_rate=10.0)

        # First deploy
        for _ in range(30):
            slats.update(angle_of_attack_deg=14.0, airspeed_mps=30.0, dt=0.016)

        # Then retract
        slats.update(angle_of_attack_deg=5.0, airspeed_mps=30.0, dt=0.016)
        state = slats.get_state()

        assert state.is_deploying is False
        assert state.is_retracting is True

    def test_symmetric_positions(self) -> None:
        """Test left and right slats move together."""
        slats = AutomaticSlats()

        for _ in range(60):
            slats.update(angle_of_attack_deg=12.0, airspeed_mps=30.0, dt=0.016)

        state = slats.get_state()
        assert state.left_position == state.right_position
        assert state.left_position == state.position


class TestAutomaticSlatsReset:
    """Test slat reset functionality."""

    def test_reset_retracts_slats(self) -> None:
        """Test reset retracts slats fully."""
        slats = AutomaticSlats()

        # Deploy
        for _ in range(120):
            slats.update(angle_of_attack_deg=14.0, airspeed_mps=30.0, dt=0.016)

        assert slats.get_slat_position() > 0.8

        # Reset
        slats.reset()

        assert slats.get_slat_position() == 0.0
        assert slats.get_cl_bonus() == 0.0

    def test_reset_clears_state_flags(self) -> None:
        """Test reset clears deploying/retracting flags."""
        slats = AutomaticSlats()

        slats.update(angle_of_attack_deg=14.0, airspeed_mps=30.0, dt=0.016)
        slats.reset()

        state = slats.get_state()
        assert state.is_deploying is False
        assert state.is_retracting is False

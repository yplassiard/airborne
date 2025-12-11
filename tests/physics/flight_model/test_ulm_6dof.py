"""Tests for ULM 6DOF flight model."""

import math

import pytest

from airborne.physics.flight_model.base import AircraftState, ControlInputs
from airborne.physics.flight_model.ulm_6dof import ULM6DOFFlightModel
from airborne.physics.vectors import Vector3


class TestULM6DOFFlightModelInitialization:
    """Test ULM6DOFFlightModel initialization."""

    def test_initialization_with_required_params(self) -> None:
        """Test model initializes with required parameters."""
        model = ULM6DOFFlightModel()
        model.initialize(
            {
                "wing_area_sqft": 122.0,
                "weight_lbs": 580.0,
                "max_thrust_lbs": 90.0,
            }
        )

        assert model.wing_area == pytest.approx(122.0 * 0.092903, rel=0.01)
        assert model.empty_mass == pytest.approx(580.0 * 0.453592, rel=0.01)

    def test_initialization_missing_wing_area(self) -> None:
        """Test initialization fails without wing_area_sqft."""
        model = ULM6DOFFlightModel()
        with pytest.raises(ValueError, match="wing_area_sqft required"):
            model.initialize({"weight_lbs": 580.0, "max_thrust_lbs": 90.0})

    def test_initialization_missing_weight(self) -> None:
        """Test initialization fails without weight_lbs."""
        model = ULM6DOFFlightModel()
        with pytest.raises(ValueError, match="weight_lbs required"):
            model.initialize({"wing_area_sqft": 122.0, "max_thrust_lbs": 90.0})

    def test_initialization_missing_thrust(self) -> None:
        """Test initialization fails without max_thrust_lbs."""
        model = ULM6DOFFlightModel()
        with pytest.raises(ValueError, match="max_thrust_lbs required"):
            model.initialize({"wing_area_sqft": 122.0, "weight_lbs": 580.0})

    def test_initialization_with_slats_enabled(self) -> None:
        """Test model initializes with slats enabled."""
        model = ULM6DOFFlightModel()
        model.initialize(
            {
                "wing_area_sqft": 122.0,
                "weight_lbs": 580.0,
                "max_thrust_lbs": 90.0,
                "has_slats": True,
                "slat_deploy_aoa_deg": 6.0,
            }
        )

        assert model.has_slats is True
        assert model._slat_deploy_aoa_deg == 6.0

    def test_initialization_with_flaperons_enabled(self) -> None:
        """Test model initializes with flaperons enabled."""
        model = ULM6DOFFlightModel()
        model.initialize(
            {
                "wing_area_sqft": 122.0,
                "weight_lbs": 580.0,
                "max_thrust_lbs": 90.0,
                "has_flaperons": True,
            }
        )

        assert model.has_flaperons is True

    def test_ulm_specific_defaults(self) -> None:
        """Test ULM-specific default values are set correctly."""
        model = ULM6DOFFlightModel()
        model.initialize(
            {
                "wing_area_sqft": 122.0,
                "weight_lbs": 580.0,
                "max_thrust_lbs": 90.0,
            }
        )

        # ULM should have higher base CL
        assert model.cl_0 == 0.35
        # ULM should have higher max CL
        assert model.cl_max == 1.8
        # ULM should have lower pitch inertia
        assert model.pitch_inertia == 300.0
        # ULM should have higher elevator effectiveness
        assert model.elevator_effectiveness == 0.6


class TestULM6DOFFlightModelPhysics:
    """Test ULM6DOFFlightModel physics calculations."""

    @pytest.fixture
    def initialized_model(self) -> ULM6DOFFlightModel:
        """Create an initialized ULM model."""
        model = ULM6DOFFlightModel()
        model.initialize(
            {
                "wing_area_sqft": 122.0,
                "weight_lbs": 580.0,
                "max_thrust_lbs": 90.0,
                "has_slats": True,
            }
        )
        return model

    def test_update_returns_state(self, initialized_model: ULM6DOFFlightModel) -> None:
        """Test update returns aircraft state."""
        inputs = ControlInputs(throttle=0.5)
        state = initialized_model.update(0.016, inputs)

        assert isinstance(state, AircraftState)

    def test_update_increments_counter(self, initialized_model: ULM6DOFFlightModel) -> None:
        """Test update increments the update counter."""
        inputs = ControlInputs()
        initial_count = initialized_model.get_update_count()

        initialized_model.update(0.016, inputs)
        initialized_model.update(0.016, inputs)

        assert initialized_model.get_update_count() == initial_count + 2

    def test_lift_generated_at_airspeed(self, initialized_model: ULM6DOFFlightModel) -> None:
        """Test lift is generated when aircraft has airspeed."""
        # Set initial velocity
        initialized_model.state.velocity = Vector3(0.0, 0.0, 30.0)  # 30 m/s forward
        initialized_model.state.rotation.x = 0.05  # Small pitch up

        inputs = ControlInputs(throttle=0.5)
        initialized_model.update(0.016, inputs)

        forces = initialized_model.get_forces()
        assert forces.lift.y > 0.0  # Lift should have upward component

    def test_no_lift_at_zero_airspeed(self, initialized_model: ULM6DOFFlightModel) -> None:
        """Test no lift is generated at zero airspeed."""
        initialized_model.state.velocity = Vector3.zero()

        inputs = ControlInputs(throttle=0.5)
        initialized_model.update(0.016, inputs)

        forces = initialized_model.get_forces()
        assert forces.lift.magnitude() < 1.0  # Essentially zero

    def test_thrust_proportional_to_throttle(self, initialized_model: ULM6DOFFlightModel) -> None:
        """Test thrust is proportional to throttle setting."""
        initialized_model.state.velocity = Vector3(0.0, 0.0, 20.0)

        # Half throttle
        inputs_half = ControlInputs(throttle=0.5)
        initialized_model.update(0.016, inputs_half)
        forces_half = initialized_model.get_forces()
        thrust_half = forces_half.thrust.magnitude()

        # Full throttle
        inputs_full = ControlInputs(throttle=1.0)
        initialized_model.update(0.016, inputs_full)
        forces_full = initialized_model.get_forces()
        thrust_full = forces_full.thrust.magnitude()

        assert thrust_full > thrust_half

    def test_weight_always_downward(self, initialized_model: ULM6DOFFlightModel) -> None:
        """Test weight force always acts downward."""
        inputs = ControlInputs(throttle=0.5)
        initialized_model.update(0.016, inputs)

        forces = initialized_model.get_forces()
        assert forces.weight.y < 0.0  # Downward
        assert forces.weight.x == 0.0
        assert forces.weight.z == 0.0

    def test_ground_detection(self, initialized_model: ULM6DOFFlightModel) -> None:
        """Test aircraft detects ground contact."""
        # Start above ground
        initialized_model.state.position.y = 10.0
        initialized_model.state.velocity = Vector3(0.0, -5.0, 0.0)  # Descending

        inputs = ControlInputs()

        # Run until ground contact
        for _ in range(100):
            initialized_model.update(0.016, inputs)
            if initialized_model.state.on_ground:
                break

        assert initialized_model.state.on_ground
        assert initialized_model.state.position.y >= 0.0

    def test_fuel_consumption(self, initialized_model: ULM6DOFFlightModel) -> None:
        """Test fuel is consumed during operation."""
        initial_fuel = initialized_model.state.fuel

        inputs = ControlInputs(throttle=0.8)

        # Run for several updates
        for _ in range(100):
            initialized_model.update(0.016, inputs)

        assert initialized_model.state.fuel < initial_fuel


class TestULM6DOFSlatsIntegration:
    """Test automatic slat integration in ULM model."""

    @pytest.fixture
    def model_with_slats(self) -> ULM6DOFFlightModel:
        """Create a model with slats enabled."""
        model = ULM6DOFFlightModel()
        model.initialize(
            {
                "wing_area_sqft": 122.0,
                "weight_lbs": 580.0,
                "max_thrust_lbs": 90.0,
                "has_slats": True,
                "slat_deploy_aoa_deg": 6.0,
                "cl_slat_bonus": 0.4,
                "stall_aoa_slat_bonus": 8.0,
            }
        )
        return model

    def test_slats_deploy_at_high_aoa(self, model_with_slats: ULM6DOFFlightModel) -> None:
        """Test slats deploy when AOA increases."""
        # Set up for high AOA
        model_with_slats.state.velocity = Vector3(0.0, 0.0, 20.0)
        model_with_slats.state.rotation.x = 0.25  # ~14 degrees pitch up

        inputs = ControlInputs(throttle=0.5)

        # Run updates to allow slat deployment
        for _ in range(60):
            model_with_slats.update(0.016, inputs)

        assert model_with_slats.current_slat_position > 0.0

    def test_slats_retract_at_low_aoa(self, model_with_slats: ULM6DOFFlightModel) -> None:
        """Test slats retract when AOA decreases."""
        # First deploy slats
        model_with_slats.state.velocity = Vector3(0.0, 0.0, 20.0)
        model_with_slats.state.rotation.x = 0.25

        inputs = ControlInputs(throttle=0.5)
        for _ in range(60):
            model_with_slats.update(0.016, inputs)

        initial_slat_pos = model_with_slats.current_slat_position

        # Now reduce AOA
        model_with_slats.state.rotation.x = 0.0

        for _ in range(120):
            model_with_slats.update(0.016, inputs)

        assert model_with_slats.current_slat_position < initial_slat_pos

    def test_slats_increase_max_cl(self, model_with_slats: ULM6DOFFlightModel) -> None:
        """Test slats increase maximum lift coefficient."""
        # Get CL at high AOA without slats deployed
        model_without_slats = ULM6DOFFlightModel()
        model_without_slats.initialize(
            {
                "wing_area_sqft": 122.0,
                "weight_lbs": 580.0,
                "max_thrust_lbs": 90.0,
                "has_slats": False,
            }
        )

        aoa_rad = 0.3  # High AOA

        cl_without_slats = model_without_slats._calculate_lift_coefficient(aoa_rad, 0.0)

        # Force slat deployment
        model_with_slats.current_slat_position = 1.0
        cl_with_slats = model_with_slats._calculate_lift_coefficient(aoa_rad, 0.0)

        assert cl_with_slats > cl_without_slats


class TestULM6DOFModelReset:
    """Test ULM model reset functionality."""

    def test_reset_to_new_state(self) -> None:
        """Test model can be reset to a new state."""
        model = ULM6DOFFlightModel()
        model.initialize(
            {
                "wing_area_sqft": 122.0,
                "weight_lbs": 580.0,
                "max_thrust_lbs": 90.0,
            }
        )

        # Run some updates
        inputs = ControlInputs(throttle=0.5)
        for _ in range(10):
            model.update(0.016, inputs)

        # Reset to new state
        new_state = AircraftState(
            position=Vector3(100.0, 500.0, 200.0),
            velocity=Vector3(0.0, 0.0, 30.0),
        )
        model.reset(new_state)

        assert model.state.position.x == 100.0
        assert model.state.position.y == 500.0
        assert model.get_update_count() == 0

    def test_reset_clears_external_forces(self) -> None:
        """Test reset clears accumulated external forces."""
        model = ULM6DOFFlightModel()
        model.initialize(
            {
                "wing_area_sqft": 122.0,
                "weight_lbs": 580.0,
                "max_thrust_lbs": 90.0,
            }
        )

        # Apply external force
        model.apply_force(Vector3(1000.0, 0.0, 0.0), Vector3.zero())

        # Reset
        model.reset(AircraftState())

        assert model.external_force == Vector3.zero()


class TestULM6DOFLiftCoefficient:
    """Test lift coefficient calculations."""

    @pytest.fixture
    def model(self) -> ULM6DOFFlightModel:
        """Create initialized model."""
        m = ULM6DOFFlightModel()
        m.initialize(
            {
                "wing_area_sqft": 122.0,
                "weight_lbs": 580.0,
                "max_thrust_lbs": 90.0,
                "cl_0": 0.35,
                "cl_alpha": 0.11,
                "cl_max": 1.8,
                "stall_aoa_deg": 15.0,
            }
        )
        return m

    def test_cl_at_zero_aoa(self, model: ULM6DOFFlightModel) -> None:
        """Test CL at zero angle of attack equals cl_0."""
        cl = model._calculate_lift_coefficient(0.0, 0.0)
        assert cl == pytest.approx(model.cl_0, rel=0.01)

    def test_cl_increases_with_aoa(self, model: ULM6DOFFlightModel) -> None:
        """Test CL increases with angle of attack."""
        cl_5deg = model._calculate_lift_coefficient(math.radians(5.0), 0.0)
        cl_10deg = model._calculate_lift_coefficient(math.radians(10.0), 0.0)

        assert cl_10deg > cl_5deg

    def test_cl_limited_at_max(self, model: ULM6DOFFlightModel) -> None:
        """Test CL doesn't exceed cl_max before stall."""
        cl = model._calculate_lift_coefficient(math.radians(14.0), 0.0)
        assert cl <= model.cl_max

    def test_cl_decreases_after_stall(self, model: ULM6DOFFlightModel) -> None:
        """Test CL decreases after stall AOA."""
        cl_at_stall = model._calculate_lift_coefficient(math.radians(15.0), 0.0)
        cl_post_stall = model._calculate_lift_coefficient(math.radians(25.0), 0.0)

        assert cl_post_stall < cl_at_stall

    def test_flaps_increase_cl(self, model: ULM6DOFFlightModel) -> None:
        """Test flaps increase lift coefficient."""
        aoa = math.radians(5.0)

        cl_no_flaps = model._calculate_lift_coefficient(aoa, 0.0)
        cl_full_flaps = model._calculate_lift_coefficient(aoa, 1.0)

        assert cl_full_flaps > cl_no_flaps


class TestULM6DOFGlideRatio:
    """Test glide ratio calculations for ULM Class 3 aircraft."""

    @pytest.fixture
    def ch701_model(self) -> ULM6DOFFlightModel:
        """Create a model configured like a CH701."""
        model = ULM6DOFFlightModel()
        model.initialize(
            {
                "wing_area_sqft": 122.0,  # 11.3 m²
                "weight_lbs": 992.0,
                "max_thrust_lbs": 100.0,
                "wing_span_m": 8.2,
                "drag_coefficient": 0.035,
                "oswald_efficiency": 0.75,
            }
        )
        return model

    @pytest.fixture
    def generic_ulm_model(self) -> ULM6DOFFlightModel:
        """Create a generic ULM Class 3 model."""
        model = ULM6DOFFlightModel()
        model.initialize(
            {
                "wing_area_sqft": 130.0,
                "weight_lbs": 900.0,
                "max_thrust_lbs": 90.0,
                "wing_span_m": 9.0,
            }
        )
        return model

    def test_aspect_ratio_calculated_from_geometry(self, ch701_model: ULM6DOFFlightModel) -> None:
        """Test aspect ratio is calculated from span and area."""
        # CH701: span=8.2m, area=11.3m² -> AR = 8.2²/11.3 ≈ 5.95
        ar = ch701_model.get_aspect_ratio()
        expected_ar = 8.2**2 / (122.0 * 0.092903)
        assert ar == pytest.approx(expected_ar, rel=0.01)

    def test_best_glide_ratio_in_realistic_range_ch701(
        self, ch701_model: ULM6DOFFlightModel
    ) -> None:
        """Test CH701 best glide ratio is realistic (8:1 to 10:1)."""
        best_ld = ch701_model.get_best_glide_ratio()

        # CH701 with slats typically achieves 8:1 to 10:1
        assert 7.0 <= best_ld <= 11.0, f"CH701 glide ratio {best_ld:.1f} outside expected 8-10"

    def test_best_glide_ratio_in_realistic_range_generic(
        self, generic_ulm_model: ULM6DOFFlightModel
    ) -> None:
        """Test generic ULM Class 3 best glide ratio is realistic."""
        best_ld = generic_ulm_model.get_best_glide_ratio()

        # Generic multiaxis ULM typically achieves 8:1 to 12:1
        assert 7.0 <= best_ld <= 13.0, (
            f"Generic ULM glide ratio {best_ld:.1f} outside expected 8-12"
        )

    def test_best_glide_cl_is_reasonable(self, ch701_model: ULM6DOFFlightModel) -> None:
        """Test best glide CL is in reasonable range."""
        cl_best = ch701_model.get_best_glide_cl()

        # Best glide CL typically 0.5 to 1.0 for light aircraft
        assert 0.4 <= cl_best <= 1.2, f"Best glide CL {cl_best:.2f} outside reasonable range"

    def test_current_glide_ratio_zero_at_rest(self, ch701_model: ULM6DOFFlightModel) -> None:
        """Test current glide ratio is zero when aircraft at rest."""
        # No update called, drag_coefficient_total should be 0
        ld = ch701_model.get_glide_ratio()
        assert ld == 0.0

    def test_current_glide_ratio_in_flight(self, ch701_model: ULM6DOFFlightModel) -> None:
        """Test current glide ratio is computed correctly in flight."""
        # Set up for steady flight
        ch701_model.state.velocity = Vector3(0.0, 0.0, 30.0)  # 30 m/s forward
        ch701_model.state.rotation.x = 0.05  # Small pitch up

        inputs = ControlInputs(throttle=0.0)
        ch701_model.update(0.016, inputs)

        ld = ch701_model.get_glide_ratio()

        # In flight, should have a positive glide ratio
        assert ld > 0.0
        # Should be less than or near best glide ratio
        assert ld <= ch701_model.get_best_glide_ratio() * 1.1

    def test_higher_drag_reduces_glide_ratio(self) -> None:
        """Test that higher parasite drag reduces glide ratio."""
        model_low_drag = ULM6DOFFlightModel()
        model_low_drag.initialize(
            {
                "wing_area_sqft": 122.0,
                "weight_lbs": 900.0,
                "max_thrust_lbs": 100.0,
                "wing_span_m": 8.0,
                "drag_coefficient": 0.030,
            }
        )

        model_high_drag = ULM6DOFFlightModel()
        model_high_drag.initialize(
            {
                "wing_area_sqft": 122.0,
                "weight_lbs": 900.0,
                "max_thrust_lbs": 100.0,
                "wing_span_m": 8.0,
                "drag_coefficient": 0.050,
            }
        )

        assert model_low_drag.get_best_glide_ratio() > model_high_drag.get_best_glide_ratio()

    def test_higher_aspect_ratio_improves_glide_ratio(self) -> None:
        """Test that higher aspect ratio improves glide ratio."""
        model_low_ar = ULM6DOFFlightModel()
        model_low_ar.initialize(
            {
                "wing_area_sqft": 122.0,
                "weight_lbs": 900.0,
                "max_thrust_lbs": 100.0,
                "wing_span_m": 7.0,  # Lower AR
            }
        )

        model_high_ar = ULM6DOFFlightModel()
        model_high_ar.initialize(
            {
                "wing_area_sqft": 122.0,
                "weight_lbs": 900.0,
                "max_thrust_lbs": 100.0,
                "wing_span_m": 10.0,  # Higher AR
            }
        )

        assert model_high_ar.get_best_glide_ratio() > model_low_ar.get_best_glide_ratio()

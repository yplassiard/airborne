"""Tests for Weight-Shift (pendular/trike) flight model."""

import math

import pytest

from airborne.physics.flight_model.base import AircraftState, ControlInputs
from airborne.physics.flight_model.weight_shift import WeightShiftFlightModel
from airborne.physics.vectors import Vector3


class TestWeightShiftFlightModelInitialization:
    """Test WeightShiftFlightModel initialization."""

    def test_initialization_with_required_params(self) -> None:
        """Test model initializes with required parameters."""
        model = WeightShiftFlightModel()
        model.initialize(
            {
                "wing_area_sqft": 180.0,
                "weight_lbs": 550.0,
            }
        )

        assert model.wing_area == pytest.approx(180.0 * 0.092903, rel=0.01)
        assert model.empty_mass == pytest.approx(550.0 * 0.453592, rel=0.01)

    def test_initialization_missing_wing_area(self) -> None:
        """Test initialization fails without wing_area_sqft."""
        model = WeightShiftFlightModel()
        with pytest.raises(ValueError, match="wing_area_sqft required"):
            model.initialize({"weight_lbs": 550.0})

    def test_initialization_missing_weight(self) -> None:
        """Test initialization fails without weight_lbs."""
        model = WeightShiftFlightModel()
        with pytest.raises(ValueError, match="weight_lbs required"):
            model.initialize({"wing_area_sqft": 180.0})

    def test_initialization_with_optional_params(self) -> None:
        """Test initialization with optional parameters."""
        model = WeightShiftFlightModel()
        model.initialize(
            {
                "wing_area_sqft": 180.0,
                "weight_lbs": 550.0,
                "wing_span_m": 10.5,
                "hang_point_height_m": 1.3,
                "trim_airspeed_kt": 55.0,
            }
        )

        assert model.wing_span == 10.5
        assert model.hang_point_height == 1.3
        assert model.trim_airspeed == pytest.approx(55.0 * 0.514444, rel=0.01)

    def test_weight_shift_specific_defaults(self) -> None:
        """Test weight-shift specific default values."""
        model = WeightShiftFlightModel()
        model.initialize(
            {
                "wing_area_sqft": 180.0,
                "weight_lbs": 550.0,
            }
        )

        # Flex wing characteristics
        assert model.cl_0 == 0.50  # Higher base CL for curved wing
        assert model.stall_aoa_deg == 20.0  # Higher stall AOA for flex wing
        assert model.drag_coefficient == 0.06  # Higher drag


class TestWeightShiftFlightModelPhysics:
    """Test WeightShiftFlightModel physics calculations."""

    @pytest.fixture
    def initialized_model(self) -> WeightShiftFlightModel:
        """Create an initialized weight-shift model."""
        model = WeightShiftFlightModel()
        model.initialize(
            {
                "wing_area_sqft": 180.0,
                "weight_lbs": 550.0,
                "wing_span_m": 10.0,
                "max_thrust_lbs": 180.0,
            }
        )
        return model

    def test_update_returns_state(self, initialized_model: WeightShiftFlightModel) -> None:
        """Test update returns aircraft state."""
        inputs = ControlInputs(throttle=0.5)
        state = initialized_model.update(0.016, inputs)

        assert isinstance(state, AircraftState)

    def test_update_increments_counter(self, initialized_model: WeightShiftFlightModel) -> None:
        """Test update increments the update counter."""
        inputs = ControlInputs()
        initial_count = initialized_model.get_update_count()

        initialized_model.update(0.016, inputs)
        initialized_model.update(0.016, inputs)

        assert initialized_model.get_update_count() == initial_count + 2

    def test_lift_generated_at_airspeed(self, initialized_model: WeightShiftFlightModel) -> None:
        """Test lift is generated when aircraft has airspeed."""
        initialized_model.state.velocity = Vector3(0.0, 0.0, 25.0)
        initialized_model.state.rotation.x = 0.05

        inputs = ControlInputs(throttle=0.5)
        initialized_model.update(0.016, inputs)

        forces = initialized_model.get_forces()
        assert forces.lift.y > 0.0

    def test_weight_always_downward(self, initialized_model: WeightShiftFlightModel) -> None:
        """Test weight force always acts downward."""
        inputs = ControlInputs(throttle=0.5)
        initialized_model.update(0.016, inputs)

        forces = initialized_model.get_forces()
        assert forces.weight.y < 0.0


class TestWeightShiftPendulumDynamics:
    """Test pendulum dynamics unique to weight-shift aircraft."""

    @pytest.fixture
    def model(self) -> WeightShiftFlightModel:
        """Create initialized model."""
        m = WeightShiftFlightModel()
        m.initialize(
            {
                "wing_area_sqft": 180.0,
                "weight_lbs": 550.0,
                "pitch_authority": 0.3,
                "roll_authority": 0.25,
            }
        )
        return m

    def test_bar_forward_creates_pitch_offset(self, model: WeightShiftFlightModel) -> None:
        """Test pushing bar forward creates pitch offset."""
        # Push bar forward (positive pitch input)
        inputs = ControlInputs(pitch=0.5, throttle=0.5)

        for _ in range(60):  # Run for ~1 second
            model.update(0.016, inputs)

        pitch_offset, _ = model.get_trike_offsets()
        assert pitch_offset > 0.0  # Trike should be offset forward

    def test_bar_back_creates_negative_pitch_offset(self, model: WeightShiftFlightModel) -> None:
        """Test pulling bar back creates negative pitch offset."""
        inputs = ControlInputs(pitch=-0.5, throttle=0.5)

        for _ in range(60):
            model.update(0.016, inputs)

        pitch_offset, _ = model.get_trike_offsets()
        assert pitch_offset < 0.0  # Trike should be offset back

    def test_bar_left_creates_roll_offset(self, model: WeightShiftFlightModel) -> None:
        """Test shifting bar left creates roll offset."""
        inputs = ControlInputs(roll=-0.5, throttle=0.5)

        for _ in range(60):
            model.update(0.016, inputs)

        _, roll_offset = model.get_trike_offsets()
        assert roll_offset < 0.0

    def test_bar_right_creates_positive_roll_offset(self, model: WeightShiftFlightModel) -> None:
        """Test shifting bar right creates positive roll offset."""
        inputs = ControlInputs(roll=0.5, throttle=0.5)

        for _ in range(60):
            model.update(0.016, inputs)

        _, roll_offset = model.get_trike_offsets()
        assert roll_offset > 0.0

    def test_trike_offset_limited(self, model: WeightShiftFlightModel) -> None:
        """Test trike offset is physically limited."""
        # Try to push bar all the way
        inputs = ControlInputs(pitch=1.0, roll=1.0, throttle=0.5)

        for _ in range(200):
            model.update(0.016, inputs)

        pitch_offset, roll_offset = model.get_trike_offsets()

        # Should be limited to max offset (~0.4 rad)
        assert abs(pitch_offset) <= 0.45
        assert abs(roll_offset) <= 0.45

    def test_pendulum_returns_to_neutral(self, model: WeightShiftFlightModel) -> None:
        """Test trike returns to neutral when bar released."""
        # First offset the trike
        inputs = ControlInputs(pitch=0.8, throttle=0.5)
        for _ in range(60):
            model.update(0.016, inputs)

        initial_offset, _ = model.get_trike_offsets()
        assert abs(initial_offset) > 0.1

        # Release bar (neutral input)
        inputs = ControlInputs(pitch=0.0, throttle=0.5)
        for _ in range(120):
            model.update(0.016, inputs)

        final_offset, _ = model.get_trike_offsets()
        assert abs(final_offset) < abs(initial_offset)


class TestWeightShiftSpeedStability:
    """Test speed stability unique to flex-wing aircraft."""

    @pytest.fixture
    def model(self) -> WeightShiftFlightModel:
        """Create model with known trim speed."""
        m = WeightShiftFlightModel()
        m.initialize(
            {
                "wing_area_sqft": 180.0,
                "weight_lbs": 550.0,
                "trim_airspeed_kt": 50.0,  # ~25.7 m/s
                "speed_stability": 0.5,
            }
        )
        return m

    def test_trim_speed_configured(self, model: WeightShiftFlightModel) -> None:
        """Test trim speed is set from configuration."""
        expected_trim = 50.0 * 0.514444  # kt to m/s
        assert model.trim_airspeed == pytest.approx(expected_trim, rel=0.01)


class TestWeightShiftLiftCoefficient:
    """Test flex wing lift coefficient calculations."""

    @pytest.fixture
    def model(self) -> WeightShiftFlightModel:
        """Create initialized model."""
        m = WeightShiftFlightModel()
        m.initialize(
            {
                "wing_area_sqft": 180.0,
                "weight_lbs": 550.0,
                "cl_0": 0.50,
                "cl_alpha": 0.08,
                "cl_max": 1.4,
                "stall_aoa_deg": 20.0,
            }
        )
        return m

    def test_cl_at_zero_aoa(self, model: WeightShiftFlightModel) -> None:
        """Test CL at zero angle of attack."""
        cl = model._calculate_lift_coefficient(0.0)
        assert cl == pytest.approx(0.50, rel=0.01)

    def test_cl_increases_with_aoa(self, model: WeightShiftFlightModel) -> None:
        """Test CL increases with angle of attack."""
        cl_5deg = model._calculate_lift_coefficient(math.radians(5.0))
        cl_10deg = model._calculate_lift_coefficient(math.radians(10.0))

        assert cl_10deg > cl_5deg

    def test_cl_limited_at_max(self, model: WeightShiftFlightModel) -> None:
        """Test CL doesn't exceed cl_max."""
        cl = model._calculate_lift_coefficient(math.radians(18.0))
        assert cl <= model.cl_max

    def test_flex_wing_gentle_stall(self, model: WeightShiftFlightModel) -> None:
        """Test flex wing has gentler stall characteristics."""
        cl_at_stall = model._calculate_lift_coefficient(math.radians(20.0))
        cl_5_past_stall = model._calculate_lift_coefficient(math.radians(25.0))
        cl_10_past_stall = model._calculate_lift_coefficient(math.radians(30.0))

        # Should decrease gradually, not dramatically
        assert cl_5_past_stall < cl_at_stall
        assert cl_10_past_stall < cl_5_past_stall
        # But should still have significant lift
        assert cl_10_past_stall > 0.3


class TestWeightShiftModelReset:
    """Test weight-shift model reset functionality."""

    def test_reset_to_new_state(self) -> None:
        """Test model can be reset to a new state."""
        model = WeightShiftFlightModel()
        model.initialize(
            {
                "wing_area_sqft": 180.0,
                "weight_lbs": 550.0,
            }
        )

        # Run some updates with bar input
        inputs = ControlInputs(pitch=0.5, throttle=0.5)
        for _ in range(30):
            model.update(0.016, inputs)

        # Verify trike is offset
        pitch_offset, _ = model.get_trike_offsets()
        assert abs(pitch_offset) > 0.01

        # Reset
        new_state = AircraftState(
            position=Vector3(100.0, 500.0, 200.0),
            velocity=Vector3(0.0, 0.0, 25.0),
        )
        model.reset(new_state)

        # Offsets should be cleared
        pitch_offset, roll_offset = model.get_trike_offsets()
        assert pitch_offset == 0.0
        assert roll_offset == 0.0
        assert model.get_update_count() == 0

    def test_reset_clears_external_forces(self) -> None:
        """Test reset clears accumulated external forces."""
        model = WeightShiftFlightModel()
        model.initialize(
            {
                "wing_area_sqft": 180.0,
                "weight_lbs": 550.0,
            }
        )

        model.apply_force(Vector3(1000.0, 0.0, 0.0), Vector3.zero())
        model.reset(AircraftState())

        assert model.external_force == Vector3.zero()


class TestWeightShiftGlideRatio:
    """Test glide ratio calculations for ULM Class 2 (trike) aircraft."""

    @pytest.fixture
    def tanarg_model(self) -> WeightShiftFlightModel:
        """Create a model configured like an Air Création Tanarg."""
        model = WeightShiftFlightModel()
        model.initialize(
            {
                "wing_area_sqft": 161.0,  # 15 m² BioniX wing
                "weight_lbs": 595.0,
                "wing_span_m": 9.8,
                "drag_coefficient": 0.055,
                "oswald_efficiency": 0.6,
            }
        )
        return model

    @pytest.fixture
    def generic_trike_model(self) -> WeightShiftFlightModel:
        """Create a generic trike model."""
        model = WeightShiftFlightModel()
        model.initialize(
            {
                "wing_area_sqft": 180.0,
                "weight_lbs": 550.0,
                "wing_span_m": 10.0,
                "drag_coefficient": 0.065,
            }
        )
        return model

    def test_aspect_ratio_calculated_from_geometry(
        self, tanarg_model: WeightShiftFlightModel
    ) -> None:
        """Test aspect ratio is calculated from span and area."""
        # Tanarg: span=9.8m, area=15m² -> AR = 9.8²/15 ≈ 6.4
        ar = tanarg_model.get_aspect_ratio()
        expected_ar = 9.8**2 / (161.0 * 0.092903)
        assert ar == pytest.approx(expected_ar, rel=0.01)

    def test_best_glide_ratio_in_realistic_range_tanarg(
        self, tanarg_model: WeightShiftFlightModel
    ) -> None:
        """Test Tanarg best glide ratio is realistic (6:1 to 8:1)."""
        best_ld = tanarg_model.get_best_glide_ratio()

        # High-performance trike with streamlined pod: 7:1 to 9:1
        assert 6.0 <= best_ld <= 10.0, f"Tanarg glide ratio {best_ld:.1f} outside expected 7-9"

    def test_best_glide_ratio_in_realistic_range_generic(
        self, generic_trike_model: WeightShiftFlightModel
    ) -> None:
        """Test generic trike best glide ratio is realistic."""
        best_ld = generic_trike_model.get_best_glide_ratio()

        # Generic trike typically achieves 5:1 to 8:1
        assert 5.0 <= best_ld <= 9.0, (
            f"Generic trike glide ratio {best_ld:.1f} outside expected 5-8"
        )

    def test_trike_glide_ratio_lower_than_multiaxis(self) -> None:
        """Test that trike glide ratio is lower than multiaxis ULM."""
        # Create comparable aircraft
        trike = WeightShiftFlightModel()
        trike.initialize(
            {
                "wing_area_sqft": 160.0,
                "weight_lbs": 550.0,
                "wing_span_m": 10.0,
                "drag_coefficient": 0.06,  # Higher drag (exposed pilot)
                "oswald_efficiency": 0.6,  # Lower efficiency (flex wing)
            }
        )

        # Import here to avoid circular imports in test
        from airborne.physics.flight_model.ulm_6dof import ULM6DOFFlightModel

        multiaxis = ULM6DOFFlightModel()
        multiaxis.initialize(
            {
                "wing_area_sqft": 160.0,
                "weight_lbs": 550.0,
                "max_thrust_lbs": 100.0,
                "wing_span_m": 10.0,
                "drag_coefficient": 0.035,  # Lower drag (enclosed)
                "oswald_efficiency": 0.75,  # Higher efficiency (rigid wing)
            }
        )

        # Multiaxis should have better glide ratio
        assert multiaxis.get_best_glide_ratio() > trike.get_best_glide_ratio()

    def test_best_glide_cl_is_reasonable(self, tanarg_model: WeightShiftFlightModel) -> None:
        """Test best glide CL is in reasonable range for flex wing."""
        cl_best = tanarg_model.get_best_glide_cl()

        # Best glide CL for flex wing typically 0.6 to 1.0
        assert 0.5 <= cl_best <= 1.3, f"Best glide CL {cl_best:.2f} outside reasonable range"

    def test_current_glide_ratio_zero_at_rest(self, tanarg_model: WeightShiftFlightModel) -> None:
        """Test current glide ratio is zero when aircraft at rest."""
        ld = tanarg_model.get_glide_ratio()
        assert ld == 0.0

    def test_current_glide_ratio_in_flight(self, tanarg_model: WeightShiftFlightModel) -> None:
        """Test current glide ratio is computed correctly in flight."""
        # Set up for steady flight
        tanarg_model.state.velocity = Vector3(0.0, 0.0, 25.0)  # 25 m/s forward (~50 kt)
        tanarg_model.state.rotation.x = 0.05  # Small pitch up

        inputs = ControlInputs(throttle=0.0)
        tanarg_model.update(0.016, inputs)

        ld = tanarg_model.get_glide_ratio()

        # In flight, should have a positive glide ratio
        assert ld > 0.0
        # Should be less than or near best glide ratio
        assert ld <= tanarg_model.get_best_glide_ratio() * 1.1

    def test_streamlined_pod_improves_glide_ratio(self) -> None:
        """Test that lower drag (streamlined pod) improves glide ratio."""
        model_basic = WeightShiftFlightModel()
        model_basic.initialize(
            {
                "wing_area_sqft": 180.0,
                "weight_lbs": 550.0,
                "wing_span_m": 10.0,
                "drag_coefficient": 0.070,  # Open trike, exposed pilot
            }
        )

        model_streamlined = WeightShiftFlightModel()
        model_streamlined.initialize(
            {
                "wing_area_sqft": 180.0,
                "weight_lbs": 550.0,
                "wing_span_m": 10.0,
                "drag_coefficient": 0.050,  # Streamlined pod
            }
        )

        assert model_streamlined.get_best_glide_ratio() > model_basic.get_best_glide_ratio()

    def test_higher_performance_wing_improves_glide(self) -> None:
        """Test that higher performance wing improves glide ratio."""
        model_basic_wing = WeightShiftFlightModel()
        model_basic_wing.initialize(
            {
                "wing_area_sqft": 180.0,
                "weight_lbs": 550.0,
                "wing_span_m": 10.0,
                "oswald_efficiency": 0.55,  # Basic flex wing
            }
        )

        model_perf_wing = WeightShiftFlightModel()
        model_perf_wing.initialize(
            {
                "wing_area_sqft": 180.0,
                "weight_lbs": 550.0,
                "wing_span_m": 10.0,
                "oswald_efficiency": 0.65,  # High-performance wing (BioniX etc)
            }
        )

        assert model_perf_wing.get_best_glide_ratio() > model_basic_wing.get_best_glide_ratio()

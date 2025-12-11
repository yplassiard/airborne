"""Tests for ground effect implementation in Simple6DOF flight model.

Ground effect (effet de sol) increases lift and reduces induced drag when
flying close to the ground. These tests verify:
1. Ground effect calculation at various heights
2. Integration with lift and drag forces
3. Interaction with other forces (thrust, weight)
4. Behavior at edge cases (on ground, high altitude)
5. Correct physics during takeoff and landing scenarios
"""

import math
import pytest

from airborne.physics.flight_model.simple_6dof import Simple6DOFFlightModel
from airborne.physics.flight_model.base import AircraftState, ControlInputs
from airborne.physics.vectors import Vector3


class TestGroundEffectCalculation:
    """Tests for the ground effect calculation method."""

    @pytest.fixture
    def flight_model(self):
        """Create a configured flight model for testing."""
        model = Simple6DOFFlightModel()
        model.initialize({
            "wing_area_sqft": 174.0,  # C172 wing area
            "weight_lbs": 2400.0,
            "max_thrust_lbs": 300.0,
            "wing_span_m": 11.0,  # C172 wingspan
        })
        return model

    def test_no_ground_effect_above_wingspan(self, flight_model):
        """Test no ground effect when height > wingspan."""
        # At 15m AGL with 11m wingspan - should have no effect
        lift_mult, drag_mult = flight_model._calculate_ground_effect(15.0)

        assert lift_mult == 1.0
        assert drag_mult == 1.0

    def test_no_ground_effect_on_ground(self, flight_model):
        """Test no ground effect when on ground (height <= 0)."""
        lift_mult, drag_mult = flight_model._calculate_ground_effect(0.0)

        assert lift_mult == 1.0
        assert drag_mult == 1.0

        # Also test negative (below ground - shouldn't happen but be safe)
        lift_mult, drag_mult = flight_model._calculate_ground_effect(-1.0)

        assert lift_mult == 1.0
        assert drag_mult == 1.0

    def test_maximum_ground_effect_at_low_height(self, flight_model):
        """Test maximum ground effect at very low heights."""
        # At 1m AGL with 11m wingspan (h/b = 0.09)
        lift_mult, drag_mult = flight_model._calculate_ground_effect(1.0)

        # Should have significant effect
        assert lift_mult > 1.10  # At least 10% lift increase
        assert drag_mult < 0.60  # At least 40% induced drag reduction

    def test_moderate_ground_effect_at_half_wingspan(self, flight_model):
        """Test moderate ground effect at half wingspan height."""
        # At 5.5m AGL with 11m wingspan (h/b = 0.5)
        lift_mult, drag_mult = flight_model._calculate_ground_effect(5.5)

        # Should have moderate effect
        assert 1.02 < lift_mult < 1.08  # 2-8% lift increase
        assert 0.70 < drag_mult < 0.90  # 10-30% drag reduction

    def test_minimal_ground_effect_near_wingspan(self, flight_model):
        """Test minimal ground effect near wingspan height."""
        # At 10m AGL with 11m wingspan (h/b = 0.91)
        lift_mult, drag_mult = flight_model._calculate_ground_effect(10.0)

        # Should have minimal effect
        assert 1.0 < lift_mult < 1.02  # Less than 2% lift increase
        assert 0.95 < drag_mult < 1.0  # Less than 5% drag reduction

    def test_ground_effect_gradual_transition(self, flight_model):
        """Test that ground effect transitions smoothly with height."""
        heights = [1.0, 2.0, 4.0, 6.0, 8.0, 10.0, 11.0, 12.0]
        lift_mults = []
        drag_mults = []

        for h in heights:
            lift_mult, drag_mult = flight_model._calculate_ground_effect(h)
            lift_mults.append(lift_mult)
            drag_mults.append(drag_mult)

        # Lift multiplier should decrease monotonically with height
        for i in range(len(lift_mults) - 1):
            assert lift_mults[i] >= lift_mults[i + 1], \
                f"Lift multiplier should decrease: {lift_mults[i]} >= {lift_mults[i+1]} at heights {heights[i]}, {heights[i+1]}"

        # Drag multiplier should increase monotonically with height
        for i in range(len(drag_mults) - 1):
            assert drag_mults[i] <= drag_mults[i + 1], \
                f"Drag multiplier should increase: {drag_mults[i]} <= {drag_mults[i+1]} at heights {heights[i]}, {heights[i+1]}"

    def test_ground_effect_disabled(self, flight_model):
        """Test that ground effect can be disabled."""
        flight_model.set_ground_effect_enabled(False)

        # Even at low height, should return 1.0
        lift_mult, drag_mult = flight_model._calculate_ground_effect(1.0)

        assert lift_mult == 1.0
        assert drag_mult == 1.0

        # Re-enable and verify it works again
        flight_model.set_ground_effect_enabled(True)
        lift_mult, drag_mult = flight_model._calculate_ground_effect(1.0)

        assert lift_mult > 1.0

    def test_ground_effect_factor_stored(self, flight_model):
        """Test that ground effect factor is stored for telemetry."""
        # Set up state with low AGL
        flight_model.state.agl_altitude_m = 2.0
        flight_model.state.velocity = Vector3(0.0, 0.0, 30.0)  # ~60 kts forward

        # Run force calculation
        inputs = ControlInputs(throttle=0.5)
        flight_model._calculate_forces(inputs)

        # Ground effect factor should be stored
        assert flight_model.get_ground_effect_factor() > 1.0


class TestGroundEffectWithForces:
    """Tests for ground effect integration with force calculations."""

    @pytest.fixture
    def flight_model(self):
        """Create a configured flight model for testing."""
        model = Simple6DOFFlightModel()
        model.initialize({
            "wing_area_sqft": 174.0,
            "weight_lbs": 2400.0,
            "max_thrust_lbs": 300.0,
            "wing_span_m": 11.0,
        })
        return model

    def test_lift_increased_in_ground_effect(self, flight_model):
        """Test that lift force is increased when in ground effect."""
        # Set up state at approach speed
        flight_model.state.velocity = Vector3(0.0, 0.0, 30.0)  # ~60 kts
        flight_model.state.rotation = Vector3(0.05, 0.0, 0.0)  # ~3° pitch

        inputs = ControlInputs(throttle=0.3, flaps=0.5)

        # Calculate forces OUT of ground effect (high altitude)
        flight_model.state.agl_altitude_m = 100.0
        flight_model._calculate_forces(inputs)
        lift_oge = flight_model.forces.lift.y

        # Calculate forces IN ground effect (low altitude)
        flight_model.state.agl_altitude_m = 2.0
        flight_model._calculate_forces(inputs)
        lift_ige = flight_model.forces.lift.y

        # Lift should be higher in ground effect
        assert lift_ige > lift_oge, \
            f"Lift IGE ({lift_ige:.1f}N) should be greater than OGE ({lift_oge:.1f}N)"

        # Increase should be reasonable (5-15%)
        lift_increase_pct = (lift_ige - lift_oge) / lift_oge * 100
        assert 3.0 < lift_increase_pct < 20.0, \
            f"Lift increase {lift_increase_pct:.1f}% outside expected range"

    def test_induced_drag_reduced_in_ground_effect(self, flight_model):
        """Test that induced drag is reduced when in ground effect."""
        # Set up state at approach speed with positive lift
        flight_model.state.velocity = Vector3(0.0, 0.0, 30.0)
        flight_model.state.rotation = Vector3(0.1, 0.0, 0.0)  # ~6° pitch for more lift

        inputs = ControlInputs(throttle=0.3, flaps=0.5)

        # Calculate forces OUT of ground effect
        flight_model.state.agl_altitude_m = 100.0
        flight_model._calculate_forces(inputs)
        induced_drag_oge = flight_model.drag_induced_n

        # Calculate forces IN ground effect
        flight_model.state.agl_altitude_m = 2.0
        flight_model._calculate_forces(inputs)
        induced_drag_ige = flight_model.drag_induced_n

        # Induced drag should be lower in ground effect
        assert induced_drag_ige < induced_drag_oge, \
            f"Induced drag IGE ({induced_drag_ige:.1f}N) should be less than OGE ({induced_drag_oge:.1f}N)"

    def test_parasite_drag_unchanged_in_ground_effect(self, flight_model):
        """Test that parasite drag is NOT affected by ground effect."""
        flight_model.state.velocity = Vector3(0.0, 0.0, 30.0)

        inputs = ControlInputs(throttle=0.3)

        # Calculate forces OUT of ground effect
        flight_model.state.agl_altitude_m = 100.0
        flight_model._calculate_forces(inputs)
        parasite_drag_oge = flight_model.drag_parasite_n

        # Calculate forces IN ground effect
        flight_model.state.agl_altitude_m = 2.0
        flight_model._calculate_forces(inputs)
        parasite_drag_ige = flight_model.drag_parasite_n

        # Parasite drag should be the same
        assert abs(parasite_drag_ige - parasite_drag_oge) < 0.1, \
            f"Parasite drag should be unchanged: IGE={parasite_drag_ige:.1f}N, OGE={parasite_drag_oge:.1f}N"

    def test_thrust_unaffected_by_ground_effect(self, flight_model):
        """Test that thrust is not affected by ground effect."""
        flight_model.state.velocity = Vector3(0.0, 0.0, 30.0)
        flight_model.state.rotation = Vector3(0.0, 0.0, 0.0)  # Heading north

        inputs = ControlInputs(throttle=0.8)

        # Calculate forces OUT of ground effect
        flight_model.state.agl_altitude_m = 100.0
        flight_model._calculate_forces(inputs)
        thrust_oge = flight_model.forces.thrust.magnitude()

        # Calculate forces IN ground effect
        flight_model.state.agl_altitude_m = 2.0
        flight_model._calculate_forces(inputs)
        thrust_ige = flight_model.forces.thrust.magnitude()

        # Thrust should be identical
        assert abs(thrust_ige - thrust_oge) < 0.1, \
            f"Thrust should be unchanged: IGE={thrust_ige:.1f}N, OGE={thrust_oge:.1f}N"

    def test_weight_unaffected_by_ground_effect(self, flight_model):
        """Test that weight is not affected by ground effect."""
        inputs = ControlInputs()

        # Calculate forces OUT of ground effect
        flight_model.state.agl_altitude_m = 100.0
        flight_model._calculate_forces(inputs)
        weight_oge = flight_model.forces.weight.y

        # Calculate forces IN ground effect
        flight_model.state.agl_altitude_m = 2.0
        flight_model._calculate_forces(inputs)
        weight_ige = flight_model.forces.weight.y

        # Weight should be identical
        assert weight_ige == weight_oge


class TestGroundEffectTakeoffScenario:
    """Tests simulating takeoff with ground effect."""

    @pytest.fixture
    def flight_model(self):
        """Create a configured flight model for takeoff testing."""
        model = Simple6DOFFlightModel()
        model.initialize({
            "wing_area_sqft": 174.0,
            "weight_lbs": 2400.0,
            "max_thrust_lbs": 300.0,
            "wing_span_m": 11.0,
            "cl_0": 0.30,
            "cl_alpha": 0.105,
        })
        return model

    def test_takeoff_roll_lift_buildup(self, flight_model):
        """Test lift increases during takeoff roll with ground effect."""
        dt = 0.016  # 60 Hz
        inputs = ControlInputs(throttle=1.0)

        # Start on ground
        flight_model.state.on_ground = True
        flight_model.state.agl_altitude_m = 0.0
        flight_model.state.velocity = Vector3(0.0, 0.0, 10.0)  # Starting roll
        flight_model.state.mark_velocity_dirty()

        lifts = []
        speeds = [10, 15, 20, 25, 30]  # m/s

        for speed in speeds:
            flight_model.state.velocity = Vector3(0.0, 0.0, float(speed))
            flight_model.state.mark_velocity_dirty()  # Mark dirty after velocity change
            flight_model.state.agl_altitude_m = 1.5  # Just above ground
            flight_model._calculate_forces(inputs)
            lifts.append(flight_model.forces.lift.magnitude())

        # Lift should increase with speed (quadratically)
        for i in range(len(lifts) - 1):
            assert lifts[i + 1] > lifts[i], \
                f"Lift should increase with speed: {lifts[i]:.1f}N < {lifts[i+1]:.1f}N"

    def test_liftoff_transition_out_of_ground_effect(self, flight_model):
        """Test the transition out of ground effect after liftoff."""
        flight_model.state.velocity = Vector3(0.0, 2.0, 30.0)  # Climbing at 30m/s
        flight_model.state.rotation = Vector3(0.1, 0.0, 0.0)  # Climb pitch

        inputs = ControlInputs(throttle=1.0)

        # Track lift as altitude increases
        altitudes = [1.0, 2.0, 4.0, 6.0, 8.0, 11.0, 15.0]
        lift_values = []

        for alt in altitudes:
            flight_model.state.agl_altitude_m = alt
            flight_model._calculate_forces(inputs)
            lift_values.append(flight_model.forces.lift.magnitude())

        # Lift should decrease as we climb out of ground effect
        # (same CL but less ground effect boost)
        max_lift_idx = 0  # Should be at lowest altitude
        assert lift_values[0] >= lift_values[-1], \
            "Lift should be higher in ground effect than out of it"

    def test_takeoff_performance_improvement(self, flight_model):
        """Test that ground effect provides net performance improvement."""
        flight_model.state.velocity = Vector3(0.0, 0.0, 25.0)  # ~50 kts
        flight_model.state.rotation = Vector3(0.08, 0.0, 0.0)  # ~5° pitch

        inputs = ControlInputs(throttle=1.0)

        # Calculate at 2m AGL (in ground effect)
        flight_model.state.agl_altitude_m = 2.0
        flight_model._calculate_forces(inputs)

        lift_ige = flight_model.forces.lift.magnitude()
        total_drag_ige = flight_model.forces.drag.magnitude()

        # Calculate at 50m AGL (out of ground effect)
        flight_model.state.agl_altitude_m = 50.0
        flight_model._calculate_forces(inputs)

        lift_oge = flight_model.forces.lift.magnitude()
        total_drag_oge = flight_model.forces.drag.magnitude()

        # L/D ratio should be better in ground effect
        ld_ige = lift_ige / total_drag_ige if total_drag_ige > 0 else 0
        ld_oge = lift_oge / total_drag_oge if total_drag_oge > 0 else 0

        assert ld_ige > ld_oge, \
            f"L/D should be better in ground effect: IGE={ld_ige:.2f}, OGE={ld_oge:.2f}"


class TestGroundEffectLandingScenario:
    """Tests simulating landing with ground effect (float tendency)."""

    @pytest.fixture
    def flight_model(self):
        """Create a configured flight model for landing testing."""
        model = Simple6DOFFlightModel()
        model.initialize({
            "wing_area_sqft": 174.0,
            "weight_lbs": 2400.0,
            "max_thrust_lbs": 300.0,
            "wing_span_m": 11.0,
        })
        return model

    def test_landing_flare_float(self, flight_model):
        """Test that aircraft tends to float in ground effect during flare."""
        # Approach configuration
        flight_model.state.velocity = Vector3(0.0, -1.0, 28.0)  # Descending at approach speed
        flight_model.state.rotation = Vector3(0.05, 0.0, 0.0)  # Slight pitch up

        inputs = ControlInputs(throttle=0.2, flaps=1.0)  # Landing config

        # Calculate total vertical force at different heights
        heights = [10.0, 5.0, 3.0, 2.0, 1.0]
        vertical_forces = []

        weight = flight_model.state.mass * 9.81

        for h in heights:
            flight_model.state.agl_altitude_m = h
            flight_model._calculate_forces(inputs)

            # Net vertical force = lift - weight
            lift_vertical = flight_model.forces.lift.y
            net_vertical = lift_vertical - weight
            vertical_forces.append(net_vertical)

        # As we get lower, lift increases (ground effect)
        # So the net upward force should increase (become less negative)
        for i in range(len(vertical_forces) - 1):
            assert vertical_forces[i + 1] >= vertical_forces[i] - 10, \
                f"Vertical force should increase (less negative) as we descend into ground effect"

    def test_flare_requires_pitch_reduction(self, flight_model):
        """Test that more lift in ground effect means less pitch needed to float."""
        flight_model.state.velocity = Vector3(0.0, 0.0, 28.0)

        inputs = ControlInputs(throttle=0.1, flaps=1.0)

        # Find pitch needed to achieve level flight (lift = weight) at two heights
        weight = flight_model.state.mass * 9.81

        def find_level_pitch(agl_m):
            """Find pitch angle where lift equals weight."""
            flight_model.state.agl_altitude_m = agl_m
            for pitch_deg in range(0, 15):
                flight_model.state.rotation = Vector3(pitch_deg * 0.0175, 0.0, 0.0)
                flight_model._calculate_forces(inputs)
                if flight_model.forces.lift.y >= weight:
                    return pitch_deg
            return 15  # Max

        pitch_oge = find_level_pitch(50.0)  # Out of ground effect
        pitch_ige = find_level_pitch(2.0)   # In ground effect

        # Should need less pitch in ground effect (or same if already level)
        assert pitch_ige <= pitch_oge, \
            f"Should need less pitch IGE ({pitch_ige}°) than OGE ({pitch_oge}°)"


class TestGroundEffectWithExternalForces:
    """Tests for ground effect interaction with external forces."""

    @pytest.fixture
    def flight_model(self):
        """Create a configured flight model."""
        model = Simple6DOFFlightModel()
        model.initialize({
            "wing_area_sqft": 174.0,
            "weight_lbs": 2400.0,
            "max_thrust_lbs": 300.0,
            "wing_span_m": 11.0,
        })
        return model

    def test_ground_effect_with_wind_gust(self, flight_model):
        """Test ground effect still works when external wind force is applied."""
        flight_model.state.velocity = Vector3(0.0, 0.0, 30.0)
        flight_model.state.agl_altitude_m = 2.0

        inputs = ControlInputs(throttle=0.5)

        # Calculate baseline with ground effect
        flight_model._calculate_forces(inputs)
        lift_baseline = flight_model.forces.lift.y

        # Apply external force (simulating wind gust)
        wind_gust = Vector3(100.0, 50.0, 0.0)  # Lateral and vertical gust
        flight_model.apply_force(wind_gust, Vector3.zero())

        # Update and check lift is still affected by ground effect
        dt = 0.016
        flight_model.update(dt, inputs)

        # Ground effect should still be applied (factor > 1.0)
        assert flight_model.get_ground_effect_factor() > 1.0

    def test_ground_effect_with_ground_forces(self, flight_model):
        """Test ground effect just above ground with ground reaction force."""
        # Just above touchdown - very low AGL
        flight_model.state.agl_altitude_m = 0.5
        flight_model.state.velocity = Vector3(0.0, -0.5, 25.0)  # About to touch down

        inputs = ControlInputs(throttle=0.1, flaps=1.0)

        flight_model._calculate_forces(inputs)

        # Should have maximum ground effect
        ge_factor = flight_model.get_ground_effect_factor()
        assert ge_factor > 1.10, \
            f"Should have strong ground effect at 0.5m AGL: {ge_factor}"

        # Lift should be significantly boosted
        lift = flight_model.forces.lift.magnitude()
        assert lift > 0, "Should have positive lift"

    def test_total_force_correct_with_ground_effect(self, flight_model):
        """Test that total force sums correctly with ground effect applied."""
        flight_model.state.velocity = Vector3(0.0, 0.0, 30.0)
        flight_model.state.agl_altitude_m = 2.0
        flight_model.state.rotation = Vector3(0.05, 0.0, 0.0)

        inputs = ControlInputs(throttle=0.7)

        flight_model._calculate_forces(inputs)

        # Verify total force is sum of components
        expected_total = (
            flight_model.forces.lift +
            flight_model.forces.drag +
            flight_model.forces.thrust +
            flight_model.forces.weight
        )

        actual_total = flight_model.forces.total

        # Should match within floating point tolerance
        assert abs(expected_total.x - actual_total.x) < 0.01
        assert abs(expected_total.y - actual_total.y) < 0.01
        assert abs(expected_total.z - actual_total.z) < 0.01


class TestGroundEffectPhysicsAccuracy:
    """Tests to verify ground effect physics are realistic."""

    @pytest.fixture
    def flight_model(self):
        """Create a C172-like flight model."""
        model = Simple6DOFFlightModel()
        model.initialize({
            "wing_area_sqft": 174.0,
            "weight_lbs": 2400.0,
            "max_thrust_lbs": 300.0,
            "wing_span_m": 11.0,
            "aspect_ratio": 7.4,
            "oswald_efficiency": 0.7,
        })
        return model

    def test_ground_effect_magnitude_realistic(self, flight_model):
        """Test that ground effect magnitude matches real-world data.

        Based on flight test data and theory:
        - At h/b = 0.1: ~10-15% lift increase, ~45-55% induced drag reduction
        - At h/b = 0.5: ~3-5% lift increase, ~15-25% induced drag reduction
        """
        # h/b = 0.1 (1.1m AGL with 11m wingspan)
        lift_mult, drag_mult = flight_model._calculate_ground_effect(1.1)
        assert 1.08 < lift_mult < 1.18, f"Lift mult at h/b=0.1: {lift_mult}"
        assert 0.40 < drag_mult < 0.60, f"Drag mult at h/b=0.1: {drag_mult}"

        # h/b = 0.5 (5.5m AGL with 11m wingspan)
        lift_mult, drag_mult = flight_model._calculate_ground_effect(5.5)
        assert 1.02 < lift_mult < 1.08, f"Lift mult at h/b=0.5: {lift_mult}"
        assert 0.70 < drag_mult < 0.90, f"Drag mult at h/b=0.5: {drag_mult}"

    def test_span_efficiency_increase_in_ground_effect(self, flight_model):
        """Test that effective span efficiency increases in ground effect.

        Ground effect increases the effective Oswald efficiency factor,
        which is reflected in reduced induced drag coefficient.
        """
        flight_model.state.velocity = Vector3(0.0, 0.0, 30.0)
        flight_model.state.rotation = Vector3(0.1, 0.0, 0.0)  # Generate lift

        inputs = ControlInputs(throttle=0.5)

        # Out of ground effect
        flight_model.state.agl_altitude_m = 50.0
        flight_model._calculate_forces(inputs)
        cd_induced_oge = flight_model.drag_induced_n

        # In ground effect
        flight_model.state.agl_altitude_m = 2.0
        flight_model._calculate_forces(inputs)
        cd_induced_ige = flight_model.drag_induced_n

        # Induced drag reduction
        reduction = (cd_induced_oge - cd_induced_ige) / cd_induced_oge

        # Should see significant reduction (20-50% at low height)
        assert 0.15 < reduction < 0.60, \
            f"Induced drag reduction {reduction*100:.1f}% outside expected range"

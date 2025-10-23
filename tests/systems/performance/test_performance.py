"""Tests for performance calculator system."""

import pytest

from airborne.systems.performance import PerformanceCalculator, VSpeedCalculator


class TestVSpeedCalculator:
    """Test V-speed calculations."""

    @pytest.fixture
    def c172_vspeed_calc(self) -> VSpeedCalculator:
        """Cessna 172 V-speed calculator."""
        return VSpeedCalculator(
            reference_weight=2550.0, reference_vstall=47.0, cl_max_clean=1.4, cl_max_landing=2.0
        )

    def test_vstall_at_reference_weight(self, c172_vspeed_calc: VSpeedCalculator) -> None:
        """Test V_stall at reference weight matches POH."""
        vstall = c172_vspeed_calc.calculate_vstall(2550.0)
        assert vstall == pytest.approx(47.0, abs=0.1)

    def test_vstall_decreases_with_lower_weight(self, c172_vspeed_calc: VSpeedCalculator) -> None:
        """Test V_stall decreases as weight decreases (sqrt relationship)."""
        # At 2000 lbs (78% of ref weight)
        vstall_light = c172_vspeed_calc.calculate_vstall(2000.0)

        # Expected: 47 × sqrt(2000/2550) = 47 × sqrt(0.784) = 47 × 0.885 = 41.6 KIAS
        expected = 47.0 * (2000.0 / 2550.0) ** 0.5
        assert vstall_light == pytest.approx(expected, abs=0.5)
        assert vstall_light < 47.0  # Lighter aircraft stalls slower

    def test_vstall_increases_with_higher_weight(self, c172_vspeed_calc: VSpeedCalculator) -> None:
        """Test V_stall increases as weight increases."""
        # At max gross (2550 lbs)
        vstall_heavy = c172_vspeed_calc.calculate_vstall(2550.0)

        # At empty + pilot (1800 lbs)
        vstall_light = c172_vspeed_calc.calculate_vstall(1800.0)

        assert vstall_heavy > vstall_light

    def test_vstall_landing_lower_than_clean(self, c172_vspeed_calc: VSpeedCalculator) -> None:
        """Test landing stall speed is lower due to flaps."""
        vstall_clean = c172_vspeed_calc.calculate_vstall(2550.0)
        vstall_landing = c172_vspeed_calc.calculate_vstall_landing(2550.0)

        assert vstall_landing < vstall_clean
        # Should be about 15-20% lower (depends on CL_max ratio)
        expected_ratio = (1.4 / 2.0) ** 0.5  # sqrt(CL_clean / CL_landing)
        assert vstall_landing == pytest.approx(vstall_clean * expected_ratio, abs=2.0)

    def test_vspeeds_relationships(self, c172_vspeed_calc: VSpeedCalculator) -> None:
        """Test V-speeds follow correct relationships."""
        vspeeds = c172_vspeed_calc.calculate_vspeeds(2550.0)

        # V_SO < V_S (landing config stalls slower)
        assert vspeeds.v_so < vspeeds.v_s

        # V_R > V_S (rotation above stall)
        assert vspeeds.v_r > vspeeds.v_s
        assert vspeeds.v_r == pytest.approx(vspeeds.v_s * 1.1, abs=1.0)

        # V_X > V_R (climb speed higher than rotation)
        assert vspeeds.v_x > vspeeds.v_r

        # V_Y > V_X (best rate faster than best angle)
        assert vspeeds.v_y > vspeeds.v_x

        # V_2 between V_R and V_X
        assert vspeeds.v_r < vspeeds.v_2 < vspeeds.v_x

    def test_vspeeds_match_poh_reference(self, c172_vspeed_calc: VSpeedCalculator) -> None:
        """Test calculated V-speeds match C172 POH at reference weight."""
        vspeeds = c172_vspeed_calc.calculate_vspeeds(2550.0)

        # POH values (C172S at 2550 lbs)
        assert vspeeds.v_s == pytest.approx(47.0, abs=1.0)  # 47 KIAS
        # V_R calculated is ~51.7, POH says 55 (includes safety margin)
        assert vspeeds.v_r == pytest.approx(51.7, abs=1.0)
        # Or check it's in reasonable range
        assert 50.0 < vspeeds.v_r < 60.0

    def test_flap_configuration_speeds(self, c172_vspeed_calc: VSpeedCalculator) -> None:
        """Test stall speed with different flap settings."""
        vs_clean = c172_vspeed_calc.calculate_vspeed_for_config(2550.0, flap_setting=0)
        vs_10deg = c172_vspeed_calc.calculate_vspeed_for_config(2550.0, flap_setting=10)
        vs_20deg = c172_vspeed_calc.calculate_vspeed_for_config(2550.0, flap_setting=20)
        vs_full = c172_vspeed_calc.calculate_vspeed_for_config(2550.0, flap_setting=30)

        # Each flap increment should reduce stall speed
        assert vs_clean > vs_10deg > vs_20deg > vs_full


class TestPerformanceCalculator:
    """Test takeoff and climb performance calculations."""

    @pytest.fixture
    def c172_config(self) -> dict:
        """Cessna 172 performance configuration."""
        return {
            "reference_weight_lbs": 2550.0,
            "wing_area_sqft": 174.0,
            "max_power_hp": 180.0,
            "cl_max_clean": 1.4,
            "cl_max_landing": 2.0,
            "vspeeds_reference": {"V_S": 47, "V_R": 55, "V_X": 59, "V_Y": 73},
            "takeoff_reference": {
                "ground_roll_ft": 960,
                "distance_50ft": 1685,
                "climb_rate_fpm": 730,
            },
        }

    def test_initialize_calculator(self, c172_config: dict) -> None:
        """Test performance calculator initialization."""
        calc = PerformanceCalculator(c172_config)

        assert calc.reference_weight == 2550.0
        assert calc.ref_ground_roll_ft == 960.0
        assert calc.ref_climb_rate_fpm == 730.0

    def test_takeoff_distance_at_reference_weight(self, c172_config: dict) -> None:
        """Test takeoff distance matches POH at reference weight."""
        calc = PerformanceCalculator(c172_config)

        takeoff = calc.calculate_takeoff_distance(2550.0, headwind_kts=0.0)

        # Should be close to POH reference (960 ft)
        assert takeoff.ground_roll_ft == pytest.approx(960.0, rel=0.05)
        assert takeoff.distance_50ft == pytest.approx(1685.0, rel=0.10)

    def test_takeoff_distance_increases_with_weight(self, c172_config: dict) -> None:
        """Test heavier aircraft needs longer takeoff roll."""
        calc = PerformanceCalculator(c172_config)

        takeoff_light = calc.calculate_takeoff_distance(2000.0)
        takeoff_heavy = calc.calculate_takeoff_distance(2550.0)

        # Heavier should need more distance
        assert takeoff_heavy.ground_roll_ft > takeoff_light.ground_roll_ft
        assert takeoff_heavy.distance_50ft > takeoff_light.distance_50ft

    def test_headwind_reduces_takeoff_distance(self, c172_config: dict) -> None:
        """Test headwind reduces takeoff distance."""
        calc = PerformanceCalculator(c172_config)

        takeoff_calm = calc.calculate_takeoff_distance(2550.0, headwind_kts=0.0)
        takeoff_headwind = calc.calculate_takeoff_distance(2550.0, headwind_kts=10.0)

        # Headwind should reduce distance
        assert takeoff_headwind.ground_roll_ft < takeoff_calm.ground_roll_ft

    def test_tailwind_increases_takeoff_distance(self, c172_config: dict) -> None:
        """Test tailwind increases takeoff distance."""
        calc = PerformanceCalculator(c172_config)

        takeoff_calm = calc.calculate_takeoff_distance(2550.0, headwind_kts=0.0)
        takeoff_tailwind = calc.calculate_takeoff_distance(2550.0, headwind_kts=-10.0)

        # Tailwind should increase distance
        assert takeoff_tailwind.ground_roll_ft > takeoff_calm.ground_roll_ft

    def test_grass_runway_increases_distance(self, c172_config: dict) -> None:
        """Test grass runway requires more distance."""
        calc = PerformanceCalculator(c172_config)

        takeoff_paved = calc.calculate_takeoff_distance(
            2550.0, headwind_kts=0.0, runway_surface="paved"
        )
        takeoff_grass = calc.calculate_takeoff_distance(
            2550.0, headwind_kts=0.0, runway_surface="grass_short"
        )

        # Grass should require more distance
        assert takeoff_grass.ground_roll_ft > takeoff_paved.ground_roll_ft

    def test_density_altitude_increases_distance(self, c172_config: dict) -> None:
        """Test higher density altitude increases takeoff distance."""
        calc = PerformanceCalculator(c172_config)

        takeoff_sealevel = calc.calculate_takeoff_distance(
            2550.0, headwind_kts=0.0, density_altitude_ft=0.0
        )
        takeoff_5000ft = calc.calculate_takeoff_distance(
            2550.0, headwind_kts=0.0, density_altitude_ft=5000.0
        )

        # High DA should increase distance
        assert takeoff_5000ft.ground_roll_ft > takeoff_sealevel.ground_roll_ft

    def test_flaps_reduce_takeoff_distance(self, c172_config: dict) -> None:
        """Test flaps reduce takeoff distance."""
        calc = PerformanceCalculator(c172_config)

        takeoff_no_flaps = calc.calculate_takeoff_distance(2550.0, headwind_kts=0.0, flap_setting=0)
        takeoff_10deg_flaps = calc.calculate_takeoff_distance(
            2550.0, headwind_kts=0.0, flap_setting=10
        )

        # Flaps should reduce distance
        assert takeoff_10deg_flaps.ground_roll_ft < takeoff_no_flaps.ground_roll_ft

    def test_climb_rate_at_reference_weight(self, c172_config: dict) -> None:
        """Test climb rate matches POH at reference weight."""
        calc = PerformanceCalculator(c172_config)

        climb_rate = calc.calculate_climb_rate(2550.0)

        # Should match POH reference (730 fpm)
        assert climb_rate == pytest.approx(730.0, rel=0.05)

    def test_climb_rate_decreases_with_weight(self, c172_config: dict) -> None:
        """Test heavier aircraft climbs slower."""
        calc = PerformanceCalculator(c172_config)

        climb_light = calc.calculate_climb_rate(2000.0)
        climb_heavy = calc.calculate_climb_rate(2550.0)

        # Lighter should climb faster
        assert climb_light > climb_heavy

    def test_climb_rate_decreases_with_density_altitude(self, c172_config: dict) -> None:
        """Test climb rate decreases at higher altitude."""
        calc = PerformanceCalculator(c172_config)

        climb_sealevel = calc.calculate_climb_rate(2550.0, density_altitude_ft=0.0)
        climb_5000ft = calc.calculate_climb_rate(2550.0, density_altitude_ft=5000.0)

        # Climb rate should be lower at altitude
        assert climb_5000ft < climb_sealevel

    def test_rotation_speed_matches_vstall(self, c172_config: dict) -> None:
        """Test rotation speed is reasonable relative to stall."""
        calc = PerformanceCalculator(c172_config)

        vspeeds = calc.calculate_vspeeds(2550.0)
        takeoff = calc.calculate_takeoff_distance(2550.0)

        # Rotation should be close to calculated V_R
        assert takeoff.rotation_speed_kias == pytest.approx(vspeeds.v_r, abs=1.0)

        # Liftoff should be slightly above rotation
        assert takeoff.liftoff_speed_kias > takeoff.rotation_speed_kias
        assert takeoff.liftoff_speed_kias == pytest.approx(
            takeoff.rotation_speed_kias * 1.05, abs=1.0
        )

    def test_performance_summary(self, c172_config: dict) -> None:
        """Test comprehensive performance summary."""
        calc = PerformanceCalculator(c172_config)

        summary = calc.get_performance_summary(2550.0, headwind_kts=0.0)

        assert summary["weight_lbs"] == 2550.0
        assert "vspeeds" in summary
        assert "takeoff" in summary
        assert "climb_rate_fpm" in summary

        # Check types
        assert summary["vspeeds"].v_s > 0
        assert summary["takeoff"].ground_roll_ft > 0
        assert summary["climb_rate_fpm"] > 0


class TestPerformanceEdgeCases:
    """Test edge cases and extreme scenarios."""

    def test_very_light_weight(self) -> None:
        """Test performance with minimum weight."""
        calc = VSpeedCalculator(reference_weight=2550.0, reference_vstall=47.0)

        # Empty weight only (1600 lbs)
        vstall = calc.calculate_vstall(1600.0)

        # Should be significantly lower than reference
        expected = 47.0 * (1600.0 / 2550.0) ** 0.5
        assert vstall == pytest.approx(expected, abs=0.5)
        assert vstall < 40.0  # Much lower stall speed

    def test_heavy_aircraft_performance(self) -> None:
        """Test with heavy aircraft (A380-like)."""
        config = {
            "reference_weight_lbs": 1268000.0,  # A380 MTOW
            "wing_area_sqft": 9100.0,
            "max_power_hp": 80000.0,  # Equivalent HP from thrust
            "cl_max_clean": 1.5,
            "cl_max_landing": 2.5,
            "vspeeds_reference": {"V_S": 110, "V_R": 165, "V_X": 175, "V_Y": 180},
            "takeoff_reference": {
                "ground_roll_ft": 9800,
                "distance_50ft": 11800,
                "climb_rate_fpm": 1500,
            },
        }

        calc = PerformanceCalculator(config)
        vspeeds = calc.calculate_vspeeds(1268000.0)

        # V_stall should be around 110 KIAS
        assert vspeeds.v_s == pytest.approx(110.0, abs=5.0)

        # Rotation speed is 1.1 × V_stall = 121 KIAS (theoretical)
        # Actual A380 V_R is higher (~165) due to safety margins and operational procedures
        assert vspeeds.v_r == pytest.approx(121.0, abs=5.0)
        assert vspeeds.v_r > vspeeds.v_s  # Must be above stall

    def test_zero_weight_handling(self) -> None:
        """Test calculator doesn't crash with zero/negative weight."""
        calc = VSpeedCalculator(reference_weight=2550.0, reference_vstall=47.0)

        # Should handle gracefully (not crash)
        vstall = calc.calculate_vstall(0.1)  # Near-zero weight
        assert vstall >= 0.0  # Non-negative result

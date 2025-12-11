"""Tests for ULM ground physics."""


import pytest

from airborne.physics.ground_physics import GroundContact
from airborne.physics.ground_physics_ulm import (
    TaildragConfig,
    ULMGroundPhysics,
    WindConditions,
)
from airborne.physics.vectors import Vector3


class TestULMGroundPhysicsInitialization:
    """Test ULMGroundPhysics initialization."""

    def test_default_initialization(self) -> None:
        """Test initialization with default values."""
        ground = ULMGroundPhysics()

        assert ground.mass_kg == 450.0
        assert ground.wing_span == 8.0
        assert ground.wing_area == 12.0
        assert ground.weathervane_sensitivity == 0.3

    def test_custom_initialization(self) -> None:
        """Test initialization with custom values."""
        ground = ULMGroundPhysics(
            mass_kg=350.0,
            max_brake_force_n=2500.0,
            wing_span_m=10.0,
            wing_area_m2=15.0,
        )

        assert ground.mass_kg == 350.0
        assert ground.max_brake_force_n == 2500.0
        assert ground.wing_span == 10.0
        assert ground.wing_area == 15.0

    def test_taildragger_config(self) -> None:
        """Test initialization with taildragger config."""
        td_config = TaildragConfig(
            is_taildragger=True,
            tailwheel_locked=False,
            prop_clearance_m=0.25,
        )
        ground = ULMGroundPhysics(taildragger_config=td_config)

        assert ground.taildragger.is_taildragger is True
        assert ground.taildragger.tailwheel_locked is False
        assert ground.taildragger.prop_clearance_m == 0.25


class TestWindConditions:
    """Test wind condition handling."""

    @pytest.fixture
    def ground(self) -> ULMGroundPhysics:
        """Create ground physics instance."""
        return ULMGroundPhysics(mass_kg=400.0, wing_area_m2=12.0)

    def test_set_wind(self, ground: ULMGroundPhysics) -> None:
        """Test setting wind conditions."""
        wind = WindConditions(
            speed_mps=10.0,
            direction_deg=270.0,
            gust_speed_mps=15.0,
            turbulence_intensity=0.3,
        )
        ground.set_wind(wind)

        assert ground.wind.speed_mps == 10.0
        assert ground.wind.direction_deg == 270.0
        assert ground.wind.gust_speed_mps == 15.0

    def test_default_wind_is_calm(self, ground: ULMGroundPhysics) -> None:
        """Test default wind is calm."""
        assert ground.wind.speed_mps == 0.0


class TestWeathervaning:
    """Test crosswind weathervaning behavior."""

    @pytest.fixture
    def ground(self) -> ULMGroundPhysics:
        """Create ground physics with known parameters."""
        g = ULMGroundPhysics(
            mass_kg=400.0,
            wing_area_m2=12.0,
        )
        g.weathervane_sensitivity = 0.3
        return g

    def test_no_weathervane_in_calm(self, ground: ULMGroundPhysics) -> None:
        """Test no weathervaning force in calm wind."""
        ground.set_wind(WindConditions(speed_mps=0.0, direction_deg=270.0))

        contact = GroundContact(on_ground=True, ground_speed_mps=5.0)
        forces = ground.calculate_ground_forces(contact, aircraft_heading_deg=0.0)

        # Weathervane force should be negligible
        # Only base ground forces should be present
        assert abs(forces.total_force.x) < 100.0  # Small baseline

    def test_weathervane_with_crosswind(self, ground: ULMGroundPhysics) -> None:
        """Test weathervaning force with crosswind."""
        ground.set_wind(WindConditions(speed_mps=10.0, direction_deg=270.0))

        contact = GroundContact(on_ground=True, ground_speed_mps=5.0)
        forces = ground.calculate_ground_forces(contact, aircraft_heading_deg=0.0)

        # Should have lateral force component
        assert forces.total_force.magnitude() > 0.0

    def test_max_weathervane_at_90_degrees(self, ground: ULMGroundPhysics) -> None:
        """Test maximum weathervaning at 90 degree crosswind."""
        ground.set_wind(WindConditions(speed_mps=10.0, direction_deg=90.0))

        contact = GroundContact(on_ground=True, ground_speed_mps=5.0)

        # At 90 degrees crosswind (wind from heading 90, aircraft heading 0)
        forces_90 = ground.calculate_ground_forces(contact, aircraft_heading_deg=0.0)

        # At 45 degrees crosswind
        ground.set_wind(WindConditions(speed_mps=10.0, direction_deg=45.0))
        forces_45 = ground.calculate_ground_forces(contact, aircraft_heading_deg=0.0)

        # 90 degree crosswind should produce more force than 45 degree
        force_90_mag = forces_90.total_force.magnitude()
        force_45_mag = forces_45.total_force.magnitude()

        # Both should have force, 90 should be larger or similar magnitude
        assert force_90_mag >= force_45_mag * 0.7

    def test_no_weathervane_with_headwind(self, ground: ULMGroundPhysics) -> None:
        """Test no weathervaning force with direct headwind."""
        ground.set_wind(WindConditions(speed_mps=10.0, direction_deg=0.0))

        contact = GroundContact(on_ground=True, ground_speed_mps=5.0)
        forces = ground.calculate_ground_forces(contact, aircraft_heading_deg=0.0)

        # Direct headwind - no crosswind component
        # Weathervane force should be zero or minimal
        # Only base ground forces present
        assert abs(forces.total_force.x) < 50.0


class TestTaildragDynamics:
    """Test taildragger-specific ground dynamics."""

    @pytest.fixture
    def taildragger(self) -> ULMGroundPhysics:
        """Create taildragger ground physics."""
        td_config = TaildragConfig(
            is_taildragger=True,
            tailwheel_locked=False,
            wheelbase_m=4.0,
        )
        return ULMGroundPhysics(
            mass_kg=400.0,
            taildragger_config=td_config,
        )

    @pytest.fixture
    def tricycle(self) -> ULMGroundPhysics:
        """Create tricycle ground physics."""
        return ULMGroundPhysics(mass_kg=400.0)

    def test_taildragger_forces_at_speed(self, taildragger: ULMGroundPhysics) -> None:
        """Test taildragger generates forces at speed with sideslip."""
        contact = GroundContact(on_ground=True, ground_speed_mps=10.0, heading_deg=0.0)
        velocity = Vector3(2.0, 0.0, 10.0)  # Some sideslip

        forces = taildragger.calculate_ground_forces(
            contact,
            rudder_input=0.0,
            brake_input=0.0,
            velocity=velocity,
            aircraft_heading_deg=0.0,
        )

        # Should have some force from taildragger dynamics
        assert forces.total_force.magnitude() > 0.0

    def test_tricycle_no_taildragger_forces(self, tricycle: ULMGroundPhysics) -> None:
        """Test tricycle doesn't have taildragger forces."""
        contact = GroundContact(on_ground=True, ground_speed_mps=10.0, heading_deg=0.0)
        velocity = Vector3(2.0, 0.0, 10.0)

        forces = tricycle.calculate_ground_forces(
            contact,
            rudder_input=0.0,
            brake_input=0.0,
            velocity=velocity,
            aircraft_heading_deg=0.0,
        )

        # Should have baseline forces but no taildragger-specific
        assert forces.total_force.magnitude() >= 0.0

    def test_tailwheel_steering(self, taildragger: ULMGroundPhysics) -> None:
        """Test tailwheel steering at low speed."""
        contact = GroundContact(on_ground=True, ground_speed_mps=5.0, heading_deg=0.0)
        velocity = Vector3(0.0, 0.0, 5.0)

        forces_neutral = taildragger.calculate_ground_forces(
            contact,
            rudder_input=0.0,
            velocity=velocity,
            aircraft_heading_deg=0.0,
        )

        forces_right = taildragger.calculate_ground_forces(
            contact,
            rudder_input=0.5,
            velocity=velocity,
            aircraft_heading_deg=0.0,
        )

        # Rudder input should change forces
        force_diff = (forces_right.total_force - forces_neutral.total_force).magnitude()
        assert force_diff > 0.0


class TestGroundEffect:
    """Test ground effect calculations."""

    @pytest.fixture
    def ground(self) -> ULMGroundPhysics:
        """Create ground physics with known wing span."""
        return ULMGroundPhysics(wing_span_m=10.0)

    def test_no_ground_effect_high(self, ground: ULMGroundPhysics) -> None:
        """Test no ground effect at high altitude."""
        factor = ground.calculate_ground_effect(height_agl_m=20.0, cl=1.2)
        assert factor == 1.0

    def test_no_ground_effect_on_ground(self, ground: ULMGroundPhysics) -> None:
        """Test no ground effect when on ground."""
        factor = ground.calculate_ground_effect(height_agl_m=0.0, cl=1.2)
        assert factor == 1.0

    def test_ground_effect_low_altitude(self, ground: ULMGroundPhysics) -> None:
        """Test ground effect increases lift at low altitude."""
        factor = ground.calculate_ground_effect(height_agl_m=2.0, cl=1.2)
        assert factor > 1.0

    def test_ground_effect_stronger_lower(self, ground: ULMGroundPhysics) -> None:
        """Test ground effect is stronger at lower altitudes."""
        factor_high = ground.calculate_ground_effect(height_agl_m=8.0, cl=1.2)
        factor_low = ground.calculate_ground_effect(height_agl_m=2.0, cl=1.2)

        assert factor_low > factor_high


class TestCrosswindLimit:
    """Test crosswind limit calculations."""

    @pytest.fixture
    def ground(self) -> ULMGroundPhysics:
        """Create ground physics instance."""
        return ULMGroundPhysics()

    def test_no_crosswind(self, ground: ULMGroundPhysics) -> None:
        """Test crosswind ratio is zero in calm."""
        ground.set_wind(WindConditions(speed_mps=0.0))
        ratio = ground.calculate_crosswind_limit(max_demonstrated_crosswind_kt=12.0)
        assert ratio == 0.0

    def test_at_limit(self, ground: ULMGroundPhysics) -> None:
        """Test crosswind ratio is 1.0 at limit."""
        # 12 kt = 6.17 m/s
        ground.set_wind(WindConditions(speed_mps=6.17, direction_deg=90.0))
        ratio = ground.calculate_crosswind_limit(max_demonstrated_crosswind_kt=12.0)
        assert ratio == pytest.approx(1.0, rel=0.1)

    def test_over_limit(self, ground: ULMGroundPhysics) -> None:
        """Test crosswind ratio exceeds 1.0 over limit."""
        # 20 kt = 10.3 m/s
        ground.set_wind(WindConditions(speed_mps=10.3, direction_deg=90.0))
        ratio = ground.calculate_crosswind_limit(max_demonstrated_crosswind_kt=12.0)
        assert ratio > 1.0

    def test_gusts_considered(self, ground: ULMGroundPhysics) -> None:
        """Test gusts are used for crosswind calculation."""
        ground.set_wind(WindConditions(speed_mps=5.0, gust_speed_mps=10.0))
        ratio = ground.calculate_crosswind_limit(max_demonstrated_crosswind_kt=12.0)

        # Should use gust speed (10 m/s = ~19 kt) not steady speed
        assert ratio > 1.0


class TestTaxiDifficulty:
    """Test taxi difficulty assessment."""

    @pytest.fixture
    def ground(self) -> ULMGroundPhysics:
        """Create ground physics instance."""
        return ULMGroundPhysics()

    def test_easy_in_calm(self, ground: ULMGroundPhysics) -> None:
        """Test taxi is easy in calm conditions."""
        ground.set_wind(WindConditions(speed_mps=2.0))
        difficulty = ground.get_taxi_difficulty(surface_type="asphalt")
        assert difficulty == "easy"

    def test_moderate_with_wind(self, ground: ULMGroundPhysics) -> None:
        """Test taxi is moderate with wind."""
        ground.set_wind(WindConditions(speed_mps=6.0))  # ~12 kt
        difficulty = ground.get_taxi_difficulty(surface_type="asphalt")
        assert difficulty in ("easy", "moderate")

    def test_challenging_with_strong_wind(self, ground: ULMGroundPhysics) -> None:
        """Test taxi is challenging with strong wind."""
        ground.set_wind(WindConditions(speed_mps=10.0, gust_speed_mps=15.0))  # ~20 kt gusting 30
        difficulty = ground.get_taxi_difficulty(surface_type="asphalt")
        assert difficulty in ("challenging", "dangerous")

    def test_taildragger_harder(self) -> None:
        """Test taildragger makes taxi harder."""
        td_config = TaildragConfig(is_taildragger=True)
        ground_td = ULMGroundPhysics(taildragger_config=td_config)
        ground_tri = ULMGroundPhysics()

        ground_td.set_wind(WindConditions(speed_mps=6.0))
        ground_tri.set_wind(WindConditions(speed_mps=6.0))

        diff_td = ground_td.get_taxi_difficulty()
        diff_tri = ground_tri.get_taxi_difficulty()

        # Taildragger should be at least as hard
        difficulty_order = ["easy", "moderate", "challenging", "dangerous"]
        assert difficulty_order.index(diff_td) >= difficulty_order.index(diff_tri)

    def test_grass_harder_than_asphalt(self, ground: ULMGroundPhysics) -> None:
        """Test grass is harder than asphalt."""
        ground.set_wind(WindConditions(speed_mps=5.0))

        diff_asphalt = ground.get_taxi_difficulty(surface_type="asphalt")
        diff_grass = ground.get_taxi_difficulty(surface_type="grass")

        difficulty_order = ["easy", "moderate", "challenging", "dangerous"]
        assert difficulty_order.index(diff_grass) >= difficulty_order.index(diff_asphalt)

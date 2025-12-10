"""Tests for the damage model and crash report system."""

import pytest
from pathlib import Path
import tempfile

from airborne.plugins.safety.damage_model import (
    CrashCause,
    CrashReport,
    DamageEvent,
    DamageModel,
    DamageType,
    FlightState,
)


class TestDamageModel:
    """Tests for DamageModel class."""

    def test_initialization_with_defaults(self):
        """Test damage model initializes with default values."""
        model = DamageModel()

        assert model.total_damage == 0.0
        assert not model.is_crashed
        assert all(level == 0.0 for level in model.damage.values())

    def test_initialization_with_config(self):
        """Test damage model uses aircraft config for limits."""
        config = {
            "name": "Test Aircraft",
            "landing_limits": {
                "max_sink_rate_fpm": 500,
                "hard_landing_fpm": 300,
                "max_crosswind_kts": 10,
            },
            "surface_compatibility": {
                "allowed_surfaces": ["asphalt", "concrete"],
                "restricted_surfaces": ["grass"],
                "prohibited_surfaces": ["water", "sand"],
            },
        }

        model = DamageModel(config)

        assert model.max_sink_rate_fpm == 500
        assert model.hard_landing_fpm == 300
        assert model.max_crosswind_kts == 10
        assert "asphalt" in model.allowed_surfaces
        assert "water" in model.prohibited_surfaces

    def test_apply_damage(self):
        """Test applying damage to aircraft components."""
        model = DamageModel()

        model.apply_damage(DamageType.GEAR, 0.3, "Test damage", sim_time=10.0)

        assert model.damage[DamageType.GEAR] == 0.3
        assert len(model.events) == 1
        assert model.events[0].severity == 0.3
        assert model.events[0].description == "Test damage"

    def test_damage_accumulates(self):
        """Test that damage accumulates on same component."""
        model = DamageModel()

        model.apply_damage(DamageType.GEAR, 0.3, "First damage")
        model.apply_damage(DamageType.GEAR, 0.3, "Second damage")

        assert model.damage[DamageType.GEAR] == 0.6
        assert len(model.events) == 2

    def test_damage_caps_at_one(self):
        """Test that damage caps at 1.0 per component."""
        model = DamageModel()

        model.apply_damage(DamageType.GEAR, 0.8, "Heavy damage")
        model.apply_damage(DamageType.GEAR, 0.5, "More damage")

        assert model.damage[DamageType.GEAR] == 1.0

    def test_hard_landing_no_damage(self):
        """Test landing within limits causes no damage."""
        model = DamageModel()

        result = model.check_hard_landing(300)  # Below threshold

        assert not result
        assert model.damage[DamageType.GEAR] == 0.0

    def test_hard_landing_moderate(self):
        """Test hard landing causes gear damage."""
        config = {
            "landing_limits": {
                "max_sink_rate_fpm": 600,
                "hard_landing_fpm": 400,
            }
        }
        model = DamageModel(config)

        result = model.check_hard_landing(500)  # Between thresholds

        assert result
        assert model.damage[DamageType.GEAR] > 0.0
        assert not model.is_crashed

    def test_hard_landing_crash(self):
        """Test excessive sink rate causes crash."""
        config = {
            "landing_limits": {
                "max_sink_rate_fpm": 600,
                "hard_landing_fpm": 400,
            }
        }
        model = DamageModel(config)

        model.check_hard_landing(700)  # Above max

        assert model.is_crashed
        assert model.damage[DamageType.GEAR] == 1.0

    def test_prohibited_surface_crash(self):
        """Test landing on prohibited surface causes crash."""
        config = {
            "surface_compatibility": {
                "prohibited_surfaces": ["water"],
            }
        }
        model = DamageModel(config)

        result = model.check_surface_compatibility("water", 0.0)

        assert result
        assert model.is_crashed

    def test_restricted_surface_damage(self):
        """Test landing on restricted surface causes damage but not crash."""
        config = {
            "surface_compatibility": {
                "allowed_surfaces": ["asphalt"],
                "restricted_surfaces": ["grass"],
                "prohibited_surfaces": ["water"],
            }
        }
        model = DamageModel(config)

        result = model.check_surface_compatibility("grass", 0.0)

        assert result
        assert model.damage[DamageType.GEAR] > 0.0
        assert not model.is_crashed

    def test_crosswind_within_limits(self):
        """Test crosswind within limits causes no damage."""
        config = {"landing_limits": {"max_crosswind_kts": 15}}
        model = DamageModel(config)

        result = model.check_crosswind(10.0, 0.0)

        assert not result
        assert model.damage[DamageType.GEAR] == 0.0

    def test_crosswind_moderate_excess(self):
        """Test moderate crosswind excess causes damage."""
        config = {"landing_limits": {"max_crosswind_kts": 15}}
        model = DamageModel(config)

        result = model.check_crosswind(20.0, 0.0)

        assert result
        assert model.damage[DamageType.GEAR] > 0.0
        assert not model.is_crashed

    def test_crosswind_severe_crash(self):
        """Test severe crosswind causes crash."""
        config = {"landing_limits": {"max_crosswind_kts": 15}}
        model = DamageModel(config)

        result = model.check_crosswind(30.0, 0.0)  # Way over limit

        assert result
        assert model.is_crashed

    def test_terrain_collision(self):
        """Test terrain collision causes crash."""
        model = DamageModel()

        result = model.check_terrain_collision(
            agl_altitude_m=-10,  # Below terrain
            vertical_speed_mps=-5.0,
            sim_time=0.0,
        )

        assert result
        assert model.is_crashed
        assert model.damage[DamageType.AIRFRAME] == 1.0

    def test_reset(self):
        """Test reset clears all damage."""
        model = DamageModel()
        model.apply_damage(DamageType.GEAR, 0.5, "Test")
        model._crashed = True

        model.reset()

        assert model.total_damage == 0.0
        assert not model.is_crashed
        assert len(model.events) == 0


class TestCrashReport:
    """Tests for CrashReport class."""

    def create_sample_flight_state(self) -> FlightState:
        """Create a sample flight state for testing."""
        return FlightState(
            altitude_msl_ft=100.0,
            altitude_agl_ft=50.0,
            airspeed_kts=65.0,
            groundspeed_kts=60.0,
            vertical_speed_fpm=-800.0,
            heading_deg=270.0,
            pitch_deg=-3.0,
            roll_deg=5.0,
            latitude=37.615223,
            longitude=-122.389977,
            on_ground=True,
            flaps_position=1.0,
            throttle_position=0.0,
            fuel_remaining_gal=20.0,
            weight_lbs=2400.0,
            wind_speed_kts=15.0,
            wind_direction_deg=300.0,
            crosswind_component_kts=12.0,
        )

    def test_to_markdown(self):
        """Test markdown report generation."""
        from datetime import datetime

        flight_state = self.create_sample_flight_state()

        report = CrashReport(
            report_id="test-123",
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            aircraft_type="Cessna 172",
            aircraft_callsign="N12345",
            latitude=37.615223,
            longitude=-122.389977,
            airport_icao="KSFO",
            runway_id="28R",
            primary_cause=CrashCause.HARD_LANDING,
            cause_description="Landing gear collapsed due to excessive sink rate.",
            flight_state=flight_state,
            damage_events=[
                DamageEvent(
                    timestamp=100.0,
                    damage_type=DamageType.GEAR,
                    severity=1.0,
                    description="Gear collapse",
                )
            ],
            contributing_factors=["Excessive sink rate"],
            recommendations=["Practice flare timing"],
        )

        markdown = report.to_markdown()

        assert "# Crash Report" in markdown
        assert "Cessna 172" in markdown
        assert "Hard Landing" in markdown
        assert "KSFO" in markdown
        assert "28R" in markdown
        assert "Excessive sink rate" in markdown

    def test_save_to_file(self):
        """Test saving report to file."""
        from datetime import datetime

        flight_state = self.create_sample_flight_state()

        report = CrashReport(
            report_id="test-456",
            timestamp=datetime.now(),
            aircraft_type="Test Aircraft",
            aircraft_callsign="TEST",
            latitude=37.0,
            longitude=-122.0,
            airport_icao=None,
            runway_id=None,
            primary_cause=CrashCause.TERRAIN_COLLISION,
            cause_description="Test crash",
            flight_state=flight_state,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = report.save_to_file(tmpdir)

            assert filepath.exists()
            assert filepath.suffix == ".md"

            # Check JSON also created
            json_path = filepath.with_suffix(".json")
            assert json_path.exists()


class TestDamageModelCrashReport:
    """Integration tests for damage model crash report generation."""

    def test_generate_crash_report(self):
        """Test generating crash report from damage model."""
        config = {
            "name": "Cessna 172",
            "landing_limits": {
                "max_sink_rate_fpm": 600,
                "hard_landing_fpm": 400,
            },
        }
        model = DamageModel(config)
        model.callsign = "N12345"

        # Trigger crash
        model.check_hard_landing(700, sim_time=50.0)

        # Create flight state
        flight_state = FlightState(
            altitude_msl_ft=0.0,
            altitude_agl_ft=0.0,
            airspeed_kts=60.0,
            groundspeed_kts=55.0,
            vertical_speed_fpm=-700.0,
            heading_deg=90.0,
            pitch_deg=-5.0,
            roll_deg=0.0,
            latitude=37.0,
            longitude=-122.0,
            on_ground=True,
            flaps_position=1.0,
            throttle_position=0.0,
            fuel_remaining_gal=25.0,
            weight_lbs=2300.0,
        )

        report = model.generate_crash_report(flight_state, "KPAO", "31")

        assert report.primary_cause == CrashCause.HARD_LANDING
        assert report.aircraft_type == "Cessna 172"
        assert report.aircraft_callsign == "N12345"
        assert len(report.damage_events) > 0
        assert report.airport_icao == "KPAO"
        assert report.runway_id == "31"

    def test_audio_crash_summary(self):
        """Test audio crash summary generation."""
        model = DamageModel()
        model.check_hard_landing(1000)  # Crash

        summary = model.get_audio_crash_summary()

        assert "Crash" in summary
        assert "hard landing" in summary.lower()

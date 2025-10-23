"""Tests for weight and balance system."""

import pytest

from airborne.systems.weight_balance import LoadStation, WeightBalanceSystem


class TestLoadStation:
    """Test LoadStation class."""

    def test_initialize_station(self) -> None:
        """Test station initialization."""
        station = LoadStation(
            name="seat_pilot",
            arm=85.0,
            max_weight=200.0,
            current_weight=180.0,
            station_type="seat",
        )

        assert station.name == "seat_pilot"
        assert station.arm == 85.0
        assert station.max_weight == 200.0
        assert station.current_weight == 180.0
        assert station.station_type == "seat"

    def test_calculate_moment(self) -> None:
        """Test moment calculation."""
        station = LoadStation("pilot", 85.0, 200.0, 180.0, "seat")

        moment = station.calculate_moment()
        assert moment == pytest.approx(15300.0)  # 180 × 85

    def test_is_overweight(self) -> None:
        """Test overweight detection."""
        station = LoadStation("pilot", 85.0, 200.0, 180.0, "seat")
        assert not station.is_overweight()

        station.current_weight = 250.0
        assert station.is_overweight()

    def test_set_weight(self) -> None:
        """Test setting weight."""
        station = LoadStation("pilot", 85.0, 200.0, 0.0, "seat")

        # Valid weight
        assert station.set_weight(180.0)
        assert station.current_weight == 180.0

        # Negative weight (invalid)
        assert not station.set_weight(-10.0)
        assert station.current_weight == 180.0  # Unchanged

        # Over max (clamped)
        assert station.set_weight(250.0)
        assert station.current_weight == 200.0  # Clamped to max

    def test_add_weight(self) -> None:
        """Test adding/removing weight."""
        station = LoadStation("cargo", 142.0, 120.0, 50.0, "cargo")

        # Add weight
        assert station.add_weight(30.0)
        assert station.current_weight == 80.0

        # Remove weight
        assert station.add_weight(-20.0)
        assert station.current_weight == 60.0

        # Over max (clamped)
        assert station.add_weight(100.0)
        assert station.current_weight == 120.0  # Clamped

    def test_get_remaining_capacity(self) -> None:
        """Test remaining capacity calculation."""
        station = LoadStation("cargo", 142.0, 120.0, 50.0, "cargo")

        assert station.get_remaining_capacity() == pytest.approx(70.0)


class TestWeightBalanceSystem:
    """Test WeightBalanceSystem class."""

    @pytest.fixture
    def c172_config(self) -> dict:
        """Cessna 172 W&B configuration."""
        return {
            "empty_weight": 1600.0,
            "empty_moment": 136000.0,  # 1600 × 85 = CG at 85"
            "max_gross_weight": 2550.0,
            "cg_limits": {"forward": 82.9, "aft": 95.5},
            "stations": {
                "fuel": [
                    {
                        "name": "fuel_main",
                        "arm": 95.0,
                        "max_weight": 312.0,
                        "initial_weight": 312.0,
                    }
                ],
                "seats": [
                    {
                        "name": "seat_pilot",
                        "arm": 85.0,
                        "max_weight": 200.0,
                        "initial_weight": 200.0,
                    },
                    {
                        "name": "seat_copilot",
                        "arm": 85.0,
                        "max_weight": 200.0,
                        "initial_weight": 0.0,
                    },
                ],
                "cargo": [
                    {
                        "name": "cargo_bay",
                        "arm": 142.0,
                        "max_weight": 120.0,
                        "initial_weight": 0.0,
                    }
                ],
            },
        }

    def test_initialize_system(self, c172_config: dict) -> None:
        """Test system initialization."""
        wb = WeightBalanceSystem(c172_config)

        assert wb.empty_weight == 1600.0
        assert wb.empty_moment == 136000.0
        assert wb.max_gross_weight == 2550.0
        assert wb.cg_forward_limit == 82.9
        assert wb.cg_aft_limit == 95.5

        # Check stations loaded
        assert "fuel_main" in wb.stations
        assert "seat_pilot" in wb.stations
        assert "seat_copilot" in wb.stations
        assert "cargo_bay" in wb.stations

    def test_calculate_total_weight(self, c172_config: dict) -> None:
        """Test total weight calculation."""
        wb = WeightBalanceSystem(c172_config)

        # Initial: 1600 (empty) + 312 (fuel) + 200 (pilot) = 2112 lbs
        total = wb.calculate_total_weight()
        assert total == pytest.approx(2112.0, rel=0.01)

    def test_calculate_cg(self, c172_config: dict) -> None:
        """Test CG calculation."""
        wb = WeightBalanceSystem(c172_config)

        # Empty: 1600 lbs @ 85" = 136000 lb-in
        # Fuel: 312 lbs @ 95" = 29640 lb-in
        # Pilot: 200 lbs @ 85" = 17000 lb-in
        # Total moment: 136000 + 29640 + 17000 = 182640 lb-in
        # Total weight: 2112 lbs
        # CG: 182640 / 2112 = 86.5"

        cg = wb.calculate_cg()
        assert cg == pytest.approx(86.5, abs=0.1)

    def test_cg_shifts_with_fuel_burn(self, c172_config: dict) -> None:
        """Test CG moves forward as fuel burns (fuel is aft)."""
        wb = WeightBalanceSystem(c172_config)

        cg_full = wb.calculate_cg()

        # Burn half fuel (156 lbs)
        wb.update_station_weight("fuel_main", 156.0)
        cg_half = wb.calculate_cg()

        # Burn all fuel
        wb.update_station_weight("fuel_main", 0.0)
        cg_empty = wb.calculate_cg()

        # CG should move forward as fuel (aft of CG) decreases
        assert cg_full > cg_half > cg_empty

    def test_is_within_limits_normal(self, c172_config: dict) -> None:
        """Test limits check for normal loading."""
        wb = WeightBalanceSystem(c172_config)

        within_limits, msg = wb.is_within_limits()
        assert within_limits
        assert msg == "Within limits"

    def test_is_within_limits_overweight(self, c172_config: dict) -> None:
        """Test limits check for overweight condition."""
        wb = WeightBalanceSystem(c172_config)

        # Add excessive weight to exceed max gross weight
        wb.update_station_weight("seat_copilot", 200.0)
        wb.update_station_weight("cargo_bay", 120.0)

        # Set pilot weight to 400 lbs to exceed limits
        wb.stations["seat_pilot"].current_weight = 400.0

        # Total now: 1600 + 312 + 400 + 200 + 120 = 2632 lbs (exceeds 2550 max)
        within_limits, msg = wb.is_within_limits()
        assert not within_limits
        assert "Overweight" in msg

    def test_is_within_limits_cg_aft(self, c172_config: dict) -> None:
        """Test CG too far aft."""
        wb = WeightBalanceSystem(c172_config)

        # Put heavy weight in cargo bay (far aft)
        wb.update_station_weight("cargo_bay", 120.0)
        wb.update_station_weight("seat_pilot", 0.0)  # Remove pilot

        # This moves CG aft
        within_limits, msg = wb.is_within_limits()

        # Check if CG exceeded limits
        cg = wb.calculate_cg()
        if cg > wb.cg_aft_limit:
            assert not within_limits
            assert "too far aft" in msg

    def test_update_station_weight(self, c172_config: dict) -> None:
        """Test updating station weight."""
        wb = WeightBalanceSystem(c172_config)

        # Update copilot weight
        assert wb.update_station_weight("seat_copilot", 180.0)

        station = wb.get_station("seat_copilot")
        assert station is not None
        assert station.current_weight == 180.0

        # Invalid station
        assert not wb.update_station_weight("nonexistent", 100.0)

    def test_get_fuel_weight(self, c172_config: dict) -> None:
        """Test fuel weight calculation."""
        wb = WeightBalanceSystem(c172_config)

        fuel_weight = wb.get_fuel_weight()
        assert fuel_weight == pytest.approx(312.0)

        # Burn half fuel
        wb.update_station_weight("fuel_main", 156.0)
        fuel_weight = wb.get_fuel_weight()
        assert fuel_weight == pytest.approx(156.0)

    def test_get_occupant_weight(self, c172_config: dict) -> None:
        """Test occupant weight calculation."""
        wb = WeightBalanceSystem(c172_config)

        # Initial: only pilot (200 lbs)
        occupant_weight = wb.get_occupant_weight()
        assert occupant_weight == pytest.approx(200.0)

        # Add copilot
        wb.update_station_weight("seat_copilot", 180.0)
        occupant_weight = wb.get_occupant_weight()
        assert occupant_weight == pytest.approx(380.0)

    def test_get_cargo_weight(self, c172_config: dict) -> None:
        """Test cargo weight calculation."""
        wb = WeightBalanceSystem(c172_config)

        # Initial: no cargo
        cargo_weight = wb.get_cargo_weight()
        assert cargo_weight == pytest.approx(0.0)

        # Add cargo
        wb.update_station_weight("cargo_bay", 50.0)
        cargo_weight = wb.get_cargo_weight()
        assert cargo_weight == pytest.approx(50.0)

    def test_get_weight_breakdown(self, c172_config: dict) -> None:
        """Test detailed weight breakdown."""
        wb = WeightBalanceSystem(c172_config)

        breakdown = wb.get_weight_breakdown()

        assert breakdown["empty"] == 1600.0
        assert breakdown["fuel"] == pytest.approx(312.0)
        assert breakdown["occupants"] == pytest.approx(200.0)
        assert breakdown["cargo"] == pytest.approx(0.0)
        assert breakdown["total"] == pytest.approx(2112.0)
        assert "cg" in breakdown


class TestWeightBalanceEdgeCases:
    """Test edge cases and extreme scenarios."""

    def test_empty_aircraft(self) -> None:
        """Test aircraft with no loading."""
        config = {
            "empty_weight": 1600.0,
            "empty_moment": 136000.0,
            "max_gross_weight": 2550.0,
            "cg_limits": {"forward": 82.9, "aft": 95.5},
            "stations": {},
        }

        wb = WeightBalanceSystem(config)

        # Should calculate based on empty weight only
        total = wb.calculate_total_weight()
        assert total == 1600.0

        cg = wb.calculate_cg()
        assert cg == pytest.approx(85.0)  # 136000 / 1600

    def test_max_gross_weight_scenario(self) -> None:
        """Test at maximum gross weight."""
        config = {
            "empty_weight": 1600.0,
            "empty_moment": 136000.0,
            "max_gross_weight": 2550.0,
            "cg_limits": {"forward": 82.9, "aft": 95.5},
            "stations": {
                "fuel": [
                    {"name": "fuel", "arm": 95.0, "max_weight": 312.0, "initial_weight": 312.0}
                ],
                "seats": [
                    {"name": "pilot", "arm": 85.0, "max_weight": 200.0, "initial_weight": 200.0},
                    {"name": "copilot", "arm": 85.0, "max_weight": 200.0, "initial_weight": 200.0},
                    {"name": "rear1", "arm": 118.0, "max_weight": 200.0, "initial_weight": 120.0},
                    {"name": "rear2", "arm": 118.0, "max_weight": 200.0, "initial_weight": 120.0},
                ],
            },
        }

        wb = WeightBalanceSystem(config)

        # Total: 1600 + 312 + 200 + 200 + 120 + 120 = 2552 (over max)
        total = wb.calculate_total_weight()
        assert total > wb.max_gross_weight

        within_limits, msg = wb.is_within_limits()
        assert not within_limits
        assert "Overweight" in msg

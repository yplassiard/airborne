"""Tests for Cessna 172 system implementations."""

import pytest

from airborne.systems.electrical.simple_12v import Simple12VElectricalSystem
from airborne.systems.fuel.simple_gravity import SimpleGravityFuelSystem
from airborne.systems.fuel.base import FuelSelectorPosition
from airborne.systems.lighting.standard import StandardLightingSystem


class TestSimple12VElectricalSystem:
    """Test Cessna 172 12V electrical system."""

    def test_initialization(self):
        """Test electrical system can be initialized."""
        system = Simple12VElectricalSystem()
        assert system is not None
        assert system.battery_voltage == 12.6
        assert system.battery_current_ah == 35.0

    def test_battery_discharge(self):
        """Test battery discharges under load."""
        system = Simple12VElectricalSystem()
        system.initialize({
            "loads": {
                "nav_lights": {"amps": 1.5, "essential": False}
            }
        })

        # Turn on master switch and nav lights
        system.set_master_switch(True)
        system.set_load_enabled("nav_lights", True)

        initial_ah = system.battery_current_ah

        # Update for 1 second with no engine (no alternator)
        system.update(dt=1.0, engine_rpm=0.0)

        # Battery should have discharged
        assert system.battery_current_ah < initial_ah

    def test_alternator_charging(self):
        """Test alternator charges battery when engine running."""
        system = Simple12VElectricalSystem()
        system.initialize({
            "loads": {
                "nav_lights": {"amps": 1.5, "essential": False}
            }
        })

        # Discharge battery a bit first
        system.battery_current_ah = 30.0
        system._update_battery_voltage()

        # Turn on master switch and lights
        system.set_master_switch(True)
        system.set_load_enabled("nav_lights", True)

        initial_ah = system.battery_current_ah

        # Update with engine running at 2400 RPM
        system.update(dt=1.0, engine_rpm=2400.0)

        # Battery should be charging (alternator output > load)
        state = system.get_state()
        assert state.battery_current_amps > 0  # Positive = charging

    def test_starter_requires_voltage(self):
        """Test starter won't crank with low battery voltage."""
        system = Simple12VElectricalSystem()
        system.initialize({
            "loads": {
                "starter_motor": {"amps": 150.0, "essential": True}
            }
        })

        # Drain battery to critical level
        system.battery_current_ah = 2.0  # Very low
        system._update_battery_voltage()

        system.set_master_switch(True)

        # Try to draw starter current
        can_crank = system.can_draw_current(150.0)

        # Should fail - not enough voltage
        assert can_crank is False

    def test_battery_dead_state(self):
        """Test completely dead battery."""
        system = Simple12VElectricalSystem()
        system.initialize({})

        # Kill battery
        system.battery_current_ah = 0.0
        system._update_battery_voltage()

        system.set_master_switch(True)
        system.update(dt=0.016, engine_rpm=0.0)

        state = system.get_state()
        assert "BATTERY_DEAD" in state.failures
        assert state.battery_voltage == 0.0

    def test_alternator_failure(self):
        """Test alternator failure causes battery drain."""
        system = Simple12VElectricalSystem()
        system.initialize({
            "loads": {
                "avionics": {"amps": 10.0, "essential": False}
            }
        })

        system.set_master_switch(True)
        system.set_load_enabled("avionics", True)

        # Simulate alternator failure
        system.simulate_failure("alternator")

        # Update with engine running (but alternator failed)
        system.update(dt=1.0, engine_rpm=2400.0)

        state = system.get_state()
        assert "ALTERNATOR_FAILURE" in state.warnings
        assert state.battery_current_amps < 0  # Discharging


class TestSimpleGravityFuelSystem:
    """Test Cessna 172 gravity-feed fuel system."""

    def test_initialization(self):
        """Test fuel system can be initialized."""
        system = SimpleGravityFuelSystem()
        system.initialize({
            "tanks": {
                "left": {
                    "capacity_total": 28.0,
                    "capacity_usable": 26.0,
                    "fuel_type": "avgas_100ll",
                    "position": [-5.0, 0.0, -8.0]
                },
                "right": {
                    "capacity_total": 28.0,
                    "capacity_usable": 26.0,
                    "fuel_type": "avgas_100ll",
                    "position": [-5.0, 0.0, 8.0]
                }
            }
        })

        assert len(system.tanks) == 2
        assert "left" in system.tanks
        assert "right" in system.tanks

    def test_fuel_consumption(self):
        """Test fuel is consumed during flight."""
        system = SimpleGravityFuelSystem()
        system.initialize({
            "tanks": {
                "left": {
                    "capacity_total": 28.0,
                    "capacity_usable": 26.0,
                    "fuel_type": "avgas_100ll",
                    "position": [-5.0, 0.0, -8.0]
                },
                "right": {
                    "capacity_total": 28.0,
                    "capacity_usable": 26.0,
                    "fuel_type": "avgas_100ll",
                    "position": [-5.0, 0.0, 8.0]
                }
            }
        })

        system.set_selector_position(FuelSelectorPosition.BOTH)

        initial_fuel = system.tanks["left"].current_quantity + system.tanks["right"].current_quantity

        # Consume fuel at 8 GPH for 1 hour (should consume ~8 gallons)
        system.update(dt=3600.0, fuel_flow_gph=8.0)

        final_fuel = system.tanks["left"].current_quantity + system.tanks["right"].current_quantity

        # Should have consumed approximately 8 gallons
        consumed = initial_fuel - final_fuel
        assert 7.9 < consumed < 8.1

    def test_fuel_exhaustion(self):
        """Test engine dies when fuel exhausted."""
        system = SimpleGravityFuelSystem()
        system.initialize({
            "tanks": {
                "left": {
                    "capacity_total": 28.0,
                    "capacity_usable": 26.0,
                    "initial_quantity": 0.1,  # Almost empty
                    "fuel_type": "avgas_100ll",
                    "position": [-5.0, 0.0, -8.0]
                },
                "right": {
                    "capacity_total": 28.0,
                    "capacity_usable": 26.0,
                    "initial_quantity": 0.1,  # Almost empty
                    "fuel_type": "avgas_100ll",
                    "position": [-5.0, 0.0, 8.0]
                }
            }
        })

        system.set_selector_position(FuelSelectorPosition.BOTH)

        # Consume remaining fuel
        system.update(dt=360.0, fuel_flow_gph=10.0)  # 1 gallon in 6 minutes

        # Check state
        state = system.get_state()

        # Should have fuel exhausted failure
        assert "FUEL_EXHAUSTED" in state.failures
        assert system.get_available_fuel_flow() == 0.0

    def test_fuel_selector_off(self):
        """Test fuel selector OFF stops fuel flow."""
        system = SimpleGravityFuelSystem()
        system.initialize({
            "tanks": {
                "left": {
                    "capacity_total": 28.0,
                    "capacity_usable": 26.0,
                    "fuel_type": "avgas_100ll",
                    "position": [-5.0, 0.0, -8.0]
                }
            }
        })

        system.set_selector_position(FuelSelectorPosition.OFF)

        # No fuel should be available
        assert system.get_available_fuel_flow() == 0.0

        state = system.get_state()
        assert "FUEL_SELECTOR_OFF" in state.failures

    def test_fuel_imbalance_warning(self):
        """Test fuel imbalance warning."""
        system = SimpleGravityFuelSystem()
        system.initialize({
            "tanks": {
                "left": {
                    "capacity_total": 28.0,
                    "capacity_usable": 26.0,
                    "initial_quantity": 20.0,  # More fuel
                    "fuel_type": "avgas_100ll",
                    "position": [-5.0, 0.0, -8.0]
                },
                "right": {
                    "capacity_total": 28.0,
                    "capacity_usable": 26.0,
                    "initial_quantity": 10.0,  # Less fuel (10 gal difference)
                    "fuel_type": "avgas_100ll",
                    "position": [-5.0, 0.0, 8.0]
                }
            }
        })

        state = system.get_state()
        assert "FUEL_IMBALANCE" in state.warnings

    def test_refueling(self):
        """Test ground refueling operation."""
        system = SimpleGravityFuelSystem()
        system.initialize({
            "tanks": {
                "left": {
                    "capacity_total": 28.0,
                    "capacity_usable": 26.0,
                    "initial_quantity": 10.0,
                    "fuel_type": "avgas_100ll",
                    "position": [-5.0, 0.0, -8.0]
                }
            }
        })

        # Refuel 10 gallons
        success = system.refuel("left", 10.0)
        assert success is True
        assert system.tanks["left"].current_quantity == 20.0

        # Try to overfill (should fail)
        success = system.refuel("left", 20.0)  # Would exceed capacity
        assert success is False


class TestStandardLightingSystem:
    """Test standard lighting system."""

    def test_initialization(self):
        """Test lighting system can be initialized."""
        system = StandardLightingSystem()
        system.initialize({
            "lights": {
                "nav_lights": {"power_draw": 1.5},
                "beacon": {"power_draw": 2.0}
            }
        })

        assert len(system.lights) == 2
        assert "nav_lights" in system.lights

    def test_lights_require_voltage(self):
        """Test lights dim/fail with low voltage."""
        system = StandardLightingSystem()
        system.initialize({
            "lights": {
                "landing_light": {"power_draw": 8.0}
            }
        })

        system.set_light_enabled("landing_light", True)

        # Full voltage - full brightness
        system.update(dt=0.016, bus_voltage=14.0)
        state = system.get_light_state("landing_light")
        assert state.brightness == 1.0

        # Low voltage - dimmed
        system.update(dt=0.016, bus_voltage=11.0)
        state = system.get_light_state("landing_light")
        assert 0.0 < state.brightness < 1.0

        # Very low voltage - off
        system.update(dt=0.016, bus_voltage=9.0)
        state = system.get_light_state("landing_light")
        assert state.brightness == 0.0

    def test_power_consumption(self):
        """Test total power draw calculation."""
        system = StandardLightingSystem()
        system.initialize({
            "lights": {
                "nav_lights": {"power_draw": 1.5},
                "beacon": {"power_draw": 2.0},
                "landing_light": {"power_draw": 8.0}
            }
        })

        # Turn on all lights
        system.set_light_enabled("nav_lights", True)
        system.set_light_enabled("beacon", True)
        system.set_light_enabled("landing_light", True)

        total_draw = system.get_total_power_draw()
        assert total_draw == 11.5  # 1.5 + 2.0 + 8.0

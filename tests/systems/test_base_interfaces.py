"""Tests for base system interfaces.

These tests verify that the abstract base classes are properly defined
and can be subclassed correctly.
"""

import pytest

from airborne.systems.electrical.base import (
    BatteryType,
    ElectricalBus,
    ElectricalLoad,
    ElectricalState,
    IElectricalSystem,
    PowerSource,
)
from airborne.systems.engines.base import (
    EngineControls,
    EngineIgnitionType,
    EngineState,
    EngineType,
    IEngine,
)
from airborne.systems.fuel.base import (
    FuelSelectorPosition,
    FuelState,
    FuelTank,
    FuelType,
    IFuelSystem,
)


class TestElectricalBaseInterface:
    """Test electrical system base interface."""

    def test_electrical_load_creation(self):
        """Test ElectricalLoad dataclass creation."""
        load = ElectricalLoad(
            name="test_load", current_draw_amps=5.0, essential=True, enabled=False, min_voltage=11.0
        )
        assert load.name == "test_load"
        assert load.current_draw_amps == 5.0
        assert load.essential is True
        assert load.enabled is False
        assert load.min_voltage == 11.0

    def test_electrical_bus_creation(self):
        """Test ElectricalBus dataclass creation."""
        bus = ElectricalBus(
            name="main_bus",
            voltage_nominal=12.0,
            voltage_current=12.6,
            loads=[],
            power_sources=[PowerSource.BATTERY],
        )
        assert bus.name == "main_bus"
        assert bus.voltage_nominal == 12.0
        assert bus.voltage_current == 12.6
        assert len(bus.loads) == 0
        assert PowerSource.BATTERY in bus.power_sources

    def test_electrical_state_creation(self):
        """Test ElectricalState dataclass creation."""
        state = ElectricalState(
            buses={},
            battery_voltage=12.6,
            battery_soc_percent=100.0,
            battery_current_amps=0.0,
            alternator_output_amps=0.0,
            total_load_amps=0.0,
            power_sources_available=[PowerSource.BATTERY],
            warnings=[],
            failures=[],
        )
        assert state.battery_voltage == 12.6
        assert state.battery_soc_percent == 100.0
        assert len(state.warnings) == 0
        assert len(state.failures) == 0

    def test_battery_type_enum(self):
        """Test BatteryType enum values."""
        assert BatteryType.LEAD_ACID.value == "lead_acid"
        assert BatteryType.NICAD.value == "nicad"
        assert BatteryType.LITHIUM_ION.value == "lithium_ion"

    def test_power_source_enum(self):
        """Test PowerSource enum values."""
        assert PowerSource.BATTERY.value == "battery"
        assert PowerSource.ALTERNATOR.value == "alternator"
        assert PowerSource.GENERATOR.value == "generator"
        assert PowerSource.APU_GENERATOR.value == "apu_generator"
        assert PowerSource.EXTERNAL_POWER.value == "external_power"
        assert PowerSource.RAT.value == "rat"

    def test_ielectrical_system_is_abstract(self):
        """Test that IElectricalSystem cannot be instantiated directly."""
        with pytest.raises(TypeError):
            IElectricalSystem()  # type: ignore

    def test_ielectrical_system_subclass(self):
        """Test that IElectricalSystem can be subclassed."""

        class MockElectricalSystem(IElectricalSystem):
            def initialize(self, config: dict) -> None:
                pass

            def update(self, dt: float, engine_rpm: float) -> None:
                pass

            def get_state(self) -> ElectricalState:
                return ElectricalState(
                    buses={},
                    battery_voltage=12.0,
                    battery_soc_percent=50.0,
                    battery_current_amps=0.0,
                    alternator_output_amps=0.0,
                    total_load_amps=0.0,
                    power_sources_available=[],
                )

            def set_load_enabled(self, load_name: str, enabled: bool) -> bool:
                return True

            def get_bus_voltage(self, bus_name: str) -> float:
                return 12.0

            def can_draw_current(self, amps: float) -> bool:
                return True

            def simulate_failure(self, failure_type: str) -> None:
                pass

        # Should be able to instantiate concrete implementation
        system = MockElectricalSystem()
        assert system is not None
        state = system.get_state()
        assert state.battery_voltage == 12.0


class TestFuelBaseInterface:
    """Test fuel system base interface."""

    def test_fuel_tank_creation(self):
        """Test FuelTank dataclass creation."""
        tank = FuelTank(
            name="left",
            capacity_total=28.0,
            capacity_usable=26.0,
            current_quantity=26.0,
            fuel_type=FuelType.AVGAS_100LL,
            position=(-5.0, 0.0, -8.0),
        )
        assert tank.name == "left"
        assert tank.capacity_total == 28.0
        assert tank.capacity_usable == 26.0
        assert tank.current_quantity == 26.0
        assert tank.fuel_type == FuelType.AVGAS_100LL
        assert tank.position == (-5.0, 0.0, -8.0)

    def test_fuel_state_creation(self):
        """Test FuelState dataclass creation."""
        state = FuelState(
            tanks={},
            total_quantity_gallons=52.0,
            total_usable_gallons=52.0,
            total_weight_lbs=312.0,
            fuel_selector_position=FuelSelectorPosition.BOTH,
            fuel_flow_rate_gph=8.0,
            fuel_pressure_psi=5.0,
            fuel_temperature_c=20.0,
            center_of_gravity_shift=(0.0, 0.0, 0.0),
            warnings=[],
            failures=[],
            time_remaining_minutes=390.0,
        )
        assert state.total_quantity_gallons == 52.0
        assert state.fuel_selector_position == FuelSelectorPosition.BOTH
        assert state.fuel_flow_rate_gph == 8.0
        assert state.time_remaining_minutes == 390.0

    def test_fuel_type_enum(self):
        """Test FuelType enum values."""
        assert FuelType.AVGAS_100LL.value == "avgas_100ll"
        assert FuelType.JET_A.value == "jet_a"
        assert FuelType.JET_A1.value == "jet_a1"
        assert FuelType.MOGAS.value == "mogas"

    def test_fuel_selector_position_enum(self):
        """Test FuelSelectorPosition enum values."""
        assert FuelSelectorPosition.OFF.value == "off"
        assert FuelSelectorPosition.LEFT.value == "left"
        assert FuelSelectorPosition.RIGHT.value == "right"
        assert FuelSelectorPosition.BOTH.value == "both"
        assert FuelSelectorPosition.CROSSFEED.value == "crossfeed"
        assert FuelSelectorPosition.CENTER.value == "center"
        assert FuelSelectorPosition.ALL.value == "all"

    def test_ifuel_system_is_abstract(self):
        """Test that IFuelSystem cannot be instantiated directly."""
        with pytest.raises(TypeError):
            IFuelSystem()  # type: ignore

    def test_ifuel_system_subclass(self):
        """Test that IFuelSystem can be subclassed."""

        class MockFuelSystem(IFuelSystem):
            def initialize(self, config: dict) -> None:
                pass

            def update(self, dt: float, fuel_flow_gph: float) -> None:
                pass

            def get_state(self) -> FuelState:
                return FuelState(
                    tanks={},
                    total_quantity_gallons=50.0,
                    total_usable_gallons=50.0,
                    total_weight_lbs=300.0,
                    fuel_selector_position=FuelSelectorPosition.BOTH,
                    fuel_flow_rate_gph=8.0,
                    fuel_pressure_psi=5.0,
                    fuel_temperature_c=20.0,
                    center_of_gravity_shift=(0.0, 0.0, 0.0),
                )

            def set_selector_position(self, position: FuelSelectorPosition) -> bool:
                return True

            def get_available_fuel_flow(self) -> float:
                return 15.0

            def set_pump_enabled(self, pump_name: str, enabled: bool) -> bool:
                return True

            def refuel(self, tank_name: str, gallons: float) -> bool:
                return True

            def get_fuel_weight_distribution(self) -> dict[str, float]:
                return {"left": 150.0, "right": 150.0}

            def drain_tank(self, tank_name: str, gallons: float) -> float:
                return gallons

        # Should be able to instantiate concrete implementation
        system = MockFuelSystem()
        assert system is not None
        state = system.get_state()
        assert state.total_quantity_gallons == 50.0


class TestEngineBaseInterface:
    """Test engine base interface."""

    def test_engine_state_creation(self):
        """Test EngineState dataclass creation."""
        state = EngineState(
            engine_type=EngineType.PISTON_NATURALLY_ASPIRATED,
            running=True,
            power_output_hp=160.0,
            fuel_flow_gph=9.5,
            temperature_c=80.0,
            rpm=2400.0,
            manifold_pressure_inhg=25.0,
            oil_pressure_psi=50.0,
            oil_temperature_c=85.0,
            cylinder_head_temp_c=350.0,
            starter_engaged=False,
        )
        assert state.engine_type == EngineType.PISTON_NATURALLY_ASPIRATED
        assert state.running is True
        assert state.power_output_hp == 160.0
        assert state.rpm == 2400.0
        assert len(state.warnings) == 0
        assert len(state.failures) == 0

    def test_engine_controls_creation(self):
        """Test EngineControls dataclass creation."""
        controls = EngineControls(
            throttle=0.75,
            mixture=0.85,
            magneto_left=True,
            magneto_right=True,
            starter=False,
            carburetor_heat=False,
            propeller_rpm=1.0,
        )
        assert controls.throttle == 0.75
        assert controls.mixture == 0.85
        assert controls.magneto_left is True
        assert controls.magneto_right is True

    def test_engine_type_enum(self):
        """Test EngineType enum values."""
        assert EngineType.PISTON_NATURALLY_ASPIRATED.value == "piston_naturally_aspirated"
        assert EngineType.PISTON_TURBOCHARGED.value == "piston_turbocharged"
        assert EngineType.PISTON_SUPERCHARGED.value == "piston_supercharged"
        assert EngineType.TURBOPROP.value == "turboprop"
        assert EngineType.TURBOFAN.value == "turbofan"
        assert EngineType.TURBOJET.value == "turbojet"

    def test_engine_ignition_type_enum(self):
        """Test EngineIgnitionType enum values."""
        assert EngineIgnitionType.MAGNETO.value == "magneto"
        assert EngineIgnitionType.ELECTRONIC.value == "electronic"
        assert EngineIgnitionType.FADEC.value == "fadec"

    def test_iengine_is_abstract(self):
        """Test that IEngine cannot be instantiated directly."""
        with pytest.raises(TypeError):
            IEngine()  # type: ignore

    def test_iengine_subclass(self):
        """Test that IEngine can be subclassed."""

        class MockEngine(IEngine):
            def initialize(self, config: dict) -> None:
                pass

            def update(
                self,
                dt: float,
                controls: EngineControls,
                electrical_available: bool,
                fuel_available: float,
            ) -> None:
                pass

            def get_state(self) -> EngineState:
                return EngineState(
                    engine_type=EngineType.PISTON_NATURALLY_ASPIRATED,
                    running=True,
                    power_output_hp=100.0,
                    fuel_flow_gph=7.0,
                    temperature_c=75.0,
                    rpm=2000.0,
                )

            def get_thrust_force(self) -> float:
                return 500.0

            def can_start(self) -> bool:
                return True

            def simulate_failure(self, failure_type: str) -> None:
                pass

            def get_fuel_consumption_rate(self) -> float:
                return 7.0

        # Should be able to instantiate concrete implementation
        engine = MockEngine()
        assert engine is not None
        state = engine.get_state()
        assert state.power_output_hp == 100.0

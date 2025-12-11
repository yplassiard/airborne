"""Tests for Rotax engine implementations."""

import pytest

from airborne.systems.engines.base import EngineControls
from airborne.systems.engines.rotax import RotaxEngine, RotaxModel


class TestRotaxEngineInitialization:
    """Test RotaxEngine initialization."""

    def test_default_initialization(self) -> None:
        """Test engine initializes with default values."""
        engine = RotaxEngine()

        assert engine.running is False
        assert engine.engine_rpm == 0.0
        assert engine.prop_rpm == 0.0
        assert engine.power_hp == 0.0

    def test_initialize_912uls(self) -> None:
        """Test initialization as 912 ULS."""
        engine = RotaxEngine()
        engine.initialize({"model": "912uls", "max_power_hp": 100})

        assert engine.config.model == RotaxModel.ROTAX_912_ULS
        assert engine.config.max_power_hp == 100.0
        assert engine.config.max_rpm == 5800.0
        assert engine.config.reduction_ratio == 2.43

    def test_initialize_582(self) -> None:
        """Test initialization as 582 two-stroke."""
        engine = RotaxEngine()
        engine.initialize({"model": "582"})

        assert engine.config.model == RotaxModel.ROTAX_582
        assert engine.config.max_power_hp == 65.0
        assert engine.config.is_two_stroke is True
        assert engine.config.cylinders == 2

    def test_initialize_914(self) -> None:
        """Test initialization as 914 turbo."""
        engine = RotaxEngine()
        engine.initialize({"model": "914ul"})

        assert engine.config.model == RotaxModel.ROTAX_914_UL
        assert engine.config.max_power_hp == 115.0

    def test_custom_parameters(self) -> None:
        """Test custom parameters override defaults."""
        engine = RotaxEngine()
        engine.initialize(
            {
                "model": "912uls",
                "max_power_hp": 95,
                "max_rpm": 5500,
                "idle_rpm": 1500,
                "reduction_ratio": 2.27,
            }
        )

        assert engine.config.max_power_hp == 95.0
        assert engine.config.max_rpm == 5500.0
        assert engine.config.idle_rpm == 1500.0
        assert engine.config.reduction_ratio == 2.27


class TestRotaxEngineStartup:
    """Test engine startup behavior."""

    @pytest.fixture
    def engine(self) -> RotaxEngine:
        """Create initialized engine."""
        e = RotaxEngine()
        e.initialize({"model": "912uls", "max_power_hp": 100})
        return e

    def test_engine_requires_starter(self, engine: RotaxEngine) -> None:
        """Test engine won't start without starter engaged."""
        controls = EngineControls(
            throttle=0.0,
            mixture=1.0,
            magneto_left=True,
            magneto_right=True,
            starter=False,
        )

        for _ in range(60):
            engine.update(0.016, controls, True, 10.0)

        assert engine.running is False

    def test_engine_requires_ignition(self, engine: RotaxEngine) -> None:
        """Test engine won't start without ignition."""
        controls = EngineControls(
            throttle=0.0,
            mixture=1.0,
            magneto_left=False,
            magneto_right=False,
            starter=True,
        )

        for _ in range(60):
            engine.update(0.016, controls, True, 10.0)

        assert engine.running is False

    def test_engine_requires_fuel(self, engine: RotaxEngine) -> None:
        """Test engine won't start without fuel."""
        controls = EngineControls(
            throttle=0.0,
            mixture=1.0,
            magneto_left=True,
            magneto_right=True,
            starter=True,
        )

        for _ in range(60):
            engine.update(0.016, controls, True, 0.0)

        assert engine.running is False

    def test_successful_start(self, engine: RotaxEngine) -> None:
        """Test engine starts with correct conditions."""
        controls = EngineControls(
            throttle=0.0,
            mixture=1.0,
            magneto_left=True,
            magneto_right=True,
            starter=True,
        )

        for _ in range(60):
            engine.update(0.016, controls, True, 10.0)

        assert engine.running is True
        assert engine.engine_rpm > 0.0


class TestRotaxEngineRunning:
    """Test running engine behavior."""

    @pytest.fixture
    def running_engine(self) -> RotaxEngine:
        """Create running engine."""
        engine = RotaxEngine()
        engine.initialize({"model": "912uls", "max_power_hp": 100})
        engine.running = True
        engine.engine_rpm = 1400.0  # Idle
        engine._warmup_factor = 1.0  # Warm
        return engine

    def test_idle_rpm(self, running_engine: RotaxEngine) -> None:
        """Test engine maintains idle RPM at zero throttle."""
        controls = EngineControls(
            throttle=0.0,
            mixture=1.0,
            magneto_left=True,
            magneto_right=True,
        )

        for _ in range(120):
            running_engine.update(0.016, controls, True, 10.0)

        assert running_engine.engine_rpm == pytest.approx(1400.0, rel=0.1)

    def test_full_throttle_rpm(self, running_engine: RotaxEngine) -> None:
        """Test engine reaches max RPM at full throttle."""
        controls = EngineControls(
            throttle=1.0,
            mixture=1.0,
            magneto_left=True,
            magneto_right=True,
        )

        for _ in range(300):
            running_engine.update(0.016, controls, True, 30.0)

        assert running_engine.engine_rpm == pytest.approx(5800.0, rel=0.05)

    def test_gearbox_reduction(self, running_engine: RotaxEngine) -> None:
        """Test prop RPM is reduced by gearbox ratio."""
        controls = EngineControls(
            throttle=1.0,
            mixture=1.0,
            magneto_left=True,
            magneto_right=True,
        )

        for _ in range(300):
            running_engine.update(0.016, controls, True, 30.0)

        expected_prop_rpm = running_engine.engine_rpm / 2.43
        assert running_engine.prop_rpm == pytest.approx(expected_prop_rpm, rel=0.01)
        assert running_engine.get_prop_rpm() == running_engine.prop_rpm

    def test_power_increases_with_throttle(self, running_engine: RotaxEngine) -> None:
        """Test power increases with throttle."""
        # Half throttle
        controls_half = EngineControls(
            throttle=0.5, mixture=1.0, magneto_left=True, magneto_right=True
        )
        for _ in range(200):
            running_engine.update(0.016, controls_half, True, 30.0)
        power_half = running_engine.power_hp

        # Full throttle
        controls_full = EngineControls(
            throttle=1.0, mixture=1.0, magneto_left=True, magneto_right=True
        )
        for _ in range(200):
            running_engine.update(0.016, controls_full, True, 30.0)
        power_full = running_engine.power_hp

        assert power_full > power_half

    def test_fuel_consumption_increases_with_power(self, running_engine: RotaxEngine) -> None:
        """Test fuel consumption increases with power."""
        # Low power
        controls_low = EngineControls(
            throttle=0.3, mixture=1.0, magneto_left=True, magneto_right=True
        )
        for _ in range(120):
            running_engine.update(0.016, controls_low, True, 30.0)
        fuel_low = running_engine.fuel_flow_lph

        # High power
        controls_high = EngineControls(
            throttle=0.9, mixture=1.0, magneto_left=True, magneto_right=True
        )
        for _ in range(200):
            running_engine.update(0.016, controls_high, True, 30.0)
        fuel_high = running_engine.fuel_flow_lph

        assert fuel_high > fuel_low


class TestRotaxEngineIgnition:
    """Test dual ignition system behavior."""

    @pytest.fixture
    def running_engine(self) -> RotaxEngine:
        """Create warm running engine."""
        engine = RotaxEngine()
        engine.initialize({"model": "912uls", "max_power_hp": 100})
        engine.running = True
        engine.engine_rpm = 5000.0
        engine._warmup_factor = 1.0
        return engine

    def test_single_ignition_power_loss(self, running_engine: RotaxEngine) -> None:
        """Test single ignition results in power loss."""
        # Both circuits
        controls_both = EngineControls(
            throttle=0.8, mixture=1.0, magneto_left=True, magneto_right=True
        )
        running_engine.update(0.016, controls_both, True, 30.0)
        power_both = running_engine.power_hp

        # Single circuit
        controls_single = EngineControls(
            throttle=0.8, mixture=1.0, magneto_left=True, magneto_right=False
        )
        running_engine.update(0.016, controls_single, True, 30.0)
        power_single = running_engine.power_hp

        # ~4% power loss expected
        assert power_single < power_both

    def test_no_ignition_shuts_down(self, running_engine: RotaxEngine) -> None:
        """Test engine shuts down with no ignition."""
        controls = EngineControls(
            throttle=0.5, mixture=1.0, magneto_left=False, magneto_right=False
        )

        for _ in range(30):
            running_engine.update(0.016, controls, True, 30.0)

        assert running_engine.running is False


class TestRotaxEngineFuelSystem:
    """Test fuel system behavior."""

    @pytest.fixture
    def running_engine(self) -> RotaxEngine:
        """Create running engine."""
        engine = RotaxEngine()
        engine.initialize({"model": "912uls"})
        engine.running = True
        engine.engine_rpm = 3000.0
        engine._warmup_factor = 1.0
        return engine

    def test_fuel_starvation_shutdown(self, running_engine: RotaxEngine) -> None:
        """Test engine shuts down without fuel."""
        controls = EngineControls(throttle=0.5, mixture=1.0, magneto_left=True, magneto_right=True)

        for _ in range(30):
            running_engine.update(0.016, controls, True, 0.0)

        assert running_engine.running is False
        assert running_engine.fuel_flow_lph == 0.0

    def test_mixture_affects_fuel_flow(self, running_engine: RotaxEngine) -> None:
        """Test mixture affects fuel consumption."""
        controls_rich = EngineControls(
            throttle=0.7, mixture=1.0, magneto_left=True, magneto_right=True
        )
        running_engine.update(0.016, controls_rich, True, 30.0)
        fuel_rich = running_engine.fuel_flow_lph

        controls_lean = EngineControls(
            throttle=0.7, mixture=0.6, magneto_left=True, magneto_right=True
        )
        running_engine.update(0.016, controls_lean, True, 30.0)
        fuel_lean = running_engine.fuel_flow_lph

        assert fuel_lean < fuel_rich


class TestRotaxEngineTemperatures:
    """Test temperature management."""

    @pytest.fixture
    def running_engine(self) -> RotaxEngine:
        """Create running engine."""
        engine = RotaxEngine()
        engine.initialize({"model": "912uls"})
        engine.running = True
        engine.engine_rpm = 4000.0
        return engine

    def test_temperatures_increase_when_running(self, running_engine: RotaxEngine) -> None:
        """Test temperatures increase during operation."""
        initial_coolant = running_engine.coolant_temp_c
        initial_oil = running_engine.oil_temp_c

        controls = EngineControls(throttle=0.7, mixture=1.0, magneto_left=True, magneto_right=True)

        for _ in range(300):
            running_engine.update(0.016, controls, True, 30.0)

        assert running_engine.coolant_temp_c > initial_coolant
        assert running_engine.oil_temp_c > initial_oil

    def test_temperatures_stabilize(self, running_engine: RotaxEngine) -> None:
        """Test temperatures stabilize during sustained operation."""
        controls = EngineControls(throttle=0.6, mixture=1.0, magneto_left=True, magneto_right=True)

        # Run until stable
        for _ in range(1000):
            running_engine.update(0.016, controls, True, 30.0)

        coolant_stable = running_engine.coolant_temp_c

        for _ in range(200):
            running_engine.update(0.016, controls, True, 30.0)

        # Should be stable
        assert running_engine.coolant_temp_c == pytest.approx(coolant_stable, rel=0.05)


class TestRotaxEngineState:
    """Test engine state reporting."""

    def test_state_reports_rpm(self) -> None:
        """Test state includes RPM."""
        engine = RotaxEngine()
        engine.initialize({"model": "912uls"})
        engine.running = True
        engine.engine_rpm = 4500.0

        state = engine.get_state()
        assert state.rpm == 4500.0

    def test_state_reports_warnings(self) -> None:
        """Test state includes warnings."""
        engine = RotaxEngine()
        engine.initialize({"model": "912uls"})
        engine.running = True
        engine.engine_rpm = 6500.0  # Over redline
        engine.coolant_temp_c = 130.0  # Over max

        state = engine.get_state()
        assert "OVER RPM" in state.warnings
        assert "HIGH COOLANT TEMP" in state.warnings

    def test_state_fuel_flow_conversion(self) -> None:
        """Test fuel flow is converted to GPH for state."""
        engine = RotaxEngine()
        engine.initialize({"model": "912uls"})
        engine.fuel_flow_lph = 18.927  # ~5 GPH

        state = engine.get_state()
        assert state.fuel_flow_gph == pytest.approx(5.0, rel=0.01)


class TestRotaxEngineFailure:
    """Test engine failure simulation."""

    def test_simulate_failure(self) -> None:
        """Test failure simulation stops engine."""
        engine = RotaxEngine()
        engine.initialize({"model": "912uls"})
        engine.running = True
        engine.engine_rpm = 4000.0

        engine.simulate_failure("Seized piston")

        assert engine.failed is True
        assert engine.failure_type == "Seized piston"
        assert engine.running is False

    def test_failed_engine_winds_down(self) -> None:
        """Test failed engine RPM decreases."""
        engine = RotaxEngine()
        engine.initialize({"model": "912uls"})
        engine.running = True
        engine.engine_rpm = 5000.0
        engine.simulate_failure("Oil starvation")

        controls = EngineControls(throttle=1.0, mixture=1.0, magneto_left=True, magneto_right=True)

        initial_rpm = engine.engine_rpm
        for _ in range(300):
            engine.update(0.016, controls, True, 30.0)

        assert engine.engine_rpm < initial_rpm

    def test_failed_engine_cannot_restart(self) -> None:
        """Test failed engine cannot be restarted."""
        engine = RotaxEngine()
        engine.initialize({"model": "912uls"})
        engine.simulate_failure("Broken conrod")

        assert engine.can_start() is False


class TestRotaxEngineThrust:
    """Test thrust calculation."""

    def test_no_thrust_when_stopped(self) -> None:
        """Test no thrust when engine not running."""
        engine = RotaxEngine()
        engine.initialize({"model": "912uls"})
        engine.running = False

        assert engine.get_thrust_force() == 0.0

    def test_thrust_proportional_to_power(self) -> None:
        """Test thrust increases with power."""
        engine = RotaxEngine()
        engine.initialize({"model": "912uls"})
        engine.running = True
        engine.power_hp = 50.0
        thrust_50 = engine.get_thrust_force()

        engine.power_hp = 100.0
        thrust_100 = engine.get_thrust_force()

        assert thrust_100 > thrust_50

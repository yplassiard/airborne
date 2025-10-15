"""Tests for SimplePistonEngine implementation."""

from airborne.systems.engines.base import EngineControls, EngineType
from airborne.systems.engines.piston_simple import SimplePistonEngine


class TestSimplePistonEngine:
    """Test cases for SimplePistonEngine."""

    def test_initialization(self):
        """Test engine initializes with default config."""
        engine = SimplePistonEngine()
        engine.initialize({})

        assert engine.rpm == 0.0
        assert not engine.running
        assert not engine.starting
        assert not engine.failed

    def test_engine_requires_electrical_for_starter(self):
        """Test engine starter requires electrical power."""
        engine = SimplePistonEngine()
        engine.initialize({})

        controls = EngineControls(
            starter=True,
            magneto_left=True,
            magneto_right=True,
            mixture=0.8,
        )

        # Update without electrical - starter should not crank
        engine.update(0.1, controls, electrical_available=False, fuel_available=10.0)

        assert engine.rpm == 0.0
        assert not engine.starting

        # Update with electrical - starter should crank
        engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        assert engine.rpm > 0.0
        assert engine.starting

    def test_engine_requires_magnetos_to_start(self):
        """Test engine requires at least one magneto on to start."""
        engine = SimplePistonEngine()
        engine.initialize({})

        controls = EngineControls(
            starter=True,
            magneto_left=False,
            magneto_right=False,
            mixture=0.8,
            throttle=0.2,  # Need some throttle for cold start
        )

        # Crank with no magnetos
        for _ in range(30):  # Crank for 3 seconds
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        assert not engine.running  # Should not start

        # Now turn on magnetos
        controls.magneto_left = True
        controls.magneto_right = True

        for _ in range(30):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        assert engine.running  # Should start now

    def test_engine_requires_fuel_to_start(self):
        """Test engine requires fuel to start."""
        engine = SimplePistonEngine()
        engine.initialize({})

        controls = EngineControls(
            starter=True,
            magneto_left=True,
            magneto_right=True,
            mixture=0.8,
            throttle=0.2,  # Need some throttle for cold start
        )

        # Crank with no fuel
        for _ in range(30):
            engine.update(0.1, controls, electrical_available=True, fuel_available=0.0)

        assert not engine.running  # Should not start

        # Now add fuel
        for _ in range(30):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        assert engine.running  # Should start now

    def test_engine_dies_immediately_without_fuel(self):
        """Test engine dies immediately when fuel exhausted (NO FORGIVENESS)."""
        engine = SimplePistonEngine()
        engine.initialize({})

        # Start engine
        controls = EngineControls(
            starter=True,
            magneto_left=True,
            magneto_right=True,
            mixture=0.8,
            throttle=0.5,
        )

        for _ in range(30):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        assert engine.running
        initial_rpm = engine.rpm

        # Cut fuel - engine should die immediately
        controls.starter = False
        engine.update(0.1, controls, electrical_available=True, fuel_available=0.0)

        assert not engine.running
        assert engine.rpm < initial_rpm  # RPM windmilling down

    def test_engine_dies_with_magnetos_off(self):
        """Test engine dies when both magnetos turned off."""
        engine = SimplePistonEngine()
        engine.initialize({})

        # Start and warm up engine
        controls = EngineControls(
            starter=True,
            magneto_left=True,
            magneto_right=True,
            mixture=0.8,
            throttle=0.5,
        )

        for _ in range(30):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        controls.starter = False
        assert engine.running

        # Turn off both magnetos
        controls.magneto_left = False
        controls.magneto_right = False

        engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        assert not engine.running

    def test_engine_runs_on_single_magneto(self):
        """Test engine can run on just one magneto."""
        engine = SimplePistonEngine()
        engine.initialize({})

        # Start engine with both magnetos
        controls = EngineControls(
            starter=True,
            magneto_left=True,
            magneto_right=True,
            mixture=0.8,
            throttle=0.5,
        )

        for _ in range(30):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        controls.starter = False
        assert engine.running

        # Turn off left magneto, keep right on
        controls.magneto_left = False

        for _ in range(10):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        assert engine.running  # Should still run on one magneto

    def test_throttle_controls_rpm(self):
        """Test throttle controls engine RPM."""
        engine = SimplePistonEngine()
        engine.initialize({})

        # Start engine with some throttle
        controls = EngineControls(
            starter=True,
            magneto_left=True,
            magneto_right=True,
            mixture=0.8,
            throttle=0.2,  # Start with some throttle
        )

        for _ in range(30):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        controls.starter = False

        # Reduce to idle
        controls.throttle = 0.0
        for _ in range(20):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        idle_rpm = engine.rpm

        # Increase throttle
        controls.throttle = 1.0  # Full throttle

        for _ in range(50):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        full_throttle_rpm = engine.rpm

        assert full_throttle_rpm > idle_rpm
        assert full_throttle_rpm > 2000.0  # Should be near max RPM

    def test_mixture_affects_fuel_consumption(self):
        """Test mixture control affects fuel consumption."""
        engine = SimplePistonEngine()
        engine.initialize({})

        # Start engine
        controls = EngineControls(
            starter=True,
            magneto_left=True,
            magneto_right=True,
            mixture=0.8,
            throttle=0.5,
        )

        for _ in range(30):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        controls.starter = False

        # Run at lean mixture
        controls.mixture = 0.5
        for _ in range(10):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        lean_fuel_flow = engine.fuel_flow_gph

        # Run at rich mixture
        controls.mixture = 1.0
        for _ in range(10):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        rich_fuel_flow = engine.fuel_flow_gph

        assert rich_fuel_flow > lean_fuel_flow

    def test_engine_produces_power_output(self):
        """Test engine produces horsepower when running."""
        engine = SimplePistonEngine()
        engine.initialize({})

        # Start engine
        controls = EngineControls(
            starter=True,
            magneto_left=True,
            magneto_right=True,
            mixture=0.8,
            throttle=0.5,
        )

        for _ in range(30):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        controls.starter = False

        # Run at half throttle
        for _ in range(20):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        state = engine.get_state()

        assert state.power_output_hp > 0.0
        assert state.power_output_hp < engine.config.max_horsepower

        # Increase to full throttle
        controls.throttle = 1.0
        for _ in range(20):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        state_full = engine.get_state()
        assert state_full.power_output_hp > state.power_output_hp

    def test_engine_state_reporting(self):
        """Test engine reports state correctly."""
        engine = SimplePistonEngine()
        engine.initialize({})

        # Engine off
        state = engine.get_state()
        assert state.engine_type == EngineType.PISTON_NATURALLY_ASPIRATED
        assert not state.running
        assert state.rpm == 0.0
        assert state.fuel_flow_gph == 0.0
        assert state.power_output_hp == 0.0

        # Start engine
        controls = EngineControls(
            starter=True,
            magneto_left=True,
            magneto_right=True,
            mixture=0.8,
            throttle=0.5,
        )

        for _ in range(30):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        state = engine.get_state()
        assert state.running
        assert state.rpm > 0.0
        assert state.fuel_flow_gph > 0.0
        assert state.power_output_hp > 0.0
        assert state.manifold_pressure_inhg is not None
        assert state.oil_pressure_psi is not None
        assert state.oil_temperature_c is not None

    def test_oil_pressure_depends_on_rpm(self):
        """Test oil pressure increases with RPM."""
        engine = SimplePistonEngine()
        engine.initialize({})

        # Start engine with some throttle
        controls = EngineControls(
            starter=True,
            magneto_left=True,
            magneto_right=True,
            mixture=0.8,
            throttle=0.2,
        )

        for _ in range(30):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        controls.starter = False

        # Reduce to idle
        controls.throttle = 0.0
        for _ in range(20):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        idle_oil_pressure = engine.oil_pressure_psi

        # Run up to high RPM
        controls.throttle = 1.0
        for _ in range(50):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        high_rpm_oil_pressure = engine.oil_pressure_psi

        assert high_rpm_oil_pressure > idle_oil_pressure

    def test_engine_warms_up_over_time(self):
        """Test engine temperatures increase during operation."""
        engine = SimplePistonEngine()
        engine.initialize({})

        # Start engine
        controls = EngineControls(
            starter=True,
            magneto_left=True,
            magneto_right=True,
            mixture=0.8,
            throttle=0.5,
        )

        for _ in range(30):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        controls.starter = False
        initial_temp = engine.oil_temp_f

        # Run for a while
        for _ in range(100):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        warmed_temp = engine.oil_temp_f

        assert warmed_temp > initial_temp

    def test_simulated_failure(self):
        """Test engine failure simulation."""
        engine = SimplePistonEngine()
        engine.initialize({})

        # Start engine
        controls = EngineControls(
            starter=True,
            magneto_left=True,
            magneto_right=True,
            mixture=0.8,
            throttle=0.5,
        )

        for _ in range(30):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        assert engine.running

        # Simulate failure
        engine.simulate_failure("oil_pressure")

        assert engine.failed
        assert not engine.running

        # Engine should not restart
        controls.starter = True
        for _ in range(30):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        assert not engine.running

    def test_get_fuel_consumption_rate(self):
        """Test fuel consumption rate reporting."""
        engine = SimplePistonEngine()
        engine.initialize({})

        # Engine off
        assert engine.get_fuel_consumption_rate() == 0.0

        # Start and run engine
        controls = EngineControls(
            starter=True,
            magneto_left=True,
            magneto_right=True,
            mixture=0.8,
            throttle=0.5,
        )

        for _ in range(30):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        controls.starter = False
        for _ in range(10):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        assert engine.get_fuel_consumption_rate() > 0.0

    def test_thrust_calculation(self):
        """Test thrust force calculation."""
        engine = SimplePistonEngine()
        engine.initialize({})

        # Engine off
        assert engine.get_thrust_force() == 0.0

        # Start and run engine
        controls = EngineControls(
            starter=True,
            magneto_left=True,
            magneto_right=True,
            mixture=0.8,
            throttle=0.5,
        )

        for _ in range(30):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        controls.starter = False
        for _ in range(10):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        thrust = engine.get_thrust_force()
        assert thrust > 0.0

        # Higher throttle = more thrust
        controls.throttle = 1.0
        for _ in range(20):
            engine.update(0.1, controls, electrical_available=True, fuel_available=10.0)

        thrust_full = engine.get_thrust_force()
        assert thrust_full > thrust

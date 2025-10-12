"""Tests for simple piston engine plugin."""

from unittest.mock import Mock

import pytest

from airborne.core.event_bus import EventBus
from airborne.core.messaging import Message, MessageTopic
from airborne.core.plugin import PluginContext, PluginType
from airborne.plugins.engines.simple_piston import EngineStateEvent, SimplePistonEngine


class TestSimplePistonEngineMetadata:
    """Test engine plugin metadata."""

    def test_get_metadata(self) -> None:
        """Test getting plugin metadata."""
        engine = SimplePistonEngine()
        metadata = engine.get_metadata()

        assert metadata.name == "simple_piston_engine"
        assert metadata.version == "1.0.0"
        assert metadata.plugin_type == PluginType.AIRCRAFT_SYSTEM
        assert "engine" in metadata.provides
        assert "propulsion" in metadata.provides
        assert metadata.optional is False
        assert metadata.requires_physics is True


class TestSimplePistonEngineInitialization:
    """Test engine initialization."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def message_queue(self) -> Mock:
        """Create mock message queue."""
        queue = Mock()
        queue.subscribe = Mock()
        queue.publish = Mock()
        queue.unsubscribe = Mock()
        return queue

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: Mock) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={},
            plugin_registry=None,
        )

    def test_initialize(self, context: PluginContext) -> None:
        """Test engine initialization."""
        engine = SimplePistonEngine()
        engine.initialize(context)

        assert engine.context == context
        # Should subscribe to engine state messages
        context.message_queue.subscribe.assert_called_once_with(
            MessageTopic.ENGINE_STATE, engine.handle_message
        )

    def test_initial_state(self) -> None:
        """Test initial engine state."""
        engine = SimplePistonEngine()

        assert engine.rpm == 0.0
        assert engine.running is False
        assert engine.starter_engaged is False
        assert engine.magneto_left is False
        assert engine.magneto_right is False
        assert engine.mixture == 1.0
        assert engine.throttle == 0.0


class TestSimplePistonEngineControls:
    """Test engine control handling."""

    @pytest.fixture
    def engine(self) -> SimplePistonEngine:
        """Create engine instance."""
        return SimplePistonEngine()

    def test_handle_starter_message(self, engine: SimplePistonEngine) -> None:
        """Test handling starter control message."""
        message = Message(
            sender="test",
            recipients=["simple_piston_engine"],
            topic=MessageTopic.ENGINE_STATE,
            data={"starter": True},
        )

        engine.handle_message(message)
        assert engine.starter_engaged is True

        message.data["starter"] = False
        engine.handle_message(message)
        assert engine.starter_engaged is False

    def test_handle_magneto_message(self, engine: SimplePistonEngine) -> None:
        """Test handling magneto control messages."""
        message = Message(
            sender="test",
            recipients=["simple_piston_engine"],
            topic=MessageTopic.ENGINE_STATE,
            data={"magneto_left": True, "magneto_right": True},
        )

        engine.handle_message(message)
        assert engine.magneto_left is True
        assert engine.magneto_right is True

    def test_handle_mixture_message(self, engine: SimplePistonEngine) -> None:
        """Test handling mixture control message."""
        message = Message(
            sender="test",
            recipients=["simple_piston_engine"],
            topic=MessageTopic.ENGINE_STATE,
            data={"mixture": 0.75},
        )

        engine.handle_message(message)
        assert engine.mixture == 0.75

    def test_mixture_clamped_to_valid_range(self, engine: SimplePistonEngine) -> None:
        """Test mixture is clamped to 0-1 range."""
        message = Message(
            sender="test",
            recipients=["simple_piston_engine"],
            topic=MessageTopic.ENGINE_STATE,
            data={"mixture": 1.5},
        )

        engine.handle_message(message)
        assert engine.mixture == 1.0

        message.data["mixture"] = -0.5
        engine.handle_message(message)
        assert engine.mixture == 0.0

    def test_handle_throttle_message(self, engine: SimplePistonEngine) -> None:
        """Test handling throttle control message."""
        message = Message(
            sender="test",
            recipients=["simple_piston_engine"],
            topic=MessageTopic.ENGINE_STATE,
            data={"throttle": 0.5},
        )

        engine.handle_message(message)
        assert engine.throttle == 0.5


class TestSimplePistonEngineStartup:
    """Test engine startup behavior."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def message_queue(self) -> Mock:
        """Create mock message queue."""
        queue = Mock()
        queue.subscribe = Mock()
        queue.publish = Mock()
        return queue

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: Mock) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={},
            plugin_registry=None,
        )

    @pytest.fixture
    def engine(self, context: PluginContext) -> SimplePistonEngine:
        """Create initialized engine."""
        engine = SimplePistonEngine()
        engine.initialize(context)
        return engine

    def test_engine_does_not_start_without_ignition(self, engine: SimplePistonEngine) -> None:
        """Test engine requires magnetos to start."""
        engine.starter_engaged = True
        engine.mixture = 1.0
        engine.throttle = 0.2

        # Update for 5 seconds
        for _ in range(300):
            engine.update(0.016)

        # Should not start without magnetos
        assert engine.running is False

    def test_engine_does_not_start_without_fuel(self, engine: SimplePistonEngine) -> None:
        """Test engine requires fuel mixture to start."""
        engine.starter_engaged = True
        engine.magneto_left = True
        engine.mixture = 0.0  # No fuel
        engine.throttle = 0.2

        # Update for 5 seconds
        for _ in range(300):
            engine.update(0.016)

        # Should not start without fuel
        assert engine.running is False

    def test_engine_starts_with_proper_conditions(self, engine: SimplePistonEngine) -> None:
        """Test engine starts with starter, ignition, and fuel."""
        engine.starter_engaged = True
        engine.magneto_left = True
        engine.magneto_right = True
        engine.mixture = 1.0
        engine.throttle = 0.1

        # Update until engine starts
        for _ in range(300):
            engine.update(0.016)
            if engine.running:
                break

        assert engine.running is True
        assert engine.rpm > 400

    def test_rpm_increases_during_startup(self, engine: SimplePistonEngine) -> None:
        """Test RPM increases when starter is engaged."""
        engine.starter_engaged = True
        engine.magneto_left = True
        engine.mixture = 1.0

        initial_rpm = engine.rpm

        # Update for 1 second
        for _ in range(60):
            engine.update(0.016)

        assert engine.rpm > initial_rpm


class TestSimplePistonEngineRunning:
    """Test running engine behavior."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def message_queue(self) -> Mock:
        """Create mock message queue."""
        queue = Mock()
        queue.subscribe = Mock()
        queue.publish = Mock()
        return queue

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: Mock) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={},
            plugin_registry=None,
        )

    @pytest.fixture
    def running_engine(self, context: PluginContext) -> SimplePistonEngine:
        """Create a running engine."""
        engine = SimplePistonEngine()
        engine.initialize(context)

        # Start the engine
        engine.starter_engaged = True
        engine.magneto_left = True
        engine.magneto_right = True
        engine.mixture = 1.0
        engine.throttle = 0.1

        # Run until started
        for _ in range(300):
            engine.update(0.016)
            if engine.running:
                break

        engine.starter_engaged = False
        return engine

    def test_rpm_increases_with_throttle(self, running_engine: SimplePistonEngine) -> None:
        """Test RPM responds to throttle input."""
        # Set to idle
        running_engine.throttle = 0.0
        for _ in range(60):
            running_engine.update(0.016)
        idle_rpm = running_engine.rpm

        # Increase throttle
        running_engine.throttle = 0.5
        for _ in range(120):
            running_engine.update(0.016)

        assert running_engine.rpm > idle_rpm

    def test_oil_pressure_builds_when_running(self, running_engine: SimplePistonEngine) -> None:
        """Test oil pressure increases with RPM."""
        running_engine.throttle = 0.5

        # Update for 2 seconds
        for _ in range(120):
            running_engine.update(0.016)

        assert running_engine.oil_pressure > 20.0

    def test_oil_temperature_increases_when_running(
        self, running_engine: SimplePistonEngine
    ) -> None:
        """Test oil temperature increases over time."""
        initial_temp = running_engine.oil_temp
        running_engine.throttle = 0.5

        # Update for 5 seconds
        for _ in range(300):
            running_engine.update(0.016)

        assert running_engine.oil_temp > initial_temp

    def test_fuel_flow_increases_with_rpm(self, running_engine: SimplePistonEngine) -> None:
        """Test fuel flow increases with engine RPM."""
        running_engine.throttle = 0.0
        for _ in range(60):
            running_engine.update(0.016)
        idle_fuel_flow = running_engine.fuel_flow

        running_engine.throttle = 0.7
        for _ in range(120):
            running_engine.update(0.016)

        assert running_engine.fuel_flow > idle_fuel_flow

    def test_manifold_pressure_decreases_with_throttle(
        self, running_engine: SimplePistonEngine
    ) -> None:
        """Test manifold pressure varies with throttle."""
        # Full throttle = high manifold pressure
        running_engine.throttle = 1.0
        for _ in range(60):
            running_engine.update(0.016)
        full_throttle_pressure = running_engine.manifold_pressure

        # Idle = low manifold pressure (high vacuum)
        running_engine.throttle = 0.0
        for _ in range(60):
            running_engine.update(0.016)
        idle_pressure = running_engine.manifold_pressure

        assert full_throttle_pressure > idle_pressure


class TestSimplePistonEngineShutdown:
    """Test engine shutdown behavior."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def message_queue(self) -> Mock:
        """Create mock message queue."""
        queue = Mock()
        queue.subscribe = Mock()
        queue.publish = Mock()
        queue.unsubscribe = Mock()
        return queue

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: Mock) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={},
            plugin_registry=None,
        )

    @pytest.fixture
    def running_engine(self, context: PluginContext) -> SimplePistonEngine:
        """Create a running engine."""
        engine = SimplePistonEngine()
        engine.initialize(context)

        # Start the engine
        engine.starter_engaged = True
        engine.magneto_left = True
        engine.magneto_right = True
        engine.mixture = 1.0
        engine.throttle = 0.1

        # Run until started
        for _ in range(300):
            engine.update(0.016)
            if engine.running:
                break

        engine.starter_engaged = False
        return engine

    def test_engine_stops_when_magnetos_off(self, running_engine: SimplePistonEngine) -> None:
        """Test engine stops when ignition is cut."""
        assert running_engine.running is True

        # Cut ignition
        running_engine.magneto_left = False
        running_engine.magneto_right = False

        # Update until engine stops
        for _ in range(300):
            running_engine.update(0.016)
            if not running_engine.running:
                break

        assert running_engine.running is False
        assert running_engine.rpm < 200

    def test_engine_stops_when_mixture_cutoff(self, running_engine: SimplePistonEngine) -> None:
        """Test engine stops with fuel cutoff."""
        assert running_engine.running is True

        # Cut fuel
        running_engine.mixture = 0.0

        # Update until engine stops
        for _ in range(300):
            running_engine.update(0.016)
            if not running_engine.running:
                break

        assert running_engine.running is False

    def test_shutdown_unsubscribes_from_messages(self, running_engine: SimplePistonEngine) -> None:
        """Test shutdown cleans up subscriptions."""
        running_engine.shutdown()

        # Should unsubscribe from messages
        running_engine.context.message_queue.unsubscribe.assert_called_once_with(
            MessageTopic.ENGINE_STATE, running_engine.handle_message
        )

        assert running_engine.running is False
        assert running_engine.rpm == 0.0


class TestSimplePistonEngineEventPublishing:
    """Test engine event publishing."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def message_queue(self) -> Mock:
        """Create mock message queue."""
        queue = Mock()
        queue.subscribe = Mock()
        queue.publish = Mock()
        return queue

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: Mock) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={},
            plugin_registry=None,
        )

    @pytest.fixture
    def engine(self, context: PluginContext) -> SimplePistonEngine:
        """Create initialized engine."""
        engine = SimplePistonEngine()
        engine.initialize(context)
        return engine

    def test_publishes_engine_state_event(
        self, engine: SimplePistonEngine, event_bus: EventBus
    ) -> None:
        """Test engine publishes state events."""
        received_events = []

        def handler(event: EngineStateEvent) -> None:
            received_events.append(event)

        event_bus.subscribe(EngineStateEvent, handler)

        engine.update(0.016)

        assert len(received_events) == 1
        assert isinstance(received_events[0], EngineStateEvent)
        assert received_events[0].rpm == engine.rpm
        assert received_events[0].running == engine.running

    def test_publishes_engine_state_message(self, engine: SimplePistonEngine) -> None:
        """Test engine publishes state messages."""
        engine.update(0.016)

        # Should publish message
        engine.context.message_queue.publish.assert_called()

        # Check message content
        call_args = engine.context.message_queue.publish.call_args
        message = call_args[0][0]

        assert isinstance(message, Message)
        assert message.sender == "simple_piston_engine"
        assert message.topic == MessageTopic.ENGINE_STATE
        assert "rpm" in message.data
        assert "running" in message.data
        assert "power_hp" in message.data


class TestSimplePistonEnginePowerCalculation:
    """Test engine power output calculation."""

    def test_power_is_zero_when_not_running(self) -> None:
        """Test power is zero when engine is off."""
        engine = SimplePistonEngine()
        engine.running = False

        power = engine._calculate_power()
        assert power == 0.0

    def test_power_increases_with_throttle(self) -> None:
        """Test power increases with throttle input."""
        engine = SimplePistonEngine()
        engine.running = True
        engine.rpm = 2400

        engine.throttle = 0.25
        power_low = engine._calculate_power()

        engine.throttle = 0.75
        power_high = engine._calculate_power()

        assert power_high > power_low

    def test_power_affected_by_mixture(self) -> None:
        """Test mixture affects power output."""
        engine = SimplePistonEngine()
        engine.running = True
        engine.rpm = 2400
        engine.throttle = 0.75

        # Optimal mixture
        engine.mixture = 0.8
        power_optimal = engine._calculate_power()

        # Too lean
        engine.mixture = 0.3
        power_lean = engine._calculate_power()

        # Too rich
        engine.mixture = 1.0
        power_rich = engine._calculate_power()

        assert power_optimal > power_lean
        assert power_optimal > power_rich

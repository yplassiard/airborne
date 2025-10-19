"""Tests for simple fuel system plugin."""

from unittest.mock import Mock

import pytest

from airborne.core.event_bus import EventBus
from airborne.core.messaging import Message, MessageTopic
from airborne.core.plugin import PluginContext, PluginType
from airborne.plugins.systems.simple_fuel_plugin import FuelStateEvent, SimpleFuelSystem


class TestSimpleFuelSystemMetadata:
    """Test fuel system plugin metadata."""

    def test_get_metadata(self) -> None:
        """Test getting plugin metadata."""
        fuel = SimpleFuelSystem()
        metadata = fuel.get_metadata()

        assert metadata.name == "simple_fuel_system"
        assert metadata.version == "1.0.0"
        assert metadata.plugin_type == PluginType.AIRCRAFT_SYSTEM
        assert "fuel" in metadata.provides
        assert "simple_piston_engine" in metadata.dependencies
        assert metadata.optional is False


class TestSimpleFuelSystemInitialization:
    """Test fuel system initialization."""

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
        """Test fuel system initialization."""
        fuel = SimpleFuelSystem()
        fuel.initialize(context)

        assert fuel.context == context
        # Should subscribe to engine and fuel messages
        assert context.message_queue.subscribe.call_count == 2

    def test_initial_state(self) -> None:
        """Test initial fuel system state."""
        fuel = SimpleFuelSystem()

        assert fuel.left_tank_quantity == 26.0  # Full
        assert fuel.right_tank_quantity == 26.0  # Full
        assert fuel.fuel_selector == "both"
        assert fuel.left_pump_on is False
        assert fuel.right_pump_on is False
        assert fuel.fuel_pressure == 0.0


class TestSimpleFuelSystemControls:
    """Test fuel system control handling."""

    @pytest.fixture
    def fuel(self) -> SimpleFuelSystem:
        """Create fuel system instance."""
        return SimpleFuelSystem()

    def test_handle_fuel_selector_message(self, fuel: SimpleFuelSystem) -> None:
        """Test handling fuel selector message."""
        message = Message(
            sender="test",
            recipients=["simple_fuel_system"],
            topic=MessageTopic.FUEL_STATE,
            data={"fuel_selector": "left"},
        )

        fuel.handle_message(message)
        assert fuel.fuel_selector == "left"

        message.data["fuel_selector"] = "right"
        fuel.handle_message(message)
        assert fuel.fuel_selector == "right"

        message.data["fuel_selector"] = "both"
        fuel.handle_message(message)
        assert fuel.fuel_selector == "both"

        message.data["fuel_selector"] = "off"
        fuel.handle_message(message)
        assert fuel.fuel_selector == "off"

    def test_handle_pump_messages(self, fuel: SimpleFuelSystem) -> None:
        """Test handling pump control messages."""
        message = Message(
            sender="test",
            recipients=["simple_fuel_system"],
            topic=MessageTopic.FUEL_STATE,
            data={"left_pump": True, "right_pump": True},
        )

        fuel.handle_message(message)
        assert fuel.left_pump_on is True
        assert fuel.right_pump_on is True

    def test_ignores_invalid_selector_values(self, fuel: SimpleFuelSystem) -> None:
        """Test invalid selector values are ignored."""
        initial_selector = fuel.fuel_selector

        message = Message(
            sender="test",
            recipients=["simple_fuel_system"],
            topic=MessageTopic.FUEL_STATE,
            data={"fuel_selector": "invalid"},
        )

        fuel.handle_message(message)
        assert fuel.fuel_selector == initial_selector


class TestSimpleFuelSystemPressure:
    """Test fuel pressure behavior."""

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
    def fuel(self, context: PluginContext) -> SimpleFuelSystem:
        """Create initialized fuel system."""
        system = SimpleFuelSystem()
        system.initialize(context)
        return system

    def test_no_pressure_when_selector_off(self, fuel: SimpleFuelSystem) -> None:
        """Test no fuel pressure when selector is off."""
        fuel.fuel_selector = "off"
        fuel.left_pump_on = True

        fuel.update(0.016)

        assert fuel.fuel_pressure == 0.0

    def test_pressure_with_pump_on(self, fuel: SimpleFuelSystem) -> None:
        """Test fuel pressure with pump on."""
        fuel.fuel_selector = "both"
        fuel.left_pump_on = True

        fuel.update(0.016)

        assert fuel.fuel_pressure > 0.0
        assert fuel.fuel_pressure == pytest.approx(4.5)  # Pump pressure

    def test_pressure_with_gravity_feed(self, fuel: SimpleFuelSystem) -> None:
        """Test fuel pressure with gravity feed only."""
        fuel.fuel_selector = "both"
        fuel.left_pump_on = False
        fuel.right_pump_on = False

        fuel.update(0.016)

        assert fuel.fuel_pressure > 0.0
        assert fuel.fuel_pressure == pytest.approx(2.5)  # Gravity pressure

    def test_no_pressure_when_tanks_empty(self, fuel: SimpleFuelSystem) -> None:
        """Test no pressure when tanks are empty."""
        fuel.fuel_selector = "both"
        fuel.left_pump_on = True
        fuel.left_tank_quantity = 0.0
        fuel.right_tank_quantity = 0.0

        fuel.update(0.016)

        assert fuel.fuel_pressure == 0.0


class TestSimpleFuelSystemConsumption:
    """Test fuel consumption behavior."""

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
    def fuel(self, context: PluginContext) -> SimpleFuelSystem:
        """Create initialized fuel system."""
        system = SimpleFuelSystem()
        system.initialize(context)
        return system

    def test_fuel_consumed_from_left_tank(self, fuel: SimpleFuelSystem) -> None:
        """Test fuel is consumed from left tank when selected."""
        fuel.fuel_selector = "left"
        fuel._engine_fuel_demand = 8.0  # 8 GPH

        initial_left = fuel.left_tank_quantity
        initial_right = fuel.right_tank_quantity

        # Run for 60 seconds
        for _ in range(3600):
            fuel.update(0.016)

        assert fuel.left_tank_quantity < initial_left
        assert fuel.right_tank_quantity == initial_right  # Unchanged

    def test_fuel_consumed_from_right_tank(self, fuel: SimpleFuelSystem) -> None:
        """Test fuel is consumed from right tank when selected."""
        fuel.fuel_selector = "right"
        fuel._engine_fuel_demand = 8.0

        initial_left = fuel.left_tank_quantity
        initial_right = fuel.right_tank_quantity

        # Run for 60 seconds
        for _ in range(3600):
            fuel.update(0.016)

        assert fuel.right_tank_quantity < initial_right
        assert fuel.left_tank_quantity == initial_left  # Unchanged

    def test_fuel_consumed_equally_from_both_tanks(self, fuel: SimpleFuelSystem) -> None:
        """Test fuel is consumed equally from both tanks."""
        fuel.fuel_selector = "both"
        fuel._engine_fuel_demand = 8.0

        initial_left = fuel.left_tank_quantity
        initial_right = fuel.right_tank_quantity

        # Run for 60 seconds
        for _ in range(3600):
            fuel.update(0.016)

        left_consumed = initial_left - fuel.left_tank_quantity
        right_consumed = initial_right - fuel.right_tank_quantity

        assert left_consumed == pytest.approx(right_consumed, abs=0.01)

    def test_no_fuel_consumed_when_selector_off(self, fuel: SimpleFuelSystem) -> None:
        """Test no fuel is consumed when selector is off."""
        fuel.fuel_selector = "off"
        fuel._engine_fuel_demand = 8.0

        initial_left = fuel.left_tank_quantity
        initial_right = fuel.right_tank_quantity

        # Run for 60 seconds
        for _ in range(3600):
            fuel.update(0.016)

        assert fuel.left_tank_quantity == initial_left
        assert fuel.right_tank_quantity == initial_right

    def test_fuel_quantity_cannot_go_negative(self, fuel: SimpleFuelSystem) -> None:
        """Test fuel quantity is clamped to zero."""
        fuel.fuel_selector = "left"
        fuel.left_tank_quantity = 0.1  # Almost empty
        fuel._engine_fuel_demand = 10.0  # High demand

        # Run for a long time
        for _ in range(7200):
            fuel.update(0.016)

        assert fuel.left_tank_quantity >= 0.0


class TestSimpleFuelSystemFlow:
    """Test fuel flow calculation."""

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
    def fuel(self, context: PluginContext) -> SimpleFuelSystem:
        """Create initialized fuel system."""
        system = SimpleFuelSystem()
        system.initialize(context)
        return system

    def test_fuel_flow_matches_engine_demand(self, fuel: SimpleFuelSystem) -> None:
        """Test fuel flow matches engine demand."""
        fuel.fuel_selector = "both"
        fuel._engine_fuel_demand = 7.5

        fuel.update(0.016)

        assert fuel.fuel_flow == pytest.approx(7.5)

    def test_no_flow_when_selector_off(self, fuel: SimpleFuelSystem) -> None:
        """Test no fuel flow when selector is off."""
        fuel.fuel_selector = "off"
        fuel._engine_fuel_demand = 8.0

        fuel.update(0.016)

        assert fuel.fuel_flow == 0.0

    def test_no_flow_when_tanks_empty(self, fuel: SimpleFuelSystem) -> None:
        """Test no fuel flow when tanks are empty."""
        fuel.fuel_selector = "both"
        fuel._engine_fuel_demand = 8.0
        fuel.left_tank_quantity = 0.0
        fuel.right_tank_quantity = 0.0

        fuel.update(0.016)

        assert fuel.fuel_flow == 0.0


class TestSimpleFuelSystemIntegration:
    """Test fuel system integration with engine."""

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
    def fuel(self, context: PluginContext) -> SimpleFuelSystem:
        """Create initialized fuel system."""
        system = SimpleFuelSystem()
        system.initialize(context)
        return system

    def test_receives_engine_fuel_demand(self, fuel: SimpleFuelSystem) -> None:
        """Test fuel system receives engine fuel demand."""
        message = Message(
            sender="simple_piston_engine",
            recipients=["*"],
            topic=MessageTopic.ENGINE_STATE,
            data={"fuel_flow": 8.5},
        )

        fuel.handle_message(message)

        assert fuel._engine_fuel_demand == 8.5

    def test_responds_to_engine_demand(self, fuel: SimpleFuelSystem) -> None:
        """Test fuel flow responds to engine demand."""
        fuel.fuel_selector = "both"

        # Engine running at cruise
        engine_msg = Message(
            sender="simple_piston_engine",
            recipients=["*"],
            topic=MessageTopic.ENGINE_STATE,
            data={"fuel_flow": 7.0},
        )
        fuel.handle_message(engine_msg)
        fuel.update(0.016)

        assert fuel.fuel_flow == pytest.approx(7.0)


class TestSimpleFuelSystemShutdown:
    """Test fuel system shutdown behavior."""

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
    def fuel(self, context: PluginContext) -> SimpleFuelSystem:
        """Create initialized fuel system."""
        system = SimpleFuelSystem()
        system.initialize(context)
        return system

    def test_shutdown_closes_selector(self, fuel: SimpleFuelSystem) -> None:
        """Test shutdown closes fuel selector."""
        fuel.fuel_selector = "both"
        fuel.left_pump_on = True

        fuel.shutdown()

        assert fuel.fuel_selector == "off"
        assert fuel.left_pump_on is False
        assert fuel.right_pump_on is False
        assert fuel.fuel_pressure == 0.0

    def test_shutdown_unsubscribes_from_messages(self, fuel: SimpleFuelSystem) -> None:
        """Test shutdown cleans up subscriptions."""
        fuel.shutdown()

        # Should unsubscribe from both topics
        assert fuel.context.message_queue.unsubscribe.call_count == 2


class TestSimpleFuelSystemEventPublishing:
    """Test fuel system event publishing."""

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
    def fuel(self, context: PluginContext) -> SimpleFuelSystem:
        """Create initialized fuel system."""
        system = SimpleFuelSystem()
        system.initialize(context)
        return system

    def test_publishes_fuel_state_event(self, fuel: SimpleFuelSystem, event_bus: EventBus) -> None:
        """Test fuel system publishes state events."""
        received_events = []

        def handler(event: FuelStateEvent) -> None:
            received_events.append(event)

        event_bus.subscribe(FuelStateEvent, handler)

        fuel.update(0.016)

        assert len(received_events) == 1
        assert isinstance(received_events[0], FuelStateEvent)
        assert received_events[0].left_tank_quantity == fuel.left_tank_quantity
        assert received_events[0].total_quantity == fuel._get_total_fuel()

    def test_publishes_fuel_state_message(self, fuel: SimpleFuelSystem) -> None:
        """Test fuel system publishes state messages."""
        # Clear the mock calls from initialization
        fuel.context.message_queue.publish.reset_mock()

        fuel.update(0.016)

        # Should publish two messages (FUEL_STATE and SYSTEM_STATE)
        assert fuel.context.message_queue.publish.call_count == 2

        # Check both messages
        calls = fuel.context.message_queue.publish.call_args_list

        # First message should be FUEL_STATE
        fuel_msg = calls[0][0][0]
        assert isinstance(fuel_msg, Message)
        assert fuel_msg.sender == "simple_fuel_system"
        assert fuel_msg.topic == MessageTopic.FUEL_STATE
        assert "total_fuel" in fuel_msg.data
        assert "fuel_flow" in fuel_msg.data
        assert "fuel_available" in fuel_msg.data

        # Second message should be SYSTEM_STATE
        system_msg = calls[1][0][0]
        assert isinstance(system_msg, Message)
        assert system_msg.sender == "simple_fuel_system"
        assert system_msg.topic == MessageTopic.SYSTEM_STATE
        assert "system" in system_msg.data
        assert system_msg.data["system"] == "fuel"


class TestSimpleFuelSystemTotalFuel:
    """Test total fuel calculation."""

    def test_total_fuel_both_tanks_full(self) -> None:
        """Test total fuel when both tanks are full."""
        fuel = SimpleFuelSystem()

        total = fuel._get_total_fuel()
        assert total == pytest.approx(52.0)  # 26 + 26

    def test_total_fuel_partially_empty(self) -> None:
        """Test total fuel with partial tanks."""
        fuel = SimpleFuelSystem()
        fuel.left_tank_quantity = 10.0
        fuel.right_tank_quantity = 15.0

        total = fuel._get_total_fuel()
        assert total == pytest.approx(25.0)

    def test_total_fuel_both_tanks_empty(self) -> None:
        """Test total fuel when both tanks are empty."""
        fuel = SimpleFuelSystem()
        fuel.left_tank_quantity = 0.0
        fuel.right_tank_quantity = 0.0

        total = fuel._get_total_fuel()
        assert total == pytest.approx(0.0)

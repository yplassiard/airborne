"""Unit tests for SimpleFuelSystem plugin.

Tests fuel system initialization, fuel consumption, pump operation,
and message propagation to ensure proper integration with other systems.
"""

import pytest

from airborne.core.event_bus import EventBus
from airborne.core.messaging import MessageQueue, MessageTopic
from airborne.core.plugin import PluginContext
from airborne.plugins.systems.simple_fuel_plugin import SimpleFuelSystem


@pytest.fixture
def event_bus():
    """Provide a fresh EventBus for each test."""
    return EventBus()


@pytest.fixture
def message_queue():
    """Provide a fresh MessageQueue for each test."""
    return MessageQueue()


@pytest.fixture
def plugin_context(event_bus, message_queue):
    """Provide a PluginContext for testing."""
    context = PluginContext(
        event_bus=event_bus,
        message_queue=message_queue,
        config={},
        plugin_registry=None,
    )
    return context


@pytest.fixture
def fuel_system(plugin_context):
    """Provide an initialized SimpleFuelSystem."""
    system = SimpleFuelSystem()
    system.initialize(plugin_context)
    return system


class TestSimpleFuelSystemInitialization:
    """Test fuel system initialization and configuration."""

    def test_initialization_with_default_config(self, plugin_context):
        """Test fuel system initializes with default values."""
        system = SimpleFuelSystem()
        system.initialize(plugin_context)

        assert system.left_tank_capacity == 26.0
        assert system.right_tank_capacity == 26.0
        assert system.left_tank_quantity == 26.0  # Start full
        assert system.right_tank_quantity == 26.0
        assert system.fuel_selector == "both"
        assert system.fuel_pressure == 2.5  # Gravity feed when selector is "both"
        assert system.fuel_flow == 0.0  # No engine demand yet

    def test_initialization_with_custom_config(self, event_bus, message_queue):
        """Test fuel system initializes with custom configuration."""
        custom_config = {
            "left_tank_capacity": 30.0,
            "right_tank_capacity": 30.0,
            "unusable_fuel": 3.0,
            "fuel_selector": "left",
        }
        context = PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config=custom_config,
            plugin_registry=None,
        )

        system = SimpleFuelSystem()
        system.initialize(context)

        assert system.left_tank_capacity == 30.0
        assert system.right_tank_capacity == 30.0
        assert system.left_tank_quantity == 30.0
        assert system.right_tank_quantity == 30.0
        assert system.unusable_fuel == 3.0
        assert system.fuel_selector == "left"

    def test_initial_state_message_published(self, event_bus, message_queue):
        """Test fuel system publishes initial state immediately after initialization."""
        messages_received = []

        def capture_message(msg):
            messages_received.append(msg)

        # Subscribe before initializing
        message_queue.subscribe(MessageTopic.SYSTEM_STATE, capture_message)

        context = PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={},
            plugin_registry=None,
        )

        system = SimpleFuelSystem()
        system.initialize(context)

        # Process messages
        message_queue.process()

        # Should have received initial state message
        assert len(messages_received) > 0

        # Find the SYSTEM_STATE message with system="fuel"
        fuel_messages = [
            msg
            for msg in messages_received
            if msg.topic == MessageTopic.SYSTEM_STATE and msg.data.get("system") == "fuel"
        ]

        assert len(fuel_messages) == 1
        fuel_msg = fuel_messages[0]

        # Verify initial fuel state
        assert fuel_msg.data["total_quantity_gallons"] == 52.0  # 26 + 26
        assert fuel_msg.data["time_remaining_minutes"] == 0.0  # No fuel flow yet
        assert fuel_msg.sender == "simple_fuel_system"

    def test_initial_fuel_state_message_published(self, event_bus, message_queue):
        """Test fuel system publishes FUEL_STATE message with fuel_available flag."""
        messages_received = []

        def capture_message(msg):
            messages_received.append(msg)

        # Subscribe before initializing
        message_queue.subscribe(MessageTopic.FUEL_STATE, capture_message)

        context = PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={},
            plugin_registry=None,
        )

        system = SimpleFuelSystem()
        system.initialize(context)

        # Process messages
        message_queue.process()

        # Should have received initial FUEL_STATE message
        assert len(messages_received) > 0

        fuel_msg = messages_received[0]
        assert fuel_msg.topic == MessageTopic.FUEL_STATE
        assert fuel_msg.data["total_fuel"] == 52.0
        assert fuel_msg.data["fuel_available"] is True  # Fuel is available
        assert fuel_msg.data["fuel_pressure"] == 2.5  # Gravity feed


class TestFuelAvailability:
    """Test fuel availability logic for engine starting."""

    def test_fuel_available_with_both_selector(self, fuel_system):
        """Test fuel is available when selector is 'both' and tanks have fuel."""
        fuel_system.fuel_selector = "both"
        fuel_system.left_tank_quantity = 10.0
        fuel_system.right_tank_quantity = 10.0

        assert fuel_system._is_fuel_available() is True

    def test_fuel_not_available_when_selector_off(self, fuel_system):
        """Test fuel is not available when selector is 'off'."""
        fuel_system.fuel_selector = "off"
        fuel_system.left_tank_quantity = 26.0
        fuel_system.right_tank_quantity = 26.0

        assert fuel_system._is_fuel_available() is False

    def test_fuel_not_available_when_tanks_empty(self, fuel_system):
        """Test fuel is not available when tanks are below unusable fuel level."""
        fuel_system.fuel_selector = "both"
        fuel_system.left_tank_quantity = 1.0  # Below unusable_fuel (2.0)
        fuel_system.right_tank_quantity = 1.0

        assert fuel_system._is_fuel_available() is False

    def test_fuel_available_with_left_selector_only(self, fuel_system):
        """Test fuel is available when only left tank has fuel and left selector."""
        fuel_system.fuel_selector = "left"
        fuel_system.left_tank_quantity = 10.0
        fuel_system.right_tank_quantity = 0.0

        assert fuel_system._is_fuel_available() is True

    def test_fuel_not_available_with_wrong_selector(self, fuel_system):
        """Test fuel is not available when selector doesn't match fuel location."""
        fuel_system.fuel_selector = "right"
        fuel_system.left_tank_quantity = 26.0
        fuel_system.right_tank_quantity = 0.0

        assert fuel_system._is_fuel_available() is False


class TestFuelConsumption:
    """Test fuel consumption based on engine demand."""

    def test_no_consumption_when_selector_off(self, fuel_system):
        """Test no fuel is consumed when selector is off."""
        fuel_system.fuel_selector = "off"
        fuel_system._engine_fuel_demand = 10.0  # Engine wants fuel

        initial_left = fuel_system.left_tank_quantity
        initial_right = fuel_system.right_tank_quantity

        fuel_system.update(1.0)  # Update for 1 second

        assert fuel_system.left_tank_quantity == initial_left
        assert fuel_system.right_tank_quantity == initial_right
        assert fuel_system.fuel_flow == 0.0

    def test_consumption_from_both_tanks(self, fuel_system):
        """Test fuel is consumed equally from both tanks when selector is 'both'."""
        fuel_system.fuel_selector = "both"
        fuel_system._engine_fuel_demand = 9.0  # 9 GPH

        initial_total = fuel_system._get_total_fuel()

        # Run for 1 hour (3600 seconds)
        for _ in range(3600):
            fuel_system.update(1.0)

        # Should have consumed 9 gallons total (4.5 from each tank)
        final_total = fuel_system._get_total_fuel()
        consumed = initial_total - final_total

        assert abs(consumed - 9.0) < 0.1  # Within 0.1 gallon tolerance
        # Both tanks should have consumed roughly equally
        left_consumed = 26.0 - fuel_system.left_tank_quantity
        right_consumed = 26.0 - fuel_system.right_tank_quantity
        assert abs(left_consumed - right_consumed) < 0.1

    def test_consumption_from_single_tank(self, fuel_system):
        """Test fuel is consumed from selected tank only."""
        fuel_system.fuel_selector = "left"
        fuel_system._engine_fuel_demand = 5.0  # 5 GPH

        initial_right = fuel_system.right_tank_quantity

        # Run for 1 hour
        for _ in range(3600):
            fuel_system.update(1.0)

        # Right tank should be unchanged
        assert fuel_system.right_tank_quantity == initial_right

        # Left tank should have consumed ~5 gallons
        left_consumed = 26.0 - fuel_system.left_tank_quantity
        assert abs(left_consumed - 5.0) < 0.1

    def test_fuel_does_not_go_negative(self, fuel_system):
        """Test fuel quantity never goes below zero."""
        fuel_system.fuel_selector = "left"
        fuel_system.left_tank_quantity = 1.0  # Only 1 gallon
        fuel_system._engine_fuel_demand = 100.0  # Huge demand

        # Run for 1 hour
        for _ in range(3600):
            fuel_system.update(1.0)

        assert fuel_system.left_tank_quantity >= 0.0


class TestFuelPressure:
    """Test fuel pressure based on pumps and fuel availability."""

    def test_pressure_with_pump_on(self, fuel_system):
        """Test fuel pressure when pump is on."""
        fuel_system.fuel_selector = "both"
        fuel_system.left_pump_on = True
        fuel_system._update_fuel_pressure()

        assert fuel_system.fuel_pressure == 4.5  # Pump pressure

    def test_pressure_with_gravity_feed_only(self, fuel_system):
        """Test fuel pressure with gravity feed (no pump)."""
        fuel_system.fuel_selector = "both"
        fuel_system.left_pump_on = False
        fuel_system.right_pump_on = False
        fuel_system._update_fuel_pressure()

        assert fuel_system.fuel_pressure == 2.5  # Gravity pressure

    def test_no_pressure_when_selector_off(self, fuel_system):
        """Test no fuel pressure when selector is off."""
        fuel_system.fuel_selector = "off"
        fuel_system.left_pump_on = True  # Even with pump on
        fuel_system._update_fuel_pressure()

        assert fuel_system.fuel_pressure == 0.0

    def test_no_pressure_when_tanks_empty(self, fuel_system):
        """Test no fuel pressure when tanks are empty."""
        fuel_system.fuel_selector = "both"
        fuel_system.left_tank_quantity = 0.0
        fuel_system.right_tank_quantity = 0.0
        fuel_system.left_pump_on = True
        fuel_system._update_fuel_pressure()

        assert fuel_system.fuel_pressure == 0.0


class TestFuelSystemMessages:
    """Test message handling and publishing."""

    def test_handles_engine_fuel_demand(self, fuel_system):
        """Test fuel system responds to engine fuel demand messages."""
        from airborne.core.messaging import Message, MessagePriority

        # Send ENGINE_STATE message with fuel_flow
        fuel_system.context.message_queue.publish(
            Message(
                sender="engine",
                recipients=["*"],
                topic=MessageTopic.ENGINE_STATE,
                data={"fuel_flow": 8.5},
                priority=MessagePriority.NORMAL,
            )
        )
        # Process the message
        fuel_system.context.message_queue.process()

        assert fuel_system._engine_fuel_demand == 8.5

    def test_handles_fuel_selector_change(self, fuel_system):
        """Test fuel system responds to fuel selector messages."""
        from airborne.core.messaging import Message, MessagePriority

        # Send FUEL_STATE message to change selector
        fuel_system.context.message_queue.publish(
            Message(
                sender="panel",
                recipients=["*"],
                topic=MessageTopic.FUEL_STATE,
                data={"fuel_selector": "LEFT"},  # Uppercase should work
                priority=MessagePriority.NORMAL,
            )
        )
        # Process the message
        fuel_system.context.message_queue.process()

        assert fuel_system.fuel_selector == "left"

    def test_handles_pump_control(self, fuel_system):
        """Test fuel system responds to pump control messages."""
        from airborne.core.messaging import Message, MessagePriority

        # Send FUEL_STATE message to turn on left pump
        fuel_system.context.message_queue.publish(
            Message(
                sender="panel",
                recipients=["*"],
                topic=MessageTopic.FUEL_STATE,
                data={"left_pump": True, "right_pump": False},
                priority=MessagePriority.NORMAL,
            )
        )
        # Process the message
        fuel_system.context.message_queue.process()

        assert fuel_system.left_pump_on is True
        assert fuel_system.right_pump_on is False

    def test_publishes_state_on_update(self, fuel_system):
        """Test fuel system publishes state during update."""
        messages_received = []

        def capture_message(msg):
            if msg.data.get("system") == "fuel":
                messages_received.append(msg)

        fuel_system.context.message_queue.subscribe(MessageTopic.SYSTEM_STATE, capture_message)

        # Update fuel system
        fuel_system.update(0.016)

        # Process messages
        fuel_system.context.message_queue.process()

        assert len(messages_received) > 0

        fuel_msg = messages_received[0]
        assert "total_quantity_gallons" in fuel_msg.data
        assert "time_remaining_minutes" in fuel_msg.data

    def test_time_remaining_calculation_with_fuel_flow(self, fuel_system):
        """Test time remaining is calculated correctly when engine is running."""
        # Set engine fuel demand to 10 GPH
        fuel_system._engine_fuel_demand = 10.0
        fuel_system.fuel_selector = "both"

        # Update to apply fuel flow
        fuel_system._calculate_fuel_flow()

        messages_received = []

        def capture_message(msg):
            if msg.data.get("system") == "fuel":
                messages_received.append(msg)

        fuel_system.context.message_queue.subscribe(MessageTopic.SYSTEM_STATE, capture_message)

        # Publish state
        fuel_system._publish_state()
        fuel_system.context.message_queue.process()

        assert len(messages_received) >= 1
        fuel_msg = messages_received[-1]  # Get the most recent message

        # With 52 gallons and 10 GPH flow, should have ~312 minutes (5.2 hours)
        expected_minutes = (52.0 / 10.0) * 60.0  # 312 minutes
        assert abs(fuel_msg.data["time_remaining_minutes"] - expected_minutes) < 1.0


class TestEngineStartingWithFuel:
    """Test that engine can verify fuel availability for starting."""

    def test_fuel_available_message_sent_on_initialization(self, event_bus, message_queue):
        """Test FUEL_STATE message includes fuel_available flag."""
        messages_received = []

        def capture_message(msg):
            messages_received.append(msg)

        message_queue.subscribe(MessageTopic.FUEL_STATE, capture_message)

        context = PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={},
            plugin_registry=None,
        )

        system = SimpleFuelSystem()
        system.initialize(context)

        message_queue.process()

        # Find FUEL_STATE message
        fuel_state_msgs = [msg for msg in messages_received if msg.topic == MessageTopic.FUEL_STATE]
        assert len(fuel_state_msgs) == 1

        fuel_msg = fuel_state_msgs[0]
        assert "fuel_available" in fuel_msg.data
        assert fuel_msg.data["fuel_available"] is True

    def test_fuel_not_available_when_empty_tanks(self, fuel_system):
        """Test fuel_available flag is False when tanks are empty."""
        # Empty both tanks
        fuel_system.left_tank_quantity = 0.0
        fuel_system.right_tank_quantity = 0.0

        messages_received = []

        def capture_message(msg):
            messages_received.append(msg)

        fuel_system.context.message_queue.subscribe(MessageTopic.FUEL_STATE, capture_message)

        fuel_system._publish_state()
        fuel_system.context.message_queue.process()

        fuel_msg = [msg for msg in messages_received if msg.topic == MessageTopic.FUEL_STATE][
            -1
        ]  # Get the most recent message
        assert fuel_msg.data["fuel_available"] is False


class TestFuelSystemShutdown:
    """Test fuel system shutdown behavior."""

    def test_shutdown_closes_selector(self, fuel_system):
        """Test fuel system closes selector on shutdown."""
        fuel_system.fuel_selector = "both"
        fuel_system.left_pump_on = True
        fuel_system.right_pump_on = True

        fuel_system.shutdown()

        assert fuel_system.fuel_selector == "off"
        assert fuel_system.left_pump_on is False
        assert fuel_system.right_pump_on is False
        assert fuel_system.fuel_pressure == 0.0

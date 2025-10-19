"""Tests for simple electrical system plugin."""

from unittest.mock import Mock

import pytest

from airborne.core.event_bus import EventBus
from airborne.core.messaging import Message, MessageTopic
from airborne.core.plugin import PluginContext, PluginType
from airborne.plugins.systems.simple_electrical_plugin import (
    ElectricalStateEvent,
    SimpleElectricalSystem,
)


class TestSimpleElectricalSystemMetadata:
    """Test electrical system plugin metadata."""

    def test_get_metadata(self) -> None:
        """Test getting plugin metadata."""
        electrical = SimpleElectricalSystem()
        metadata = electrical.get_metadata()

        assert metadata.name == "simple_electrical_system"
        assert metadata.version == "1.0.0"
        assert metadata.plugin_type == PluginType.AIRCRAFT_SYSTEM
        assert "electrical" in metadata.provides
        assert "power" in metadata.provides
        assert "simple_piston_engine" in metadata.dependencies
        assert metadata.optional is False


class TestSimpleElectricalSystemInitialization:
    """Test electrical system initialization."""

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
        """Test electrical system initialization."""
        electrical = SimpleElectricalSystem()
        electrical.initialize(context)

        assert electrical.context == context
        # Should subscribe to three topics: ENGINE_STATE, ELECTRICAL_STATE, and electrical.master_switch
        assert context.message_queue.subscribe.call_count == 3

    def test_initial_state(self) -> None:
        """Test initial electrical system state."""
        electrical = SimpleElectricalSystem()

        assert electrical.battery_voltage == 12.6  # Fully charged
        assert electrical.battery_charge_ah == 35.0  # Full capacity
        assert electrical.alternator_online is False
        assert electrical.battery_master is False
        assert electrical.alternator_switch is False
        assert electrical.bus_voltage == 0.0


class TestSimpleElectricalSystemSwitches:
    """Test electrical system switch handling."""

    @pytest.fixture
    def electrical(self) -> SimpleElectricalSystem:
        """Create electrical system instance."""
        return SimpleElectricalSystem()

    def test_handle_battery_master_message(self, electrical: SimpleElectricalSystem) -> None:
        """Test handling battery master switch message."""
        message = Message(
            sender="test",
            recipients=["simple_electrical_system"],
            topic=MessageTopic.ELECTRICAL_STATE,
            data={"battery_master": True},
        )

        electrical.handle_message(message)
        assert electrical.battery_master is True

        message.data["battery_master"] = False
        electrical.handle_message(message)
        assert electrical.battery_master is False

    def test_handle_alternator_switch_message(self, electrical: SimpleElectricalSystem) -> None:
        """Test handling alternator switch message."""
        message = Message(
            sender="test",
            recipients=["simple_electrical_system"],
            topic=MessageTopic.ELECTRICAL_STATE,
            data={"alternator_switch": True},
        )

        electrical.handle_message(message)
        assert electrical.alternator_switch is True


class TestSimpleElectricalSystemBattery:
    """Test battery behavior."""

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
    def electrical(self, context: PluginContext) -> SimpleElectricalSystem:
        """Create initialized electrical system."""
        system = SimpleElectricalSystem()
        system.initialize(context)
        return system

    def test_bus_voltage_zero_when_master_off(self, electrical: SimpleElectricalSystem) -> None:
        """Test bus voltage is zero when battery master is off."""
        electrical.battery_master = False
        electrical.update(0.016)

        assert electrical.bus_voltage == 0.0

    def test_bus_voltage_present_when_master_on(self, electrical: SimpleElectricalSystem) -> None:
        """Test bus voltage is present when battery master is on."""
        electrical.battery_master = True
        electrical.update(0.016)

        assert electrical.bus_voltage > 0.0

    def test_battery_discharges_under_load(self, electrical: SimpleElectricalSystem) -> None:
        """Test battery discharges when supplying load."""
        electrical.battery_master = True
        initial_charge = electrical.battery_charge_ah

        # Discharge for 60 seconds
        for _ in range(3600):
            electrical.update(0.016)

        assert electrical.battery_charge_ah < initial_charge

    def test_battery_voltage_drops_under_load(self, electrical: SimpleElectricalSystem) -> None:
        """Test battery voltage drops under load."""
        electrical.battery_master = True
        initial_voltage = electrical.battery_voltage

        # Discharge significantly
        for _ in range(7200):  # ~2 minutes
            electrical.update(0.016)

        assert electrical.battery_voltage < initial_voltage


class TestSimpleElectricalSystemAlternator:
    """Test alternator behavior."""

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
    def electrical(self, context: PluginContext) -> SimpleElectricalSystem:
        """Create initialized electrical system."""
        system = SimpleElectricalSystem()
        system.initialize(context)
        return system

    def test_alternator_offline_when_engine_off(self, electrical: SimpleElectricalSystem) -> None:
        """Test alternator is offline when engine is off."""
        electrical.alternator_switch = True
        electrical._engine_running = False
        electrical._engine_rpm = 0.0

        electrical.update(0.016)

        assert electrical.alternator_online is False
        assert electrical.alternator_current == 0.0

    def test_alternator_offline_when_switch_off(self, electrical: SimpleElectricalSystem) -> None:
        """Test alternator is offline when switch is off."""
        electrical.alternator_switch = False
        electrical._engine_running = True
        electrical._engine_rpm = 2000.0

        electrical.update(0.016)

        assert electrical.alternator_online is False

    def test_alternator_online_with_engine_running(
        self, electrical: SimpleElectricalSystem
    ) -> None:
        """Test alternator comes online with engine running."""
        electrical.battery_master = True
        electrical.alternator_switch = True
        electrical._engine_running = True
        electrical._engine_rpm = 1000.0  # Idle RPM

        electrical.update(0.016)

        assert electrical.alternator_online is True
        assert electrical.alternator_current > 0.0

    def test_alternator_charges_battery(self, electrical: SimpleElectricalSystem) -> None:
        """Test alternator charges depleted battery."""
        # Deplete battery first
        electrical.battery_master = True
        for _ in range(3600):
            electrical.update(0.016)

        depleted_charge = electrical.battery_charge_ah

        # Now charge with alternator
        electrical.alternator_switch = True
        electrical._engine_running = True
        electrical._engine_rpm = 2000.0

        for _ in range(600):  # ~10 seconds
            electrical.update(0.016)

        assert electrical.battery_charge_ah > depleted_charge

    def test_bus_voltage_regulated_with_alternator(
        self, electrical: SimpleElectricalSystem
    ) -> None:
        """Test bus voltage is regulated to 14V with alternator."""
        electrical.battery_master = True
        electrical.alternator_switch = True
        electrical._engine_running = True
        electrical._engine_rpm = 2000.0

        electrical.update(0.016)

        assert electrical.bus_voltage == pytest.approx(14.0)

    def test_alternator_rpm_scales_with_engine(self, electrical: SimpleElectricalSystem) -> None:
        """Test alternator RPM scales with engine RPM."""
        electrical.alternator_switch = True
        electrical._engine_running = True
        electrical._engine_rpm = 2000.0

        electrical.update(0.016)

        # Alternator spins ~2.5x engine RPM
        assert electrical.alternator_rpm == pytest.approx(5000.0)


class TestSimpleElectricalSystemLoad:
    """Test electrical load calculation."""

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
    def electrical(self, context: PluginContext) -> SimpleElectricalSystem:
        """Create initialized electrical system."""
        system = SimpleElectricalSystem()
        system.initialize(context)
        return system

    def test_base_load_present(self, electrical: SimpleElectricalSystem) -> None:
        """Test base electrical load is present."""
        electrical.update(0.016)

        assert electrical.total_load >= electrical.base_load


class TestSimpleElectricalSystemIntegration:
    """Test electrical system integration with engine."""

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
    def electrical(self, context: PluginContext) -> SimpleElectricalSystem:
        """Create initialized electrical system."""
        system = SimpleElectricalSystem()
        system.initialize(context)
        return system

    def test_receives_engine_state_messages(self, electrical: SimpleElectricalSystem) -> None:
        """Test electrical system receives engine state messages."""
        message = Message(
            sender="simple_piston_engine",
            recipients=["*"],
            topic=MessageTopic.ENGINE_STATE,
            data={"running": True, "rpm": 2000.0},
        )

        electrical.handle_message(message)

        assert electrical._engine_running is True
        assert electrical._engine_rpm == 2000.0

    def test_alternator_responds_to_engine_state(self, electrical: SimpleElectricalSystem) -> None:
        """Test alternator responds to engine running state."""
        electrical.alternator_switch = True

        # Engine off
        engine_msg = Message(
            sender="simple_piston_engine",
            recipients=["*"],
            topic=MessageTopic.ENGINE_STATE,
            data={"running": False, "rpm": 0.0},
        )
        electrical.handle_message(engine_msg)
        electrical.update(0.016)
        assert electrical.alternator_online is False

        # Engine running
        engine_msg.data["running"] = True
        engine_msg.data["rpm"] = 1500.0
        electrical.handle_message(engine_msg)
        electrical.update(0.016)
        assert electrical.alternator_online is True


class TestSimpleElectricalSystemShutdown:
    """Test electrical system shutdown behavior."""

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
    def electrical(self, context: PluginContext) -> SimpleElectricalSystem:
        """Create initialized electrical system."""
        system = SimpleElectricalSystem()
        system.initialize(context)
        return system

    def test_shutdown_turns_off_switches(self, electrical: SimpleElectricalSystem) -> None:
        """Test shutdown turns off all switches."""
        electrical.battery_master = True
        electrical.alternator_switch = True

        electrical.shutdown()

        assert electrical.battery_master is False
        assert electrical.alternator_switch is False
        assert electrical.bus_voltage == 0.0

    def test_shutdown_unsubscribes_from_messages(self, electrical: SimpleElectricalSystem) -> None:
        """Test shutdown cleans up subscriptions."""
        electrical.shutdown()

        # Should unsubscribe from three topics
        assert electrical.context.message_queue.unsubscribe.call_count == 3


class TestSimpleElectricalSystemEventPublishing:
    """Test electrical system event publishing."""

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
    def electrical(self, context: PluginContext) -> SimpleElectricalSystem:
        """Create initialized electrical system."""
        system = SimpleElectricalSystem()
        system.initialize(context)
        return system

    def test_publishes_electrical_state_event(
        self, electrical: SimpleElectricalSystem, event_bus: EventBus
    ) -> None:
        """Test electrical system publishes state events."""
        received_events = []

        def handler(event: ElectricalStateEvent) -> None:
            received_events.append(event)

        event_bus.subscribe(ElectricalStateEvent, handler)

        electrical.update(0.016)

        assert len(received_events) == 1
        assert isinstance(received_events[0], ElectricalStateEvent)
        assert received_events[0].battery_voltage == electrical.battery_voltage
        assert received_events[0].bus_voltage == electrical.bus_voltage

    def test_publishes_electrical_state_message(self, electrical: SimpleElectricalSystem) -> None:
        """Test electrical system publishes state messages."""
        # Clear the mock calls from initialization
        electrical.context.message_queue.publish.reset_mock()

        electrical.update(0.016)

        # Should publish two messages (ELECTRICAL_STATE and SYSTEM_STATE)
        assert electrical.context.message_queue.publish.call_count == 2

        # Check both messages
        calls = electrical.context.message_queue.publish.call_args_list

        # First message should be ELECTRICAL_STATE
        electrical_msg = calls[0][0][0]
        assert isinstance(electrical_msg, Message)
        assert electrical_msg.sender == "simple_electrical_system"
        assert electrical_msg.topic == MessageTopic.ELECTRICAL_STATE
        assert "battery_voltage" in electrical_msg.data
        assert "bus_voltage" in electrical_msg.data
        assert "power_available" in electrical_msg.data

        # Second message should be SYSTEM_STATE
        system_msg = calls[1][0][0]
        assert isinstance(system_msg, Message)
        assert system_msg.sender == "simple_electrical_system"
        assert system_msg.topic == MessageTopic.SYSTEM_STATE
        assert "system" in system_msg.data
        assert system_msg.data["system"] == "electrical"


class TestSimpleElectricalSystemBatteryPercentage:
    """Test battery percentage calculation."""

    def test_battery_percentage_full(self) -> None:
        """Test battery percentage when fully charged."""
        electrical = SimpleElectricalSystem()
        electrical.battery_charge_ah = 35.0

        percentage = electrical._get_battery_percentage()
        assert percentage == pytest.approx(100.0)

    def test_battery_percentage_half(self) -> None:
        """Test battery percentage at 50% charge."""
        electrical = SimpleElectricalSystem()
        electrical.battery_charge_ah = 17.5

        percentage = electrical._get_battery_percentage()
        assert percentage == pytest.approx(50.0)

    def test_battery_percentage_empty(self) -> None:
        """Test battery percentage when empty."""
        electrical = SimpleElectricalSystem()
        electrical.battery_charge_ah = 0.0

        percentage = electrical._get_battery_percentage()
        assert percentage == pytest.approx(0.0)

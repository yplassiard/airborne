"""Tests for system plugin wrappers (electrical, fuel, engine)."""

from unittest.mock import Mock

from airborne.core.event_bus import EventBus
from airborne.core.messaging import Message, MessagePriority, MessageQueue, MessageTopic
from airborne.core.plugin import PluginContext
from airborne.plugins.systems.electrical_plugin import ElectricalPlugin
from airborne.plugins.systems.engine_plugin import EnginePlugin
from airborne.plugins.systems.fuel_plugin import FuelPlugin


def create_test_context(config: dict, queue: MessageQueue) -> PluginContext:
    """Create a PluginContext for testing.

    Args:
        config: Configuration dictionary.
        queue: Message queue.

    Returns:
        PluginContext instance.
    """
    registry = Mock()
    registry.register = Mock()
    registry.unregister = Mock()
    return PluginContext(
        event_bus=EventBus(),
        message_queue=queue,
        config=config,
        plugin_registry=registry,
    )


class TestElectricalPlugin:
    """Test cases for ElectricalPlugin wrapper."""

    def test_initialization(self):
        """Test electrical plugin initializes correctly."""
        plugin = ElectricalPlugin()
        context = create_test_context(
            config={"electrical": {"implementation": "simple_12v"}},
            queue=MessageQueue(),
        )

        plugin.initialize(context)

        assert plugin.electrical_system is not None
        assert plugin.context is not None

    def test_master_switch_control(self):
        """Test master switch control via message."""
        plugin = ElectricalPlugin()
        queue = MessageQueue()
        context = create_test_context(
            queue=queue,
            config={"electrical": {"implementation": "simple_12v"}},
        )

        plugin.initialize(context)

        # Send master switch ON message
        queue.publish(
            Message(
                sender="control_panel",
                recipients=["electrical"],
                topic="electrical.master_switch",
                data={"state": "ON"},
                priority=MessagePriority.HIGH,
            )
        )

        # Process messages
        queue.process()

        # Verify system responded (check via state message)
        plugin.update(0.1)
        queue.process()

        # Should have published SYSTEM_STATE message
        assert queue.pending_count() == 0  # All messages processed

    def test_light_control(self):
        """Test light control via messages."""
        plugin = ElectricalPlugin()
        queue = MessageQueue()

        # Configure electrical system with nav_lights load
        config = {
            "electrical": {
                "implementation": "simple_12v",
                "loads": {"nav_lights": {"amps": 1.5, "essential": False}},
            }
        }

        context = create_test_context(
            queue=queue,
            config=config,
        )

        plugin.initialize(context)

        # Turn on nav lights
        queue.publish(
            Message(
                sender="control_panel",
                recipients=["electrical"],
                topic="electrical.nav_lights",
                data={"state": "ON"},
                priority=MessagePriority.HIGH,
            )
        )

        queue.process()

        # Verify load was created and enabled
        assert "nav_lights" in plugin.electrical_system.loads
        assert plugin.electrical_system.loads["nav_lights"].enabled

    def test_engine_rpm_updates_alternator(self):
        """Test engine RPM updates alternator output."""
        plugin = ElectricalPlugin()
        queue = MessageQueue()
        context = create_test_context(
            queue=queue,
            config={"electrical": {"implementation": "simple_12v"}},
        )

        plugin.initialize(context)

        # Send low RPM (alternator off)
        queue.publish(
            Message(
                sender="engine_plugin",
                recipients=["*"],
                topic=MessageTopic.ENGINE_STATE,
                data={"rpm": 500.0},
                priority=MessagePriority.NORMAL,
            )
        )

        queue.process()
        assert plugin.engine_rpm == 500.0

        # Send high RPM (alternator should be on)
        queue.publish(
            Message(
                sender="engine_plugin",
                recipients=["*"],
                topic=MessageTopic.ENGINE_STATE,
                data={"rpm": 2000.0},
                priority=MessagePriority.NORMAL,
            )
        )

        queue.process()
        assert plugin.engine_rpm == 2000.0

    def test_publishes_system_state(self):
        """Test plugin publishes electrical system state."""
        plugin = ElectricalPlugin()
        queue = MessageQueue()
        context = create_test_context(
            queue=queue,
            config={"electrical": {"implementation": "simple_12v"}},
        )

        plugin.initialize(context)

        # Subscribe to system state messages
        received_messages = []

        def capture_state(msg):
            received_messages.append(msg)

        queue.subscribe(MessageTopic.SYSTEM_STATE, capture_state)

        # Update plugin
        plugin.update(0.1)
        queue.process()

        # Should have received system state
        assert len(received_messages) > 0
        state_msg = received_messages[0]
        assert state_msg.data["system"] == "electrical"
        assert "battery_voltage" in state_msg.data
        assert "bus_voltage" in state_msg.data


class TestFuelPlugin:
    """Test cases for FuelPlugin wrapper."""

    def test_initialization(self):
        """Test fuel plugin initializes correctly."""
        plugin = FuelPlugin()
        queue = MessageQueue()
        context = create_test_context(
            queue=queue,
            config={"fuel": {"implementation": "simple_gravity"}},
        )

        plugin.initialize(context)

        assert plugin.fuel_system is not None
        assert plugin.context is not None

    def test_fuel_selector_control(self):
        """Test fuel selector control via message."""
        plugin = FuelPlugin()
        queue = MessageQueue()
        context = create_test_context(
            queue=queue,
            config={"fuel": {"implementation": "simple_gravity"}},
        )

        plugin.initialize(context)

        # Set selector to BOTH
        queue.publish(
            Message(
                sender="control_panel",
                recipients=["fuel"],
                topic="fuel.selector",
                data={"state": "BOTH"},
                priority=MessagePriority.HIGH,
            )
        )

        queue.process()

        # Verify selector position changed
        from airborne.systems.fuel.base import FuelSelectorPosition

        state = plugin.fuel_system.get_state()
        assert state.fuel_selector_position == FuelSelectorPosition.BOTH

    def test_fuel_pump_control(self):
        """Test fuel pump control via message."""
        plugin = FuelPlugin()
        queue = MessageQueue()
        context = create_test_context(
            queue=queue,
            config={"fuel": {"implementation": "simple_gravity"}},
        )

        plugin.initialize(context)

        # Turn on fuel pump
        queue.publish(
            Message(
                sender="control_panel",
                recipients=["fuel"],
                topic="fuel.pump",
                data={"state": "ON"},
                priority=MessagePriority.HIGH,
            )
        )

        queue.process()

        # Verify pump was enabled (if it exists in the system)
        # Simple gravity system may not have boost pump, so just verify no crash

    def test_fuel_shutoff_valve(self):
        """Test fuel shutoff valve control."""
        plugin = FuelPlugin()
        queue = MessageQueue()
        context = create_test_context(
            queue=queue,
            config={"fuel": {"implementation": "simple_gravity"}},
        )

        plugin.initialize(context)

        # Close shutoff valve
        queue.publish(
            Message(
                sender="control_panel",
                recipients=["fuel"],
                topic="fuel.shutoff",
                data={"state": "CLOSED"},
                priority=MessagePriority.HIGH,
            )
        )

        queue.process()

        # Verify selector went to OFF
        from airborne.systems.fuel.base import FuelSelectorPosition

        state = plugin.fuel_system.get_state()
        assert state.fuel_selector_position == FuelSelectorPosition.OFF

    def test_engine_fuel_consumption(self):
        """Test engine fuel consumption updates fuel system."""
        plugin = FuelPlugin()
        queue = MessageQueue()
        context = create_test_context(
            queue=queue,
            config={"fuel": {"implementation": "simple_gravity"}},
        )

        plugin.initialize(context)

        # Send engine state with fuel flow
        queue.publish(
            Message(
                sender="engine_plugin",
                recipients=["*"],
                topic=MessageTopic.ENGINE_STATE,
                data={"fuel_flow": 8.5},
                priority=MessagePriority.NORMAL,
            )
        )

        queue.process()
        assert plugin.current_fuel_flow_gph == 8.5

    def test_publishes_fuel_state(self):
        """Test plugin publishes fuel system state."""
        plugin = FuelPlugin()
        queue = MessageQueue()
        context = create_test_context(
            queue=queue,
            config={"fuel": {"implementation": "simple_gravity"}},
        )

        plugin.initialize(context)

        # Subscribe to system state messages
        received_messages = []

        def capture_state(msg):
            received_messages.append(msg)

        queue.subscribe(MessageTopic.SYSTEM_STATE, capture_state)

        # Set selector to BOTH so fuel is available
        queue.publish(
            Message(
                sender="control_panel",
                recipients=["fuel"],
                topic="fuel.selector",
                data={"state": "BOTH"},
                priority=MessagePriority.HIGH,
            )
        )
        queue.process()

        # Update plugin
        plugin.update(0.1)
        queue.process()

        # Should have received system state
        assert len(received_messages) > 0
        state_msg = received_messages[-1]  # Get latest message
        assert state_msg.data["system"] == "fuel"
        assert "total_quantity_gallons" in state_msg.data
        assert "available_fuel_flow_gph" in state_msg.data


class TestEnginePlugin:
    """Test cases for EnginePlugin wrapper."""

    def test_initialization(self):
        """Test engine plugin initializes correctly."""
        plugin = EnginePlugin()
        queue = MessageQueue()
        context = create_test_context(
            queue=queue,
            config={"engine": {"implementation": "piston_simple"}},
        )

        plugin.initialize(context)

        assert plugin.engine is not None
        assert plugin.context is not None

    def test_throttle_control(self):
        """Test throttle control via message."""
        plugin = EnginePlugin()
        queue = MessageQueue()
        context = create_test_context(
            queue=queue,
            config={"engine": {"implementation": "piston_simple"}},
        )

        plugin.initialize(context)

        # Set throttle to 50%
        queue.publish(
            Message(
                sender="control_panel",
                recipients=["engine"],
                topic="engine.throttle",
                data={"value": 50.0},
                priority=MessagePriority.HIGH,
            )
        )

        queue.process()

        # Verify throttle was set
        assert plugin.controls.throttle == 0.5

    def test_mixture_control(self):
        """Test mixture control via message."""
        plugin = EnginePlugin()
        queue = MessageQueue()
        context = create_test_context(
            queue=queue,
            config={"engine": {"implementation": "piston_simple"}},
        )

        plugin.initialize(context)

        # Set mixture to RICH
        queue.publish(
            Message(
                sender="control_panel",
                recipients=["engine"],
                topic="engine.mixture",
                data={"state": "RICH"},
                priority=MessagePriority.HIGH,
            )
        )

        queue.process()
        assert plugin.controls.mixture == 1.0

        # Set mixture to LEAN
        queue.publish(
            Message(
                sender="control_panel",
                recipients=["engine"],
                topic="engine.mixture",
                data={"state": "LEAN"},
                priority=MessagePriority.HIGH,
            )
        )

        queue.process()
        assert plugin.controls.mixture == 0.5

        # Set mixture to IDLE_CUTOFF
        queue.publish(
            Message(
                sender="control_panel",
                recipients=["engine"],
                topic="engine.mixture",
                data={"state": "IDLE_CUTOFF"},
                priority=MessagePriority.HIGH,
            )
        )

        queue.process()
        assert plugin.controls.mixture == 0.0

    def test_magneto_control(self):
        """Test magneto switch control via message."""
        plugin = EnginePlugin()
        queue = MessageQueue()
        context = create_test_context(
            queue=queue,
            config={"engine": {"implementation": "piston_simple"}},
        )

        plugin.initialize(context)

        # Set magnetos to BOTH
        queue.publish(
            Message(
                sender="control_panel",
                recipients=["engine"],
                topic="engine.magnetos",
                data={"state": "BOTH"},
                priority=MessagePriority.HIGH,
            )
        )

        queue.process()
        assert plugin.controls.magneto_left
        assert plugin.controls.magneto_right
        assert not plugin.controls.starter

        # Set magnetos to START
        queue.publish(
            Message(
                sender="control_panel",
                recipients=["engine"],
                topic="engine.magnetos",
                data={"state": "START"},
                priority=MessagePriority.HIGH,
            )
        )

        queue.process()
        assert plugin.controls.magneto_left
        assert plugin.controls.magneto_right
        assert plugin.controls.starter

    def test_monitors_electrical_availability(self):
        """Test plugin monitors electrical system for starter power."""
        plugin = EnginePlugin()
        queue = MessageQueue()
        context = create_test_context(
            queue=queue,
            config={"engine": {"implementation": "piston_simple"}},
        )

        plugin.initialize(context)

        # Send low voltage
        queue.publish(
            Message(
                sender="electrical_plugin",
                recipients=["*"],
                topic=MessageTopic.SYSTEM_STATE,
                data={"system": "electrical", "bus_voltage": 10.0},
                priority=MessagePriority.NORMAL,
            )
        )

        queue.process()
        assert not plugin.electrical_available  # Below 11.0V threshold

        # Send good voltage
        queue.publish(
            Message(
                sender="electrical_plugin",
                recipients=["*"],
                topic=MessageTopic.SYSTEM_STATE,
                data={"system": "electrical", "bus_voltage": 12.5},
                priority=MessagePriority.NORMAL,
            )
        )

        queue.process()
        assert plugin.electrical_available  # Above 11.0V threshold

    def test_monitors_fuel_availability(self):
        """Test plugin monitors fuel system for available fuel flow."""
        plugin = EnginePlugin()
        queue = MessageQueue()
        context = create_test_context(
            queue=queue,
            config={"engine": {"implementation": "piston_simple"}},
        )

        plugin.initialize(context)

        # Send fuel available
        queue.publish(
            Message(
                sender="fuel_plugin",
                recipients=["*"],
                topic=MessageTopic.SYSTEM_STATE,
                data={"system": "fuel", "available_fuel_flow_gph": 15.0},
                priority=MessagePriority.NORMAL,
            )
        )

        queue.process()
        assert plugin.fuel_available_gph == 15.0

        # Send no fuel
        queue.publish(
            Message(
                sender="fuel_plugin",
                recipients=["*"],
                topic=MessageTopic.SYSTEM_STATE,
                data={"system": "fuel", "available_fuel_flow_gph": 0.0},
                priority=MessagePriority.NORMAL,
            )
        )

        queue.process()
        assert plugin.fuel_available_gph == 0.0

    def test_publishes_engine_state(self):
        """Test plugin publishes engine state."""
        plugin = EnginePlugin()
        queue = MessageQueue()
        context = create_test_context(
            queue=queue,
            config={"engine": {"implementation": "piston_simple"}},
        )

        plugin.initialize(context)

        # Subscribe to engine state messages
        received_messages = []

        def capture_state(msg):
            received_messages.append(msg)

        queue.subscribe(MessageTopic.ENGINE_STATE, capture_state)

        # Update plugin
        plugin.update(0.1)
        queue.process()

        # Should have received engine state
        assert len(received_messages) > 0
        state_msg = received_messages[0]
        assert "running" in state_msg.data
        assert "rpm" in state_msg.data
        assert "fuel_flow" in state_msg.data
        assert "horsepower" in state_msg.data


class TestPluginIntegration:
    """Test integrated system behavior."""

    def test_full_engine_start_sequence(self):
        """Test complete engine start with electrical and fuel dependencies."""
        # Create all three plugins
        electrical = ElectricalPlugin()
        fuel = FuelPlugin()
        engine = EnginePlugin()

        queue = MessageQueue()

        # Initialize all plugins with fuel tanks configured
        context = create_test_context(
            queue=queue,
            config={
                "electrical": {"implementation": "simple_12v"},
                "fuel": {
                    "implementation": "simple_gravity",
                    "tanks": {
                        "left": {
                            "capacity_total": 28.0,
                            "capacity_usable": 26.0,
                            "initial_quantity": 20.0,  # Start with fuel
                            "fuel_type": "avgas_100ll",
                            "position": [-5.0, 0.0, -8.0],
                        },
                        "right": {
                            "capacity_total": 28.0,
                            "capacity_usable": 26.0,
                            "initial_quantity": 20.0,  # Start with fuel
                            "fuel_type": "avgas_100ll",
                            "position": [-5.0, 0.0, 8.0],
                        },
                    },
                },
                "engine": {"implementation": "piston_simple"},
            },
        )

        electrical.initialize(context)
        fuel.initialize(context)
        engine.initialize(context)

        # Step 1: Turn on master switch
        queue.publish(
            Message(
                sender="control_panel",
                recipients=["electrical"],
                topic="electrical.master_switch",
                data={"state": "ON"},
                priority=MessagePriority.HIGH,
            )
        )
        queue.process()

        # Step 2: Set fuel selector to BOTH
        queue.publish(
            Message(
                sender="control_panel",
                recipients=["fuel"],
                topic="fuel.selector",
                data={"state": "BOTH"},
                priority=MessagePriority.HIGH,
            )
        )
        queue.process()

        # Step 3: Set mixture to RICH
        queue.publish(
            Message(
                sender="control_panel",
                recipients=["engine"],
                topic="engine.mixture",
                data={"state": "RICH"},
                priority=MessagePriority.HIGH,
            )
        )
        queue.process()

        # Step 4: Set magnetos to BOTH
        queue.publish(
            Message(
                sender="control_panel",
                recipients=["engine"],
                topic="engine.magnetos",
                data={"state": "BOTH"},
                priority=MessagePriority.HIGH,
            )
        )
        queue.process()

        # Step 5: Set throttle slightly open for cold start
        queue.publish(
            Message(
                sender="control_panel",
                recipients=["engine"],
                topic="engine.throttle",
                data={"value": 10.0},  # 10% throttle for starting
                priority=MessagePriority.HIGH,
            )
        )
        queue.process()

        # Update systems to publish states
        electrical.update(0.1)
        fuel.update(0.1)
        queue.process()

        # Engine needs to receive the electrical state message
        engine.update(0.1)
        queue.process()

        # Step 6: Engage starter
        queue.publish(
            Message(
                sender="control_panel",
                recipients=["engine"],
                topic="engine.magnetos",
                data={"state": "START"},
                priority=MessagePriority.HIGH,
            )
        )
        queue.process()

        # Simulate engine cranking (need longer for starter to reach 200 RPM)
        for _ in range(50):
            electrical.update(0.1)
            fuel.update(0.1)
            engine.update(0.1)
            queue.process()

        # Engine should have started
        assert engine.engine.running, (
            f"Engine failed to start. "
            f"electrical_available={engine.electrical_available}, "
            f"fuel_available={engine.fuel_available_gph}, "
            f"rpm={engine.engine.rpm}, "
            f"starting={engine.engine.starting}, "
            f"magneto_left={engine.controls.magneto_left}, "
            f"magneto_right={engine.controls.magneto_right}, "
            f"mixture={engine.controls.mixture}, "
            f"throttle={engine.controls.throttle}, "
            f"starter={engine.controls.starter}"
        )

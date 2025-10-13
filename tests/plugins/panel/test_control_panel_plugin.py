"""Tests for control panel plugin."""

from unittest.mock import Mock

import pytest

from airborne.core.event_bus import EventBus
from airborne.core.messaging import MessageTopic
from airborne.core.plugin import PluginContext, PluginType
from airborne.plugins.panel import (
    ControlPanelPlugin,
    ControlType,
    Panel,
    PanelControl,
)


class TestPanelControl:
    """Test PanelControl dataclass."""

    def test_create_control(self) -> None:
        """Test creating a panel control."""
        control = PanelControl(
            id="master_switch",
            name="Master Switch",
            control_type=ControlType.SWITCH,
            states=["OFF", "ON"],
            target_plugin="electrical",
            message_topic="electrical.master_switch",
        )

        assert control.id == "master_switch"
        assert control.name == "Master Switch"
        assert control.control_type == ControlType.SWITCH
        assert control.states == ["OFF", "ON"]
        assert control.current_state_index == 0
        assert control.get_current_state() == "OFF"

    def test_next_state(self) -> None:
        """Test advancing to next state."""
        control = PanelControl(
            id="test",
            name="Test",
            control_type=ControlType.SWITCH,
            states=["OFF", "ON"],
        )

        assert control.get_current_state() == "OFF"
        control.next_state()
        assert control.get_current_state() == "ON"
        control.next_state()  # Wraps around
        assert control.get_current_state() == "OFF"

    def test_previous_state(self) -> None:
        """Test going to previous state."""
        control = PanelControl(
            id="test",
            name="Test",
            control_type=ControlType.SWITCH,
            states=["OFF", "ON"],
            current_state_index=1,
        )

        assert control.get_current_state() == "ON"
        control.previous_state()
        assert control.get_current_state() == "OFF"
        control.previous_state()  # Wraps around
        assert control.get_current_state() == "ON"

    def test_set_state_by_name(self) -> None:
        """Test setting state by name."""
        control = PanelControl(
            id="test",
            name="Test",
            control_type=ControlType.LEVER,
            states=["IDLE_CUTOFF", "LEAN", "RICH"],
        )

        assert control.set_state("RICH") is True
        assert control.get_current_state() == "RICH"

        assert control.set_state("INVALID") is False
        assert control.get_current_state() == "RICH"  # Unchanged

    def test_set_state_by_index(self) -> None:
        """Test setting state by index."""
        control = PanelControl(
            id="test",
            name="Test",
            control_type=ControlType.LEVER,
            states=["IDLE_CUTOFF", "LEAN", "RICH"],
        )

        assert control.set_state_index(2) is True
        assert control.get_current_state() == "RICH"

        assert control.set_state_index(10) is False
        assert control.get_current_state() == "RICH"  # Unchanged


class TestPanel:
    """Test Panel dataclass."""

    def test_create_panel(self) -> None:
        """Test creating a panel."""
        controls = [
            PanelControl("switch1", "Switch 1", ControlType.SWITCH, ["OFF", "ON"]),
            PanelControl("switch2", "Switch 2", ControlType.SWITCH, ["OFF", "ON"]),
        ]
        panel = Panel(name="Test Panel", description="Test description", controls=controls)

        assert panel.name == "Test Panel"
        assert panel.description == "Test description"
        assert len(panel.controls) == 2


class TestControlPanelPlugin:
    """Test ControlPanelPlugin."""

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
    def registry(self) -> Mock:
        """Create mock registry."""
        reg = Mock()
        reg.register = Mock()
        reg.unregister = Mock()
        return reg

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: Mock, registry: Mock) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={"panels": {"definition": "tests/fixtures/panels/test_panel.yaml"}},
            plugin_registry=registry,
        )

    def test_get_metadata(self) -> None:
        """Test getting plugin metadata."""
        plugin = ControlPanelPlugin()
        metadata = plugin.get_metadata()

        assert metadata.name == "control_panel_plugin"
        assert metadata.version == "1.0.0"
        assert metadata.plugin_type == PluginType.FEATURE
        assert "control_panel_manager" in metadata.provides

    def test_initialize(self, context: PluginContext) -> None:
        """Test plugin initialization."""
        plugin = ControlPanelPlugin()
        plugin.initialize(context)

        assert plugin.context == context
        assert isinstance(plugin.panels, list)

        # Should register component
        assert context.plugin_registry.register.called

    def test_navigate_panels(self) -> None:
        """Test panel navigation."""
        plugin = ControlPanelPlugin()

        # Add test panels
        plugin.panels = [
            Panel("Panel 1", "Description 1"),
            Panel("Panel 2", "Description 2"),
            Panel("Panel 3", "Description 3"),
        ]

        # Create minimal context
        event_bus = EventBus()
        message_queue = Mock()
        message_queue.publish = Mock()
        context = PluginContext(
            event_bus=event_bus, message_queue=message_queue, config={}, plugin_registry=None
        )
        plugin.context = context

        assert plugin.current_panel_index == 0

        # Next panel
        plugin.next_panel()
        assert plugin.current_panel_index == 1

        # Previous panel
        plugin.previous_panel()
        assert plugin.current_panel_index == 0

        # Wrap around
        plugin.previous_panel()
        assert plugin.current_panel_index == 2

    def test_navigate_controls(self) -> None:
        """Test control navigation."""
        plugin = ControlPanelPlugin()

        # Add test panel with controls
        controls = [
            PanelControl("switch1", "Switch 1", ControlType.SWITCH, ["OFF", "ON"]),
            PanelControl("switch2", "Switch 2", ControlType.SWITCH, ["OFF", "ON"]),
            PanelControl("switch3", "Switch 3", ControlType.SWITCH, ["OFF", "ON"]),
        ]
        plugin.panels = [Panel("Test Panel", "Description", controls=controls)]

        # Create minimal context
        event_bus = EventBus()
        message_queue = Mock()
        message_queue.publish = Mock()
        context = PluginContext(
            event_bus=event_bus, message_queue=message_queue, config={}, plugin_registry=None
        )
        plugin.context = context

        assert plugin.current_control_index == 0

        # Next control
        plugin.next_control()
        assert plugin.current_control_index == 1

        # Previous control
        plugin.previous_control()
        assert plugin.current_control_index == 0

        # Wrap around
        plugin.previous_control()
        assert plugin.current_control_index == 2

    def test_activate_control(self) -> None:
        """Test activating a control."""
        plugin = ControlPanelPlugin()

        # Add test panel with control
        control = PanelControl(
            id="master_switch",
            name="Master Switch",
            control_type=ControlType.SWITCH,
            states=["OFF", "ON"],
            target_plugin="electrical",
            message_topic="electrical.master_switch",
        )
        plugin.panels = [Panel("Test Panel", "Description", controls=[control])]

        # Create minimal context
        event_bus = EventBus()
        message_queue = Mock()
        message_queue.publish = Mock()
        context = PluginContext(
            event_bus=event_bus, message_queue=message_queue, config={}, plugin_registry=None
        )
        plugin.context = context

        assert control.get_current_state() == "OFF"

        # Activate control
        plugin.activate_current_control()
        assert control.get_current_state() == "ON"

        # Should send messages
        assert message_queue.publish.called

    def test_set_control_state(self) -> None:
        """Test setting control state by ID."""
        plugin = ControlPanelPlugin()

        # Add test panel with control
        control = PanelControl(
            id="mixture",
            name="Mixture",
            control_type=ControlType.LEVER,
            states=["IDLE_CUTOFF", "LEAN", "RICH"],
            target_plugin="engine",
            message_topic="engine.mixture",
        )
        plugin.panels = [Panel("Test Panel", "Description", controls=[control])]

        # Create minimal context
        event_bus = EventBus()
        message_queue = Mock()
        message_queue.publish = Mock()
        context = PluginContext(
            event_bus=event_bus, message_queue=message_queue, config={}, plugin_registry=None
        )
        plugin.context = context

        assert plugin.set_control_state("mixture", "RICH") is True
        assert control.get_current_state() == "RICH"

        assert plugin.set_control_state("nonexistent", "RICH") is False

    def test_get_control_by_id(self) -> None:
        """Test getting control by ID."""
        plugin = ControlPanelPlugin()

        # Add test panels with controls
        control1 = PanelControl("switch1", "Switch 1", ControlType.SWITCH, ["OFF", "ON"])
        control2 = PanelControl("switch2", "Switch 2", ControlType.SWITCH, ["OFF", "ON"])

        plugin.panels = [
            Panel("Panel 1", "Description", controls=[control1]),
            Panel("Panel 2", "Description", controls=[control2]),
        ]

        found = plugin.get_control_by_id("switch2")
        assert found == control2

        not_found = plugin.get_control_by_id("nonexistent")
        assert not_found is None

    def test_system_state_tracking(self) -> None:
        """Test system state tracking for checklist verification."""
        plugin = ControlPanelPlugin()

        # Add test panel with control
        control = PanelControl(
            id="master_switch",
            name="Master Switch",
            control_type=ControlType.SWITCH,
            states=["OFF", "ON"],
            target_plugin="electrical",
            message_topic="electrical.master_switch",
        )
        plugin.panels = [Panel("Test Panel", "Description", controls=[control])]

        # Create minimal context
        event_bus = EventBus()
        message_queue = Mock()
        message_queue.publish = Mock()
        context = PluginContext(
            event_bus=event_bus, message_queue=message_queue, config={}, plugin_registry=None
        )
        plugin.context = context

        # Activate control
        plugin.activate_current_control()

        # Should publish SYSTEM_STATE_CHANGED message
        calls = message_queue.publish.call_args_list
        system_state_msg = None
        for call in calls:
            msg = call[0][0]
            if msg.topic == MessageTopic.SYSTEM_STATE_CHANGED:
                system_state_msg = msg
                break

        assert system_state_msg is not None
        assert "state" in system_state_msg.data
        assert "electrical" in system_state_msg.data["state"]

    def test_button_control(self) -> None:
        """Test momentary button control."""
        plugin = ControlPanelPlugin()

        # Add test panel with button
        button = PanelControl(
            id="start_button",
            name="Start Button",
            control_type=ControlType.BUTTON,
            states=["PRESSED"],
            target_plugin="engine",
            message_topic="engine.start_button",
        )
        plugin.panels = [Panel("Test Panel", "Description", controls=[button])]

        # Create minimal context
        event_bus = EventBus()
        message_queue = Mock()
        message_queue.publish = Mock()
        context = PluginContext(
            event_bus=event_bus, message_queue=message_queue, config={}, plugin_registry=None
        )
        plugin.context = context

        # Activate button
        plugin.activate_current_control()

        # Should send button press message (not state change)
        calls = message_queue.publish.call_args_list
        button_msg = None
        for call in calls:
            msg = call[0][0]
            if msg.topic == "engine.start_button":
                button_msg = msg
                break

        assert button_msg is not None
        assert button_msg.data["action"] == "pressed"

    def test_list_panels(self) -> None:
        """Test listing panel names."""
        plugin = ControlPanelPlugin()
        plugin.panels = [
            Panel("Panel 1", "Description 1"),
            Panel("Panel 2", "Description 2"),
        ]

        panel_names = plugin.list_panels()
        assert len(panel_names) == 2
        assert "Panel 1" in panel_names
        assert "Panel 2" in panel_names

    def test_get_panel_by_name(self) -> None:
        """Test getting panel by name."""
        plugin = ControlPanelPlugin()
        panel1 = Panel("Panel 1", "Description 1")
        panel2 = Panel("Panel 2", "Description 2")
        plugin.panels = [panel1, panel2]

        found = plugin.get_panel_by_name("Panel 2")
        assert found == panel2

        not_found = plugin.get_panel_by_name("Nonexistent")
        assert not_found is None

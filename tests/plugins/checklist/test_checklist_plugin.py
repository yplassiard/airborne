"""Tests for checklist plugin."""

from unittest.mock import Mock

import pytest

from airborne.core.event_bus import EventBus
from airborne.core.plugin import PluginContext, PluginType
from airborne.plugins.checklist import (
    Checklist,
    ChecklistItem,
    ChecklistItemState,
    ChecklistPlugin,
)


class TestChecklistItem:
    """Test ChecklistItem dataclass."""

    def test_create_item(self) -> None:
        """Test creating a checklist item."""
        item = ChecklistItem(
            challenge="Fuel Pump", response="ON", verify_condition="fuel.pump == ON"
        )

        assert item.challenge == "Fuel Pump"
        assert item.response == "ON"
        assert item.verify_condition == "fuel.pump == ON"
        assert item.state == ChecklistItemState.PENDING
        assert item.completed_by is None

    def test_item_string_representation(self) -> None:
        """Test string representation."""
        item = ChecklistItem(challenge="Master Switch", response="ON")
        assert str(item) == "Master Switch... ON"


class TestChecklist:
    """Test Checklist dataclass."""

    def test_create_checklist(self) -> None:
        """Test creating a checklist."""
        items = [
            ChecklistItem("Fuel Pump", "ON"),
            ChecklistItem("Master Switch", "ON"),
        ]
        checklist = Checklist(
            id="test_checklist",
            name="Test Checklist",
            description="Test description",
            items=items,
        )

        assert checklist.id == "test_checklist"
        assert checklist.name == "Test Checklist"
        assert len(checklist.items) == 2
        assert checklist.current_index is None

    def test_is_complete_empty(self) -> None:
        """Test is_complete on empty checklist."""
        checklist = Checklist(id="test", name="Test", description="Test")
        assert checklist.is_complete() is True

    def test_is_complete_all_completed(self) -> None:
        """Test is_complete when all items completed."""
        items = [
            ChecklistItem("Item 1", "Response 1", state=ChecklistItemState.COMPLETED),
            ChecklistItem("Item 2", "Response 2", state=ChecklistItemState.COMPLETED),
        ]
        checklist = Checklist(id="test", name="Test", description="Test", items=items)
        assert checklist.is_complete() is True

    def test_is_complete_with_skipped(self) -> None:
        """Test is_complete with skipped items."""
        items = [
            ChecklistItem("Item 1", "Response 1", state=ChecklistItemState.COMPLETED),
            ChecklistItem("Item 2", "Response 2", state=ChecklistItemState.SKIPPED),
        ]
        checklist = Checklist(id="test", name="Test", description="Test", items=items)
        assert checklist.is_complete() is True

    def test_is_complete_not_finished(self) -> None:
        """Test is_complete when items pending."""
        items = [
            ChecklistItem("Item 1", "Response 1", state=ChecklistItemState.COMPLETED),
            ChecklistItem("Item 2", "Response 2", state=ChecklistItemState.PENDING),
        ]
        checklist = Checklist(id="test", name="Test", description="Test", items=items)
        assert checklist.is_complete() is False

    def test_get_current_item(self) -> None:
        """Test getting current item."""
        items = [
            ChecklistItem("Item 1", "Response 1"),
            ChecklistItem("Item 2", "Response 2"),
        ]
        checklist = Checklist(id="test", name="Test", description="Test", items=items)

        # No current item initially
        assert checklist.get_current_item() is None

        # Set current index
        checklist.current_index = 0
        assert checklist.get_current_item() == items[0]

        checklist.current_index = 1
        assert checklist.get_current_item() == items[1]

    def test_get_completion_percentage(self) -> None:
        """Test completion percentage calculation."""
        items = [
            ChecklistItem("Item 1", "Response 1", state=ChecklistItemState.COMPLETED),
            ChecklistItem("Item 2", "Response 2", state=ChecklistItemState.PENDING),
            ChecklistItem("Item 3", "Response 3", state=ChecklistItemState.COMPLETED),
            ChecklistItem("Item 4", "Response 4", state=ChecklistItemState.SKIPPED),
        ]
        checklist = Checklist(id="test", name="Test", description="Test", items=items)

        # 2 out of 4 completed = 50%
        assert checklist.get_completion_percentage() == 50.0


class TestChecklistPlugin:
    """Test ChecklistPlugin."""

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
            config={"checklists": {"directory": "tests/fixtures/checklists"}},
            plugin_registry=registry,
        )

    def test_get_metadata(self) -> None:
        """Test getting plugin metadata."""
        plugin = ChecklistPlugin()
        metadata = plugin.get_metadata()

        assert metadata.name == "checklist_plugin"
        assert metadata.version == "1.0.0"
        assert metadata.plugin_type == PluginType.FEATURE
        assert "checklist_manager" in metadata.provides

    def test_initialize(self, context: PluginContext) -> None:
        """Test plugin initialization."""
        plugin = ChecklistPlugin()
        plugin.initialize(context)

        assert plugin.context == context
        assert isinstance(plugin.checklists, dict)

        # Should register component
        assert context.plugin_registry.register.called

        # Should subscribe to messages (POSITION_UPDATED, SYSTEM_STATE_CHANGED, input.checklist_menu)
        assert context.message_queue.subscribe.call_count == 3

    def test_start_checklist(self) -> None:
        """Test starting a checklist."""
        plugin = ChecklistPlugin()

        # Create a test checklist
        items = [
            ChecklistItem("Item 1", "Response 1"),
            ChecklistItem("Item 2", "Response 2"),
        ]
        checklist = Checklist(id="test", name="Test", description="Test", items=items)
        plugin.checklists["test"] = checklist

        # Create minimal context
        event_bus = EventBus()
        message_queue = Mock()
        message_queue.publish = Mock()
        context = PluginContext(
            event_bus=event_bus, message_queue=message_queue, config={}, plugin_registry=None
        )
        plugin.context = context

        # Start checklist
        result = plugin.start_checklist("test")

        assert result is True
        assert plugin.active_checklist == checklist
        assert checklist.current_index == 0
        assert checklist.items[0].state == ChecklistItemState.IN_PROGRESS

        # Should announce start
        assert message_queue.publish.called

    def test_start_nonexistent_checklist(self) -> None:
        """Test starting a non-existent checklist."""
        plugin = ChecklistPlugin()
        result = plugin.start_checklist("nonexistent")
        assert result is False

    def test_complete_current_item(self) -> None:
        """Test completing current checklist item."""
        plugin = ChecklistPlugin()

        # Create and start checklist
        items = [
            ChecklistItem("Item 1", "Response 1"),
            ChecklistItem("Item 2", "Response 2"),
        ]
        checklist = Checklist(
            id="test",
            name="Test",
            description="Test",
            items=items,
            current_index=0,
        )
        checklist.items[0].state = ChecklistItemState.IN_PROGRESS
        plugin.active_checklist = checklist

        # Create minimal context
        event_bus = EventBus()
        message_queue = Mock()
        message_queue.publish = Mock()
        context = PluginContext(
            event_bus=event_bus, message_queue=message_queue, config={}, plugin_registry=None
        )
        plugin.context = context

        # Complete first item
        result = plugin.complete_current_item(manual=True)

        assert result is True
        assert items[0].state == ChecklistItemState.COMPLETED
        assert items[0].completed_by == "manual"
        assert checklist.current_index == 1
        assert items[1].state == ChecklistItemState.IN_PROGRESS

    def test_skip_current_item(self) -> None:
        """Test skipping current checklist item."""
        plugin = ChecklistPlugin()

        # Create and start checklist
        items = [
            ChecklistItem("Item 1", "Response 1"),
            ChecklistItem("Item 2", "Response 2"),
        ]
        checklist = Checklist(
            id="test",
            name="Test",
            description="Test",
            items=items,
            current_index=0,
        )
        checklist.items[0].state = ChecklistItemState.IN_PROGRESS
        plugin.active_checklist = checklist

        # Create minimal context
        event_bus = EventBus()
        message_queue = Mock()
        message_queue.publish = Mock()
        context = PluginContext(
            event_bus=event_bus, message_queue=message_queue, config={}, plugin_registry=None
        )
        plugin.context = context

        # Skip first item
        result = plugin.skip_current_item()

        assert result is True
        assert items[0].state == ChecklistItemState.SKIPPED
        assert checklist.current_index == 1

    def test_checklist_completion(self) -> None:
        """Test checklist completion."""
        plugin = ChecklistPlugin()

        # Create checklist with one item
        items = [ChecklistItem("Item 1", "Response 1")]
        checklist = Checklist(
            id="test",
            name="Test",
            description="Test",
            items=items,
            current_index=0,
        )
        checklist.items[0].state = ChecklistItemState.IN_PROGRESS
        plugin.active_checklist = checklist

        # Create minimal context
        event_bus = EventBus()
        message_queue = Mock()
        message_queue.publish = Mock()
        context = PluginContext(
            event_bus=event_bus, message_queue=message_queue, config={}, plugin_registry=None
        )
        plugin.context = context

        # Complete last item
        result = plugin.complete_current_item()

        assert result is False  # No more items
        assert plugin.active_checklist is None  # Checklist ended
        assert items[0].state == ChecklistItemState.COMPLETED

    def test_auto_verify_items(self) -> None:
        """Test auto-verification of checklist items."""
        plugin = ChecklistPlugin()

        # Create checklist with verify condition
        items = [ChecklistItem("Fuel Pump", "ON", verify_condition="fuel.pump == ON")]
        checklist = Checklist(
            id="test",
            name="Test",
            description="Test",
            items=items,
            current_index=0,
        )
        checklist.items[0].state = ChecklistItemState.IN_PROGRESS
        plugin.active_checklist = checklist

        # Set system state
        plugin._system_state = {"fuel": {"pump": "ON"}}

        # Create minimal context
        event_bus = EventBus()
        message_queue = Mock()
        message_queue.publish = Mock()
        context = PluginContext(
            event_bus=event_bus, message_queue=message_queue, config={}, plugin_registry=None
        )
        plugin.context = context

        # Auto-verify
        plugin._auto_verify_items()

        # Item should be auto-completed
        assert items[0].state == ChecklistItemState.COMPLETED
        assert items[0].completed_by == "auto"

    def test_check_verify_condition(self) -> None:
        """Test verify condition checking."""
        plugin = ChecklistPlugin()
        plugin._system_state = {"fuel": {"pump": "ON"}, "electrical": {"battery": "OFF"}}

        # Test simple condition
        assert plugin._check_verify_condition("fuel.pump == ON") is True
        assert plugin._check_verify_condition("fuel.pump == OFF") is False

        # Test nested condition
        assert plugin._check_verify_condition("electrical.battery == OFF") is True
        assert plugin._check_verify_condition("electrical.battery == ON") is False

    def test_list_checklists(self) -> None:
        """Test listing checklists."""
        plugin = ChecklistPlugin()
        plugin.checklists = {
            "checklist1": Checklist("checklist1", "Checklist 1", "Description 1"),
            "checklist2": Checklist("checklist2", "Checklist 2", "Description 2"),
        }

        checklist_ids = plugin.list_checklists()
        assert len(checklist_ids) == 2
        assert "checklist1" in checklist_ids
        assert "checklist2" in checklist_ids

    def test_get_checklist(self) -> None:
        """Test getting checklist by ID."""
        plugin = ChecklistPlugin()
        checklist = Checklist("test", "Test", "Description")
        plugin.checklists["test"] = checklist

        retrieved = plugin.get_checklist("test")
        assert retrieved == checklist

        # Test non-existent checklist
        assert plugin.get_checklist("nonexistent") is None

"""Tests for InputHandlerManager."""

import pytest

from airborne.core.input_event import InputEvent
from airborne.core.input_handler import InputHandler
from airborne.core.input_handler_manager import InputHandlerManager


class MockHandler(InputHandler):
    """Mock input handler for testing."""

    def __init__(
        self,
        priority: int,
        name: str = "mock",
        active: bool = True,
        can_handle: bool = True,
        will_consume: bool = True,
    ):
        """Initialize mock handler.

        Args:
            priority: Handler priority.
            name: Handler name.
            active: Whether handler is active.
            can_handle: Whether handler can handle events.
            will_consume: Whether handler will consume events.
        """
        self._priority = priority
        self._name = name
        self._active = active
        self._can_handle = can_handle
        self._will_consume = will_consume
        self.handle_count = 0
        self.last_event = None

    def get_priority(self) -> int:
        return self._priority

    def can_handle_input(self, event: InputEvent) -> bool:
        return self._can_handle

    def handle_input(self, event: InputEvent) -> bool:
        self.handle_count += 1
        self.last_event = event
        return self._will_consume

    def is_active(self) -> bool:
        return self._active

    def get_name(self) -> str:
        return self._name


class TestInputHandlerManagerRegistration:
    """Test handler registration and unregistration."""

    def test_register_handler(self):
        """Test registering a handler."""
        manager = InputHandlerManager()
        handler = MockHandler(priority=10, name="test")

        manager.register(handler)

        assert manager.get_handler_count() == 1
        assert manager.get_handler("test") == handler

    def test_register_multiple_handlers(self):
        """Test registering multiple handlers."""
        manager = InputHandlerManager()
        handler1 = MockHandler(priority=10, name="h1")
        handler2 = MockHandler(priority=20, name="h2")
        handler3 = MockHandler(priority=5, name="h3")

        manager.register(handler1)
        manager.register(handler2)
        manager.register(handler3)

        assert manager.get_handler_count() == 3

    def test_register_sorts_by_priority(self):
        """Test handlers are sorted by priority."""
        manager = InputHandlerManager()
        handler1 = MockHandler(priority=100, name="h1")
        handler2 = MockHandler(priority=10, name="h2")
        handler3 = MockHandler(priority=50, name="h3")

        manager.register(handler1)
        manager.register(handler2)
        manager.register(handler3)

        handlers = manager.get_all_handlers()
        assert handlers[0].get_name() == "h2"  # Priority 10
        assert handlers[1].get_name() == "h3"  # Priority 50
        assert handlers[2].get_name() == "h1"  # Priority 100

    def test_register_duplicate_name_raises_error(self):
        """Test registering handler with duplicate name raises error."""
        manager = InputHandlerManager()
        handler1 = MockHandler(priority=10, name="test")
        handler2 = MockHandler(priority=20, name="test")

        manager.register(handler1)

        with pytest.raises(ValueError, match="already registered"):
            manager.register(handler2)

    def test_register_with_custom_name(self):
        """Test registering handler with custom name."""
        manager = InputHandlerManager()
        handler = MockHandler(priority=10, name="default")

        manager.register(handler, name="custom")

        assert manager.get_handler("custom") == handler
        assert manager.get_handler("default") is None

    def test_unregister_handler(self):
        """Test unregistering a handler."""
        manager = InputHandlerManager()
        handler = MockHandler(priority=10, name="test")

        manager.register(handler)
        assert manager.get_handler_count() == 1

        manager.unregister(handler)
        assert manager.get_handler_count() == 0
        assert manager.get_handler("test") is None

    def test_unregister_by_name(self):
        """Test unregistering handler by name."""
        manager = InputHandlerManager()
        handler = MockHandler(priority=10, name="test")

        manager.register(handler)
        manager.unregister_by_name("test")

        assert manager.get_handler_count() == 0

    def test_unregister_not_registered_raises_error(self):
        """Test unregistering non-registered handler raises error."""
        manager = InputHandlerManager()
        handler = MockHandler(priority=10, name="test")

        with pytest.raises(ValueError, match="not registered"):
            manager.unregister(handler)

    def test_unregister_by_name_not_found_raises_error(self):
        """Test unregistering by non-existent name raises error."""
        manager = InputHandlerManager()

        with pytest.raises(ValueError, match="not found"):
            manager.unregister_by_name("nonexistent")

    def test_clear_all_handlers(self):
        """Test clearing all handlers."""
        manager = InputHandlerManager()
        manager.register(MockHandler(priority=10, name="h1"))
        manager.register(MockHandler(priority=20, name="h2"))

        assert manager.get_handler_count() == 2

        manager.clear()
        assert manager.get_handler_count() == 0


class TestInputHandlerManagerDispatch:
    """Test input event dispatch."""

    def test_process_input_single_handler(self):
        """Test processing input with single handler."""
        manager = InputHandlerManager()
        handler = MockHandler(priority=10, name="test", will_consume=True)
        manager.register(handler)

        event = InputEvent.from_keyboard(key=1, mods=0)
        result = manager.process_input(event)

        assert result is True
        assert handler.handle_count == 1
        assert handler.last_event == event

    def test_process_input_priority_order(self):
        """Test handlers called in priority order."""
        manager = InputHandlerManager()
        handler1 = MockHandler(priority=100, name="low", will_consume=False)
        handler2 = MockHandler(priority=10, name="high", will_consume=True)
        handler3 = MockHandler(priority=50, name="mid", will_consume=False)

        manager.register(handler1)
        manager.register(handler2)
        manager.register(handler3)

        event = InputEvent.from_keyboard(key=1, mods=0)
        manager.process_input(event)

        # High priority handler should consume first
        assert handler2.handle_count == 1
        assert handler3.handle_count == 0  # Not reached
        assert handler1.handle_count == 0  # Not reached

    def test_process_input_continues_when_not_consumed(self):
        """Test event propagates when not consumed."""
        manager = InputHandlerManager()
        handler1 = MockHandler(priority=10, name="h1", will_consume=False)
        handler2 = MockHandler(priority=20, name="h2", will_consume=False)
        handler3 = MockHandler(priority=30, name="h3", will_consume=True)

        manager.register(handler1)
        manager.register(handler2)
        manager.register(handler3)

        event = InputEvent.from_keyboard(key=1, mods=0)
        result = manager.process_input(event)

        assert result is True
        assert handler1.handle_count == 1
        assert handler2.handle_count == 1
        assert handler3.handle_count == 1

    def test_process_input_skips_inactive_handlers(self):
        """Test inactive handlers are skipped."""
        manager = InputHandlerManager()
        handler1 = MockHandler(priority=10, name="h1", active=False, will_consume=True)
        handler2 = MockHandler(priority=20, name="h2", active=True, will_consume=True)

        manager.register(handler1)
        manager.register(handler2)

        event = InputEvent.from_keyboard(key=1, mods=0)
        result = manager.process_input(event)

        assert result is True
        assert handler1.handle_count == 0  # Skipped (inactive)
        assert handler2.handle_count == 1

    def test_process_input_skips_cant_handle(self):
        """Test handlers that can't handle event are skipped."""
        manager = InputHandlerManager()
        handler1 = MockHandler(priority=10, name="h1", can_handle=False)
        handler2 = MockHandler(priority=20, name="h2", can_handle=True, will_consume=True)

        manager.register(handler1)
        manager.register(handler2)

        event = InputEvent.from_keyboard(key=1, mods=0)
        result = manager.process_input(event)

        assert result is True
        assert handler1.handle_count == 0  # Skipped (can't handle)
        assert handler2.handle_count == 1

    def test_process_input_no_consumers_returns_false(self):
        """Test returns False when no handler consumes event."""
        manager = InputHandlerManager()
        handler = MockHandler(priority=10, name="test", will_consume=False)
        manager.register(handler)

        event = InputEvent.from_keyboard(key=1, mods=0)
        result = manager.process_input(event)

        assert result is False
        assert handler.handle_count == 1

    def test_process_input_empty_manager_returns_false(self):
        """Test returns False when no handlers registered."""
        manager = InputHandlerManager()
        event = InputEvent.from_keyboard(key=1, mods=0)

        result = manager.process_input(event)

        assert result is False

    def test_process_input_handles_handler_exception(self):
        """Test manager continues when handler raises exception."""

        class FailingHandler(InputHandler):
            def get_priority(self) -> int:
                return 10

            def can_handle_input(self, event: InputEvent) -> bool:
                return True

            def handle_input(self, event: InputEvent) -> bool:
                raise RuntimeError("Handler error")

            def get_name(self) -> str:
                return "failing"

        manager = InputHandlerManager()
        failing_handler = FailingHandler()
        success_handler = MockHandler(priority=20, name="success", will_consume=True)

        manager.register(failing_handler)
        manager.register(success_handler)

        event = InputEvent.from_keyboard(key=1, mods=0)
        result = manager.process_input(event)

        # Should continue to next handler despite exception
        assert result is True
        assert success_handler.handle_count == 1


class TestInputHandlerManagerIntrospection:
    """Test manager introspection methods."""

    def test_get_handler_by_name(self):
        """Test getting handler by name."""
        manager = InputHandlerManager()
        handler = MockHandler(priority=10, name="test")
        manager.register(handler)

        retrieved = manager.get_handler("test")
        assert retrieved == handler

    def test_get_handler_not_found_returns_none(self):
        """Test getting non-existent handler returns None."""
        manager = InputHandlerManager()
        assert manager.get_handler("nonexistent") is None

    def test_get_all_handlers(self):
        """Test getting all handlers."""
        manager = InputHandlerManager()
        h1 = MockHandler(priority=10, name="h1")
        h2 = MockHandler(priority=20, name="h2")

        manager.register(h1)
        manager.register(h2)

        handlers = manager.get_all_handlers()
        assert len(handlers) == 2
        assert h1 in handlers
        assert h2 in handlers

    def test_get_handler_count(self):
        """Test getting handler count."""
        manager = InputHandlerManager()
        assert manager.get_handler_count() == 0

        manager.register(MockHandler(priority=10, name="h1"))
        assert manager.get_handler_count() == 1

        manager.register(MockHandler(priority=20, name="h2"))
        assert manager.get_handler_count() == 2

    def test_get_active_handler_count(self):
        """Test getting active handler count."""
        manager = InputHandlerManager()
        manager.register(MockHandler(priority=10, name="h1", active=True))
        manager.register(MockHandler(priority=20, name="h2", active=False))
        manager.register(MockHandler(priority=30, name="h3", active=True))

        assert manager.get_active_handler_count() == 2

    def test_get_handler_info(self):
        """Test getting handler info for debugging."""
        manager = InputHandlerManager()
        manager.register(MockHandler(priority=10, name="h1", active=True))
        manager.register(MockHandler(priority=20, name="h2", active=False))

        info = manager.get_handler_info()

        assert len(info) == 2
        assert info[0]["name"] == "h1"
        assert info[0]["priority"] == 10
        assert info[0]["active"] is True
        assert info[1]["name"] == "h2"
        assert info[1]["priority"] == 20
        assert info[1]["active"] is False

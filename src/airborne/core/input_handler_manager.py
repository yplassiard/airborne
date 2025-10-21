"""Input handler manager for priority-based event dispatch.

This module provides centralized management of input handlers, dispatching
input events to handlers in priority order and managing handler registration.

Typical usage:
    manager = InputHandlerManager()
    manager.register(menu_handler)
    manager.register(control_panel_handler)
    manager.register(flight_controls_handler)

    # Process input event
    event = InputEvent.from_keyboard(pygame.K_F1, 0)
    handled = manager.process_input(event)
"""

from typing import Any

from airborne.core.input_event import InputEvent
from airborne.core.input_handler import InputHandler
from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


class InputHandlerManager:
    """Manages priority-based input event dispatch.

    The manager maintains a list of input handlers sorted by priority,
    dispatching input events to handlers in order until one consumes the event.

    Only active handlers (is_active() returns True) are considered for dispatch.

    Examples:
        >>> manager = InputHandlerManager()
        >>> manager.register(MenuHandler())  # Priority 10
        >>> manager.register(PanelHandler())  # Priority 100
        >>> event = InputEvent.from_keyboard(pygame.K_F1, 0)
        >>> manager.process_input(event)
        True
    """

    def __init__(self):
        """Initialize input handler manager."""
        self._handlers: list[InputHandler] = []
        self._handlers_by_name: dict[str, InputHandler] = {}
        logger.debug("InputHandlerManager initialized")

    def register(self, handler: InputHandler, name: str | None = None) -> None:
        """Register an input handler.

        Handlers are automatically sorted by priority after registration.
        Lower priority values are processed first.

        Args:
            handler: InputHandler instance to register.
            name: Optional name for handler (defaults to handler.get_name()).

        Raises:
            ValueError: If handler with same name already registered.
        """
        handler_name = name if name else handler.get_name()

        if handler_name in self._handlers_by_name:
            raise ValueError(f"Handler '{handler_name}' already registered")

        self._handlers.append(handler)
        self._handlers_by_name[handler_name] = handler

        # Re-sort by priority (lower = higher priority)
        self._handlers.sort(key=lambda h: h.get_priority())

        logger.info(
            "Registered handler '%s' with priority %d",
            handler_name,
            handler.get_priority(),
        )

    def unregister(self, handler: InputHandler) -> None:
        """Remove a handler from the manager.

        Args:
            handler: InputHandler instance to remove.

        Raises:
            ValueError: If handler not found.
        """
        if handler not in self._handlers:
            raise ValueError("Handler not registered")

        handler_name = handler.get_name()
        self._handlers.remove(handler)

        if handler_name in self._handlers_by_name:
            del self._handlers_by_name[handler_name]

        logger.info("Unregistered handler '%s'", handler_name)

    def unregister_by_name(self, name: str) -> None:
        """Remove a handler by name.

        Args:
            name: Name of handler to remove.

        Raises:
            ValueError: If handler with name not found.
        """
        if name not in self._handlers_by_name:
            raise ValueError(f"Handler '{name}' not found")

        handler = self._handlers_by_name[name]
        self.unregister(handler)

    def get_handler(self, name: str) -> InputHandler | None:
        """Get a handler by name.

        Args:
            name: Name of handler to retrieve.

        Returns:
            InputHandler instance or None if not found.
        """
        return self._handlers_by_name.get(name)

    def get_all_handlers(self) -> list[InputHandler]:
        """Get all registered handlers in priority order.

        Returns:
            List of InputHandler instances, sorted by priority.
        """
        return self._handlers.copy()

    def process_input(self, event: InputEvent) -> bool:
        """Dispatch input event to handlers in priority order.

        Handlers are called in priority order (lowest priority value first).
        Only active handlers (is_active() returns True) are considered.

        Processing stops when:
        - A handler returns True (event consumed)
        - All handlers have been tried

        Args:
            event: Input event to process.

        Returns:
            True if any handler consumed the event, False otherwise.
        """
        for handler in self._handlers:
            # Skip inactive handlers
            if not handler.is_active():
                continue

            # Check if handler wants this event
            if not handler.can_handle_input(event):
                continue

            # Let handler process event
            try:
                consumed = handler.handle_input(event)
                if consumed:
                    logger.debug(
                        "Event consumed by handler '%s' (priority %d)",
                        handler.get_name(),
                        handler.get_priority(),
                    )
                    return True
            except Exception as e:
                logger.error(
                    "Error in handler '%s': %s",
                    handler.get_name(),
                    e,
                    exc_info=True,
                )
                # Continue to next handler on error

        logger.debug("Event not consumed by any handler")
        return False

    def get_handler_count(self) -> int:
        """Get number of registered handlers.

        Returns:
            Count of registered handlers.
        """
        return len(self._handlers)

    def get_active_handler_count(self) -> int:
        """Get number of currently active handlers.

        Returns:
            Count of handlers where is_active() returns True.
        """
        return sum(1 for h in self._handlers if h.is_active())

    def clear(self) -> None:
        """Remove all registered handlers."""
        self._handlers.clear()
        self._handlers_by_name.clear()
        logger.info("Cleared all handlers")

    def get_handler_info(self) -> list[dict[str, Any]]:
        """Get information about all registered handlers.

        Useful for debugging and introspection.

        Returns:
            List of dicts with handler info (name, priority, active).
        """
        return [
            {
                "name": h.get_name(),
                "priority": h.get_priority(),
                "active": h.is_active(),
            }
            for h in self._handlers
        ]

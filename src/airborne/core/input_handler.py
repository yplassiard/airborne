"""Input handler interface for unified input processing.

This module provides the abstract base class for all input handlers in the system.
Handlers process input events from any source (keyboard, joystick, controller, network)
and are dispatched in priority order.

Typical usage:
    class MenuInputHandler(InputHandler):
        def get_priority(self) -> int:
            return 10  # High priority for menus

        def can_handle_input(self, event: InputEvent) -> bool:
            return self._menu.is_open()

        def handle_input(self, event: InputEvent) -> bool:
            if event.matches_keyboard(pygame.K_ESCAPE):
                self._menu.close()
                return True
            return False
"""

from abc import ABC, abstractmethod

from airborne.core.input_event import InputEvent


class InputHandler(ABC):
    """Abstract base class for input handlers.

    Input handlers process input events from any source in a priority-ordered chain.
    Each handler can inspect an event, decide if it wants to handle it, and optionally
    consume the event to prevent further propagation.

    Priority ranges (suggested):
    - 0-99: Modal overlays (menus, dialogs) - highest priority
    - 100-199: Context handlers (control panel, active widgets)
    - 200+: Default handlers (flight controls, instrument readouts)

    Subclasses must implement:
    - get_priority(): Return handler's priority level
    - can_handle_input(): Check if handler wants this event
    - handle_input(): Process the event
    - is_active(): Check if handler is currently active (optional override)
    """

    @abstractmethod
    def get_priority(self) -> int:
        """Get handler priority for dispatch ordering.

        Lower numbers = higher priority (processed first).

        Suggested ranges:
        - 0-99: Modal overlays (menus, dialogs)
        - 100-199: Context handlers (control panel)
        - 200+: Default handlers (flight controls)

        Returns:
            Priority value as integer.
        """

    @abstractmethod
    def can_handle_input(self, event: InputEvent) -> bool:
        """Check if this handler wants to process the input event.

        This is called before handle_input() to allow handlers to quickly
        reject events they don't care about.

        Args:
            event: Input event to check.

        Returns:
            True if handler should receive this event.
        """

    @abstractmethod
    def handle_input(self, event: InputEvent) -> bool:
        """Process an input event.

        Args:
            event: Input event to process.

        Returns:
            True if event was consumed (stop propagation).
            False if event should continue to next handler.
        """

    def is_active(self) -> bool:
        """Check if handler is currently active.

        Default implementation returns True (always active).
        Override for conditional handlers (e.g., menus that are only
        active when open).

        Returns:
            True if handler should be considered for event processing.
        """
        return True

    def get_name(self) -> str:
        """Get handler name for debugging.

        Default implementation uses class name.
        Override to provide more descriptive name.

        Returns:
            Handler name string.
        """
        return self.__class__.__name__

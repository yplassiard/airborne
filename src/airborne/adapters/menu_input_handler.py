"""Input handler adapter for menu systems.

This adapter wraps the existing Menu base class to work with the new
InputHandler interface, allowing menus to participate in priority-based
input dispatch.
"""

import pygame

from airborne.core.input_event import InputEvent
from airborne.core.input_handler import InputHandler
from airborne.core.logging_system import get_logger
from airborne.ui.menu import Menu

logger = get_logger(__name__)


class MenuInputHandler(InputHandler):
    """Input handler adapter for menu system.

    Wraps a Menu instance to work with the new InputHandler interface.
    Handles standard menu navigation keys (UP, DOWN, ESC, RETURN, number keys).

    The handler is only active when the menu is open (menu.is_open() returns True).

    Examples:
        >>> atc_menu = ATCMenu(tts_provider, atc_queue, message_queue)
        >>> handler = MenuInputHandler(
        ...     menu=atc_menu,
        ...     name="atc_menu",
        ...     priority=20
        ... )
        >>> manager.register(handler)
    """

    def __init__(self, menu: Menu, name: str, priority: int):
        """Initialize menu input handler.

        Args:
            menu: Menu instance to wrap.
            name: Handler name for debugging.
            priority: Handler priority (lower = higher priority).
        """
        self._menu = menu
        self._name = name
        self._priority = priority

    def get_priority(self) -> int:
        """Get handler priority."""
        return self._priority

    def can_handle_input(self, event: InputEvent) -> bool:
        """Check if handler can process this event.

        Only handles keyboard events.

        Args:
            event: Input event to check.

        Returns:
            True if this is a keyboard event.
        """
        # Only handle keyboard events
        return event.key is not None

    def handle_input(self, event: InputEvent) -> bool:
        """Handle keyboard input for menu navigation.

        Handles standard menu keys:
        - ESC: Close menu
        - UP/DOWN: Navigate menu
        - RETURN/ENTER: Select current option
        - Number keys (1-9): Direct selection

        Args:
            event: Input event to handle.

        Returns:
            True if key was consumed, False otherwise.
        """
        key = event.key

        # ESC closes menu
        if key == pygame.K_ESCAPE:
            self._menu.close()
            return True

        # Number keys select option directly
        if pygame.K_1 <= key <= pygame.K_9:
            number = key - pygame.K_0
            return self._menu.select_option(str(number))

        # Up/Down arrows navigate
        if key == pygame.K_UP:
            return self._menu.move_selection_up()
        elif key == pygame.K_DOWN:
            return self._menu.move_selection_down()

        # Enter selects current option
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            return self._menu.select_current()

        # TAB also selects current (alternative to RETURN)
        if key == pygame.K_TAB:
            return self._menu.select_current()

        return False

    def is_active(self) -> bool:
        """Check if handler is active.

        Menu handler is active only when menu is open.

        Returns:
            True if menu is open.
        """
        return self._menu.is_open()

    def get_name(self) -> str:
        """Get handler name."""
        return self._name


class ChecklistMenuInputHandler(MenuInputHandler):
    """Specialized input handler for checklist menu.

    Extends MenuInputHandler to support checklist-specific keys:
    - Shift+Enter: Verify item as affirmative
    - Ctrl+Enter: Verify item as negative
    """

    def handle_input(self, event: InputEvent) -> bool:
        """Handle keyboard input for checklist menu.

        Handles standard menu keys plus checklist verification:
        - Shift+Enter: Verify affirmative
        - Ctrl+Enter: Verify negative

        Args:
            event: Input event to handle.

        Returns:
            True if key was consumed, False otherwise.
        """
        key = event.key
        mods = event.mods

        # Handle checklist verification in execution mode
        if self._menu.get_state() == "CHECKLIST_EXECUTION":
            # Shift+Enter = verify affirmative (check item)
            if (
                key in (pygame.K_RETURN, pygame.K_KP_ENTER)
                and (mods & pygame.KMOD_SHIFT)
                and hasattr(self._menu, "verify_item")
            ):
                self._menu.verify_item()
                return True

            # Ctrl+Enter = cancel checklist
            if (
                key in (pygame.K_RETURN, pygame.K_KP_ENTER)
                and (mods & pygame.KMOD_CTRL)
                and hasattr(self._menu, "cancel_checklist")
            ):
                self._menu.cancel_checklist()
                return True

            # ESC also cancels checklist
            if key == pygame.K_ESCAPE and hasattr(self._menu, "cancel_checklist"):
                self._menu.cancel_checklist()
                return True

        # Fall back to standard menu handling
        return super().handle_input(event)

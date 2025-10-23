"""Generic menu system for AirBorne flight simulator.

This module provides a reusable base class for building interactive menus
with keyboard navigation, TTS announcements, and customizable behavior.

Typical usage:
    class MyMenu(Menu):
        def _build_options(self, context):
            return [
                MenuOption(key="1", label="Option 1", data={"action": "do_something"}),
                MenuOption(key="2", label="Option 2", data={"action": "do_other"}),
            ]

        def _handle_selection(self, option):
            # Handle the selected option
            action = option.data.get("action")
            self._execute_action(action)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageQueue, MessageTopic

logger = get_logger(__name__)


@dataclass
class MenuOption:
    """Represents a single menu option.

    Attributes:
        key: Key to select this option (e.g., "1", "2").
        label: Human-readable label shown in menu.
        message_key: TTS message key for announcing this option.
        data: Additional data associated with this option (menu-specific).
        enabled: Whether this option is currently selectable.
    """

    key: str
    label: str
    message_key: str | None = None
    data: dict[str, Any] | None = None
    enabled: bool = True


class Menu(ABC):
    """Generic base class for interactive menus.

    Provides standard menu functionality:
    - Open/close menu
    - Navigate up/down through options
    - Select current option
    - TTS announcements
    - State management

    Subclasses must implement:
    - _build_options(context): Build menu options
    - _handle_selection(option): Handle option selection
    - _get_menu_opened_message(): Get TTS message key for menu opening

    Subclasses can optionally override:
    - _on_open(): Called after menu opens
    - _on_close(): Called before menu closes
    - _is_available(): Check if menu can be opened
    """

    def __init__(
        self,
        message_queue: MessageQueue | None = None,
        sender_name: str = "menu",
    ):
        """Initialize menu.

        Args:
            message_queue: Message queue for TTS announcements.
            sender_name: Name used as message sender (for logging/debugging).
        """
        self._message_queue = message_queue
        self._sender_name = sender_name
        self._state = "CLOSED"  # CLOSED, OPEN
        self._current_options: list[MenuOption] = []
        self._selected_index = 0

        logger.debug("%s initialized", sender_name)

    def open(self, context: Any = None) -> bool:
        """Open the menu.

        Args:
            context: Optional context for building menu options (menu-specific).

        Returns:
            True if menu opened successfully, False otherwise.
        """
        # Check availability
        if not self._is_available(context):
            logger.warning("%s not available", self._sender_name)
            return False

        # Build options
        self._current_options = self._build_options(context)

        if not self._current_options:
            logger.warning("%s has no options", self._sender_name)
            return False

        # Open menu
        self._state = "OPEN"
        self._selected_index = 0
        logger.info("%s opened with %d options", self._sender_name, len(self._current_options))

        # Custom open logic
        self._on_open(context)

        # Announce menu opening
        self._announce_menu_opened()

        return True

    def close(self, speak: bool = True) -> None:
        """Close the menu.

        Args:
            speak: If True, announce menu closed via TTS.
        """
        if self._state == "CLOSED":
            return

        # Custom close logic
        self._on_close()

        # Close menu
        self._state = "CLOSED"
        self._current_options = []
        self._selected_index = 0
        logger.debug("%s closed", self._sender_name)

        # Announce closing
        if speak:
            self._announce_menu_closed()

    def move_selection_up(self) -> bool:
        """Move selection up in the list.

        Returns:
            True if selection moved, False if at top.
        """
        if self._state != "OPEN" or not self._current_options:
            return False

        # Get enabled options
        enabled_options = [opt for opt in self._current_options if opt.enabled]
        if not enabled_options:
            return False

        if self._selected_index > 0:
            self._selected_index -= 1
            self._announce_current_selection()
            return True

        return False

    def move_selection_down(self) -> bool:
        """Move selection down in the list.

        Returns:
            True if selection moved, False if at bottom.
        """
        if self._state != "OPEN" or not self._current_options:
            return False

        # Get enabled options
        enabled_options = [opt for opt in self._current_options if opt.enabled]
        if not enabled_options:
            return False

        if self._selected_index < len(enabled_options) - 1:
            self._selected_index += 1
            self._announce_current_selection()
            return True

        return False

    def select_current(self) -> bool:
        """Select the currently highlighted option.

        Returns:
            True if option was selected successfully, False otherwise.
        """
        if self._state != "OPEN" or not self._current_options:
            return False

        # Get enabled options
        enabled_options = [opt for opt in self._current_options if opt.enabled]
        if not enabled_options:
            return False

        if 0 <= self._selected_index < len(enabled_options):
            selected_option = enabled_options[self._selected_index]
            return self.select_option(selected_option.key)

        return False

    def select_option(self, key: str) -> bool:
        """Select a menu option by key.

        Args:
            key: Option key (e.g., "1", "2", "3").

        Returns:
            True if option was found and selected, False otherwise.
        """
        if self._state != "OPEN":
            logger.warning("%s cannot select option in state: %s", self._sender_name, self._state)
            return False

        # Find option by key
        selected_option = None
        for option in self._current_options:
            if option.key == key and option.enabled:
                selected_option = option
                break

        if not selected_option:
            logger.debug("%s invalid or disabled option: %s", self._sender_name, key)
            self._announce_invalid_option()
            return False

        logger.info("%s selected: %s", self._sender_name, selected_option.label)

        # Handle the selection (subclass-specific logic)
        self._handle_selection(selected_option)

        return True

    def is_open(self) -> bool:
        """Check if menu is currently open.

        Returns:
            True if menu is open.
        """
        return self._state == "OPEN"

    def get_state(self) -> str:
        """Get current menu state.

        Returns:
            Current state string.
        """
        return self._state

    def get_current_options(self) -> list[MenuOption]:
        """Get current menu options.

        Returns:
            Copy of current options list.
        """
        return self._current_options.copy()

    # Abstract methods (must be implemented by subclasses)

    @abstractmethod
    def _build_options(self, context: Any) -> list[MenuOption]:
        """Build menu options based on context.

        Args:
            context: Context for building options (menu-specific).

        Returns:
            List of MenuOption objects.
        """
        pass

    @abstractmethod
    def _handle_selection(self, option: MenuOption) -> None:
        """Handle selection of a menu option.

        Args:
            option: The selected MenuOption.
        """
        pass

    @abstractmethod
    def _get_menu_opened_message(self) -> str:
        """Get TTS message key for menu opened announcement.

        Returns:
            Message key string (e.g., "MSG_MENU_OPENED").
        """
        pass

    @abstractmethod
    def _get_menu_closed_message(self) -> str:
        """Get TTS message key for menu closed announcement.

        Returns:
            Message key string (e.g., "MSG_MENU_CLOSED").
        """
        pass

    @abstractmethod
    def _get_invalid_option_message(self) -> str:
        """Get TTS message key for invalid option announcement.

        Returns:
            Message key string (e.g., "MSG_INVALID_OPTION").
        """
        pass

    # Optional customization hooks

    def _is_available(self, context: Any) -> bool:
        """Check if menu is available to be opened.

        Args:
            context: Context for availability check.

        Returns:
            True if menu can be opened. Default implementation returns True.
        """
        return True

    def _on_open(self, context: Any) -> None:
        """Called after menu opens successfully.

        Args:
            context: Context passed to open().
        """
        pass

    def _on_close(self) -> None:
        """Called before menu closes."""
        pass

    # TTS announcement helpers

    def _announce_menu_opened(self) -> None:
        """Announce menu opening and first option via TTS."""
        if not self._message_queue or not self._current_options:
            return

        # Build message keys: menu opened + first option
        message_keys = [self._get_menu_opened_message()]

        # Add first enabled option
        for option in self._current_options:
            if option.enabled and option.message_key:
                message_keys.append(option.message_key)
                break

        self._speak(message_keys, interrupt=True)

    def _announce_menu_closed(self) -> None:
        """Announce menu closing via TTS."""
        if not self._message_queue:
            return

        self._speak(self._get_menu_closed_message())

    def _announce_current_selection(self) -> None:
        """Announce currently selected option via TTS."""
        if not self._message_queue:
            return

        # Get enabled options
        enabled_options = [opt for opt in self._current_options if opt.enabled]
        if not (0 <= self._selected_index < len(enabled_options)):
            return

        option = enabled_options[self._selected_index]
        if option.message_key:
            # Speak: "Number X option"
            message_keys = [f"MSG_NUMBER_{option.key}", option.message_key]
            self._speak(message_keys, interrupt=True)

    def _announce_invalid_option(self) -> None:
        """Announce invalid option selection via TTS."""
        if not self._message_queue:
            return

        self._speak(self._get_invalid_option_message())

    def _speak(
        self,
        message_keys: str | list[str],
        priority: str = "high",
        interrupt: bool = False,
    ) -> None:
        """Speak message via TTS.

        Args:
            message_keys: Message key or list of keys to speak.
            priority: Priority level (high, normal, low).
            interrupt: Whether to interrupt current speech.
        """
        if not self._message_queue:
            return

        self._message_queue.publish(
            Message(
                sender=self._sender_name,
                recipients=["*"],
                topic=MessageTopic.TTS_SPEAK,
                data={"text": message_keys, "priority": priority, "interrupt": interrupt},
                priority=MessagePriority.HIGH if priority == "high" else MessagePriority.NORMAL,
            )
        )

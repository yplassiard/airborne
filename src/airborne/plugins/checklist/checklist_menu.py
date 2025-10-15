"""Checklist menu system for interactive checklist selection and execution.

This module provides an interactive menu system for viewing available checklists
and executing them with challenge-response verification.

Typical usage example:
    menu = ChecklistMenu(checklist_plugin, tts_provider, message_queue)
    menu.open()  # Show available checklists
    menu.select_option("1")  # Select first checklist
    menu.verify_item()  # Pilot verifies current item
"""

from dataclasses import dataclass
from typing import Any

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageTopic

logger = get_logger(__name__)


@dataclass
class ChecklistMenuOption:
    """Represents a single checklist menu option.

    Attributes:
        key: Key to select this option (e.g., "1", "2").
        checklist_id: ID of the checklist.
        checklist_name: Display name of the checklist.
        description: Brief description.
    """

    key: str
    checklist_id: str
    checklist_name: str
    description: str


class ChecklistMenu:
    """Interactive menu for checklist selection and execution.

    Provides a user-friendly interface for:
    - Browsing available checklists
    - Selecting a checklist to execute
    - Challenge-response item verification
    - Pilot readback with realistic timing

    The menu uses a state machine:
    - CLOSED: Menu not visible
    - CHECKLIST_SELECTION: Showing list of available checklists
    - CHECKLIST_EXECUTION: Executing selected checklist
    """

    def __init__(
        self,
        checklist_plugin: Any,
        tts_provider: Any | None = None,
        message_queue: Any | None = None,
    ):
        """Initialize checklist menu.

        Args:
            checklist_plugin: ChecklistPlugin instance for checklist operations.
            tts_provider: TTS provider for reading menu (deprecated, use message_queue).
            message_queue: Message queue for sending TTS requests.
        """
        self._checklist_plugin = checklist_plugin
        self._tts = tts_provider
        self._message_queue = message_queue
        self._state = "CLOSED"  # CLOSED, CHECKLIST_SELECTION, CHECKLIST_EXECUTION
        self._current_options: list[ChecklistMenuOption] = []
        self._selected_index = 0  # For up/down navigation

        logger.info("Checklist menu initialized")

    def open(self) -> None:
        """Open the checklist menu showing available checklists."""
        # Get available checklists
        checklist_ids = self._checklist_plugin.list_checklists()

        if not checklist_ids:
            logger.warning("No checklists available")
            self._speak_message("MSG_CHECKLIST_NONE_AVAILABLE")
            return

        # Build menu options
        self._current_options = []
        for idx, checklist_id in enumerate(checklist_ids, start=1):
            checklist = self._checklist_plugin.get_checklist(checklist_id)
            if checklist:
                option = ChecklistMenuOption(
                    key=str(idx),
                    checklist_id=checklist.id,
                    checklist_name=checklist.name,
                    description=checklist.description,
                )
                self._current_options.append(option)

        self._state = "CHECKLIST_SELECTION"
        self._selected_index = 0
        logger.info(f"Checklist menu opened with {len(self._current_options)} checklists")

        # Read menu to player
        self.read_menu()

    def close(self, speak: bool = True) -> None:
        """Close the checklist menu.

        Args:
            speak: If True, speak "menu closed" message. Default True.
        """
        if self._state != "CLOSED":
            # If we're executing a checklist, we don't close - just exit selection menu
            if self._state == "CHECKLIST_EXECUTION":
                logger.debug("Cannot close menu during checklist execution")
                return

            self._state = "CLOSED"
            self._current_options = []
            self._selected_index = 0
            logger.debug("Checklist menu closed")

            if speak:
                self._speak_message("MSG_CHECKLIST_MENU_CLOSED")

    def select_option(self, key: str) -> bool:
        """Select a menu option by key (number).

        Args:
            key: Option key (e.g., "1", "2", "3").

        Returns:
            True if option was found and selected, False otherwise.
        """
        if self._state != "CHECKLIST_SELECTION":
            logger.warning(f"Cannot select option, menu state is: {self._state}")
            return False

        # Find option by key
        selected_option = None
        for option in self._current_options:
            if option.key == key:
                selected_option = option
                break

        if not selected_option:
            logger.debug(f"Invalid option selected: {key}")
            self._speak_message("MSG_CHECKLIST_INVALID_OPTION")
            return False

        logger.info(f"Selected checklist: {selected_option.checklist_name}")

        # Start the checklist
        success = self._checklist_plugin.start_checklist(selected_option.checklist_id)

        if success:
            self._state = "CHECKLIST_EXECUTION"
            # Don't close menu immediately - wait for checklist completion
        else:
            self._speak_message("MSG_CHECKLIST_START_FAILED")

        return success

    def move_selection_up(self) -> bool:
        """Move selection up in the list.

        Returns:
            True if selection moved, False if at top.
        """
        if self._state != "CHECKLIST_SELECTION" or not self._current_options:
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
        if self._state != "CHECKLIST_SELECTION" or not self._current_options:
            return False

        if self._selected_index < len(self._current_options) - 1:
            self._selected_index += 1
            self._announce_current_selection()
            return True

        return False

    def select_current(self) -> bool:
        """Select the currently highlighted option.

        Returns:
            True if option was selected, False otherwise.
        """
        if self._state != "CHECKLIST_SELECTION" or not self._current_options:
            return False

        if 0 <= self._selected_index < len(self._current_options):
            selected_option = self._current_options[self._selected_index]
            return self.select_option(selected_option.key)

        return False

    def verify_item(self) -> bool:
        """Pilot verifies the current checklist item.

        This is called when pilot presses a key to verify the item.

        Returns:
            True if item was verified successfully.
        """
        if self._state != "CHECKLIST_EXECUTION":
            return False

        # Complete current item
        success = self._checklist_plugin.complete_current_item(manual=True)

        # If checklist is complete, return to menu
        if not success:
            # Checklist completed
            self._state = "CHECKLIST_SELECTION"
            # Re-open menu to show checklists again
            self.open()

        return success

    def skip_item(self) -> bool:
        """Pilot skips the current checklist item.

        Returns:
            True if item was skipped successfully.
        """
        if self._state != "CHECKLIST_EXECUTION":
            return False

        # Skip current item
        success = self._checklist_plugin.skip_current_item()

        # If checklist is complete, return to menu
        if not success:
            # Checklist completed
            self._state = "CHECKLIST_SELECTION"
            # Re-open menu to show checklists again
            self.open()

        return success

    def read_menu(self) -> None:
        """Read menu options aloud using TTS."""
        if self._state != "CHECKLIST_SELECTION" or not self._current_options:
            return

        # Build list of message keys to speak
        message_keys = ["MSG_CHECKLIST_MENU_OPENED"]

        # Add each checklist option
        for option in self._current_options:
            # Speak: "Number 1: Before Engine Start"
            message_keys.append(f"MSG_NUMBER_{option.key}")
            message_keys.append("MSG_WORD_COLON")
            # Map checklist names to MSG keys
            checklist_msg_key = self._get_checklist_message_key(option.checklist_name)
            message_keys.append(checklist_msg_key)

        message_keys.append("MSG_CHECKLIST_PRESS_ESC")

        logger.debug(f"Reading menu with {len(message_keys)} messages")

        # Speak menu using message queue
        self._speak_message(message_keys)

    def _announce_current_selection(self) -> None:
        """Announce the currently selected option."""
        if not (0 <= self._selected_index < len(self._current_options)):
            return

        option = self._current_options[self._selected_index]
        checklist_msg_key = self._get_checklist_message_key(option.checklist_name)

        # Speak: "Number 1: Before Engine Start"
        message_keys = [
            f"MSG_NUMBER_{option.key}",
            "MSG_WORD_COLON",
            checklist_msg_key,
        ]

        self._speak_message(message_keys)

    def _get_checklist_message_key(self, checklist_name: str) -> str:
        """Get MSG key for checklist name.

        Args:
            checklist_name: Display name of checklist.

        Returns:
            MSG key for TTS.
        """
        # Map common checklist names to MSG keys
        name_to_key = {
            "Before Engine Start": "MSG_CHECKLIST_BEFORE_START",
            "Engine Start": "MSG_CHECKLIST_ENGINE_START",
            "Before Takeoff": "MSG_CHECKLIST_BEFORE_TAKEOFF",
            "Takeoff": "MSG_CHECKLIST_TAKEOFF",
            "Before Landing": "MSG_CHECKLIST_BEFORE_LANDING",
            "After Landing": "MSG_CHECKLIST_AFTER_LANDING",
            "Shutdown": "MSG_CHECKLIST_SHUTDOWN",
        }

        return name_to_key.get(checklist_name, "MSG_CHECKLIST_UNKNOWN")

    def _speak_message(self, message_keys: str | list[str]) -> None:
        """Speak message using message queue.

        Args:
            message_keys: Message key or list of keys.
        """
        if not self._message_queue:
            return

        self._message_queue.publish(
            Message(
                sender="checklist_menu",
                recipients=["*"],
                topic=MessageTopic.TTS_SPEAK,
                data={"text": message_keys, "priority": "high", "interrupt": True},
                priority=MessagePriority.HIGH,
            )
        )

    def is_open(self) -> bool:
        """Check if menu is currently open.

        Returns:
            True if menu is in any open state.
        """
        return self._state != "CLOSED"

    def is_executing_checklist(self) -> bool:
        """Check if currently executing a checklist.

        Returns:
            True if in checklist execution mode.
        """
        return self._state == "CHECKLIST_EXECUTION"

    def get_state(self) -> str:
        """Get current menu state.

        Returns:
            Current state string.
        """
        return self._state

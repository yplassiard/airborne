"""Checklist menu system for interactive checklist selection and execution.

This module provides an interactive menu system for viewing available checklists
and executing them with challenge-response verification.

Typical usage example:
    menu = ChecklistMenu(checklist_plugin, message_queue)
    menu.open()  # Show available checklists
    menu.select_option("1")  # Select first checklist
    menu.verify_item()  # Pilot verifies current item
"""

from typing import Any

from airborne.core.logging_system import get_logger
from airborne.plugins.checklist.checklist_plugin import ChecklistPlugin
from airborne.ui.menu import Menu, MenuOption

logger = get_logger(__name__)


class ChecklistMenu(Menu):
    """Interactive menu for checklist selection and execution.

    Extends the generic Menu base class to provide checklist-specific functionality.
    Provides a user-friendly interface for:
    - Browsing available checklists
    - Selecting a checklist to execute
    - Challenge-response item verification
    - Pilot readback with realistic timing

    The menu uses a state machine:
    - CLOSED: Menu not visible
    - OPEN: Showing list of available checklists (CHECKLIST_SELECTION in old API)
    - CHECKLIST_EXECUTION: Executing selected checklist (additional state)
    """

    def __init__(
        self,
        checklist_plugin: ChecklistPlugin,
        message_queue: Any | None = None,
    ):
        """Initialize checklist menu.

        Args:
            checklist_plugin: ChecklistPlugin instance for checklist operations.
            message_queue: Message queue for sending TTS requests.
        """
        super().__init__(message_queue, sender_name="checklist_menu")

        self._checklist_plugin = checklist_plugin
        self._executing_checklist = False

        logger.info("Checklist menu initialized")

    # Public API methods

    def is_executing_checklist(self) -> bool:
        """Check if currently executing a checklist.

        Returns:
            True if in checklist execution mode.
        """
        return self._executing_checklist

    # Override base methods to handle CHECKLIST_EXECUTION state

    def get_state(self) -> str:
        """Get current menu state.

        Returns:
            Current state string (CLOSED, CHECKLIST_SELECTION, CHECKLIST_EXECUTION).
        """
        if self._executing_checklist:
            return "CHECKLIST_EXECUTION"

        # Map OPEN to CHECKLIST_SELECTION for backward compatibility
        base_state = super().get_state()
        if base_state == "OPEN":
            return "CHECKLIST_SELECTION"
        return base_state

    def is_open(self) -> bool:
        """Check if menu is currently open.

        Returns:
            True if menu is in any open state (selection or execution).
        """
        # Menu is considered "open" during checklist execution too
        return super().is_open() or self._executing_checklist

    def close(self, speak: bool = True) -> None:
        """Close the checklist menu.

        Args:
            speak: If True, speak "menu closed" message. Default True.
        """
        # If we're executing a checklist, we don't close - just exit selection menu
        if self._executing_checklist:
            logger.debug("Cannot close menu during checklist execution")
            return

        super().close(speak)

    # Implement abstract methods from Menu base class

    def _build_options(self, context: Any) -> list[MenuOption]:
        """Build menu options from available checklists.

        Args:
            context: Not used for checklist menu.

        Returns:
            List of MenuOption for available checklists.
        """
        # Get available checklists
        checklist_ids = self._checklist_plugin.list_checklists()

        if not checklist_ids:
            logger.warning("No checklists available")
            return []

        # Build menu options
        options = []
        for idx, checklist_id in enumerate(checklist_ids, start=1):
            checklist = self._checklist_plugin.get_checklist(checklist_id)
            if checklist:
                message_key = self._get_checklist_message_key(checklist.name)
                option = MenuOption(
                    key=str(idx),
                    label=checklist.name,
                    message_key=message_key,
                    data={
                        "checklist_id": checklist.id,
                        "description": checklist.description,
                    },
                )
                options.append(option)

        return options

    def _handle_selection(self, option: MenuOption) -> None:
        """Handle selection of a checklist.

        Args:
            option: The selected MenuOption containing checklist_id in data.
        """
        checklist_id = option.data.get("checklist_id")
        if not checklist_id:
            logger.error("Selected option missing checklist_id")
            return

        logger.info(f"Selected checklist: {option.label}")

        # Start the checklist
        success = self._checklist_plugin.start_checklist(checklist_id)

        if success:
            # Close menu silently and enter execution state
            super().close(speak=False)
            self._executing_checklist = True
            # Don't close menu completely - wait for checklist completion
        else:
            self._speak("MSG_CHECKLIST_START_FAILED")

    def _get_menu_opened_message(self) -> str:
        """Get TTS message key for menu opened.

        Returns:
            Message key string.
        """
        return "MSG_CHECKLIST_MENU_OPENED"

    def _get_menu_closed_message(self) -> str:
        """Get TTS message key for menu closed.

        Returns:
            Message key string.
        """
        return "MSG_CHECKLIST_MENU_CLOSED"

    def _get_invalid_option_message(self) -> str:
        """Get TTS message key for invalid option.

        Returns:
            Message key string.
        """
        return "MSG_CHECKLIST_INVALID_OPTION"

    def _is_available(self, context: Any) -> bool:
        """Check if checklist menu should be available.

        Args:
            context: Not used.

        Returns:
            True if checklists are available.
        """
        # Always available if checklists exist
        return len(self._checklist_plugin.list_checklists()) > 0

    # Checklist-specific methods

    def verify_item(self) -> bool:
        """Pilot verifies the current checklist item.

        This is called when pilot presses a key to verify the item.

        Returns:
            True if item was verified successfully.
        """
        if not self._executing_checklist:
            return False

        # Complete current item
        success = self._checklist_plugin.complete_current_item(manual=True)

        # If checklist is complete, close menu silently
        if not success:
            # Checklist completed - close menu without announcement
            self._executing_checklist = False
            logger.debug("Checklist completed - menu closed automatically")

        return success

    def skip_item(self) -> bool:
        """Pilot skips the current checklist item.

        Returns:
            True if item was skipped successfully.
        """
        if not self._executing_checklist:
            return False

        # Skip current item
        success = self._checklist_plugin.skip_current_item()

        # If checklist is complete, return to menu
        if not success:
            # Checklist completed
            self._executing_checklist = False
            # Re-open menu to show checklists again
            self.open()

        return success

    def cancel_checklist(self) -> bool:
        """Cancel the current checklist (mark as failed).

        Returns:
            True if checklist was cancelled successfully.
        """
        if not self._executing_checklist:
            return False

        # Cancel the active checklist
        success = self._checklist_plugin.cancel_checklist()

        if success:
            # Return to checklist selection
            self._executing_checklist = False
            # Re-open menu to show checklists again
            self.open()

        return success

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
            "Normal Takeoff": "MSG_CHECKLIST_TAKEOFF",
            "Before Landing": "MSG_CHECKLIST_BEFORE_LANDING",
            "After Landing": "MSG_CHECKLIST_AFTER_LANDING",
            "Shutdown": "MSG_CHECKLIST_SHUTDOWN",
            "Engine Shutdown": "MSG_CHECKLIST_SHUTDOWN",
        }

        return name_to_key.get(checklist_name, "MSG_CHECKLIST_UNKNOWN")

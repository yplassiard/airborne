"""Input handler adapter for control panel system.

This adapter wraps the existing ControlPanelPlugin to work with the new
InputHandler interface, allowing the control panel to participate in
priority-based input dispatch.
"""

from typing import Any

from airborne.core.input_event import InputEvent
from airborne.core.input_handler import InputHandler
from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


class ControlPanelInputHandler(InputHandler):
    """Input handler adapter for control panel.

    Wraps a ControlPanelPlugin instance to work with the new InputHandler interface.
    Delegates key handling to the plugin's handle_key_press() method.

    The control panel always participates in input handling (always active),
    but only consumes keys that it handles. The priority system ensures that
    menus get first chance at handling keys.

    Examples:
        >>> control_panel = ControlPanelPlugin()
        >>> handler = ControlPanelInputHandler(
        ...     control_panel=control_panel,
        ...     name="control_panel",
        ...     priority=100
        ... )
        >>> manager.register(handler)
    """

    def __init__(self, control_panel: Any, name: str, priority: int):
        """Initialize control panel input handler.

        Args:
            control_panel: ControlPanelPlugin instance to wrap.
            name: Handler name for debugging.
            priority: Handler priority (lower = higher priority).
        """
        self._control_panel = control_panel
        self._name = name
        self._priority = priority

    def get_priority(self) -> int:
        """Get handler priority."""
        return self._priority

    def can_handle_input(self, event: InputEvent) -> bool:
        """Check if handler can process this event.

        Control panel only handles keyboard events.

        Args:
            event: Input event to check.

        Returns:
            True if this is a keyboard event.
        """
        # Only handle keyboard events
        return event.key is not None

    def handle_input(self, event: InputEvent) -> bool:
        """Handle keyboard input for control panel.

        Delegates to the control panel's handle_key_press() method.

        Args:
            event: Input event to handle.

        Returns:
            True if key was consumed by control panel, False otherwise.
        """
        key = event.key
        mods = event.mods

        # Delegate to control panel
        return self._control_panel.handle_key_press(key, mods)

    def is_active(self) -> bool:
        """Check if handler is active.

        Control panel is always active.

        Returns:
            Always True.
        """
        return True

    def get_name(self) -> str:
        """Get handler name."""
        return self._name

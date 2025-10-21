"""Input handler adapters for legacy code.

This package provides adapter classes that wrap existing input handling
code to work with the new InputHandler interface.
"""

from airborne.adapters.control_panel_input_handler import ControlPanelInputHandler
from airborne.adapters.menu_input_handler import (
    ChecklistMenuInputHandler,
    MenuInputHandler,
)

__all__ = [
    "MenuInputHandler",
    "ChecklistMenuInputHandler",
    "ControlPanelInputHandler",
]

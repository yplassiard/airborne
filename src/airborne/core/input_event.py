"""Input event abstraction for unified handling of keyboard, joystick, controller, and network inputs.

This module provides a common interface for all input types, allowing the same
action to be triggered by multiple input sources (e.g., keyboard key, joystick button,
or network command).

Typical usage:
    # Keyboard event
    event = InputEvent.from_keyboard(pygame.K_F1, pygame.KMOD_NONE)

    # Joystick button event
    event = InputEvent.from_joystick_button(device_id="joy0", button=0)

    # Joystick axis event
    event = InputEvent.from_joystick_axis(device_id="joy0", axis=1, value=0.8)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class InputSourceType(Enum):
    """Type of input source."""

    KEYBOARD = "keyboard"
    JOYSTICK_BUTTON = "joystick_button"
    JOYSTICK_AXIS = "joystick_axis"
    JOYSTICK_HAT = "joystick_hat"
    CONTROLLER_BUTTON = "controller_button"
    CONTROLLER_AXIS = "controller_axis"
    NETWORK = "network"


@dataclass
class InputEvent:
    """Unified input event for all input sources.

    Represents an input event from any source (keyboard, joystick, controller, network).
    Provides a common interface for input handling regardless of the underlying device.

    Attributes:
        source_type: Type of input source.
        device_id: Unique identifier for the input device (e.g., "keyboard", "joy0").
        key: Keyboard key code (pygame constant), None for non-keyboard inputs.
        button: Joystick/controller button number, None for non-button inputs.
        axis: Joystick/controller axis number, None for non-axis inputs.
        axis_value: Value of analog axis (-1.0 to 1.0), 0.0 for non-axis inputs.
        hat: Joystick hat number, None for non-hat inputs.
        hat_value: Hat position as (x, y) tuple, None for non-hat inputs.
        mods: Keyboard modifier flags (pygame constants), 0 for non-keyboard inputs.
        network_command: Network command string, None for non-network inputs.
        metadata: Additional metadata specific to the input source.

    Examples:
        >>> # Keyboard F1 key with no modifiers
        >>> event = InputEvent.from_keyboard(pygame.K_F1, 0)
        >>> event.source_type
        <InputSourceType.KEYBOARD: 'keyboard'>

        >>> # Joystick button 0
        >>> event = InputEvent.from_joystick_button("joy0", 0)
        >>> event.button
        0
    """

    source_type: InputSourceType
    device_id: str
    key: int | None = None
    button: int | None = None
    axis: int | None = None
    axis_value: float = 0.0
    hat: int | None = None
    hat_value: tuple[int, int] | None = None
    mods: int = 0
    network_command: str | None = None
    metadata: dict[str, Any] | None = None

    @classmethod
    def from_keyboard(cls, key: int, mods: int) -> "InputEvent":
        """Create keyboard input event.

        Args:
            key: Pygame key constant (e.g., pygame.K_F1).
            mods: Pygame modifier flags (e.g., pygame.KMOD_CTRL).

        Returns:
            InputEvent for keyboard input.
        """
        return cls(
            source_type=InputSourceType.KEYBOARD,
            device_id="keyboard",
            key=key,
            mods=mods,
        )

    @classmethod
    def from_joystick_button(cls, device_id: str, button: int) -> "InputEvent":
        """Create joystick button input event.

        Args:
            device_id: Unique joystick identifier (e.g., "joy0").
            button: Button number.

        Returns:
            InputEvent for joystick button.
        """
        return cls(
            source_type=InputSourceType.JOYSTICK_BUTTON,
            device_id=device_id,
            button=button,
        )

    @classmethod
    def from_joystick_axis(cls, device_id: str, axis: int, value: float) -> "InputEvent":
        """Create joystick axis input event.

        Args:
            device_id: Unique joystick identifier (e.g., "joy0").
            axis: Axis number (0=X, 1=Y, etc.).
            value: Axis value in range -1.0 to 1.0.

        Returns:
            InputEvent for joystick axis.
        """
        return cls(
            source_type=InputSourceType.JOYSTICK_AXIS,
            device_id=device_id,
            axis=axis,
            axis_value=value,
        )

    @classmethod
    def from_joystick_hat(cls, device_id: str, hat: int, value: tuple[int, int]) -> "InputEvent":
        """Create joystick hat (D-pad) input event.

        Args:
            device_id: Unique joystick identifier (e.g., "joy0").
            hat: Hat number.
            value: Hat position as (x, y) tuple, each -1, 0, or 1.

        Returns:
            InputEvent for joystick hat.
        """
        return cls(
            source_type=InputSourceType.JOYSTICK_HAT,
            device_id=device_id,
            hat=hat,
            hat_value=value,
        )

    @classmethod
    def from_network(cls, command: str, metadata: dict[str, Any] | None = None) -> "InputEvent":
        """Create network input event.

        Args:
            command: Network command string (e.g., "MENU_ATC").
            metadata: Additional metadata from network source.

        Returns:
            InputEvent for network input.
        """
        return cls(
            source_type=InputSourceType.NETWORK,
            device_id="network",
            network_command=command,
            metadata=metadata,
        )

    def matches_keyboard(self, key: int, mods: int = 0) -> bool:
        """Check if event matches keyboard key/modifier combo.

        Args:
            key: Pygame key constant.
            mods: Pygame modifier flags (optional).

        Returns:
            True if event matches the specified key/mods.
        """
        if self.source_type != InputSourceType.KEYBOARD:
            return False
        if self.key != key:
            return False
        return not (mods and not self.mods & mods)

    def matches_button(self, button: int, device_id: str | None = None) -> bool:
        """Check if event matches joystick/controller button.

        Args:
            button: Button number.
            device_id: Optional device ID to match specific device.

        Returns:
            True if event matches the specified button.
        """
        if self.source_type not in (
            InputSourceType.JOYSTICK_BUTTON,
            InputSourceType.CONTROLLER_BUTTON,
        ):
            return False
        if self.button != button:
            return False
        return not (device_id and self.device_id != device_id)

    def matches_axis(self, axis: int, threshold: float = 0.5, device_id: str | None = None) -> bool:
        """Check if event matches joystick/controller axis above threshold.

        Args:
            axis: Axis number.
            threshold: Minimum absolute value to consider active (default 0.5).
            device_id: Optional device ID to match specific device.

        Returns:
            True if event matches axis and value exceeds threshold.
        """
        if self.source_type not in (
            InputSourceType.JOYSTICK_AXIS,
            InputSourceType.CONTROLLER_AXIS,
        ):
            return False
        if self.axis != axis:
            return False
        if abs(self.axis_value) < threshold:
            return False
        return not (device_id and self.device_id != device_id)

    def matches_network_command(self, command: str) -> bool:
        """Check if event matches network command.

        Args:
            command: Command string to match.

        Returns:
            True if event matches the specified command.
        """
        if self.source_type != InputSourceType.NETWORK:
            return False
        return self.network_command == command

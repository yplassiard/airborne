"""Action binding system for mapping inputs to actions.

This module provides a system for binding multiple input sources to named actions.
For example, the "MENU_ATC" action could be triggered by:
- F1 keyboard key
- Joystick button 0
- Network command "open_atc_menu"

Typical usage:
    binding = ActionBinding(
        action="MENU_ATC",
        bindings=[
            InputBinding.from_keyboard(pygame.K_F1),
            InputBinding.from_joystick_button("joy0", 0),
        ]
    )

    event = InputEvent.from_keyboard(pygame.K_F1, 0)
    if binding.matches(event):
        print("ATC menu action triggered!")
"""

from dataclasses import dataclass

from airborne.core.input_event import InputEvent, InputSourceType


@dataclass
class InputBinding:
    """Defines a single input that can trigger an action.

    An InputBinding represents one way to trigger an action (e.g., press F1 key).
    Multiple InputBindings can be associated with a single action.

    Attributes:
        source_type: Type of input source.
        key: Keyboard key code (for keyboard inputs).
        mods: Keyboard modifiers (for keyboard inputs).
        button: Button number (for joystick/controller inputs).
        axis: Axis number (for analog inputs).
        axis_threshold: Minimum axis value to trigger (for analog inputs).
        axis_direction: Direction for axis ("positive" or "negative").
        device_id: Device identifier (None = any device).
        network_command: Network command string (for network inputs).

    Examples:
        >>> # F1 key binding
        >>> binding = InputBinding.from_keyboard(pygame.K_F1)

        >>> # Joystick button 0 on any device
        >>> binding = InputBinding.from_joystick_button(button=0)

        >>> # Right stick up on specific controller
        >>> binding = InputBinding.from_joystick_axis(
        ...     axis=3, threshold=0.5, direction="positive", device_id="joy0"
        ... )
    """

    source_type: InputSourceType
    key: int | None = None
    mods: int = 0
    button: int | None = None
    axis: int | None = None
    axis_threshold: float = 0.5
    axis_direction: str = "positive"  # "positive", "negative", or "both"
    device_id: str | None = None
    network_command: str | None = None

    @classmethod
    def from_keyboard(cls, key: int, mods: int = 0) -> "InputBinding":
        """Create keyboard input binding.

        Args:
            key: Pygame key constant.
            mods: Pygame modifier flags (optional).

        Returns:
            InputBinding for keyboard input.
        """
        return cls(source_type=InputSourceType.KEYBOARD, key=key, mods=mods)

    @classmethod
    def from_joystick_button(cls, button: int, device_id: str | None = None) -> "InputBinding":
        """Create joystick button input binding.

        Args:
            button: Button number.
            device_id: Optional device ID (None = any device).

        Returns:
            InputBinding for joystick button.
        """
        return cls(
            source_type=InputSourceType.JOYSTICK_BUTTON,
            button=button,
            device_id=device_id,
        )

    @classmethod
    def from_joystick_axis(
        cls,
        axis: int,
        threshold: float = 0.5,
        direction: str = "positive",
        device_id: str | None = None,
    ) -> "InputBinding":
        """Create joystick axis input binding.

        Args:
            axis: Axis number.
            threshold: Minimum absolute value to trigger (default 0.5).
            direction: Axis direction ("positive", "negative", or "both").
            device_id: Optional device ID (None = any device).

        Returns:
            InputBinding for joystick axis.
        """
        return cls(
            source_type=InputSourceType.JOYSTICK_AXIS,
            axis=axis,
            axis_threshold=threshold,
            axis_direction=direction,
            device_id=device_id,
        )

    @classmethod
    def from_network(cls, command: str) -> "InputBinding":
        """Create network input binding.

        Args:
            command: Network command string.

        Returns:
            InputBinding for network input.
        """
        return cls(source_type=InputSourceType.NETWORK, network_command=command)

    def matches(self, event: InputEvent) -> bool:
        """Check if input event matches this binding.

        Args:
            event: Input event to check.

        Returns:
            True if event matches this binding.
        """
        # Check source type
        if event.source_type != self.source_type:
            return False

        # Check device ID if specified
        if self.device_id and event.device_id != self.device_id:
            return False

        # Type-specific matching
        if self.source_type == InputSourceType.KEYBOARD:
            return self._matches_keyboard(event)
        elif self.source_type in (
            InputSourceType.JOYSTICK_BUTTON,
            InputSourceType.CONTROLLER_BUTTON,
        ):
            return self._matches_button(event)
        elif self.source_type in (
            InputSourceType.JOYSTICK_AXIS,
            InputSourceType.CONTROLLER_AXIS,
        ):
            return self._matches_axis(event)
        elif self.source_type == InputSourceType.NETWORK:
            return self._matches_network(event)

        return False

    def _matches_keyboard(self, event: InputEvent) -> bool:
        """Check keyboard event match."""
        if event.key != self.key:
            return False
        # If mods specified, check them; otherwise ignore
        return not (self.mods and not event.mods & self.mods)

    def _matches_button(self, event: InputEvent) -> bool:
        """Check button event match."""
        return event.button == self.button

    def _matches_axis(self, event: InputEvent) -> bool:
        """Check axis event match."""
        if event.axis != self.axis:
            return False

        # Check threshold and direction
        if abs(event.axis_value) < self.axis_threshold:
            return False

        return not (
            self.axis_direction == "positive"
            and event.axis_value < 0
            or self.axis_direction == "negative"
            and event.axis_value > 0
        )

    def _matches_network(self, event: InputEvent) -> bool:
        """Check network event match."""
        return event.network_command == self.network_command


@dataclass
class ActionBinding:
    """Maps an action name to multiple input bindings.

    An ActionBinding represents a named action (e.g., "MENU_ATC") that can be
    triggered by multiple input sources.

    Attributes:
        action: Action name (e.g., "MENU_ATC", "FLIGHT_PITCH_UP").
        bindings: List of InputBinding that can trigger this action.
        enabled: Whether this action binding is currently enabled.

    Examples:
        >>> # ATC menu can be triggered by F1 or joystick button 0
        >>> binding = ActionBinding(
        ...     action="MENU_ATC",
        ...     bindings=[
        ...         InputBinding.from_keyboard(pygame.K_F1),
        ...         InputBinding.from_joystick_button(0),
        ...     ]
        ... )
        >>> event = InputEvent.from_keyboard(pygame.K_F1, 0)
        >>> if binding.matches(event):
        ...     print("ATC menu triggered!")
    """

    action: str
    bindings: list[InputBinding]
    enabled: bool = True

    def matches(self, event: InputEvent) -> bool:
        """Check if input event matches any binding for this action.

        Args:
            event: Input event to check.

        Returns:
            True if event matches any binding and action is enabled.
        """
        if not self.enabled:
            return False

        return any(binding.matches(event) for binding in self.bindings)

    def add_binding(self, binding: InputBinding) -> None:
        """Add a new input binding to this action.

        Args:
            binding: InputBinding to add.
        """
        self.bindings.append(binding)

    def remove_binding(self, binding: InputBinding) -> None:
        """Remove an input binding from this action.

        Args:
            binding: InputBinding to remove.

        Raises:
            ValueError: If binding not found.
        """
        self.bindings.remove(binding)

    def clear_bindings(self) -> None:
        """Remove all bindings from this action."""
        self.bindings.clear()

    def enable(self) -> None:
        """Enable this action binding."""
        self.enabled = True

    def disable(self) -> None:
        """Disable this action binding."""
        self.enabled = False


class ActionBindingRegistry:
    """Registry for managing action bindings.

    Provides central management of all action bindings in the application,
    allowing actions to be looked up by name and input events to be matched
    to actions.

    Examples:
        >>> registry = ActionBindingRegistry()
        >>> registry.register(ActionBinding(
        ...     action="MENU_ATC",
        ...     bindings=[InputBinding.from_keyboard(pygame.K_F1)]
        ... ))
        >>> event = InputEvent.from_keyboard(pygame.K_F1, 0)
        >>> actions = registry.get_matching_actions(event)
        >>> print(actions)  # ['MENU_ATC']
    """

    def __init__(self):
        """Initialize action binding registry."""
        self._bindings: dict[str, ActionBinding] = {}

    def register(self, binding: ActionBinding) -> None:
        """Register an action binding.

        Args:
            binding: ActionBinding to register.

        Raises:
            ValueError: If action already registered.
        """
        if binding.action in self._bindings:
            raise ValueError(f"Action '{binding.action}' already registered")
        self._bindings[binding.action] = binding

    def unregister(self, action: str) -> None:
        """Unregister an action binding.

        Args:
            action: Action name to unregister.

        Raises:
            ValueError: If action not found.
        """
        if action not in self._bindings:
            raise ValueError(f"Action '{action}' not found")
        del self._bindings[action]

    def get_binding(self, action: str) -> ActionBinding | None:
        """Get action binding by name.

        Args:
            action: Action name.

        Returns:
            ActionBinding or None if not found.
        """
        return self._bindings.get(action)

    def get_matching_actions(self, event: InputEvent) -> list[str]:
        """Get all actions that match the input event.

        Args:
            event: Input event to match.

        Returns:
            List of action names that match the event.
        """
        actions = []
        for action, binding in self._bindings.items():
            if binding.matches(event):
                actions.append(action)
        return actions

    def get_all_actions(self) -> list[str]:
        """Get list of all registered action names.

        Returns:
            List of action name strings.
        """
        return list(self._bindings.keys())

    def clear(self) -> None:
        """Remove all action bindings."""
        self._bindings.clear()

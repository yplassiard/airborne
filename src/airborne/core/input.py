"""Input management system for keyboard and joystick input.

This module provides input handling with configurable key bindings and
support for keyboard and joystick controls. Input events are published
to the event bus for consumption by other systems.

Performance optimizations:
- Efficient key state tracking
- Debouncing for discrete actions
- Smooth analog input handling

Typical usage example:
    from airborne.core.input import InputManager, InputConfig
    from airborne.core.event_bus import EventBus

    event_bus = EventBus()
    config = InputConfig()
    input_manager = InputManager(event_bus, config)

    # In game loop
    input_manager.process_events(pygame_events)
    input_manager.update(dt)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any  # noqa: F401

import pygame  # pylint: disable=no-member

from airborne.core.event_bus import Event, EventBus
from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


@dataclass
class InputStateEvent(Event):
    """Event published when input state is updated.

    Attributes:
        pitch: Pitch control (-1.0 to 1.0).
        roll: Roll control (-1.0 to 1.0).
        yaw: Yaw control (-1.0 to 1.0).
        throttle: Throttle setting (0.0 to 1.0).
        brakes: Brake application (0.0 to 1.0).
        flaps: Flap position (0.0 to 1.0).
        gear: Gear position (0.0 to 1.0).
    """

    pitch: float = 0.0
    roll: float = 0.0
    yaw: float = 0.0
    throttle: float = 0.0
    brakes: float = 0.0
    flaps: float = 0.0
    gear: float = 1.0


@dataclass
class InputActionEvent(Event):
    """Event published when a discrete input action occurs.

    Attributes:
        action: The input action that occurred.
        value: Optional numeric value for the action.
    """

    action: str = ""
    value: float | None = None


class InputAction(Enum):
    """Input actions that can be bound to keys.

    Each action represents a logical game input that can be triggered
    by different physical inputs (keys, buttons, axes).
    """

    # Flight controls
    PITCH_UP = "pitch_up"
    PITCH_DOWN = "pitch_down"
    ROLL_LEFT = "roll_left"
    ROLL_RIGHT = "roll_right"
    YAW_LEFT = "yaw_left"
    YAW_RIGHT = "yaw_right"
    THROTTLE_INCREASE = "throttle_increase"
    THROTTLE_DECREASE = "throttle_decrease"
    THROTTLE_FULL = "throttle_full"
    THROTTLE_IDLE = "throttle_idle"

    # Brakes and gear
    BRAKES = "brakes"
    PARKING_BRAKE = "parking_brake"
    GEAR_TOGGLE = "gear_toggle"

    # Flaps
    FLAPS_UP = "flaps_up"
    FLAPS_DOWN = "flaps_down"

    # View controls
    VIEW_NEXT = "view_next"
    VIEW_PREV = "view_prev"

    # TTS controls
    TTS_NEXT = "tts_next"
    TTS_REPEAT = "tts_repeat"
    TTS_INTERRUPT = "tts_interrupt"

    # Menu controls
    MENU_TOGGLE = "menu_toggle"
    MENU_UP = "menu_up"
    MENU_DOWN = "menu_down"
    MENU_SELECT = "menu_select"
    MENU_BACK = "menu_back"

    # Instrument readouts
    READ_AIRSPEED = "read_airspeed"
    READ_ALTITUDE = "read_altitude"
    READ_HEADING = "read_heading"
    READ_VSPEED = "read_vspeed"
    READ_ATTITUDE = "read_attitude"  # Bank and pitch angles

    # System controls
    PAUSE = "pause"
    QUIT = "quit"


@dataclass
class InputConfig:
    """Configuration for input system.

    Attributes:
        keyboard_bindings: Map of pygame key constants to InputAction.
        axis_sensitivity: Sensitivity multiplier for analog axes (0.0-2.0).
        axis_deadzone: Deadzone for analog axes (0.0-1.0).
        throttle_increment: Amount to change throttle per keypress (0.0-1.0).
        enable_joystick: Whether to enable joystick input.
    """

    keyboard_bindings: dict[int, InputAction] = field(default_factory=dict)
    axis_sensitivity: float = 1.0
    axis_deadzone: float = 0.1
    throttle_increment: float = 0.05
    enable_joystick: bool = True

    def __post_init__(self) -> None:
        """Initialize default key bindings if not provided."""
        if not self.keyboard_bindings:
            self.keyboard_bindings = self._get_default_bindings()

    def _get_default_bindings(self) -> dict[int, InputAction]:
        """Get default keyboard bindings.

        Returns:
            Dictionary mapping pygame keys to input actions.
        """
        return {
            # Flight controls
            pygame.K_UP: InputAction.PITCH_DOWN,
            pygame.K_DOWN: InputAction.PITCH_UP,
            pygame.K_LEFT: InputAction.ROLL_LEFT,
            pygame.K_RIGHT: InputAction.ROLL_RIGHT,
            pygame.K_q: InputAction.YAW_LEFT,
            pygame.K_e: InputAction.YAW_RIGHT,
            pygame.K_HOME: InputAction.THROTTLE_INCREASE,
            pygame.K_END: InputAction.THROTTLE_DECREASE,
            pygame.K_PAGEUP: InputAction.THROTTLE_FULL,
            pygame.K_PAGEDOWN: InputAction.THROTTLE_IDLE,
            # Brakes and gear
            pygame.K_b: InputAction.BRAKES,
            pygame.K_p: InputAction.PARKING_BRAKE,
            pygame.K_g: InputAction.GEAR_TOGGLE,
            # Flaps
            pygame.K_LEFTBRACKET: InputAction.FLAPS_UP,
            pygame.K_RIGHTBRACKET: InputAction.FLAPS_DOWN,
            # View
            pygame.K_v: InputAction.VIEW_NEXT,
            pygame.K_c: InputAction.VIEW_PREV,
            # Instrument readouts
            pygame.K_s: InputAction.READ_AIRSPEED,  # S for Speed
            pygame.K_l: InputAction.READ_ALTITUDE,  # L for aLtitude
            pygame.K_h: InputAction.READ_HEADING,  # H for Heading
            pygame.K_w: InputAction.READ_VSPEED,  # W for Vertical speed (up/down)
            pygame.K_t: InputAction.READ_ATTITUDE,  # T for aTtitude (bank/pitch)
            # TTS
            pygame.K_n: InputAction.TTS_NEXT,  # N for Next
            pygame.K_r: InputAction.TTS_REPEAT,  # R for Repeat
            pygame.K_i: InputAction.TTS_INTERRUPT,  # I for Interrupt
            # Menu
            pygame.K_TAB: InputAction.MENU_TOGGLE,
            pygame.K_a: InputAction.MENU_UP,
            pygame.K_z: InputAction.MENU_DOWN,
            pygame.K_RETURN: InputAction.MENU_SELECT,
            pygame.K_BACKSPACE: InputAction.MENU_BACK,
            # System
            pygame.K_SPACE: InputAction.PAUSE,
            pygame.K_ESCAPE: InputAction.QUIT,
        }


@dataclass
class InputState:
    """Current state of all input controls.

    This represents the processed input state after applying
    deadz ones, sensitivity, and combining multiple sources.

    Attributes:
        pitch: Pitch control (-1.0 to 1.0).
        roll: Roll control (-1.0 to 1.0).
        yaw: Yaw control (-1.0 to 1.0).
        throttle: Throttle setting (0.0 to 1.0).
        brakes: Brake application (0.0 to 1.0).
        flaps: Flap position (0.0 to 1.0).
        gear: Gear position (0.0 = up, 1.0 = down).
    """

    pitch: float = 0.0
    roll: float = 0.0
    yaw: float = 0.0
    throttle: float = 0.0
    brakes: float = 0.0
    flaps: float = 0.0
    gear: float = 1.0  # Default gear down

    def clamp_all(self) -> None:
        """Clamp all values to valid ranges."""
        self.pitch = max(-1.0, min(1.0, self.pitch))
        self.roll = max(-1.0, min(1.0, self.roll))
        self.yaw = max(-1.0, min(1.0, self.yaw))
        self.throttle = max(0.0, min(1.0, self.throttle))
        self.brakes = max(0.0, min(1.0, self.brakes))
        self.flaps = max(0.0, min(1.0, self.flaps))
        self.gear = max(0.0, min(1.0, self.gear))


class InputManager:  # pylint: disable=too-many-instance-attributes
    """Manages input from keyboard and joystick.

    Processes input events, maintains input state, and publishes
    input events to the event bus. Supports configurable key bindings
    and joystick configuration.

    Examples:
        >>> event_bus = EventBus()
        >>> config = InputConfig()
        >>> manager = InputManager(event_bus, config)
        >>> manager.process_events(pygame_events)
        >>> manager.update(dt)
        >>> state = manager.get_state()
        >>> print(f"Throttle: {state.throttle:.2f}")
    """

    def __init__(self, event_bus: EventBus, config: InputConfig | None = None) -> None:
        """Initialize input manager.

        Args:
            event_bus: Event bus for publishing input events.
            config: Input configuration (uses defaults if None).
        """
        self.event_bus = event_bus
        self.config = config if config is not None else InputConfig()

        # Current input state
        self.state = InputState()

        # Key press state tracking
        self._keys_pressed: set[int] = set()
        self._keys_just_pressed: set[int] = set()
        self._keys_just_released: set[int] = set()

        # Track which actions have been triggered during current key hold
        # Used to prevent non-repeatable actions from repeating
        self._actions_triggered: set[InputAction] = set()

        # Define which actions allow key repeat (levers/sliders)
        # All other actions are one-shot (switches)
        self._repeatable_actions: set[InputAction] = {
            InputAction.THROTTLE_INCREASE,
            InputAction.THROTTLE_DECREASE,
            InputAction.FLAPS_UP,
            InputAction.FLAPS_DOWN,
        }

        # Joystick support
        self.joystick: Any = None  # pygame.joystick.Joystick | None
        self._initialize_joystick()

        # Throttle smoothing
        self._target_throttle = 0.0

        logger.info(
            "Input manager initialized with %d key bindings", len(self.config.keyboard_bindings)
        )

    def _initialize_joystick(self) -> None:
        """Initialize joystick if available and enabled."""
        if not self.config.enable_joystick:
            return

        pygame.joystick.init()
        joystick_count = pygame.joystick.get_count()

        if joystick_count > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            logger.info(
                "Joystick initialized: %s (%d axes, %d buttons)",
                self.joystick.get_name(),
                self.joystick.get_numaxes(),
                self.joystick.get_numbuttons(),
            )
        else:
            logger.debug("No joystick detected")

    def process_events(self, events: list[pygame.event.Event]) -> None:
        """Process pygame events.

        Args:
            events: List of pygame events from event queue.
        """
        # Clear per-frame input tracking
        self._keys_just_pressed.clear()
        self._keys_just_released.clear()

        for event in events:
            if event.type == pygame.KEYDOWN:
                self._handle_key_down(event.key)
            elif event.type == pygame.KEYUP:
                self._handle_key_up(event.key)
            elif event.type == pygame.JOYBUTTONDOWN:
                self._handle_joy_button_down(event.button)
            elif event.type == pygame.JOYBUTTONUP:
                self._handle_joy_button_up(event.button)

    def _handle_key_down(self, key: int) -> None:
        """Handle key press event.

        Args:
            key: Pygame key constant.
        """
        is_repeat = key in self._keys_pressed

        self._keys_pressed.add(key)
        if not is_repeat:
            self._keys_just_pressed.add(key)

        # Check for bound action
        action = self.config.keyboard_bindings.get(key)
        if action:
            # For key repeat events, only trigger repeatable actions
            if is_repeat:
                if action not in self._repeatable_actions:
                    return  # Skip non-repeatable actions on repeat
            else:
                # First press: clear previous trigger state for this action
                self._actions_triggered.discard(action)

            # Check if this non-repeatable action was already triggered
            if action not in self._repeatable_actions:
                if action in self._actions_triggered:
                    return  # Already triggered, don't repeat
                self._actions_triggered.add(action)

            self._handle_action_pressed(action)

    def _handle_key_up(self, key: int) -> None:
        """Handle key release event.

        Args:
            key: Pygame key constant.
        """
        if key not in self._keys_pressed:
            return  # Not pressed

        self._keys_pressed.discard(key)
        self._keys_just_released.add(key)

        # Check for bound action
        action = self.config.keyboard_bindings.get(key)
        if action:
            # Clear trigger state for non-repeatable actions
            self._actions_triggered.discard(action)
            self._handle_action_released(action)

    def _handle_action_pressed(self, action: InputAction) -> None:
        """Handle action press.

        Args:
            action: Input action that was triggered.
        """
        # Continuous controls (handled in update)
        if action in (
            InputAction.PITCH_UP,
            InputAction.PITCH_DOWN,
            InputAction.ROLL_LEFT,
            InputAction.ROLL_RIGHT,
            InputAction.YAW_LEFT,
            InputAction.YAW_RIGHT,
        ):
            return  # Handled in update loop

        # Discrete controls
        if action == InputAction.THROTTLE_INCREASE:
            self._target_throttle = min(1.0, self._target_throttle + self.config.throttle_increment)
            self.event_bus.publish(
                InputActionEvent(action=action.value, value=self._target_throttle)
            )
        elif action == InputAction.THROTTLE_DECREASE:
            self._target_throttle = max(0.0, self._target_throttle - self.config.throttle_increment)
            self.event_bus.publish(
                InputActionEvent(action=action.value, value=self._target_throttle)
            )
        elif action == InputAction.THROTTLE_FULL:
            self._target_throttle = 1.0
            self.event_bus.publish(
                InputActionEvent(action=action.value, value=self._target_throttle)
            )
        elif action == InputAction.THROTTLE_IDLE:
            self._target_throttle = 0.0
            self.event_bus.publish(
                InputActionEvent(action=action.value, value=self._target_throttle)
            )
        elif action == InputAction.GEAR_TOGGLE:
            self.state.gear = 0.0 if self.state.gear > 0.5 else 1.0
            self.event_bus.publish(InputActionEvent(action=action.value, value=self.state.gear))
        elif action == InputAction.FLAPS_UP:
            self.state.flaps = max(0.0, self.state.flaps - 0.25)
            self.event_bus.publish(InputActionEvent(action=action.value, value=self.state.flaps))
        elif action == InputAction.FLAPS_DOWN:
            self.state.flaps = min(1.0, self.state.flaps + 0.25)
            self.event_bus.publish(InputActionEvent(action=action.value, value=self.state.flaps))
        else:
            # Publish discrete action events (menu, TTS, etc.)
            self.event_bus.publish(InputActionEvent(action=action.value))

    def _handle_action_released(self, action: InputAction) -> None:
        """Handle action release.

        Args:
            action: Input action that was released.
        """
        # Brakes are released when key is released
        if action == InputAction.BRAKES:
            self.state.brakes = 0.0

    def _handle_joy_button_down(self, button: int) -> None:
        """Handle joystick button press.

        Args:
            button: Joystick button index.
        """
        # Joystick button mapping to be implemented in future
        logger.debug("Joystick button %d pressed", button)

    def _handle_joy_button_up(self, button: int) -> None:
        """Handle joystick button release.

        Args:
            button: Joystick button index.
        """
        logger.debug("Joystick button %d released", button)

    def update(self, dt: float) -> None:
        """Update input state.

        Called once per frame to update continuous controls and
        apply smoothing.

        Args:
            dt: Delta time in seconds.
        """
        # Update continuous keyboard controls
        self._update_keyboard_controls()

        # Update joystick controls
        if self.joystick:
            self._update_joystick_controls()

        # Smooth throttle changes
        if abs(self._target_throttle - self.state.throttle) > 0.001:
            # Smooth transition to target throttle
            throttle_rate = 2.0  # units per second
            delta = self._target_throttle - self.state.throttle
            max_change = throttle_rate * dt
            change = max(-max_change, min(max_change, delta))
            self.state.throttle += change

        # Clamp all values
        self.state.clamp_all()

        # Publish state update
        self.event_bus.publish(
            InputStateEvent(
                pitch=self.state.pitch,
                roll=self.state.roll,
                yaw=self.state.yaw,
                throttle=self.state.throttle,
                brakes=self.state.brakes,
                flaps=self.state.flaps,
                gear=self.state.gear,
            )
        )

    def _update_keyboard_controls(self) -> None:
        """Update continuous controls from keyboard."""
        # Reset continuous controls
        pitch = 0.0
        roll = 0.0
        yaw = 0.0
        brakes = 0.0

        # Check which keys are currently held
        for key in self._keys_pressed:
            action = self.config.keyboard_bindings.get(key)
            if not action:
                continue

            if action == InputAction.PITCH_UP:
                pitch += 1.0
            elif action == InputAction.PITCH_DOWN:
                pitch -= 1.0
            elif action == InputAction.ROLL_LEFT:
                roll -= 1.0
            elif action == InputAction.ROLL_RIGHT:
                roll += 1.0
            elif action == InputAction.YAW_LEFT:
                yaw -= 1.0
            elif action == InputAction.YAW_RIGHT:
                yaw += 1.0
            elif action == InputAction.BRAKES:
                brakes = 1.0

        # Update state
        self.state.pitch = pitch
        self.state.roll = roll
        self.state.yaw = yaw
        self.state.brakes = brakes

    def _update_joystick_controls(self) -> None:
        """Update controls from joystick axes."""
        if not self.joystick:
            return

        # Typical joystick layout:
        # Axis 0: Roll (X)
        # Axis 1: Pitch (Y)
        # Axis 2: Throttle or Yaw
        # Axis 3: Yaw or Throttle

        if self.joystick.get_numaxes() >= 2:
            # Roll from axis 0
            roll_raw = self.joystick.get_axis(0)
            self.state.roll = self._apply_deadzone(roll_raw)

            # Pitch from axis 1 (inverted)
            pitch_raw = -self.joystick.get_axis(1)
            self.state.pitch = self._apply_deadzone(pitch_raw)

        if self.joystick.get_numaxes() >= 4:
            # Yaw from axis 3
            yaw_raw = self.joystick.get_axis(3)
            self.state.yaw = self._apply_deadzone(yaw_raw)

    def _apply_deadzone(self, value: float) -> float:
        """Apply deadzone and sensitivity to axis value.

        Args:
            value: Raw axis value (-1.0 to 1.0).

        Returns:
            Processed value with deadzone and sensitivity applied.
        """
        # Apply deadzone
        if abs(value) < self.config.axis_deadzone:
            return 0.0

        # Remap range outside deadzone to full range
        sign = 1.0 if value > 0 else -1.0
        magnitude = (abs(value) - self.config.axis_deadzone) / (1.0 - self.config.axis_deadzone)

        # Apply sensitivity
        return sign * magnitude * self.config.axis_sensitivity

    def get_state(self) -> InputState:
        """Get current input state.

        Returns:
            Current input state (reference, not copy).
        """
        return self.state

    def is_action_pressed(self, action: InputAction) -> bool:
        """Check if an action is currently pressed.

        Args:
            action: Action to check.

        Returns:
            True if action is currently pressed.
        """
        # Find keys bound to this action
        for key, bound_action in self.config.keyboard_bindings.items():
            if bound_action == action and key in self._keys_pressed:
                return True
        return False

    def is_action_just_pressed(self, action: InputAction) -> bool:
        """Check if an action was just pressed this frame.

        Args:
            action: Action to check.

        Returns:
            True if action was just pressed.
        """
        for key, bound_action in self.config.keyboard_bindings.items():
            if bound_action == action and key in self._keys_just_pressed:
                return True
        return False

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
from pathlib import Path
from typing import Any  # noqa: F401

import pygame  # pylint: disable=no-member

from airborne.core.event_bus import Event, EventBus
from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageQueue, MessageTopic

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
    # Trim positions stored in DEGREES (aircraft-specific range)
    # Positive = nose up / right, Negative = nose down / left
    pitch_trim_deg: float = 0.0  # Pitch trim in degrees (e.g., -10° to +20° for C172)
    rudder_trim_deg: float = 0.0  # Rudder trim in degrees (e.g., -15° to +15°)
    # Legacy normalized values for backward compatibility (computed from degrees)
    pitch_trim: float = 0.0  # Normalized pitch trim (-1.0 to 1.0) - DEPRECATED
    rudder_trim: float = 0.0  # Normalized rudder trim (-1.0 to 1.0) - DEPRECATED


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
    PARKING_BRAKE_SET = "parking_brake_set"
    PARKING_BRAKE_RELEASE = "parking_brake_release"
    GEAR_TOGGLE = "gear_toggle"

    # Flaps (discrete positions)
    FLAPS_UP = "flaps_up"
    FLAPS_DOWN = "flaps_down"
    FLAPS_READ = "flaps_read"  # Announce current flap position

    # Auto-trim controls
    AUTO_TRIM_ENABLE = "auto_trim_enable"  # Enable auto-trim (Shift+T)
    AUTO_TRIM_DISABLE = "auto_trim_disable"  # Disable auto-trim (Ctrl+T)
    AUTO_TRIM_READ = "auto_trim_read"  # Read auto-trim status (T)

    # Trim controls
    TRIM_PITCH_UP = "trim_pitch_up"  # Roll trim wheel back (nose up)
    TRIM_PITCH_DOWN = "trim_pitch_down"  # Roll trim wheel forward (nose down)
    TRIM_RUDDER_LEFT = "trim_rudder_left"  # Twist rudder trim left
    TRIM_RUDDER_RIGHT = "trim_rudder_right"  # Twist rudder trim right

    # Flight instructor controls
    INSTRUCTOR_ENABLE = "instructor_enable"  # Enable flight instructor (Shift+F9)
    INSTRUCTOR_DISABLE = "instructor_disable"  # Disable flight instructor (Ctrl+F9)
    INSTRUCTOR_ASSESSMENT = "instructor_assessment"  # Request on-demand assessment (F9)

    # Control centering
    CENTER_CONTROLS = "center_controls"  # Center pitch/roll/yaw (Right Shift)

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
    READ_ENGINE = "read_engine"  # Engine status (RPM, manifold pressure, etc.)
    READ_ELECTRICAL = "read_electrical"  # Electrical status (battery, alternator)
    READ_FUEL = "read_fuel"  # Fuel status (quantity, consumption, remaining time)
    READ_PITCH_TRIM = "read_pitch_trim"  # Read current pitch trim position
    READ_RUDDER_TRIM = "read_rudder_trim"  # Read current rudder trim position

    # Radio frequency controls (legacy F11/F12 system)
    COM1_TUNE_UP = "com1_tune_up"  # F12 - Increase COM1 frequency
    COM1_TUNE_DOWN = "com1_tune_down"  # Shift+F12 - Decrease COM1 frequency
    COM1_SWAP = "com1_swap"  # Ctrl+F12 - Swap COM1 active/standby
    COM1_READ = "com1_read"  # Alt+F12 - Read COM1 frequency
    COM2_TUNE_UP = "com2_tune_up"  # F11 - Increase COM2 frequency
    COM2_TUNE_DOWN = "com2_tune_down"  # Shift+F11 - Decrease COM2 frequency
    COM2_SWAP = "com2_swap"  # Ctrl+F11 - Swap COM2 active/standby
    COM2_READ = "com2_read"  # Alt+F11 - Read COM2 frequency
    READ_ACTIVE_RADIO = "read_active_radio"  # Alt+9 - Read selected radio's active frequency

    # Dual-knob radio system (Cessna 172, traditional radios)
    RADIO_OUTER_KNOB_INCREASE = "radio_outer_knob_increase"  # Shift+D - Increase MHz
    RADIO_OUTER_KNOB_DECREASE = "radio_outer_knob_decrease"  # Ctrl+D - Decrease MHz
    RADIO_OUTER_KNOB_READ = "radio_outer_knob_read"  # D - Announce MHz
    RADIO_INNER_KNOB_INCREASE = "radio_inner_knob_increase"  # Shift+F - Increase kHz
    RADIO_INNER_KNOB_DECREASE = "radio_inner_knob_decrease"  # Ctrl+F - Decrease kHz
    RADIO_INNER_KNOB_READ = "radio_inner_knob_read"  # F - Announce kHz
    RADIO_ANNOUNCE_FREQUENCY = "radio_announce_frequency"  # S - Announce full frequency

    # ATC/Radio controls
    ATC_MENU = "atc_menu"  # F1 - Open/close ATC menu
    # F2 - Checklist menu (defined below)
    # F3 - Ground services menu (defined below)
    ATC_ACKNOWLEDGE = "atc_acknowledge"  # Shift+F1 - Acknowledge/readback
    RADIO_PANEL = "radio_panel"  # Ctrl+F1 - Open radio panel (announce controls)
    ATC_REPEAT = "atc_repeat"  # Alt+F1 - Request repeat ("say again")
    ATC_SELECT_1 = "atc_select_1"  # Number keys for menu selection
    ATC_SELECT_2 = "atc_select_2"
    ATC_SELECT_3 = "atc_select_3"
    ATC_SELECT_4 = "atc_select_4"
    ATC_SELECT_5 = "atc_select_5"
    ATC_SELECT_6 = "atc_select_6"
    ATC_SELECT_7 = "atc_select_7"
    ATC_SELECT_8 = "atc_select_8"
    ATC_SELECT_9 = "atc_select_9"

    # Checklist controls
    CHECKLIST_MENU = "checklist_menu"  # F2 - Open/close checklist menu

    # Ground services controls
    GROUND_SERVICES_MENU = "ground_services_menu"  # F3 - Open/close ground services menu

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
        keyboard_mode: Control mode for keyboard input ('incremental' or 'smooth').
        keyboard_increment: Control deflection per keypress in incremental mode (0.0-1.0).
    """

    keyboard_bindings: dict[int, InputAction] = field(default_factory=dict)
    axis_sensitivity: float = 1.0
    axis_deadzone: float = 0.1
    throttle_increment: float = 0.01  # Changed to 1% per frame
    enable_joystick: bool = True
    keyboard_mode: str = (
        "incremental"  # 'incremental' (FlightGear-style) or 'smooth' (joystick-style)
    )
    keyboard_increment: float = 0.02  # 2% per keypress (50 taps for full deflection, finer control)

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
            pygame.K_COMMA: InputAction.YAW_LEFT,  # Comma without modifier = yaw left
            pygame.K_e: InputAction.YAW_RIGHT,
            pygame.K_HOME: InputAction.THROTTLE_INCREASE,
            pygame.K_END: InputAction.THROTTLE_DECREASE,
            # Brakes and gear
            pygame.K_b: InputAction.BRAKES,
            # Note: P key with modifiers handled specially (Shift+P=SET, Ctrl+P=RELEASE)
            pygame.K_g: InputAction.GEAR_TOGGLE,
            # Flaps
            pygame.K_LEFTBRACKET: InputAction.FLAPS_UP,
            pygame.K_RIGHTBRACKET: InputAction.FLAPS_DOWN,
            # Note: Trim keys with modifiers handled specially:
            # - Shift+Period (AZERTY colon) = pitch trim up
            # - Ctrl+Period (AZERTY colon) = pitch trim down
            # - Shift+Comma = rudder trim right
            # - Ctrl+Comma = rudder trim left
            # - Plain Comma = yaw left (when no modifier pressed)
            # View
            pygame.K_c: InputAction.VIEW_NEXT,  # C for Cycle view
            pygame.K_x: InputAction.VIEW_PREV,  # X for previous view
            # Instrument readouts
            pygame.K_s: InputAction.READ_AIRSPEED,  # S for Speed
            pygame.K_l: InputAction.READ_ALTITUDE,  # L for aLtitude
            pygame.K_h: InputAction.READ_HEADING,  # H for Heading
            pygame.K_v: InputAction.READ_VSPEED,  # V for Vertical speed
            pygame.K_w: InputAction.READ_VSPEED,  # W for Vertical speed (legacy)
            # TTS
            pygame.K_n: InputAction.TTS_NEXT,  # N for Next
            pygame.K_r: InputAction.TTS_REPEAT,  # R for Repeat
            pygame.K_i: InputAction.TTS_INTERRUPT,  # I for Interrupt
            # Menu
            pygame.K_TAB: InputAction.MENU_TOGGLE,
            # Note: K_a removed - now used for altimeter in control panel
            pygame.K_z: InputAction.MENU_DOWN,
            pygame.K_RETURN: InputAction.MENU_SELECT,
            pygame.K_ESCAPE: InputAction.MENU_BACK,  # ESC closes menus (Ctrl+Q to quit app)
            # ATC Menu Selection (number keys)
            pygame.K_1: InputAction.ATC_SELECT_1,
            pygame.K_2: InputAction.ATC_SELECT_2,
            pygame.K_3: InputAction.ATC_SELECT_3,
            pygame.K_4: InputAction.ATC_SELECT_4,
            pygame.K_5: InputAction.ATC_SELECT_5,
            pygame.K_6: InputAction.ATC_SELECT_6,
            pygame.K_7: InputAction.ATC_SELECT_7,
            pygame.K_8: InputAction.ATC_SELECT_8,
            pygame.K_9: InputAction.ATC_SELECT_9,
            # System
            pygame.K_SPACE: InputAction.PAUSE,
            # Note: Ctrl+Q is handled specially for QUIT (see _handle_key_down)
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
    # Trim in degrees (primary storage)
    pitch_trim_deg: float = 0.0  # Pitch trim in degrees
    rudder_trim_deg: float = 0.0  # Rudder trim in degrees
    # Normalized trim for backward compatibility
    pitch_trim: float = 0.0  # Normalized pitch trim (-1.0 to 1.0)
    rudder_trim: float = 0.0  # Normalized rudder trim (-1.0 to 1.0)

    def clamp_all(self) -> None:
        """Clamp all values to valid ranges."""
        self.pitch = max(-1.0, min(1.0, self.pitch))
        self.roll = max(-1.0, min(1.0, self.roll))
        self.yaw = max(-1.0, min(1.0, self.yaw))
        self.throttle = max(0.0, min(1.0, self.throttle))
        self.brakes = max(0.0, min(1.0, self.brakes))
        self.flaps = max(0.0, min(1.0, self.flaps))
        self.gear = max(0.0, min(1.0, self.gear))
        # Note: degree-based trim is clamped by InputManager based on aircraft config
        self.pitch_trim = max(-1.0, min(1.0, self.pitch_trim))
        self.rudder_trim = max(-1.0, min(1.0, self.rudder_trim))


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

    def __init__(
        self,
        event_bus: EventBus,
        config: InputConfig | None = None,
        message_queue: MessageQueue | None = None,
        aircraft_config: dict | None = None,
    ) -> None:
        """Initialize input manager.

        Args:
            event_bus: Event bus for publishing input events.
            config: Input configuration (uses defaults if None).
            message_queue: Message queue for inter-plugin communication (optional).
            aircraft_config: Aircraft configuration (for fixed_gear, etc.).
        """
        self.event_bus = event_bus
        self.message_queue = message_queue
        self.config = config if config is not None else InputConfig()

        # Aircraft configuration
        self.aircraft_config = aircraft_config or {}
        self.fixed_gear = self.aircraft_config.get("fixed_gear", False)

        # Trim configuration from aircraft (degrees-based)
        # Default values for C172-like aircraft if not specified
        trim_config = self.aircraft_config.get("trim", {})
        pitch_trim_config = trim_config.get("pitch", {})
        rudder_trim_config = trim_config.get("rudder", {})

        self._pitch_trim_min_deg = pitch_trim_config.get("min_deg", -10.0)
        self._pitch_trim_max_deg = pitch_trim_config.get("max_deg", 20.0)
        self._pitch_trim_step_deg = pitch_trim_config.get("step_deg", 1.0)
        self._pitch_trim_neutral_deg = pitch_trim_config.get("neutral_deg", 0.0)

        self._rudder_trim_min_deg = rudder_trim_config.get("min_deg", -15.0)
        self._rudder_trim_max_deg = rudder_trim_config.get("max_deg", 15.0)
        self._rudder_trim_step_deg = rudder_trim_config.get("step_deg", 1.0)
        self._rudder_trim_neutral_deg = rudder_trim_config.get("neutral_deg", 0.0)

        # Current input state
        self.state = InputState()

        # Previous state for change detection
        self._previous_throttle = 0.0

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
            InputAction.TRIM_PITCH_UP,
            InputAction.TRIM_PITCH_DOWN,
            InputAction.TRIM_RUDDER_LEFT,
            InputAction.TRIM_RUDDER_RIGHT,
        }

        # Joystick support
        self.joystick: Any = None  # pygame.joystick.Joystick | None
        self._initialize_joystick()

        # Throttle smoothing
        self._target_throttle = 0.0

        # Throttle rate limiting (10 clicks per second = 0.1s between clicks)
        self._throttle_click_interval = 0.1  # seconds between throttle adjustments
        # Initialize to interval so first throttle action works immediately
        self._time_since_last_throttle_click = self._throttle_click_interval

        # Trim adjustment rate limiting (same as throttle)
        self._trim_click_interval = 0.1  # seconds between trim adjustments
        self._time_since_last_trim_click = self._trim_click_interval

        # Context-aware input system (YAML-based)
        self.context_manager: Any = None  # InputContextManager | None
        self._initialize_context_manager()

        # Track previous trim values for change detection (TTS announcements)
        self._previous_pitch_trim = 0.0
        self._previous_rudder_trim = 0.0

        # Track active modifier-based actions (like trim controls)
        # These actions are triggered by key+modifier combinations and need special tracking
        self._modifier_actions: set[InputAction] = set()

        # Discrete flap positions (loaded from aircraft config)
        self._flap_positions: list[dict] = []  # List of {name, degrees, normalized}
        self._flap_index: int = 0  # Current discrete flap position index
        self._flap_target: float = 0.0  # Target flap position (normalized 0-1)
        self._flap_transitioning: bool = False  # Whether flaps are currently moving
        self._flap_rate: float = 0.33  # Flaps movement rate per second (default: 3 sec full travel)
        self._load_flap_config()

        # Auto-trim state
        self._auto_trim_enabled: bool = False

        # Keyboard control - smooth rate-based deflection
        self._pitch_input_target = 0.0  # Target input direction (-1, 0, or +1)
        self._roll_input_target = 0.0
        self._yaw_input_target = 0.0
        # Current smoothed yoke position (interpolates toward target)
        self._pitch_input_smoothed = 0.0
        self._roll_input_smoothed = 0.0
        self._yaw_input_smoothed = 0.0
        # Smoothing rate - how fast yoke moves to target (units per second)
        self._keyboard_deflection_rate = 1.25  # Full deflection in ~0.8 seconds
        # Trim adjustment rate when using Shift modifier (units per second)
        self._trim_adjustment_rate = 0.3  # How fast trim adjusts with Shift+arrow

        logger.info(
            "Input manager initialized with %d key bindings", len(self.config.keyboard_bindings)
        )

    def _load_flap_config(self) -> None:
        """Load discrete flap positions from aircraft configuration."""
        flaps_config = self.aircraft_config.get("flaps", {})
        positions = flaps_config.get("positions", [])

        if positions:
            self._flap_positions = positions
            default_index = flaps_config.get("default_position", 0)
            self._flap_index = default_index
            if 0 <= default_index < len(positions):
                self._flap_target = positions[default_index].get("normalized", 0.0)
                self.state.flaps = self._flap_target
            # Calculate flap rate from transition time
            transition_time = flaps_config.get("transition_time_sec", 3.0)
            if transition_time > 0:
                self._flap_rate = 1.0 / transition_time
            logger.info(
                f"Loaded {len(positions)} discrete flap positions, "
                f"transition time: {transition_time}s"
            )
        else:
            # Default flap positions if not configured
            self._flap_positions = [
                {"name": "UP", "degrees": 0, "normalized": 0.0},
                {"name": "10", "degrees": 10, "normalized": 0.33},
                {"name": "20", "degrees": 20, "normalized": 0.67},
                {"name": "FULL", "degrees": 30, "normalized": 1.0},
            ]
            logger.debug("Using default flap positions (no aircraft config)")

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

    def _initialize_context_manager(self, aircraft_id: str | None = None) -> None:
        """Initialize context-aware input system from YAML configs.

        Args:
            aircraft_id: Aircraft identifier for loading user keybinding overrides.
        """
        if not self.message_queue:
            logger.debug("Context manager disabled (no message queue)")
            return

        try:
            from airborne.core.input_context import InputContextManager

            # Look for config/input directory
            config_dir = Path("config/input")
            if not config_dir.exists():
                logger.warning(f"Input config directory not found: {config_dir}")
                return

            self.context_manager = InputContextManager(
                config_dir, self.message_queue, aircraft_id=aircraft_id, event_bus=self.event_bus
            )
            logger.info(
                "Context-aware input system initialized (%d contexts loaded, aircraft=%s)",
                len(self.context_manager.contexts),
                aircraft_id or "none",
            )

            # Detect and log any conflicts
            conflicts = self.context_manager.detect_conflicts()
            if conflicts:
                logger.warning(f"Detected {len(conflicts)} key binding conflicts:")
                for conflict in conflicts[:5]:  # Log first 5
                    logger.warning(
                        f"  {conflict['context']}: {'+'.join(conflict['modifiers'])}{conflict['key']} → {conflict['actions']}"
                    )

        except ImportError as e:
            logger.debug(f"Context manager not available: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize context manager: {e}")

    def reinitialize_context_manager(self, aircraft_id: str) -> None:
        """Reinitialize context manager with aircraft-specific keybindings.

        Call this after loading an aircraft to apply user-defined keybinding
        overrides for that aircraft.

        Args:
            aircraft_id: Aircraft identifier (e.g., "cessna172").
        """
        logger.info("Reinitializing context manager for aircraft: %s", aircraft_id)
        self._initialize_context_manager(aircraft_id=aircraft_id)

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
                self._handle_key_down(event.key, event.scancode)
            elif event.type == pygame.KEYUP:
                self._handle_key_up(event.key, event.scancode)
            elif event.type == pygame.JOYBUTTONDOWN:
                self._handle_joy_button_down(event.button)
            elif event.type == pygame.JOYBUTTONUP:
                self._handle_joy_button_up(event.button)

    def _handle_key_down(self, key: int, scancode: int) -> None:
        """Handle key press event.

        Args:
            key: Pygame key constant (affected by keyboard layout).
            scancode: Physical key scancode (layout-independent).
        """
        is_repeat = key in self._keys_pressed

        self._keys_pressed.add(key)
        if not is_repeat:
            self._keys_just_pressed.add(key)

        # Log every key press with name, modifiers, and binding status
        mods = pygame.key.get_mods()
        key_name = pygame.key.name(key)
        bound_action = self.config.keyboard_bindings.get(key)
        mod_names = []
        if mods & (pygame.KMOD_SHIFT | pygame.KMOD_LSHIFT | pygame.KMOD_RSHIFT):
            mod_names.append("SHIFT")
        if mods & (pygame.KMOD_CTRL | pygame.KMOD_LCTRL | pygame.KMOD_RCTRL):
            mod_names.append("CTRL")
        if mods & (pygame.KMOD_ALT | pygame.KMOD_LALT | pygame.KMOD_RALT):
            mod_names.append("ALT")
        mod_str = "+".join(mod_names) + "+" if mod_names else ""

        if bound_action:
            logger.info(
                f"KEY: {mod_str}{key_name} (code={key}, scan={scancode}) -> BOUND to {bound_action.name}"
            )
        else:
            logger.info(f"KEY: {mod_str}{key_name} (code={key}, scan={scancode}) -> NOT BOUND")

        # IMPORTANT: Handle Alt+number keys BEFORE context manager
        # On macOS, Alt+number generates Unicode characters (¡™£¢∞§¶•ª) instead of
        # number keycodes, so the context manager (which uses key names) won't match them.
        # We use scancodes here which are layout-independent physical key positions.
        if mods & (pygame.KMOD_ALT | pygame.KMOD_LALT | pygame.KMOD_RALT):
            alt_scancode_actions = {
                pygame.KSCAN_1: InputAction.READ_AIRSPEED,  # Alt+1: Airspeed
                pygame.KSCAN_2: InputAction.READ_ALTITUDE,  # Alt+2: Altitude
                pygame.KSCAN_3: InputAction.READ_HEADING,  # Alt+3: Heading
                pygame.KSCAN_4: InputAction.READ_VSPEED,  # Alt+4: Vertical speed
                pygame.KSCAN_5: InputAction.READ_ENGINE,  # Alt+5: Engine status
                pygame.KSCAN_6: InputAction.READ_ELECTRICAL,  # Alt+6: Electrical status
                pygame.KSCAN_7: InputAction.READ_FUEL,  # Alt+7: Fuel status
                pygame.KSCAN_8: InputAction.READ_ATTITUDE,  # Alt+8: Attitude (bank/pitch)
                pygame.KSCAN_9: InputAction.READ_ACTIVE_RADIO,  # Alt+9: Active radio frequency
            }
            if scancode in alt_scancode_actions:
                if not is_repeat:
                    self._handle_action_pressed(alt_scancode_actions[scancode])
                return

            # Alt+0: where_am_i (handled via message queue, not InputAction enum)
            if scancode == pygame.KSCAN_0 and not is_repeat:
                if self.message_queue:
                    logger.info("Alt+0 detected - where am I query")
                    self.message_queue.publish(
                        Message(
                            sender="input_manager",
                            recipients=["*"],
                            topic="input.where_am_i",
                            data={"key": key, "mods": mods},
                            priority=MessagePriority.NORMAL,
                        )
                    )
                return

        # Try context-aware input system (YAML-based)
        if self.context_manager:
            handled = self.context_manager.handle_key_press(key, mods, is_repeat)
            if handled:
                logger.debug(f"Key handled by context manager: {mod_str}{key_name}")
                return  # Context manager handled it, don't fall through to hardcoded handlers

        # Fallback to hardcoded handlers below
        # Special handling for F1 with modifiers (ATC menu)
        if key == pygame.K_F1:
            mods = pygame.key.get_mods()
            if mods & pygame.KMOD_SHIFT:
                action = InputAction.ATC_ACKNOWLEDGE
            elif mods & (pygame.KMOD_CTRL | pygame.KMOD_LCTRL | pygame.KMOD_RCTRL):
                logger.info("Ctrl+F1 detected - opening radio panel")
                action = InputAction.RADIO_PANEL
            elif mods & (pygame.KMOD_ALT | pygame.KMOD_LALT | pygame.KMOD_RALT):
                action = InputAction.ATC_REPEAT
            else:
                action = InputAction.ATC_MENU

            if not is_repeat:
                self._handle_action_pressed(action)
            return

        # Special handling for F2 (Checklist menu)
        if key == pygame.K_F2:
            action = InputAction.CHECKLIST_MENU
            if not is_repeat:
                self._handle_action_pressed(action)
            return

        # Special handling for F3 (Ground services menu)
        if key == pygame.K_F3:
            logger.info("F3 key detected in InputManager")
            action = InputAction.GROUND_SERVICES_MENU
            if not is_repeat:
                logger.info("F3 action: %s (not repeat)", action.value)
                self._handle_action_pressed(action)
            else:
                logger.info("F3 pressed but is_repeat=True, ignoring")
            return

        # Special handling for Ctrl+Q to quit (ESC now closes ATC menu)
        if key == pygame.K_q:
            mods = pygame.key.get_mods()
            if mods & pygame.KMOD_CTRL:
                if not is_repeat:
                    self._handle_action_pressed(InputAction.QUIT)
                return

        # Special handling for Shift+P (parking brake SET) and Ctrl+P (parking brake RELEASE)
        if key == pygame.K_p:
            if mods & (pygame.KMOD_SHIFT | pygame.KMOD_LSHIFT | pygame.KMOD_RSHIFT):
                if not is_repeat:
                    self._handle_action_pressed(InputAction.PARKING_BRAKE_SET)
                return
            elif mods & (pygame.KMOD_CTRL | pygame.KMOD_LCTRL | pygame.KMOD_RCTRL):
                if not is_repeat:
                    self._handle_action_pressed(InputAction.PARKING_BRAKE_RELEASE)
                return

        # Special handling for Semicolon key (AZERTY - key to right of comma) - Pitch trim
        # Shift+Semicolon = pitch trim up, Ctrl+Semicolon = pitch trim down, plain Semicolon = read pitch trim
        if key == pygame.K_SEMICOLON:
            if mods & (pygame.KMOD_SHIFT | pygame.KMOD_LSHIFT | pygame.KMOD_RSHIFT):
                self._handle_action_pressed(InputAction.TRIM_PITCH_UP)
                return
            elif mods & (pygame.KMOD_CTRL | pygame.KMOD_LCTRL | pygame.KMOD_RCTRL):
                self._handle_action_pressed(InputAction.TRIM_PITCH_DOWN)
                return
            else:
                # No modifier - read pitch trim
                self._handle_action_pressed(InputAction.READ_PITCH_TRIM)
                return

        # Special handling for Comma key - Rudder trim
        # Shift+Comma = rudder trim right, Ctrl+Comma = rudder trim left, plain Comma = read rudder trim
        if key == pygame.K_COMMA:
            logger.debug(
                f"Comma key pressed: mods={mods:#x}, has_shift={bool(mods & (pygame.KMOD_SHIFT | pygame.KMOD_LSHIFT | pygame.KMOD_RSHIFT))}, has_ctrl={bool(mods & (pygame.KMOD_CTRL | pygame.KMOD_LCTRL | pygame.KMOD_RCTRL))}"
            )
            if mods & (pygame.KMOD_SHIFT | pygame.KMOD_LSHIFT | pygame.KMOD_RSHIFT):
                logger.info("Shift+Comma detected - triggering TRIM_RUDDER_RIGHT")
                self._handle_action_pressed(InputAction.TRIM_RUDDER_RIGHT)
                return
            elif mods & (pygame.KMOD_CTRL | pygame.KMOD_LCTRL | pygame.KMOD_RCTRL):
                logger.info("Ctrl+Comma detected - triggering TRIM_RUDDER_LEFT")
                self._handle_action_pressed(InputAction.TRIM_RUDDER_LEFT)
                return
            else:
                # No modifier - read rudder trim
                logger.info("Comma (no modifier) detected - triggering READ_RUDDER_TRIM")
                self._handle_action_pressed(InputAction.READ_RUDDER_TRIM)
                return

        # Special handling for F9 key - Flight instructor
        # Shift+F9 = enable instructor, Ctrl+F9 = disable instructor, plain F9 = on-demand assessment
        if key == pygame.K_F9:
            if mods & (pygame.KMOD_SHIFT | pygame.KMOD_LSHIFT | pygame.KMOD_RSHIFT):
                if not is_repeat:
                    logger.info("Shift+F9 detected - enabling flight instructor")
                    self._handle_action_pressed(InputAction.INSTRUCTOR_ENABLE)
                return
            elif mods & (pygame.KMOD_CTRL | pygame.KMOD_LCTRL | pygame.KMOD_RCTRL):
                if not is_repeat:
                    logger.info("Ctrl+F9 detected - disabling flight instructor")
                    self._handle_action_pressed(InputAction.INSTRUCTOR_DISABLE)
                return
            else:
                # No modifier - on-demand assessment
                if not is_repeat:
                    logger.info("F9 (no modifier) detected - requesting instructor assessment")
                    self._handle_action_pressed(InputAction.INSTRUCTOR_ASSESSMENT)
                return

        # Special handling for D key - Radio outer knob (MHz)
        # Shift+D = increase MHz, Ctrl+D = decrease MHz, plain D = announce MHz
        if key == pygame.K_d:
            if mods & (pygame.KMOD_SHIFT | pygame.KMOD_LSHIFT | pygame.KMOD_RSHIFT):
                if not is_repeat:
                    logger.info("Shift+D detected - radio outer knob increase")
                    self._handle_action_pressed(InputAction.RADIO_OUTER_KNOB_INCREASE)
                return
            elif mods & (pygame.KMOD_CTRL | pygame.KMOD_LCTRL | pygame.KMOD_RCTRL):
                if not is_repeat:
                    logger.info("Ctrl+D detected - radio outer knob decrease")
                    self._handle_action_pressed(InputAction.RADIO_OUTER_KNOB_DECREASE)
                return
            else:
                # No modifier - announce MHz
                if not is_repeat:
                    logger.info("D (no modifier) detected - announce MHz")
                    self._handle_action_pressed(InputAction.RADIO_OUTER_KNOB_READ)
                return

        # Special handling for F key - Radio inner knob (kHz)
        # Shift+F = increase kHz, Ctrl+F = decrease kHz, plain F = announce kHz
        if key == pygame.K_f:
            if mods & (pygame.KMOD_SHIFT | pygame.KMOD_LSHIFT | pygame.KMOD_RSHIFT):
                if not is_repeat:
                    logger.info("Shift+F detected - radio inner knob increase")
                    self._handle_action_pressed(InputAction.RADIO_INNER_KNOB_INCREASE)
                return
            elif mods & (pygame.KMOD_CTRL | pygame.KMOD_LCTRL | pygame.KMOD_RCTRL):
                if not is_repeat:
                    logger.info("Ctrl+F detected - radio inner knob decrease")
                    self._handle_action_pressed(InputAction.RADIO_INNER_KNOB_DECREASE)
                return
            else:
                # No modifier - announce kHz
                if not is_repeat:
                    logger.info("F (no modifier) detected - announce kHz")
                    self._handle_action_pressed(InputAction.RADIO_INNER_KNOB_READ)
                return

        # Special handling for S key - Announce full radio frequency
        if key == pygame.K_s:
            if not is_repeat:
                logger.info("S detected - announce full frequency")
                self._handle_action_pressed(InputAction.RADIO_ANNOUNCE_FREQUENCY)
            return

        # Special handling for F12 key - COM1 radio tuning
        # Shift+F12 = tune down, Ctrl+F12 = swap, Alt+F12 = read, plain F12 = tune up
        if key == pygame.K_F12:
            if mods & (pygame.KMOD_SHIFT | pygame.KMOD_LSHIFT | pygame.KMOD_RSHIFT):
                if not is_repeat:
                    logger.info("Shift+F12 detected - COM1 tune down")
                    self._handle_action_pressed(InputAction.COM1_TUNE_DOWN)
                return
            elif mods & (pygame.KMOD_CTRL | pygame.KMOD_LCTRL | pygame.KMOD_RCTRL):
                if not is_repeat:
                    logger.info("Ctrl+F12 detected - COM1 swap active/standby")
                    self._handle_action_pressed(InputAction.COM1_SWAP)
                return
            elif mods & (pygame.KMOD_ALT | pygame.KMOD_LALT | pygame.KMOD_RALT):
                if not is_repeat:
                    logger.info("Alt+F12 detected - read COM1 frequency")
                    self._handle_action_pressed(InputAction.COM1_READ)
                return
            else:
                # No modifier - tune up
                if not is_repeat:
                    logger.info("F12 (no modifier) detected - COM1 tune up")
                    self._handle_action_pressed(InputAction.COM1_TUNE_UP)
                return

        # Special handling for F11 key - COM2 radio tuning
        # Shift+F11 = tune down, Ctrl+F11 = swap, Alt+F11 = read, plain F11 = tune up
        if key == pygame.K_F11:
            if mods & (pygame.KMOD_SHIFT | pygame.KMOD_LSHIFT | pygame.KMOD_RSHIFT):
                if not is_repeat:
                    logger.info("Shift+F11 detected - COM2 tune down")
                    self._handle_action_pressed(InputAction.COM2_TUNE_DOWN)
                return
            elif mods & (pygame.KMOD_CTRL | pygame.KMOD_LCTRL | pygame.KMOD_RCTRL):
                if not is_repeat:
                    logger.info("Ctrl+F11 detected - COM2 swap active/standby")
                    self._handle_action_pressed(InputAction.COM2_SWAP)
                return
            elif mods & (pygame.KMOD_ALT | pygame.KMOD_LALT | pygame.KMOD_RALT):
                if not is_repeat:
                    logger.info("Alt+F11 detected - read COM2 frequency")
                    self._handle_action_pressed(InputAction.COM2_READ)
                return
            else:
                # No modifier - tune up
                if not is_repeat:
                    logger.info("F11 (no modifier) detected - COM2 tune up")
                    self._handle_action_pressed(InputAction.COM2_TUNE_UP)
                return

        # Special handling for Right Shift alone to center controls
        if key == pygame.K_RSHIFT:
            if not is_repeat:
                self._handle_action_pressed(InputAction.CENTER_CONTROLS)
            return

        # Special handling for Control key alone to stop TTS
        if key in (pygame.K_LCTRL, pygame.K_RCTRL):
            if not is_repeat:
                self._handle_action_pressed(InputAction.TTS_INTERRUPT)
            return

        # Check for bound action
        bound_action = self.config.keyboard_bindings.get(key)
        if bound_action:
            # For key repeat events, only trigger repeatable actions
            if is_repeat:
                if bound_action not in self._repeatable_actions:
                    return  # Skip non-repeatable actions on repeat
            else:
                # First press: clear previous trigger state for this action
                self._actions_triggered.discard(bound_action)

            # Check if this non-repeatable action was already triggered
            if bound_action not in self._repeatable_actions:
                if bound_action in self._actions_triggered:
                    return  # Already triggered, don't repeat
                self._actions_triggered.add(bound_action)

            self._handle_action_pressed(bound_action)

    def _handle_key_up(self, key: int, scancode: int) -> None:
        """Handle key release event.

        Args:
            key: Pygame key constant (affected by keyboard layout).
            scancode: Physical key scancode (layout-independent, for future use).
        """
        _ = scancode  # Reserved for future scancode-based key tracking
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
        # Center controls (instant)
        if action == InputAction.CENTER_CONTROLS:
            logger.info("Centering all flight controls")
            if self.config.keyboard_mode == "incremental":
                # Incremental mode: set deflection values to 0
                self.state.pitch = 0.0
                self.state.roll = 0.0
                self.state.yaw = 0.0
            else:
                # Smooth mode: set targets and smoothed values to 0
                self._pitch_input_target = 0.0
                self._roll_input_target = 0.0
                self._yaw_input_target = 0.0
                self._pitch_input_smoothed = 0.0
                self._roll_input_smoothed = 0.0
                self._yaw_input_smoothed = 0.0
                self.state.pitch = 0.0
                self.state.roll = 0.0
                self.state.yaw = 0.0
            self.event_bus.publish(InputActionEvent(action=action.value))
            return

        # Continuous controls (handled in update)
        if action in (
            InputAction.PITCH_UP,
            InputAction.PITCH_DOWN,
            InputAction.ROLL_LEFT,
            InputAction.ROLL_RIGHT,
            InputAction.YAW_LEFT,
            InputAction.YAW_RIGHT,
            InputAction.THROTTLE_INCREASE,
            InputAction.THROTTLE_DECREASE,
        ):
            return  # Handled in update loop

        # Trim actions need special tracking since they come from modifier+key combinations
        if action in (
            InputAction.TRIM_PITCH_UP,
            InputAction.TRIM_PITCH_DOWN,
            InputAction.TRIM_RUDDER_LEFT,
            InputAction.TRIM_RUDDER_RIGHT,
        ):
            self._modifier_actions.add(action)
            return  # Handled in update loop

        # Discrete controls
        if action == InputAction.THROTTLE_FULL:
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
            # Skip gear toggle for fixed gear aircraft
            if self.fixed_gear:
                logger.debug("Gear toggle ignored (fixed gear aircraft)")
                return
            self.state.gear = 0.0 if self.state.gear > 0.5 else 1.0
            self.event_bus.publish(InputActionEvent(action=action.value, value=self.state.gear))
        elif action == InputAction.FLAPS_UP:
            self._change_flap_position(-1)
        elif action == InputAction.FLAPS_DOWN:
            self._change_flap_position(1)
        elif action == InputAction.FLAPS_READ:
            self._announce_flap_position()
        elif action == InputAction.AUTO_TRIM_ENABLE:
            self._set_auto_trim(True)
        elif action == InputAction.AUTO_TRIM_DISABLE:
            self._set_auto_trim(False)
        elif action == InputAction.AUTO_TRIM_READ:
            self._announce_auto_trim_status()
        elif action in (InputAction.PARKING_BRAKE_SET, InputAction.PARKING_BRAKE_RELEASE):
            # Set or release parking brake via message queue to physics plugin
            if self.message_queue:
                from airborne.core.messaging import Message, MessagePriority

                brake_action = "set" if action == InputAction.PARKING_BRAKE_SET else "release"
                self.message_queue.publish(
                    Message(
                        sender="input_manager",
                        recipients=["physics_plugin"],
                        topic="parking_brake",
                        data={"action": brake_action},
                        priority=MessagePriority.HIGH,
                    )
                )
                logger.debug(f"Parking brake {brake_action} message sent")
            # Also publish to event bus for TTS feedback
            self.event_bus.publish(InputActionEvent(action=action.value))
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

        # Announce throttle percent when throttle keys are released
        elif action in (InputAction.THROTTLE_INCREASE, InputAction.THROTTLE_DECREASE):
            throttle_percent = int(self._target_throttle * 100)
            self.event_bus.publish(
                InputActionEvent(action="throttle_released", value=throttle_percent)
            )

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
        # Update throttle rate limiting timer
        self._time_since_last_throttle_click += dt
        self._time_since_last_trim_click += dt

        # Update flap transition (gradual movement to target position)
        self._update_flap_transition(dt)

        # Update continuous keyboard controls
        self._update_keyboard_controls()

        # Update joystick controls (overrides keyboard if joystick present)
        if self.joystick:
            self._update_joystick_controls()
        elif self.config.keyboard_mode == "smooth":
            # SMOOTH mode: Apply smooth rate-based deflection (joystick-style)
            # This makes keyboard behave like a joystick with smooth movement:
            # - Hold key = gradually deflect yoke to full
            # - Release = gradually return to neutral

            # Smooth pitch input toward target
            if abs(self._pitch_input_target - self._pitch_input_smoothed) > 0.001:
                pitch_delta = self._keyboard_deflection_rate * dt
                if self._pitch_input_smoothed < self._pitch_input_target:
                    self._pitch_input_smoothed = min(
                        self._pitch_input_target, self._pitch_input_smoothed + pitch_delta
                    )
                else:
                    self._pitch_input_smoothed = max(
                        self._pitch_input_target, self._pitch_input_smoothed - pitch_delta
                    )

            # Smooth roll input toward target
            if abs(self._roll_input_target - self._roll_input_smoothed) > 0.001:
                roll_delta = self._keyboard_deflection_rate * dt
                if self._roll_input_smoothed < self._roll_input_target:
                    self._roll_input_smoothed = min(
                        self._roll_input_target, self._roll_input_smoothed + roll_delta
                    )
                else:
                    self._roll_input_smoothed = max(
                        self._roll_input_target, self._roll_input_smoothed - roll_delta
                    )

            # Smooth yaw input toward target
            if abs(self._yaw_input_target - self._yaw_input_smoothed) > 0.001:
                yaw_delta = self._keyboard_deflection_rate * dt
                if self._yaw_input_smoothed < self._yaw_input_target:
                    self._yaw_input_smoothed = min(
                        self._yaw_input_target, self._yaw_input_smoothed + yaw_delta
                    )
                else:
                    self._yaw_input_smoothed = max(
                        self._yaw_input_target, self._yaw_input_smoothed - yaw_delta
                    )

            # Set controls to smoothed values
            self.state.pitch = self._pitch_input_smoothed
            self.state.roll = self._roll_input_smoothed
            self.state.yaw = self._yaw_input_smoothed
        # else: INCREMENTAL mode - state is already set directly in _update_keyboard_incremental()

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

        # Publish state update to event bus (for UI/audio feedback)
        self.event_bus.publish(
            InputStateEvent(
                pitch=self.state.pitch,
                roll=self.state.roll,
                yaw=self.state.yaw,
                throttle=self.state.throttle,
                brakes=self.state.brakes,
                flaps=self.state.flaps,
                gear=self.state.gear,
                pitch_trim=self.state.pitch_trim,
                rudder_trim=self.state.rudder_trim,
            )
        )

        # Publish control inputs to message queue (for physics and systems)
        if self.message_queue:
            # Detect throttle changes for debug logging
            throttle_changed = abs(self.state.throttle - self._previous_throttle) > 0.001
            if throttle_changed:
                logger.debug(
                    "InputManager: Throttle changed from %.3f to %.3f (target: %.3f)",
                    self._previous_throttle,
                    self.state.throttle,
                    self._target_throttle,
                )
                self._previous_throttle = self.state.throttle

            # Publish control inputs message for physics plugin
            self.message_queue.publish(
                Message(
                    sender="input_manager",
                    recipients=["*"],
                    topic=MessageTopic.CONTROL_INPUT,
                    data={
                        "pitch": self.state.pitch,
                        "roll": self.state.roll,
                        "yaw": self.state.yaw,
                        "throttle": self.state.throttle,
                        "brakes": self.state.brakes,
                        "flaps": self.state.flaps,
                        "gear": self.state.gear,
                        "pitch_trim": self.state.pitch_trim,  # Normalized (-1 to 1)
                        "rudder_trim": self.state.rudder_trim,  # Normalized (-1 to 1)
                        "pitch_trim_deg": self.state.pitch_trim_deg,  # Degrees
                        "rudder_trim_deg": self.state.rudder_trim_deg,  # Degrees
                    },
                    priority=MessagePriority.HIGH,
                )
            )

    def _update_keyboard_controls(self) -> None:
        """Update continuous controls from keyboard."""
        # Two control modes:
        # 1. INCREMENTAL (FlightGear-style, default for keyboard):
        #    - Each keypress adds/subtracts a fixed increment
        #    - Deflection stays at that value until changed
        #    - Easy to master on keyboard
        # 2. SMOOTH (joystick-style, for analog devices):
        #    - Hold key = smoothly deflect toward target
        #    - Release = return to center
        #    - Feels like real joystick

        if self.config.keyboard_mode == "incremental":
            self._update_keyboard_incremental()
        else:
            self._update_keyboard_smooth()

    def _update_keyboard_incremental(self) -> None:
        """Update controls using FlightGear-style incremental mode."""
        brakes = 0.0

        # Check for Shift modifier
        mods = pygame.key.get_mods()
        shift_pressed = bool(mods & (pygame.KMOD_SHIFT | pygame.KMOD_LSHIFT | pygame.KMOD_RSHIFT))

        # Process just-pressed keys for incremental changes
        for key in self._keys_just_pressed:
            action = self.config.keyboard_bindings.get(key)
            if not action:
                continue

            if action == InputAction.PITCH_UP:
                if not shift_pressed:
                    self.state.pitch = min(1.0, self.state.pitch + self.config.keyboard_increment)
            elif action == InputAction.PITCH_DOWN:
                if not shift_pressed:
                    self.state.pitch = max(-1.0, self.state.pitch - self.config.keyboard_increment)
            elif action == InputAction.ROLL_LEFT:
                self.state.roll = max(-1.0, self.state.roll - self.config.keyboard_increment)
            elif action == InputAction.ROLL_RIGHT:
                self.state.roll = min(1.0, self.state.roll + self.config.keyboard_increment)
            elif action == InputAction.YAW_LEFT:
                self.state.yaw = max(-1.0, self.state.yaw - self.config.keyboard_increment)
            elif action == InputAction.YAW_RIGHT:
                self.state.yaw = min(1.0, self.state.yaw + self.config.keyboard_increment)

        # Check which keys are currently held (for brakes and throttle)
        for key in self._keys_pressed:
            action = self.config.keyboard_bindings.get(key)
            if not action:
                continue

            if action == InputAction.THROTTLE_INCREASE:
                # Rate-limited throttle increase (10 clicks/second max)
                if self._time_since_last_throttle_click >= self._throttle_click_interval:
                    # Shift modifier = 10% increment, otherwise 1%
                    increment = 0.10 if shift_pressed else 0.01
                    old_throttle = self._target_throttle
                    self._target_throttle = min(1.0, self._target_throttle + increment)
                    # Play click sound if throttle actually changed
                    if abs(self._target_throttle - old_throttle) > 0.001:
                        self.event_bus.publish(
                            InputActionEvent(action="throttle_click", value=self._target_throttle)
                        )
                        self._time_since_last_throttle_click = 0.0
            elif action == InputAction.THROTTLE_DECREASE:
                # Rate-limited throttle decrease (10 clicks/second max)
                if self._time_since_last_throttle_click >= self._throttle_click_interval:
                    # Shift modifier = 10% decrement, otherwise 1%
                    decrement = 0.10 if shift_pressed else 0.01
                    old_throttle = self._target_throttle
                    self._target_throttle = max(0.0, self._target_throttle - decrement)
                    # Play click sound if throttle actually changed
                    if abs(self._target_throttle - old_throttle) > 0.001:
                        self.event_bus.publish(
                            InputActionEvent(action="throttle_click", value=self._target_throttle)
                        )
                        self._time_since_last_throttle_click = 0.0
            elif action == InputAction.BRAKES:
                brakes = 1.0

        # Handle trim controls (same for both modes)
        self._process_trim_controls()

        self.state.brakes = brakes

    def _update_keyboard_smooth(self) -> None:
        """Update controls using smooth joystick-style mode."""
        pitch_input_target = 0.0
        roll_input_target = 0.0
        yaw_input_target = 0.0
        brakes = 0.0

        # Check for Shift modifier
        mods = pygame.key.get_mods()
        shift_pressed = bool(mods & (pygame.KMOD_SHIFT | pygame.KMOD_LSHIFT | pygame.KMOD_RSHIFT))

        # Check which keys are currently held
        for key in self._keys_pressed:
            action = self.config.keyboard_bindings.get(key)
            if not action:
                continue

            if action == InputAction.PITCH_UP:
                if not shift_pressed:
                    pitch_input_target += 1.0  # Push forward (nose down)
            elif action == InputAction.PITCH_DOWN:
                if not shift_pressed:
                    pitch_input_target -= 1.0  # Pull back (nose up)
            elif action == InputAction.ROLL_LEFT:
                roll_input_target -= 1.0  # Roll left
            elif action == InputAction.ROLL_RIGHT:
                roll_input_target += 1.0  # Roll right
            elif action == InputAction.YAW_LEFT:
                yaw_input_target -= 1.0  # Yaw left
            elif action == InputAction.YAW_RIGHT:
                yaw_input_target += 1.0  # Yaw right
            elif action == InputAction.THROTTLE_INCREASE:
                # Rate-limited throttle increase (10 clicks/second max)
                if self._time_since_last_throttle_click >= self._throttle_click_interval:
                    # Shift modifier = 10% increment, otherwise 1%
                    mods = pygame.key.get_mods()
                    increment = 0.10 if (mods & pygame.KMOD_SHIFT) else 0.01
                    old_throttle = self._target_throttle
                    self._target_throttle = min(1.0, self._target_throttle + increment)
                    # Play click sound if throttle actually changed
                    if abs(self._target_throttle - old_throttle) > 0.001:
                        self.event_bus.publish(
                            InputActionEvent(action="throttle_click", value=self._target_throttle)
                        )
                        self._time_since_last_throttle_click = 0.0
            elif action == InputAction.THROTTLE_DECREASE:
                # Rate-limited throttle decrease (10 clicks/second max)
                if self._time_since_last_throttle_click >= self._throttle_click_interval:
                    # Shift modifier = 10% decrement, otherwise 1%
                    mods = pygame.key.get_mods()
                    decrement = 0.10 if (mods & pygame.KMOD_SHIFT) else 0.01
                    old_throttle = self._target_throttle
                    self._target_throttle = max(0.0, self._target_throttle - decrement)
                    # Play click sound if throttle actually changed
                    if abs(self._target_throttle - old_throttle) > 0.001:
                        self.event_bus.publish(
                            InputActionEvent(action="throttle_click", value=self._target_throttle)
                        )
                        self._time_since_last_throttle_click = 0.0
            elif action == InputAction.BRAKES:
                brakes = 1.0

        # Handle trim controls (same for both modes)
        self._process_trim_controls()

        # Set the target input directions for yoke control
        # These are smoothly interpolated in update() method
        self._pitch_input_target = pitch_input_target
        self._roll_input_target = roll_input_target
        self._yaw_input_target = yaw_input_target
        self.state.brakes = brakes

    def _pitch_trim_deg_to_normalized(self, deg: float) -> float:
        """Convert pitch trim from degrees to normalized (-1.0 to +1.0).

        Uses aircraft-specific trim range from config.
        Maps min_deg to -1.0, max_deg to +1.0.

        Args:
            deg: Trim position in degrees.

        Returns:
            Normalized trim value (-1.0 to +1.0).
        """
        trim_range = self._pitch_trim_max_deg - self._pitch_trim_min_deg
        if trim_range <= 0:
            return 0.0
        # Map [min_deg, max_deg] to [-1.0, +1.0]
        return 2.0 * (deg - self._pitch_trim_min_deg) / trim_range - 1.0

    def _rudder_trim_deg_to_normalized(self, deg: float) -> float:
        """Convert rudder trim from degrees to normalized (-1.0 to +1.0).

        Args:
            deg: Trim position in degrees.

        Returns:
            Normalized trim value (-1.0 to +1.0).
        """
        trim_range = self._rudder_trim_max_deg - self._rudder_trim_min_deg
        if trim_range <= 0:
            return 0.0
        return 2.0 * (deg - self._rudder_trim_min_deg) / trim_range - 1.0

    def _format_trim_announcement(self, deg: float, is_pitch: bool = True) -> str:
        """Format trim position for TTS announcement.

        Args:
            deg: Trim position in degrees.
            is_pitch: True for pitch trim, False for rudder trim.

        Returns:
            Formatted string like "5 degrees nose up" or "neutral".
        """
        # Round to nearest integer for announcement
        rounded_deg = round(deg)

        if abs(rounded_deg) < 0.5:
            return "neutral"

        if is_pitch:
            direction = "nose up" if rounded_deg > 0 else "nose down"
        else:
            direction = "right" if rounded_deg > 0 else "left"

        return f"{abs(rounded_deg)} degrees {direction}"

    @staticmethod
    def _trim_to_percent(trim_value: float) -> int:
        """Convert trim value (-1.0 to +1.0) to percentage (0-100).

        DEPRECATED: Use degree-based trim instead.

        Args:
            trim_value: Trim value in range [-1.0, 1.0]
                       -1.0 = 0% (full down/left)
                        0.0 = 50% (neutral)
                       +1.0 = 100% (full up/right)

        Returns:
            Percentage value (0-100)
        """
        return int((trim_value + 1.0) / 2.0 * 100)

    def _process_trim_controls(self) -> None:
        """Process trim control inputs (shared by both keyboard modes).

        Trim is stored in DEGREES and converted to normalized values for physics.
        Each click adjusts by the aircraft-specific step_deg (typically 1°).
        """
        # Check for Shift modifier
        mods = pygame.key.get_mods()
        shift_pressed = bool(mods & (pygame.KMOD_SHIFT | pygame.KMOD_LSHIFT | pygame.KMOD_RSHIFT))

        # Process modifier-based actions (trim controls from Shift+Semicolon/Comma)
        # Collect actions that were processed so we can remove them after
        actions_to_remove: set[InputAction] = set()

        for action in self._modifier_actions:
            if action == InputAction.TRIM_PITCH_UP:
                # Rate-limited trim increase (10 clicks/second max)
                if self._time_since_last_trim_click >= self._trim_click_interval:
                    old_trim_deg = self.state.pitch_trim_deg
                    new_trim_deg = min(
                        self._pitch_trim_max_deg,
                        self.state.pitch_trim_deg + self._pitch_trim_step_deg
                    )
                    self.state.pitch_trim_deg = new_trim_deg
                    # Update normalized value for backward compatibility
                    self.state.pitch_trim = self._pitch_trim_deg_to_normalized(new_trim_deg)

                    # Publish event for TTS announcement (with degrees)
                    if abs(new_trim_deg - old_trim_deg) > 0.01:
                        self.event_bus.publish(
                            InputActionEvent(action="trim_pitch_adjusted", value=new_trim_deg)
                        )
                        self._time_since_last_trim_click = 0.0
                        actions_to_remove.add(action)

            elif action == InputAction.TRIM_PITCH_DOWN:
                # Rate-limited trim decrease (10 clicks/second max)
                if self._time_since_last_trim_click >= self._trim_click_interval:
                    old_trim_deg = self.state.pitch_trim_deg
                    new_trim_deg = max(
                        self._pitch_trim_min_deg,
                        self.state.pitch_trim_deg - self._pitch_trim_step_deg
                    )
                    self.state.pitch_trim_deg = new_trim_deg
                    self.state.pitch_trim = self._pitch_trim_deg_to_normalized(new_trim_deg)

                    if abs(new_trim_deg - old_trim_deg) > 0.01:
                        self.event_bus.publish(
                            InputActionEvent(action="trim_pitch_adjusted", value=new_trim_deg)
                        )
                        self._time_since_last_trim_click = 0.0
                        actions_to_remove.add(action)

            elif action == InputAction.TRIM_RUDDER_RIGHT:
                # Rate-limited rudder trim right (10 clicks/second max)
                if self._time_since_last_trim_click >= self._trim_click_interval:
                    old_trim_deg = self.state.rudder_trim_deg
                    new_trim_deg = min(
                        self._rudder_trim_max_deg,
                        self.state.rudder_trim_deg + self._rudder_trim_step_deg
                    )
                    self.state.rudder_trim_deg = new_trim_deg
                    self.state.rudder_trim = self._rudder_trim_deg_to_normalized(new_trim_deg)

                    if abs(new_trim_deg - old_trim_deg) > 0.01:
                        logger.info(
                            f"Rudder trim RIGHT: {old_trim_deg:.1f}° -> {new_trim_deg:.1f}°"
                        )
                        self.event_bus.publish(
                            InputActionEvent(action="trim_rudder_adjusted", value=new_trim_deg)
                        )
                        self._time_since_last_trim_click = 0.0
                        actions_to_remove.add(action)

            elif action == InputAction.TRIM_RUDDER_LEFT:
                # Rate-limited rudder trim left (10 clicks/second max)
                if self._time_since_last_trim_click >= self._trim_click_interval:
                    old_trim_deg = self.state.rudder_trim_deg
                    new_trim_deg = max(
                        self._rudder_trim_min_deg,
                        self.state.rudder_trim_deg - self._rudder_trim_step_deg
                    )
                    self.state.rudder_trim_deg = new_trim_deg
                    self.state.rudder_trim = self._rudder_trim_deg_to_normalized(new_trim_deg)

                    if abs(new_trim_deg - old_trim_deg) > 0.01:
                        logger.info(
                            f"Rudder trim LEFT: {old_trim_deg:.1f}° -> {new_trim_deg:.1f}°"
                        )
                        self.event_bus.publish(
                            InputActionEvent(action="trim_rudder_adjusted", value=new_trim_deg)
                        )
                        self._time_since_last_trim_click = 0.0
                        actions_to_remove.add(action)

        # Remove processed trim actions (they should only fire once per click)
        self._modifier_actions -= actions_to_remove

        # Handle Shift+arrow keys for pitch trim adjustment (hybrid control)
        if shift_pressed:
            # Check if pitch keys are held with Shift
            pitch_up_held = pygame.K_UP in self._keys_pressed
            pitch_down_held = pygame.K_DOWN in self._keys_pressed

            # Continuous trim adjustment rate (degrees per second when held)
            trim_rate_deg_per_sec = 10.0  # 10 degrees per second
            trim_change_deg = trim_rate_deg_per_sec * 0.016  # Assume ~60 FPS

            if pitch_down_held:
                # Shift+DOWN = trim nose up (continuously adjust while held)
                old_trim_deg = self.state.pitch_trim_deg
                new_trim_deg = min(
                    self._pitch_trim_max_deg,
                    self.state.pitch_trim_deg + trim_change_deg
                )
                self.state.pitch_trim_deg = new_trim_deg
                self.state.pitch_trim = self._pitch_trim_deg_to_normalized(new_trim_deg)

                # TTS announcement on significant change (every 1°)
                if int(old_trim_deg) != int(new_trim_deg):
                    self.event_bus.publish(
                        InputActionEvent(action="trim_pitch_adjusted", value=new_trim_deg)
                    )

            elif pitch_up_held:
                # Shift+UP = trim nose down (continuously adjust while held)
                old_trim_deg = self.state.pitch_trim_deg
                new_trim_deg = max(
                    self._pitch_trim_min_deg,
                    self.state.pitch_trim_deg - trim_change_deg
                )
                self.state.pitch_trim_deg = new_trim_deg
                self.state.pitch_trim = self._pitch_trim_deg_to_normalized(new_trim_deg)

                # TTS announcement on significant change (every 1°)
                if int(old_trim_deg) != int(new_trim_deg):
                    self.event_bus.publish(
                        InputActionEvent(action="trim_pitch_adjusted", value=new_trim_deg)
                    )

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

    def _change_flap_position(self, direction: int) -> None:
        """Change flap position by one discrete step.

        Args:
            direction: -1 for up (retract), +1 for down (extend)
        """
        if not self._flap_positions:
            return

        new_index = self._flap_index + direction
        if 0 <= new_index < len(self._flap_positions):
            self._flap_index = new_index
            position = self._flap_positions[new_index]
            self._flap_target = position.get("normalized", 0.0)
            self._flap_transitioning = True

            # Publish "flaps commanded" event for TTS announcement
            self.event_bus.publish(
                InputActionEvent(
                    action="flaps_commanded",
                    value=position.get("degrees", 0),
                )
            )
            logger.info(
                f"Flaps commanded to {position.get('name', 'UNKNOWN')} ({position.get('degrees', 0)}°)"
            )

    def _update_flap_transition(self, dt: float) -> None:
        """Update flap position transition (gradual movement).

        Args:
            dt: Delta time in seconds.
        """
        if not self._flap_transitioning:
            return

        # Move flaps toward target at configured rate
        diff = self._flap_target - self.state.flaps
        if abs(diff) < 0.01:
            # Reached target
            self.state.flaps = self._flap_target
            self._flap_transitioning = False

            # Publish "flaps set" event for TTS announcement
            if self._flap_positions and 0 <= self._flap_index < len(self._flap_positions):
                position = self._flap_positions[self._flap_index]
                self.event_bus.publish(
                    InputActionEvent(
                        action="flaps_set",
                        value=position.get("degrees", 0),
                    )
                )
                logger.info(
                    f"Flaps set to {position.get('name', 'UNKNOWN')} ({position.get('degrees', 0)}°)"
                )
        else:
            # Move toward target
            move_amount = self._flap_rate * dt
            if diff > 0:
                self.state.flaps = min(self._flap_target, self.state.flaps + move_amount)
            else:
                self.state.flaps = max(self._flap_target, self.state.flaps - move_amount)

    def _announce_flap_position(self) -> None:
        """Announce current flap position via TTS."""
        if self._flap_positions and 0 <= self._flap_index < len(self._flap_positions):
            position = self._flap_positions[self._flap_index]
            self.event_bus.publish(
                InputActionEvent(
                    action="flaps_read",
                    value=position.get("degrees", 0),
                )
            )

    def _set_auto_trim(self, enabled: bool) -> None:
        """Enable or disable auto-trim.

        Args:
            enabled: Whether to enable auto-trim.
        """
        if self._auto_trim_enabled == enabled:
            return  # No change

        self._auto_trim_enabled = enabled

        # Publish to message queue for physics plugin
        if self.message_queue:
            self.message_queue.publish(
                Message(
                    sender="input_manager",
                    recipients=["physics_plugin"],
                    topic="flight_controls.auto_trim",
                    data={"enabled": enabled},
                    priority=MessagePriority.HIGH,
                )
            )

        # Publish event for TTS feedback
        action = "auto_trim_enabled" if enabled else "auto_trim_disabled"
        self.event_bus.publish(InputActionEvent(action=action))
        logger.info(f"Auto-trim {'enabled' if enabled else 'disabled'}")

    def _announce_auto_trim_status(self) -> None:
        """Announce current auto-trim status via TTS."""
        self.event_bus.publish(
            InputActionEvent(
                action="auto_trim_read",
                value=1.0 if self._auto_trim_enabled else 0.0,
            )
        )

"""Input configuration loader for YAML-based input bindings.

This module loads input bindings and handler priorities from YAML configuration
files, supporting multiple input sources (keyboard, joystick, controller, network).

Typical usage:
    config = InputConfig.load_from_directory("config/input_bindings")

    # Get action bindings
    for action_binding in config.get_all_action_bindings():
        print(f"{action_binding.action}: {len(action_binding.bindings)} bindings")

    # Get handler priority
    priority = config.get_handler_priority("atc_menu")
"""

from pathlib import Path

import pygame
import yaml

from airborne.core.action_binding import (
    ActionBinding,
    ActionBindingRegistry,
    InputBinding,
)
from airborne.core.input_event import InputSourceType
from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


class InputConfig:
    """Loads and manages input configuration from YAML files.

    Provides centralized configuration for:
    - Action bindings (mapping actions to multiple inputs)
    - Handler priorities (dispatch order)

    Examples:
        >>> config = InputConfig.load_from_directory("config/input_bindings")
        >>> menu_bindings = config.get_action_binding("MENU_ATC")
        >>> priority = config.get_handler_priority("atc_menu")
    """

    # Pygame key name mapping
    _KEY_MAP = {
        "F1": pygame.K_F1,
        "F2": pygame.K_F2,
        "F3": pygame.K_F3,
        "F4": pygame.K_F4,
        "F5": pygame.K_F5,
        "F6": pygame.K_F6,
        "F7": pygame.K_F7,
        "F8": pygame.K_F8,
        "F9": pygame.K_F9,
        "F10": pygame.K_F10,
        "F11": pygame.K_F11,
        "F12": pygame.K_F12,
        "ESCAPE": pygame.K_ESCAPE,
        "TAB": pygame.K_TAB,
        "RETURN": pygame.K_RETURN,
        "SPACE": pygame.K_SPACE,
        "UP": pygame.K_UP,
        "DOWN": pygame.K_DOWN,
        "LEFT": pygame.K_LEFT,
        "RIGHT": pygame.K_RIGHT,
        "HOME": pygame.K_HOME,
        "END": pygame.K_END,
        "PAGEUP": pygame.K_PAGEUP,
        "PAGEDOWN": pygame.K_PAGEDOWN,
        "COMMA": pygame.K_COMMA,
        "PERIOD": pygame.K_PERIOD,
        "SHIFT": pygame.K_LSHIFT,
        "CTRL": pygame.K_LCTRL,
        "ALT": pygame.K_LALT,
        # Letters
        "A": pygame.K_a,
        "B": pygame.K_b,
        "C": pygame.K_c,
        "D": pygame.K_d,
        "E": pygame.K_e,
        "F": pygame.K_f,
        "G": pygame.K_g,
        "H": pygame.K_h,
        "I": pygame.K_i,
        "J": pygame.K_j,
        "K": pygame.K_k,
        "L": pygame.K_l,
        "M": pygame.K_m,
        "N": pygame.K_n,
        "O": pygame.K_o,
        "P": pygame.K_p,
        "Q": pygame.K_q,
        "R": pygame.K_r,
        "S": pygame.K_s,
        "T": pygame.K_t,
        "U": pygame.K_u,
        "V": pygame.K_v,
        "W": pygame.K_w,
        "X": pygame.K_x,
        "Y": pygame.K_y,
        "Z": pygame.K_z,
        # Numbers
        "0": pygame.K_0,
        "1": pygame.K_1,
        "2": pygame.K_2,
        "3": pygame.K_3,
        "4": pygame.K_4,
        "5": pygame.K_5,
        "6": pygame.K_6,
        "7": pygame.K_7,
        "8": pygame.K_8,
        "9": pygame.K_9,
    }

    # Pygame modifier mapping
    _MOD_MAP = {
        "SHIFT": pygame.KMOD_SHIFT,
        "CTRL": pygame.KMOD_CTRL,
        "ALT": pygame.KMOD_ALT,
    }

    def __init__(self):
        """Initialize input configuration."""
        self._action_registry = ActionBindingRegistry()
        self._handler_priorities: dict[str, int] = {}

    @classmethod
    def load_from_directory(cls, directory: str | Path) -> "InputConfig":
        """Load configuration from directory of YAML files.

        Args:
            directory: Path to directory containing YAML files.

        Returns:
            InputConfig instance with loaded configuration.

        Raises:
            FileNotFoundError: If directory doesn't exist.
            ValueError: If YAML parsing fails.
        """
        config = cls()
        directory = Path(directory)

        if not directory.exists():
            raise FileNotFoundError(f"Config directory not found: {directory}")

        # Load all YAML files in directory
        for yaml_file in directory.glob("*.yaml"):
            logger.info(f"Loading input config from {yaml_file}")
            config._load_yaml_file(yaml_file)

        return config

    def _load_yaml_file(self, file_path: Path) -> None:
        """Load configuration from a YAML file.

        Args:
            file_path: Path to YAML file.
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data:
                logger.warning(f"Empty YAML file: {file_path}")
                return

            # Check for action bindings
            if "actions" in data:
                self._load_actions(data["actions"])

            # Check for handler priorities
            if "priorities" in data:
                self._load_priorities(data["priorities"])

        except Exception as e:
            logger.error(f"Error loading YAML file {file_path}: {e}")
            raise

    def _load_actions(self, actions: dict) -> None:
        """Load action bindings from YAML data.

        Args:
            actions: Dictionary of action configurations.
        """
        for action_name, action_data in actions.items():
            bindings = []

            for binding_data in action_data.get("bindings", []):
                input_binding = self._parse_input_binding(binding_data)
                if input_binding:
                    bindings.append(input_binding)

            if bindings:
                action_binding = ActionBinding(action=action_name, bindings=bindings)
                try:
                    self._action_registry.register(action_binding)
                    logger.debug(f"Registered action '{action_name}' with {len(bindings)} bindings")
                except ValueError as e:
                    logger.warning(f"Could not register action '{action_name}': {e}")

    def _parse_input_binding(self, binding_data: dict) -> InputBinding | None:
        """Parse a single input binding from YAML data.

        Args:
            binding_data: Dictionary with binding configuration.

        Returns:
            InputBinding instance or None if parsing fails.
        """
        binding_type = binding_data.get("type")

        try:
            if binding_type == "keyboard":
                return self._parse_keyboard_binding(binding_data)
            elif binding_type == "joystick_button":
                return self._parse_joystick_button_binding(binding_data)
            elif binding_type == "joystick_axis":
                return self._parse_joystick_axis_binding(binding_data)
            elif binding_type == "joystick_hat":
                return self._parse_joystick_hat_binding(binding_data)
            elif binding_type == "network":
                return self._parse_network_binding(binding_data)
            else:
                logger.warning(f"Unknown binding type: {binding_type}")
                return None
        except Exception as e:
            logger.error(f"Error parsing binding: {e}")
            return None

    def _parse_keyboard_binding(self, data: dict) -> InputBinding:
        """Parse keyboard binding from YAML data."""
        key_name = data.get("key", "")
        key = self._KEY_MAP.get(key_name.upper())

        if key is None:
            raise ValueError(f"Unknown key name: {key_name}")

        # Parse modifiers (optional)
        mods = 0
        if "mods" in data:
            mod_name = data["mods"].upper()
            mods = self._MOD_MAP.get(mod_name, 0)

        return InputBinding.from_keyboard(key=key, mods=mods)

    def _parse_joystick_button_binding(self, data: dict) -> InputBinding:
        """Parse joystick button binding from YAML data."""
        button = data.get("button")
        device = data.get("device")  # "any" or specific device ID

        device_id = None if device == "any" else device

        return InputBinding.from_joystick_button(button=button, device_id=device_id)

    def _parse_joystick_axis_binding(self, data: dict) -> InputBinding:
        """Parse joystick axis binding from YAML data."""
        axis = data.get("axis")
        threshold = data.get("threshold", 0.5)
        direction = data.get("direction", "positive")
        device = data.get("device")

        device_id = None if device == "any" else device

        return InputBinding.from_joystick_axis(
            axis=axis, threshold=threshold, direction=direction, device_id=device_id
        )

    def _parse_joystick_hat_binding(self, data: dict) -> InputBinding:
        """Parse joystick hat binding from YAML data."""
        hat = data.get("hat", 0)
        value = tuple(data.get("value", [0, 0]))  # Convert list to tuple
        device = data.get("device")

        device_id = None if device == "any" else device

        # Create binding manually since we don't have from_joystick_hat
        return InputBinding(
            source_type=InputSourceType.JOYSTICK_HAT,
            hat=hat,
            hat_value=value,
            device_id=device_id,
        )

    def _parse_network_binding(self, data: dict) -> InputBinding:
        """Parse network binding from YAML data."""
        command = data.get("command", "")
        return InputBinding.from_network(command=command)

    def _load_priorities(self, priorities: dict) -> None:
        """Load handler priorities from YAML data.

        Args:
            priorities: Dictionary of handler name -> priority.
        """
        for handler_name, priority in priorities.items():
            self._handler_priorities[handler_name] = priority
            logger.debug(f"Loaded priority for '{handler_name}': {priority}")

    # Public API

    def get_action_binding(self, action: str) -> ActionBinding | None:
        """Get action binding by name.

        Args:
            action: Action name.

        Returns:
            ActionBinding or None if not found.
        """
        return self._action_registry.get_binding(action)

    def get_all_action_bindings(self) -> list[ActionBinding]:
        """Get all registered action bindings.

        Returns:
            List of ActionBinding instances.
        """
        return [
            self._action_registry.get_binding(action)
            for action in self._action_registry.get_all_actions()
        ]

    def get_action_registry(self) -> ActionBindingRegistry:
        """Get the action binding registry.

        Returns:
            ActionBindingRegistry instance.
        """
        return self._action_registry

    def get_handler_priority(self, handler_name: str) -> int:
        """Get priority for a handler.

        Args:
            handler_name: Name of handler.

        Returns:
            Priority value (default 999 if not configured).
        """
        return self._handler_priorities.get(handler_name, 999)

    def get_all_handler_priorities(self) -> dict[str, int]:
        """Get all configured handler priorities.

        Returns:
            Dictionary of handler name -> priority.
        """
        return self._handler_priorities.copy()

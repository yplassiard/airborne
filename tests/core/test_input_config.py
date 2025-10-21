"""Tests for InputConfig YAML loader."""


import pygame

from airborne.core.input_config import InputConfig
from airborne.core.input_event import InputEvent


class TestInputConfigLoader:
    """Test loading configuration from YAML files."""

    def test_load_from_directory(self):
        """Test loading config from directory."""
        config = InputConfig.load_from_directory("config/input_bindings")

        assert config is not None
        assert config.get_action_registry() is not None

    def test_load_menu_actions(self):
        """Test menu actions are loaded."""
        config = InputConfig.load_from_directory("config/input_bindings")

        # Check ATC menu action
        atc_binding = config.get_action_binding("MENU_ATC")
        assert atc_binding is not None
        assert atc_binding.action == "MENU_ATC"
        assert len(atc_binding.bindings) >= 1  # At least keyboard binding

    def test_load_flight_control_actions(self):
        """Test flight control actions are loaded."""
        config = InputConfig.load_from_directory("config/input_bindings")

        # Check pitch up action
        pitch_up_binding = config.get_action_binding("FLIGHT_PITCH_UP")
        assert pitch_up_binding is not None
        assert len(pitch_up_binding.bindings) >= 1

    def test_load_handler_priorities(self):
        """Test handler priorities are loaded."""
        config = InputConfig.load_from_directory("config/input_bindings")

        # Check some priorities
        assert config.get_handler_priority("checklist_menu") == 10
        assert config.get_handler_priority("atc_menu") == 20
        assert config.get_handler_priority("control_panel") == 100

    def test_get_all_action_bindings(self):
        """Test getting all action bindings."""
        config = InputConfig.load_from_directory("config/input_bindings")

        bindings = config.get_all_action_bindings()
        assert len(bindings) > 0

        # Check that all bindings have actions
        for binding in bindings:
            assert binding.action is not None
            assert len(binding.bindings) > 0

    def test_get_all_handler_priorities(self):
        """Test getting all handler priorities."""
        config = InputConfig.load_from_directory("config/input_bindings")

        priorities = config.get_all_handler_priorities()
        assert len(priorities) > 0
        assert "checklist_menu" in priorities
        assert "atc_menu" in priorities

    def test_get_handler_priority_default(self):
        """Test getting priority for unconfigured handler returns default."""
        config = InputConfig.load_from_directory("config/input_bindings")

        priority = config.get_handler_priority("nonexistent_handler")
        assert priority == 999  # Default priority


class TestKeyboardBindingParsing:
    """Test parsing of keyboard bindings from YAML."""

    def test_keyboard_f1_binding(self):
        """Test F1 keyboard binding matches event."""
        config = InputConfig.load_from_directory("config/input_bindings")
        atc_binding = config.get_action_binding("MENU_ATC")

        event = InputEvent.from_keyboard(key=pygame.K_F1, mods=0)
        assert atc_binding.matches(event)

    def test_keyboard_with_modifier(self):
        """Test keyboard binding with modifier."""
        config = InputConfig.load_from_directory("config/input_bindings")
        verify_yes_binding = config.get_action_binding("CHECKLIST_VERIFY_YES")

        # Should match Shift+Enter
        event = InputEvent.from_keyboard(key=pygame.K_RETURN, mods=pygame.KMOD_SHIFT)
        assert verify_yes_binding.matches(event)

    def test_keyboard_letter_key(self):
        """Test keyboard letter key binding."""
        config = InputConfig.load_from_directory("config/input_bindings")

        # Flight controls use arrow keys
        pitch_down_binding = config.get_action_binding("FLIGHT_PITCH_DOWN")
        event = InputEvent.from_keyboard(key=pygame.K_UP, mods=0)
        assert pitch_down_binding.matches(event)


class TestJoystickBindingParsing:
    """Test parsing of joystick bindings from YAML."""

    def test_joystick_button_binding(self):
        """Test joystick button binding matches event."""
        config = InputConfig.load_from_directory("config/input_bindings")
        atc_binding = config.get_action_binding("MENU_ATC")

        # Should match joystick button 0
        event = InputEvent.from_joystick_button(device_id="joy0", button=0)
        assert atc_binding.matches(event)

    def test_joystick_axis_positive(self):
        """Test joystick axis positive direction."""
        config = InputConfig.load_from_directory("config/input_bindings")
        roll_right_binding = config.get_action_binding("FLIGHT_ROLL_RIGHT")

        # Should match X axis positive
        event = InputEvent.from_joystick_axis(device_id="joy0", axis=0, value=0.8)
        assert roll_right_binding.matches(event)

    def test_joystick_axis_negative(self):
        """Test joystick axis negative direction."""
        config = InputConfig.load_from_directory("config/input_bindings")
        roll_left_binding = config.get_action_binding("FLIGHT_ROLL_LEFT")

        # Should match X axis negative
        event = InputEvent.from_joystick_axis(device_id="joy0", axis=0, value=-0.8)
        assert roll_left_binding.matches(event)


class TestNetworkBindingParsing:
    """Test parsing of network bindings from YAML."""

    def test_network_command_binding(self):
        """Test network command binding matches event."""
        config = InputConfig.load_from_directory("config/input_bindings")
        atc_binding = config.get_action_binding("MENU_ATC")

        # Should match network command
        event = InputEvent.from_network(command="open_atc_menu")
        assert atc_binding.matches(event)


class TestMultipleInputSources:
    """Test that actions can be triggered by multiple input sources."""

    def test_menu_atc_multiple_sources(self):
        """Test MENU_ATC can be triggered by keyboard, joystick, or network."""
        config = InputConfig.load_from_directory("config/input_bindings")
        atc_binding = config.get_action_binding("MENU_ATC")

        # Keyboard F1
        event_keyboard = InputEvent.from_keyboard(key=pygame.K_F1, mods=0)
        assert atc_binding.matches(event_keyboard)

        # Joystick button 0
        event_button = InputEvent.from_joystick_button(device_id="joy0", button=0)
        assert atc_binding.matches(event_button)

        # Network command
        event_network = InputEvent.from_network(command="open_atc_menu")
        assert atc_binding.matches(event_network)

    def test_flight_control_multiple_sources(self):
        """Test flight control can use keyboard or joystick."""
        config = InputConfig.load_from_directory("config/input_bindings")
        pitch_up_binding = config.get_action_binding("FLIGHT_PITCH_UP")

        # Keyboard DOWN
        event_keyboard = InputEvent.from_keyboard(key=pygame.K_DOWN, mods=0)
        assert pitch_up_binding.matches(event_keyboard)

        # Joystick Y axis positive
        event_joystick = InputEvent.from_joystick_axis(device_id="joy0", axis=1, value=0.8)
        assert pitch_up_binding.matches(event_joystick)

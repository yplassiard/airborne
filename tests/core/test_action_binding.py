"""Tests for action binding system."""

import pytest

from airborne.core.action_binding import (
    ActionBinding,
    ActionBindingRegistry,
    InputBinding,
)
from airborne.core.input_event import InputEvent


class TestInputBinding:
    """Test InputBinding creation and matching."""

    def test_from_keyboard(self):
        """Test creating keyboard binding."""
        binding = InputBinding.from_keyboard(key=1, mods=0)

        assert binding.key == 1
        assert binding.mods == 0

    def test_from_keyboard_with_mods(self):
        """Test creating keyboard binding with modifiers."""
        binding = InputBinding.from_keyboard(key=1, mods=64)

        assert binding.key == 1
        assert binding.mods == 64

    def test_from_joystick_button(self):
        """Test creating joystick button binding."""
        binding = InputBinding.from_joystick_button(button=0)

        assert binding.button == 0
        assert binding.device_id is None

    def test_from_joystick_button_with_device(self):
        """Test creating joystick button binding with device ID."""
        binding = InputBinding.from_joystick_button(button=0, device_id="joy0")

        assert binding.button == 0
        assert binding.device_id == "joy0"

    def test_from_joystick_axis(self):
        """Test creating joystick axis binding."""
        binding = InputBinding.from_joystick_axis(axis=1, threshold=0.7, direction="positive")

        assert binding.axis == 1
        assert binding.axis_threshold == 0.7
        assert binding.axis_direction == "positive"

    def test_from_network(self):
        """Test creating network binding."""
        binding = InputBinding.from_network(command="MENU_ATC")

        assert binding.network_command == "MENU_ATC"

    def test_matches_keyboard(self):
        """Test keyboard binding matches correct event."""
        binding = InputBinding.from_keyboard(key=1, mods=0)
        event = InputEvent.from_keyboard(key=1, mods=0)

        assert binding.matches(event)

    def test_matches_keyboard_wrong_key(self):
        """Test keyboard binding doesn't match wrong key."""
        binding = InputBinding.from_keyboard(key=1, mods=0)
        event = InputEvent.from_keyboard(key=2, mods=0)

        assert not binding.matches(event)

    def test_matches_keyboard_with_mods(self):
        """Test keyboard binding matches with modifiers."""
        binding = InputBinding.from_keyboard(key=1, mods=64)
        event = InputEvent.from_keyboard(key=1, mods=64)

        assert binding.matches(event)

    def test_matches_keyboard_wrong_mods(self):
        """Test keyboard binding doesn't match wrong modifiers."""
        binding = InputBinding.from_keyboard(key=1, mods=64)
        event = InputEvent.from_keyboard(key=1, mods=0)

        assert not binding.matches(event)

    def test_matches_button(self):
        """Test button binding matches correct event."""
        binding = InputBinding.from_joystick_button(button=0)
        event = InputEvent.from_joystick_button(device_id="joy0", button=0)

        assert binding.matches(event)

    def test_matches_button_wrong_button(self):
        """Test button binding doesn't match wrong button."""
        binding = InputBinding.from_joystick_button(button=0)
        event = InputEvent.from_joystick_button(device_id="joy0", button=1)

        assert not binding.matches(event)

    def test_matches_button_with_device_id(self):
        """Test button binding matches specific device."""
        binding = InputBinding.from_joystick_button(button=0, device_id="joy0")
        event = InputEvent.from_joystick_button(device_id="joy0", button=0)

        assert binding.matches(event)

    def test_matches_button_wrong_device_id(self):
        """Test button binding doesn't match wrong device."""
        binding = InputBinding.from_joystick_button(button=0, device_id="joy0")
        event = InputEvent.from_joystick_button(device_id="joy1", button=0)

        assert not binding.matches(event)

    def test_matches_axis_positive(self):
        """Test axis binding matches positive direction."""
        binding = InputBinding.from_joystick_axis(axis=1, threshold=0.5, direction="positive")
        event = InputEvent.from_joystick_axis(device_id="joy0", axis=1, value=0.8)

        assert binding.matches(event)

    def test_matches_axis_negative(self):
        """Test axis binding matches negative direction."""
        binding = InputBinding.from_joystick_axis(axis=1, threshold=0.5, direction="negative")
        event = InputEvent.from_joystick_axis(device_id="joy0", axis=1, value=-0.8)

        assert binding.matches(event)

    def test_matches_axis_both_directions(self):
        """Test axis binding matches both directions."""
        binding = InputBinding.from_joystick_axis(axis=1, threshold=0.5, direction="both")
        event_pos = InputEvent.from_joystick_axis(device_id="joy0", axis=1, value=0.8)
        event_neg = InputEvent.from_joystick_axis(device_id="joy0", axis=1, value=-0.8)

        assert binding.matches(event_pos)
        assert binding.matches(event_neg)

    def test_matches_axis_below_threshold(self):
        """Test axis binding doesn't match below threshold."""
        binding = InputBinding.from_joystick_axis(axis=1, threshold=0.5, direction="positive")
        event = InputEvent.from_joystick_axis(device_id="joy0", axis=1, value=0.3)

        assert not binding.matches(event)

    def test_matches_axis_wrong_direction(self):
        """Test axis binding doesn't match wrong direction."""
        binding = InputBinding.from_joystick_axis(axis=1, threshold=0.5, direction="positive")
        event = InputEvent.from_joystick_axis(device_id="joy0", axis=1, value=-0.8)

        assert not binding.matches(event)

    def test_matches_network(self):
        """Test network binding matches correct command."""
        binding = InputBinding.from_network(command="MENU_ATC")
        event = InputEvent.from_network(command="MENU_ATC")

        assert binding.matches(event)

    def test_matches_network_wrong_command(self):
        """Test network binding doesn't match wrong command."""
        binding = InputBinding.from_network(command="MENU_ATC")
        event = InputEvent.from_network(command="MENU_CHECKLIST")

        assert not binding.matches(event)

    def test_matches_wrong_source_type(self):
        """Test binding doesn't match different source type."""
        binding = InputBinding.from_keyboard(key=1, mods=0)
        event = InputEvent.from_joystick_button(device_id="joy0", button=0)

        assert not binding.matches(event)


class TestActionBinding:
    """Test ActionBinding functionality."""

    def test_create_action_binding(self):
        """Test creating action binding."""
        binding = ActionBinding(
            action="MENU_ATC",
            bindings=[InputBinding.from_keyboard(key=1, mods=0)],
        )

        assert binding.action == "MENU_ATC"
        assert len(binding.bindings) == 1
        assert binding.enabled is True

    def test_matches_single_binding(self):
        """Test action matches single input binding."""
        binding = ActionBinding(
            action="MENU_ATC",
            bindings=[InputBinding.from_keyboard(key=1, mods=0)],
        )
        event = InputEvent.from_keyboard(key=1, mods=0)

        assert binding.matches(event)

    def test_matches_multiple_bindings(self):
        """Test action matches any of multiple bindings."""
        binding = ActionBinding(
            action="MENU_ATC",
            bindings=[
                InputBinding.from_keyboard(key=1, mods=0),
                InputBinding.from_joystick_button(button=0),
            ],
        )

        event_keyboard = InputEvent.from_keyboard(key=1, mods=0)
        event_button = InputEvent.from_joystick_button(device_id="joy0", button=0)

        assert binding.matches(event_keyboard)
        assert binding.matches(event_button)

    def test_matches_disabled_action(self):
        """Test disabled action doesn't match."""
        binding = ActionBinding(
            action="MENU_ATC",
            bindings=[InputBinding.from_keyboard(key=1, mods=0)],
            enabled=False,
        )
        event = InputEvent.from_keyboard(key=1, mods=0)

        assert not binding.matches(event)

    def test_add_binding(self):
        """Test adding binding to action."""
        binding = ActionBinding(action="MENU_ATC", bindings=[])

        assert len(binding.bindings) == 0

        binding.add_binding(InputBinding.from_keyboard(key=1, mods=0))
        assert len(binding.bindings) == 1

    def test_remove_binding(self):
        """Test removing binding from action."""
        input_binding = InputBinding.from_keyboard(key=1, mods=0)
        binding = ActionBinding(action="MENU_ATC", bindings=[input_binding])

        assert len(binding.bindings) == 1

        binding.remove_binding(input_binding)
        assert len(binding.bindings) == 0

    def test_clear_bindings(self):
        """Test clearing all bindings."""
        binding = ActionBinding(
            action="MENU_ATC",
            bindings=[
                InputBinding.from_keyboard(key=1, mods=0),
                InputBinding.from_joystick_button(button=0),
            ],
        )

        assert len(binding.bindings) == 2

        binding.clear_bindings()
        assert len(binding.bindings) == 0

    def test_enable_disable(self):
        """Test enabling and disabling action."""
        binding = ActionBinding(
            action="MENU_ATC",
            bindings=[InputBinding.from_keyboard(key=1, mods=0)],
        )

        assert binding.enabled is True

        binding.disable()
        assert binding.enabled is False

        binding.enable()
        assert binding.enabled is True


class TestActionBindingRegistry:
    """Test ActionBindingRegistry functionality."""

    def test_register_action(self):
        """Test registering action."""
        registry = ActionBindingRegistry()
        binding = ActionBinding(
            action="MENU_ATC",
            bindings=[InputBinding.from_keyboard(key=1, mods=0)],
        )

        registry.register(binding)

        assert registry.get_binding("MENU_ATC") == binding

    def test_register_duplicate_raises_error(self):
        """Test registering duplicate action raises error."""
        registry = ActionBindingRegistry()
        binding1 = ActionBinding(action="MENU_ATC", bindings=[])
        binding2 = ActionBinding(action="MENU_ATC", bindings=[])

        registry.register(binding1)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(binding2)

    def test_unregister_action(self):
        """Test unregistering action."""
        registry = ActionBindingRegistry()
        binding = ActionBinding(action="MENU_ATC", bindings=[])

        registry.register(binding)
        assert registry.get_binding("MENU_ATC") is not None

        registry.unregister("MENU_ATC")
        assert registry.get_binding("MENU_ATC") is None

    def test_unregister_not_found_raises_error(self):
        """Test unregistering non-existent action raises error."""
        registry = ActionBindingRegistry()

        with pytest.raises(ValueError, match="not found"):
            registry.unregister("NONEXISTENT")

    def test_get_binding(self):
        """Test getting binding by action name."""
        registry = ActionBindingRegistry()
        binding = ActionBinding(action="MENU_ATC", bindings=[])

        registry.register(binding)

        retrieved = registry.get_binding("MENU_ATC")
        assert retrieved == binding

    def test_get_binding_not_found(self):
        """Test getting non-existent binding returns None."""
        registry = ActionBindingRegistry()

        assert registry.get_binding("NONEXISTENT") is None

    def test_get_matching_actions(self):
        """Test getting actions that match event."""
        registry = ActionBindingRegistry()
        registry.register(
            ActionBinding(
                action="MENU_ATC",
                bindings=[InputBinding.from_keyboard(key=1, mods=0)],
            )
        )
        registry.register(
            ActionBinding(
                action="MENU_CHECKLIST",
                bindings=[InputBinding.from_keyboard(key=2, mods=0)],
            )
        )

        event = InputEvent.from_keyboard(key=1, mods=0)
        actions = registry.get_matching_actions(event)

        assert "MENU_ATC" in actions
        assert "MENU_CHECKLIST" not in actions

    def test_get_matching_actions_multiple(self):
        """Test multiple actions can match same event."""
        registry = ActionBindingRegistry()
        registry.register(
            ActionBinding(
                action="ACTION1",
                bindings=[InputBinding.from_keyboard(key=1, mods=0)],
            )
        )
        registry.register(
            ActionBinding(
                action="ACTION2",
                bindings=[InputBinding.from_keyboard(key=1, mods=0)],
            )
        )

        event = InputEvent.from_keyboard(key=1, mods=0)
        actions = registry.get_matching_actions(event)

        assert len(actions) == 2
        assert "ACTION1" in actions
        assert "ACTION2" in actions

    def test_get_all_actions(self):
        """Test getting all registered action names."""
        registry = ActionBindingRegistry()
        registry.register(ActionBinding(action="ACTION1", bindings=[]))
        registry.register(ActionBinding(action="ACTION2", bindings=[]))

        actions = registry.get_all_actions()

        assert len(actions) == 2
        assert "ACTION1" in actions
        assert "ACTION2" in actions

    def test_clear(self):
        """Test clearing all bindings."""
        registry = ActionBindingRegistry()
        registry.register(ActionBinding(action="ACTION1", bindings=[]))
        registry.register(ActionBinding(action="ACTION2", bindings=[]))

        assert len(registry.get_all_actions()) == 2

        registry.clear()
        assert len(registry.get_all_actions()) == 0

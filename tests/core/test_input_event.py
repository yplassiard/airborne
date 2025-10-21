"""Tests for InputEvent abstraction."""


from airborne.core.input_event import InputEvent, InputSourceType


class TestInputEventCreation:
    """Test InputEvent factory methods."""

    def test_from_keyboard(self):
        """Test keyboard event creation."""
        event = InputEvent.from_keyboard(key=1, mods=0)

        assert event.source_type == InputSourceType.KEYBOARD
        assert event.device_id == "keyboard"
        assert event.key == 1
        assert event.mods == 0
        assert event.button is None
        assert event.axis is None

    def test_from_keyboard_with_mods(self):
        """Test keyboard event with modifiers."""
        event = InputEvent.from_keyboard(key=115, mods=64)  # S with Ctrl

        assert event.source_type == InputSourceType.KEYBOARD
        assert event.key == 115
        assert event.mods == 64

    def test_from_joystick_button(self):
        """Test joystick button event creation."""
        event = InputEvent.from_joystick_button(device_id="joy0", button=3)

        assert event.source_type == InputSourceType.JOYSTICK_BUTTON
        assert event.device_id == "joy0"
        assert event.button == 3
        assert event.key is None

    def test_from_joystick_axis(self):
        """Test joystick axis event creation."""
        event = InputEvent.from_joystick_axis(device_id="joy0", axis=1, value=0.8)

        assert event.source_type == InputSourceType.JOYSTICK_AXIS
        assert event.device_id == "joy0"
        assert event.axis == 1
        assert event.axis_value == 0.8

    def test_from_joystick_hat(self):
        """Test joystick hat event creation."""
        event = InputEvent.from_joystick_hat(device_id="joy0", hat=0, value=(1, 0))

        assert event.source_type == InputSourceType.JOYSTICK_HAT
        assert event.device_id == "joy0"
        assert event.hat == 0
        assert event.hat_value == (1, 0)

    def test_from_network(self):
        """Test network event creation."""
        event = InputEvent.from_network(command="MENU_ATC")

        assert event.source_type == InputSourceType.NETWORK
        assert event.device_id == "network"
        assert event.network_command == "MENU_ATC"

    def test_from_network_with_metadata(self):
        """Test network event with metadata."""
        metadata = {"client_id": "12345", "timestamp": 1234567890}
        event = InputEvent.from_network(command="MENU_ATC", metadata=metadata)

        assert event.network_command == "MENU_ATC"
        assert event.metadata == metadata


class TestInputEventMatching:
    """Test InputEvent matching methods."""

    def test_matches_keyboard_key_only(self):
        """Test keyboard matching without modifiers."""
        event = InputEvent.from_keyboard(key=115, mods=0)

        assert event.matches_keyboard(key=115)
        assert not event.matches_keyboard(key=116)

    def test_matches_keyboard_with_mods(self):
        """Test keyboard matching with modifiers."""
        event = InputEvent.from_keyboard(key=115, mods=64)  # S with Ctrl

        assert event.matches_keyboard(key=115, mods=64)
        assert event.matches_keyboard(key=115)  # mods=0 means don't check mods
        assert not event.matches_keyboard(key=116, mods=64)

    def test_matches_keyboard_wrong_source(self):
        """Test keyboard matching fails for non-keyboard events."""
        event = InputEvent.from_joystick_button(device_id="joy0", button=0)

        assert not event.matches_keyboard(key=115)

    def test_matches_button(self):
        """Test button matching."""
        event = InputEvent.from_joystick_button(device_id="joy0", button=3)

        assert event.matches_button(button=3)
        assert not event.matches_button(button=4)

    def test_matches_button_with_device_id(self):
        """Test button matching with device ID filter."""
        event = InputEvent.from_joystick_button(device_id="joy0", button=3)

        assert event.matches_button(button=3, device_id="joy0")
        assert not event.matches_button(button=3, device_id="joy1")

    def test_matches_button_wrong_source(self):
        """Test button matching fails for non-button events."""
        event = InputEvent.from_keyboard(key=115, mods=0)

        assert not event.matches_button(button=3)

    def test_matches_axis_above_threshold(self):
        """Test axis matching with value above threshold."""
        event = InputEvent.from_joystick_axis(device_id="joy0", axis=1, value=0.8)

        assert event.matches_axis(axis=1, threshold=0.5)
        assert event.matches_axis(axis=1, threshold=0.7)
        assert not event.matches_axis(axis=1, threshold=0.9)

    def test_matches_axis_below_threshold(self):
        """Test axis matching with value below threshold."""
        event = InputEvent.from_joystick_axis(device_id="joy0", axis=1, value=0.3)

        assert not event.matches_axis(axis=1, threshold=0.5)

    def test_matches_axis_negative_value(self):
        """Test axis matching with negative value."""
        event = InputEvent.from_joystick_axis(device_id="joy0", axis=1, value=-0.8)

        assert event.matches_axis(axis=1, threshold=0.5)  # Uses absolute value

    def test_matches_axis_with_device_id(self):
        """Test axis matching with device ID filter."""
        event = InputEvent.from_joystick_axis(device_id="joy0", axis=1, value=0.8)

        assert event.matches_axis(axis=1, device_id="joy0")
        assert not event.matches_axis(axis=1, device_id="joy1")

    def test_matches_axis_wrong_source(self):
        """Test axis matching fails for non-axis events."""
        event = InputEvent.from_keyboard(key=115, mods=0)

        assert not event.matches_axis(axis=1)

    def test_matches_network_command(self):
        """Test network command matching."""
        event = InputEvent.from_network(command="MENU_ATC")

        assert event.matches_network_command("MENU_ATC")
        assert not event.matches_network_command("MENU_CHECKLIST")

    def test_matches_network_command_wrong_source(self):
        """Test network command matching fails for non-network events."""
        event = InputEvent.from_keyboard(key=115, mods=0)

        assert not event.matches_network_command("MENU_ATC")


class TestInputEventEdgeCases:
    """Test edge cases and special scenarios."""

    def test_keyboard_mods_zero_means_ignore(self):
        """Test that mods=0 in matches_keyboard ignores modifiers."""
        event = InputEvent.from_keyboard(key=115, mods=64)

        # When checking with mods=0, should match regardless of actual mods
        assert event.matches_keyboard(key=115, mods=0)

    def test_axis_zero_below_threshold(self):
        """Test that zero axis value is below default threshold."""
        event = InputEvent.from_joystick_axis(device_id="joy0", axis=1, value=0.0)

        assert not event.matches_axis(axis=1)  # Default threshold is 0.5

    def test_axis_custom_threshold(self):
        """Test axis matching with custom threshold."""
        event = InputEvent.from_joystick_axis(device_id="joy0", axis=1, value=0.2)

        assert not event.matches_axis(axis=1, threshold=0.5)
        assert event.matches_axis(axis=1, threshold=0.1)

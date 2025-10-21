"""Unit tests for generic Menu base class."""

import pytest

from airborne.core.messaging import MessageQueue
from airborne.ui.menu import Menu, MenuOption


class ConcreteTestMenu(Menu):
    """Concrete test implementation of Menu."""

    def __init__(self, message_queue=None, sender_name="test_menu"):
        """Initialize test menu."""
        super().__init__(message_queue, sender_name)
        self.build_called = False
        self.handle_called = False
        self.handle_option = None
        self.test_options = []
        self.is_available_return = True

    def _build_options(self, context):
        """Build test options."""
        self.build_called = True
        return self.test_options

    def _handle_selection(self, option):
        """Handle test selection."""
        self.handle_called = True
        self.handle_option = option

    def _get_menu_opened_message(self):
        """Get menu opened message."""
        return "MSG_TEST_MENU_OPENED"

    def _get_menu_closed_message(self):
        """Get menu closed message."""
        return "MSG_TEST_MENU_CLOSED"

    def _get_invalid_option_message(self):
        """Get invalid option message."""
        return "MSG_TEST_INVALID_OPTION"

    def _is_available(self, context):
        """Check if menu is available."""
        return self.is_available_return


@pytest.fixture
def message_queue():
    """Create message queue for testing."""
    return MessageQueue()


@pytest.fixture
def menu(message_queue):
    """Create test menu."""
    return ConcreteTestMenu(message_queue)


def test_menu_initialization(menu):
    """Test menu initializes correctly."""
    assert menu is not None
    assert menu.get_state() == "CLOSED"
    assert not menu.is_open()
    assert len(menu.get_current_options()) == 0


def test_menu_open_with_options(menu):
    """Test menu opens successfully with options."""
    menu.test_options = [
        MenuOption(key="1", label="Option 1", message_key="MSG_OPT_1"),
        MenuOption(key="2", label="Option 2", message_key="MSG_OPT_2"),
    ]

    result = menu.open()

    assert result is True
    assert menu.is_open()
    assert menu.get_state() == "OPEN"
    assert menu.build_called
    assert len(menu.get_current_options()) == 2


def test_menu_open_without_options(menu):
    """Test menu does not open without options."""
    menu.test_options = []

    result = menu.open()

    assert result is False
    assert not menu.is_open()
    assert menu.get_state() == "CLOSED"


def test_menu_open_when_not_available(menu):
    """Test menu does not open when not available."""
    menu.test_options = [MenuOption(key="1", label="Option 1")]
    menu.is_available_return = False

    result = menu.open()

    assert result is False
    assert not menu.is_open()


def test_menu_close(menu):
    """Test menu closes correctly."""
    menu.test_options = [MenuOption(key="1", label="Option 1", message_key="MSG_OPT_1")]
    menu.open()

    menu.close()

    assert not menu.is_open()
    assert menu.get_state() == "CLOSED"
    assert len(menu.get_current_options()) == 0


def test_menu_select_option(menu):
    """Test selecting option by key."""
    option1 = MenuOption(key="1", label="Option 1", message_key="MSG_OPT_1", data={"action": "test"})
    option2 = MenuOption(key="2", label="Option 2", message_key="MSG_OPT_2")
    menu.test_options = [option1, option2]
    menu.open()

    result = menu.select_option("1")

    assert result is True
    assert menu.handle_called
    assert menu.handle_option == option1
    assert menu.handle_option.data["action"] == "test"


def test_menu_select_invalid_option(menu):
    """Test selecting invalid option."""
    menu.test_options = [MenuOption(key="1", label="Option 1", message_key="MSG_OPT_1")]
    menu.open()

    result = menu.select_option("9")

    assert result is False
    assert not menu.handle_called


def test_menu_select_disabled_option(menu):
    """Test selecting disabled option fails."""
    menu.test_options = [
        MenuOption(key="1", label="Option 1", message_key="MSG_OPT_1", enabled=False)
    ]
    menu.open()

    result = menu.select_option("1")

    assert result is False
    assert not menu.handle_called


def test_menu_select_when_closed(menu):
    """Test selecting option when menu is closed."""
    result = menu.select_option("1")

    assert result is False
    assert not menu.handle_called


def test_menu_move_selection_down(menu):
    """Test moving selection down."""
    menu.test_options = [
        MenuOption(key="1", label="Option 1", message_key="MSG_OPT_1"),
        MenuOption(key="2", label="Option 2", message_key="MSG_OPT_2"),
        MenuOption(key="3", label="Option 3", message_key="MSG_OPT_3"),
    ]
    menu.open()

    # Initially at index 0
    assert menu._selected_index == 0

    # Move down
    result = menu.move_selection_down()
    assert result is True
    assert menu._selected_index == 1

    # Move down again
    result = menu.move_selection_down()
    assert result is True
    assert menu._selected_index == 2

    # At bottom, cannot move
    result = menu.move_selection_down()
    assert result is False
    assert menu._selected_index == 2


def test_menu_move_selection_up(menu):
    """Test moving selection up."""
    menu.test_options = [
        MenuOption(key="1", label="Option 1", message_key="MSG_OPT_1"),
        MenuOption(key="2", label="Option 2", message_key="MSG_OPT_2"),
        MenuOption(key="3", label="Option 3", message_key="MSG_OPT_3"),
    ]
    menu.open()

    # Move to index 2
    menu.move_selection_down()
    menu.move_selection_down()
    assert menu._selected_index == 2

    # Move up
    result = menu.move_selection_up()
    assert result is True
    assert menu._selected_index == 1

    # Move up again
    result = menu.move_selection_up()
    assert result is True
    assert menu._selected_index == 0

    # At top, cannot move
    result = menu.move_selection_up()
    assert result is False
    assert menu._selected_index == 0


def test_menu_select_current(menu):
    """Test selecting current option."""
    option1 = MenuOption(key="1", label="Option 1", message_key="MSG_OPT_1")
    option2 = MenuOption(key="2", label="Option 2", message_key="MSG_OPT_2")
    menu.test_options = [option1, option2]
    menu.open()

    # Initially at index 0
    result = menu.select_current()
    assert result is True
    assert menu.handle_option == option1

    # Reset and move to index 1
    menu.handle_called = False
    menu.handle_option = None
    menu.close()
    menu.open()
    menu.move_selection_down()

    result = menu.select_current()
    assert result is True
    assert menu.handle_option == option2


def test_menu_navigation_with_disabled_options(menu):
    """Test navigation skips disabled options correctly."""
    menu.test_options = [
        MenuOption(key="1", label="Option 1", message_key="MSG_OPT_1", enabled=True),
        MenuOption(key="2", label="Option 2", message_key="MSG_OPT_2", enabled=False),
        MenuOption(key="3", label="Option 3", message_key="MSG_OPT_3", enabled=True),
    ]
    menu.open()

    # Initially at index 0 (option 1, enabled)
    assert menu._selected_index == 0

    # Move down - should move to index 1 (but skip disabled in enabled list)
    result = menu.move_selection_down()
    assert result is True
    # Selected index is 1, which corresponds to enabled option at actual index 2
    assert menu._selected_index == 1


def test_menu_get_current_options_returns_copy(menu):
    """Test get_current_options returns a copy."""
    menu.test_options = [MenuOption(key="1", label="Option 1", message_key="MSG_OPT_1")]
    menu.open()

    options = menu.get_current_options()
    options.append(MenuOption(key="2", label="Option 2", message_key="MSG_OPT_2"))

    # Original should not be modified
    assert len(menu.get_current_options()) == 1


def test_menu_tts_announcements(menu, message_queue):
    """Test that TTS messages are published correctly."""
    captured_messages = []

    def capture_handler(msg):
        captured_messages.append(msg)

    message_queue.subscribe("ui.tts.speak", capture_handler)

    menu.test_options = [
        MenuOption(key="1", label="Option 1", message_key="MSG_OPT_1"),
        MenuOption(key="2", label="Option 2", message_key="MSG_OPT_2"),
    ]

    # Open menu
    menu.open()
    message_queue.process()

    # Should have announced menu opened + first option
    assert len(captured_messages) > 0
    assert "MSG_TEST_MENU_OPENED" in str(captured_messages[-1].data.get("text"))

    # Close menu
    captured_messages.clear()
    menu.close()
    message_queue.process()

    # Should have announced menu closed
    assert len(captured_messages) > 0
    assert "MSG_TEST_MENU_CLOSED" in str(captured_messages[-1].data.get("text"))


def test_menu_option_dataclass():
    """Test MenuOption dataclass."""
    option = MenuOption(
        key="1",
        label="Test Option",
        message_key="MSG_TEST",
        data={"custom": "value"},
        enabled=True,
    )

    assert option.key == "1"
    assert option.label == "Test Option"
    assert option.message_key == "MSG_TEST"
    assert option.data["custom"] == "value"
    assert option.enabled is True


def test_menu_option_defaults():
    """Test MenuOption default values."""
    option = MenuOption(key="1", label="Test")

    assert option.message_key is None
    assert option.data is None
    assert option.enabled is True

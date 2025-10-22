"""Unit tests for Question widget."""

import pytest

from airborne.core.messaging import MessageQueue
from airborne.ui.question import Question, QuestionOption


@pytest.fixture
def message_queue():
    """Create message queue for testing."""
    return MessageQueue()


@pytest.fixture
def question(message_queue):
    """Create question widget."""
    return Question(message_queue, "test_question")


def test_question_initialization(question):
    """Test question initializes correctly."""
    assert question is not None
    assert question.get_state() == "CLOSED"
    assert not question.is_waiting()


def test_question_ask(question):
    """Test asking a question."""
    options = [
        QuestionOption(key="y", label="Yes", message_key="MSG_YES"),
        QuestionOption(key="n", label="No", message_key="MSG_NO"),
    ]

    result = question.ask(
        prompt_message="MSG_CONFIRM",
        options=options,
    )

    assert result is True
    assert question.is_waiting()
    assert question.get_state() == "WAITING_INPUT"
    assert len(question.get_options()) == 2


def test_question_ask_without_options(question):
    """Test asking question without options fails."""
    result = question.ask(
        prompt_message="MSG_CONFIRM",
        options=[],
    )

    assert result is False
    assert not question.is_waiting()


def test_question_ask_when_already_waiting(question):
    """Test asking question when already waiting fails."""
    options = [QuestionOption(key="y", label="Yes")]

    question.ask("MSG_CONFIRM", options)

    # Try to ask again
    result = question.ask("MSG_ANOTHER", options)

    assert result is False


def test_question_respond(question):
    """Test responding to question."""
    callback_called = False
    callback_option = None

    def on_response(option):
        nonlocal callback_called, callback_option
        callback_called = True
        callback_option = option

    yes_option = QuestionOption(key="y", label="Yes", message_key="MSG_YES", data="yes_data")
    no_option = QuestionOption(key="n", label="No", message_key="MSG_NO")

    question.ask(
        prompt_message="MSG_CONFIRM",
        options=[yes_option, no_option],
        on_response=on_response,
    )

    result = question.respond("y")

    assert result is True
    assert callback_called
    assert callback_option == yes_option
    assert callback_option.data == "yes_data"
    assert not question.is_waiting()
    assert question.get_state() == "CLOSED"


def test_question_respond_case_insensitive(question):
    """Test responding is case-insensitive."""
    callback_called = False

    def on_response(option):
        nonlocal callback_called
        callback_called = True

    question.ask(
        prompt_message="MSG_CONFIRM",
        options=[QuestionOption(key="Y", label="Yes")],
        on_response=on_response,
    )

    result = question.respond("y")

    assert result is True
    assert callback_called


def test_question_respond_invalid(question):
    """Test responding with invalid key."""
    callback_called = False

    def on_response(option):
        nonlocal callback_called
        callback_called = True

    question.ask(
        prompt_message="MSG_CONFIRM",
        options=[QuestionOption(key="y", label="Yes")],
        on_response=on_response,
    )

    result = question.respond("x")

    assert result is False
    assert not callback_called
    assert question.is_waiting()  # Still waiting


def test_question_respond_when_not_waiting(question):
    """Test responding when not waiting fails."""
    result = question.respond("y")

    assert result is False


def test_question_close(question):
    """Test closing question."""
    question.ask(
        prompt_message="MSG_CONFIRM",
        options=[QuestionOption(key="y", label="Yes")],
    )

    question.close()

    assert not question.is_waiting()
    assert question.get_state() == "CLOSED"
    assert len(question.get_options()) == 0


def test_question_close_when_already_closed(question):
    """Test closing when already closed doesn't crash."""
    question.close()
    question.close()  # Should not crash

    assert question.get_state() == "CLOSED"


def test_question_get_options_returns_copy(question):
    """Test get_options returns a copy."""
    options = [QuestionOption(key="y", label="Yes")]
    question.ask("MSG_CONFIRM", options)

    retrieved_options = question.get_options()
    retrieved_options.append(QuestionOption(key="n", label="No"))

    # Original should not be modified
    assert len(question.get_options()) == 1


def test_question_callback_exception_handling(question):
    """Test callback exceptions are caught."""

    def bad_callback(option):
        raise RuntimeError("Test error")

    question.ask(
        prompt_message="MSG_CONFIRM",
        options=[QuestionOption(key="y", label="Yes")],
        on_response=bad_callback,
    )

    # Should not raise, just log error
    result = question.respond("y")

    assert result is True
    assert not question.is_waiting()


def test_question_tts_announcements(question, message_queue):
    """Test that TTS messages are published correctly."""
    captured_messages = []

    def capture_handler(msg):
        captured_messages.append(msg)

    message_queue.subscribe("ui.tts.speak", capture_handler)

    options = [
        QuestionOption(key="y", label="Yes", message_key="MSG_YES"),
        QuestionOption(key="n", label="No", message_key="MSG_NO"),
    ]

    # Ask question
    question.ask("MSG_CONFIRM", options)
    message_queue.process()

    # Should have announced question
    assert len(captured_messages) > 0
    message_data = captured_messages[-1].data.get("text")
    assert "MSG_CONFIRM" in str(message_data)


def test_question_option_dataclass():
    """Test QuestionOption dataclass."""
    option = QuestionOption(
        key="y",
        label="Yes",
        message_key="MSG_YES",
        data={"value": True},
    )

    assert option.key == "y"
    assert option.label == "Yes"
    assert option.message_key == "MSG_YES"
    assert option.data["value"] is True


def test_question_option_defaults():
    """Test QuestionOption default values."""
    option = QuestionOption(key="y", label="Yes")

    assert option.message_key is None
    assert option.data is None

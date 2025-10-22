"""Question widget for interactive prompts and confirmations.

This module provides a reusable widget for asking questions and waiting for
user responses. Used for yes/no confirmations, multi-choice selections, and
other interactive prompts.

Typical usage:
    question = Question(
        message_queue=message_queue,
        prompt_message="MSG_CONFIRM_ACTION",
        options=[
            QuestionOption(key="y", label="Yes", message_key="MSG_YES"),
            QuestionOption(key="n", label="No", message_key="MSG_NO"),
        ]
    )

    question.ask(on_response=handle_response)
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageQueue, MessageTopic

logger = get_logger(__name__)


@dataclass
class QuestionOption:
    """Represents a response option for a question.

    Attributes:
        key: Key to select this option (e.g., "y", "n", "1").
        label: Human-readable label.
        message_key: TTS message key for this option.
        data: Additional data associated with this option.
    """

    key: str
    label: str
    message_key: str | None = None
    data: Any = None


class Question:
    """Widget for asking questions and handling responses.

    Provides:
    - Present question with multiple options
    - Wait for user response
    - TTS announcements
    - Callback on response

    States:
    - CLOSED: Not asking question
    - WAITING_INPUT: Waiting for user to respond
    """

    def __init__(
        self,
        message_queue: MessageQueue | None = None,
        sender_name: str = "question",
    ):
        """Initialize question widget.

        Args:
            message_queue: Message queue for TTS announcements.
            sender_name: Name used as message sender.
        """
        self._message_queue = message_queue
        self._sender_name = sender_name
        self._state = "CLOSED"
        self._prompt_message: str | None = None
        self._options: list[QuestionOption] = []
        self._on_response: Callable[[QuestionOption], None] | None = None

        logger.debug("%s initialized", sender_name)

    def ask(
        self,
        prompt_message: str,
        options: list[QuestionOption],
        on_response: Callable[[QuestionOption], None] | None = None,
    ) -> bool:
        """Ask a question and wait for response.

        Args:
            prompt_message: TTS message key for the question prompt.
            options: List of QuestionOption for possible responses.
            on_response: Callback function called when user responds.

        Returns:
            True if question was asked, False otherwise.
        """
        if self._state != "CLOSED":
            logger.warning("%s already waiting for response", self._sender_name)
            return False

        if not options:
            logger.warning("%s asked with no options", self._sender_name)
            return False

        self._prompt_message = prompt_message
        self._options = options
        self._on_response = on_response
        self._state = "WAITING_INPUT"

        logger.info("%s asking with %d options", self._sender_name, len(options))

        # Announce question
        self._announce_question()

        return True

    def respond(self, key: str) -> bool:
        """Respond to the question with a key.

        Args:
            key: Key of selected option.

        Returns:
            True if response was valid, False otherwise.
        """
        if self._state != "WAITING_INPUT":
            logger.warning("%s not waiting for response", self._sender_name)
            return False

        # Find option by key
        selected_option = None
        for option in self._options:
            if option.key.lower() == key.lower():
                selected_option = option
                break

        if not selected_option:
            logger.debug("%s invalid response: %s", self._sender_name, key)
            self._announce_invalid()
            return False

        logger.info("%s response: %s", self._sender_name, selected_option.label)

        # Call callback
        if self._on_response:
            try:
                self._on_response(selected_option)
            except Exception as e:
                logger.error("%s response callback error: %s", self._sender_name, e)

        # Close question
        self.close()

        return True

    def close(self) -> None:
        """Close the question without responding."""
        if self._state == "CLOSED":
            return

        self._state = "CLOSED"
        self._prompt_message = None
        self._options = []
        self._on_response = None

        logger.debug("%s closed", self._sender_name)

    def is_waiting(self) -> bool:
        """Check if waiting for response.

        Returns:
            True if waiting for user input.
        """
        return self._state == "WAITING_INPUT"

    def get_state(self) -> str:
        """Get current state.

        Returns:
            Current state string.
        """
        return self._state

    def get_options(self) -> list[QuestionOption]:
        """Get current options.

        Returns:
            Copy of options list.
        """
        return self._options.copy()

    # TTS announcements

    def _announce_question(self) -> None:
        """Announce the question prompt via TTS."""
        if not self._message_queue or not self._prompt_message:
            return

        # Build message: prompt + list options
        message_keys = [self._prompt_message]

        # Add options (for simple yes/no, announce both)
        for option in self._options:
            if option.message_key:
                message_keys.append(option.message_key)

        self._speak(message_keys, interrupt=True)

    def _announce_invalid(self) -> None:
        """Announce invalid response via TTS."""
        if not self._message_queue:
            return

        self._speak("MSG_INVALID_OPTION")

    def _speak(
        self,
        message_keys: str | list[str],
        priority: str = "high",
        interrupt: bool = False,
    ) -> None:
        """Speak message via TTS.

        Args:
            message_keys: Message key or list of keys.
            priority: Priority level.
            interrupt: Whether to interrupt current speech.
        """
        if not self._message_queue:
            return

        self._message_queue.publish(
            Message(
                sender=self._sender_name,
                recipients=["*"],
                topic=MessageTopic.TTS_SPEAK,
                data={"text": message_keys, "priority": priority, "interrupt": interrupt},
                priority=MessagePriority.HIGH if priority == "high" else MessagePriority.NORMAL,
            )
        )

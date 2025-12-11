"""ATC message queue system with realistic timing and priority handling.

This module implements a FIFO message queue for ATC communications with:
- Minimum 2-second spacing between messages
- Random delays (2-10 seconds) for realistic ATC response times
- Priority-based message ordering
- Only one message plays at a time

Typical usage example:
    queue = ATCMessageQueue(atc_audio_manager)

    # Enqueue pilot message
    pilot_msg = ATCMessage(
        message_key="PILOT_REQUEST_TAXI",
        sender="PILOT",
        delay_after=3.0
    )
    queue.enqueue(pilot_msg)

    # Process queue every frame
    queue.process(dt)
"""

import random
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


@dataclass
class ATCMessage:
    """Represents a single ATC or pilot radio transmission.

    Attributes:
        message_key: Message key(s) from atc_en.yaml (single key or list for sequence).
        sender: Who is transmitting - "PILOT" or "ATC".
        priority: Message priority (0-10, higher = more urgent, default 0).
        delay_after: Seconds to wait after this message completes (default 2.0).
        callback: Optional callback function called when message completes playback.
        timestamp: Time when message was enqueued (set automatically).
    """

    message_key: str | list[str]
    sender: str  # "PILOT" or "ATC"
    priority: int = 0
    delay_after: float = 2.0
    callback: Callable[[], None] | None = None
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        """Validate message attributes."""
        if self.sender not in ("PILOT", "ATC"):
            raise ValueError(f"sender must be 'PILOT' or 'ATC', got: {self.sender}")
        if self.priority < 0 or self.priority > 10:
            raise ValueError(f"priority must be 0-10, got: {self.priority}")
        if self.delay_after < 0:
            raise ValueError(f"delay_after must be >= 0, got: {self.delay_after}")


class ATCMessageQueue:
    """FIFO message queue for ATC communications with realistic timing.

    Manages the queuing and playback of ATC and pilot radio transmissions,
    ensuring proper spacing between messages and handling priority ordering.

    The queue has three states:
    - IDLE: No messages playing or waiting
    - TRANSMITTING: Currently playing a message
    - WAITING: Finished message, waiting for delay before next

    Examples:
        >>> queue = ATCMessageQueue(atc_audio)
        >>> msg = ATCMessage("PILOT_REQUEST_TAXI", "PILOT", delay_after=3.0)
        >>> queue.enqueue(msg)
        >>> queue.process(0.016)  # Call every frame
        >>> queue.is_busy()
        True
    """

    def __init__(self, atc_audio_manager: Any, min_delay: float = 2.0, max_delay: float = 10.0):
        """Initialize the ATC message queue.

        Args:
            atc_audio_manager: ATCAudioManager instance for playing messages.
            min_delay: Minimum random delay for ATC responses (seconds, default 2.0).
            max_delay: Maximum random delay for ATC responses (seconds, default 10.0).
        """
        self._atc_audio = atc_audio_manager
        self._queue: deque[ATCMessage] = deque()
        self._current_message: ATCMessage | None = None
        self._current_source_id: int | None = None
        self._wait_until: float = 0.0
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._state: str = "IDLE"  # IDLE, TRANSMITTING, WAITING

        logger.info(f"ATC message queue initialized (delay range: {min_delay}-{max_delay}s)")

    def enqueue(self, message: ATCMessage) -> None:
        """Add a message to the queue.

        Messages are inserted based on priority (higher priority goes first).
        Messages with the same priority maintain FIFO order.

        Args:
            message: ATCMessage to enqueue.

        Note:
            Emergency messages (priority >= 9) can interrupt current transmission.
        """
        # Find insertion point based on priority
        insert_index = len(self._queue)
        for i, queued_msg in enumerate(self._queue):
            if message.priority > queued_msg.priority:
                insert_index = i
                break

        self._queue.insert(insert_index, message)

        logger.debug(
            f"Enqueued {message.sender} message: {message.message_key} "
            f"(priority={message.priority}, queue_size={len(self._queue)})"
        )

        # Emergency messages can interrupt current transmission
        if message.priority >= 9 and self._state == "TRANSMITTING":
            logger.warning(
                f"Emergency message interrupting current transmission: {message.message_key}"
            )
            self._interrupt_current()

    def process(self, dt: float) -> None:
        """Process the queue (call every frame).

        Handles state transitions and message playback.

        Args:
            dt: Delta time since last frame (seconds).
        """
        current_time = time.time()

        # Update ATCAudioManager to cleanup finished playback
        if hasattr(self._atc_audio, "update"):
            self._atc_audio.update()

        # State: WAITING - Waiting for delay to expire
        if self._state == "WAITING":
            if current_time >= self._wait_until:
                self._state = "IDLE"
                logger.debug("Wait period expired, returning to IDLE")

        # State: TRANSMITTING - Check if current message finished
        elif self._state == "TRANSMITTING" and self._current_message:
            # Check if audio is still playing using ATCAudioManager.is_playing()
            is_still_playing = False
            if hasattr(self._atc_audio, "is_playing"):
                is_still_playing = self._atc_audio.is_playing()

            if not is_still_playing:
                # Audio finished, transition to WAITING
                self._complete_current_message()

        # State: IDLE - Start next message if available
        if self._state == "IDLE" and len(self._queue) > 0:
            self._play_next_message()

    def _is_dynamic_text(self, message_key: str | list[str]) -> bool:
        """Check if message_key contains dynamic text vs a config key.

        Dynamic text contains spaces (natural speech), while config keys
        use underscores (e.g., "ATC_TOWER_CLEARED_TAKEOFF").

        Args:
            message_key: Message key or dynamic text.

        Returns:
            True if the message is dynamic text.
        """
        if isinstance(message_key, list):
            # Lists of keys are always config keys
            return False
        # Dynamic text has spaces, config keys use underscores
        return " " in message_key

    def _play_next_message(self) -> None:
        """Play the next message in the queue."""
        if not self._queue:
            return

        self._current_message = self._queue.popleft()

        # Truncate for logging
        msg_display = self._current_message.message_key
        if isinstance(msg_display, str) and len(msg_display) > 60:
            msg_display = msg_display[:60] + "..."

        logger.info(f"Playing {self._current_message.sender} message: {msg_display}")

        try:
            # Check if this is dynamic text or a config key
            if self._is_dynamic_text(self._current_message.message_key):
                # Dynamic text - use play_dynamic_speech (generates TTS on main thread)
                # Note: TTS must run on main thread (pyttsx3/NSSpeechSynthesizer requirement)
                if hasattr(self._atc_audio, "play_dynamic_speech"):
                    self._current_source_id = self._atc_audio.play_dynamic_speech(
                        self._current_message.message_key,
                        sender=self._current_message.sender,
                        volume=1.0,
                    )
                else:
                    logger.warning("play_dynamic_speech not available, skipping")
                    self._complete_current_message()
                    return
            else:
                # Config key - use play_atc_message (pre-recorded, non-blocking)
                self._current_source_id = self._atc_audio.play_atc_message(
                    self._current_message.message_key, volume=1.0
                )

            self._state = "TRANSMITTING"

        except Exception as e:
            logger.error(f"Error playing message: {e}")
            self._complete_current_message()

    def _complete_current_message(self) -> None:
        """Complete current message and set up wait period."""
        if not self._current_message:
            return

        # Calculate wait period
        if self._current_message.sender == "ATC":
            # ATC responses have randomized delay
            delay = random.uniform(self._min_delay, self._max_delay)
        else:
            # Pilot messages use specified delay
            delay = self._current_message.delay_after

        self._wait_until = time.time() + delay

        logger.debug(
            f"Message completed, waiting {delay:.1f}s before next "
            f"(sender={self._current_message.sender})"
        )

        # Call completion callback if provided
        if self._current_message.callback:
            try:
                self._current_message.callback()
            except Exception as e:
                logger.error(f"Error in message callback: {e}")

        # Clear current message
        self._current_message = None
        self._current_source_id = None
        self._state = "WAITING"

    def _interrupt_current(self) -> None:
        """Interrupt current message (for emergency transmissions)."""
        if self._current_message:
            logger.warning(f"Interrupting message: {self._current_message.message_key}")
            # Stop current audio playback
            # Note: This would require ATCAudioManager to have a stop() method
            # For now, we just reset state
            self._current_message = None
            self._current_source_id = None
            self._state = "IDLE"

    def is_busy(self) -> bool:
        """Check if queue is busy (transmitting or waiting).

        Returns:
            True if currently transmitting or waiting.
        """
        return self._state in ("TRANSMITTING", "WAITING")

    def is_transmitting(self) -> bool:
        """Check if currently transmitting a message.

        Returns:
            True if a message is currently playing.
        """
        return self._state == "TRANSMITTING"

    def get_queue_size(self) -> int:
        """Get number of messages in queue.

        Returns:
            Number of queued messages waiting to be transmitted.
        """
        return len(self._queue)

    def get_current_message(self) -> ATCMessage | None:
        """Get currently transmitting message.

        Returns:
            Current ATCMessage or None if not transmitting.
        """
        return self._current_message

    def clear(self) -> None:
        """Clear all queued messages and reset state.

        Note:
            Does not interrupt currently playing message.
        """
        cleared_count = len(self._queue)
        self._queue.clear()

        if cleared_count > 0:
            logger.info(f"Cleared {cleared_count} messages from queue")

    def shutdown(self) -> None:
        """Shutdown the queue and clear all messages."""
        self.clear()
        self._current_message = None
        self._current_source_id = None
        self._state = "IDLE"
        logger.info("ATC message queue shut down")

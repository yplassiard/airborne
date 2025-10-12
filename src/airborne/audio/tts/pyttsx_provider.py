"""pyttsx3 TTS provider implementation.

This module provides a concrete implementation of the ITTSProvider interface
using the pyttsx3 library for cross-platform text-to-speech.

Typical usage example:
    from airborne.audio.tts.pyttsx_provider import PyTTSXProvider

    tts = PyTTSXProvider()
    tts.initialize({"rate": 200, "volume": 0.9})
    tts.speak("Welcome to AirBorne")
"""

import threading
from collections import deque
from collections.abc import Callable
from typing import Any

try:
    import pyttsx3  # type: ignore[import-untyped]

    PYTTSX_AVAILABLE = True
except ImportError:
    PYTTSX_AVAILABLE = False

from airborne.audio.tts.base import ITTSProvider, TTSPriority, TTSState
from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


class PyTTSXError(Exception):
    """Raised when pyttsx3 operations fail."""


class SpeechItem:
    """Item in the speech queue."""

    def __init__(
        self,
        text: str,
        priority: TTSPriority,
        callback: Callable[[], None] | None = None,
    ) -> None:
        """Initialize speech item.

        Args:
            text: Text to speak.
            priority: Priority level.
            callback: Optional completion callback.
        """
        self.text = text
        self.priority = priority
        self.callback = callback


class PyTTSXProvider(ITTSProvider):
    """pyttsx3-based TTS provider.

    Cross-platform text-to-speech using pyttsx3, which uses:
    - SAPI5 on Windows
    - NSS on macOS
    - espeak on Linux

    Examples:
        >>> tts = PyTTSXProvider()
        >>> tts.initialize({"rate": 200})
        >>> tts.speak("Engine started")
        >>> tts.shutdown()
    """

    def __init__(self) -> None:
        """Initialize the provider (not started yet)."""
        if not PYTTSX_AVAILABLE:
            raise ImportError("pyttsx3 is not installed. Install it with: uv add pyttsx3")

        self._engine = None
        self._initialized = False
        self._state = TTSState.IDLE
        self._queue: deque[SpeechItem] = deque()
        self._current_item: SpeechItem | None = None
        self._lock = threading.Lock()
        self._speaking_thread: threading.Thread | None = None
        self._stop_requested = False

    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize pyttsx3 engine.

        Args:
            config: Configuration with keys:
                - rate: Speech rate in words per minute (default: 200)
                - volume: Volume 0.0 to 1.0 (default: 1.0)
                - voice: Voice ID (optional, uses default if not specified)

        Raises:
            PyTTSXError: If initialization fails.
        """
        if self._initialized:
            logger.warning("pyttsx3 already initialized")
            return

        try:
            self._engine = pyttsx3.init()

            # Set rate
            rate = config.get("rate", 200)
            self._engine.setProperty("rate", rate)  # type: ignore[attr-defined]

            # Set volume
            volume = config.get("volume", 1.0)
            self._engine.setProperty("volume", volume)  # type: ignore[attr-defined]

            # Set voice if specified
            voice_id = config.get("voice")
            if voice_id:
                self._engine.setProperty("voice", voice_id)  # type: ignore[attr-defined]

            # Register callbacks
            self._engine.connect("started-utterance", self._on_start)  # type: ignore[attr-defined]
            self._engine.connect("finished-utterance", self._on_finish)  # type: ignore[attr-defined]

            self._initialized = True
            logger.info("pyttsx3 TTS initialized: rate=%d, volume=%.2f", rate, volume)

        except Exception as e:
            raise PyTTSXError("Failed to initialize pyttsx3: %s", e) from e

    def shutdown(self) -> None:
        """Shutdown pyttsx3 and release resources."""
        if not self._initialized:
            return

        self.stop()
        self.clear_queue()

        if self._engine:
            try:
                self._engine.stop()
            except Exception as e:
                logger.error("Error stopping pyttsx3 engine: %s", e)

        self._initialized = False
        self._engine = None
        logger.info("pyttsx3 TTS shutdown")

    def speak(
        self,
        text: str,
        priority: TTSPriority = TTSPriority.NORMAL,
        interrupt: bool = False,
        callback: Callable[[], None] | None = None,
    ) -> None:
        """Speak text with priority handling.

        Args:
            text: Text to speak.
            priority: Priority level.
            interrupt: If True, stop current speech.
            callback: Optional callback when done.
        """
        if not self._initialized or not text.strip():
            return

        item = SpeechItem(text, priority, callback)

        with self._lock:
            if interrupt or priority == TTSPriority.CRITICAL:
                # Clear queue and stop current speech
                self._queue.clear()
                self.stop()
                self._queue.append(item)
            elif priority == TTSPriority.HIGH:
                # Insert at front of queue
                self._queue.appendleft(item)
            else:
                # Add to end of queue
                self._queue.append(item)

        logger.debug("Queued speech: '%s' (priority=%s)", text[:50], priority.name)
        self._process_queue()

    def stop(self) -> None:
        """Stop current speech immediately."""
        if not self._initialized or not self._engine:
            return

        with self._lock:
            self._stop_requested = True
            if self._state == TTSState.SPEAKING:
                try:
                    self._engine.stop()
                except Exception as e:
                    logger.error("Error stopping speech: %s", e)
            self._state = TTSState.IDLE
            self._current_item = None

        logger.debug("Stopped speech")

    def pause(self) -> None:
        """Pause current speech.

        Note:
            pyttsx3 doesn't natively support pause/resume, so this stops speech.
        """
        self.stop()
        self._state = TTSState.PAUSED

    def resume(self) -> None:
        """Resume speech.

        Note:
            Since pyttsx3 doesn't support true pause/resume, this processes
            the next item in the queue.
        """
        if self._state == TTSState.PAUSED:
            self._state = TTSState.IDLE
            self._process_queue()

    def is_speaking(self) -> bool:
        """Check if currently speaking.

        Returns:
            True if speaking.
        """
        with self._lock:
            return self._state == TTSState.SPEAKING

    def get_state(self) -> TTSState:
        """Get current TTS state.

        Returns:
            Current state.
        """
        with self._lock:
            return self._state

    def set_rate(self, rate: int) -> None:
        """Set speech rate.

        Args:
            rate: Words per minute.
        """
        if self._engine:
            self._engine.setProperty("rate", rate)
            logger.debug("Set speech rate: %d", rate)

    def set_volume(self, volume: float) -> None:
        """Set speech volume.

        Args:
            volume: Volume 0.0 to 1.0.
        """
        if self._engine:
            volume = max(0.0, min(1.0, volume))
            self._engine.setProperty("volume", volume)
            logger.debug("Set speech volume: %.2f", volume)

    def set_voice(self, voice_id: str) -> None:
        """Set voice by ID.

        Args:
            voice_id: Voice identifier.
        """
        if self._engine:
            self._engine.setProperty("voice", voice_id)
            logger.debug("Set voice: %s", voice_id)

    def get_voices(self) -> list[dict[str, Any]]:
        """Get available voices.

        Returns:
            List of voice dictionaries.
        """
        if not self._engine:
            return []

        voices = self._engine.getProperty("voices")
        result = []

        for voice in voices:
            result.append(
                {
                    "id": voice.id,
                    "name": voice.name,
                    "languages": voice.languages if hasattr(voice, "languages") else [],
                    "gender": voice.gender if hasattr(voice, "gender") else None,
                }
            )

        return result

    def clear_queue(self) -> None:
        """Clear the speech queue."""
        with self._lock:
            self._queue.clear()
        logger.debug("Cleared speech queue")

    def get_queue_length(self) -> int:
        """Get queue length.

        Returns:
            Number of queued items.
        """
        with self._lock:
            return len(self._queue)

    def _process_queue(self) -> None:
        """Process the next item in the queue."""
        if not self._initialized or not self._engine:
            return

        with self._lock:
            # Already speaking or queue empty
            if self._state == TTSState.SPEAKING or not self._queue:
                return

            # Get next item
            self._current_item = self._queue.popleft()
            self._state = TTSState.SPEAKING
            self._stop_requested = False

        # Speak in a separate thread to avoid blocking
        if self._speaking_thread is None or not self._speaking_thread.is_alive():
            self._speaking_thread = threading.Thread(target=self._speak_thread, daemon=True)
            self._speaking_thread.start()

    def _speak_thread(self) -> None:
        """Thread function for speaking."""
        if not self._current_item or not self._engine:
            return

        try:
            logger.debug("Speaking: '%s'", self._current_item.text[:50])
            self._engine.say(self._current_item.text)
            self._engine.runAndWait()

            # Call callback if provided
            if self._current_item.callback and not self._stop_requested:
                try:
                    self._current_item.callback()
                except Exception as e:
                    logger.error("Error in speech callback: %s", e)

        except Exception as e:
            logger.error("Error during speech: %s", e)

        finally:
            with self._lock:
                self._state = TTSState.IDLE
                self._current_item = None

            # Process next item
            if not self._stop_requested:
                self._process_queue()

    def _on_start(self, name: str) -> None:
        """Callback when utterance starts.

        Args:
            name: Utterance name.
        """
        logger.debug("Utterance started: %s", name)

    def _on_finish(self, name: str, completed: bool) -> None:
        """Callback when utterance finishes.

        Args:
            name: Utterance name.
            completed: Whether it completed normally.
        """
        logger.debug("Utterance finished: %s (completed=%s)", name, completed)

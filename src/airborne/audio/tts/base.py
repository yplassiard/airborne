"""Abstract TTS (Text-to-Speech) interface.

This module defines the interface for text-to-speech providers that enable
self-voicing accessibility for the flight simulator.

Typical usage example:
    from airborne.audio.tts.base import ITTSProvider

    class MyTTSProvider(ITTSProvider):
        def initialize(self, config: dict[str, Any]) -> None:
            # Setup TTS engine
            pass
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import Enum, auto
from typing import Any


class TTSState(Enum):
    """TTS engine states."""

    IDLE = auto()
    SPEAKING = auto()
    PAUSED = auto()


class TTSPriority(Enum):
    """Speech priority levels."""

    CRITICAL = 0  # Warnings, alerts (interrupts everything)
    HIGH = 1  # Important info (interrupts normal speech)
    NORMAL = 2  # Regular speech
    LOW = 3  # Background info


class ITTSProvider(ABC):
    """Abstract interface for text-to-speech providers.

    TTS providers convert text to spoken audio for accessibility. They support
    queuing, interruption, rate/volume control, and callbacks.

    Examples:
        >>> tts = PyTTSXProvider()
        >>> tts.initialize({"rate": 200, "volume": 0.9})
        >>> tts.speak("Engine started", priority=TTSPriority.NORMAL)
        >>> tts.speak("WARNING: Low fuel!", priority=TTSPriority.CRITICAL)
        >>> tts.shutdown()
    """

    @abstractmethod
    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize the TTS engine.

        Args:
            config: Configuration dictionary with provider-specific settings.
                Common keys:
                - rate: Speech rate in words per minute (default: 200)
                - volume: Volume level 0.0 to 1.0 (default: 1.0)
                - voice: Voice ID or name (provider-specific)
                - language: Language code (e.g., "en-US")

        Raises:
            RuntimeError: If initialization fails.

        Examples:
            >>> tts.initialize({"rate": 180, "volume": 0.8, "voice": "default"})
        """

    @abstractmethod
    def shutdown(self) -> None:
        """Shutdown the TTS engine.

        Stops any speaking, clears the queue, and releases resources.

        Examples:
            >>> tts.shutdown()
        """

    @abstractmethod
    def speak(
        self,
        text: str,
        priority: TTSPriority = TTSPriority.NORMAL,
        interrupt: bool = False,
        callback: Callable[[], None] | None = None,
    ) -> None:
        """Speak text with given priority.

        Args:
            text: Text to speak.
            priority: Speech priority level.
            interrupt: If True, stop current speech immediately.
            callback: Optional callback when speech finishes.

        Examples:
            >>> tts.speak("Altitude 10000 feet")
            >>> tts.speak("WARNING!", priority=TTSPriority.CRITICAL, interrupt=True)
            >>> tts.speak("Task complete", callback=lambda: print("Done"))
        """

    @abstractmethod
    def stop(self) -> None:
        """Stop current speech immediately.

        Examples:
            >>> tts.stop()
        """

    @abstractmethod
    def pause(self) -> None:
        """Pause current speech.

        Examples:
            >>> tts.pause()
        """

    @abstractmethod
    def resume(self) -> None:
        """Resume paused speech.

        Examples:
            >>> tts.resume()
        """

    @abstractmethod
    def is_speaking(self) -> bool:
        """Check if currently speaking.

        Returns:
            True if speaking, False otherwise.

        Examples:
            >>> if not tts.is_speaking():
            ...     tts.speak("Ready")
        """

    @abstractmethod
    def get_state(self) -> TTSState:
        """Get current TTS state.

        Returns:
            Current TTS state.

        Examples:
            >>> state = tts.get_state()
            >>> if state == TTSState.IDLE:
            ...     print("TTS ready")
        """

    @abstractmethod
    def set_rate(self, rate: int) -> None:
        """Set speech rate.

        Args:
            rate: Speech rate in words per minute (typically 100-300).

        Examples:
            >>> tts.set_rate(220)
        """

    @abstractmethod
    def set_volume(self, volume: float) -> None:
        """Set speech volume.

        Args:
            volume: Volume level from 0.0 (silent) to 1.0 (max).

        Examples:
            >>> tts.set_volume(0.7)
        """

    @abstractmethod
    def set_voice(self, voice_id: str) -> None:
        """Set the voice to use.

        Args:
            voice_id: Voice identifier (provider-specific).

        Examples:
            >>> tts.set_voice("english-us")
        """

    @abstractmethod
    def get_voices(self) -> list[dict[str, Any]]:
        """Get list of available voices.

        Returns:
            List of voice dictionaries with keys like:
                - id: Voice identifier
                - name: Voice name
                - language: Language code
                - gender: Voice gender (if available)

        Examples:
            >>> voices = tts.get_voices()
            >>> for voice in voices:
            ...     print(f"{voice['name']} ({voice['language']})")
        """

    def clear_queue(self) -> None:
        """Clear the speech queue.

        Note:
            Default implementation does nothing. Override if your provider
            supports queuing.

        Examples:
            >>> tts.clear_queue()
        """

    def get_queue_length(self) -> int:
        """Get the number of queued speech items.

        Returns:
            Number of items in queue.

        Note:
            Default implementation returns 0. Override if your provider
            supports queuing.

        Examples:
            >>> length = tts.get_queue_length()
            >>> print(f"{length} items queued")
        """
        return 0

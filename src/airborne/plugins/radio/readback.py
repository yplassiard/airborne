"""ATC readback and hearback system for realistic radio communications.

This module implements pilot readback of ATC instructions with validation
and repeat request functionality, following real-world aviation procedures.

Key features:
- Extracts critical elements from ATC messages (altitude, heading, runway, frequency)
- Generates proper pilot readbacks with correct phraseology
- Validates readback accuracy
- Handles repeat requests ("Say again")
- Tracks message history for readback

Typical usage example:
    readback_system = ATCReadbackSystem(atc_queue, tts_provider)

    # Acknowledge last ATC instruction (Shift+F1)
    readback_system.acknowledge()

    # Request repeat (Ctrl+F1)
    readback_system.request_repeat()
"""

import re
from collections import deque
from dataclasses import dataclass
from typing import Any, Optional

from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


# Critical element patterns for extraction
CRITICAL_ELEMENTS = {
    "altitude": r"(?:maintain|climb|descend).*?(\d+,?\d*)\s*(?:feet|ft)",
    "heading": r"(?:turn|heading)\s*(?:left|right)?\s*(?:heading)?\s*(\d{3})",
    "runway": r"runway\s*(\d{1,2}[LRC]?)",
    "frequency": r"(?:contact|frequency).*?(\d{3}\.\d{1,2})",
    "squawk": r"squawk\s*(\d{4})",
    "speed": r"(?:maintain|reduce|increase)\s*(?:speed)?\s*(\d+)\s*knots?",
}


@dataclass
class ATCInstruction:
    """Represents an ATC instruction with extracted critical elements.

    Attributes:
        message_key: Original message key(s).
        full_text: Full instruction text (if available).
        elements: Dictionary of critical elements (altitude, heading, etc.).
        timestamp: When instruction was received.
    """

    message_key: str | list[str]
    full_text: str = ""
    elements: dict[str, str] = None
    timestamp: float = 0.0

    def __post_init__(self):
        """Initialize elements dict if not provided."""
        if self.elements is None:
            self.elements = {}


class ReadbackValidator:
    """Validates pilot readbacks against original ATC instructions.

    This class extracts critical elements from ATC messages and validates
    that pilot readbacks contain the correct information.
    """

    def extract_critical_elements(self, message: str) -> dict[str, str]:
        """Extract critical elements from ATC message.

        Args:
            message: ATC message text.

        Returns:
            Dictionary of extracted elements (e.g., {"altitude": "3000", "heading": "270"}).
        """
        elements = {}

        for element_type, pattern in CRITICAL_ELEMENTS.items():
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                elements[element_type] = match.group(1)
                logger.debug(f"Extracted {element_type}: {match.group(1)}")

        return elements

    def generate_readback(self, elements: dict[str, str], callsign: str = "") -> str:
        """Generate proper pilot readback from elements.

        Args:
            elements: Dictionary of critical elements.
            callsign: Aircraft callsign (optional).

        Returns:
            Formatted readback string with proper phraseology.
        """
        readback_parts = []

        # Altitude
        if "altitude" in elements:
            alt = elements["altitude"].replace(",", "")
            # Convert to spoken form (e.g., "3000" -> "three thousand")
            readback_parts.append(f"maintain {alt}")

        # Heading
        if "heading" in elements:
            hdg = elements["heading"]
            readback_parts.append(f"heading {hdg}")

        # Runway
        if "runway" in elements:
            rwy = elements["runway"]
            readback_parts.append(f"runway {rwy}")

        # Frequency
        if "frequency" in elements:
            freq = elements["frequency"]
            readback_parts.append(f"contact {freq}")

        # Squawk
        if "squawk" in elements:
            sqwk = elements["squawk"]
            readback_parts.append(f"squawk {sqwk}")

        # Speed
        if "speed" in elements:
            spd = elements["speed"]
            readback_parts.append(f"{spd} knots")

        # Build full readback
        if readback_parts:
            readback = ", ".join(readback_parts)
            if callsign:
                readback += f", {callsign}"
            return readback
        else:
            # No critical elements, generic acknowledgment
            return "Roger" if not callsign else f"Roger, {callsign}"

    def validate_readback(
        self, original_elements: dict[str, str], readback_elements: dict[str, str]
    ) -> tuple[bool, list[str]]:
        """Validate pilot readback against original instruction.

        Args:
            original_elements: Elements extracted from original ATC message.
            readback_elements: Elements extracted from pilot readback.

        Returns:
            Tuple of (is_correct, list_of_errors).
        """
        errors = []

        for key, original_value in original_elements.items():
            readback_value = readback_elements.get(key, "")

            # Normalize values for comparison
            original_norm = original_value.replace(",", "").strip()
            readback_norm = readback_value.replace(",", "").strip()

            if original_norm != readback_norm:
                errors.append(f"Incorrect {key}: expected {original_value}, got {readback_value}")
                logger.warning(
                    f"Readback error: {key} mismatch (expected={original_value}, got={readback_value})"
                )

        is_correct = len(errors) == 0
        return is_correct, errors


class ATCReadbackSystem:
    """Manages ATC readback and repeat request functionality.

    Tracks recent ATC messages and provides functionality for:
    - Acknowledging last instruction with proper readback (Shift+F1)
    - Requesting repeat of last message (Ctrl+F1)
    - Validating readback accuracy

    Examples:
        >>> system = ATCReadbackSystem(queue, tts)
        >>> system.record_atc_instruction("ATC_TOWER_CLEARED_TAKEOFF_31")
        >>> system.acknowledge()  # Generates and sends readback
    """

    def __init__(
        self, atc_queue: Any, tts_provider: Any, callsign: str = "Cessna 123AB"
    ):
        """Initialize readback system.

        Args:
            atc_queue: ATCMessageQueue for enqueueing readback messages.
            tts_provider: TTS provider for speaking messages.
            callsign: Aircraft callsign for readbacks.
        """
        self._atc_queue = atc_queue
        self._tts = tts_provider
        self._callsign = callsign
        self._validator = ReadbackValidator()

        # Track last 3 ATC instructions for readback/repeat
        self._instruction_history: deque[ATCInstruction] = deque(maxlen=3)

        logger.info(f"ATC readback system initialized (callsign: {callsign})")

    def record_atc_instruction(
        self, message_key: str | list[str], full_text: str = ""
    ) -> None:
        """Record an ATC instruction for potential readback.

        Args:
            message_key: Message key(s) from atc_en.yaml.
            full_text: Full text of instruction (if available).
        """
        import time

        # Extract critical elements
        elements = {}
        if full_text:
            elements = self._validator.extract_critical_elements(full_text)

        instruction = ATCInstruction(
            message_key=message_key,
            full_text=full_text,
            elements=elements,
            timestamp=time.time(),
        )

        self._instruction_history.append(instruction)

        logger.debug(
            f"Recorded ATC instruction: {message_key} (elements: {list(elements.keys())})"
        )

    def acknowledge(self) -> bool:
        """Acknowledge last ATC instruction with readback (Shift+F1).

        Generates appropriate readback based on critical elements in the
        last ATC message and enqueues pilot message.

        Returns:
            True if acknowledgment was sent, False if no instruction to acknowledge.
        """
        if not self._instruction_history:
            logger.warning("No ATC instruction to acknowledge")
            if self._tts:
                self._tts.speak("No instruction to acknowledge")
            return False

        # Get last instruction
        last_instruction = self._instruction_history[-1]

        # Generate readback
        readback_text = self._validator.generate_readback(
            last_instruction.elements, self._callsign
        )

        logger.info(f"Acknowledging with readback: {readback_text}")

        # Enqueue pilot readback message
        from airborne.plugins.radio.atc_queue import ATCMessage

        pilot_msg = ATCMessage(
            message_key="PILOT_READBACK",  # Generic readback message
            sender="PILOT",
            priority=0,
            delay_after=2.0,
        )
        self._atc_queue.enqueue(pilot_msg)

        # Enqueue ATC response ("Readback correct" or corrections)
        # For now, assume correct (in full implementation, would validate)
        atc_response = ATCMessage(
            message_key="ATC_READBACK_CORRECT",
            sender="ATC",
            priority=0,
            delay_after=0.0,
        )
        self._atc_queue.enqueue(atc_response)

        return True

    def request_repeat(self) -> bool:
        """Request repeat of last ATC message (Ctrl+F1).

        Sends "Say again" request and enqueues ATC to repeat last instruction.

        Returns:
            True if repeat was requested, False if no instruction to repeat.
        """
        if not self._instruction_history:
            logger.warning("No ATC instruction to repeat")
            if self._tts:
                self._tts.speak("No instruction to repeat")
            return False

        # Get last instruction
        last_instruction = self._instruction_history[-1]

        logger.info(f"Requesting repeat of: {last_instruction.message_key}")

        # Enqueue pilot "say again" message
        from airborne.plugins.radio.atc_queue import ATCMessage

        pilot_msg = ATCMessage(
            message_key="PILOT_SAY_AGAIN",
            sender="PILOT",
            priority=0,
            delay_after=2.0,
        )
        self._atc_queue.enqueue(pilot_msg)

        # Enqueue ATC repeat
        atc_repeat = ATCMessage(
            message_key=last_instruction.message_key,
            sender="ATC",
            priority=0,
            delay_after=0.0,
        )
        self._atc_queue.enqueue(atc_repeat)

        return True

    def get_last_atc_message(self) -> Optional[ATCInstruction]:
        """Get last ATC instruction.

        Returns:
            Last ATCInstruction or None if no history.
        """
        if self._instruction_history:
            return self._instruction_history[-1]
        return None

    def get_instruction_history(self) -> list[ATCInstruction]:
        """Get instruction history (up to last 3 messages).

        Returns:
            List of ATCInstruction objects.
        """
        return list(self._instruction_history)

    def clear_history(self) -> None:
        """Clear instruction history."""
        self._instruction_history.clear()
        logger.debug("Cleared instruction history")

    def set_callsign(self, callsign: str) -> None:
        """Update aircraft callsign.

        Args:
            callsign: New callsign for readbacks.
        """
        self._callsign = callsign
        logger.info(f"Updated callsign to: {callsign}")

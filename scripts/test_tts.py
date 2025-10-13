#!/usr/bin/env python3
"""Test TTS audio feedback functionality."""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from airborne.audio.tts.base import TTSPriority
from airborne.audio.tts.pyttsx_provider import PYTTSX_AVAILABLE, PyTTSXProvider
from airborne.core.logging_system import get_logger, initialize_logging

logger = get_logger(__name__)


def wait_for_speech(tts: PyTTSXProvider, extra_delay: float = 0.5) -> None:
    """Wait for TTS to finish speaking.

    Args:
        tts: TTS provider instance.
        extra_delay: Extra delay after speech completes (seconds).
    """
    while tts.is_speaking():
        time.sleep(0.1)
    time.sleep(extra_delay)


def test_basic_speech(tts: PyTTSXProvider) -> None:
    """Test basic speech output.

    Args:
        tts: TTS provider instance.
    """
    print("\n=== TEST 1: Basic Speech ===")
    logger.info("Testing basic speech output")

    tts.speak("Welcome to AirBorne flight simulator. This is a test of basic speech.")
    wait_for_speech(tts, 1.0)

    print("✓ Basic speech test complete")


def test_speech_rate(tts: PyTTSXProvider) -> None:
    """Test speech rate changes.

    Args:
        tts: TTS provider instance.
    """
    print("\n=== TEST 2: Speech Rate ===")
    logger.info("Testing speech rate changes")

    rates = [
        (120, "very slow"),
        (150, "slow"),
        (200, "normal"),
        (250, "fast"),
        (300, "very fast"),
    ]

    for rate, description in rates:
        print(f"  Testing rate {rate} WPM ({description})...")
        tts.set_rate(rate)
        tts.speak(f"This is {description} speech at {rate} words per minute.")
        wait_for_speech(tts, 0.8)

    # Reset to normal
    tts.set_rate(180)
    print("✓ Speech rate test complete")


def test_volume(tts: PyTTSXProvider) -> None:
    """Test volume changes.

    Args:
        tts: TTS provider instance.
    """
    print("\n=== TEST 3: Volume Levels ===")
    logger.info("Testing volume changes")

    volumes = [
        (0.3, "quiet"),
        (0.6, "medium"),
        (0.9, "loud"),
        (1.0, "maximum"),
    ]

    for volume, description in volumes:
        print(f"  Testing volume {volume:.1f} ({description})...")
        tts.set_volume(volume)
        tts.speak(f"This is {description} volume at {volume:.1f}.")
        wait_for_speech(tts, 0.8)

    # Reset to normal
    tts.set_volume(0.9)
    print("✓ Volume test complete")


def test_voices(tts: PyTTSXProvider) -> None:
    """Test available voices.

    Args:
        tts: TTS provider instance.
    """
    print("\n=== TEST 4: Available Voices ===")
    logger.info("Testing voice changes")

    voices = tts.get_voices()
    print(f"  Found {len(voices)} available voices:")

    for i, voice in enumerate(voices[:5]):  # Test first 5 voices
        print(f"    {i + 1}. {voice['name']}")
        logger.info("Voice: %s (ID: %s)", voice["name"], voice["id"])

    if len(voices) > 0:
        print("\n  Testing first 3 voices:")
        for i, voice in enumerate(voices[:3]):
            print(f"    Switching to: {voice['name']}")
            tts.set_voice(voice["id"])
            tts.speak(f"This is voice {i + 1}, {voice['name']}.")
            wait_for_speech(tts, 0.8)

        # Reset to default (first voice)
        tts.set_voice(voices[0]["id"])
        print("✓ Voice test complete")
    else:
        print("⚠ No voices available to test")


def test_priority_queuing(tts: PyTTSXProvider) -> None:
    """Test priority-based speech queuing.

    Args:
        tts: TTS provider instance.
    """
    print("\n=== TEST 5: Priority Queuing ===")
    logger.info("Testing priority queuing")

    print("  Queueing multiple phrases with different priorities...")

    # Queue several items
    tts.speak("This is a normal priority message.", priority=TTSPriority.NORMAL)
    tts.speak("This is another normal message.", priority=TTSPriority.NORMAL)
    tts.speak("This is a high priority message!", priority=TTSPriority.HIGH)
    tts.speak("This is a low priority message.", priority=TTSPriority.LOW)

    print(f"  Queue length: {tts.get_queue_length()}")

    # Wait for all to complete
    wait_for_speech(tts, 3.0)
    print("✓ Priority queuing test complete")


def test_interrupt(tts: PyTTSXProvider) -> None:
    """Test speech interruption.

    Args:
        tts: TTS provider instance.
    """
    print("\n=== TEST 6: Speech Interruption ===")
    logger.info("Testing speech interruption")

    print("  Starting long speech...")
    tts.speak("This is a very long message that should be interrupted before it finishes.")

    # Wait a moment then interrupt
    time.sleep(1.0)
    print("  Interrupting with critical message...")
    tts.speak("CRITICAL: Emergency message!", priority=TTSPriority.CRITICAL, interrupt=True)

    wait_for_speech(tts, 1.0)
    print("✓ Interruption test complete")


def test_aviation_phrases(tts: PyTTSXProvider) -> None:
    """Test aviation-specific phrases.

    Args:
        tts: TTS provider instance.
    """
    print("\n=== TEST 7: Aviation Phrases ===")
    logger.info("Testing aviation phrases")

    aviation_phrases = [
        "Airspeed one hundred twenty knots",
        "Altitude three thousand five hundred feet",
        "Vertical speed, positive five hundred feet per minute",
        "Cleared for takeoff, runway two seven",
        "Wind two seven zero at one five knots",
        "Traffic alert, two o'clock, three miles",
    ]

    for phrase in aviation_phrases:
        print(f"  Speaking: {phrase}")
        tts.speak(phrase)
        wait_for_speech(tts, 0.5)

    print("✓ Aviation phrases test complete")


def main() -> int:
    """Test TTS functionality."""
    # Initialize logging
    initialize_logging("config/logging.yaml")

    print("\n" + "=" * 60)
    print("  AirBorne TTS Audio Test Suite")
    print("=" * 60)

    # Check if pyttsx3 is available
    if not PYTTSX_AVAILABLE:
        print("\n❌ ERROR: pyttsx3 is not installed!")
        print("   Install with: uv add pyttsx3")
        logger.error("pyttsx3 is not installed!")
        return 1

    print("\n✓ pyttsx3 library is available")

    try:
        # Initialize TTS
        print("\nInitializing TTS engine...")
        tts = PyTTSXProvider()
        tts.initialize({"rate": 180, "volume": 0.9})
        print("✓ TTS initialized successfully")

        # Run all tests
        test_basic_speech(tts)
        test_speech_rate(tts)
        test_volume(tts)
        test_voices(tts)
        test_priority_queuing(tts)
        test_interrupt(tts)
        test_aviation_phrases(tts)

        # Final message
        print("\n=== All Tests Complete ===")
        tts.speak("All TTS tests completed successfully. AirBorne audio system ready.")
        wait_for_speech(tts, 1.0)

        # Shutdown
        tts.shutdown()
        print("\n✓ TTS shutdown successfully")

        print("\n" + "=" * 60)
        print("  ✓ ALL TESTS PASSED")
        print("=" * 60 + "\n")

        logger.info("=== TTS Test Suite PASSED ===")
        return 0

    except Exception as e:
        print(f"\n❌ ERROR: TTS test failed: {e}")
        logger.error("TTS test failed: %s", e, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

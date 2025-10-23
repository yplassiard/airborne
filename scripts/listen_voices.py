#!/usr/bin/env python3
"""
Kokoro TTS Voice Listener

Quick interactive script to listen to all 19 English voices.
Press Enter to hear the next voice, or Ctrl+C to quit.
"""

import subprocess
import tempfile
from pathlib import Path

import soundfile as sf
from kokoro_onnx import Kokoro

# All available English voices
VOICES = {
    "Female Voices": [
        ("af_alloy", "Neutral, versatile"),
        ("af_aoede", "Warm, friendly"),
        ("af_bella", "Clear, professional ⭐"),
        ("af_heart", "Emotional, expressive"),
        ("af_jessica", "Confident, authoritative"),
        ("af_kore", "Calm, reassuring"),
        ("af_nicole", "Bright, energetic"),
        ("af_nova", "Modern, crisp"),
        ("af_river", "Smooth, flowing"),
        ("af_sarah", "Professional, clear ⭐"),
        ("af_sky", "Airy, light"),
    ],
    "Male Voices": [
        ("am_adam", "Professional, clear ⭐"),
        ("am_echo", "Deep, resonant"),
        ("am_eric", "Friendly, approachable"),
        ("am_fenrir", "Strong, authoritative"),
        ("am_liam", "Smooth, conversational"),
        ("am_michael", "Warm, trustworthy ⭐"),
        ("am_onyx", "Rich, deep"),
        ("am_puck", "Playful, energetic"),
    ],
}

# Sample text
SAMPLE_TEXT = (
    "Palo Alto Tower, Cessna one two three alpha bravo, ready for departure runway three one."
)


def play_voice(kokoro: Kokoro, voice: str, description: str, temp_dir: Path):
    """Generate and play a voice sample."""
    print(f"\n  🔊 Playing: {voice:12} - {description}")

    # Generate audio
    samples, sample_rate = kokoro.create(SAMPLE_TEXT, voice=voice, lang="en-us")

    # Save to temp file
    temp_file = temp_dir / f"{voice}.wav"
    sf.write(str(temp_file), samples, sample_rate)

    # Play with afplay
    subprocess.run(["afplay", str(temp_file)], check=True)


def main():
    """Main entry point."""
    print("\n" + "=" * 60)
    print("Kokoro TTS Voice Listener")
    print("=" * 60)
    print(f'\nSample: "{SAMPLE_TEXT}"')
    print("\nPress Enter to hear each voice (Ctrl+C to quit)\n")

    # Initialize Kokoro
    print("Initializing Kokoro...")
    kokoro = Kokoro(
        model_path="assets/models/kokoro-v1.0.onnx", voices_path="assets/models/voices-v1.0.bin"
    )
    print("✓ Ready!\n")

    # Create temp directory for audio files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        try:
            # Play female voices
            print("\n" + "─" * 60)
            print("FEMALE VOICES (11)")
            print("─" * 60)

            for voice, description in VOICES["Female Voices"]:
                input()  # Wait for Enter
                play_voice(kokoro, voice, description, temp_path)

            # Play male voices
            print("\n" + "─" * 60)
            print("MALE VOICES (8)")
            print("─" * 60)

            for voice, description in VOICES["Male Voices"]:
                input()  # Wait for Enter
                play_voice(kokoro, voice, description, temp_path)

            print("\n" + "=" * 60)
            print("✓ All voices played!")
            print("=" * 60 + "\n")

        except KeyboardInterrupt:
            print("\n\n✓ Stopped by user\n")
            return 0
        except Exception as e:
            print(f"\n✗ Error: {e}")
            import traceback

            traceback.print_exc()
            return 1

    return 0


if __name__ == "__main__":
    exit(main())

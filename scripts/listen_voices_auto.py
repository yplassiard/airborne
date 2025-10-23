#!/usr/bin/env python3
"""
Kokoro TTS Voice Listener (Auto-play)

Automatically plays all 19 voices with a 1-second pause between each.
Press Ctrl+C to stop at any time.
"""

import subprocess
import tempfile
import time
from pathlib import Path

import soundfile as sf
from kokoro_onnx import Kokoro

# All available English voices
VOICES = [
    # Female
    ("af_alloy", "Female - Neutral, versatile"),
    ("af_aoede", "Female - Warm, friendly"),
    ("af_bella", "Female - Clear, professional ⭐"),
    ("af_heart", "Female - Emotional, expressive"),
    ("af_jessica", "Female - Confident, authoritative"),
    ("af_kore", "Female - Calm, reassuring"),
    ("af_nicole", "Female - Bright, energetic"),
    ("af_nova", "Female - Modern, crisp"),
    ("af_river", "Female - Smooth, flowing"),
    ("af_sarah", "Female - Professional, clear ⭐"),
    ("af_sky", "Female - Airy, light"),
    # Male
    ("am_adam", "Male - Professional, clear ⭐"),
    ("am_echo", "Male - Deep, resonant"),
    ("am_eric", "Male - Friendly, approachable"),
    ("am_fenrir", "Male - Strong, authoritative"),
    ("am_liam", "Male - Smooth, conversational"),
    ("am_michael", "Male - Warm, trustworthy ⭐"),
    ("am_onyx", "Male - Rich, deep"),
    ("am_puck", "Male - Playful, energetic"),
]

SAMPLE_TEXT = (
    "Palo Alto Tower, Cessna one two three alpha bravo, ready for departure runway three one."
)


def main():
    """Main entry point."""
    print("\n" + "=" * 70)
    print("Kokoro TTS Voice Listener (Auto-play)")
    print("=" * 70)
    print(f'\nSample: "{SAMPLE_TEXT}"')
    print(f"\nPlaying all {len(VOICES)} voices automatically...")
    print("Press Ctrl+C to stop\n")

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
            for i, (voice, description) in enumerate(VOICES, 1):
                print(f"[{i}/{len(VOICES)}] 🔊 {voice:12} - {description}")

                # Generate audio
                samples, sample_rate = kokoro.create(SAMPLE_TEXT, voice=voice, lang="en-us")

                # Save to temp file
                temp_file = temp_path / f"{voice}.wav"
                sf.write(str(temp_file), samples, sample_rate)

                # Play with afplay
                subprocess.run(["afplay", str(temp_file)], check=True)

                # Brief pause before next voice
                if i < len(VOICES):
                    time.sleep(1)

            print("\n" + "=" * 70)
            print(f"✓ All {len(VOICES)} voices played!")
            print("=" * 70 + "\n")

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

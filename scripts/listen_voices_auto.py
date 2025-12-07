#!/usr/bin/env python3
"""
Kokoro TTS Voice Listener (Auto-play)

Automatically plays all 19 voices with a 1-second pause between each.
Press Ctrl+C to stop at any time.
"""

import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import soundfile as sf
from kokoro_onnx import Kokoro

# Auto-detect project root (handles running from scripts/ or project root)
SCRIPT_DIR = Path(__file__).resolve().parent
if SCRIPT_DIR.name == "scripts":
    PROJECT_ROOT = SCRIPT_DIR.parent
else:
    PROJECT_ROOT = SCRIPT_DIR

# Change to project root so relative paths work
os.chdir(PROJECT_ROOT)

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


def play_audio(audio_file):
    """Play audio file using platform-appropriate player.
    
    Args:
        audio_file: Path to audio file to play
    """
    system = platform.system()
    
    if system == "Darwin":  # macOS
        subprocess.run(["afplay", str(audio_file)], check=True)
    elif system == "Windows":
        # Use Windows Media Player command line
        subprocess.run(["powershell", "-c", f"(New-Object Media.SoundPlayer '{audio_file}').PlaySync()"], check=True)
    else:  # Linux
        # Try common Linux audio players
        players = ["aplay", "paplay", "ffplay"]
        for player in players:
            try:
                subprocess.run([player, str(audio_file)], check=True, stderr=subprocess.DEVNULL)
                break
            except FileNotFoundError:
                continue
        else:
            print(f"Warning: No audio player found. Install aplay, paplay, or ffplay")


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

                # Play with platform-appropriate player
                play_audio(temp_file)

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

#!/usr/bin/env python3
"""
Kokoro TTS Installation Test

Quick test to verify Kokoro ONNX is installed and working correctly.
Works on Windows, macOS, and Linux.
"""

import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Auto-detect project root (handles running from scripts/ or project root)
SCRIPT_DIR = Path(__file__).resolve().parent
if SCRIPT_DIR.name == "scripts":
    PROJECT_ROOT = SCRIPT_DIR.parent
else:
    PROJECT_ROOT = SCRIPT_DIR

# Change to project root so relative paths work
os.chdir(PROJECT_ROOT)
print(f"Working directory: {PROJECT_ROOT}\n")


def play_audio(audio_file):
    """Play audio file using platform-appropriate player.
    
    Args:
        audio_file: Path to audio file to play
    """
    system = platform.system()
    
    try:
        if system == "Darwin":  # macOS
            subprocess.run(["afplay", str(audio_file)], check=True)
        elif system == "Windows":
            # Use Windows Media Player via PowerShell
            subprocess.run(
                ["powershell", "-c", f"(New-Object Media.SoundPlayer '{audio_file}').PlaySync()"],
                check=True
            )
        else:  # Linux
            # Try common Linux audio players
            players = ["aplay", "paplay", "ffplay"]
            for player in players:
                try:
                    subprocess.run([player, str(audio_file)], check=True, stderr=subprocess.DEVNULL)
                    return
                except FileNotFoundError:
                    continue
            print(f"Warning: No audio player found. Audio saved to: {audio_file}")
    except Exception as e:
        print(f"Warning: Could not play audio: {e}")
        print(f"Audio file saved to: {audio_file}")


def main():
    """Test Kokoro installation."""
    print("Testing Kokoro ONNX TTS installation...")
    print("=" * 50)

    # Import Kokoro
    start_time = time.time()
    try:
        from kokoro_onnx import Kokoro
        import soundfile as sf
    except ImportError as e:
        print(f"[ERROR] Import failed: {e}")
        print("\nPlease install:")
        print("  pip install kokoro-onnx soundfile")
        return 1

    # Initialize Kokoro
    try:
        kokoro = Kokoro(
            model_path="assets/models/kokoro-v1.0.onnx",
            voices_path="assets/models/voices-v1.0.bin"
        )
        init_time = time.time() - start_time
        print(f"[OK] Initialized in {init_time:.2f}s")
    except Exception as e:
        print(f"[ERROR] Initialization failed: {e}")
        print("\nMake sure model files exist:")
        print("  assets/models/kokoro-v1.0.onnx")
        print("  assets/models/voices-v1.0.bin")
        return 1

    # Generate test audio
    test_text = "Testing Kokoro text to speech. Installation successful!"
    print(f"\nGenerating: '{test_text}'")
    
    gen_start = time.time()
    try:
        samples, sample_rate = kokoro.create(
            text=test_text,
            voice="af_bella",
            lang="en-us"
        )
        gen_time = time.time() - gen_start
        audio_duration = len(samples) / sample_rate
        speed_factor = audio_duration / gen_time if gen_time > 0 else 0
        
        print(f"[OK] Generated in {gen_time:.2f}s ({audio_duration:.2f}s audio, {speed_factor:.1f}x realtime)")
    except Exception as e:
        print(f"[ERROR] Generation failed: {e}")
        return 1

    # Save audio file
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = Path(f.name)
        
        sf.write(str(temp_path), samples, sample_rate)
        print(f"[OK] Saved to: {temp_path}")
    except Exception as e:
        print(f"[ERROR] Save failed: {e}")
        return 1

    # Play audio
    print(f"\nPlaying audio...")
    play_audio(temp_path)

    print("\n" + "=" * 50)
    print("[OK] Installation verified!")
    print("\nKokoro TTS is ready to use.")
    print("Available voices: af_bella, af_sarah, am_adam, am_michael, and 15 more")
    
    return 0


if __name__ == "__main__":
    exit(main())

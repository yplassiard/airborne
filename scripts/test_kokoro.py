#!/usr/bin/env python3
"""
Quick test script for Kokoro TTS installation.
Generates a short audio sample to verify everything works.
"""

import sys
import time
import soundfile as sf
from pathlib import Path


def test_kokoro():
    """Test Kokoro ONNX TTS installation."""
    print("Testing Kokoro ONNX TTS installation...")

    try:
        from kokoro_onnx import Kokoro
    except ImportError as e:
        print(f"✗ Failed to import Kokoro ONNX: {e}")
        return False

    try:
        # Initialize Kokoro with ONNX models
        print("Initializing Kokoro with ONNX models...")
        start = time.time()
        kokoro = Kokoro(
            model_path="assets/models/kokoro-v1.0.onnx",
            voices_path="assets/models/voices-v1.0.bin"
        )
        init_time = time.time() - start
        print(f"✓ Initialized in {init_time:.2f}s")

        # Test voice generation
        print("Generating test audio with af_bella voice...")
        text = "Kokoro TTS installation successful. All systems nominal."
        start = time.time()
        samples, sample_rate = kokoro.create(text, voice='af_bella', lang='en-us')
        gen_time = time.time() - start
        audio_duration = len(samples) / sample_rate

        print(f"✓ Generated in {gen_time:.2f}s ({audio_duration:.2f}s audio, {audio_duration/gen_time:.1f}x realtime)")
        print(f"✓ Sample rate: {sample_rate} Hz")

        # Save to file
        output_file = Path('/tmp/kokoro_test.wav')
        sf.write(str(output_file), samples, sample_rate)
        print(f"✓ Saved to: {output_file}")
        print("✓ Installation verified!")
        print(f"\nPlay with: afplay {output_file}")
        return True

    except Exception as e:
        print(f"✗ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = test_kokoro()
    sys.exit(0 if success else 1)

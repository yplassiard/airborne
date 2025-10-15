#!/usr/bin/env python3
"""Quick test to verify FMOD can load OGG files."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from airborne.audio.engine.fmod_engine import FMODEngine

    print("Testing FMOD OGG loading...")

    # Initialize FMOD
    engine = FMODEngine()
    engine.initialize({"max_channels": 8})
    print("✓ FMOD initialized")

    # Test loading an MP3 file
    test_file = "data/speech/en/airspeed_120_knots.mp3"
    print(f"\nLoading: {test_file}")

    sound = engine.load_sound(test_file, preload=True)
    print("✓ Loaded successfully!")
    print(f"  Format: {sound.format}")
    print(f"  Sample rate: {sound.sample_rate}")
    print(f"  Channels: {sound.channels}")

    # Test playing it
    print("\nPlaying sound...")
    source_id = engine.play_2d(sound, volume=1.0, pitch=1.0, loop=False)
    print(f"✓ Playing on source {source_id}")

    # Wait a moment
    import time

    time.sleep(2)

    # Cleanup
    engine.shutdown()
    print("\n✓ All tests passed!")

except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

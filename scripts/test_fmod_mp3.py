#!/usr/bin/env python3
"""Test FMOD's ability to play MP3 files."""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from airborne.audio.engine.fmod_engine import FMODEngine

    print("Testing FMOD MP3 playback...")

    # Initialize FMOD
    engine = FMODEngine()
    engine.initialize({"max_channels": 8})
    print("✓ FMOD initialized")

    # Test loading the MP3 file
    test_file = "./assets/sounds/aircraft/batteryon1.mp3"
    print(f"\nLoading: {test_file}")

    sound = engine.load_sound(test_file, preload=True)
    print("✓ Loaded successfully!")
    print(f"  Format: {sound.format}")
    print(f"  Sample rate: {sound.sample_rate}")
    print(f"  Channels: {sound.channels}")
    print(f"  FMOD handle: {sound.handle}")

    # Test playing it
    print("\nPlaying sound...")
    source_id = engine.play_2d(sound, volume=1.0, pitch=1.0, loop=False)
    print(f"✓ Playing on source {source_id}")

    # Update FMOD and wait for playback
    print("\nPlayback in progress...")
    for i in range(20):  # 2 seconds (20 * 0.1s)
        engine.update()
        time.sleep(0.1)

        # Check if still playing
        state = engine.get_source_state(source_id)
        if i % 5 == 0:
            print(f"  State at {i * 0.1:.1f}s: {state}")

    # Cleanup
    print("\nCleaning up...")
    engine.shutdown()
    print("✓ Test completed!")

except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

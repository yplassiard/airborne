#!/usr/bin/env python3
"""Test battery sound sequence: batteryon -> batteryloop."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from airborne.audio.engine.fmod_engine import FMODEngine

    print("Testing battery sound sequence...")

    # Initialize FMOD
    engine = FMODEngine()
    engine.initialize({"max_channels": 8})
    print("✓ FMOD initialized\n")

    # Load both sounds
    batteryon = engine.load_sound("assets/sounds/aircraft/batteryon1.mp3", preload=True)
    batteryloop = engine.load_sound(
        "assets/sounds/aircraft/batteryloop1.mp3", preload=True, loop_mode=True
    )
    print(f"✓ Loaded batteryon1.mp3 (duration ~{batteryon.duration:.2f}s)")
    print("✓ Loaded batteryloop1.mp3 (loop mode)\n")

    # Play batteryon (one-shot)
    print("Playing batteryon1.mp3...")
    source_on = engine.play_2d(batteryon, volume=1.0, pitch=1.0, loop=False)

    # Monitor until it stops
    print("Waiting for batteryon to finish...")
    start_time = time.time()
    while True:
        engine.update()
        time.sleep(0.05)

        state = engine.get_source_state(source_on)
        elapsed = time.time() - start_time

        if state.name == "STOPPED":
            print(f"✓ batteryon1.mp3 finished after {elapsed:.2f}s\n")
            break

        if elapsed > 5.0:  # Safety timeout
            print("⚠ Timeout waiting for sound to finish\n")
            break

    # Now start the battery loop
    print("Starting batteryloop1.mp3 (looping)...")
    source_loop = engine.play_2d(batteryloop, volume=0.8, pitch=1.0, loop=True)
    print("✓ Battery loop playing")
    print("\n🔋 MASTER SWITCH NOW ON - Battery can discharge\n")

    # Let it loop for a bit
    print("Looping for 3 seconds...")
    for i in range(30):
        engine.update()
        time.sleep(0.1)
        if i % 10 == 0:
            state = engine.get_source_state(source_loop)
            print(f"  Loop state at {i * 0.1:.1f}s: {state}")

    # Stop loop
    print("\nStopping battery loop...")
    engine.stop_source(source_loop)

    # Cleanup
    engine.shutdown()
    print("✓ Test completed successfully!")

except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

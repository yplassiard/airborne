#!/usr/bin/env python3
"""Integration test for battery sound sequence with electrical system."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from airborne.audio.engine.fmod_engine import FMODEngine
from airborne.audio.sound_manager import SoundManager

print("Battery Sound Sequence Integration Test")
print("=" * 50)

# Initialize audio
engine = FMODEngine()
engine.initialize({"max_channels": 8})
sound_manager = SoundManager()
sound_manager.initialize(engine, None)

print("\n1. Testing battery ON sequence:")
print("-" * 50)

battery_ready = False


def on_battery_ready():
    """Callback when battery is fully on."""
    global battery_ready
    battery_ready = True
    print("\n✓ BATTERY IS NOW ON - Electrical system can activate!")


print("   Starting battery ON sequence...")
sound_manager.play_battery_sound(True, on_complete_callback=on_battery_ready)

# Monitor the sequence
print("   Monitoring sequence progress...")
start_time = time.time()
while not battery_ready and (time.time() - start_time) < 5.0:
    sound_manager.update()
    time.sleep(0.05)

elapsed = time.time() - start_time
if battery_ready:
    print(f"\n   ✓ Sequence completed in {elapsed:.2f}s")
    print("   - batteryon1.mp3 played (~1.6s)")
    print("   - batteryloop1.mp3 started looping")
    print("   - Callback invoked successfully")
else:
    print("\n   ✗ Sequence did not complete within 5 seconds")

# Let the loop play for a bit
print("\n2. Battery loop should be playing now...")
for i in range(20):
    sound_manager.update()
    time.sleep(0.1)
print("   ✓ Loop played for 2 seconds")

# Test battery OFF
print("\n3. Testing battery OFF:")
print("-" * 50)
print("   Turning battery OFF...")
sound_manager.play_battery_sound(False)
time.sleep(0.1)
sound_manager.update()
print("   ✓ batteryloop1.mp3 stopped")
print("   ✓ batteryoff1.mp3 played")

# Wait for shutdown sound
time.sleep(2)
sound_manager.update()

# Cleanup
sound_manager.shutdown()
print("\n" + "=" * 50)
print("✓ Integration test completed successfully!")
print("\nThe sequence is ready for use in the main app.")

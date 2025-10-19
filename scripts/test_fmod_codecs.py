#!/usr/bin/env python3
"""Test FMOD codec support."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    import pyfmodex

    print("FMOD Version Information:")
    print(f"  pyfmodex version: {pyfmodex.__version__}")

    # Initialize FMOD
    system = pyfmodex.System()
    system.init()

    print("\nFMOD initialized successfully")

    # Test loading different formats
    test_files = [
        ("WAV", "assets/sounds/aircraft/ef3_engine.wav"),
        ("MP3 - batteryon1", "assets/sounds/aircraft/batteryon1.mp3"),
        ("MP3 - batteryoff1", "assets/sounds/aircraft/batteryoff1.mp3"),
        ("MP3 - batteryloop1", "assets/sounds/aircraft/batteryloop1.mp3"),
    ]

    print("\nTesting codec support:")
    for format_name, filepath in test_files:
        if not Path(filepath).exists():
            print(f"  ✗ {format_name}: File not found - {filepath}")
            continue

        try:
            sound = system.create_sound(filepath, mode=pyfmodex.flags.MODE.DEFAULT)

            # Try to get some info
            try:
                sound_type = sound.sound_type
                print(f"  ✓ {format_name}: Loaded successfully (type: {sound_type})")
            except:
                print(f"  ✓ {format_name}: Loaded successfully")

            sound.release()
        except Exception as e:
            print(f"  ✗ {format_name}: Failed - {e}")

    system.release()
    print("\n✓ Test completed!")

except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

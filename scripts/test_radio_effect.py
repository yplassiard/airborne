#!/usr/bin/env python3
"""Test script to play ATC message with radio effect.

This script plays an ATC message with and without radio effect so you can
compare and evaluate the effect quality.

Usage:
    python scripts/test_radio_effect.py
    python scripts/test_radio_effect.py --message ATC_TOWER_CLEARED_TAKEOFF_31
    python scripts/test_radio_effect.py --no-effect  # Play without effect
"""

import argparse
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    import pyfmodex  # type: ignore[import-untyped]

    FMOD_AVAILABLE = True
except ImportError:
    FMOD_AVAILABLE = False
    print("Error: pyfmodex not installed. Install with: uv add pyfmodex")
    sys.exit(1)

# Import directly to avoid module init issues
import importlib.util

# Load FMODEngine directly
fmod_spec = importlib.util.spec_from_file_location(
    "fmod_engine", Path(__file__).parent.parent / "src/airborne/audio/engine/fmod_engine.py"
)
fmod_module = importlib.util.module_from_spec(fmod_spec)
fmod_spec.loader.exec_module(fmod_module)
FMODEngine = fmod_module.FMODEngine

# Load ATCAudioManager directly
atc_spec = importlib.util.spec_from_file_location(
    "atc_audio", Path(__file__).parent.parent / "src/airborne/audio/atc/atc_audio.py"
)
atc_module = importlib.util.module_from_spec(atc_spec)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
atc_spec.loader.exec_module(atc_module)
ATCAudioManager = atc_module.ATCAudioManager


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Test ATC radio effect by playing sample messages")
    parser.add_argument(
        "--message",
        type=str,
        default="ATC_TOWER_CLEARED_TAKEOFF_31",
        help="ATC message key to play (default: ATC_TOWER_CLEARED_TAKEOFF_31)",
    )
    parser.add_argument(
        "--no-effect",
        action="store_true",
        help="Play without radio effect for comparison",
    )
    parser.add_argument(
        "--list-messages",
        action="store_true",
        help="List available ATC messages and exit",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Play message twice: first without effect, then with effect",
    )

    args = parser.parse_args()

    # Initialize FMOD engine
    print("Initializing FMOD audio engine...")
    try:
        engine = FMODEngine()
        engine.initialize({"max_channels": 32})
        print("✓ FMOD engine initialized\n")
    except Exception as e:
        print(f"Error initializing FMOD: {e}")
        sys.exit(1)

    # Initialize ATC audio manager
    config_dir = Path("config")
    speech_dir = Path("data/atc/en")

    if not speech_dir.exists():
        print(f"Error: ATC speech directory not found: {speech_dir}")
        print("Run: python scripts/generate_atc_speech.py")
        sys.exit(1)

    print("Initializing ATC audio manager...")
    try:
        atc_audio = ATCAudioManager(engine, config_dir, speech_dir)
        print("✓ ATC audio manager initialized\n")
    except Exception as e:
        print(f"Error initializing ATC audio: {e}")
        sys.exit(1)

    # List messages if requested
    if args.list_messages:
        messages = atc_audio.get_available_messages()
        print(f"Available ATC messages ({len(messages)}):\n")
        for msg in sorted(messages):
            print(f"  {msg}")
        engine.shutdown()
        return

    # Check if message exists
    message_key = args.message
    if message_key not in atc_audio.get_available_messages():
        print(f"Error: Message key not found: {message_key}")
        print("\nAvailable messages:")
        for msg in sorted(atc_audio.get_available_messages())[:10]:
            print(f"  {msg}")
        print(f"  ... and {len(atc_audio.get_available_messages()) - 10} more")
        print("\nUse --list-messages to see all available messages")
        engine.shutdown()
        sys.exit(1)

    # Play message
    if args.compare:
        # Play without effect first
        print(f"Playing WITHOUT radio effect: {message_key}")
        print("(Listen to the clean, unprocessed audio...)\n")
        atc_audio.set_radio_effect_enabled(False)
        source_id = atc_audio.play_atc_message(message_key, volume=1.0)

        if source_id:
            # Wait for message to finish
            while engine.get_source_state(source_id).name == "PLAYING":
                engine.update()
                time.sleep(0.016)  # ~60 FPS

            print("✓ Finished playing without effect\n")
            time.sleep(1.0)  # Pause between messages

        # Play with effect
        print(f"Playing WITH radio effect: {message_key}")
        print("(Listen for bandwidth limiting, compression, and radio characteristics...)\n")
        atc_audio.set_radio_effect_enabled(True)
        source_id = atc_audio.play_atc_message(message_key, volume=1.0)

        if source_id:
            # Wait for message to finish
            while engine.get_source_state(source_id).name == "PLAYING":
                engine.update()
                time.sleep(0.016)  # ~60 FPS

            print("✓ Finished playing with effect\n")

    else:
        # Play once with or without effect
        if args.no_effect:
            print(f"Playing WITHOUT radio effect: {message_key}\n")
            atc_audio.set_radio_effect_enabled(False)
        else:
            print(f"Playing WITH radio effect: {message_key}\n")
            atc_audio.set_radio_effect_enabled(True)

        source_id = atc_audio.play_atc_message(message_key, volume=1.0)

        if source_id:
            print("Playing... (press Ctrl+C to stop)")

            # Wait for message to finish
            try:
                while engine.get_source_state(source_id).name == "PLAYING":
                    engine.update()
                    time.sleep(0.016)  # ~60 FPS

                print("\n✓ Finished playing\n")

            except KeyboardInterrupt:
                print("\n\nStopped by user")
                engine.stop_source(source_id)
        else:
            print("Error: Failed to play message")

    # Shutdown
    print("Shutting down...")
    atc_audio.shutdown()
    engine.shutdown()
    print("✓ Done")


if __name__ == "__main__":
    main()

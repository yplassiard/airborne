#!/usr/bin/env python3
"""Import useful sounds from Eurofly 2 extraction.

Organizes and copies relevant audio files from Eurofly extraction
to AirBorne's data/sounds directory.
"""

import shutil
from pathlib import Path

# Source and destination
SOURCE_DIR = Path.home() / "ef/extracted/app/audio"
DEST_DIR = Path("data/sounds")


def copy_sound(source: Path, dest: Path) -> bool:
    """Copy a sound file if source exists.

    Args:
        source: Source file path
        dest: Destination file path

    Returns:
        True if copied successfully
    """
    if source.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        print(f"✓ Copied: {dest.name}")
        return True
    print(f"✗ Not found: {source}")
    return False


def main() -> None:
    """Import Eurofly sounds."""
    print("Importing Eurofly 2 sounds to AirBorne...")
    print(f"Source: {SOURCE_DIR}")
    print(f"Destination: {DEST_DIR}")
    print()

    if not SOURCE_DIR.exists():
        print(f"ERROR: Source directory not found: {SOURCE_DIR}")
        print("Please extract ef2.exe first using innoextract")
        return

    copied = 0
    total = 0

    # Environment sounds
    print("=== Environment Sounds ===")
    env_dest = DEST_DIR / "environment"
    weather_src = SOURCE_DIR / "weather"

    env_sounds = [
        # Wind
        (weather_src / "wind1.ogg", env_dest / "wind_light.ogg"),
        (weather_src / "wind2.ogg", env_dest / "wind_moderate.ogg"),
        # Rain
        (weather_src / "lightrain1.ogg", env_dest / "rain_light.ogg"),
        (weather_src / "rain1.ogg", env_dest / "rain_moderate.ogg"),
        (weather_src / "heavyrain1.ogg", env_dest / "rain_heavy.ogg"),
        # Storm
        (weather_src / "lightstorm1.ogg", env_dest / "storm_light.ogg"),
        (weather_src / "storm1.ogg", env_dest / "storm_moderate.ogg"),
        (weather_src / "heavystorm1.ogg", env_dest / "storm_heavy.ogg"),
        # Thunder
        (weather_src / "thunder1.ogg", env_dest / "thunder.ogg"),
        # Crash
        (SOURCE_DIR / "crash.mp3", env_dest / "crash.mp3"),
        (SOURCE_DIR / "crashwater.mp3", env_dest / "crash_water.mp3"),
        # Fall
        (SOURCE_DIR / "falling.mp3", env_dest / "falling.mp3"),
    ]

    for src, dst in env_sounds:
        total += 1
        if copy_sound(src, dst):
            copied += 1

    # Aircraft sounds
    print("\n=== Aircraft Sounds ===")
    aircraft_src = SOURCE_DIR / "aircraft"
    aircraft_dest = DEST_DIR / "aircraft"

    aircraft_sounds = [
        # Doors
        (aircraft_src / "doorsopen1.mp3", aircraft_dest / "door_open.mp3"),
        (aircraft_src / "doorsclose1.mp3", aircraft_dest / "door_close.mp3"),
        # Boarding
        (aircraft_src / "boardinga.mp3", aircraft_dest / "boarding.mp3"),
        # Clicks/switches
        (aircraft_src / "click1.mp3", aircraft_dest / "switch_1.mp3"),
        (aircraft_src / "click2.mp3", aircraft_dest / "switch_2.mp3"),
        (aircraft_src / "click3.mp3", aircraft_dest / "switch_3.mp3"),
        # Ding
        (aircraft_src / "ding.mp3", aircraft_dest / "ding.mp3"),
        # Brakes
        (aircraft_src / "brakeson.mp3", aircraft_dest / "brakes_on.mp3"),
        (aircraft_src / "brakesoff.mp3", aircraft_dest / "brakes_off.mp3"),
    ]

    for src, dst in aircraft_sounds:
        total += 1
        if copy_sound(src, dst):
            copied += 1

    # Airport/ATC sounds
    print("\n=== Airport Sounds ===")
    airport_src = SOURCE_DIR / "airport"
    airport_dest = DEST_DIR / "airport"

    airport_sounds = [
        # Gate
        (airport_src / "gate.mp3", airport_dest / "gate.mp3"),
        (airport_src / "gateclose.mp3", airport_dest / "gate_close.mp3"),
        # Parking
        (airport_src / "parking.mp3", airport_dest / "parking.mp3"),
        # Applause (for successful landing)
        (airport_src / "applause.mp3", airport_dest / "applause.mp3"),
    ]

    for src, dst in airport_sounds:
        total += 1
        if copy_sound(src, dst):
            copied += 1

    # UI/Cue sounds
    print("\n=== UI/Cue Sounds ===")
    cues_dest = DEST_DIR / "cues"

    cue_sounds = [
        # Tones
        (SOURCE_DIR / "tones/1.ogg", cues_dest / "beep_1.ogg"),
        (SOURCE_DIR / "tones/2.ogg", cues_dest / "beep_2.ogg"),
        (SOURCE_DIR / "tones/3.ogg", cues_dest / "beep_3.ogg"),
        # Message
        (SOURCE_DIR / "message.ogg", cues_dest / "message.ogg"),
        # Radar
        (SOURCE_DIR / "radar.mp3", cues_dest / "radar.mp3"),
        # Point
        (SOURCE_DIR / "point.mp3", cues_dest / "point.mp3"),
    ]

    for src, dst in cue_sounds:
        total += 1
        if copy_sound(src, dst):
            copied += 1

    print("\n✅ Import complete!")
    print(f"   Copied: {copied}/{total} files")
    print("\nNote: Keep placeholder WAV files for engine sounds.")
    print("      Eurofly uses more complex engine audio system.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate cockpit panel control speech messages for AirBorne.

This script generates pre-recorded TTS audio files for all cockpit panel controls
using the macOS 'say' command with Samantha voice at 180 WPM.

Usage:
    python scripts/generate_cockpit_speech.py
"""

import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# Configuration
VOICE = "Samantha"
RATE = 180  # Words per minute
OUTPUT_DIR = Path("data/speech/en")
FORMAT = "mp3"

# Cockpit panel control messages
COCKPIT_MESSAGES = {
    # Panel names
    "instrument_panel": "Instrument Panel",
    "pedestal": "Pedestal",
    "engine_controls": "Engine Controls",
    "overhead_panel": "Overhead Panel",
    "flight_controls": "Flight Controls",
    # Instrument Panel - Master Switch
    "master_switch": "Master Switch",
    "master_off": "Master Off",
    "master_on": "Master On",
    # Instrument Panel - Avionics Master
    "avionics_master": "Avionics Master",
    "avionics_off": "Avionics Off",
    "avionics_on": "Avionics On",
    # Instrument Panel - Beacon
    "beacon": "Beacon",
    "beacon_off": "Beacon Off",
    "beacon_on": "Beacon On",
    # Instrument Panel - Nav Lights
    "nav_lights": "Nav Lights",
    "nav_lights_off": "Nav Lights Off",
    "nav_lights_on": "Nav Lights On",
    # Instrument Panel - Strobe
    "strobe": "Strobe",
    "strobe_off": "Strobe Off",
    "strobe_on": "Strobe On",
    # Instrument Panel - Taxi Light
    "taxi_light": "Taxi Light",
    "taxi_light_off": "Taxi Light Off",
    "taxi_light_on": "Taxi Light On",
    # Instrument Panel - Landing Light
    "landing_light": "Landing Light",
    "landing_light_off": "Landing Light Off",
    "landing_light_on": "Landing Light On",
    # Pedestal - Mixture Lever
    "mixture": "Mixture",
    "mixture_idle_cutoff": "Mixture Idle Cutoff",
    "mixture_lean": "Mixture Lean",
    "mixture_rich": "Mixture Rich",
    # Pedestal - Carburetor Heat
    "carburetor_heat": "Carburetor Heat",
    "carb_heat_cold": "Carb Heat Cold",
    "carb_heat_hot": "Carb Heat Hot",
    # Pedestal - Throttle (0-100% in 5% increments)
    "throttle": "Throttle",
    **{f"throttle_{i}_percent": f"Throttle {i} Percent" for i in range(0, 101, 5)},
    # Pedestal - Fuel Selector Valve
    "fuel_selector": "Fuel Selector",
    "fuel_off": "Fuel Off",
    "fuel_left": "Fuel Left",
    "fuel_right": "Fuel Right",
    "fuel_both": "Fuel Both",
    # Pedestal - Fuel Shutoff Valve
    "fuel_shutoff_valve": "Fuel Shutoff Valve",
    "fuel_shutoff_closed": "Fuel Shutoff Closed",
    "fuel_shutoff_open": "Fuel Shutoff Open",
    # Pedestal - Fuel Pump
    "fuel_pump": "Fuel Pump",
    "fuel_pump_off": "Fuel Pump Off",
    "fuel_pump_on": "Fuel Pump On",
    # Pedestal - Primer Pump
    "primer": "Primer",
    "primer_pressed": "Primer Pressed",
    # Engine Controls - Magnetos
    "magnetos": "Magnetos",
    "magnetos_off": "Magnetos Off",
    "magnetos_right": "Magnetos Right",
    "magnetos_left": "Magnetos Left",
    "magnetos_both": "Magnetos Both",
    "magnetos_start": "Magnetos Start",
    # Engine Controls - Starter
    "starter": "Starter",
    "starter_pressed": "Starter Pressed",
    # Overhead Panel - Pitot Heat
    "pitot_heat": "Pitot Heat",
    "pitot_heat_off": "Pitot Heat Off",
    "pitot_heat_on": "Pitot Heat On",
    # Flight Controls - Flaps
    "flaps": "Flaps",
    "flaps_up": "Flaps Up",
    "flaps_10": "Flaps 10",
    "flaps_20": "Flaps 20",
    "flaps_30": "Flaps 30",
    "flaps_full": "Flaps Full",
    # Flight Controls - Elevator Trim
    "elevator_trim": "Elevator Trim",
    "trim_nose_down": "Trim Nose Down",
    "trim_neutral": "Trim Neutral",
    "trim_nose_up": "Trim Nose Up",
    # Flight Controls - Parking Brake
    "parking_brake": "Parking Brake",
    "parking_brake_released": "Parking Brake Released",
    "parking_brake_set": "Parking Brake Set",
}


def generate_speech_file(filename: str, text: str) -> tuple[str, bool, str]:
    """Generate a single speech file.

    Args:
        filename: Output filename without extension.
        text: Text to synthesize.

    Returns:
        Tuple of (filename, success, error_message).
    """
    output_path = OUTPUT_DIR / f"{filename}.{FORMAT}"
    temp_aiff_path = OUTPUT_DIR / f"temp_{filename}.aiff"

    try:
        # Generate AIFF with 'say'
        cmd = ["say", "-v", VOICE, "-r", str(RATE), "-o", str(temp_aiff_path), text]
        subprocess.run(cmd, capture_output=True, check=True, text=True)

        if not temp_aiff_path.exists():
            return (filename, False, "AIFF file not created")

        # Convert to MP3 with ffmpeg
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(temp_aiff_path),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "64k",
            "-ar",
            "22050",
            "-ac",
            "1",
            str(output_path),
        ]
        subprocess.run(cmd, capture_output=True, check=True, text=True)

        # Remove temp AIFF file
        if temp_aiff_path.exists():
            temp_aiff_path.unlink()

        if not output_path.exists():
            return (filename, False, "MP3 file not created")

        return (filename, True, "")

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        return (filename, False, error_msg)
    except Exception as e:
        return (filename, False, str(e))


def main():
    """Generate all cockpit panel control speech files."""
    # Check for required commands
    try:
        subprocess.run(["say", "--version"], capture_output=True, check=False)
    except FileNotFoundError:
        print("Error: 'say' command not found. This script requires macOS.")
        sys.exit(1)

    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=False)
    except FileNotFoundError:
        print("Error: 'ffmpeg' command not found. Please install ffmpeg.")
        sys.exit(1)

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Generating {len(COCKPIT_MESSAGES)} cockpit control speech files...")
    print(f"Voice: {VOICE}, Rate: {RATE} WPM, Format: {FORMAT}")
    print(f"Output: {OUTPUT_DIR}/")
    print()

    # Generate files in parallel
    success_count = 0
    failure_count = 0

    with ProcessPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(generate_speech_file, filename, text): filename
            for filename, text in COCKPIT_MESSAGES.items()
        }

        for future in as_completed(futures):
            filename, success, error = future.result()
            if success:
                print(f"✓ {filename}.{FORMAT}")
                success_count += 1
            else:
                print(f"✗ {filename}.{FORMAT} - {error}")
                failure_count += 1

    print()
    print(f"Complete: {success_count} succeeded, {failure_count} failed")

    if failure_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

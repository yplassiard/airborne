#!/usr/bin/env python3
"""Generate TTS audio files for instrument readouts.

Uses macOS 'say' command to generate speech files with Samantha voice at 200 WPM.
"""

import subprocess
import sys
from pathlib import Path

# Configuration
VOICE = "Samantha"  # Cockpit voice
RATE = 200  # Words per minute
OUTPUT_DIR = Path(__file__).parent.parent / "assets" / "sounds" / "pilot"
TEMP_DIR = Path("/tmp")

# Check for ffmpeg
try:
    subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    FFMPEG_AVAILABLE = True
except (subprocess.CalledProcessError, FileNotFoundError):
    print("Warning: ffmpeg not available, will output AIFF files only")
    FFMPEG_AVAILABLE = False


def generate_speech(text: str, output_filename: str) -> None:
    """Generate speech audio file.

    Args:
        text: Text to speak
        output_filename: Output filename (without extension)
    """
    output_path = OUTPUT_DIR / f"{output_filename}.mp3"

    # Skip if file already exists
    if output_path.exists():
        print(f"  Skipping {output_filename} (already exists)")
        return

    print(f"  Generating {output_filename}: '{text}'")

    # Generate to temp AIFF first
    temp_aiff_path = TEMP_DIR / f"{output_filename}.aiff"

    cmd = ["say", "-v", VOICE, "-r", str(RATE), "-o", str(temp_aiff_path), text]

    subprocess.run(
        cmd,
        capture_output=True,
        check=True,
    )

    # Convert to MP3 using ffmpeg
    if FFMPEG_AVAILABLE:
        subprocess.run(
            [
                "ffmpeg",
                "-i",
                str(temp_aiff_path),
                "-codec:a",
                "libmp3lame",
                "-q:a",
                "2",
                "-y",
                str(output_path),
            ],
            capture_output=True,
            check=True,
        )
        temp_aiff_path.unlink()
    else:
        # Just rename to .aiff
        print("  Warning: ffmpeg not available, keeping as AIFF")
        temp_aiff_path.rename(output_path.with_suffix(".aiff"))


def main() -> int:
    """Generate all instrument readout TTS files."""
    print(f"Generating instrument readout TTS files with {VOICE} at {RATE} WPM")
    print(f"Output directory: {OUTPUT_DIR}")

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Engine instruments
    print("\nEngine instruments:")
    generate_speech("engine stopped", "MSG_ENGINE_STOPPED")
    generate_speech("engine RPM", "MSG_WORD_ENGINE_RPM")
    generate_speech("manifold pressure", "MSG_WORD_MANIFOLD_PRESSURE")
    generate_speech("inches", "MSG_WORD_INCHES")
    generate_speech("oil pressure", "MSG_WORD_OIL_PRESSURE")
    generate_speech("PSI", "MSG_WORD_PSI")
    generate_speech("oil temperature", "MSG_WORD_OIL_TEMPERATURE")
    generate_speech("degrees", "MSG_WORD_DEGREES")
    generate_speech("fuel flow", "MSG_WORD_FUEL_FLOW")
    generate_speech("gallons per hour", "MSG_WORD_GALLONS_PER_HOUR")

    # Electrical instruments
    print("\nElectrical instruments:")
    generate_speech("battery", "MSG_WORD_BATTERY")
    generate_speech("volts", "MSG_WORD_VOLTS")
    generate_speech("percent", "MSG_WORD_PERCENT")
    generate_speech("battery charging", "MSG_BATTERY_CHARGING")
    generate_speech("battery discharging", "MSG_BATTERY_DISCHARGING")
    generate_speech("battery stable", "MSG_BATTERY_STABLE")
    generate_speech("at", "MSG_WORD_AT")
    generate_speech("amps", "MSG_WORD_AMPS")
    generate_speech("alternator output", "MSG_WORD_ALTERNATOR_OUTPUT")

    # Fuel instruments
    print("\nFuel instruments:")
    generate_speech("fuel quantity", "MSG_WORD_FUEL_QUANTITY")
    generate_speech("gallons", "MSG_WORD_GALLONS")
    generate_speech("fuel remaining", "MSG_WORD_FUEL_REMAINING")
    generate_speech("hours", "MSG_WORD_HOURS")
    generate_speech("minutes", "MSG_WORD_MINUTES")

    # Numbers (needed for values)
    print("\nNumbers (0-100):")
    for i in range(0, 101):
        generate_speech(str(i), f"MSG_NUMBER_{i}")

    # Common larger numbers for RPM
    print("\nRPM values:")
    for rpm in range(500, 3001, 100):
        generate_speech(str(rpm), f"MSG_NUMBER_{rpm}")

    print("\n✓ Generation complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

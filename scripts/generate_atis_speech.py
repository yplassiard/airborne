#!/usr/bin/env python3
"""Generate ATIS speech files using macOS text-to-speech.

This script generates pre-recorded ATIS (Automatic Terminal Information Service)
announcement phrases using the same voice as ATC.
"""

import subprocess
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import multiprocessing

# ATIS messages to generate
ATIS_MESSAGES = {
    "airport_information": "Airport information",
    "time_1730_zulu": "Time 1730 zulu",
    "wind_310_at_8_knots": "Wind 310 at 8 knots",
    "visibility_10_miles": "Visibility 10 miles",
    "ceiling_3000_broken": "Ceiling 3000 broken",
    "temperature_15_celsius": "Temperature 15 celsius",
    "dewpoint_8_celsius": "Dewpoint 8 celsius",
    "altimeter_2992": "Altimeter 2992",
    "runway_31_in_use": "Runway 31 in use",
    "landing_runway_31": "Landing runway 31",
    "departing_runway_31": "Departing runway 31",
    "advise_you_have_information": "Advise you have information",
    "information_alpha": "Information alpha",
    "information_bravo": "Information bravo",
    "information_charlie": "Information charlie",
}


def generate_speech(args):
    """Generate a single speech file using macOS 'say' command.

    Args:
        args: Tuple of (filename, text, output_dir, voice, rate)

    Returns:
        Tuple of (filename, success, error_message)
    """
    filename, text, output_dir, voice, rate = args

    output_path = output_dir / f"{filename}.mp3"

    try:
        # Generate speech with macOS say command
        # Use AIFF first, then convert to MP3
        aiff_path = output_dir / f"{filename}.aiff"

        # Generate AIFF
        subprocess.run(
            ["say", "-v", voice, "-r", str(rate), "-o", str(aiff_path), text],
            check=True,
            capture_output=True,
        )

        # Convert to MP3 using ffmpeg
        subprocess.run(
            [
                "ffmpeg",
                "-i", str(aiff_path),
                "-codec:a", "libmp3lame",
                "-b:a", "64k",
                "-ar", "22050",
                "-ac", "1",  # Mono
                "-y",  # Overwrite
                str(output_path),
            ],
            check=True,
            capture_output=True,
        )

        # Remove temporary AIFF file
        aiff_path.unlink()

        return (filename, True, None)

    except subprocess.CalledProcessError as e:
        return (filename, False, str(e))
    except Exception as e:
        return (filename, False, str(e))


def main():
    """Generate all ATIS speech files."""
    output_dir = Path("data/atc/en")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Voice settings (same as ATC)
    voice = "Evan"  # Male US voice for ATC/ATIS
    rate = 175  # Words per minute (slightly slower than cockpit)

    print("=" * 60)
    print("GENERATING ATIS SPEECH FILES")
    print("=" * 60)
    print(f"\nVoice: {voice}")
    print(f"Rate: {rate} WPM")
    print(f"Output: {output_dir}")
    print(f"Messages to generate: {len(ATIS_MESSAGES)}\n")

    # Prepare arguments for parallel processing
    args_list = [
        (filename, text, output_dir, voice, rate)
        for filename, text in ATIS_MESSAGES.items()
    ]

    # Generate speech files in parallel
    num_workers = min(multiprocessing.cpu_count(), len(ATIS_MESSAGES))
    print(f"Generating speech files using {num_workers} workers...\n")

    success_count = 0
    failed_count = 0

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        results = executor.map(generate_speech, args_list)

        for filename, success, error in results:
            if success:
                print(f"✓ {filename}.mp3")
                success_count += 1
            else:
                print(f"✗ {filename}.mp3 - Error: {error}")
                failed_count += 1

    print("\n" + "=" * 60)
    print("GENERATION COMPLETE")
    print("=" * 60)
    print(f"\nSuccessful: {success_count}/{len(ATIS_MESSAGES)}")
    if failed_count > 0:
        print(f"Failed: {failed_count}/{len(ATIS_MESSAGES)}")
    print(f"\nAll ATIS speech files saved to: {output_dir}")


if __name__ == "__main__":
    main()

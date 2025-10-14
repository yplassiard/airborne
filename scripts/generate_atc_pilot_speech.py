#!/usr/bin/env python3
"""Script to generate ATC and pilot speech messages for interactive radio.

This script generates pre-recorded audio for:
1. ATC messages (Evan voice at 220 WPM)
2. Pilot messages (Oliver voice at 200 WPM)

Usage:
    uv run python scripts/generate_atc_pilot_speech.py
"""

import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# Check if 'say' command is available (macOS)
SAY_AVAILABLE = False
try:
    result = subprocess.run(
        ["say", "--version"],
        capture_output=True,
        check=False,
    )
    SAY_AVAILABLE = result.returncode == 0 or "say" in result.stderr.decode().lower()
except FileNotFoundError:
    pass

if not SAY_AVAILABLE:
    print("Error: 'say' command not found. This script requires macOS.")
    sys.exit(1)

# Check if ffmpeg is available
FFMPEG_AVAILABLE = False
try:
    result = subprocess.run(
        ["ffmpeg", "-version"],
        capture_output=True,
        check=False,
    )
    FFMPEG_AVAILABLE = result.returncode == 0
except FileNotFoundError:
    print("Error: ffmpeg not found. Required for MP3 conversion.")
    sys.exit(1)


# ATC messages (Evan 220 WPM) - text to synthesize
ATC_MESSAGES = {
    # Additional messages for readback system
    "readback_correct": "Readback correct",
}

# Pilot messages (Oliver 200 WPM)
PILOT_MESSAGES = {
    # Ground Operations
    "request_startup_clearance": "Ground, Cessna one two three alpha bravo, request startup clearance",
    "request_pushback": "Ground, Cessna one two three alpha bravo, request pushback",
    "request_taxi": "Ground, Cessna one two three alpha bravo, request taxi",
    "ready_for_departure": "Tower, Cessna one two three alpha bravo, ready for departure",

    # Taxiing
    "holding_short": "Tower, Cessna one two three alpha bravo, holding short",
    "ready_for_takeoff": "Tower, Cessna one two three alpha bravo, ready for takeoff",

    # Takeoff
    "request_takeoff_clearance": "Tower, Cessna one two three alpha bravo, request takeoff clearance",
    "rolling": "Cessna one two three alpha bravo, rolling",
    "departing": "Cessna one two three alpha bravo, departing",

    # In Flight - Departure
    "airborne": "Cessna one two three alpha bravo, airborne",
    "with_you": "Departure, Cessna one two three alpha bravo, with you",
    "level_at": "Cessna one two three alpha bravo, level at",
    "climbing_to": "Cessna one two three alpha bravo, climbing to",
    "leaving": "Cessna one two three alpha bravo, leaving",

    # In Flight - Cruise
    "request_higher": "Center, Cessna one two three alpha bravo, request higher",
    "request_lower": "Center, Cessna one two three alpha bravo, request lower",
    "request_direct": "Center, Cessna one two three alpha bravo, request direct",
    "traffic_in_sight": "Cessna one two three alpha bravo, traffic in sight",
    "negative_visual_contact": "Cessna one two three alpha bravo, negative visual contact",

    # In Flight - Approach
    "request_approach": "Approach, Cessna one two three alpha bravo, request approach",
    "descending_to": "Cessna one two three alpha bravo, descending to",
    "reducing_speed": "Cessna one two three alpha bravo, reducing speed",
    "established_on_approach": "Cessna one two three alpha bravo, established on approach",

    # Landing
    "runway_in_sight": "Cessna one two three alpha bravo, runway in sight",
    "landing": "Cessna one two three alpha bravo, landing",
    "going_around": "Cessna one two three alpha bravo, going around",
    "clear_of_runway": "Cessna one two three alpha bravo, clear of runway",

    # Readback & Acknowledgment
    "readback": "Roger",  # Generic - actual readback assembled at runtime
    "say_again": "Cessna one two three alpha bravo, say again",
    "roger": "Cessna one two three alpha bravo, roger",
    "wilco": "Cessna one two three alpha bravo, wilco",
    "unable": "Cessna one two three alpha bravo, unable",
    "affirmative": "Cessna one two three alpha bravo, affirmative",
    "negative": "Cessna one two three alpha bravo, negative",

    # ATIS
    "request_atis": "Ground, Cessna one two three alpha bravo, request ATIS",
    "have_information_alpha": "Cessna one two three alpha bravo, have information alpha",
    "have_information_bravo": "Cessna one two three alpha bravo, have information bravo",
    "have_information_charlie": "Cessna one two three alpha bravo, have information charlie",

    # Emergency
    "declaring_emergency": "Mayday, mayday, mayday. Cessna one two three alpha bravo, declaring an emergency",
    "request_priority_handling": "Cessna one two three alpha bravo, request priority handling",
    "pan_pan_pan_pan": "Pan pan, pan pan, pan pan",
    "mayday_mayday_mayday": "Mayday, mayday, mayday",
}


def generate_speech_file(
    text: str,
    output_path: Path,
    voice: str,
    rate: int,
) -> None:
    """Generate speech audio file for given text using macOS 'say'.

    Args:
        text: Text to synthesize.
        output_path: Path to save audio file.
        voice: Voice name for 'say' command.
        rate: Speech rate in words per minute.
    """
    # Generate to AIFF first (native format for 'say')
    temp_aiff_path = output_path.parent / f"temp_{output_path.stem}.aiff"

    print(f"  Generating: {text} -> {output_path.name}")

    try:
        # Generate speech using 'say' command
        cmd = [
            "say",
            "-v", voice,
            "-r", str(rate),
            "-o", str(temp_aiff_path),
            text
        ]

        subprocess.run(cmd, capture_output=True, check=True)

        if not temp_aiff_path.exists():
            print(f"  Error: 'say' failed to generate {temp_aiff_path}")
            return

        # Convert AIFF to MP3
        print(f"  Converting AIFF to MP3: {output_path.name}")
        subprocess.run(
            [
                "ffmpeg",
                "-i", str(temp_aiff_path),
                "-c:a", "libmp3lame",
                "-b:a", "64k",
                "-ar", "22050",
                "-ac", "1",
                "-y",
                str(output_path),
            ],
            capture_output=True,
            check=True,
        )

        # Remove temporary AIFF file
        if temp_aiff_path.exists():
            temp_aiff_path.unlink()

    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode() if e.stderr else ""
        stdout = e.stdout.decode() if e.stdout else ""
        print(f"  Error generating {text}: {stderr or stdout or str(e)}")
        if temp_aiff_path.exists():
            temp_aiff_path.unlink()
    except Exception as e:
        print(f"  Error generating {text}: {e}")
        if temp_aiff_path.exists():
            temp_aiff_path.unlink()


def main() -> None:
    """Main entry point."""
    import os

    # Create output directories
    atc_dir = Path("data/speech/atc/en")
    pilot_dir = Path("data/speech/pilot/en")
    atc_dir.mkdir(parents=True, exist_ok=True)
    pilot_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("ATC & Pilot Speech Generation")
    print("=" * 70)

    # Generate ATC messages (Evan at 220 WPM)
    print(f"\n1. Generating {len(ATC_MESSAGES)} ATC messages (Evan, 220 WPM)...")
    print(f"   Output: {atc_dir}")

    atc_tasks = []
    for filename, text in ATC_MESSAGES.items():
        output_path = atc_dir / f"{filename}.mp3"
        atc_tasks.append((text, output_path, "Evan", 220))

    # Generate pilot messages (Oliver at 200 WPM)
    print(f"\n2. Generating {len(PILOT_MESSAGES)} pilot messages (Oliver, 200 WPM)...")
    print(f"   Output: {pilot_dir}")

    pilot_tasks = []
    for filename, text in PILOT_MESSAGES.items():
        output_path = pilot_dir / f"{filename}.mp3"
        pilot_tasks.append((text, output_path, "Oliver", 200))

    all_tasks = atc_tasks + pilot_tasks
    total = len(all_tasks)

    print(f"\nGenerating {total} total speech files using parallel processing...\n")

    # Generate files in parallel
    completed = 0
    failed = 0
    max_workers = os.cpu_count() or 4

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(generate_speech_file, text, path, voice, rate): (text, path)
            for text, path, voice, rate in all_tasks
        }

        for future in as_completed(futures):
            text, path = futures[future]
            try:
                future.result()
                completed += 1
                if completed % 5 == 0:
                    print(f"Progress: {completed}/{total} ({completed*100//total}%)")
            except Exception as e:
                failed += 1
                print(f"  Error: {e}")

    print("\n" + "=" * 70)
    print(f"✓ Done! Generated {completed} speech files")
    print(f"  ATC messages: {len(ATC_MESSAGES)} files in {atc_dir}")
    print(f"  Pilot messages: {len(PILOT_MESSAGES)} files in {pilot_dir}")
    if failed > 0:
        print(f"⚠ {failed} files failed to generate")
    print("=" * 70)


if __name__ == "__main__":
    main()

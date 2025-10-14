#!/usr/bin/env python3
"""Script to generate ATC speech files with different voice.

This script generates pre-recorded speech files for ATC communications
using macOS 'say' command with a male voice (different from cockpit TTS).

Usage:
    python scripts/generate_atc_speech.py --voice Alex --rate 175
"""

import argparse
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
    print("Warning: ffmpeg not found. Only AIFF format will be supported.")
    FFMPEG_AVAILABLE = False


def normalize_text_to_filename(text: str) -> str:
    """Convert text to normalized filename.

    Args:
        text: Text message.

    Returns:
        Normalized filename without extension.
    """
    normalized = text.lower().strip()
    normalized = normalized.replace(" ", "_")
    normalized = "".join(c for c in normalized if c.isalnum() or c == "_")
    return normalized


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
        cmd = ["say", "-v", voice, "-r", str(rate), "-o", str(temp_aiff_path), text]

        result = subprocess.run(
            cmd,
            capture_output=True,
            check=True,
        )

        if not temp_aiff_path.exists():
            print(f"  Error: 'say' failed to generate {temp_aiff_path}")
            return

        # Convert to MP3 using ffmpeg
        if not FFMPEG_AVAILABLE:
            print("  Warning: ffmpeg not available, keeping as AIFF")
            temp_aiff_path.rename(output_path.with_suffix(".aiff"))
            return

        if output_path.suffix == ".mp3":
            print(f"  Converting AIFF to MP3: {output_path.name}")
            subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    str(temp_aiff_path),
                    "-c:a",
                    "libmp3lame",
                    "-b:a",
                    "64k",
                    "-ar",
                    "22050",
                    "-ac",
                    "1",
                    "-y",
                    str(output_path),
                ],
                capture_output=True,
                check=True,
            )
        else:
            print(f"  Warning: Unsupported format {output_path.suffix}")
            return

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


def get_atc_messages() -> list[tuple[str, str]]:
    """Get list of ATC messages to generate.

    Returns:
        List of (text, filename) tuples.
    """
    messages = [
        # Greetings
        ("Good morning", "good_morning"),
        ("Good afternoon", "good_afternoon"),
        ("Good evening", "good_evening"),
        # Ground Control
        ("Taxi to runway 31 via Alpha", "taxi_to_runway_31_via_alpha"),
        ("Taxi to runway 13 via Bravo", "taxi_to_runway_13_via_bravo"),
        ("Hold short of runway 31", "hold_short_of_runway_31"),
        ("Hold short of runway 13", "hold_short_of_runway_13"),
        ("Cross runway 31", "cross_runway_31"),
        ("Contact tower 120 point 5", "contact_tower_120_point_5"),
        ("Contact tower 118 point 3", "contact_tower_118_point_3"),
        # Tower - Takeoff
        ("Runway 31, line up and wait", "runway_31_line_up_and_wait"),
        ("Runway 13, line up and wait", "runway_13_line_up_and_wait"),
        ("Runway 31, cleared for takeoff", "runway_31_cleared_for_takeoff"),
        ("Runway 13, cleared for takeoff", "runway_13_cleared_for_takeoff"),
        ("Wind 310 at 8", "wind_310_at_8"),
        ("Contact departure 125 point 35", "contact_departure_125_point_35"),
        # Departure Control
        ("Radar contact", "radar_contact"),
        ("Climb and maintain 3000", "climb_and_maintain_3000"),
        ("Climb and maintain 5000", "climb_and_maintain_5000"),
        ("Turn left heading 270", "turn_left_heading_270"),
        ("Turn right heading 090", "turn_right_heading_090"),
        ("Contact center 132 point 45", "contact_center_132_point_45"),
        # Center
        ("Climb and maintain 10000", "climb_and_maintain_10000"),
        ("Descend and maintain 5000", "descend_and_maintain_5000"),
        ("Fly heading 180", "fly_heading_180"),
        ("Proceed direct", "proceed_direct"),
        ("Traffic 2 o'clock, 5 miles", "traffic_2_oclock_5_miles"),
        # Approach
        ("Expect ILS runway 31 approach", "expect_ils_runway_31_approach"),
        ("Cleared ILS runway 31 approach", "cleared_ils_runway_31_approach"),
        ("Descend and maintain 2000", "descend_and_maintain_2000"),
        ("Reduce speed to 180 knots", "reduce_speed_to_180_knots"),
        # Tower - Landing
        ("Runway 31, cleared to land", "runway_31_cleared_to_land"),
        ("Runway 13, cleared to land", "runway_13_cleared_to_land"),
        ("Wind calm", "wind_calm"),
        ("Go around", "go_around"),
        ("Exit runway next available right", "exit_runway_next_available_right"),
        ("Contact ground 121 point 9", "contact_ground_121_point_9"),
        # Generic
        ("Roger", "roger"),
        ("Affirmative", "affirmative"),
        ("Negative", "negative"),
        ("Say again", "say_again"),
        ("Wilco", "wilco"),
        ("Unable", "unable"),
        ("Standby", "standby"),
        ("Cleared", "cleared"),
        ("Report", "report"),
        # Emergency
        ("Roger, emergency aircraft", "roger_emergency_aircraft"),
        ("Say intentions", "say_intentions"),
        ("All traffic, clear runway", "all_traffic_clear_runway"),
    ]

    return messages


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate ATC speech files using macOS 'say' with male voice"
    )
    parser.add_argument(
        "--voice",
        type=str,
        default="Alex",
        help="Voice name for 'say' command (default: Alex - male voice)",
    )
    parser.add_argument(
        "--rate",
        type=int,
        default=175,
        help="Speech rate in words per minute (default: 175, slightly slower than cockpit)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/atc",
        help="Output directory (default: data/atc)",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["mp3", "aiff"],
        default="mp3",
        help="Output audio format (default: mp3)",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="en",
        help="Language code (default: en)",
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="List available voices and exit",
    )

    args = parser.parse_args()

    # List voices if requested
    if args.list_voices:
        print("\nAvailable voices (macOS 'say'):")
        result = subprocess.run(
            ["say", "-v", "?"],
            capture_output=True,
            text=True,
        )
        print(result.stdout)
        return

    # Create output directory
    output_dir = Path(args.output_dir) / args.language
    output_dir.mkdir(parents=True, exist_ok=True)

    # Delete existing files
    existing_files = list(output_dir.glob("*.mp3")) + list(output_dir.glob("*.aiff"))
    if existing_files:
        print(f"\nDeleting {len(existing_files)} existing files in {output_dir}")
        for file in existing_files:
            file.unlink()

    print(f"\nOutput directory: {output_dir}")
    print(f"Voice: {args.voice} (ATC voice)")
    print(f"Format: {args.format}")
    print(f"Rate: {args.rate} WPM")

    # Get messages to generate
    messages = get_atc_messages()
    print(f"\nGenerating {len(messages)} ATC speech files...")
    print("Using parallel processing to speed up generation...\n")

    # Prepare tasks
    tasks = []
    for text, filename in messages:
        output_path = output_dir / f"{filename}.{args.format}"
        tasks.append((text, output_path, args.voice, args.rate))

    # Generate files in parallel
    completed = 0
    failed = 0

    import os

    max_workers = os.cpu_count() or 4

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = {
            executor.submit(generate_speech_file, text, path, voice, rate): text
            for text, path, voice, rate in tasks
        }

        # Process completed tasks
        for future in as_completed(futures):
            text = futures[future]
            try:
                future.result()
                completed += 1
                if completed % 10 == 0:
                    print(
                        f"Progress: {completed}/{len(messages)} ({completed * 100 // len(messages)}%)"
                    )
            except Exception as e:
                failed += 1
                print(f"  Error generating {text}: {e}")

    print(f"\n✓ Done! Generated {completed} ATC speech files in {output_dir}")
    if failed > 0:
        print(f"⚠ {failed} files failed to generate")


if __name__ == "__main__":
    main()

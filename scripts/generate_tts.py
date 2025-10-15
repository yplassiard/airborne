#!/usr/bin/env python3
"""Script to pre-generate TTS audio files for AirBorne.

This script uses macOS 'say' command to generate pre-recorded audio files
for all speech messages used in the application. These files are stored in
data/speech/{language}/ directory.

Usage:
    python scripts/generate_tts.py --language en --voice Samantha --rate 180

Args:
    --language: Language code (default: en)
    --voice: Voice name (default: Samantha on macOS)
    --rate: Speech rate in words per minute (default: 180)
    --output-dir: Output directory (default: data/speech)
    --format: Output format - wav, ogg, mp3 (default: mp3)
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
        # say -v Voice -r rate -o output.aiff "text"
        cmd = ["say", "-v", voice, "-r", str(rate), "-o", str(temp_aiff_path), text]

        result = subprocess.run(
            cmd,
            capture_output=True,
            check=True,
        )

        if not temp_aiff_path.exists():
            print(f"  Error: 'say' failed to generate {temp_aiff_path}")
            return

        # Convert to target format using ffmpeg
        if not FFMPEG_AVAILABLE:
            if output_path.suffix != ".aiff":
                print("  Warning: ffmpeg not available, keeping as AIFF")
                temp_aiff_path.rename(output_path.with_suffix(".aiff"))
                return

        if output_path.suffix == ".wav":
            # Convert AIFF to proper PCM WAV
            print(f"  Converting AIFF to WAV: {output_path.name}")
            subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    str(temp_aiff_path),
                    "-acodec",
                    "pcm_s16le",  # PCM 16-bit little-endian
                    "-ar",
                    "22050",  # Sample rate
                    "-ac",
                    "1",  # Mono
                    "-y",  # Overwrite
                    str(output_path),
                ],
                capture_output=True,
                check=True,
            )
        elif output_path.suffix == ".ogg":
            # Convert AIFF to OGG Vorbis
            print(f"  Converting AIFF to OGG: {output_path.name}")
            subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    str(temp_aiff_path),
                    "-c:a",
                    "libvorbis",  # Vorbis codec
                    "-q:a",
                    "4",  # Quality level 4
                    "-ar",
                    "22050",  # Sample rate
                    "-ac",
                    "1",  # Mono
                    "-y",  # Overwrite
                    str(output_path),
                ],
                capture_output=True,
                check=True,
            )
        elif output_path.suffix == ".mp3":
            # Convert AIFF to MP3
            print(f"  Converting AIFF to MP3: {output_path.name}")
            subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    str(temp_aiff_path),
                    "-c:a",
                    "libmp3lame",  # MP3 codec
                    "-b:a",
                    "64k",  # Bitrate 64kbps (good for speech)
                    "-ar",
                    "22050",  # Sample rate
                    "-ac",
                    "1",  # Mono
                    "-y",  # Overwrite
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
        # Clean up temp file
        if temp_aiff_path.exists():
            temp_aiff_path.unlink()
    except Exception as e:
        print(f"  Error generating {text}: {e}")
        # Clean up temp file
        if temp_aiff_path.exists():
            temp_aiff_path.unlink()


def heading_to_words(heading: int) -> str:
    """Convert heading to spoken form with 'niner' for 9.

    Args:
        heading: Heading in degrees (0-359).

    Returns:
        Spoken form (e.g., "two one five", "one niner zero").
    """
    # Convert to 3-digit string with leading zeros
    heading_str = f"{heading:03d}"

    # Digit to word mapping (using 'niner' for 9)
    digit_map = {
        "0": "zero",
        "1": "one",
        "2": "two",
        "3": "three",
        "4": "four",
        "5": "five",
        "6": "six",
        "7": "seven",
        "8": "eight",
        "9": "niner",
    }

    words = [digit_map[d] for d in heading_str]
    return " ".join(words)


def get_default_messages() -> list[str]:
    """Get list of default messages to generate.

    Returns:
        List of text messages.
    """
    messages = []

    # Instrument readouts - airspeed (common speeds only)
    # Most speeds will be assembled from digits + "knots"
    for speed in [0, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180]:
        messages.append(f"{speed} knots")

    # Individual digits for assembly (0-9, with "niner" for 9)
    digits = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "niner"]
    for digit in digits:
        messages.append(digit)

    # Common words for assembly
    messages.append("heading")
    messages.append("flight level")
    messages.append("feet")
    messages.append("knots")

    # Instrument readouts - altitude (specific common altitudes only)
    # Most altitudes will be assembled from digits
    for altitude in [100, 500, 1000, 1500, 2000, 2500, 3000, 4000, 5000, 10000, 15000, 20000]:
        messages.append(f"{altitude} feet")

    # Instrument readouts - vertical speed (number first)
    messages.append("Level flight")
    for vspeed in [100, 200, 300, 500, 1000, 1500, 2000]:
        messages.append(f"{vspeed} climbing")
        messages.append(f"{vspeed} descending")

    # Attitude readouts - separate bank and pitch announcements
    messages.append("Level")

    # Pitch only
    for angle in [5, 10, 15, 20, 30, 45]:
        messages.append(f"{angle} up")
        messages.append(f"{angle} down")

    # Bank only
    for angle in [5, 10, 15, 20, 30, 45]:
        messages.append(f"{angle} left")
        messages.append(f"{angle} right")

    # Action confirmations
    actions = [
        "Gear down",
        "Gear up",
        "Flaps extending",
        "Flaps retracting",
        "Throttle increased",
        "Throttle decreased",
        "Full throttle",
        "Throttle idle",
        "Brakes on",
        "Paused",
        "Next",
    ]
    messages.extend(actions)

    # System messages
    messages.extend(
        [
            "AirBorne Flight Simulator",
            "Ready for flight",
            "Error",
            "Error message",
            "Message not found",
        ]
    )

    # ATC Menu messages
    messages.extend(
        [
            "ATC Menu",
            "Menu closed",
            "Invalid option",
            "Press escape to close",
        ]
    )

    # Menu options
    messages.extend(
        [
            "Request Startup Clearance",
            "Request ATIS",
            "Request Taxi",
            "Request Takeoff Clearance",
            "Report Ready for Departure",
            "Check In with Departure",
            "Report Altitude",
            "Request Flight Following",
            "Report Position",
        ]
    )

    return messages


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate pre-recorded TTS audio files for AirBorne using macOS 'say'"
    )
    parser.add_argument(
        "--language",
        type=str,
        default="en",
        help="Language code (default: en)",
    )
    parser.add_argument(
        "--voice",
        type=str,
        default="Samantha",
        help="Voice name for 'say' command (default: Samantha)",
    )
    parser.add_argument(
        "--rate",
        type=int,
        default=180,
        help="Speech rate in words per minute (default: 180)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/speech",
        help="Output directory (default: data/speech)",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["wav", "ogg", "mp3", "aiff"],
        default="mp3",
        help="Output audio format (default: mp3)",
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

    # Delete all existing files in the language directory
    existing_files = (
        list(output_dir.glob("*.ogg"))
        + list(output_dir.glob("*.wav"))
        + list(output_dir.glob("*.mp3"))
        + list(output_dir.glob("*.aiff"))
    )
    if existing_files:
        print(f"\nDeleting {len(existing_files)} existing files in {output_dir}")
        for file in existing_files:
            file.unlink()

    print(f"\nOutput directory: {output_dir}")
    print(f"Voice: {args.voice}")
    print(f"Format: {args.format}")
    print(f"Rate: {args.rate} WPM")

    # Get messages to generate
    messages = get_default_messages()
    print(f"\nGenerating {len(messages)} speech files using macOS 'say'...")
    print("Using parallel processing to speed up generation...\n")

    # Prepare all tasks
    tasks = []
    for i, text in enumerate(messages, 1):
        filename = normalize_text_to_filename(text)
        output_path = output_dir / f"{filename}.{args.format}"
        tasks.append((i, text, output_path, args.voice, args.rate))

    # Generate files in parallel using ProcessPoolExecutor
    completed = 0
    failed = 0

    # Use number of CPU cores for parallel workers
    import os

    max_workers = os.cpu_count() or 4

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = {
            executor.submit(generate_speech_file, text, path, voice, rate): (idx, text)
            for idx, text, path, voice, rate in tasks
        }

        # Process completed tasks
        for future in as_completed(futures):
            idx, text = futures[future]
            try:
                future.result()
                completed += 1
                if completed % 10 == 0:
                    print(
                        f"Progress: {completed}/{len(messages)} ({completed * 100 // len(messages)}%)"
                    )
            except Exception as e:
                failed += 1
                print(f"  Error [{idx}] {text}: {e}")

    print(f"\n✓ Done! Generated {completed} speech files in {output_dir}")
    if failed > 0:
        print(f"⚠ {failed} files failed to generate")


if __name__ == "__main__":
    main()

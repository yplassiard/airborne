#!/usr/bin/env python3
"""Generate TTS audio files for checklist system.

Uses macOS 'say' command to generate speech files with Oliver voice at 200 WPM (pilot voice).
"""

import subprocess
import sys
from pathlib import Path

import yaml

# Configuration
VOICE = "Oliver"  # Pilot voice
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


def extract_checklist_items():
    """Extract all unique challenges and responses from checklist files."""
    challenges = set()
    responses = set()

    checklist_dir = Path(__file__).parent.parent / "config" / "checklists"

    for yaml_file in checklist_dir.glob("*.yaml"):
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
            for item in data.get("items", []):
                challenges.add(item["challenge"])
                resp = item["response"]
                if isinstance(resp, str):
                    responses.add(resp)

    return sorted(challenges), sorted(responses)


def main() -> int:
    """Generate all checklist TTS files."""
    print(f"Generating checklist TTS files with {VOICE} at {RATE} WPM")
    print(f"Output directory: {OUTPUT_DIR}")

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Menu messages
    print("\nChecklist menu messages:")
    generate_speech("checklist menu opened", "MSG_CHECKLIST_MENU_OPENED")
    generate_speech("checklist menu closed", "MSG_CHECKLIST_MENU_CLOSED")
    generate_speech("invalid option", "MSG_CHECKLIST_INVALID_OPTION")
    generate_speech("press escape to close", "MSG_CHECKLIST_PRESS_ESC")
    generate_speech("no checklists available", "MSG_CHECKLIST_NONE_AVAILABLE")
    generate_speech("checklist start failed", "MSG_CHECKLIST_START_FAILED")

    # Checklist state messages
    print("\nChecklist state messages:")
    generate_speech("starting checklist", "MSG_CHECKLIST_STARTING")
    generate_speech("checklist", "MSG_CHECKLIST_TEXT")
    generate_speech("complete", "MSG_CHECKLIST_COMPLETE")

    # Checklist names
    print("\nChecklist names:")
    generate_speech("before engine start", "MSG_CHECKLIST_BEFORE_START")
    generate_speech("engine start", "MSG_CHECKLIST_ENGINE_START")
    generate_speech("before takeoff", "MSG_CHECKLIST_BEFORE_TAKEOFF")
    generate_speech("takeoff", "MSG_CHECKLIST_TAKEOFF")
    generate_speech("before landing", "MSG_CHECKLIST_BEFORE_LANDING")
    generate_speech("after landing", "MSG_CHECKLIST_AFTER_LANDING")
    generate_speech("shutdown", "MSG_CHECKLIST_SHUTDOWN")
    generate_speech("unknown checklist", "MSG_CHECKLIST_UNKNOWN")

    # Common words
    print("\nCommon words:")
    generate_speech("check", "MSG_WORD_CHECK")
    generate_speech("skipped", "MSG_WORD_SKIPPED")
    generate_speech("colon", "MSG_WORD_COLON")  # Used for "Number 1: checklist name"

    # Extract and generate all challenges
    print("\nExtracting challenges and responses from checklists...")
    challenges, responses = extract_checklist_items()

    print(f"\nGenerating {len(challenges)} challenge messages:")
    for challenge in challenges:
        # Replace special characters for filename
        key = "MSG_CHALLENGE_" + (
            challenge.upper()
            .replace(" ", "_")
            .replace("/", "_")
            .replace("(", "_")
            .replace(")", "_")
        )
        generate_speech(challenge, key)

    print(f"\nGenerating {len(responses)} response messages:")
    for response in responses:
        # Replace special characters for filename
        key = "MSG_RESPONSE_" + (
            response.upper()
            .replace(" ", "_")
            .replace("/", "_")
            .replace("(", "_")
            .replace(")", "_")
            .replace("<", "_")
            .replace(">", "_")
        )
        generate_speech(response, key)

    print("\n✓ Generation complete!")
    print(f"Total files: {len(challenges) + len(responses) + 22}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Universal TTS generation script for AirBorne.

Generates speech files for all voice types using the unified config/speech.yaml configuration.
Supports:
- macOS: Uses 'say' command with native voices
- Windows/Linux: Uses pyttsx3 library

Usage:
    python scripts/generate_speech.py              # Generate all voices
    python scripts/generate_speech.py pilot        # Generate only pilot voice
    python scripts/generate_speech.py --clean      # Clean and regenerate all
    python scripts/generate_speech.py --list       # List available voices
"""

import argparse
import platform
import subprocess
import sys
from pathlib import Path

import yaml


def detect_platform():
    """Detect the current platform."""
    system = platform.system()
    if system == "Darwin":
        return "macos"
    elif system == "Windows":
        return "windows"
    else:
        return "linux"


def check_ffmpeg():
    """Check if ffmpeg is available for MP3 conversion."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def generate_with_say(text, output_path, voice_name, rate):
    """Generate speech using macOS 'say' command.

    Args:
        text: Text to speak
        output_path: Output MP3 file path
        voice_name: macOS voice name (e.g., "Oliver", "Samantha")
        rate: Words per minute
    """
    temp_path = output_path.with_suffix(".aiff")

    # Generate AIFF with say
    cmd = ["say", "-v", voice_name, "-r", str(rate), "-o", str(temp_path), text]
    subprocess.run(cmd, capture_output=True, check=True)

    # Convert to MP3 with ffmpeg
    if check_ffmpeg():
        subprocess.run(
            [
                "ffmpeg",
                "-i",
                str(temp_path),
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
        temp_path.unlink()
    else:
        # Rename AIFF to MP3 (will still work with most players)
        temp_path.rename(output_path.with_suffix(".aiff"))
        print("    Warning: ffmpeg not available, kept as AIFF")


def generate_with_pyttsx3(text, output_path, voice_name, rate):
    """Generate speech using pyttsx3 (Windows/Linux).

    Args:
        text: Text to speak
        output_path: Output MP3 file path
        voice_name: Voice name or language code
        rate: Words per minute
    """
    try:
        import pyttsx3
    except ImportError:
        print("Error: pyttsx3 not installed. Install with: pip install pyttsx3")
        sys.exit(1)

    engine = pyttsx3.init()

    # Set rate
    engine.setProperty("rate", rate)

    # Try to set voice by name
    voices = engine.getProperty("voices")
    for voice in voices:
        if voice_name.lower() in voice.name.lower():
            engine.setProperty("voice", voice.id)
            break

    # Save to file (pyttsx3 saves as WAV)
    temp_path = output_path.with_suffix(".wav")
    engine.save_to_file(text, str(temp_path))
    engine.runAndWait()

    # Convert to MP3 with ffmpeg
    if check_ffmpeg():
        subprocess.run(
            [
                "ffmpeg",
                "-i",
                str(temp_path),
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
        temp_path.unlink()
    else:
        # Keep as WAV
        temp_path.rename(output_path.with_suffix(".wav"))
        print("    Warning: ffmpeg not available, kept as WAV")


def generate_speech_file(message_key, text, voice_config, output_dir, force=False):
    """Generate a single speech file.

    Args:
        message_key: Message key (e.g., MSG_STARTUP)
        text: Text to speak
        voice_config: Voice configuration dict
        output_dir: Output directory path
        force: If True, regenerate even if file exists

    Returns:
        True if generated, False if skipped
    """
    output_path = output_dir / f"{message_key}.mp3"

    # Skip if exists and not forcing
    if output_path.exists() and not force:
        return False

    platform_type = detect_platform()
    engine = voice_config.get("engine", "say")

    try:
        if platform_type == "macos" and engine == "say":
            generate_with_say(text, output_path, voice_config["voice_name"], voice_config["rate"])
        else:
            generate_with_pyttsx3(
                text, output_path, voice_config.get("voice_name", "default"), voice_config["rate"]
            )
        return True
    except Exception as e:
        print(f"    Error: {e}")
        return False


def extract_checklist_items(checklist_dir):
    """Extract all unique challenges and responses from checklist files.

    Args:
        checklist_dir: Path to checklists directory

    Returns:
        Tuple of (challenges_set, responses_set)
    """
    challenges = set()
    responses = set()

    checklist_path = Path(checklist_dir)
    if not checklist_path.exists():
        print(f"Warning: Checklist directory not found: {checklist_dir}")
        return challenges, responses

    for yaml_file in checklist_path.glob("*.yaml"):
        try:
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
                for item in data.get("items", []):
                    challenges.add(item["challenge"])
                    resp = item["response"]
                    if isinstance(resp, str):
                        responses.add(resp)
        except Exception as e:
            print(f"Warning: Failed to parse {yaml_file}: {e}")

    return challenges, responses


def sanitize_filename(text):
    """Convert text to safe filename.

    Args:
        text: Text to sanitize

    Returns:
        Sanitized filename
    """
    return (
        text.upper()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("(", "_")
        .replace(")", "_")
        .replace("<", "_")
        .replace(">", "_")
        .replace(":", "_")
        .replace("?", "_")
    )


def generate_voice_messages(voice_name, voice_config, messages, base_dir, force=False):
    """Generate all messages for a specific voice.

    Args:
        voice_name: Voice identifier (e.g., "pilot", "cockpit")
        voice_config: Voice configuration dict
        messages: Dict of message_key -> message_config
        base_dir: Base output directory
        force: If True, regenerate existing files

    Returns:
        Number of files generated
    """
    output_dir = base_dir / voice_config["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)

    generated = 0
    skipped = 0

    print(
        f"\n{voice_name.upper()} voice ({voice_config['voice_name']} @ {voice_config['rate']} WPM):"
    )
    print(f"  Output: {output_dir}")

    # Generate configured messages
    for msg_key, msg_config in messages.items():
        if msg_config.get("voice") == voice_name:
            print(f"  {msg_key}: '{msg_config['text']}'")
            if generate_speech_file(msg_key, msg_config["text"], voice_config, output_dir, force):
                generated += 1
            else:
                skipped += 1

    # Generate checklist challenges and responses (only for pilot voice)
    if voice_name == "pilot":
        print("\n  Extracting checklist challenges and responses...")
        challenges, responses = extract_checklist_items("config/checklists")

        print(f"  Found {len(challenges)} challenges, {len(responses)} responses")

        # Generate challenges
        for challenge in sorted(challenges):
            msg_key = "MSG_CHALLENGE_" + sanitize_filename(challenge)
            print(f"  {msg_key}: '{challenge}'")
            if generate_speech_file(msg_key, challenge, voice_config, output_dir, force):
                generated += 1
            else:
                skipped += 1

        # Generate responses
        for response in sorted(responses):
            msg_key = "MSG_RESPONSE_" + sanitize_filename(response)
            print(f"  {msg_key}: '{response}'")
            if generate_speech_file(msg_key, response, voice_config, output_dir, force):
                generated += 1
            else:
                skipped += 1

    print(f"  Generated: {generated}, Skipped: {skipped}")
    return generated


def list_voices(config):
    """List all configured voices.

    Args:
        config: Speech configuration dict
    """
    print("\nConfigured voices:")
    print("=" * 80)
    for voice_name, voice_config in config["voices"].items():
        print(f"\n{voice_name.upper()}")
        print(f"  Description: {voice_config['description']}")
        print(f"  Engine: {voice_config['engine']}")
        print(f"  Voice: {voice_config['voice_name']}")
        print(f"  Rate: {voice_config['rate']} WPM")
        print(f"  Output: data/speech/<lang>/{voice_config['output_dir']}/")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate TTS files for AirBorne")
    parser.add_argument(
        "voices",
        nargs="*",
        help="Voice names to generate (default: all)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean and regenerate all files",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available voices",
    )
    parser.add_argument(
        "--language",
        default="en",
        help="Language code (default: en)",
    )

    args = parser.parse_args()

    # Load configuration
    config_path = Path("config/speech.yaml")
    if not config_path.exists():
        print(f"Error: Configuration file not found: {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    # List voices if requested
    if args.list:
        list_voices(config)
        return 0

    # Determine platform
    platform_type = detect_platform()
    print(f"Platform: {platform_type}")
    print(f"FFmpeg available: {check_ffmpeg()}")

    # Get voices to generate
    if args.voices:
        voices_to_generate = args.voices
        # Validate voice names
        for voice in voices_to_generate:
            if voice not in config["voices"]:
                print(f"Error: Unknown voice '{voice}'")
                print(f"Available: {', '.join(config['voices'].keys())}")
                sys.exit(1)
    else:
        voices_to_generate = list(config["voices"].keys())

    # Base output directory
    base_dir = Path("data/speech") / args.language
    base_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nGenerating speech files for: {', '.join(voices_to_generate)}")
    print(f"Output directory: {base_dir}")
    print(f"Mode: {'CLEAN (regenerate all)' if args.clean else 'INCREMENTAL (skip existing)'}")

    # Generate for each voice
    total_generated = 0
    for voice_name in voices_to_generate:
        voice_config = config["voices"][voice_name]
        generated = generate_voice_messages(
            voice_name,
            voice_config,
            config["messages"],
            base_dir,
            force=args.clean,
        )
        total_generated += generated

    print(f"\n{'=' * 80}")
    print(f"Generation complete! Total files generated: {total_generated}")
    print(f"Output location: {base_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

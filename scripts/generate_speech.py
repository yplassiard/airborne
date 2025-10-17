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


def generate_with_say_batch(items, voice_name, rate, batch_size=8):
    """Generate speech using macOS 'say' command in batches.

    Args:
        items: List of (text, output_path) tuples
        voice_name: macOS voice name (e.g., "Oliver", "Samantha")
        rate: Words per minute
        batch_size: Number of files to process simultaneously
    """
    import concurrent.futures
    import tempfile

    # Process in batches
    for i in range(0, len(items), batch_size):
        batch = items[i : i + batch_size]

        # Step 1: Generate all AIFFs in parallel
        temp_paths = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = []
            for text, output_path in batch:
                temp_path = output_path.with_suffix(".aiff")
                temp_paths.append((temp_path, output_path))
                cmd = ["say", "-v", voice_name, "-r", str(rate), "-o", str(temp_path), text]
                future = executor.submit(subprocess.run, cmd, capture_output=True, check=True)
                futures.append(future)

            # Wait for all to complete
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"    Error generating AIFF: {e}")

        # Step 2: Convert all AIFFs to MP3 in parallel with ffmpeg
        if check_ffmpeg():
            with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
                futures = []
                for temp_path, output_path in temp_paths:
                    if temp_path.exists():
                        cmd = [
                            "ffmpeg",
                            "-i",
                            str(temp_path),
                            "-af",
                            "silenceremove=start_periods=1:start_duration=0:start_threshold=-40dB:stop_periods=-1:stop_duration=0.1:stop_threshold=-40dB,areverse,silenceremove=start_periods=1:start_duration=0:start_threshold=-40dB:stop_periods=-1:stop_duration=0.1:stop_threshold=-40dB,areverse",
                            "-y",
                            str(output_path),
                        ]
                        future = executor.submit(subprocess.run, cmd, capture_output=True, check=True)
                        futures.append((future, temp_path))

                # Wait for all conversions and cleanup
                for future, temp_path in futures:
                    try:
                        future.result()
                        if temp_path.exists():
                            temp_path.unlink()
                    except Exception as e:
                        print(f"    Error converting to MP3: {e}")
        else:
            # No ffmpeg, just rename
            for temp_path, output_path in temp_paths:
                if temp_path.exists():
                    temp_path.rename(output_path.with_suffix(".aiff"))
            print("    Warning: ffmpeg not available, kept as AIFF")


def generate_with_say(text, output_path, voice_name, rate):
    """Generate speech using macOS 'say' command (single file - legacy).

    Args:
        text: Text to speak
        output_path: Output MP3 file path
        voice_name: macOS voice name (e.g., "Oliver", "Samantha")
        rate: Words per minute
    """
    generate_with_say_batch([(text, output_path)], voice_name, rate, batch_size=1)


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
    output_path = output_dir / f"{message_key}.wav"

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


def extract_panel_controls(panel_dir):
    """Extract all panel names and control names from panel files.

    Args:
        panel_dir: Path to panels directory

    Returns:
        Tuple of (panel_names_set, control_names_set, control_states_dict)
    """
    panel_names = set()
    control_names = set()
    control_states = {}  # control_name -> set of states

    panel_path = Path(panel_dir)
    if not panel_path.exists():
        print(f"Warning: Panel directory not found: {panel_dir}")
        return panel_names, control_names, control_states

    for yaml_file in panel_path.glob("*.yaml"):
        try:
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
                for panel in data.get("panels", []):
                    panel_names.add(panel["name"])
                    for control in panel.get("controls", []):
                        control_name = control["name"]
                        control_names.add(control_name)

                        # Collect states for this control
                        if control_name not in control_states:
                            control_states[control_name] = set()

                        states = control.get("states", [])
                        for state in states:
                            control_states[control_name].add(str(state))
        except Exception as e:
            print(f"Warning: Failed to parse {yaml_file}: {e}")

    return panel_names, control_names, control_states


def extract_atc_messages(atc_config_file):
    """Extract ATC messages from atc_en.yaml config.

    Args:
        atc_config_file: Path to ATC configuration file (e.g., config/atc_en.yaml)

    Returns:
        Dict of filename -> message text
    """
    messages = {}

    config_path = Path(atc_config_file)
    if not config_path.exists():
        print(f"Warning: ATC config not found: {atc_config_file}")
        return messages

    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)
            # messages: dict of MESSAGE_KEY -> "filename_without_extension"
            # We need to extract the actual text from the message key
            for msg_key, filename_base in data.get("messages", {}).items():
                # Convert message key to readable text
                # E.g., "ATC_TOWER_CLEARED_TAKEOFF_31" -> "Runway three one, cleared for takeoff"
                text = convert_atc_key_to_text(msg_key)
                messages[filename_base] = text
    except Exception as e:
        print(f"Warning: Failed to parse {atc_config_file}: {e}")

    return messages


def convert_atc_key_to_text(msg_key):
    """Convert ATC message key to readable text.

    Args:
        msg_key: Message key (e.g., "ATC_TOWER_CLEARED_TAKEOFF_31")

    Returns:
        Readable text for TTS
    """
    # Manual mapping of common ATC phrases
    text_map = {
        "ATC_TOWER_CLEARED_TAKEOFF_31": "Runway three one, cleared for takeoff",
        "ATC_TOWER_CLEARED_TAKEOFF_13": "Runway one three, cleared for takeoff",
        "ATC_TOWER_CLEARED_LAND_31": "Runway three one, cleared to land",
        "ATC_TOWER_CLEARED_LAND_13": "Runway one three, cleared to land",
        "ATC_TOWER_CONTACT_DEPARTURE": "Contact departure on one two five point three five",
        "ATC_TOWER_LINEUP_WAIT_31": "Runway three one, line up and wait",
        "ATC_TOWER_LINEUP_WAIT_13": "Runway one three, line up and wait",
        "ATC_TOWER_WIND_CHECK": "Wind three one zero at eight",
        "ATC_GROUND_TAXI_RWY_31": "Taxi to runway three one via alpha",
        "ATC_GROUND_TAXI_RWY_13": "Taxi to runway one three via bravo",
        "ATC_GROUND_CONTACT_TOWER_120_5": "Contact tower on one two zero point five",
        "ATC_GROUND_GOOD_MORNING": "Good morning",
        "ATC_GROUND_GOOD_AFTERNOON": "Good afternoon",
        "ATC_GROUND_GOOD_EVENING": "Good evening",
    }

    return text_map.get(msg_key, msg_key.replace("_", " ").lower())


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

    # Collect all items to generate
    items_to_generate = []

    # Collect configured messages
    for msg_key, msg_config in messages.items():
        if msg_config.get("voice") == voice_name:
            # Use explicit filename from config, fallback to msg_key
            filename_base = msg_config.get("filename", msg_key)
            print(f"  {msg_key}: '{msg_config['text']}' -> {filename_base}.wav")
            output_path = output_dir / f"{filename_base}.wav"
            if output_path.exists() and not force:
                skipped += 1
            else:
                items_to_generate.append((msg_config["text"], output_path))
                generated += 1

    # Collect checklist challenges and responses (only for pilot voice)
    if voice_name == "pilot":
        print("\n  Extracting checklist challenges and responses...")
        challenges, responses = extract_checklist_items("config/checklists")
        print(f"  Found {len(challenges)} challenges, {len(responses)} responses")

        for challenge in sorted(challenges):
            msg_key = "MSG_CHALLENGE_" + sanitize_filename(challenge)
            print(f"  {msg_key}: '{challenge}'")
            output_path = output_dir / f"{msg_key}.wav"
            if output_path.exists() and not force:
                skipped += 1
            else:
                items_to_generate.append((challenge, output_path))
                generated += 1

        for response in sorted(responses):
            msg_key = "MSG_RESPONSE_" + sanitize_filename(response)
            print(f"  {msg_key}: '{response}'")
            output_path = output_dir / f"{msg_key}.wav"
            if output_path.exists() and not force:
                skipped += 1
            else:
                items_to_generate.append((response, output_path))
                generated += 1

    # Collect panel and control names (only for cockpit voice)
    if voice_name == "cockpit":
        print("\n  Extracting panel and control names...")
        panel_names, control_names, control_states = extract_panel_controls("config/panels")

        print(
            f"  Found {len(panel_names)} panels, {len(control_names)} controls, "
            f"{sum(len(states) for states in control_states.values())} states"
        )

        for panel_name in sorted(panel_names):
            msg_key = "MSG_PANEL_" + sanitize_filename(panel_name)
            print(f"  {msg_key}: '{panel_name}'")
            output_path = output_dir / f"{msg_key}.wav"
            if output_path.exists() and not force:
                skipped += 1
            else:
                items_to_generate.append((panel_name, output_path))
                generated += 1

        for control_name in sorted(control_names):
            msg_key = "MSG_CONTROL_" + sanitize_filename(control_name)
            print(f"  {msg_key}: '{control_name}'")
            output_path = output_dir / f"{msg_key}.wav"
            if output_path.exists() and not force:
                skipped += 1
            else:
                items_to_generate.append((control_name, output_path))
                generated += 1

        for control_name in sorted(control_states.keys()):
            for state in sorted(control_states[control_name]):
                msg_key = "MSG_STATE_" + sanitize_filename(state)
                print(f"  {msg_key}: '{state}'")
                output_path = output_dir / f"{msg_key}.wav"
                if output_path.exists() and not force:
                    skipped += 1
                else:
                    items_to_generate.append((state, output_path))
                    generated += 1

    # Batch generate all collected items
    if items_to_generate:
        platform_type = detect_platform()
        engine = voice_config.get("engine", "say")
        if platform_type == "macos" and engine == "say":
            print(f"\n  Batch generating {len(items_to_generate)} files...")
            generate_with_say_batch(
                items_to_generate, voice_config["voice_name"], voice_config["rate"], batch_size=8
            )
        else:
            # pyttsx3 doesn't benefit from batching, process normally
            for text, output_path in items_to_generate:
                try:
                    generate_with_pyttsx3(
                        text, output_path, voice_config.get("voice_name", "default"), voice_config["rate"]
                    )
                except Exception as e:
                    print(f"    Error: {e}")

    print(f"  Generated: {generated}, Skipped: {skipped}")
    return generated


def generate_atc_messages(language, base_dir, force=False):
    """Generate ATC messages from atc_en.yaml.

    Args:
        language: Language code (e.g., "en")
        base_dir: Base output directory (e.g., data/speech/en)
        force: If True, regenerate existing files

    Returns:
        Number of files generated
    """
    # Load ATC configuration
    atc_config_file = f"config/atc_{language}.yaml"
    messages = extract_atc_messages(atc_config_file)

    if not messages:
        print(f"\nNo ATC messages found in {atc_config_file}")
        return 0

    print("\nATC Messages (Evan @ 180 WPM):")
    print(f"  Output: {base_dir}")
    print(f"  Found {len(messages)} ATC messages")

    # Use Evan voice at 180 WPM for ATC
    voice_config = {
        "engine": "say",
        "voice_name": "Evan",
        "rate": 180,
    }

    generated = 0
    skipped = 0

    for filename_base, text in sorted(messages.items()):
        print(f"  {filename_base}: '{text}'")
        if generate_speech_file(filename_base, text, voice_config, base_dir, force):
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

    # Generate ATC messages (flat structure in base_dir)
    atc_generated = generate_atc_messages(args.language, base_dir, force=args.clean)
    total_generated += atc_generated

    print(f"\n{'=' * 80}")
    print(f"Generation complete! Total files generated: {total_generated}")
    print(f"Output location: {base_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

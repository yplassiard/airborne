#!/usr/bin/env python3
"""Universal TTS generation script for AirBorne.

Generates speech files for all voice types using the unified config/speech.yaml configuration.
Supports:
- kokoro: Kokoro ONNX TTS (high-quality, local, multilingual)
- say: macOS native 'say' command
- pyttsx3: Windows/Linux TTS library

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


def check_kokoro():
    """Check if Kokoro TTS is available.

    Returns:
        Tuple of (available: bool, message: str)
    """
    try:
        from pathlib import Path

        import kokoro_onnx  # noqa: F401

        # Check if model files exist
        model_path = Path("assets/models/kokoro-v1.0.onnx")
        voices_path = Path("assets/models/voices-v1.0.bin")

        if not model_path.exists():
            return False, f"Model file not found: {model_path}"
        if not voices_path.exists():
            return False, f"Voices file not found: {voices_path}"

        return True, "Kokoro TTS available"
    except ImportError:
        return False, "kokoro-onnx not installed (run: ./scripts/install_kokoro.sh)"


# Global Kokoro instance (initialized once, reused for all generations)
_kokoro_instance = None


def get_kokoro_instance():
    """Get or create the global Kokoro instance.

    Returns:
        Kokoro instance or None if not available
    """
    global _kokoro_instance

    if _kokoro_instance is None:
        available, msg = check_kokoro()
        if not available:
            print(f"Warning: Kokoro not available - {msg}")
            return None

        try:
            from kokoro_onnx import Kokoro

            print("Initializing Kokoro TTS...")
            _kokoro_instance = Kokoro(
                model_path="assets/models/kokoro-v1.0.onnx",
                voices_path="assets/models/voices-v1.0.bin",
            )
            print("✓ Kokoro initialized")
        except Exception as e:
            print(f"Error initializing Kokoro: {e}")
            return None

    return _kokoro_instance


def wpm_to_speed(wpm):
    """Convert words-per-minute to Kokoro speed multiplier.

    Args:
        wpm: Words per minute (typical range: 140-220)

    Returns:
        Speed multiplier (0.5-2.0)
    """
    # Typical speech rate is ~180 WPM, map this to 1.0
    # 180 WPM = 1.0x speed
    # 90 WPM = 0.5x speed (slowest)
    # 360 WPM = 2.0x speed (fastest)
    return max(0.5, min(2.0, wpm / 180.0))


def generate_with_kokoro_batch(items, voice_name, language, rate):
    """Generate speech using Kokoro TTS in batches.

    Args:
        items: List of (text, output_path) tuples
        voice_name: Kokoro voice name (e.g., "af_bella", "am_adam")
        language: Language code (e.g., "en-us", "fr-fr")
        rate: Words per minute (converted to speed multiplier)
    """
    import soundfile as sf

    kokoro = get_kokoro_instance()
    if kokoro is None:
        print("Error: Kokoro not available")
        return

    speed = wpm_to_speed(rate)

    for text, output_path in items:
        try:
            # Generate audio with Kokoro
            samples, sample_rate = kokoro.create(text, voice=voice_name, lang=language, speed=speed)

            # Save as WAV file
            sf.write(str(output_path), samples, sample_rate)

        except Exception as e:
            print(f"    Error generating with Kokoro: {e}")


def generate_with_kokoro(text, output_path, voice_name, language, rate):
    """Generate speech using Kokoro TTS (single file - legacy).

    Args:
        text: Text to speak
        output_path: Output WAV file path
        voice_name: Kokoro voice name (e.g., "af_bella", "am_adam")
        language: Language code (e.g., "en-us", "fr-fr")
        rate: Words per minute (converted to speed multiplier)
    """
    generate_with_kokoro_batch([(text, output_path)], voice_name, language, rate)


def generate_with_say_batch(items, voice_name, rate, batch_size=8):
    """Generate speech using macOS 'say' command in batches.

    Args:
        items: List of (text, output_path) tuples
        voice_name: macOS voice name (e.g., "Oliver", "Samantha")
        rate: Words per minute
        batch_size: Number of files to process simultaneously
    """
    import concurrent.futures

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
                        future = executor.submit(
                            subprocess.run, cmd, capture_output=True, check=True
                        )
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


def generate_speech_file(
    message_key, text, voice_config, output_dir, language="en-us", force=False
):
    """Generate a single speech file.

    Args:
        message_key: Message key (e.g., MSG_STARTUP)
        text: Text to speak
        voice_config: Voice configuration dict
        output_dir: Output directory path
        language: Language code (e.g., "en-us", "fr-fr")
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
        if engine == "kokoro":
            generate_with_kokoro(
                text,
                output_path,
                voice_config["voice_name"],
                voice_config.get("language", language),
                voice_config["rate"],
            )
        elif platform_type == "macos" and engine == "say":
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
        .replace("(", "")
        .replace(")", "")
        .replace("<", "_")
        .replace(">", "_")
        .replace(":", "_")
        .replace("?", "_")
    )


def number_to_words(num):
    """Convert number to natural English words.

    Args:
        num: Number to convert (0-1000)

    Returns:
        String representation in words (e.g., 150 -> "one hundred fifty")
    """
    if num == 0:
        return "zero"

    if num < 0 or num > 1000:
        return str(num)

    # Special case for 1000
    if num == 1000:
        return "one thousand"

    ones = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
    teens = [
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
    ]
    tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

    result = []

    # Hundreds place
    if num >= 100:
        hundreds_digit = num // 100
        result.append(ones[hundreds_digit])
        result.append("hundred")
        num = num % 100

    # Tens and ones places
    if num >= 20:
        tens_digit = num // 10
        result.append(tens[tens_digit])
        num = num % 10
        if num > 0:
            result.append(ones[num])
    elif num >= 10:
        result.append(teens[num - 10])
    elif num > 0:
        result.append(ones[num])

    return " ".join(result)


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

    # Generate numbers 0-100 for pilot, ground, tower, approach voices (digit-based)
    if voice_name in ["pilot", "ground", "tower", "approach"]:
        print(f"\n  Generating numbers 0-100 for {voice_name} voice...")
        for num in range(0, 101):
            output_path = output_dir / f"MSG_NUMBER_{num}.wav"
            if output_path.exists() and not force:
                skipped += 1
            else:
                items_to_generate.append((str(num), output_path))
                generated += 1
        print("  Added 101 MSG_NUMBER files to generation queue")

    # Generate numbers 0-1000 for cockpit voice (natural number pronunciation with _autogen suffix)
    if voice_name == "cockpit":
        print("\n  Generating numbers 0-1000 for cockpit voice (natural pronunciation)...")
        for num in range(0, 1001):
            output_path = output_dir / f"number_{num}_autogen.wav"
            if output_path.exists() and not force:
                skipped += 1
            else:
                # Convert number to natural speech (e.g., 150 -> "one hundred fifty")
                text = number_to_words(num)
                items_to_generate.append((text, output_path))
                generated += 1
        print("  Added 1001 number files (0-1000) with natural pronunciation to generation queue")

    # Batch generate all collected items
    if items_to_generate:
        platform_type = detect_platform()
        engine = voice_config.get("engine", "say")
        language = voice_config.get("language", "en-us")

        if engine == "kokoro":
            print(f"\n  Batch generating {len(items_to_generate)} files with Kokoro...")
            generate_with_kokoro_batch(
                items_to_generate, voice_config["voice_name"], language, voice_config["rate"]
            )
        elif platform_type == "macos" and engine == "say":
            print(f"\n  Batch generating {len(items_to_generate)} files with macOS say...")
            generate_with_say_batch(
                items_to_generate, voice_config["voice_name"], voice_config["rate"], batch_size=8
            )
        else:
            # pyttsx3 doesn't benefit from batching, process normally
            print(f"\n  Generating {len(items_to_generate)} files with pyttsx3...")
            for text, output_path in items_to_generate:
                try:
                    generate_with_pyttsx3(
                        text,
                        output_path,
                        voice_config.get("voice_name", "default"),
                        voice_config["rate"],
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
        print(f"  Rate: {voice_config['rate']} WPM", end="")
        if voice_config["engine"] == "kokoro":
            speed = wpm_to_speed(voice_config["rate"])
            print(f" (Kokoro speed: {speed:.2f}x)")
        else:
            print()
        if "language" in voice_config:
            print(f"  Language: {voice_config['language']}")
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

    # Determine platform and available TTS engines
    platform_type = detect_platform()
    kokoro_available, kokoro_msg = check_kokoro()

    print(f"Platform: {platform_type}")
    print(f"FFmpeg available: {check_ffmpeg()}")
    print(f"Kokoro TTS: {'✓ Available' if kokoro_available else '✗ ' + kokoro_msg}")

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

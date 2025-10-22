#!/usr/bin/env python3
"""
Kokoro TTS Voice Sampler

Generates audio samples of all 19 English voices for easy comparison.
Useful for selecting voices for different characters in the flight simulator.
"""

import time
import soundfile as sf
from pathlib import Path
from kokoro_onnx import Kokoro


# All available English voices
FEMALE_VOICES = [
    'af_alloy',
    'af_aoede',
    'af_bella',
    'af_heart',
    'af_jessica',
    'af_kore',
    'af_nicole',
    'af_nova',
    'af_river',
    'af_sarah',
    'af_sky',
]

MALE_VOICES = [
    'am_adam',
    'am_echo',
    'am_eric',
    'am_fenrir',
    'am_liam',
    'am_michael',
    'am_onyx',
    'am_puck',
]

# Sample texts for different use cases
SAMPLE_TEXTS = {
    'pilot': "Palo Alto Tower, Cessna one two three alpha bravo, ready for departure runway three one.",
    'atc': "Cessna three alpha bravo, runway three one, wind three one zero at eight, cleared for takeoff.",
    'atis': "Palo Alto Airport information Alpha. Wind three one zero at eight knots. Altimeter three zero one seven. Runway three one in use.",
    'cockpit': "Airspeed eighty knots. Altitude two thousand feet. Heading three three zero.",
}


def generate_voice_samples(output_dir: Path, sample_type: str = 'pilot'):
    """Generate samples of all voices."""
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"Kokoro TTS Voice Sampler")
    print(f"{'='*60}\n")

    print(f"Sample type: {sample_type}")
    print(f"Text: '{SAMPLE_TEXTS[sample_type]}'\n")

    # Initialize Kokoro
    print("Initializing Kokoro...")
    start = time.time()
    kokoro = Kokoro(
        model_path="assets/models/kokoro-v1.0.onnx",
        voices_path="assets/models/voices-v1.0.bin"
    )
    print(f"✓ Initialized in {time.time() - start:.2f}s\n")

    text = SAMPLE_TEXTS[sample_type]
    total_time = 0
    total_audio = 0

    # Generate female voices
    print(f"{'Female Voices':-^60}\n")
    for voice in FEMALE_VOICES:
        start = time.time()
        samples, sample_rate = kokoro.create(text, voice=voice, lang='en-us')
        gen_time = time.time() - start
        audio_duration = len(samples) / sample_rate

        output_file = output_dir / f"{voice}.wav"
        sf.write(str(output_file), samples, sample_rate)

        print(f"  {voice:12} - {gen_time:4.2f}s ({audio_duration:.1f}s audio, "
              f"{audio_duration/gen_time:.1f}x realtime)")

        total_time += gen_time
        total_audio += audio_duration

    # Generate male voices
    print(f"\n{'Male Voices':-^60}\n")
    for voice in MALE_VOICES:
        start = time.time()
        samples, sample_rate = kokoro.create(text, voice=voice, lang='en-us')
        gen_time = time.time() - start
        audio_duration = len(samples) / sample_rate

        output_file = output_dir / f"{voice}.wav"
        sf.write(str(output_file), samples, sample_rate)

        print(f"  {voice:12} - {gen_time:4.2f}s ({audio_duration:.1f}s audio, "
              f"{audio_duration/gen_time:.1f}x realtime)")

        total_time += gen_time
        total_audio += audio_duration

    # Summary
    avg_speed = total_audio / total_time
    print(f"\n{'Summary':-^60}\n")
    print(f"  Voices generated: {len(FEMALE_VOICES) + len(MALE_VOICES)}")
    print(f"  Total generation time: {total_time:.1f}s")
    print(f"  Total audio duration: {total_audio:.1f}s")
    print(f"  Average speed: {avg_speed:.1f}x realtime")
    print(f"  Output directory: {output_dir}")
    print(f"\n  Listen with: afplay {output_dir}/<voice>.wav")
    print(f"  Or open directory: open {output_dir}")
    print()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Generate voice samples for all Kokoro voices',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Sample types:
  pilot   - Radio transmission from pilot
  atc     - ATC controller clearance
  atis    - Automated weather broadcast
  cockpit - Instrument readout

Examples:
  # Generate pilot samples
  uv run python scripts/sample_voices.py

  # Generate ATC samples
  uv run python scripts/sample_voices.py --type atc

  # Custom output directory
  uv run python scripts/sample_voices.py --output /tmp/voice_samples
        """
    )

    parser.add_argument(
        '--type',
        choices=['pilot', 'atc', 'atis', 'cockpit'],
        default='pilot',
        help='Type of sample text to use (default: pilot)'
    )

    parser.add_argument(
        '--output',
        type=Path,
        default=Path('/tmp/kokoro_voice_samples'),
        help='Output directory for samples (default: /tmp/kokoro_voice_samples)'
    )

    args = parser.parse_args()

    try:
        generate_voice_samples(args.output, args.type)
        print("✓ SUCCESS!\n")
    except FileNotFoundError as e:
        print(f"\n✗ Error: {e}")
        print("\nMake sure you've run: ./scripts/install_kokoro.sh")
        print("to download the model files.\n")
        return 1
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    exit(main())

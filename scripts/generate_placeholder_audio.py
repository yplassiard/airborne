#!/usr/bin/env python3
"""Generate placeholder audio files for testing.

Creates simple sine wave audio files for engine sounds, environment, and cues.
These are minimal placeholders to enable audio system testing.
"""

import math
import struct
import wave
from pathlib import Path


def generate_sine_wave(
    filename: str, frequency: float, duration: float, sample_rate: int = 44100
) -> None:
    """Generate a sine wave audio file.

    Args:
        filename: Output WAV file path
        frequency: Frequency in Hz
        duration: Duration in seconds
        sample_rate: Sample rate in Hz (default 44100)
    """
    num_samples = int(sample_rate * duration)

    # Generate sine wave samples
    samples = []
    for i in range(num_samples):
        # Calculate sine wave value
        value = math.sin(2.0 * math.pi * frequency * i / sample_rate)
        # Convert to 16-bit integer
        samples.append(int(value * 32767))

    # Write WAV file
    with wave.open(filename, "w") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 2 bytes (16-bit)
        wav_file.setframerate(sample_rate)

        # Pack samples as binary data
        packed_samples = struct.pack("h" * len(samples), *samples)
        wav_file.writeframes(packed_samples)

    print(f"Generated: {filename}")


def generate_fade_sine_wave(
    filename: str,
    frequency: float,
    duration: float,
    fade_in: float = 0.1,
    fade_out: float = 0.1,
    sample_rate: int = 44100,
) -> None:
    """Generate a sine wave with fade in/out.

    Args:
        filename: Output WAV file path
        frequency: Frequency in Hz
        duration: Duration in seconds
        fade_in: Fade in duration in seconds
        fade_out: Fade out duration in seconds
        sample_rate: Sample rate in Hz
    """
    num_samples = int(sample_rate * duration)
    fade_in_samples = int(sample_rate * fade_in)
    fade_out_samples = int(sample_rate * fade_out)

    samples = []
    for i in range(num_samples):
        # Calculate amplitude envelope
        amplitude = 1.0
        if i < fade_in_samples:
            # Fade in
            amplitude = i / fade_in_samples
        elif i > num_samples - fade_out_samples:
            # Fade out
            amplitude = (num_samples - i) / fade_out_samples

        # Generate sine wave with envelope
        value = amplitude * math.sin(2.0 * math.pi * frequency * i / sample_rate)
        samples.append(int(value * 32767))

    with wave.open(filename, "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        packed_samples = struct.pack("h" * len(samples), *samples)
        wav_file.writeframes(packed_samples)

    print(f"Generated: {filename}")


def main() -> None:
    """Generate all placeholder audio files."""
    # Create directories
    base_dir = Path("data/sounds")
    engines_dir = base_dir / "engines"
    environment_dir = base_dir / "environment"
    cues_dir = base_dir / "cues"

    engines_dir.mkdir(parents=True, exist_ok=True)
    environment_dir.mkdir(parents=True, exist_ok=True)
    cues_dir.mkdir(parents=True, exist_ok=True)

    print("Generating placeholder audio files...")
    print()

    # Engine sounds (different frequencies for different RPMs)
    print("Engine sounds:")
    generate_sine_wave(str(engines_dir / "piston_idle.wav"), 80.0, 2.0)
    generate_sine_wave(str(engines_dir / "piston_cruise.wav"), 120.0, 2.0)
    generate_sine_wave(str(engines_dir / "piston_full.wav"), 180.0, 2.0)
    generate_fade_sine_wave(str(engines_dir / "piston_start.wav"), 60.0, 3.0)
    generate_fade_sine_wave(str(engines_dir / "piston_shutdown.wav"), 100.0, 2.0)
    print()

    # Environment sounds
    print("Environment sounds:")
    generate_sine_wave(str(environment_dir / "wind_light.wav"), 200.0, 3.0)
    generate_sine_wave(str(environment_dir / "wind_moderate.wav"), 150.0, 3.0)
    generate_sine_wave(str(environment_dir / "wind_strong.wav"), 100.0, 3.0)
    generate_sine_wave(str(environment_dir / "ground_roll.wav"), 50.0, 2.0)
    generate_sine_wave(str(environment_dir / "touchdown.wav"), 40.0, 1.0)
    print()

    # UI/Cue sounds
    print("UI/Cue sounds:")
    generate_fade_sine_wave(str(cues_dir / "beep_high.wav"), 800.0, 0.2, 0.01, 0.05)
    generate_fade_sine_wave(str(cues_dir / "beep_low.wav"), 400.0, 0.2, 0.01, 0.05)
    generate_fade_sine_wave(str(cues_dir / "beep_warning.wav"), 600.0, 0.5, 0.05, 0.1)
    generate_fade_sine_wave(str(cues_dir / "beep_confirm.wav"), 1000.0, 0.15, 0.01, 0.05)
    generate_fade_sine_wave(str(cues_dir / "beep_error.wav"), 300.0, 0.3, 0.01, 0.05)
    generate_sine_wave(str(cues_dir / "proximity.wav"), 1200.0, 0.1)
    print()

    print("✅ All placeholder audio files generated successfully!")
    print(f"   Total files: {len(list(base_dir.rglob('*.wav')))}")
    print()
    print("Note: These are simple sine wave placeholders for testing.")
    print("      Replace with real audio samples for production.")


if __name__ == "__main__":
    main()

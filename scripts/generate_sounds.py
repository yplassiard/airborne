#!/usr/bin/env python3
"""Generate missing sound effects for AirBorne.

This script creates simple sound effects for:
- Switch/button clicks
- Knob rotations
- Rolling/tire sounds
"""

import math
import sys
import wave
from pathlib import Path

import numpy as np


def generate_click_sound(output_path: str, duration_ms: float = 50, frequency: float = 2000):
    """Generate a short click sound.

    Args:
        output_path: Path to save the WAV file
        duration_ms: Duration in milliseconds
        frequency: Base frequency in Hz
    """
    sample_rate = 44100
    duration_sec = duration_ms / 1000.0
    num_samples = int(sample_rate * duration_sec)

    # Generate a short burst with exponential decay
    t = np.linspace(0, duration_sec, num_samples)

    # Mix two frequencies for a richer click
    signal = np.sin(2 * np.pi * frequency * t) * 0.5 + np.sin(2 * np.pi * frequency * 1.5 * t) * 0.3

    # Apply exponential decay envelope
    envelope = np.exp(-t * 50)  # Fast decay
    signal = signal * envelope

    # Normalize to 16-bit range
    signal = np.int16(signal * 32767 * 0.5)  # 50% volume

    # Write WAV file
    with wave.open(output_path, "w") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(signal.tobytes())

    print(f"Generated: {output_path}")


def generate_knob_sound(output_path: str, duration_ms: float = 30, frequency: float = 800):
    """Generate a knob rotation sound.

    Args:
        output_path: Path to save the WAV file
        duration_ms: Duration in milliseconds
        frequency: Base frequency in Hz
    """
    sample_rate = 44100
    duration_sec = duration_ms / 1000.0
    num_samples = int(sample_rate * duration_sec)

    # Generate a soft mechanical sound
    t = np.linspace(0, duration_sec, num_samples)

    # Lower frequency for mechanical feel
    signal = np.sin(2 * np.pi * frequency * t)

    # Apply a smooth envelope
    envelope = np.sin(np.pi * t / duration_sec)  # Bell curve
    signal = signal * envelope

    # Normalize to 16-bit range
    signal = np.int16(signal * 32767 * 0.3)  # 30% volume (softer)

    # Write WAV file
    with wave.open(output_path, "w") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(signal.tobytes())

    print(f"Generated: {output_path}")


def generate_rolling_sound(output_path: str, duration_sec: float = 2.0):
    """Generate a tire rolling sound (loopable).

    Args:
        output_path: Path to save the WAV file
        duration_sec: Duration in seconds
    """
    sample_rate = 44100
    num_samples = int(sample_rate * duration_sec)

    # Generate white noise for tire texture
    np.random.seed(42)  # Reproducible
    noise = np.random.uniform(-1, 1, num_samples)

    # Filter to low frequency rumble (100-500 Hz)
    from scipy import signal as sp_signal

    # Bandpass filter
    sos = sp_signal.butter(4, [100, 500], btype="band", fs=sample_rate, output="sos")
    filtered = sp_signal.sosfilt(sos, noise)

    # Add periodic bumps for tire texture
    t = np.linspace(0, duration_sec, num_samples)
    bump_freq = 20  # Hz (20 bumps per second)
    bumps = np.sin(2 * np.pi * bump_freq * t) * 0.3

    # Combine filtered noise with bumps
    signal = filtered * 0.7 + bumps

    # Apply fade in/out for smooth looping
    fade_samples = int(sample_rate * 0.1)  # 100ms fade
    fade_in = np.linspace(0, 1, fade_samples)
    fade_out = np.linspace(1, 0, fade_samples)
    signal[:fade_samples] *= fade_in
    signal[-fade_samples:] *= fade_out

    # Normalize to 16-bit range
    signal = signal / np.max(np.abs(signal))  # Normalize
    signal = np.int16(signal * 32767 * 0.4)  # 40% volume

    # Write WAV file
    with wave.open(output_path, "w") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(signal.tobytes())

    print(f"Generated: {output_path}")


def main():
    """Generate all sound effects."""
    # Create output directory
    output_dir = Path("assets/sounds/aircraft")
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Generating sound effects...")

    # Generate switch clicks (various types)
    generate_click_sound(str(output_dir / "switch_on.wav"), duration_ms=50, frequency=2200)
    generate_click_sound(str(output_dir / "switch_off.wav"), duration_ms=50, frequency=1800)
    generate_click_sound(str(output_dir / "button_press.wav"), duration_ms=40, frequency=2500)

    # Generate knob sounds
    generate_knob_sound(str(output_dir / "knob_turn.wav"), duration_ms=30, frequency=700)

    # Generate rolling sound
    try:
        generate_rolling_sound(str(output_dir / "rolling.wav"), duration_sec=2.0)
    except ImportError:
        print("Warning: scipy not available, skipping rolling sound")
        print("Install scipy with: uv pip install scipy")
        # Generate simple alternative without scipy
        sample_rate = 44100
        duration_sec = 2.0
        num_samples = int(sample_rate * duration_sec)
        np.random.seed(42)
        noise = np.random.uniform(-1, 1, num_samples)
        # Simple lowpass (moving average)
        window_size = 100
        filtered = np.convolve(noise, np.ones(window_size) / window_size, mode="same")
        signal = filtered / np.max(np.abs(filtered))
        signal = np.int16(signal * 32767 * 0.4)

        with wave.open(str(output_dir / "rolling.wav"), "w") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(signal.tobytes())
        print(f"Generated (simple): {output_dir / 'rolling.wav'}")

    print("\nAll sound effects generated successfully!")
    print(f"Location: {output_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

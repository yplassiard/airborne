#!/usr/bin/env python3
"""Generate aviation radio static/white noise for ATC effect.

This script generates synthetic radio static that can be looped seamlessly.
The static is band-limited to match aviation VHF radio characteristics.
"""

import numpy as np
import struct
import wave
from pathlib import Path


def generate_bandlimited_noise(
    duration_sec: float,
    sample_rate: int = 22050,
    low_freq: float = 300.0,
    high_freq: float = 3400.0,
    seed: int = 42,
) -> np.ndarray:
    """Generate band-limited white noise for aviation radio effect.

    Args:
        duration_sec: Duration in seconds.
        sample_rate: Sample rate in Hz.
        low_freq: Low-pass filter frequency (Hz).
        high_freq: High-pass filter frequency (Hz).
        seed: Random seed for reproducibility.

    Returns:
        Numpy array of audio samples (float32, -1.0 to 1.0).
    """
    np.random.seed(seed)

    # Generate white noise
    num_samples = int(duration_sec * sample_rate)
    noise = np.random.uniform(-1.0, 1.0, num_samples).astype(np.float32)

    # Apply FFT for filtering
    fft = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(num_samples, 1.0 / sample_rate)

    # Create band-pass filter (aviation radio bandwidth)
    filter_mask = np.ones_like(freqs)
    filter_mask[freqs < low_freq] = 0.0  # High-pass
    filter_mask[freqs > high_freq] = 0.0  # Low-pass

    # Apply smooth roll-off at edges (to avoid harsh cutoffs)
    rolloff_width = 100.0  # Hz
    for i, f in enumerate(freqs):
        if low_freq - rolloff_width < f < low_freq:
            # Smooth rise
            filter_mask[i] = (f - (low_freq - rolloff_width)) / rolloff_width
        elif high_freq < f < high_freq + rolloff_width:
            # Smooth fall
            filter_mask[i] = 1.0 - (f - high_freq) / rolloff_width

    # Apply filter
    fft_filtered = fft * filter_mask

    # Convert back to time domain
    noise_filtered = np.fft.irfft(fft_filtered, n=num_samples)

    # Normalize to -1.0 to 1.0 range
    max_val = np.max(np.abs(noise_filtered))
    if max_val > 0:
        noise_filtered = noise_filtered / max_val

    return noise_filtered


def save_wav(filename: Path, audio: np.ndarray, sample_rate: int = 22050) -> None:
    """Save audio as 16-bit WAV file.

    Args:
        filename: Output WAV file path.
        audio: Audio samples (float32, -1.0 to 1.0).
        sample_rate: Sample rate in Hz.
    """
    # Convert float32 to int16
    audio_int16 = (audio * 32767).astype(np.int16)

    # Write WAV file
    with wave.open(str(filename), "w") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_int16.tobytes())

    print(f"✓ Saved: {filename} ({len(audio) / sample_rate:.1f}s, {sample_rate}Hz)")


def main():
    """Generate multiple radio static variations."""
    output_dir = Path("data/audio/effects")
    output_dir.mkdir(parents=True, exist_ok=True)

    sample_rate = 22050  # Match ATC speech sample rate

    print("Generating aviation radio static/white noise...\n")

    # 1. Subtle background static (loopable, 5 seconds)
    print("1. Generating subtle background static (loopable)...")
    static_subtle = generate_bandlimited_noise(
        duration_sec=5.0,
        sample_rate=sample_rate,
        low_freq=300.0,
        high_freq=3400.0,
        seed=42,
    )
    save_wav(output_dir / "radio_static_subtle.wav", static_subtle, sample_rate)

    # 2. Medium intensity static (loopable, 5 seconds)
    print("2. Generating medium intensity static (loopable)...")
    static_medium = generate_bandlimited_noise(
        duration_sec=5.0,
        sample_rate=sample_rate,
        low_freq=300.0,
        high_freq=3400.0,
        seed=123,
    )
    save_wav(output_dir / "radio_static_medium.wav", static_medium, sample_rate)

    # 3. Atmospheric crackle (short burst, 0.5 seconds)
    print("3. Generating atmospheric crackle...")
    crackle = generate_bandlimited_noise(
        duration_sec=0.5,
        sample_rate=sample_rate,
        low_freq=500.0,
        high_freq=3000.0,
        seed=456,
    )
    # Apply envelope for natural crackle sound
    envelope = np.exp(-np.linspace(0, 5, len(crackle)))
    crackle = crackle * envelope
    save_wav(output_dir / "radio_crackle.wav", crackle, sample_rate)

    # 4. Long background static (loopable, 10 seconds)
    print("4. Generating long background static (loopable)...")
    static_long = generate_bandlimited_noise(
        duration_sec=10.0,
        sample_rate=sample_rate,
        low_freq=300.0,
        high_freq=3400.0,
        seed=789,
    )
    save_wav(output_dir / "radio_static_long.wav", static_long, sample_rate)

    print("\n" + "=" * 60)
    print("RADIO STATIC GENERATION COMPLETE")
    print("=" * 60)
    print(f"\nGenerated 4 radio static files in: {output_dir}")
    print("\nFiles:")
    print("  1. radio_static_subtle.wav  - Subtle background static (5s, loopable)")
    print("  2. radio_static_medium.wav  - Medium intensity static (5s, loopable)")
    print("  3. radio_crackle.wav        - Short atmospheric crackle (0.5s)")
    print("  4. radio_static_long.wav    - Long background static (10s, loopable)")
    print("\nAll files are:")
    print("  - Band-limited to 300-3400 Hz (aviation radio bandwidth)")
    print("  - 22050 Hz sample rate (matches ATC speech)")
    print("  - 16-bit mono WAV format")
    print("  - Seamlessly loopable (except crackle)")


if __name__ == "__main__":
    main()

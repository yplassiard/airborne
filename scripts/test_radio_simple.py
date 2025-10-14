#!/usr/bin/env python3
"""Simple standalone test for radio effect.

This script tests the radio effect without importing the full airborne package.
"""

import random
import sys
import time
from pathlib import Path

try:
    import pyfmodex
    import yaml
except ImportError as e:
    print(f"Error: Missing dependency: {e}")
    print("Install with: uv add pyfmodex pyyaml")
    sys.exit(1)


def play_ptt_beep(system, frequency_hz, duration_ms, volume):
    """Play a PTT beep tone."""
    try:
        oscillator = system.create_dsp_by_type(pyfmodex.enums.DSP_TYPE.OSCILLATOR)
        oscillator.set_parameter_int(0, 0)  # Sine wave
        oscillator.set_parameter_float(1, frequency_hz)  # Frequency
        oscillator.set_parameter_float(2, volume)  # Volume

        channel = system.play_dsp(oscillator, paused=False)
        time.sleep(duration_ms / 1000.0)
        channel.stop()
        oscillator.release()
    except Exception as e:
        print(f"  Error playing PTT beep: {e}")


def play_crackle(system, duration_ms, volume):
    """Play a brief crackle/pop sound using white noise burst."""
    try:
        oscillator = system.create_dsp_by_type(pyfmodex.enums.DSP_TYPE.OSCILLATOR)
        oscillator.set_parameter_int(0, 5)  # White noise
        oscillator.set_parameter_float(1, volume)  # Volume

        channel = system.play_dsp(oscillator, paused=False)
        time.sleep(duration_ms / 1000.0)
        channel.stop()
        oscillator.release()
    except Exception:
        pass  # Silently fail for crackles


def test_radio_effect():
    """Test radio effect on an ATC message."""

    # Check files exist
    config_file = Path("config/radio_effects.yaml")
    atc_config_file = Path("config/atc_en.yaml")
    speech_dir = Path("data/atc/en")

    if not config_file.exists():
        print(f"Error: Radio effects config not found: {config_file}")
        sys.exit(1)

    if not atc_config_file.exists():
        print(f"Error: ATC config not found: {atc_config_file}")
        sys.exit(1)

    if not speech_dir.exists():
        print(f"Error: ATC speech directory not found: {speech_dir}")
        print("Run: python scripts/generate_atc_speech.py")
        sys.exit(1)

    # Load configs
    with open(config_file) as f:
        radio_config = yaml.safe_load(f).get("radio_effect", {})

    with open(atc_config_file) as f:
        atc_config = yaml.safe_load(f)

    # Initialize FMOD
    print("Initializing FMOD...")
    system = pyfmodex.System()
    system.init(maxchannels=32)
    print("✓ FMOD initialized\n")

    # Create DSP chain
    print("Creating radio effect DSP chain...")
    dsp_chain = []

    # High-pass filter
    if radio_config.get("highpass", {}).get("enabled", True):
        highpass = system.create_dsp_by_type(pyfmodex.enums.DSP_TYPE.HIGHPASS)
        cutoff = radio_config.get("highpass", {}).get("cutoff_hz", 300.0)
        highpass.set_parameter_float(0, cutoff)
        dsp_chain.append(("High-pass", highpass))
        print(f"  ✓ High-pass filter at {cutoff} Hz")

    # Low-pass filter
    if radio_config.get("lowpass", {}).get("enabled", True):
        lowpass = system.create_dsp_by_type(pyfmodex.enums.DSP_TYPE.LOWPASS)
        cutoff = radio_config.get("lowpass", {}).get("cutoff_hz", 3400.0)
        lowpass.set_parameter_float(0, cutoff)
        dsp_chain.append(("Low-pass", lowpass))
        print(f"  ✓ Low-pass filter at {cutoff} Hz")

    # Compressor
    if radio_config.get("compressor", {}).get("enabled", True):
        compressor = system.create_dsp_by_type(pyfmodex.enums.DSP_TYPE.COMPRESSOR)
        threshold = radio_config.get("compressor", {}).get("threshold_db", -20.0)
        ratio = radio_config.get("compressor", {}).get("ratio", 10.0)
        attack = radio_config.get("compressor", {}).get("attack_ms", 1.0)
        release = radio_config.get("compressor", {}).get("release_ms", 100.0)
        makeup_gain = radio_config.get("compressor", {}).get("makeup_gain_db", 6.0)

        compressor.set_parameter_float(0, threshold)
        compressor.set_parameter_float(1, ratio)
        compressor.set_parameter_float(2, attack)
        compressor.set_parameter_float(3, release)
        compressor.set_parameter_float(4, makeup_gain)  # Makeup gain
        dsp_chain.append(("Compressor", compressor))
        print(f"  ✓ Compressor: {ratio}:1 ratio, {threshold} dB threshold, +{makeup_gain}dB gain")

    # White noise (static)
    if radio_config.get("static_noise", {}).get("enabled", False):
        try:
            oscillator = system.create_dsp_by_type(pyfmodex.enums.DSP_TYPE.OSCILLATOR)
            oscillator.set_parameter_int(0, 5)  # White noise
            noise_level = radio_config.get("static_noise", {}).get("level", 0.08)
            oscillator.set_parameter_float(1, noise_level)
            dsp_chain.append(("White noise", oscillator))
            print(f"  ✓ White noise at {noise_level * 100:.0f}% mix")
        except Exception as e:
            print(f"  ✗ Could not add white noise: {e}")

    print(f"\n✓ Radio effect chain created ({len(dsp_chain)} DSP effects)\n")

    # Check PTT beeps configuration
    ptt_config = radio_config.get("ptt_beeps", {})
    if ptt_config.get("enabled", True):
        start_beep = ptt_config.get("start_beep", {})
        end_beep = ptt_config.get("end_beep", {})
        print("PTT beeps enabled:")
        print(
            f"  Start: {start_beep.get('frequency_hz', 1000)}Hz, {start_beep.get('duration_ms', 50)}ms"
        )
        print(f"  End: {end_beep.get('frequency_hz', 800)}Hz, {end_beep.get('duration_ms', 40)}ms")

    # Check crackles configuration
    crackles_config = radio_config.get("crackles", {})
    if crackles_config.get("enabled", False):
        freq = crackles_config.get("frequency", 0.3)
        duration = crackles_config.get("duration_ms", 20)
        vol = crackles_config.get("volume", 0.15)
        print("Random crackles enabled:")
        print(f"  Frequency: {freq}/sec, Duration: {duration}ms, Volume: {vol * 100:.0f}%")

    print()

    # Get test message
    message_key = "ATC_TOWER_CLEARED_TAKEOFF_31"
    messages = atc_config.get("messages", {})
    filename_base = messages.get(message_key)

    if not filename_base:
        print(f"Error: Message not found: {message_key}")
        sys.exit(1)

    file_ext = atc_config.get("file_extension", "mp3")
    audio_file = speech_dir / f"{filename_base}.{file_ext}"

    if not audio_file.exists():
        print(f"Error: Audio file not found: {audio_file}")
        sys.exit(1)

    print(f"Test message: {message_key}")
    print(f"Audio file: {audio_file}\n")

    # Play WITHOUT effect first
    print("=" * 60)
    print("PLAYING WITHOUT RADIO EFFECT")
    print("(Listen to clean, unprocessed audio)")
    print("=" * 60)

    sound = system.create_sound(str(audio_file), mode=pyfmodex.flags.MODE.DEFAULT)
    channel = sound.play()

    # Wait for playback to finish
    while channel.is_playing:
        system.update()
        time.sleep(0.016)

    print("\n✓ Finished\n")
    time.sleep(1.0)

    # Play WITH effect
    print("=" * 60)
    print("PLAYING WITH RADIO EFFECT + PTT BEEPS")
    print("(Listen for PTT beep, bandwidth limiting, compression, static)")
    print("=" * 60)

    # Play PTT start beep
    if ptt_config.get("enabled", True):
        start_beep = ptt_config.get("start_beep", {})
        if start_beep.get("enabled", True):
            freq = start_beep.get("frequency_hz", 1000.0)
            duration = start_beep.get("duration_ms", 50)
            vol = start_beep.get("volume", 0.3)
            print(f"[PTT START BEEP: {freq}Hz]")
            play_ptt_beep(system, freq, duration, vol)

    sound = system.create_sound(str(audio_file), mode=pyfmodex.flags.MODE.DEFAULT)
    channel = sound.play(paused=True)

    # Apply DSP chain
    for name, dsp in dsp_chain:
        channel.add_dsp(0, dsp)
        dsp.active = True

    # Start playback
    channel.paused = False

    # Wait for playback to finish with random crackles
    if crackles_config.get("enabled", False):
        crackle_freq = crackles_config.get("frequency", 0.3)
        crackle_duration = crackles_config.get("duration_ms", 20)
        crackle_volume = crackles_config.get("volume", 0.15)

        # Calculate time between crackles (average)
        avg_interval = 1.0 / crackle_freq if crackle_freq > 0 else 10.0
        next_crackle_time = time.time() + random.expovariate(1.0 / avg_interval)

        while channel.is_playing:
            system.update()

            # Check if it's time for a crackle
            current_time = time.time()
            if current_time >= next_crackle_time:
                play_crackle(system, crackle_duration, crackle_volume)
                # Schedule next crackle
                next_crackle_time = current_time + random.expovariate(1.0 / avg_interval)

            time.sleep(0.016)
    else:
        # No crackles, simple playback
        while channel.is_playing:
            system.update()
            time.sleep(0.016)

    # Play PTT end beep
    if ptt_config.get("enabled", True):
        end_beep = ptt_config.get("end_beep", {})
        if end_beep.get("enabled", True):
            freq = end_beep.get("frequency_hz", 800.0)
            duration = end_beep.get("duration_ms", 40)
            vol = end_beep.get("volume", 0.25)
            print(f"[PTT END BEEP: {freq}Hz]")
            play_ptt_beep(system, freq, duration, vol)

    print("\n✓ Finished\n")

    # Cleanup
    print("Shutting down...")
    for _, dsp in dsp_chain:
        dsp.release()
    sound.release()
    system.release()

    print("\n" + "=" * 60)
    print("RADIO EFFECT TEST COMPLETE")
    print("=" * 60)
    print("\nDid the radio effect sound realistic?")
    print("The effect should make the voice sound like aviation VHF AM radio:")
    print("  - Bandwidth limited (tinny, narrow frequency range)")
    print("  - Compressed (even volume, loud and consistent)")
    print("  - Similar to real ATC transmissions")


if __name__ == "__main__":
    test_radio_effect()

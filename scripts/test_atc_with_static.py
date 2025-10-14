#!/usr/bin/env python3
"""Test ATC audio with static layer integration.

This script tests the static layer with radio effect:
- Radio effect (bandwidth limiting, compression)
- Static layer (background noise)
- Pre-roll and post-roll timing
"""

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


def test_atc_with_static():
    """Test ATC audio with static layer."""

    # Check required files
    config_file = Path("config/radio_effects.yaml")
    atc_config_file = Path("config/atc_en.yaml")
    speech_dir = Path("data/atc/en")
    static_file = Path("data/audio/effects/radio_static_subtle.wav")

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

    if not static_file.exists():
        print(f"Error: Static layer file not found: {static_file}")
        print("Run: python scripts/generate_radio_static.py")
        sys.exit(1)

    print("=" * 60)
    print("ATC AUDIO WITH STATIC LAYER TEST")
    print("=" * 60)
    print()

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

    # Show static layer configuration
    static_config = radio_config.get("static_layer", {})
    if static_config.get("enabled", False):
        print("Static layer configuration:")
        print(f"  File: {static_config.get('file')}")
        print(f"  Volume: {static_config.get('volume', 0.15) * 100:.0f}%")
        print(f"  Pre-roll: {static_config.get('pre_roll', 0.2)}s")
        print(f"  Post-roll: {static_config.get('post_roll', 0.4)}s")

        ducking = static_config.get("ducking", {})
        if ducking.get("enabled", False):
            print(f"  Side-chain ducking:")
            print(f"    Threshold: {ducking.get('threshold_db', -40.0)} dB")
            print(f"    Ratio: {ducking.get('ratio', 4.0)}:1")
            print(f"    Attack: {ducking.get('attack_ms', 10.0)} ms")
            print(f"    Release: {ducking.get('release_ms', 200.0)} ms")
    else:
        print("⚠ Static layer is disabled")

    print()

    # Create DSP chain for voice
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
        compressor.set_parameter_float(4, makeup_gain)
        dsp_chain.append(("Compressor", compressor))
        print(f"  ✓ Compressor: {ratio}:1 ratio, {threshold} dB threshold, +{makeup_gain}dB gain")

    print(f"\n✓ Radio effect chain created ({len(dsp_chain)} DSP effects)\n")

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

    # Play with static layer
    print("=" * 60)
    print("PLAYING WITH STATIC LAYER + RADIO EFFECT")
    print("=" * 60)
    print("Listen for:")
    print("  1. Static layer starting 0.2s before voice")
    print("  2. Radio effect on voice (bandwidth limited, compressed)")
    print("  3. Static continuing 0.4s after voice ends")
    print("=" * 60)
    print()

    # Load static sound
    static_volume = static_config.get("volume", 0.15)
    static_sound = system.create_sound(
        str(static_file), mode=pyfmodex.flags.MODE.LOOP_NORMAL | pyfmodex.flags.MODE.DEFAULT
    )

    # Start static layer (pre-roll)
    static_channel = static_sound.play()
    static_channel.volume = static_volume
    print(f"[STATIC LAYER STARTED at {static_volume * 100:.0f}% volume]")
    time.sleep(0.2)  # Pre-roll

    # Load and play voice message
    voice_sound = system.create_sound(str(audio_file), mode=pyfmodex.flags.MODE.DEFAULT)
    voice_channel = voice_sound.play(paused=True)

    # Apply DSP chain to voice
    for name, dsp in dsp_chain:
        voice_channel.add_dsp(0, dsp)
        dsp.active = True

    # Start voice playback
    voice_channel.paused = False
    print(f"[VOICE MESSAGE STARTED]")

    # Wait for voice to finish
    while voice_channel.is_playing:
        system.update()
        time.sleep(0.016)

    print(f"[VOICE MESSAGE ENDED]")

    # Continue static for post-roll
    time.sleep(0.4)  # Post-roll

    # Stop static
    static_channel.stop()
    print(f"[STATIC LAYER STOPPED]")

    print("\n✓ Finished\n")

    # Cleanup
    print("Shutting down...")
    for _, dsp in dsp_chain:
        dsp.release()
    voice_sound.release()
    static_sound.release()
    system.release()

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    print()
    print("Did the static layer sound realistic?")
    print("You should have heard:")
    print("  ✓ Subtle static starting 0.2s before the voice")
    print("  ✓ Voice with radio effect (tinny, compressed)")
    print("  ✓ Static continuing 0.4s after voice ends")
    print("\nNote: Side-chain ducking is not implemented in this standalone test.")


if __name__ == "__main__":
    test_atc_with_static()

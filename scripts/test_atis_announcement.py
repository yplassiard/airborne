#!/usr/bin/env python3
"""Test ATIS announcement with radio effect and static layer.

This script tests a complete ATIS (Automatic Terminal Information Service)
announcement using pre-recorded messages played in sequence with radio
effect and background static.
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


def create_dsp_chain(system, radio_config):
    """Create radio effect DSP chain.

    Args:
        system: FMOD system instance.
        radio_config: Radio effect configuration dict.

    Returns:
        List of (name, dsp) tuples.
    """
    dsp_chain = []

    # High-pass filter
    if radio_config.get("highpass", {}).get("enabled", True):
        highpass = system.create_dsp_by_type(pyfmodex.enums.DSP_TYPE.HIGHPASS)
        cutoff = radio_config.get("highpass", {}).get("cutoff_hz", 300.0)
        highpass.set_parameter_float(0, cutoff)
        dsp_chain.append(("High-pass", highpass))

    # Low-pass filter
    if radio_config.get("lowpass", {}).get("enabled", True):
        lowpass = system.create_dsp_by_type(pyfmodex.enums.DSP_TYPE.LOWPASS)
        cutoff = radio_config.get("lowpass", {}).get("cutoff_hz", 3400.0)
        lowpass.set_parameter_float(0, cutoff)
        dsp_chain.append(("Low-pass", lowpass))

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

    return dsp_chain


def play_message_with_effect(system, audio_file, dsp_chain):
    """Play a single message with radio effect.

    Args:
        system: FMOD system instance.
        audio_file: Path to audio file.
        dsp_chain: List of DSP effects to apply.

    Returns:
        Duration in seconds that the message played.
    """
    sound = system.create_sound(str(audio_file), mode=pyfmodex.flags.MODE.DEFAULT)
    channel = sound.play(paused=True)

    # Apply DSP chain
    for name, dsp in dsp_chain:
        channel.add_dsp(0, dsp)
        dsp.active = True

    # Start playback
    channel.paused = False
    start_time = time.time()

    # Wait for playback to finish
    try:
        while channel.is_playing:
            system.update()
            time.sleep(0.016)
    except:
        # Channel became invalid (finished playing)
        pass

    duration = time.time() - start_time

    try:
        sound.release()
    except:
        pass

    return duration


def test_atis_announcement():
    """Test complete ATIS announcement."""

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

    # Load configs
    with open(config_file) as f:
        radio_config = yaml.safe_load(f).get("radio_effect", {})

    with open(atc_config_file) as f:
        atc_config = yaml.safe_load(f)

    # ATIS announcement sequence (typical format)
    # Format: "Airport information [letter], time [time], wind [wind],
    #          visibility [vis], ceiling [ceiling], temperature [temp],
    #          dewpoint [dewpoint], altimeter [alt], landing/departing runway [rwy],
    #          advise on contact you have information [letter]"
    atis_sequence = [
        "ATIS_AIRPORT_INFO",
        "ATIS_INFO_ALPHA",
        "ATIS_TIME",
        "ATIS_WIND",
        "ATIS_VISIBILITY",
        "ATIS_CEILING",
        "ATIS_TEMPERATURE",
        "ATIS_DEWPOINT",
        "ATIS_ALTIMETER",
        "ATIS_LANDING_RUNWAY",
        "ATIS_DEPARTING_RUNWAY",
        "ATIS_ADVISE_ON_CONTACT",
        "ATIS_INFO_ALPHA",
    ]

    print("=" * 60)
    print("ATIS ANNOUNCEMENT TEST")
    print("=" * 60)
    print()
    print("ATIS Sequence:")
    for i, key in enumerate(atis_sequence, 1):
        print(f"  {i}. {key}")
    print()

    # Initialize FMOD
    print("Initializing FMOD...")
    system = pyfmodex.System()
    system.init(maxchannels=32)
    print("✓ FMOD initialized\n")

    # Create DSP chain
    print("Creating radio effect DSP chain...")
    dsp_chain = create_dsp_chain(system, radio_config)
    for name, _ in dsp_chain:
        print(f"  ✓ {name}")
    print()

    # Get message mappings
    messages = atc_config.get("messages", {})
    file_ext = atc_config.get("file_extension", "mp3")

    # Verify all ATIS files exist
    missing_files = []
    for key in atis_sequence:
        filename_base = messages.get(key)
        if not filename_base:
            missing_files.append(key)
            continue
        audio_file = speech_dir / f"{filename_base}.{file_ext}"
        if not audio_file.exists():
            missing_files.append(f"{key} -> {audio_file}")

    if missing_files:
        print("Error: Missing ATIS files:")
        for f in missing_files:
            print(f"  - {f}")
        print("\nRun: python scripts/generate_atis_speech.py")
        sys.exit(1)

    # Show static layer config
    static_config = radio_config.get("static_layer", {})
    if static_config.get("enabled", False):
        print("Static layer:")
        print(f"  Volume: {static_config.get('volume', 0.15) * 100:.0f}%")
        print(f"  Pre-roll: {static_config.get('pre_roll', 0.2)}s")
        print(f"  Post-roll: {static_config.get('post_roll', 0.4)}s")
    print()

    # Play ATIS announcement
    print("=" * 60)
    print("PLAYING ATIS ANNOUNCEMENT")
    print("=" * 60)
    print()

    # Load and start static layer
    static_volume = static_config.get("volume", 0.15)
    static_sound = system.create_sound(
        str(static_file), mode=pyfmodex.flags.MODE.LOOP_NORMAL | pyfmodex.flags.MODE.DEFAULT
    )
    static_channel = static_sound.play()
    static_channel.volume = static_volume

    print(f"[STATIC LAYER STARTED at {static_volume * 100:.0f}% volume]")
    time.sleep(0.2)  # Pre-roll

    # Play each ATIS message in sequence
    total_duration = 0.0
    for i, key in enumerate(atis_sequence, 1):
        filename_base = messages.get(key)
        audio_file = speech_dir / f"{filename_base}.{file_ext}"

        print(f"[{i}/{len(atis_sequence)}] {key}...", end=" ", flush=True)
        duration = play_message_with_effect(system, audio_file, dsp_chain)
        total_duration += duration
        print(f"({duration:.1f}s)")

        # Small pause between messages for natural flow
        time.sleep(0.15)

    # Post-roll for static
    time.sleep(0.4)
    static_channel.stop()
    print("[STATIC LAYER STOPPED]")

    print()
    print(f"✓ ATIS announcement complete ({total_duration:.1f}s total)\n")

    # Cleanup
    print("Shutting down...")
    for _, dsp in dsp_chain:
        try:
            dsp.release()
        except:
            pass
    static_sound.release()
    system.release()

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    print()
    print("The ATIS announcement should sound like:")
    print("  ✓ Professional aviation radio transmission")
    print("  ✓ Continuous background static throughout")
    print("  ✓ Clear voice with radio effect (tinny, compressed)")
    print("  ✓ Seamless sequence of pre-recorded messages")
    print("  ✓ Realistic ATIS format with all required elements")


if __name__ == "__main__":
    test_atis_announcement()

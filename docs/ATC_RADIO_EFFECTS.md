# ATC Auto-Messaging with Radio Effects

## Overview

This document describes the design and implementation of the ATC auto-messaging system with real-time radio effect filtering using FMOD DSP.

## Goals

1. **Pre-defined ATC Messages**: Use pre-recorded speech files for ATC communications
2. **Radio Effect Filter**: Apply real-time radio effect (lo-fi, compressed, static) using FMOD DSP
3. **Realistic Communication**: Contextual ATC messages based on flight phase
4. **Separate Voice**: Different voice for ATC vs. cockpit TTS
5. **Push-to-Talk**: Player transmissions also get radio effect

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                     ATC Radio System                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────┐         ┌──────────────────┐          │
│  │ ATC Message     │────────>│  Radio Effect    │          │
│  │ Manager         │         │  DSP Chain       │          │
│  └─────────────────┘         └──────────────────┘          │
│         │                            │                      │
│         │                            │                      │
│         ▼                            ▼                      │
│  ┌─────────────────┐         ┌──────────────────┐          │
│  │ Speech Files    │         │  FMOD Engine     │          │
│  │ data/atc/       │         │  with DSP        │          │
│  └─────────────────┘         └──────────────────┘          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### File Structure

```
data/
  atc/
    en/
      *.mp3          # ATC voice speech files (different voice from cockpit)

config/
  atc_en.yaml       # ATC message mappings
  radio_effects.yaml # Radio effect DSP settings

src/airborne/audio/
  effects/
    __init__.py
    radio_filter.py  # Radio effect DSP implementation
  atc/
    __init__.py
    atc_audio.py     # ATC audio manager with radio effects
```

## Radio Effect Design

### DSP Chain

The radio effect consists of multiple DSP stages applied in sequence:

```
Input Audio
    │
    ▼
┌──────────────────┐
│ 1. High-Pass     │  Remove frequencies below 300 Hz
│    Filter        │  (typical radio cutoff)
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ 2. Low-Pass      │  Remove frequencies above 3400 Hz
│    Filter        │  (aviation radio bandwidth limit)
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ 3. Compression   │  Heavy compression (radio AGC)
│                  │  Ratio: 10:1, Attack: 1ms, Release: 100ms
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ 4. Distortion    │  Subtle clipping/saturation
│    (optional)    │  Drive: 1.2-1.5
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ 5. Static/Noise  │  Very low-level white noise
│    (optional)    │  Mix: 2-5%
└──────────────────┘
    │
    ▼
Output Audio (Radio Effect)
```

### FMOD DSP Implementation

FMOD provides built-in DSP effects that can be chained on channels:

- **FMOD_DSP_TYPE_HIGHPASS**: High-pass filter (remove low frequencies)
- **FMOD_DSP_TYPE_LOWPASS**: Low-pass filter (remove high frequencies)
- **FMOD_DSP_TYPE_COMPRESSOR**: Dynamic range compressor
- **FMOD_DSP_TYPE_DISTORTION**: Distortion/saturation
- **FMOD_DSP_TYPE_OSCILLATOR**: White noise generator (for static)

### Configuration (`config/radio_effects.yaml`)

```yaml
# Radio effect DSP settings for aviation communications
radio_effect:
  # High-pass filter (remove low rumble)
  highpass:
    enabled: true
    cutoff_hz: 300.0       # Typical aviation radio low cutoff

  # Low-pass filter (bandwidth limit)
  lowpass:
    enabled: true
    cutoff_hz: 3400.0      # AM radio bandwidth limit

  # Compression (AGC simulation)
  compressor:
    enabled: true
    threshold_db: -20.0    # Compress above this level
    ratio: 10.0            # Heavy compression (10:1)
    attack_ms: 1.0         # Fast attack
    release_ms: 100.0      # Moderate release

  # Distortion (subtle saturation)
  distortion:
    enabled: true
    level: 0.2             # Very subtle (0.0-1.0)

  # Static noise (atmospheric interference)
  static_noise:
    enabled: true
    level: 0.03            # 3% mix (very subtle)
    type: "white"          # white/pink noise

  # Overall effect mix
  wet_level: 0.9           # 90% effected signal
  dry_level: 0.1           # 10% original signal
```

## ATC Message System

### Message Types

1. **Startup/Ground Operations**
   - ATIS information
   - Ground clearance (taxi instructions)
   - Taxi guidance
   - Hold short instructions

2. **Takeoff Phase**
   - Lineup and wait
   - Cleared for takeoff
   - Contact departure

3. **Airborne**
   - Altitude/heading assignments
   - Traffic advisories
   - Weather updates
   - Frequency changes

4. **Approach/Landing**
   - Approach clearance
   - Runway assignment
   - Landing clearance
   - Go-around instructions

### Speech File Generation

**Separate voice for ATC** (e.g., use "Alex" male voice for ATC, "Samantha" female voice for cockpit):

```bash
# Generate ATC voice files (different from cockpit)
python scripts/generate_atc_speech.py --voice Alex --rate 175 --output-dir data/atc
```

### Message Configuration (`config/atc_en.yaml`)

```yaml
language: en
voice: Alex  # Different from cockpit voice
file_extension: mp3

# ATC messages (pre-recorded phrases)
messages:
  # Ground operations
  ATC_GROUND_TAXI_RWY_31: "taxi_to_runway_31_via_alpha"
  ATC_GROUND_HOLD_SHORT: "hold_short_of_runway_31"
  ATC_GROUND_CONTACT_TOWER: "contact_tower_120_point_5"

  # Tower - Takeoff
  ATC_TOWER_LINE_UP_WAIT: "runway_31_line_up_and_wait"
  ATC_TOWER_CLEARED_TAKEOFF: "runway_31_cleared_for_takeoff"
  ATC_TOWER_CONTACT_DEPARTURE: "contact_departure_125_point_35"

  # Departure
  ATC_DEPARTURE_CLIMB_MAINTAIN: "climb_and_maintain_3000"
  ATC_DEPARTURE_TURN_LEFT: "turn_left_heading_270"
  ATC_DEPARTURE_CONTACT_CENTER: "contact_center_132_point_45"

  # Approach
  ATC_APPROACH_CLEARED_APPROACH: "cleared_ils_runway_31_approach"
  ATC_APPROACH_DESCEND: "descend_and_maintain_2000"
  ATC_APPROACH_CONTACT_TOWER: "contact_tower_118_point_3"

  # Tower - Landing
  ATC_TOWER_CLEARED_LAND: "runway_31_cleared_to_land"
  ATC_TOWER_GO_AROUND: "go_around"

  # Generic
  ATC_ROGER: "roger"
  ATC_AFFIRM: "affirmative"
  ATC_NEGATIVE: "negative"
  ATC_SAY_AGAIN: "say_again"
```

## Implementation

### 1. Radio Effect Filter (`src/airborne/audio/effects/radio_filter.py`)

```python
"""Radio effect filter using FMOD DSP."""

from typing import Any
import pyfmodex

class RadioEffectFilter:
    """Applies aviation radio effect to audio using FMOD DSP chain."""

    def __init__(self, system: Any, config: dict[str, Any]):
        """Initialize radio effect DSP chain.

        Args:
            system: FMOD System instance.
            config: Radio effect configuration.
        """
        self._system = system
        self._config = config
        self._dsp_chain: list[Any] = []

        # Create DSP chain
        self._setup_dsp_chain()

    def _setup_dsp_chain(self) -> None:
        """Create DSP effects based on configuration."""
        # High-pass filter (remove low frequencies)
        if self._config.get("highpass", {}).get("enabled", True):
            highpass = self._system.create_dsp_by_type(pyfmodex.enums.DSP_TYPE.HIGHPASS)
            cutoff = self._config.get("highpass", {}).get("cutoff_hz", 300.0)
            highpass.set_parameter_float(0, cutoff)  # Cutoff frequency
            self._dsp_chain.append(highpass)

        # Low-pass filter (bandwidth limit)
        if self._config.get("lowpass", {}).get("enabled", True):
            lowpass = self._system.create_dsp_by_type(pyfmodex.enums.DSP_TYPE.LOWPASS)
            cutoff = self._config.get("lowpass", {}).get("cutoff_hz", 3400.0)
            lowpass.set_parameter_float(0, cutoff)  # Cutoff frequency
            self._dsp_chain.append(lowpass)

        # Compressor (AGC simulation)
        if self._config.get("compressor", {}).get("enabled", True):
            compressor = self._system.create_dsp_by_type(pyfmodex.enums.DSP_TYPE.COMPRESSOR)
            threshold = self._config.get("compressor", {}).get("threshold_db", -20.0)
            ratio = self._config.get("compressor", {}).get("ratio", 10.0)
            attack = self._config.get("compressor", {}).get("attack_ms", 1.0)
            release = self._config.get("compressor", {}).get("release_ms", 100.0)

            compressor.set_parameter_float(0, threshold)  # Threshold
            compressor.set_parameter_float(1, ratio)      # Ratio
            compressor.set_parameter_float(2, attack)     # Attack
            compressor.set_parameter_float(3, release)    # Release
            self._dsp_chain.append(compressor)

        # Distortion (optional saturation)
        if self._config.get("distortion", {}).get("enabled", False):
            distortion = self._system.create_dsp_by_type(pyfmodex.enums.DSP_TYPE.DISTORTION)
            level = self._config.get("distortion", {}).get("level", 0.2)
            distortion.set_parameter_float(0, level)  # Distortion level
            self._dsp_chain.append(distortion)

    def apply_to_channel(self, channel: Any) -> None:
        """Apply radio effect to a channel.

        Args:
            channel: FMOD Channel to apply effect to.
        """
        # Add each DSP to the channel's DSP chain
        for dsp in self._dsp_chain:
            channel.add_dsp(0, dsp)  # Add at head of DSP chain
            dsp.active = True

    def remove_from_channel(self, channel: Any) -> None:
        """Remove radio effect from a channel.

        Args:
            channel: FMOD Channel to remove effect from.
        """
        for dsp in self._dsp_chain:
            try:
                channel.remove_dsp(dsp)
            except Exception:
                pass  # Already removed

    def shutdown(self) -> None:
        """Clean up DSP resources."""
        for dsp in self._dsp_chain:
            try:
                dsp.release()
            except Exception:
                pass
        self._dsp_chain.clear()
```

### 2. ATC Audio Manager (`src/airborne/audio/atc/atc_audio.py`)

```python
"""ATC audio manager with radio effects."""

from pathlib import Path
from typing import Any
import yaml

from airborne.audio.effects.radio_filter import RadioEffectFilter
from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


class ATCAudioManager:
    """Manages ATC audio playback with radio effects."""

    def __init__(self, audio_engine: Any, config_dir: Path, speech_dir: Path):
        """Initialize ATC audio manager.

        Args:
            audio_engine: FMOD audio engine instance.
            config_dir: Path to configuration directory.
            speech_dir: Path to ATC speech files (data/atc/en/).
        """
        self._audio_engine = audio_engine
        self._speech_dir = speech_dir
        self._radio_filter: RadioEffectFilter | None = None
        self._message_map: dict[str, str] = {}
        self._file_extension = "mp3"

        # Load ATC message configuration
        atc_config_file = config_dir / "atc_en.yaml"
        self._load_atc_config(atc_config_file)

        # Load radio effect configuration
        radio_config_file = config_dir / "radio_effects.yaml"
        self._load_radio_effect(radio_config_file)

    def _load_atc_config(self, config_file: Path) -> None:
        """Load ATC message configuration."""
        if not config_file.exists():
            logger.error(f"ATC config not found: {config_file}")
            return

        try:
            with open(config_file, encoding="utf-8") as f:
                config = yaml.safe_load(f)

            self._file_extension = config.get("file_extension", "mp3")
            self._message_map = config.get("messages", {})

            logger.info(f"Loaded {len(self._message_map)} ATC messages from {config_file}")
        except Exception as e:
            logger.error(f"Error loading ATC config: {e}")

    def _load_radio_effect(self, config_file: Path) -> None:
        """Load and setup radio effect DSP."""
        if not config_file.exists():
            logger.warning(f"Radio effect config not found: {config_file}, using defaults")
            radio_config = {}
        else:
            try:
                with open(config_file, encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                radio_config = config.get("radio_effect", {})
            except Exception as e:
                logger.error(f"Error loading radio effect config: {e}")
                radio_config = {}

        # Create radio filter
        try:
            self._radio_filter = RadioEffectFilter(
                self._audio_engine._system,  # FMOD system
                radio_config
            )
            logger.info("Radio effect filter created successfully")
        except Exception as e:
            logger.error(f"Failed to create radio filter: {e}")

    def play_atc_message(self, message_key: str, volume: float = 1.0) -> int | None:
        """Play an ATC message with radio effect.

        Args:
            message_key: Message key (e.g., ATC_TOWER_CLEARED_TAKEOFF).
            volume: Volume level (0.0 to 1.0).

        Returns:
            Source ID or None if failed.
        """
        # Resolve message key to filename
        filename_base = self._message_map.get(message_key)
        if not filename_base:
            logger.warning(f"ATC message key not found: {message_key}")
            return None

        filename = f"{filename_base}.{self._file_extension}"
        filepath = self._speech_dir / filename

        if not filepath.exists():
            logger.warning(f"ATC speech file not found: {filepath}")
            return None

        # Load and play sound
        try:
            sound = self._audio_engine.load_sound(str(filepath))
            source_id = self._audio_engine.play_2d(sound, volume=volume, pitch=1.0, loop=False)

            # Apply radio effect to the channel
            if self._radio_filter and source_id:
                channel = self._audio_engine._channels.get(source_id)
                if channel:
                    self._radio_filter.apply_to_channel(channel)
                    logger.info(f"Playing ATC message with radio effect: {message_key}")

            return source_id

        except Exception as e:
            logger.error(f"Error playing ATC message {message_key}: {e}")
            return None

    def shutdown(self) -> None:
        """Shutdown ATC audio manager."""
        if self._radio_filter:
            self._radio_filter.shutdown()
        logger.info("ATC audio manager shut down")
```

### 3. Integration with Radio Plugin

Update `src/airborne/plugins/radio/radio_plugin.py` to use ATC audio manager:

```python
from airborne.audio.atc.atc_audio import ATCAudioManager

class RadioPlugin(IPlugin):
    def __init__(self):
        # ... existing code ...
        self._atc_audio: ATCAudioManager | None = None

    def initialize(self, context: PluginContext):
        # ... existing code ...

        # Initialize ATC audio manager
        audio_engine = context.registry.get("audio_engine")
        if audio_engine:
            config_dir = Path("config")
            speech_dir = Path("data/atc/en")
            self._atc_audio = ATCAudioManager(audio_engine, config_dir, speech_dir)

    def handle_message(self, message: Message):
        # ... existing code ...

        # Handle ATC message requests
        if message.topic == MessageTopic.ATC_MESSAGE:
            atc_key = message.data.get("message_key")
            if self._atc_audio:
                self._atc_audio.play_atc_message(atc_key)
```

## Testing

### Manual Testing

1. **Generate ATC speech files**:
   ```bash
   python scripts/generate_atc_speech.py
   ```

2. **Test radio effect in isolation**:
   ```bash
   python scripts/test_radio_effect.py data/atc/en/runway_31_cleared_for_takeoff.mp3
   ```

3. **Test in-game**:
   - Trigger ATC messages at various flight phases
   - Verify radio effect is applied
   - Check that cockpit TTS doesn't have radio effect

### Unit Tests

```python
def test_radio_filter_applies_correctly():
    """Test that radio filter DSP chain is applied to channel."""
    # Create mock FMOD system and channel
    # Apply radio filter
    # Verify DSP chain is attached

def test_atc_audio_plays_with_effect():
    """Test that ATC messages play with radio effect."""
    # Load ATC message
    # Play with radio effect
    # Verify channel has DSP chain

def test_cockpit_tts_no_radio_effect():
    """Test that cockpit TTS doesn't have radio effect."""
    # Play cockpit message
    # Verify no radio effect applied
```

## Future Enhancements

1. **Dynamic Static**: Add realistic static bursts based on distance/signal strength
2. **Squelch Simulation**: Add squelch open/close sounds
3. **PTT Click**: Add realistic PTT button click sounds
4. **CTAF Simulation**: Multiple aircraft on same frequency (mixing)
5. **Signal Strength**: Vary effect intensity based on distance from transmitter
6. **Interference**: Simulate co-channel interference
7. **Different Radio Types**: VHF vs. HF vs. UHF characteristics

## References

- Aviation Radio Specifications: ITU-R M.1545
- FMOD DSP Reference: https://www.fmod.com/docs/2.02/api/core-api-common-dsp-effects.html
- Aviation Phraseology: ICAO Annex 10, Vol. II

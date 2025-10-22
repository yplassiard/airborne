# Kokoro TTS Integration Guide

This document describes the Kokoro TTS integration for AirBorne flight simulator.

## Overview

**Kokoro TTS** is a lightweight, high-quality text-to-speech model with 82 million parameters that delivers comparable quality to commercial TTS services like ElevenLabs, but runs entirely locally on your Mac.

### Why Kokoro?

- ✅ **Zero cost** - No API fees, unlimited generations
- ✅ **Fast** - 3-8x faster than realtime on M4 Mac
- ✅ **High quality** - #1 on Hugging Face TTS Arena leaderboard
- ✅ **Offline** - No internet connection required
- ✅ **19 English voices** - Multiple male and female voices
- ✅ **Perfect for development** - Iterate freely without cost concerns

## Installation

Run the installation script:

```bash
./scripts/install_kokoro.sh
```

This will:
1. Check system compatibility (macOS required)
2. Install espeak-ng via Homebrew
3. Install Python packages (kokoro-onnx, soundfile)
4. Download ONNX model files (~337MB total)
5. Verify installation with test audio

## Available Voices

### Female Voices (11 voices)
- `af_alloy` - Neutral, versatile
- `af_aoede` - Warm, friendly
- `af_bella` - Clear, professional ✨ **Recommended for pilot**
- `af_heart` - Emotional, expressive
- `af_jessica` - Confident, authoritative
- `af_kore` - Calm, reassuring
- `af_nicole` - Bright, energetic
- `af_nova` - Modern, crisp
- `af_river` - Smooth, flowing
- `af_sarah` - Professional, clear ✨ **Recommended for cockpit computer**
- `af_sky` - Airy, light

### Male Voices (8 voices)
- `am_adam` - Professional, clear ✨ **Recommended for ATC**
- `am_echo` - Deep, resonant
- `am_eric` - Friendly, approachable
- `am_fenrir` - Strong, authoritative
- `am_liam` - Smooth, conversational
- `am_michael` - Warm, trustworthy ✨ **Recommended for ground control**
- `am_onyx` - Rich, deep
- `am_puck` - Playful, energetic

## Usage

### Basic Example

```python
from kokoro_onnx import Kokoro
import soundfile as sf

# Initialize Kokoro
kokoro = Kokoro(
    model_path="assets/models/kokoro-v1.0.onnx",
    voices_path="assets/models/voices-v1.0.bin"
)

# Generate speech
text = "Palo Alto Tower, Cessna one two three alpha bravo, ready for departure."
samples, sample_rate = kokoro.create(
    text,
    voice='af_bella',  # Choose any voice
    lang='en-us',      # Language code
    speed=1.0          # Speech speed (0.5-2.0)
)

# Save to file
sf.write('output.wav', samples, sample_rate)
```

### Performance Characteristics

On M4 MacBook Pro:
- **Initialization**: ~0.2s (one-time cost)
- **First generation**: ~3x faster than realtime
- **Subsequent generations**: ~8x faster than realtime
- **Sample rate**: 24,000 Hz
- **Quality**: Comparable to ElevenLabs Turbo v2

Example: A 6-second audio clip generates in ~0.8 seconds.

### Speed Control

Adjust speech speed with the `speed` parameter:

```python
# Slower (clearer)
samples, rate = kokoro.create(text, voice='af_bella', speed=0.8)

# Normal
samples, rate = kokoro.create(text, voice='af_bella', speed=1.0)

# Faster (more urgent)
samples, rate = kokoro.create(text, voice='af_bella', speed=1.2)
```

## Integration with AirBorne

### Recommended Voice Mapping

Based on testing, here are recommended voices for different roles:

| Role | Voice | Rationale |
|------|-------|-----------|
| Pilot | `af_bella` | Clear, professional, authoritative |
| Cockpit Computer | `af_sarah` | Professional, consistent, neutral |
| ATC Ground | `am_adam` | Professional, clear, official |
| ATC Tower | `am_adam` | (same as ground for consistency) |
| ATC Approach | `am_michael` | Warm, trustworthy, calming |
| ATIS | `af_sarah` | Robotic consistency for automated messages |
| Steward | `af_aoede` | Warm, friendly, welcoming |
| Ground Crew | `am_eric` | Friendly, approachable |

### Updating config/speech.yaml

Update the voice configuration to use Kokoro:

```yaml
voices:
  pilot:
    description: Pilot transmitting on radio and reading checklists
    engine: kokoro
    voice_name: af_bella
    language: en-us
    rate: 1.0  # Speed multiplier
    output_dir: pilot

  cockpit:
    description: Cockpit computer for instrument readouts
    engine: kokoro
    voice_name: af_sarah
    language: en-us
    rate: 1.1  # Slightly faster for efficiency
    output_dir: cockpit

  ground:
    description: Ground control / Clearance delivery
    engine: kokoro
    voice_name: am_adam
    language: en-us
    rate: 0.95  # Slightly slower for clarity
    output_dir: atc/ground
```

### Updating scripts/generate_speech.py

Add Kokoro backend support:

```python
from kokoro_onnx import Kokoro
import soundfile as sf

# Initialize once (reuse for all generations)
kokoro = Kokoro(
    model_path="assets/models/kokoro-v1.0.onnx",
    voices_path="assets/models/voices-v1.0.bin"
)

def generate_speech_kokoro(text, voice, output_path, speed=1.0):
    """Generate speech using Kokoro TTS."""
    samples, sample_rate = kokoro.create(
        text,
        voice=voice,
        lang='en-us',
        speed=speed
    )
    sf.write(output_path, samples, sample_rate)
```

## Testing

### Quick Test

Run the test script to verify installation:

```bash
uv run python scripts/test_kokoro.py
```

### Test Multiple Voices

```bash
uv run python << 'EOF'
from kokoro_onnx import Kokoro
import soundfile as sf

kokoro = Kokoro("assets/models/kokoro-v1.0.onnx", "assets/models/voices-v1.0.bin")

voices = ['af_bella', 'am_adam', 'af_sarah', 'am_michael']
text = "AirBorne flight simulator, all systems ready."

for voice in voices:
    samples, rate = kokoro.create(text, voice=voice, lang='en-us')
    sf.write(f'/tmp/test_{voice}.wav', samples, rate)
    print(f"Generated: /tmp/test_{voice}.wav")
EOF
```

## Performance Tips

### 1. Reuse Kokoro Instance

Initialize once and reuse for all generations:

```python
# ✅ Good - Initialize once
kokoro = Kokoro(model_path, voices_path)
for text in texts:
    samples, rate = kokoro.create(text, voice='af_bella')

# ❌ Bad - Initialize every time
for text in texts:
    kokoro = Kokoro(model_path, voices_path)  # Slow!
    samples, rate = kokoro.create(text, voice='af_bella')
```

### 2. Batch Generation

Generate all speech files in one script run for maximum efficiency.

### 3. Caching

Cache generated audio by text hash to avoid regenerating identical messages:

```python
import hashlib
from pathlib import Path

def get_cache_path(text, voice):
    hash_key = hashlib.md5(f"{text}:{voice}".encode()).hexdigest()
    return Path(f"data/speech/cache/{hash_key}.wav")

def generate_or_load(text, voice, kokoro):
    cache_path = get_cache_path(text, voice)
    if cache_path.exists():
        return cache_path  # Already generated

    samples, rate = kokoro.create(text, voice=voice, lang='en-us')
    sf.write(cache_path, samples, rate)
    return cache_path
```

## Troubleshooting

### Issue: Slow first generation

**Cause**: Model loading and initialization
**Solution**: This is normal. First generation takes ~1.5s, subsequent ones are much faster (~0.8s).

### Issue: espeak-ng not found

**Cause**: espeak-ng not installed
**Solution**: Run `brew install espeak-ng`

### Issue: Model files not found

**Cause**: Models not downloaded or wrong path
**Solution**:
```bash
# Re-download models
rm -rf assets/models/*.onnx assets/models/*.bin
./scripts/install_kokoro.sh
```

### Issue: Poor audio quality

**Cause**: Speed too fast, or wrong voice for use case
**Solution**: Try `speed=0.9` or test different voices

## Comparison: Kokoro vs ElevenLabs vs macOS `say`

| Feature | Kokoro ONNX | ElevenLabs | macOS `say` |
|---------|-------------|------------|-------------|
| **Cost** | Free | $5-99/month | Free |
| **Quality** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| **Speed** | 3-8x realtime | Network latency | Instant |
| **Voices** | 19 | 100+ | 40+ |
| **Offline** | ✅ Yes | ❌ No | ✅ Yes |
| **Iterating** | Unlimited | Limited by credits | Unlimited |
| **Best for** | Development | Production | Quick testing |

## Cost Savings

For development with ~100,000 characters of speech generation:

- **ElevenLabs**: $22-99/month = **$132-600** over 6 months
- **Kokoro**: $0 = **$0**
- **Savings**: **$132-600**

## Future: Production Considerations

For final production release, consider:

1. **Keep Kokoro for bulk messages** (numbers, controls, generic announcements)
2. **Use ElevenLabs for key voices** (pilot, main ATC) if you want the absolute best quality
3. **Hybrid approach**: Best of both worlds at minimal cost (~$20 one-time)

## Resources

- **Kokoro ONNX GitHub**: https://github.com/thewh1teagle/kokoro-onnx
- **Original Kokoro Model**: https://huggingface.co/hexgrad/Kokoro-82M
- **Voice Samples**: Test all voices with `scripts/test_kokoro.py`

## Support

For issues or questions:
1. Check this documentation
2. Test with `scripts/test_kokoro.py`
3. Verify models exist: `ls -lh assets/models/`
4. Check installation: `./scripts/install_kokoro.sh`

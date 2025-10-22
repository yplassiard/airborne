# Speech Synthesis Documentation

This directory contains all documentation related to Text-to-Speech (TTS) and voice generation for AirBorne.

## Quick Links

### Getting Started
- **[KOKORO_SETUP.md](KOKORO_SETUP.md)** - Quick start guide for Kokoro TTS installation and usage

### Complete Guides
- **[KOKORO_TTS.md](KOKORO_TTS.md)** - Complete Kokoro TTS integration guide for AirBorne
- **[KOKORO_LANGUAGES.md](KOKORO_LANGUAGES.md)** - Multi-language support guide (8 languages including French)

### Scripts Reference
- **[../scripts/README_KOKORO.md](../../scripts/README_KOKORO.md)** - Reference for all Kokoro voice scripts

## Overview

AirBorne supports multiple TTS engines:

| Engine | Platform | Quality | Cost | Offline |
|--------|----------|---------|------|---------|
| **Kokoro** | All | ⭐⭐⭐⭐ | Free | ✅ Yes |
| **macOS say** | macOS only | ⭐⭐⭐ | Free | ✅ Yes |
| **pyttsx3** | Windows/Linux | ⭐⭐ | Free | ✅ Yes |

## Kokoro TTS (Recommended)

**Kokoro** is the recommended TTS engine for development:
- 🎯 High quality (#1 on Hugging Face TTS Arena)
- 🚀 Fast (7-8x realtime on M4 Mac)
- 💰 Free (unlimited generations)
- 🌍 8 languages supported
- 🎭 19 voices (11 female, 8 male)
- 📦 Runs completely offline

### Installation

```bash
./scripts/install_kokoro.sh
```

Downloads models (~337MB) and installs dependencies.

### Quick Test

```bash
# Test installation
uv run python scripts/test_kokoro.py

# Listen to all voices
uv run python scripts/listen_voices_auto.py

# Generate speech files
uv run python scripts/generate_speech.py
```

### Configuration

Edit `config/speech.yaml` to configure voices:

```yaml
voices:
  pilot:
    description: Pilot transmitting on radio and reading checklists
    engine: kokoro              # Use kokoro engine
    voice_name: af_bella        # Kokoro voice (19 available)
    language: en-us             # Language code
    rate: 200                   # Words per minute (converted to speed)
    volume: 1.0
    output_dir: pilot

  cockpit:
    engine: kokoro
    voice_name: af_sarah
    language: en-us
    rate: 200
    output_dir: cockpit
```

## Available Scripts

### Installation
- `scripts/install_kokoro.sh` - Install Kokoro TTS and download models
- `scripts/test_kokoro.py` - Test Kokoro installation

### Voice Testing
- `scripts/listen_voices_auto.py` - Auto-play all 19 voices (English)
- `scripts/listen_voices.py` - Interactive voice listener (press Enter for each)
- `scripts/listen_voices_french.py` - Listen to French voices
- `scripts/sample_voices.py` - Generate voice samples to files

### Speech Generation
- `scripts/generate_speech.py` - Main speech generation script

## Speech Generation

Generate all speech files for the simulator:

```bash
# Generate all voices
uv run python scripts/generate_speech.py

# Generate specific voice
uv run python scripts/generate_speech.py pilot

# Regenerate all (clean)
uv run python scripts/generate_speech.py --clean

# List available voices
uv run python scripts/generate_speech.py --list
```

## Voice Recommendations

Based on testing for AirBorne:

| Role | Voice | Engine | Character |
|------|-------|--------|-----------|
| **Pilot** | `af_bella` | kokoro | Clear, professional, authoritative |
| **Cockpit Computer** | `af_sarah` | kokoro | Neutral, consistent, robotic |
| **ATC Ground/Tower** | `am_adam` | kokoro | Professional, clear, official |
| **ATC Approach** | `am_michael` | kokoro | Warm, trustworthy, calm |
| **ATIS** | `af_sarah` | kokoro | Robotic consistency |
| **Ground Crew** | `am_eric` | kokoro | Friendly, approachable |

## Multi-Language Support

Kokoro supports 8 languages:
- 🇺🇸 English (American & British)
- 🇫🇷 French
- 🇪🇸 Spanish
- 🇮🇹 Italian
- 🇧🇷 Portuguese
- 🇮🇳 Hindi
- 🇯🇵 Japanese (requires extra install)
- 🇨🇳 Mandarin (requires extra install)

See [KOKORO_LANGUAGES.md](KOKORO_LANGUAGES.md) for details.

## File Structure

```
docs/speech/
├── README.md              # This file - main index
├── KOKORO_SETUP.md        # Quick start guide
├── KOKORO_TTS.md          # Complete integration guide
└── KOKORO_LANGUAGES.md    # Multi-language guide

scripts/
├── install_kokoro.sh      # Installation script
├── test_kokoro.py         # Test script
├── generate_speech.py     # Main generation script
├── listen_voices_auto.py  # Auto-play voice listener
├── listen_voices.py       # Interactive voice listener
├── listen_voices_french.py # French voice listener
├── sample_voices.py       # Generate voice samples
└── README_KOKORO.md       # Scripts reference

assets/models/
├── kokoro-v1.0.onnx      # Main TTS model (310MB)
├── voices-v1.0.bin       # Voice embeddings (27MB)
└── README.md             # Model documentation

config/
└── speech.yaml           # Voice configuration
```

## Cost Comparison

For development with ~100,000 characters of speech:

| Service | 6-Month Cost | Quality | Offline |
|---------|--------------|---------|---------|
| **Kokoro** | **$0** | ⭐⭐⭐⭐ | ✅ |
| ElevenLabs Creator | $132 | ⭐⭐⭐⭐⭐ | ❌ |
| ElevenLabs Pro | $600 | ⭐⭐⭐⭐⭐ | ❌ |

**Savings: $132-600** during development!

## Performance

On M4 MacBook Pro (24GB RAM):
- **Initialization**: 0.2s (one-time)
- **First generation**: 3-4x realtime
- **Subsequent generations**: 7-8x realtime
- **Average across 19 voices**: 7.5x realtime

Example: Generate 112 seconds of audio in just 15 seconds!

## Troubleshooting

### Kokoro not available
```bash
./scripts/install_kokoro.sh
```

### Models not found
```bash
ls -lh assets/models/
# Should show:
# kokoro-v1.0.onnx (310MB)
# voices-v1.0.bin (27MB)
```

### Test generation
```bash
uv run python scripts/test_kokoro.py
```

## Support

For issues or questions:
1. Check documentation in this directory
2. Run test scripts (`scripts/test_kokoro.py`)
3. Verify models exist: `ls -lh assets/models/`

## See Also

- [Main README](../../README.md) - AirBorne project overview
- [Scripts README](../../scripts/README_KOKORO.md) - Kokoro scripts reference
- [Model README](../../assets/models/README.md) - Model file information

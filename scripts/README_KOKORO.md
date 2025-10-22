# Kokoro TTS Scripts

Quick reference for Kokoro TTS voice scripts.

## Installation

```bash
./scripts/install_kokoro.sh
```

Downloads models and installs all dependencies (~337MB).

## Scripts

### 1. **listen_voices_auto.py** - Quick Voice Browser
**Best for: Quickly hearing all voices**

```bash
uv run python scripts/listen_voices_auto.py
```

- ✅ Auto-plays all 19 voices one after another
- ✅ 1-second pause between each voice
- ✅ Press Ctrl+C to stop anytime
- ⏱️ Takes ~2 minutes total

**Output:**
```
[1/19] 🔊 af_alloy     - Female - Neutral, versatile
[2/19] 🔊 af_aoede     - Female - Warm, friendly
[3/19] 🔊 af_bella     - Female - Clear, professional ⭐
...
```

---

### 2. **listen_voices.py** - Interactive Voice Browser
**Best for: Carefully comparing voices**

```bash
uv run python scripts/listen_voices.py
```

- ✅ Press Enter to play each voice
- ✅ Take your time to think between voices
- ✅ Organized by Female/Male sections

**Usage:**
```
Press Enter to hear each voice (Ctrl+C to quit)

──────────────────────────────────────
FEMALE VOICES (11)
──────────────────────────────────────
[Press Enter]
  🔊 Playing: af_bella     - Clear, professional ⭐
[Press Enter]
  🔊 Playing: af_sarah     - Professional, clear ⭐
...
```

---

### 3. **sample_voices.py** - Generate Voice Samples
**Best for: Side-by-side comparison of saved files**

```bash
# Generate pilot voice samples
uv run python scripts/sample_voices.py --type pilot

# Generate ATC samples
uv run python scripts/sample_voices.py --type atc

# Generate ATIS samples
uv run python scripts/sample_voices.py --type atis

# Generate cockpit instrument samples
uv run python scripts/sample_voices.py --type cockpit
```

- ✅ Saves all 19 voices as WAV files
- ✅ Different sample texts for different use cases
- ✅ Shows generation performance stats

**Output:**
```
Female Voices
  af_bella     - 1.65s (6.0s audio, 3.6x realtime)
  af_sarah     - 0.76s (5.6s audio, 7.5x realtime)
  ...

Saved to: /tmp/kokoro_voice_samples/
```

**Open folder:**
```bash
open /tmp/kokoro_voice_samples
```

**Sample types:**
- `pilot` - Pilot radio transmission
- `atc` - ATC controller clearance
- `atis` - Automated weather broadcast
- `cockpit` - Instrument readouts

---

### 4. **test_kokoro.py** - Installation Test
**Best for: Verifying installation**

```bash
uv run python scripts/test_kokoro.py
```

- ✅ Tests model loading
- ✅ Generates short audio sample
- ✅ Shows performance metrics

**Output:**
```
Testing Kokoro ONNX TTS installation...
✓ Initialized in 0.23s
✓ Generated in 1.42s (4.18s audio, 2.9x realtime)
✓ Installation verified!

Play with: afplay /tmp/kokoro_test.wav
```

---

## Quick Decision Guide

**"I want to quickly hear all voices and pick favorites"**
→ `uv run python scripts/listen_voices_auto.py`

**"I want to carefully compare specific voices"**
→ `uv run python scripts/listen_voices.py`

**"I want to save samples and compare side-by-side"**
→ `uv run python scripts/sample_voices.py --type pilot`

**"I want to test if Kokoro is working"**
→ `uv run python scripts/test_kokoro.py`

---

## Recommended Voices

Based on testing for AirBorne:

| Role | Voice | Why |
|------|-------|-----|
| **Pilot** | `af_bella` | Clear, professional, authoritative |
| **Cockpit** | `af_sarah` | Consistent, neutral, robotic |
| **ATC Ground/Tower** | `am_adam` | Professional, clear, official |
| **Approach/Departure** | `am_michael` | Warm, trustworthy, calming |
| **ATIS** | `af_sarah` | Robotic consistency |
| **Ground Crew** | `am_eric` | Friendly, approachable |

---

## All Available Voices

**Female (11):** af_alloy, af_aoede, af_bella ⭐, af_heart, af_jessica, af_kore, af_nicole, af_nova, af_river, af_sarah ⭐, af_sky

**Male (8):** am_adam ⭐, am_echo, am_eric, am_fenrir, am_liam, am_michael ⭐, am_onyx, am_puck

⭐ = Recommended for AirBorne

---

## Troubleshooting

**"ModuleNotFoundError: No module named 'kokoro_onnx'"**
```bash
./scripts/install_kokoro.sh
```

**"FileNotFoundError: Model files not found"**
```bash
ls -lh assets/models/
# Should show kokoro-v1.0.onnx (310MB) and voices-v1.0.bin (27MB)
# If missing, re-run:
./scripts/install_kokoro.sh
```

**"afplay: command not found"**
→ macOS only. On Linux/Windows, scripts won't work without modification.

---

## Performance

On M4 MacBook Pro (24GB RAM):
- **Initialization**: ~0.2s (one-time)
- **First generation**: ~3x faster than realtime
- **Subsequent**: ~8x faster than realtime

---

## See Also

- **Complete guide**: `docs/KOKORO_TTS.md`
- **Quick start**: `KOKORO_SETUP.md` (root)
- **Model info**: `assets/models/README.md`

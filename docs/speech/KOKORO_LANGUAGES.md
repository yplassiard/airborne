# Kokoro TTS - Multi-Language Support

Kokoro TTS supports **8 languages** with all 19 voices working across all languages.

## Supported Languages

| Language | Code | Lang Parameter | Additional Install |
|----------|------|----------------|-------------------|
| 🇺🇸 American English | `a` | `en-us` | ✅ Included |
| 🇬🇧 British English | `b` | `en-gb` | ✅ Included |
| 🇫🇷 French | `f` | `fr-fr` | ✅ Included |
| 🇪🇸 Spanish | `e` | `es-es` | ✅ Included |
| 🇮🇹 Italian | `i` | `it-it` | ✅ Included |
| 🇧🇷 Portuguese | `p` | `pt-br` | ✅ Included |
| 🇮🇳 Hindi | `h` | `hi-in` | ✅ Included |
| 🇯🇵 Japanese | `j` | `ja-jp` | ⚠️ Requires `misaki[ja]` |
| 🇨🇳 Mandarin | `z` | `zh-cn` | ⚠️ Requires `misaki[zh]` |

## How It Works

All 19 voices (11 female, 8 male) work with **any language**. The same voice model produces different languages based on the `lang` parameter.

### Usage Example

```python
from kokoro_onnx import Kokoro
import soundfile as sf

kokoro = Kokoro(
    model_path="assets/models/kokoro-v1.0.onnx",
    voices_path="assets/models/voices-v1.0.bin"
)

# English
samples_en, rate = kokoro.create(
    "Ready for takeoff",
    voice='af_bella',
    lang='en-us'
)

# French
samples_fr, rate = kokoro.create(
    "Prêt pour le décollage",
    voice='af_bella',
    lang='fr-fr'
)

# Spanish
samples_es, rate = kokoro.create(
    "Listo para despegar",
    voice='af_bella',
    lang='es-es'
)
```

## French Support for AirBorne

French is **fully supported** with no additional installation required!

### Aviation Phrases in French

```python
french_aviation = {
    'pilot_ready': "Tour de contrôle, Cessna un deux trois alpha bravo, prêt pour le départ.",
    'atc_cleared': "Cessna trois alpha bravo, autorisé au décollage piste trois un.",
    'atis': "Aéroport de Palo Alto, information Alpha. Vent trois un zéro à huit nœuds.",
    'checklist': "Liste de vérification avant décollage.",
    'altitude': "Altitude deux mille pieds.",
    'airspeed': "Vitesse quatre-vingts nœuds.",
}

# Generate French speech
for key, text in french_aviation.items():
    samples, rate = kokoro.create(text, voice='af_bella', lang='fr-fr')
    sf.write(f'french_{key}.wav', samples, rate)
```

### Recommended Voices for French

Based on testing:

| Role | Voice | Quality |
|------|-------|---------|
| Pilot (Female) | `af_bella` | Clear, professional |
| Pilot (Male) | `am_adam` | Professional, authoritative |
| ATC | `am_michael` | Calm, trustworthy |
| Cockpit | `af_sarah` | Neutral, consistent |
| ATIS | `af_sarah` | Robotic consistency |

### Testing French Voices

```bash
# Test all voices with French text
uv run python << 'EOF'
from kokoro_onnx import Kokoro
import soundfile as sf

kokoro = Kokoro(
    "assets/models/kokoro-v1.0.onnx",
    "assets/models/voices-v1.0.bin"
)

text = "Bienvenue dans le simulateur de vol AirBorne."

for voice in ['af_bella', 'am_adam', 'af_sarah', 'am_michael']:
    samples, rate = kokoro.create(text, voice=voice, lang='fr-fr')
    sf.write(f'/tmp/french_{voice}.wav', samples, rate)
    print(f"Generated: /tmp/french_{voice}.wav")
EOF

# Listen to results
afplay /tmp/french_af_bella.wav
```

## Accent Quality

**Important Note**: The voices are primarily trained on English, so:

- ✅ **Pronunciation**: Generally good across all languages
- ⚠️ **Accent**: May have a slight English accent in some voices
- ✅ **Intelligibility**: Clear and understandable
- ⚠️ **Native-like**: Not quite native speaker quality

For **professional French production**, you might want to:
1. Test multiple voices to find the best French accent
2. Consider native French TTS if accent perfection is critical
3. For AirBorne development/testing, Kokoro's French is perfectly adequate

## Multi-Language Configuration

You can configure `config/speech.yaml` to support multiple languages:

```yaml
voices:
  pilot_en:
    engine: kokoro
    voice_name: af_bella
    language: en-us
    output_dir: pilot/en

  pilot_fr:
    engine: kokoro
    voice_name: af_bella
    language: fr-fr
    output_dir: pilot/fr

  atc_en:
    engine: kokoro
    voice_name: am_adam
    language: en-us
    output_dir: atc/en

  atc_fr:
    engine: kokoro
    voice_name: am_adam
    language: fr-fr
    output_dir: atc/fr
```

## Language-Specific Sample Script

Create `scripts/listen_voices_french.py` for French voice testing:

```python
#!/usr/bin/env python3
from kokoro_onnx import Kokoro
import subprocess
import tempfile
import soundfile as sf
from pathlib import Path

kokoro = Kokoro(
    "assets/models/kokoro-v1.0.onnx",
    "assets/models/voices-v1.0.bin"
)

text = "Tour de contrôle, Cessna un deux trois alpha bravo, prêt pour le départ."
voices = ['af_bella', 'am_adam', 'af_sarah', 'am_michael']

with tempfile.TemporaryDirectory() as temp_dir:
    temp_path = Path(temp_dir)

    for voice in voices:
        print(f"🔊 {voice}")
        samples, rate = kokoro.create(text, voice=voice, lang='fr-fr')
        temp_file = temp_path / f"{voice}.wav"
        sf.write(str(temp_file), samples, rate)
        subprocess.run(['afplay', str(temp_file)])
```

## Additional Languages

### Spanish (es-es)
```python
samples, rate = kokoro.create(
    "Listo para el despegue",
    voice='af_bella',
    lang='es-es'
)
```

### Italian (it-it)
```python
samples, rate = kokoro.create(
    "Pronto per il decollo",
    voice='af_bella',
    lang='it-it'
)
```

### Portuguese (pt-br)
```python
samples, rate = kokoro.create(
    "Pronto para decolagem",
    voice='af_bella',
    lang='pt-br'
)
```

## Installing Japanese/Chinese Support

For Japanese and Mandarin, install additional dependencies:

```bash
# Japanese
uv pip install "misaki[ja]"

# Mandarin
uv pip install "misaki[zh]"

# Both
uv pip install "misaki[ja,zh]"
```

Then use:
```python
# Japanese
samples, rate = kokoro.create("こんにちは", voice='af_bella', lang='ja-jp')

# Mandarin
samples, rate = kokoro.create("你好", voice='af_bella', lang='zh-cn')
```

## Cost Advantage for Multi-Language

With Kokoro, you get **all 8 languages for free**, whereas:

- **ElevenLabs**: Same pricing per character across all languages
- **Kokoro**: $0 for unlimited generation in any language
- **Savings**: Even greater when supporting multiple languages

For a bilingual English/French flight simulator:
- **ElevenLabs**: ~$200-1000+ for development
- **Kokoro**: $0

## Summary

✅ **French is fully supported** in Kokoro TTS
✅ All 19 voices work with French
✅ No additional installation required
✅ Performance same as English (~7-8x realtime)
✅ Good pronunciation, slight English accent
✅ Perfect for development and testing
✅ Production-ready quality for most use cases

## See Also

- **Main Guide**: `docs/KOKORO_TTS.md`
- **Quick Start**: `KOKORO_SETUP.md`
- **Scripts**: `scripts/README_KOKORO.md`

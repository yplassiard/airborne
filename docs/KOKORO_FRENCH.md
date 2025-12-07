# Voix Françaises Kokoro TTS

## Voix Disponibles

Kokoro TTS supporte le français avec les mêmes 19 voix que l'anglais. Il suffit de changer le code langue à `fr-fr` au lieu de `en-us`.

### Voix Féminines (11)
- `af_alloy` - Neutre, polyvalente
- `af_aoede` - Chaleureuse, amicale
- `af_bella` ⭐ - Claire, professionnelle
- `af_heart` - Émotionnelle, expressive
- `af_jessica` - Confiante, autoritaire
- `af_kore` - Calme, rassurante
- `af_nicole` - Brillante, énergique
- `af_nova` - Moderne, nette
- `af_river` - Douce, fluide
- `af_sarah` ⭐ - Professionnelle, claire
- `af_sky` - Aérienne, légère

### Voix Masculines (8)
- `am_adam` ⭐ - Professionnelle, claire
- `am_echo` - Profonde, résonnante
- `am_eric` - Amicale, accessible
- `am_fenrir` - Forte, autoritaire
- `am_liam` - Douce, conversationnelle
- `am_michael` ⭐ - Chaleureuse, digne de confiance
- `am_onyx` - Riche, profonde
- `am_puck` - Joueuse, énergique

⭐ = Recommandée pour AirBorne

## Utilisation

### Test Rapide

```powershell
# Tester toutes les voix françaises
python scripts\test_kokoro_french.py
```

### Dans Votre Code Python

```python
from kokoro_onnx import Kokoro
import soundfile as sf

# Initialiser Kokoro
kokoro = Kokoro(
    model_path="assets/models/kokoro-v1.0.onnx",
    voices_path="assets/models/voices-v1.0.bin"
)

# Générer en français
texte = "Bonjour, bienvenue à bord du simulateur de vol AirBorne."
samples, sample_rate = kokoro.create(
    texte,
    voice="af_bella",  # Choisir la voix
    lang="fr-fr"       # Code langue français
)

# Sauvegarder
sf.write("sortie.wav", samples, sample_rate)
```

## Configuration pour AirBorne

Pour utiliser le français dans AirBorne, modifiez `config\speech.yaml` :

```yaml
voices:
  pilot:
    engine: kokoro
    voice_name: af_bella
    language: fr-fr  # ← Changer de en-us à fr-fr
    rate: 160
    output_dir: data/speech/pilot/fr

  cockpit:
    engine: kokoro
    voice_name: af_sarah
    language: fr-fr  # ← Changer de en-us à fr-fr
    rate: 140
    output_dir: data/speech/fr
```

## Codes Langues Supportés

Kokoro supporte plusieurs langues :
- `en-us` - Anglais américain
- `en-gb` - Anglais britannique
- `fr-fr` - Français
- `es-es` - Espagnol
- `de-de` - Allemand
- `it-it` - Italien
- `pt-br` - Portugais brésilien
- `ja-jp` - Japonais
- `zh-cn` - Chinois mandarin

## Notes

- Les 19 voix fonctionnent avec toutes les langues
- La qualité peut varier selon la langue (meilleure pour anglais et français)
- La vitesse (rate/WPM) peut nécessiter un ajustement selon la langue
- Les accents sont automatiquement gérés par le modèle

## Exemples d'Utilisation

### Pilote en Français
```python
message = "Tour de contrôle, Cessna Alpha Bravo Charlie, prêt pour le décollage piste trois un."
samples, rate = kokoro.create(message, voice="af_bella", lang="fr-fr")
```

### Annonce ATIS en Français
```python
atis = "Information Alpha. Vent trois zéro zéro à huit nœuds. Visibilité dix kilomètres. Altimètre deux niner niner deux."
samples, rate = kokoro.create(atis, voice="af_sarah", lang="fr-fr", speed=0.85)
```

### Contrôleur ATC en Français
```python
clearance = "Cessna Alpha Bravo Charlie, autorisé au roulage piste trois un via alpha."
samples, rate = kokoro.create(clearance, voice="am_adam", lang="fr-fr")
```

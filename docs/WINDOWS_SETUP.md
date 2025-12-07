# AirBorne - Guide d'Installation Windows

Guide complet pour installer et configurer AirBorne sur Windows 10/11.

## Prérequis

### Requis
- **Windows 10/11** (64-bit)
- **Python 3.10-3.12** ([Télécharger](https://www.python.org/downloads/))
- **Git** (optionnel, pour cloner le dépôt)

### Recommandé
- **uv** - Gestionnaire de paquets Python ultra-rapide ([Installation](#installer-uv))
- **7GB d'espace disque** (pour les modèles TTS et les ressources audio)

## Installation Rapide

### 1. Installer uv (Recommandé)

```powershell
# Via PowerShell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Ou téléchargez depuis : https://docs.astral.sh/uv/

### 2. Configuration Initiale

```powershell
# Naviguez vers le répertoire du projet
cd C:\Users\bilal\Downloads\airborne-main\airborne-main

# Activez l'environnement virtuel
.\.venv\Scripts\Activate.ps1

# Lancez le script de configuration Windows
.\scripts\setup_windows.ps1
```

Ce script va :
- ✓ Vérifier l'environnement virtuel Python
- ✓ Installer toutes les dépendances depuis `pyproject.toml`
- ✓ Vérifier la présence des fichiers de configuration
- ✓ Tester les imports Python de base

### 3. Installer Kokoro TTS (Recommandé)

```powershell
# Installer Kokoro TTS avec tous les modèles
.\scripts\install_kokoro.ps1
```

Ce script va :
- ✓ Installer `kokoro-onnx` et `soundfile`
- ✓ Télécharger les modèles ONNX (~337MB)
- ✓ Télécharger les embeddings de voix (~27MB)
- ✓ Vérifier l'installation

**Téléchargement total** : ~337MB (peut prendre quelques minutes)

### 4. Tester l'Installation

```powershell
# Tester Kokoro TTS
python scripts\test_kokoro.py

# Lister les voix disponibles
python scripts\generate_speech.py --list

# Écouter toutes les voix (19 voix)
python scripts\listen_voices_auto.py
```

## Utilisation

### Générer les Fichiers Audio TTS

```powershell
# Générer tous les fichiers audio (peut prendre du temps)
python scripts\generate_speech.py

# Générer uniquement la voix du pilote
python scripts\generate_speech.py pilot

# Régénérer tous les fichiers (même s'ils existent)
python scripts\generate_speech.py --clean
```

### Lancer les Démos

```powershell
# Démo du pilote automatique
python scripts\demo_autopilot.py

# Démo des opérations au sol
python scripts\demo_ground_ops.py

# Démo des opérations au sol avec audio
python scripts\demo_ground_ops_audio.py
```

### Lancer le Simulateur Principal

```powershell
# Lancer AirBorne
python src\airborne\main.py
```

## Configuration TTS

### Option 1 : Kokoro TTS (Recommandé)

**Avantages** :
- ✓ Haute qualité audio
- ✓ 19 voix anglaises (11 féminines, 8 masculines)
- ✓ Génération rapide (~3-8x temps réel)
- ✓ Fonctionne hors ligne
- ✓ Idéal pour simulateur de vol

**Fichier** : `config\speech.yaml` (déjà configuré)

Le fichier utilise ces voix par défaut :
- **Pilote** : `af_bella` (female, claire et professionnelle)
- **Cockpit** : `af_sarah` (female, constante et robotique)
- **ATC Ground/Tower** : `am_adam` (male, professionnel)
- **ATC Approach** : `am_michael` (male, chaleureux)
- **ATIS** : `af_sarah` (female, robotique)

### Option 2 : pyttsx3 (TTS Windows Natif)

**Avantages** :
- ✓ Pas de téléchargement
- ✓ Utilise les voix Windows natives
- ✓ Léger et rapide à installer

**Inconvénients** :
- ✗ Qualité audio inférieure
- ✗ Moins de choix de voix
- ✗ Son moins naturel

**Pour utiliser pyttsx3** :

1. Modifiez `config\speech.yaml` :
   - Décommentez la section `# Fallback configuration for pyttsx3`
   - Commentez la section Kokoro (lignes 13-59)

2. Installez pyttsx3 (si pas déjà fait) :
   ```powershell
   pip install pyttsx3
   ```

3. Testez :
   ```powershell
   python scripts\test_pyttsx3.py
   ```

## Résolution de Problèmes

### Erreur : "Configuration file not found: config\speech.yaml"

**Solution** :
```powershell
# Vérifiez que le fichier existe
Test-Path .\config\speech.yaml

# Si False, le fichier de configuration a été créé par ce guide
# Assurez-vous d'être dans le bon répertoire
cd C:\Users\bilal\Downloads\airborne-main\airborne-main
```

### Erreur : "ModuleNotFoundError: No module named 'kokoro_onnx'"

**Solution** :
```powershell
# Réinstallez Kokoro
.\scripts\install_kokoro.ps1

# OU installez manuellement
pip install kokoro-onnx soundfile
```

### Erreur : "FileNotFoundError: Model files not found"

**Solution** :
```powershell
# Vérifiez la présence des modèles
Test-Path .\assets\models\kokoro-v1.0.onnx
Test-Path .\assets\models\voices-v1.0.bin

# Si False, retéléchargez les modèles
.\scripts\install_kokoro.ps1
```

Les fichiers devraient être :
- `kokoro-v1.0.onnx` : ~310MB
- `voices-v1.0.bin` : ~27MB

### Erreur : "RuntimeError: Pyfmodex could not find the fmod library"

**Cause** : Les DLL FMOD ne sont pas installées pour Windows.

**Solution** :

1. Téléchargez FMOD Engine 2.2.22 :
   - Visitez : https://www.fmod.com/download
   - Créez un compte gratuit si nécessaire
   - Téléchargez "FMOD Engine" pour Windows

2. Extrayez les DLL :
   - Ouvrez l'archive téléchargée
   - Trouvez `fmod.dll` et `fmodL.dll` dans `api/core/lib/x64/`

3. Copiez les DLL :
   ```powershell
   # Créez le répertoire si nécessaire
   New-Item -ItemType Directory -Path "lib\windows\x64" -Force
   
   # Copiez les DLL (ajustez le chemin source)
   Copy-Item "C:\Téléchargements\fmodstudioapi\api\core\lib\x64\fmod.dll" -Destination "lib\windows\x64\"
   Copy-Item "C:\Téléchargements\fmodstudioapi\api\core\lib\x64\fmodL.dll" -Destination "lib\windows\x64\"
   ```

4. Vérifiez :
   ```powershell
   Test-Path .\lib\windows\x64\fmod.dll
   Test-Path .\lib\windows\x64\fmodL.dll
   ```

### Audio ne se joue pas dans listen_voices_auto.py

**Solution** : Le script a été modifié pour Windows. Si le problème persiste :

```powershell
# Testez avec le script de test Kokoro
python scripts\test_kokoro.py

# Le fichier audio est sauvegardé dans C:\Users\...\AppData\Local\Temp\
# Vous pouvez le lire manuellement pour vérifier que la génération fonctionne
```

## Voix Disponibles (Kokoro)

### Voix Féminines (11)
- `af_alloy` - Neutre, versatile
- `af_aoede` - Chaleureuse, amicale
- `af_bella` ⭐ - Claire, professionnelle (voix pilote par défaut)
- `af_heart` - Émotionnelle, expressive
- `af_jessica` - Confiante, autoritaire
- `af_kore` - Calme, rassurante
- `af_nicole` - Brillante, énergique
- `af_nova` - Moderne, nette
- `af_river` - Douce, fluide
- `af_sarah` ⭐ - Professionnelle, claire (voix cockpit par défaut)
- `af_sky` - Aérienne, légère

### Voix Masculines (8)
- `am_adam` ⭐ - Professionnelle, claire (voix ATC par défaut)
- `am_echo` - Profonde, résonnante
- `am_eric` - Amicale, accessible
- `am_fenrir` - Forte, autoritaire
- `am_liam` - Douce, conversationnelle
- `am_michael` ⭐ - Chaleureuse, digne de confiance
- `am_onyx` - Riche, profonde
- `am_puck` - Joueuse, énergique

⭐ = Recommandée pour AirBorne

## Performances

Sur un PC Windows moderne (16GB RAM, SSD) :
- **Initialisation Kokoro** : ~0.3-0.5s (une fois)
- **Première génération** : ~3x plus rapide que temps réel
- **Générations suivantes** : ~8x plus rapide que temps réel
- **Génération complète de toutes les voix** : ~30-60 minutes (selon CPU)

## Structure des Fichiers Audio

```
data/
├── speech/
│   ├── en/                    # Voix cockpit (instruments)
│   │   ├── MSG_ALTITUDE.wav
│   │   ├── MSG_AIRSPEED.wav
│   │   └── number_0_autogen.wav ... number_1000_autogen.wav
│   ├── pilot/en/              # Voix pilote
│   │   ├── MSG_CHALLENGE_*.wav
│   │   ├── MSG_RESPONSE_*.wav
│   │   └── MSG_NUMBER_*.wav
│   └── atc/en/                # Voix ATC
│       ├── ATC_GROUND_*.wav
│       ├── ATC_TOWER_*.wav
│       └── ATC_APPROACH_*.wav
└── sounds/                     # Effets sonores
    ├── aircraft/
    ├── airport/
    └── environment/
```

## Ressources Supplémentaires

- **Documentation Kokoro** : `scripts\README_KOKORO.md`
- **Configuration TTS** : `config\speech.yaml`
- **Documentation Principale** : `README.md`

## Support

Si vous rencontrez des problèmes non couverts par ce guide :

1. Vérifiez les logs dans `log.txt`
2. Activez le mode debug dans `config\logging.yaml`
3. Consultez la documentation du projet
4. Signaler les bugs sur GitHub

---

**Bon vol ! ✈️**

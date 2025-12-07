# Guide Rapide - AirBorne Windows

## ⚠️ IMPORTANT : Répertoire de Travail

**Exécutez TOUJOURS les scripts depuis le répertoire racine du projet, PAS depuis `scripts/` !**

### ✅ Correct :
```powershell
cd C:\Users\bilal\Downloads\airborne-main\airborne-main
python scripts\test_kokoro.py
python scripts\generate_speech.py
python scripts\listen_voices_auto.py
```

### ❌ Incorrect :
```powershell
cd scripts
python test_kokoro.py  # ❌ Ne fonctionne pas !
```

## Installation Rapide

```powershell
# 1. Activer l'environnement virtuel
.\.venv\Scripts\activate

# 2. Installer Kokoro TTS
.\scripts\install_kokoro.ps1

# 3. Tester
python scripts\test_kokoro.py
```

## Commandes Principales

Depuis `C:\Users\bilal\Downloads\airborne-main\airborne-main` :

```powershell
# Tester Kokoro
python scripts\test_kokoro.py

# Lister les voix
python scripts\generate_speech.py --list

# Écouter toutes les voix
python scripts\listen_voices_auto.py

# Générer tous les fichiers audio
python scripts\generate_speech.py

# Générer seulement la voix pilote
python scripts\generate_speech.py pilot
```

## Résolution de Problèmes

### "config\speech.yaml not found"
```powershell
# Vérifiez que vous êtes dans le bon répertoire
cd C:\Users\bilal\Downloads\airborne-main\airborne-main
Test-Path config\speech.yaml  # Devrait retourner True
```

### "ModuleNotFoundError: kokoro_onnx"
```powershell
# Réinstallez dans le venv
.\.venv\Scripts\activate
.\scripts\install_kokoro.ps1
```

### "Voices file not found"
```powershell
# Vérifiez que les modèles existent
Test-Path assets\models\kokoro-v1.0.onnx     # True
Test-Path assets\models\voices-v1.0.bin      # True

# Si False, retéléchargez
.\scripts\install_kokoro.ps1
```

## Structure des Répertoires

```
airborne-main\
├── .venv\                  # Environnement virtuel Python
├── assets\
│   └── models\             # ⚠️ Modèles Kokoro ICI
│       ├── kokoro-v1.0.onnx (310MB)
│       └── voices-v1.0.bin (27MB)
├── config\                 # ⚠️ Configs ICI
│   └── speech.yaml
├── scripts\                # Scripts à exécuter DEPUIS LA RACINE
│   ├── test_kokoro.py
│   ├── generate_speech.py
│   └── listen_voices_auto.py
└── data\                   # Fichiers audio générés
    └── speech\
```

## Documentation Complète

Consultez `docs\WINDOWS_SETUP.md` pour le guide complet.

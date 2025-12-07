#!/usr/bin/env python3
"""
Script de test pour les voix françaises Kokoro TTS

Teste et joue toutes les voix françaises disponibles dans Kokoro.
"""

import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import soundfile as sf
from kokoro_onnx import Kokoro

# Auto-detect project root
SCRIPT_DIR = Path(__file__).resolve().parent
if SCRIPT_DIR.name == "scripts":
    PROJECT_ROOT = SCRIPT_DIR.parent
else:
    PROJECT_ROOT = SCRIPT_DIR

os.chdir(PROJECT_ROOT)

# Voix françaises disponibles dans Kokoro
# Format: (nom_voix, description)
FRENCH_VOICES = [
    ("af_bella", "Femme - Claire et professionnelle"),
    ("af_sarah", "Femme - Professionnelle et constante"),
    ("af_nicole", "Femme - Brillante et énergique"),
    ("am_adam", "Homme - Professionnel et clair"),
    ("am_michael", "Homme - Chaleureux et digne de confiance"),
]

# Texte de test en français
SAMPLE_TEXT = (
    "Bonjour, voici un test de synthèse vocale en français avec Kokoro. "
    "La qualité audio est excellente pour un simulateur de vol."
)


def play_audio(audio_file):
    """Joue un fichier audio avec le lecteur approprié à la plateforme."""
    system = platform.system()
    
    try:
        if system == "Darwin":  # macOS
            subprocess.run(["afplay", str(audio_file)], check=True)
        elif system == "Windows":
            subprocess.run(
                ["powershell", "-c", f"(New-Object Media.SoundPlayer '{audio_file}').PlaySync()"],
                check=True
            )
        else:  # Linux
            players = ["aplay", "paplay", "ffplay"]
            for player in players:
                try:
                    subprocess.run([player, str(audio_file)], check=True, stderr=subprocess.DEVNULL)
                    return
                except FileNotFoundError:
                    continue
            print(f"Avertissement : Aucun lecteur audio trouvé. Fichier sauvegardé : {audio_file}")
    except Exception as e:
        print(f"Avertissement : Impossible de lire l'audio : {e}")
        print(f"Fichier audio sauvegardé : {audio_file}")


def main():
    """Teste les voix françaises."""
    print("\n" + "=" * 70)
    print("Test des Voix Françaises Kokoro TTS")
    print("=" * 70)
    print(f'\nTexte de test : "{SAMPLE_TEXT}"')
    print(f"\nTest de {len(FRENCH_VOICES)} voix en français...")
    print("Appuyez sur Ctrl+C pour arrêter\n")

    # Initialiser Kokoro
    print("Initialisation de Kokoro...")
    try:
        kokoro = Kokoro(
            model_path="assets/models/kokoro-v1.0.onnx",
            voices_path="assets/models/voices-v1.0.bin"
        )
        print("✓ Kokoro initialisé!\n")
    except Exception as e:
        print(f"[ERROR] Impossible d'initialiser Kokoro : {e}")
        return 1

    # Créer un répertoire temporaire pour les fichiers audio
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        try:
            for i, (voice, description) in enumerate(FRENCH_VOICES, 1):
                print(f"[{i}/{len(FRENCH_VOICES)}] 🔊 {voice:12} - {description}")

                # Générer l'audio en français
                try:
                    samples, sample_rate = kokoro.create(
                        SAMPLE_TEXT, 
                        voice=voice, 
                        lang="fr-fr"  # Code langue pour le français
                    )
                except Exception as e:
                    print(f"    ⚠ Erreur de génération : {e}")
                    continue

                # Sauvegarder dans un fichier temporaire
                temp_file = temp_path / f"{voice}_fr.wav"
                sf.write(str(temp_file), samples, sample_rate)

                # Jouer l'audio
                play_audio(temp_file)

                # Pause brève avant la voix suivante
                if i < len(FRENCH_VOICES):
                    time.sleep(1)

            print("\n" + "=" * 70)
            print(f"✓ {len(FRENCH_VOICES)} voix françaises testées !")
            print("=" * 70 + "\n")

        except KeyboardInterrupt:
            print("\n\n✓ Arrêté par l'utilisateur\n")
            return 0
        except Exception as e:
            print(f"\n✗ Erreur : {e}")
            import traceback
            traceback.print_exc()
            return 1

    return 0


if __name__ == "__main__":
    exit(main())

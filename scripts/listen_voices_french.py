#!/usr/bin/env python3
"""
Kokoro TTS - French Voice Listener

Écoute automatique de toutes les voix françaises disponibles.
Appuyez sur Ctrl+C pour arrêter.
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

# Auto-detect project root (handles running from scripts/ or project root)
SCRIPT_DIR = Path(__file__).resolve().parent
if SCRIPT_DIR.name == "scripts":
    PROJECT_ROOT = SCRIPT_DIR.parent
else:
    PROJECT_ROOT = SCRIPT_DIR

# Change to project root so relative paths work
os.chdir(PROJECT_ROOT)

# All available voices
VOICES = [
    # Female
    ("af_alloy", "Female - Neutral"),
    ("af_aoede", "Female - Warm"),
    ("af_bella", "Female - Professional ⭐"),
    ("af_heart", "Female - Expressive"),
    ("af_jessica", "Female - Confident"),
    ("af_kore", "Female - Calm"),
    ("af_nicole", "Female - Energetic"),
    ("af_nova", "Female - Modern"),
    ("af_river", "Female - Smooth"),
    ("af_sarah", "Female - Neutral ⭐"),
    ("af_sky", "Female - Light"),
    # Male
    ("am_adam", "Male - Professional ⭐"),
    ("am_echo", "Male - Deep"),
    ("am_eric", "Male - Friendly"),
    ("am_fenrir", "Male - Strong"),
    ("am_liam", "Male - Smooth"),
    ("am_michael", "Male - Warm ⭐"),
    ("am_onyx", "Male - Rich"),
    ("am_puck", "Male - Playful"),
]

# Texte de test en français aviation
SAMPLE_TEXT = (
    "Tour de contrôle Palo Alto, Cessna un deux trois alpha bravo, "
    "prêt pour le départ piste trois un."
)


def play_audio(audio_file):
    """Joue un fichier audio avec le lecteur approprié à la plateforme."""
    system = platform.system()
    
    try:
        if system == "Darwin":  # macOS
            subprocess.run(["afplay", str(audio_file)], check=True)
        elif system == "Windows":
            # Use Windows Media Player via PowerShell
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
            print(f"Avertissement : Aucun lecteur audio trouvé. Fichier : {audio_file}")
    except Exception as e:
        print(f"Avertissement : Impossible de lire l'audio : {e}")


def main():
    """Écoute toutes les voix françaises."""
    print("\n" + "=" * 70)
    print("Kokoro TTS - French Voice Listener")
    print("=" * 70)
    print(f'\nTexte: "{SAMPLE_TEXT}"')
    print(f"\nÉcoute automatique de {len(VOICES)} voix en français...")
    print("Appuyez sur Ctrl+C pour arrêter\n")

    # Initialize Kokoro
    print("Initialisation de Kokoro...")
    try:
        kokoro = Kokoro(
            model_path="assets/models/kokoro-v1.0.onnx",
            voices_path="assets/models/voices-v1.0.bin"
        )
        print("✓ Prêt!\n")
    except Exception as e:
        print(f"✗ Erreur d'initialisation : {e}")
        return 1

    # Create temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        try:
            for i, (voice, description) in enumerate(VOICES, 1):
                print(f"[{i}/{len(VOICES)}] 🔊 {voice:12} - {description}")

                # Generate French audio
                try:
                    samples, sample_rate = kokoro.create(
                        SAMPLE_TEXT, 
                        voice=voice, 
                        lang="fr-fr"
                    )
                except Exception as e:
                    print(f"✗ Erreur: {e}\n")
                    continue

                # Save to temp file
                temp_file = temp_path / f"{voice}_fr.wav"
                sf.write(str(temp_file), samples, sample_rate)

                # Play audio using cross-platform function
                play_audio(temp_file)

                # Small pause between voices
                if i < len(VOICES):
                    time.sleep(1)
            print("\n" + "=" * 70)
            print(f"✓ Toutes les {len(VOICES)} voix françaises jouées!")
            print("=" * 70 + "\n")

        except KeyboardInterrupt:
            print("\n\n✓ Arrêté par l'utilisateur\n")
            return 0
        except Exception as e:
            print(f"\n✗ Erreur: {e}")
            import traceback

            traceback.print_exc()
            return 1

    return 0


if __name__ == "__main__":
    exit(main())

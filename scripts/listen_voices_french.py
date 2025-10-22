#!/usr/bin/env python3
"""
Kokoro TTS French Voice Listener

Listen to all 19 voices speaking French aviation phrases.
"""

import subprocess
import tempfile
import soundfile as sf
from pathlib import Path
from kokoro_onnx import Kokoro


# All available voices
VOICES = [
    # Female
    ('af_alloy', 'Female - Neutral'),
    ('af_aoede', 'Female - Warm'),
    ('af_bella', 'Female - Professional ⭐'),
    ('af_heart', 'Female - Expressive'),
    ('af_jessica', 'Female - Confident'),
    ('af_kore', 'Female - Calm'),
    ('af_nicole', 'Female - Energetic'),
    ('af_nova', 'Female - Modern'),
    ('af_river', 'Female - Smooth'),
    ('af_sarah', 'Female - Neutral ⭐'),
    ('af_sky', 'Female - Light'),
    # Male
    ('am_adam', 'Male - Professional ⭐'),
    ('am_echo', 'Male - Deep'),
    ('am_eric', 'Male - Friendly'),
    ('am_fenrir', 'Male - Strong'),
    ('am_liam', 'Male - Smooth'),
    ('am_michael', 'Male - Warm ⭐'),
    ('am_onyx', 'Male - Rich'),
    ('am_puck', 'Male - Playful'),
]

# French aviation sample text
SAMPLE_TEXT = "Tour de contrôle Palo Alto, Cessna un deux trois alpha bravo, prêt pour le départ piste trois un."


def main():
    """Main entry point."""
    print("\n" + "="*70)
    print("Kokoro TTS - French Voice Listener")
    print("="*70)
    print(f"\nTexte: \"{SAMPLE_TEXT}\"")
    print(f"\nÉcoute automatique de {len(VOICES)} voix en français...")
    print("Appuyez sur Ctrl+C pour arrêter\n")

    # Initialize Kokoro
    print("Initialisation de Kokoro...")
    kokoro = Kokoro(
        model_path="assets/models/kokoro-v1.0.onnx",
        voices_path="assets/models/voices-v1.0.bin"
    )
    print("✓ Prêt!\n")

    # Create temp directory for audio files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        try:
            for i, (voice, description) in enumerate(VOICES, 1):
                print(f"[{i}/{len(VOICES)}] 🔊 {voice:12} - {description}")

                # Generate French audio
                samples, sample_rate = kokoro.create(
                    SAMPLE_TEXT,
                    voice=voice,
                    lang='fr-fr'  # French!
                )

                # Save to temp file
                temp_file = temp_path / f"{voice}.wav"
                sf.write(str(temp_file), samples, sample_rate)

                # Play with afplay
                subprocess.run(['afplay', str(temp_file)], check=True)

                # Brief pause before next voice
                if i < len(VOICES):
                    import time
                    time.sleep(1)

            print("\n" + "="*70)
            print(f"✓ Toutes les {len(VOICES)} voix françaises jouées!")
            print("="*70 + "\n")

        except KeyboardInterrupt:
            print("\n\n✓ Arrêté par l'utilisateur\n")
            return 0
        except Exception as e:
            print(f"\n✗ Erreur: {e}")
            import traceback
            traceback.print_exc()
            return 1

    return 0


if __name__ == '__main__':
    exit(main())

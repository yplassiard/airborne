# Kokoro TTS Model Files

This directory contains the ONNX model files for Kokoro TTS.

## Files

- `kokoro-v1.0.onnx` (310MB) - Main TTS model
- `voices-v1.0.bin` (27MB) - Voice embeddings for 19 English voices

## Installation

These files are automatically downloaded when you run:

```bash
./scripts/install_kokoro.sh
```

## Manual Download

If you need to download manually:

```bash
# Download main model
curl -L -o assets/models/kokoro-v1.0.onnx \
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx

# Download voices
curl -L -o assets/models/voices-v1.0.bin \
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
```

## Verification

After downloading, verify the installation works:

```bash
uv run python scripts/test_kokoro.py
```

You should see output like:
```
Testing Kokoro ONNX TTS installation...
Initializing Kokoro with ONNX models...
✓ Initialized in 0.23s
Generating test audio with af_bella voice...
✓ Generated in 1.42s (4.18s audio, 2.9x realtime)
✓ Installation verified!
```

## Storage

Total size: ~337MB

These files are excluded from git (see `.gitignore`) to keep the repository size manageable.

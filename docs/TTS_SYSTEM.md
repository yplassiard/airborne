# AirBorne TTS System Documentation

## Overview

AirBorne uses a unified speech generation system that supports multiple voice types for different contexts (pilot, cockpit, ATC, etc.). The system automatically generates TTS files using platform-native engines and organizes them in a coherent directory structure.

## Architecture

### Configuration

All voice types and messages are defined in `config/speech.yaml`:

```yaml
voices:
  pilot:        # Pilot transmissions and checklist readbacks
  cockpit:      # Instrument readouts and system announcements
  ground:       # Ground control / Clearance delivery
  tower:        # Tower control
  approach:     # Approach/Departure control
  atis:         # Automated Terminal Information
  steward:      # Flight attendant / cabin crew

messages:
  MSG_KEY:
    text: "Text to speak"
    voice: pilot  # Which voice to use
```

### Directory Structure

```
data/speech/
└── en/                          # Language code
    ├── pilot/                   # Pilot voice files
    │   ├── MSG_CHECKLIST_*.mp3
    │   ├── MSG_CHALLENGE_*.mp3
    │   └── MSG_RESPONSE_*.mp3
    ├── cockpit/                 # Cockpit voice files
    │   ├── MSG_STARTUP.mp3
    │   ├── MSG_NUMBER_*.mp3
    │   └── MSG_ATC_MENU_*.mp3
    └── atc/                     # ATC voice files
        ├── ground/
        ├── tower/
        └── approach/
```

## Speech Generation

### Universal Generation Script

Use `scripts/generate_speech.py` to generate TTS files:

```bash
# List available voices
python scripts/generate_speech.py --list

# Generate all voices
python scripts/generate_speech.py

# Generate specific voices only
python scripts/generate_speech.py pilot cockpit

# Clean and regenerate all
python scripts/generate_speech.py --clean

# Generate for different language
python scripts/generate_speech.py --language fr
```

### Platform Support

**macOS**: Uses `say` command with native voices
- Requires: macOS system voices (Oliver, Samantha, Evan, etc.)
- Output: AIFF → MP3 (with ffmpeg) or AIFF (without)

**Windows/Linux**: Uses pyttsx3 library
- Install: `pip install pyttsx3`
- Output: WAV → MP3 (with ffmpeg) or WAV (without)

### Voice Configuration

Each voice type has these settings:

```yaml
voice_name:
  description: "Human-readable description"
  engine: "say"           # TTS engine: "say" or "pyttsx3"
  language: en-US         # Language/locale code
  voice_name: "Oliver"    # Platform-specific voice name
  rate: 200               # Words per minute
  volume: 1.0             # Volume level (0.0 to 1.0)
  output_dir: "pilot"     # Subdirectory under data/speech/<lang>/
```

### Message Configuration

Messages map keys to text and voice type:

```yaml
messages:
  MSG_STARTUP:
    text: "airborne flight simulator"
    voice: cockpit

  MSG_CHECKLIST_STARTING:
    text: "starting checklist"
    voice: pilot
```

### Dynamic Checklist Messages

Checklist challenges and responses are automatically extracted from `config/checklists/*.yaml` and generated with the pilot voice:

- `MSG_CHALLENGE_*` - Extracted from checklist challenge fields
- `MSG_RESPONSE_*` - Extracted from checklist response fields

## Audio Provider Integration

The `AudioSpeechProvider` class automatically:

1. Loads `config/speech.yaml` at startup
2. Maps voice types to directories
3. Resolves message keys to file paths using voice directories
4. Falls back to old `config/speech_en.yaml` format if needed

### File Resolution

For message key `MSG_STARTUP` with voice `cockpit`:
1. Look up message in config → voice = "cockpit"
2. Resolve voice directory → `data/speech/en/cockpit/`
3. Build filename → `MSG_STARTUP.mp3`
4. Final path → `data/speech/en/cockpit/MSG_STARTUP.mp3`

## Usage in Code

### Adding New Messages

1. Add to `config/speech.yaml`:
```yaml
messages:
  MSG_NEW_MESSAGE:
    text: "your message text"
    voice: cockpit  # or pilot, ground, etc.
```

2. Generate TTS file:
```bash
python scripts/generate_speech.py cockpit
```

3. Use in code:
```python
message_queue.publish(Message(
    sender="my_plugin",
    recipients=["*"],
    topic=MessageTopic.TTS_SPEAK,
    data={"text": "MSG_NEW_MESSAGE"},
))
```

### Multiple Messages

Speak a sequence of messages:
```python
data={"text": ["MSG_FIRST", "MSG_SECOND", "MSG_THIRD"]}
```

The audio provider will play them sequentially with natural timing.

## Voice Assignment Guidelines

- **pilot**: Radio transmissions, checklist readbacks, pilot actions
- **cockpit**: Instrument readouts, system status, menu navigation
- **ground**: Ground control communications
- **tower**: Tower control communications
- **approach**: Approach/departure control communications
- **atis**: Automated weather/airport information
- **steward**: Cabin announcements, safety briefings

## Migration from Old System

The old system used:
- Individual generation scripts: `scripts/generate_*_tts.py`
- Flat file structure: `data/speech/en/*.mp3`
- Separate configs: `config/speech_en.yaml`, `config/atc_en.yaml`

The new system:
- Single generation script: `scripts/generate_speech.py`
- Voice-based structure: `data/speech/en/<voice>/*.mp3`
- Unified config: `config/speech.yaml`

**Backward Compatibility**: The audio provider automatically falls back to old format if `config/speech.yaml` doesn't exist.

## Testing

Test the TTS system in-game:
- **F1**: Open ATC menu (cockpit voice for menu, pilot for transmissions)
- **F2**: Open checklist menu (cockpit voice for menu, pilot for challenges/responses)
- **Instrument keys**: Hear cockpit voice readouts

## Troubleshooting

### Files not found
- Check `data/speech/en/<voice>/MSG_*.mp3` exists
- Regenerate: `python scripts/generate_speech.py --clean`

### Wrong voice
- Check `config/speech.yaml` message voice assignment
- Regenerate affected voice

### No audio on Windows/Linux
- Install pyttsx3: `pip install pyttsx3`
- Check platform has TTS voices available

### Poor audio quality
- Install ffmpeg for MP3 conversion: `brew install ffmpeg` (macOS)
- Adjust voice rate/volume in `config/speech.yaml`

## Future Enhancements

- [ ] Support for additional languages (config/speech_fr.yaml, etc.)
- [ ] Voice gender/age selection
- [ ] Custom voice profiles per aircraft type
- [ ] Cloud TTS integration (Google, Azure, AWS)
- [ ] Voice effects (radio filter, reverb, etc.)
- [ ] Pronunciation dictionary for aviation terms

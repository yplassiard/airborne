# AirBorne Flight Simulator

A blind-accessible flight simulator with self-voicing capabilities, realistic physics, and comprehensive aircraft systems simulation. Designed for maximum accessibility without compromising realism.

## Features

### Core Systems
- **Fully Accessible**: Complete self-voicing with TTS, no visual interface required
- **Realistic Physics**: 6DOF flight model with authentic aerodynamics and flight dynamics
- **Modular Plugin Architecture**: Extensible system for adding new features and aircraft
- **Complete Aircraft Systems**:
  - Simple piston engine with magnetos, starter, mixture control
  - Electrical system with battery and alternator
  - Fuel system with multiple tanks and fuel pump
  - Flight instruments (airspeed, altitude, vertical speed)

### Flight Operations
- **Interactive Checklists**: Step-by-step procedures with auto-verification for realistic workflows
- **Control Panel Navigation**: Hierarchical panel system (Instrument Panel, Pedestal, Engine Controls, Overhead, Flight Controls)
- **Audio Feedback**: Realistic sounds for all controls, switches, engine, wind, and aircraft systems
- **Autopilot**: Basic autopilot with phase-based operation (taxi, takeoff, climb, cruise, descent, landing)

### Navigation & ATC
- **Airport Database**: 9,220 airports worldwide with runways and frequencies
- **Ground Navigation**: Taxiway guidance with audio cues (planned)
- **ATC Communications**:
  - Context-aware ATC menu system with flight phase detection
  - Realistic radio phraseology (ICAO standard)
  - Readback system with critical element validation
  - Radio effects (VHF AM simulation with DSP filtering)
  - ATIS announcements
- **AI Traffic & TCAS**: Simulated aircraft with collision avoidance

### Audio Systems
- **Multi-Voice TTS**: 7 different voice types (pilot, cockpit, ground, tower, approach, ATIS, steward)
- **Professional Sound Effects**: 28 aircraft sounds imported from professional simulators
- **FMOD Audio Engine**: Advanced 3D positional audio and DSP effects
- **Radio Effects**: Authentic VHF AM radio simulation with static, crackles, and PTT beeps

### Additional Features
- **Ground Services**: Refueling, pushback, boarding/deboarding
- **Weight & Balance**: Realistic weight calculations affecting performance
- **Terrain Collision Detection**: CFIT prevention system
- **Platform-Aware Logging**: Automatic log rotation with platform-specific locations

## Requirements

### System Requirements
- **Python**: 3.11 or higher
- **Operating System**: Windows, macOS, or Linux
- **Package Manager**: UV (recommended) or pip

### Runtime Dependencies
All Python dependencies are automatically managed by UV. Key libraries include:
- pygame (display and input)
- pyfmodex (3D audio engine)
- pybass3 (alternative audio backend)
- pydub (audio processing)
- pyttsx3 (TTS on Windows/Linux)

## Quick Start (Running from Source)

### 1. Install UV Package Manager

**macOS/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:**
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Clone and Run

```bash
# Clone repository
git clone https://github.com/yourusername/airborne.git
cd airborne

# Install dependencies (automatic with UV)
uv sync

# Run the simulator
uv run python src/airborne/main.py
```

### 3. First Flight

On startup, you'll spawn at Palo Alto Airport (KPAO) on the ramp with a Cessna 172.

**Basic Start Procedure:**
1. **F2** - Open checklist menu
2. **Up/Down arrows** - Navigate to "Before Engine Start" checklist
3. **Return or Tab** - Select checklist
4. **Ctrl+1** - Navigate to Instrument Panel
5. **M** - Turn on master switch (battery)
6. **Ctrl+2** - Navigate to Pedestal panel
7. **P** - Turn on fuel pump
8. **F2** - Return to checklist menu and complete "Engine Start" checklist
9. **Ctrl+3** - Navigate to Engine Controls panel
10. **S** - Hold starter button until engine starts

**Flight Controls:**
- **Arrow keys** - Pitch (up/down) and roll (left/right)
- **Comma/Period** - Rudder (yaw left/right)
- **Page Up/Down** - Throttle (increase/decrease)
- **Home/End** - Elevator trim (up/down)

**Menus:**
- **F1** - ATC menu (clearances and communications)
- **F2** - Checklist menu (procedures)
- **F3** - Ground services menu (refuel, pushback, boarding)
- **Escape** - Close current menu

**Control Panels:**
- **Ctrl+1** - Instrument Panel (master, avionics, lights)
- **Ctrl+2** - Pedestal (mixture, throttle, fuel)
- **Ctrl+3** - Engine Controls (magnetos, starter)
- **Ctrl+4** - Overhead Panel (pitot heat)
- **Ctrl+5** - Flight Controls (flaps, trim, brakes)

See `config/input_bindings/` for complete key binding reference.

## Building Standalone Applications

AirBorne can be packaged as a standalone application for distribution.

### Prerequisites

1. **Install build dependencies:**
   ```bash
   uv sync  # Installs PyInstaller automatically
   ```

2. **Install FFmpeg** (optional, for better audio quality):
   - **macOS:** `brew install ffmpeg`
   - **Linux:** `sudo apt install ffmpeg` or `sudo yum install ffmpeg`
   - **Windows:** Download from https://ffmpeg.org/download.html

### Build Commands

```bash
# Build for your current platform
./scripts/build_app.sh

# Build for specific platform
./scripts/build_app.sh macos     # Creates .app bundle
./scripts/build_app.sh linux     # Creates .tgz archive
./scripts/build_app.sh windows   # Creates NSIS installer (Windows only)

# Build for all platforms
./scripts/build_app.sh all
```

### Output Locations

- **macOS:** `dist/AirBorne.app` (double-click to run)
- **Linux:** `dist/AirBorne.tgz` (extract and run `./AirBorne`)
- **Windows:** `dist/AirBorne-Setup.exe` (run installer)

### What Gets Included

The build process automatically bundles:
- All Python dependencies
- Audio files (sounds, TTS messages)
- Configuration files (aircraft, checklists, panels)
- Airport and navigation databases
- Platform-specific audio libraries (FMOD, BASS)

### Platform-Specific Notes

**macOS:**
- Code signing is disabled by default
- App may require "Open Anyway" in Security & Privacy settings on first run

**Windows:**
- Requires NSIS installed for installer creation
- Antivirus may flag the executable (false positive)

**Linux:**
- Requires appropriate system TTS voices installed (see Speech Generation below)

## Speech Generation

AirBorne uses pre-recorded TTS messages for cockpit announcements, ATC communications, and instrument readouts. You need to generate these audio files before running the simulator.

### Installing System Voices

**macOS:**
```bash
# System voices are pre-installed
# Check available voices:
say -v ?

# Recommended voices (already installed):
# - Samantha (cockpit/instruments)
# - Oliver (pilot radio)
# - Evan (ATC)
```

**Windows:**
```powershell
# Install additional voices from Windows Settings:
# Settings → Time & Language → Speech → Manage voices → Add voices

# Recommended: Install "English (United States)" voices
# Common voices: David, Zira, Mark

# Install pyttsx3 (if not already installed):
pip install pyttsx3
```

**Linux (Ubuntu/Debian):**
```bash
# Install espeak-ng for TTS
sudo apt install espeak-ng

# Install pyttsx3
pip install pyttsx3

# Optional: Install festival for better voices
sudo apt install festival festvox-kallpc16k
```

**Linux (Fedora/RHEL):**
```bash
sudo dnf install espeak-ng
pip install pyttsx3
```

### Generating Speech Files

```bash
# List available voices on your system
python scripts/generate_speech.py --list

# Generate all speech files (recommended for first run)
python scripts/generate_speech.py

# Generate specific voice types only
python scripts/generate_speech.py cockpit pilot

# Clean old files and regenerate everything
python scripts/generate_speech.py --clean

# Generate for a different language (future feature)
python scripts/generate_speech.py --language fr
```

### Voice Configuration

Edit `config/speech.yaml` to customize voices:

```yaml
voices:
  pilot:
    description: "Pilot radio transmissions"
    engine: "say"              # "say" (macOS) or "pyttsx3" (Win/Linux)
    voice_name: "Oliver"       # System voice name
    rate: 200                  # Words per minute
    volume: 1.0                # 0.0 to 1.0
    output_dir: "pilot"        # Directory under data/speech/en/

  cockpit:
    description: "Cockpit instruments and announcements"
    engine: "say"
    voice_name: "Samantha"
    rate: 200
    volume: 1.0
    output_dir: "cockpit"

  # ... (ground, tower, approach, atis, steward)
```

### Voice Assignment Guidelines

- **pilot**: Radio transmissions, checklist readbacks, callouts
- **cockpit**: Instrument readouts, system status, menu navigation
- **ground**: Ground control communications
- **tower**: Tower control communications
- **approach**: Approach/departure control communications
- **atis**: Automated weather and airport information
- **steward**: Cabin announcements, safety briefings

### Adding Custom Messages

1. Edit `config/speech.yaml`:
   ```yaml
   messages:
     MSG_YOUR_MESSAGE:
       text: "your message text here"
       voice: cockpit  # Choose appropriate voice
   ```

2. Regenerate the voice:
   ```bash
   python scripts/generate_speech.py cockpit
   ```

3. Use in code:
   ```python
   message_queue.publish(Message(
       topic=MessageTopic.TTS_SPEAK,
       data={"text": "MSG_YOUR_MESSAGE"}
   ))
   ```

### Troubleshooting Speech

**No audio generated:**
- Verify TTS engine is installed (pyttsx3 on Windows/Linux)
- Check system has voices available: `python scripts/generate_speech.py --list`
- On Linux, ensure espeak-ng or festival is installed

**Wrong voice or poor quality:**
- Edit voice settings in `config/speech.yaml`
- Install FFmpeg for MP3 conversion (better compression)
- Adjust `rate` parameter (150-250 WPM recommended)

**Files not found at runtime:**
- Ensure speech files exist in `data/speech/en/<voice>/`
- Regenerate: `python scripts/generate_speech.py --clean`
- Check log files in `~/Library/Logs/AirBorne/` (macOS) for path errors

## Development

### Development Setup

```bash
# Clone and install
git clone https://github.com/yourusername/airborne.git
cd airborne
uv sync

# Run in development mode
uv run python src/airborne/main.py
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/airborne --cov-report=html

# Run specific test file
uv run pytest tests/core/test_event_bus.py

# Run with verbose output
uv run pytest -v
```

### Code Quality

All code must pass these checks before committing:

```bash
# Format code with Ruff
uv run ruff format .

# Lint and auto-fix
uv run ruff check . --fix

# Type check with mypy
uv run mypy src

# Quality check with pylint
uv run pylint src

# Run all checks
uv run ruff format . && uv run ruff check . --fix && uv run mypy src && uv run pytest
```

### Development Guidelines

See [CLAUDE.md](CLAUDE.md) for:
- Code style and standards
- Testing requirements (>80% coverage)
- Documentation standards (Google-style docstrings)
- Commit message format
- Development workflow

See [plan.md](plan.md) for:
- Implementation roadmap
- Phase-by-phase progress tracking
- Success criteria for each phase

### Project Structure

```
airborne/
├── src/airborne/          # Main source code
│   ├── core/              # Core systems (events, plugins, input)
│   ├── plugins/           # Plugin modules
│   │   ├── audio/         # Audio plugin (FMOD, TTS, sounds)
│   │   ├── radio/         # ATC and radio communications
│   │   ├── checklist/     # Interactive checklists
│   │   ├── panel/         # Control panel system
│   │   ├── engines/       # Engine simulations
│   │   ├── systems/       # Aircraft systems (electrical, fuel)
│   │   └── ...
│   ├── physics/           # Flight model and physics
│   ├── audio/             # Audio engines and managers
│   └── ui/                # User interface components
├── config/                # Configuration files
│   ├── aircraft/          # Aircraft definitions
│   ├── checklists/        # Checklist procedures
│   ├── panels/            # Panel layouts
│   ├── speech.yaml        # TTS voice and message config
│   └── input_bindings/    # Keyboard/joystick bindings
├── data/                  # Data files
│   ├── airports/          # Airport database (CSV)
│   ├── speech/            # Generated TTS files
│   └── aviation/          # Aviation data (callsigns, etc.)
├── assets/                # Media assets
│   └── sounds/            # Sound effects
├── scripts/               # Build and utility scripts
├── tests/                 # Unit tests
└── docs/                  # Documentation
```

## Logs and Troubleshooting

### Log Locations

- **macOS:** `~/Library/Logs/AirBorne/airborne.log`
- **Linux:** `~/.airborne/logs/airborne.log`
- **Windows:** `%AppData%/AirBorne/Logs/airborne.log`

Logs are rotated on each startup, keeping the last 5 launches.

### Common Issues

**App doesn't start:**
- Check logs for errors
- Ensure all dependencies are installed: `uv sync`
- Verify Python version: `python --version` (3.11+ required)

**No sound:**
- Check audio device is working
- Verify TTS files exist: `ls data/speech/en/cockpit/`
- Regenerate speech: `python scripts/generate_speech.py`

**Poor performance:**
- Reduce audio channels in `config/audio.yaml`
- Disable AI traffic in settings
- Run from source instead of bundled app for debugging

## Project Status

🚀 **Active Development** - Core systems functional, ongoing feature additions

**Currently Implemented:**
- ✅ 6DOF flight physics
- ✅ Complete audio system (FMOD, TTS, sound effects)
- ✅ Interactive checklists with auto-verification
- ✅ Control panel navigation system
- ✅ ATC communications with radio effects
- ✅ Basic autopilot
- ✅ Airport database (9,220 airports)
- ✅ AI traffic and TCAS
- ✅ Platform-aware logging
- ✅ Standalone application builds

**In Progress:**
- 🚧 Ground navigation and taxiway guidance
- 🚧 Weather system
- 🚧 Advanced autopilot modes
- 🚧 Multiplayer support

See [plan.md](plan.md) for detailed roadmap and progress tracking.

## Contributing

Contributions are welcome! Please:
1. Read [CLAUDE.md](CLAUDE.md) for development guidelines
2. Fork the repository
3. Create a feature branch
4. Make your changes with tests
5. Ensure all quality checks pass
6. Submit a pull request

## Documentation

- **[CLAUDE.md](CLAUDE.md)** - Development guidelines and coding standards
- **[plan.md](plan.md)** - Project roadmap and progress tracking
- **[docs/TTS_SYSTEM.md](docs/TTS_SYSTEM.md)** - Detailed TTS system documentation
- **[config/speech.yaml](config/speech.yaml)** - Voice and message configuration
- **[config/README.md](config/README.md)** - Configuration file reference

## License

TBD

## Credits

- **Development**: Created with assistance from Claude (Anthropic)
- **Sound Effects**: Imported from Eurofly 2 (28 professional aviation sounds)
- **Airport Data**: Based on OurAirports database
- **Flight Model**: Inspired by FlightGear and X-Plane physics

## Acknowledgments

Special thanks to the blind aviation community for feedback and testing, and to the developers of Eurofly 2 for pioneering blind-accessible flight simulation.

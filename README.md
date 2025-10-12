# AirBorne

A blind-accessible flight simulator with self-voicing capabilities, realistic physics, and comprehensive aircraft systems simulation.

## Features

- **Fully Accessible**: Self-voicing with TTS, no visual interface required
- **Realistic Physics**: 6DOF flight model with authentic aerodynamics
- **Plugin Architecture**: Modular, extensible system design
- **Complete Aircraft Systems**: Engines, electrical, hydraulics, fuel, avionics
- **Interactive Checklists**: Step-by-step procedures with auto-verification
- **Ground Navigation**: Airport database, taxiway guidance with audio cues
- **ATC Communications**: Realistic radio communications and phraseology
- **AI Traffic**: Simulated aircraft for TCAS and realism
- **Network Ready**: Multiplayer and live ATC support (planned)

## Requirements

- Python 3.11+
- UV package manager
- Cross-platform: Windows, macOS, Linux

## Installation

```bash
# Clone repository
git clone https://github.com/yourusername/airborne.git
cd airborne

# Install with UV
uv sync

# Run
uv run python src/airborne/main.py
```

## Development

See [CLAUDE.md](CLAUDE.md) for development guidelines and [plan.md](plan.md) for the implementation roadmap.

### Running Tests

```bash
uv run pytest
```

### Code Quality

```bash
# Format code
uv run ruff format .

# Lint
uv run ruff check . --fix

# Type check
uv run mypy src

# Quality check
uv run pylint src
```

## Project Status

🚧 **In Development** - Phase 0: Project Setup

See [plan.md](plan.md) for detailed progress.

## License

TBD

## Credits

Developed with assistance from Claude (Anthropic).

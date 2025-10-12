# AirBorne - Complete Implementation Plan

## Project Overview

AirBorne is a blind-accessible flight simulator with self-voicing capabilities, realistic physics, and comprehensive aircraft systems simulation. The architecture is plugin-based, allowing dynamic loading of aircraft systems, modular design, and extensibility.

---

## Technology Stack

- **Language**: Python 3.11+
- **Package Manager**: UV
- **Game Framework**: Pygame 2.5+
- **Audio Engine**: PyBASS (3D spatial audio, effects, multi-source)
- **TTS**: pyttsx3 (self-voicing)
- **Physics**: NumPy (vector mathematics)
- **Configuration**: YAML
- **Data Sources**:
  - OurAirports (airport database)
  - OpenStreetMap (airport geometry, cities)
  - SRTM/Open-Elevation (terrain elevation)

---

## Architecture Principles

1. **Plugin-Based**: Everything is a plugin (engines, systems, avionics, cabin)
2. **Message-Driven**: Inter-plugin communication via message queue
3. **Event-Driven**: Global event bus for state changes
4. **Configuration-Driven**: Aircraft defined in YAML, dynamically loaded
5. **Network-Ready**: Abstract network layer for multiplayer/VATSIM
6. **Modular Audio**: Pluggable audio cue strategies

---

## Phase 0: Project Setup (2-3 hours) ✅

**Status**: COMPLETED - 2025-10-12
**Notes**: Used PyBASS3 instead of pybass. Updated pyproject.toml with Ruff/mypy/pylint. All dependencies installed successfully.

### Objective
Initialize UV project, create directory structure, configure dependencies.

### Tasks

#### 0.1: Initialize UV Project
```bash
cd /Users/yan/dev/airborne
uv init
```

#### 0.2: Configure pyproject.toml
Create `pyproject.toml` with:
- Project metadata
- Core dependencies: pygame, pybass, pyttsx3, numpy, pyyaml, python-dateutil
- Dev dependencies: pytest, black, mypy
- Python version: >=3.11

#### 0.3: Install Dependencies
```bash
uv add pygame pybass pyttsx3 numpy pyyaml python-dateutil
uv add --dev pytest black mypy
```

#### 0.4: Create Directory Structure
```
airborne/
├── pyproject.toml
├── README.md
├── plan.md (this file)
├── .gitignore
├── src/
│   └── airborne/
│       ├── __init__.py
│       ├── main.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── event_bus.py
│       │   ├── messaging.py
│       │   ├── plugin.py
│       │   ├── plugin_loader.py
│       │   ├── registry.py
│       │   ├── game_loop.py
│       │   └── config.py
│       ├── audio/
│       │   ├── __init__.py
│       │   ├── engine/
│       │   │   ├── __init__.py
│       │   │   ├── base.py
│       │   │   └── pybass_engine.py
│       │   ├── cues/
│       │   │   ├── __init__.py
│       │   │   ├── base.py
│       │   │   └── implementations.py
│       │   ├── tts/
│       │   │   ├── __init__.py
│       │   │   ├── base.py
│       │   │   └── pyttsx_provider.py
│       │   └── sound_manager.py
│       ├── physics/
│       │   ├── __init__.py
│       │   ├── vectors.py
│       │   ├── flight_model/
│       │   │   ├── __init__.py
│       │   │   ├── base.py
│       │   │   └── simple_6dof.py
│       │   └── collision.py
│       ├── plugins/
│       │   ├── __init__.py
│       │   ├── core/
│       │   │   ├── __init__.py
│       │   │   └── physics_plugin.py
│       │   ├── engines/
│       │   │   ├── __init__.py
│       │   │   └── simple_piston_plugin.py
│       │   ├── systems/
│       │   │   ├── __init__.py
│       │   │   ├── electrical_plugin.py
│       │   │   └── fuel_plugin.py
│       │   └── audio/
│       │       ├── __init__.py
│       │       └── audio_plugin.py
│       ├── aircraft/
│       │   ├── __init__.py
│       │   ├── aircraft.py
│       │   └── builder.py
│       ├── terrain/
│       │   ├── __init__.py
│       │   ├── elevation_service.py
│       │   └── spatial_index.py
│       └── airports/
│           ├── __init__.py
│           ├── database.py
│           └── classifier.py
├── config/
│   ├── settings.yaml
│   └── aircraft/
│       └── cessna172.yaml
├── data/
│   ├── sounds/
│   │   ├── engines/
│   │   ├── environment/
│   │   └── cues/
│   ├── airports/
│   └── terrain/
└── tests/
    ├── __init__.py
    └── test_event_bus.py
```

#### 0.5: Create .gitignore
Include:
- `__pycache__/`
- `*.pyc`
- `.pytest_cache/`
- `.mypy_cache/`
- `data/airports/*.csv` (downloaded data)
- `data/terrain/` (cached data)

### Success Criteria
- ✅ UV project initializes without errors
- ✅ Dependencies install successfully
- ✅ Directory structure created
- ✅ Can run `uv run python -c "import pygame; import numpy; print('OK')"`
- ✅ Dev tools verified (pytest, ruff, mypy, pylint)

---

## Phase 1: Core Framework (8-10 hours)

### Objective
Build the foundational systems: event bus, message queue, plugin system, configuration loader.

### Tasks

#### 1.1: Implement Event Bus (1 hour)
**File**: `src/airborne/core/event_bus.py`

**Requirements**:
- Generic event base class with timestamp
- Priority-based event handling (CRITICAL, HIGH, NORMAL, LOW)
- Type-safe subscription by event class
- Immediate event dispatch (synchronous)
- Unsubscribe capability

**Key Classes**:
- `Event` (base dataclass)
- `EventPriority` (enum)
- `EventBus` (subscribe, publish, unsubscribe)

**Test**: Create test events and verify subscribers receive them in priority order.

#### 1.2: Implement Message Queue (2 hours)
**File**: `src/airborne/core/messaging.py`

**Requirements**:
- Priority queue for async message delivery
- Topic-based subscription
- Broadcast support (recipient = "*")
- Message priority (CRITICAL, HIGH, NORMAL, LOW)
- Process N messages per frame (bounded)
- Standard message topics (engine state, electrical, fuel, etc.)

**Key Classes**:
- `Message` (dataclass with sender, recipients, topic, data, priority)
- `MessageQueue` (subscribe, publish, process)
- `MessageTopic` (string constants)
- `MessagePriority` (enum)

**Test**: Publish messages, verify subscribers receive them in correct order.

#### 1.3: Implement Plugin Interface (2 hours)
**File**: `src/airborne/core/plugin.py`

**Requirements**:
- `IPlugin` abstract base class
- `PluginMetadata` dataclass (name, version, type, dependencies, provides, optional)
- `PluginContext` dataclass (event_bus, message_queue, config, registry)
- `PluginType` enum (CORE, AIRCRAFT_SYSTEM, WORLD, CABIN, AVIONICS, NETWORK)

**Key Methods**:
- `get_metadata() -> PluginMetadata`
- `initialize(context: PluginContext)`
- `update(dt: float)`
- `shutdown()`
- `handle_message(message: Message)`
- `on_config_changed(config: dict)`

**Test**: Create dummy plugin, verify interface methods are called.

#### 1.4: Implement Plugin Loader (2 hours)
**File**: `src/airborne/core/plugin_loader.py`

**Requirements**:
- Discover plugins in specified directories
- Load plugin classes dynamically
- Resolve dependencies (topological sort)
- Initialize plugins with context
- Track loaded plugins
- Unload plugins gracefully

**Key Classes**:
- `PluginLoader` (discover_plugins, load_plugin, unload_plugin)

**Key Methods**:
- `discover_plugins() -> List[PluginMetadata]`
- `load_plugin(plugin_name: str, context: PluginContext) -> IPlugin`
- `unload_plugin(plugin_name: str)`

**Test**: Create two plugins with dependency, verify load order.

#### 1.5: Implement Component Registry (1 hour)
**File**: `src/airborne/core/registry.py`

**Requirements**:
- Registry for interface → implementation mapping
- Factory pattern for creating components
- Support for multiple implementations of same interface

**Key Classes**:
- `ComponentRegistry` (register, create, list_implementations)

**Test**: Register multiple implementations, create instances via registry.

#### 1.6: Implement Configuration Loader (1 hour)
**File**: `src/airborne/core/config.py`

**Requirements**:
- Load YAML configuration files
- Merge multiple config files (defaults + user overrides)
- Hot-reload support (watch file changes)
- Validation against schemas

**Key Classes**:
- `ConfigLoader` (load, reload, get, set)

**Test**: Load sample YAML, verify nested access works.

#### 1.7: Implement Game Loop (1 hour)
**File**: `src/airborne/core/game_loop.py`

**Requirements**:
- Fixed timestep physics update (60Hz)
- Variable framerate rendering
- Frame rate limiting
- Delta time calculation
- Plugin update orchestration

**Key Classes**:
- `GameLoop` (run, update, render, shutdown)

**Structure**:
```python
class GameLoop:
    def run(self):
        while running:
            dt = calculate_delta_time()
            self.process_input()
            self.update(dt)  # Update plugins
            self.process_messages()  # Message queue
            self.render()
            self.limit_framerate()
```

**Test**: Run loop for 100 frames, verify consistent timing.

### Success Criteria
- ✅ Event bus dispatches events correctly
- ✅ Message queue processes messages by priority
- ✅ Plugins can be loaded dynamically
- ✅ Dependencies resolved automatically
- ✅ Configuration files load without errors
- ✅ Game loop runs at stable 60 FPS

---

## Phase 2: Audio System (6-8 hours)

### Objective
Integrate PyBASS, implement TTS, create audio manager, test 3D positioning.

### Tasks

#### 2.1: Create Audio Engine Interface (1 hour)
**File**: `src/airborne/audio/engine/base.py`

**Requirements**:
- Abstract interface for audio engines
- Support 3D positioning, panning, volume, pitch
- Sound loading and caching
- Multiple simultaneous sources
- Effects (reverb, EQ, doppler)

**Key Classes**:
- `IAudioEngine` (abstract)
- `Sound` (dataclass: path, loop, volume, pitch)
- `AudioSource` (3D position, sound, state)

**Methods**:
- `load_sound(path: str) -> Sound`
- `play_2d(sound: Sound, volume: float, pitch: float) -> int` (returns source ID)
- `play_3d(sound: Sound, position: Vector3) -> int`
- `update_source(source_id: int, position: Vector3, velocity: Vector3)`
- `stop_source(source_id: int)`
- `set_listener(position: Vector3, forward: Vector3, up: Vector3)`

#### 2.2: Implement PyBASS Engine (3 hours)
**File**: `src/airborne/audio/engine/pybass_engine.py`

**Requirements**:
- Initialize BASS library
- Implement `IAudioEngine` interface
- 3D sound positioning
- Stereo panning for 2D sounds
- Volume and pitch control
- Looping sounds
- Error handling

**Key Classes**:
- `PyBassAudioEngine(IAudioEngine)`

**Implementation Notes**:
- Use `BASS_Init()` for initialization
- Use `BASS_SampleLoad()` for loading sounds
- Use `BASS_ChannelPlay()` for playback
- Use `BASS_ChannelSet3DPosition()` for 3D positioning
- Use `BASS_Set3DPosition()` for listener
- Use `BASS_Apply3D()` to update 3D calculations

**Test**: Load sound, play at different positions, verify stereo panning works.

#### 2.3: Create TTS Interface (1 hour)
**File**: `src/airborne/audio/tts/base.py`

**Requirements**:
- Abstract TTS provider interface
- Text-to-speech with voice selection
- Rate, volume, pitch control
- Queue management (FIFO)
- Interrupt capability

**Key Classes**:
- `ITTSProvider` (abstract)
- `TTSMessage` (dataclass: text, voice, rate, volume, interrupt)

**Methods**:
- `speak(text: str, interrupt: bool = False)`
- `set_voice(voice_id: str)`
- `set_rate(rate: int)`
- `set_volume(volume: float)`
- `is_speaking() -> bool`
- `stop()`

#### 2.4: Implement pyttsx3 Provider (1 hour)
**File**: `src/airborne/audio/tts/pyttsx_provider.py`

**Requirements**:
- Implement `ITTSProvider` using pyttsx3
- Voice enumeration
- Queue management
- Non-blocking speech (run in separate thread)

**Key Classes**:
- `Pyttsx3Provider(ITTSProvider)`

**Implementation Notes**:
- Use `pyttsx3.init()`
- Use threading to avoid blocking game loop
- Manage speech queue internally

**Test**: Speak multiple phrases, verify queueing works.

#### 2.5: Create Sound Manager (2 hours)
**File**: `src/airborne/audio/sound_manager.py`

**Requirements**:
- High-level audio management
- Sound preloading and caching
- Audio source pooling
- Volume mixing (master, SFX, TTS, music)
- 3D audio scene management

**Key Classes**:
- `SoundManager`

**Methods**:
- `preload_sounds(sound_list: List[str])`
- `play_sound(name: str, position: Optional[Vector3] = None) -> int`
- `update_listener(position: Vector3, forward: Vector3)`
- `set_master_volume(volume: float)`
- `update()` (called every frame)

**Test**: Preload sounds, play multiple simultaneously, verify mixing.

#### 2.6: Create Audio Plugin (1 hour)
**File**: `src/airborne/plugins/audio/audio_plugin.py`

**Requirements**:
- Wrap audio system as plugin
- Subscribe to position updates
- Update listener position based on aircraft
- Provide audio services to other plugins

**Key Classes**:
- `AudioPlugin(IPlugin)`

**Metadata**:
- Type: CORE
- Provides: ["audio_engine", "sound_manager", "tts"]

**Test**: Load plugin, verify it receives position updates.

### Success Criteria
- ✅ PyBASS initializes without errors
- ✅ Can load and play WAV/OGG files
- ✅ 3D positioning works (sound pans left/right based on position)
- ✅ TTS speaks text without blocking
- ✅ Multiple sounds play simultaneously
- ✅ Volume control works

---

## Phase 3: Physics & Math (4-6 hours)

### Objective
Implement vector math, basic flight physics, collision detection.

### Tasks

#### 3.1: Implement Vector Math (1 hour)
**File**: `src/airborne/physics/vectors.py`

**Requirements**:
- Vector3 class using NumPy
- Common operations: add, subtract, multiply, divide, dot, cross
- Magnitude, normalize, distance
- Rotation utilities (quaternions for later)

**Key Classes**:
- `Vector3` (x, y, z components)

**Methods**:
- `magnitude() -> float`
- `normalized() -> Vector3`
- `dot(other: Vector3) -> float`
- `cross(other: Vector3) -> Vector3`
- `distance_to(other: Vector3) -> float`

**Test**: Verify vector operations match expected results.

#### 3.2: Create Flight Model Interface (1 hour)
**File**: `src/airborne/physics/flight_model/base.py`

**Requirements**:
- Abstract flight model interface
- Input: control surfaces (pitch, roll, yaw, throttle)
- Output: forces and moments
- State: position, velocity, acceleration, rotation

**Key Classes**:
- `IFlightModel` (abstract)
- `AircraftState` (dataclass: position, velocity, rotation, etc.)
- `ControlInputs` (dataclass: pitch, roll, yaw, throttle)
- `FlightForces` (dataclass: lift, drag, thrust, weight)

**Methods**:
- `update(dt: float, inputs: ControlInputs) -> AircraftState`
- `apply_force(force: Vector3, position: Vector3)`
- `get_state() -> AircraftState`

#### 3.3: Implement Simple 6DOF Flight Model (3-4 hours)
**File**: `src/airborne/physics/flight_model/simple_6dof.py`

**Requirements**:
- 6 degrees of freedom (position x,y,z + rotation pitch,roll,yaw)
- Basic aerodynamic forces (lift, drag, thrust, weight)
- Simplified lift equation: L = 0.5 * ρ * v² * S * Cl
- Drag: D = 0.5 * ρ * v² * S * Cd
- Thrust from engine plugin
- Gravity: F = m * g
- Euler integration (good enough for start)

**Physics Model**:
```
Lift = f(airspeed, angle of attack, wing area)
Drag = f(airspeed, drag coefficient)
Thrust = from engine
Weight = constant (minus fuel burn)

Net Force = Lift + Drag + Thrust + Weight
Acceleration = Net Force / Mass
Velocity += Acceleration * dt
Position += Velocity * dt
```

**Key Classes**:
- `Simple6DOFFlightModel(IFlightModel)`

**Parameters** (from config):
- `wing_area_sqft`
- `weight_lbs`
- `drag_coefficient`
- `lift_coefficient_slope`

**Test**: Apply throttle, verify altitude increases. Remove throttle, verify descent.

#### 3.4: Implement Collision Detection (1 hour)
**File**: `src/airborne/physics/collision.py`

**Requirements**:
- Ground collision (altitude < terrain elevation)
- Detect landing (low vertical speed + ground contact)
- Simple bounding sphere for aircraft

**Key Classes**:
- `CollisionDetector`

**Methods**:
- `check_ground_collision(position: Vector3, terrain_elevation: float) -> bool`
- `check_landing(state: AircraftState, terrain_elevation: float) -> bool`

**Test**: Position aircraft below ground, verify collision detected.

#### 3.5: Create Physics Plugin (1 hour)
**File**: `src/airborne/plugins/core/physics_plugin.py`

**Requirements**:
- Wrap physics system as plugin
- Load flight model from config
- Update physics every frame
- Publish position updates via message queue

**Key Classes**:
- `PhysicsPlugin(IPlugin)`

**Metadata**:
- Type: CORE
- Provides: ["flight_model", "collision_detector"]

**Messages Published**:
- `MessageTopic.POSITION_UPDATED` (every frame)
- `MessageTopic.COLLISION_DETECTED` (on collision)

**Test**: Load plugin, apply inputs, verify state updates.

### Success Criteria
- ✅ Vector math operations correct
- ✅ Aircraft climbs with throttle
- ✅ Aircraft descends without throttle
- ✅ Turning affects heading
- ✅ Ground collision prevents negative altitude
- ✅ Physics plugin integrates cleanly

---

## Phase 4: First Playable Prototype (6-8 hours)

### Objective
Create minimal Pygame window, implement simple engine, integrate systems, achieve first flight.

### Tasks

#### 4.1: Create Pygame Window (1 hour)
**File**: `src/airborne/main.py`

**Requirements**:
- Initialize Pygame
- Create window (800x600, resizable)
- Black background with "AirBorne" text centered
- Handle window events (close, resize)
- Keyboard input handling
- Frame rate display (optional debug)

**Key Structure**:
```python
def main():
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("AirBorne")

    # Initialize core systems
    event_bus = EventBus()
    message_queue = MessageQueue()
    plugin_loader = PluginLoader([...])

    # Load plugins
    # ...

    # Game loop
    game_loop = GameLoop(...)
    game_loop.run()
```

**Test**: Run `uv run python src/airborne/main.py`, see window.

#### 4.2: Implement Input System (1 hour)
**File**: `src/airborne/core/input.py`

**Requirements**:
- Keyboard input mapping
- Joystick support (optional for now)
- Key bindings from config
- Publish input events

**Key Classes**:
- `InputManager`

**Default Controls**:
- Arrow Up/Down: Pitch
- Arrow Left/Right: Roll
- Plus/Minus: Throttle
- Space: Next TTS announcement
- Escape: Quit

**Test**: Press keys, verify events published.

#### 4.3: Create Simple Piston Engine Plugin (2-3 hours)
**File**: `src/airborne/plugins/engines/simple_piston_plugin.py`

**Requirements**:
- Throttle → RPM → thrust calculation
- Fuel consumption (gallons/hour)
- Engine temperature (simple model)
- Engine sounds (pitch varies with RPM)

**Physics Model**:
```
Target RPM = throttle * max_rpm
Current RPM += (Target RPM - Current RPM) * spool_rate * dt
Thrust = (RPM / max_rpm) * max_power_hp * 0.5
Fuel Flow = base_fuel_flow * (RPM / max_rpm)
```

**Key Classes**:
- `SimplePistonEnginePlugin(IPlugin)`

**Metadata**:
- Type: AIRCRAFT_SYSTEM
- Provides: ["engine"]
- Dependencies: ["electrical"]

**Messages Published**:
- `MessageTopic.ENGINE_STATE` (RPM, thrust, fuel flow, temperature)

**Messages Subscribed**:
- `MessageTopic.TEMPERATURE_CHANGED` (affects efficiency)
- `MessageTopic.ELECTRICAL_STATE` (starter requires power)

**Test**: Set throttle, verify thrust output increases.

#### 4.4: Create Simple Electrical System Plugin (1 hour)
**File**: `src/airborne/plugins/systems/electrical_plugin.py`

**Requirements**:
- Battery (voltage, capacity Ah)
- Alternator (driven by engine)
- Power consumption tracking
- Bus voltage calculation

**Key Classes**:
- `ElectricalSystemPlugin(IPlugin)`

**Metadata**:
- Type: AIRCRAFT_SYSTEM
- Provides: ["electrical"]

**Messages Published**:
- `MessageTopic.ELECTRICAL_STATE` (battery voltage, bus voltage, amps)

**Messages Subscribed**:
- `MessageTopic.ENGINE_STATE` (alternator needs running engine)

**Test**: Start engine, verify alternator charges battery.

#### 4.5: Create Simple Fuel System Plugin (1 hour)
**File**: `src/airborne/plugins/systems/fuel_plugin.py`

**Requirements**:
- Fuel tanks (capacity, current level)
- Fuel pumps (electric)
- Fuel flow to engine
- Low fuel warnings

**Key Classes**:
- `FuelSystemPlugin(IPlugin)`

**Metadata**:
- Type: AIRCRAFT_SYSTEM
- Provides: ["fuel"]
- Dependencies: ["electrical"]

**Messages Published**:
- `MessageTopic.FUEL_STATE` (fuel level, flow rate)

**Messages Subscribed**:
- `MessageTopic.ENGINE_STATE` (consumes fuel)
- `MessageTopic.ELECTRICAL_STATE` (pumps need power)

**Test**: Run engine, verify fuel decreases.

#### 4.6: Create Aircraft Class (1 hour)
**File**: `src/airborne/aircraft/aircraft.py`

**Requirements**:
- Composition of plugins (systems)
- Load from configuration
- Update all systems
- Query system state

**Key Classes**:
- `Aircraft`

**Methods**:
- `add_system(instance_id: str, plugin: IPlugin)`
- `get_system(instance_id: str) -> IPlugin`
- `update(dt: float)` (calls all system updates)

**Test**: Create aircraft with engine, verify updates propagate.

#### 4.7: Create Aircraft Builder (1-2 hours)
**File**: `src/airborne/aircraft/builder.py`

**Requirements**:
- Load aircraft from YAML config
- Resolve plugin dependencies
- Instantiate plugins with configs
- Return fully configured Aircraft

**Key Classes**:
- `AircraftBuilder`

**Methods**:
- `build(config_path: Path) -> Aircraft`
- `_resolve_dependencies(plugins: List[dict]) -> List[dict]`
- `_load_plugin(plugin_config: dict) -> IPlugin`

**Test**: Load Cessna 172 config, verify all systems loaded.

#### 4.8: Create Cessna 172 Configuration (30 min)
**File**: `config/aircraft/cessna172.yaml`

**Content**:
```yaml
aircraft:
  name: "Cessna 172 Skyhawk"
  icao_code: "C172"

  flight_model: "Simple6DOF"
  flight_model_config:
    wing_area_sqft: 174
    weight_lbs: 2450
    drag_coefficient: 0.027
    lift_coefficient_slope: 0.09

  plugins:
    - plugin: "simple_piston_engine"
      instance_id: "engine"
      config:
        max_power_hp: 180
        max_rpm: 2700
        fuel_consumption_base_gph: 9.5
        sound: "sounds/engines/piston_loop.wav"

    - plugin: "electrical_system"
      instance_id: "electrical"
      config:
        battery_voltage: 24
        battery_capacity_ah: 35
        alternator_voltage: 28
        alternator_amps: 60

    - plugin: "fuel_system"
      instance_id: "fuel"
      config:
        tanks:
          - name: "left"
            capacity_gallons: 26
          - name: "right"
            capacity_gallons: 26
```

#### 4.9: Integrate Everything in Main Loop (1 hour)
**File**: `src/airborne/main.py`

**Requirements**:
- Initialize all core systems
- Load aircraft from config
- Connect input to flight controls
- Update physics with engine thrust
- Update audio listener with aircraft position
- TTS announcements (altitude callouts)

**Main Loop Structure**:
```python
# Initialize
event_bus = EventBus()
message_queue = MessageQueue()
plugin_loader = PluginLoader([...])
config = ConfigLoader.load("config/settings.yaml")

# Load core plugins
audio_plugin = plugin_loader.load_plugin("audio_plugin", context)
physics_plugin = plugin_loader.load_plugin("physics_plugin", context)

# Build aircraft
builder = AircraftBuilder(plugin_loader)
aircraft = builder.build("config/aircraft/cessna172.yaml")

# Game loop
while running:
    # Input
    inputs = input_manager.get_inputs()

    # Update
    aircraft.update(dt)
    physics_plugin.update(dt)
    message_queue.process()

    # Audio
    state = physics_plugin.get_state()
    audio_plugin.update_listener(state.position, state.forward)

    # Render
    render_screen()
```

**Test**: Run game, press throttle, hear engine, aircraft climbs.

### Success Criteria
- ✅ Pygame window opens
- ✅ "AirBorne" displayed on screen
- ✅ Engine responds to throttle input
- ✅ Aircraft climbs/descends based on physics
- ✅ Engine sound pitch changes with RPM
- ✅ TTS announces altitude periodically
- ✅ Fuel decreases over time
- ✅ Battery voltage shown (debug output)

---

## Phase 5: Ground Navigation & Proximity Audio (8-10 hours)

### Objective
Implement airport database, taxiway system, ground physics, proximity audio cues.

### Tasks

#### 5.1: Download OurAirports Data (30 min)
**Files**: `data/airports/airports.csv`, `runways.csv`, `airport-frequencies.csv`

**Source**: https://ourairports.com/data/

**Script**: Create `scripts/download_airport_data.py`
```python
import requests

urls = [
    "https://davidmegginson.github.io/ourairports-data/airports.csv",
    "https://davidmegginson.github.io/ourairports-data/runways.csv",
    "https://davidmegginson.github.io/ourairports-data/airport-frequencies.csv"
]

for url in urls:
    filename = url.split("/")[-1]
    # Download and save to data/airports/
```

**Test**: Run script, verify CSVs downloaded.

#### 5.2: Implement Airport Database Parser (2 hours)
**File**: `src/airborne/airports/database.py`

**Requirements**:
- Parse OurAirports CSV files
- Index airports by ICAO code
- Query airports by position (spatial index)
- Load runways for airport
- Load frequencies for airport

**Key Classes**:
- `Airport` (dataclass: ICAO, name, position, elevation, type)
- `Runway` (dataclass: id, heading, length, width, surface, has_ILS)
- `Frequency` (dataclass: type, frequency, description)
- `AirportDatabase`

**Methods**:
- `load_from_csv(airports_path, runways_path, frequencies_path)`
- `get_airport(icao: str) -> Optional[Airport]`
- `get_airports_near(position: Vector3, radius_nm: float) -> List[Airport]`
- `get_runways(icao: str) -> List[Runway]`
- `get_frequencies(icao: str) -> List[Frequency]`

**Test**: Load database, query KPAO, verify runways returned.

#### 5.3: Implement Airport Classifier (1 hour)
**File**: `src/airborne/airports/classifier.py`

**Requirements**:
- Classify airports as SMALL, MEDIUM, LARGE, XL
- Based on: number of runways, longest runway, ILS presence
- Manual overrides for major hubs

**Key Classes**:
- `AirportCategory` (enum)
- `AirportClassifier`

**Classification Logic**:
```
SMALL: 1 runway, <3000ft, or grass surface
MEDIUM: 1-2 paved runways, <7000ft
LARGE: 2+ runways, or >7000ft
XL: 4+ runways, or in major_hubs list (KLAX, LFPG, etc.)
```

**Methods**:
- `classify(airport: Airport, runways: List[Runway]) -> AirportCategory`

**Test**: Classify KPAO (small), KSFO (XL), verify correct.

#### 5.4: Implement Spatial Index (1 hour)
**File**: `src/airborne/airports/spatial_index.py`

**Requirements**:
- Fast spatial queries (airports near position)
- Grid-based or quadtree
- Support radius queries

**Key Classes**:
- `SpatialIndex`

**Methods**:
- `insert(position: Vector3, data: Any)`
- `query_radius(position: Vector3, radius: float) -> List[Any]`

**Test**: Insert 100 airports, query radius, verify correct results.

#### 5.5: Implement Basic Taxiway System (2 hours)
**File**: `src/airborne/airports/taxiway.py`

**Requirements**:
- For now, hardcode simple taxiway for test airport
- Represent as graph (nodes + edges)
- Calculate distance to edges
- Calculate distance to centerline

**Key Classes**:
- `TaxiwayNode` (position)
- `TaxiwayEdge` (node1, node2, width)
- `TaxiwayGraph`
- `TaxiwayProximityDetector`

**Methods**:
- `get_distance_to_edge(position: Vector3) -> (left_distance, right_distance)`
- `get_distance_to_centerline(position: Vector3) -> float`
- `get_current_taxiway(position: Vector3) -> Optional[str]`

**Test**: Position aircraft on taxiway, verify edge distances calculated.

#### 5.6: Implement Ground Physics (1 hour)
**File**: `src/airborne/physics/ground_physics.py`

**Requirements**:
- Friction when on ground
- Nose wheel steering
- Differential braking for turns
- Ground speed calculation

**Key Classes**:
- `GroundPhysics`

**Methods**:
- `update(dt: float, state: AircraftState, inputs: ControlInputs) -> AircraftState`
- `apply_friction(velocity: Vector3) -> Vector3`
- `apply_steering(heading: float, steering_input: float) -> float`

**Test**: Position aircraft on ground, apply steering, verify heading changes.

#### 5.7: Implement Proximity Audio Cue Interface (1 hour)
**File**: `src/airborne/audio/cues/base.py`

**Requirements**:
- Abstract interface for proximity cues
- Input: aircraft state, ground context
- Output: list of audio cues to play

**Key Classes**:
- `IProximityCueGenerator` (abstract)
- `GroundContext` (dataclass: distance_to_left_edge, distance_to_right_edge, etc.)
- `AudioCue` (dataclass: sound_id, pan, volume, pitch, loop, priority)

**Methods**:
- `update(state: AircraftState, context: GroundContext) -> List[AudioCue]`

#### 5.8: Implement Beeping Proximity Cues (2 hours)
**File**: `src/airborne/audio/cues/implementations.py`

**Requirements**:
- Beeping sound when approaching taxiway edge
- Frequency increases with proximity
- Stereo panning (left edge = left speaker, right edge = right speaker)
- Configurable warning distance

**Key Classes**:
- `BeepingProximityCue(IProximityCueGenerator)`

**Algorithm**:
```
if distance_to_left_edge < warning_distance:
    intensity = 1.0 - (distance / warning_distance)
    beep_rate = 1.0 + (intensity * 3.0)  # 1-4 Hz
    volume = intensity * 0.7
    pan = -0.8  # Hard left
    play beep sound
```

**Test**: Position aircraft near edge, verify beeping increases.

#### 5.9: Create Ground Navigation Plugin (1 hour)
**File**: `src/airborne/plugins/ground/ground_nav_plugin.py`

**Requirements**:
- Integrate taxiway system, proximity detector, audio cues
- Subscribe to position updates
- Publish proximity audio cues

**Key Classes**:
- `GroundNavPlugin(IPlugin)`

**Metadata**:
- Type: WORLD
- Provides: ["ground_navigation"]
- Dependencies: ["audio"]

**Test**: Load plugin, taxi on taxiway, hear edge warnings.

### Success Criteria
- ✅ Airport database loads successfully
- ✅ Can query nearest airport
- ✅ Taxiway edge distances calculated correctly
- ✅ Ground physics feels realistic (friction, steering)
- ✅ Beeping sound when approaching taxiway edge
- ✅ Stereo panning indicates left vs right edge
- ✅ Beep rate increases as edge gets closer

---

## Phase 6: Terrain & Elevation (6-8 hours)

### Objective
Integrate elevation data (SRTM), OpenStreetMap for cities, terrain collision.

### Tasks

#### 6.1: Implement Elevation Service Interface (1 hour)
**File**: `src/airborne/terrain/elevation_service.py`

**Requirements**:
- Abstract interface for elevation providers
- Query elevation at lat/lon
- Batch queries for efficiency
- Caching

**Key Classes**:
- `IElevationProvider` (abstract)
- `ElevationService` (caches providers)

**Methods**:
- `get_elevation(lat: float, lon: float) -> float`
- `get_elevations(coords: List[(lat, lon)]) -> List[float]`

#### 6.2: Implement SRTM Elevation Provider (2-3 hours)
**File**: `src/airborne/terrain/srtm_provider.py`

**Requirements**:
- Use `elevation` Python library or Open-Elevation API
- Download SRTM tiles as needed
- Cache tiles locally
- Interpolate between data points

**Key Classes**:
- `SRTMElevationProvider(IElevationProvider)`

**Test**: Query elevation of known location, verify result.

#### 6.3: Implement OpenStreetMap City Importer (2 hours)
**File**: `src/airborne/terrain/osm_provider.py`

**Requirements**:
- Use `osmnx` or `overpy` to query OSM
- Extract cities, towns, water bodies
- Store as spatial index
- Query nearby cities for audio callouts

**Key Classes**:
- `OSMProvider`
- `City` (dataclass: name, position, population)

**Methods**:
- `get_cities_near(position: Vector3, radius_nm: float) -> List[City]`

**Test**: Query near San Francisco, verify cities returned.

#### 6.4: Implement Terrain Collision (1 hour)
**File**: `src/airborne/physics/collision.py` (extend)

**Requirements**:
- Check aircraft altitude vs terrain elevation
- Prevent descent below terrain
- Crash detection

**Methods**:
- `check_terrain_collision(state: AircraftState, terrain_elevation: float) -> bool`

**Test**: Fly into mountain, verify collision detected.

#### 6.5: Create Terrain Plugin (1-2 hours)
**File**: `src/airborne/plugins/terrain/terrain_plugin.py`

**Requirements**:
- Integrate elevation service, OSM provider
- Subscribe to position updates
- Publish terrain elevation at current position
- Publish nearby cities for callouts

**Key Classes**:
- `TerrainPlugin(IPlugin)`

**Metadata**:
- Type: WORLD
- Provides: ["terrain", "elevation"]

**Messages Published**:
- `MessageTopic.TERRAIN_ELEVATION` (current terrain elevation)
- `MessageTopic.NEARBY_CITIES` (list of cities)

**Test**: Fly around, verify elevation updates.

### Success Criteria
- ✅ Elevation data loads successfully
- ✅ Aircraft cannot descend below terrain
- ✅ Nearby cities detected
- ✅ TTS announces "Approaching San Francisco" when near

---

## Phase 7: Checklists & Control Panels (6-8 hours)

### Objective
Implement interactive checklists, complete control panel system.

### Tasks

#### 7.1: Implement Checklist System (3 hours)
**File**: `src/airborne/plugins/checklist/checklist_plugin.py`

**Requirements**:
- Load checklists from YAML
- Challenge-response pattern
- Auto-verify items based on system state
- TTS announcements
- Track completion

**Key Classes**:
- `ChecklistItem` (challenge, response, verify_condition, state)
- `Checklist` (list of items, current_index)
- `ChecklistPlugin(IPlugin)`

**Methods**:
- `start_checklist(checklist_id: str)`
- `complete_current_item()`
- `skip_current_item()`
- `_auto_verify_items()` (checks verify_condition)

**Test**: Load checklist, verify items complete automatically.

#### 7.2: Create Sample Checklists (1 hour)
**Files**:
- `config/checklists/cessna172_before_start.yaml`
- `config/checklists/cessna172_takeoff.yaml`
- `config/checklists/cessna172_landing.yaml`

**Content**: Standard Cessna 172 checklists with verify conditions.

#### 7.3: Implement Control Panel System (3-4 hours)
**File**: `src/airborne/plugins/panel/control_panel_plugin.py`

**Requirements**:
- Hierarchical panel navigation (overhead, pedestal, instrument, etc.)
- Every switch, button, knob, lever
- Audio navigation (TTS describes current control)
- Toggle/adjust controls
- Send state changes to target plugins

**Key Classes**:
- `Panel` (name, controls)
- `PanelControl` (id, name, type, states, target_plugin, message_topic)
- `ControlPanelPlugin(IPlugin)`

**Navigation**:
- Tab: Next panel
- Arrow keys: Navigate controls
- Enter: Toggle/activate control
- Number keys: Direct control selection

**Methods**:
- `navigate_to_panel(panel_name: str)`
- `select_next_control()`
- `select_previous_control()`
- `activate_current_control()`

**Test**: Navigate panel, toggle switch, verify message sent.

#### 7.4: Create Cessna 172 Panel Definition (1 hour)
**File**: `config/panels/cessna172_panel.yaml`

**Content**:
```yaml
panels:
  - name: "Instrument Panel"
    controls:
      - id: "master_switch"
        name: "Master Switch"
        type: "switch"
        states: ["OFF", "ON"]
        target_plugin: "electrical"
        message_topic: "electrical.master_switch"

      - id: "fuel_pump"
        name: "Fuel Pump"
        type: "switch"
        states: ["OFF", "ON"]
        target_plugin: "fuel"
        message_topic: "fuel.pump"

  - name: "Engine Controls"
    controls:
      - id: "mixture"
        name: "Mixture"
        type: "lever"
        states: ["IDLE_CUTOFF", "LEAN", "RICH"]
        target_plugin: "engine"
        message_topic: "engine.mixture"
```

### Success Criteria
- ✅ Checklists load from YAML
- ✅ TTS reads checklist items
- ✅ Items auto-complete when conditions met
- ✅ Control panel navigable via keyboard
- ✅ Switch toggles send messages to plugins
- ✅ TTS announces control state changes

---

## Phase 8: Radio & ATC (8-10 hours)

### Objective
Implement radio system, ATC communications, frequencies.

### Tasks

#### 8.1: Implement Frequency Manager (1 hour)
**File**: `src/airborne/plugins/radio/frequency_manager.py`

**Requirements**:
- Track active frequencies (COM1, COM2, NAV1, NAV2)
- Tune frequencies
- Store standby frequencies
- Swap active/standby

**Key Classes**:
- `FrequencyManager`

**Methods**:
- `set_active(radio: str, frequency: float)`
- `set_standby(radio: str, frequency: float)`
- `swap(radio: str)` (active ↔ standby)

**Test**: Tune frequency, verify stored correctly.

#### 8.2: Implement ATC Manager (3-4 hours)
**File**: `src/airborne/plugins/radio/atc_manager.py`

**Requirements**:
- Context-aware ATC (knows position, altitude, heading)
- Different ATC types (Ground, Tower, Departure, Approach, Center)
- Phraseology templates
- TTS with different voice for ATC
- Push-to-talk mechanic

**Key Classes**:
- `ATCManager`
- `ATCController` (type, position, frequency, phraseology)

**Methods**:
- `request_clearance()`
- `request_taxi()`
- `request_takeoff()`
- `report_position()`
- `_generate_response(request_type: str) -> str`

**Phraseology Examples**:
- Pilot: "Palo Alto Ground, Cessna 123AB, at parking with information Bravo, request taxi"
- Ground: "Cessna 123AB, Palo Alto Ground, taxi to runway 31 via taxiway Alpha"

**Test**: Request taxi, verify ATC responds appropriately.

#### 8.3: Implement Phraseology System (2 hours)
**File**: `src/airborne/plugins/radio/phraseology.py`

**Requirements**:
- Template-based phraseology
- Context substitution (callsign, altitude, heading, airport)
- Standard ICAO phraseology

**Key Classes**:
- `PhraseMaker`

**Templates**:
```python
TAXI_REQUEST = "{airport} Ground, {callsign}, at {location} with information {atis}, request taxi"
TAXI_CLEARANCE = "{callsign}, {airport} Ground, taxi to runway {runway} via {taxiway}"
TAKEOFF_REQUEST = "{airport} Tower, {callsign}, ready for departure runway {runway}"
TAKEOFF_CLEARANCE = "{callsign}, runway {runway}, cleared for takeoff"
```

**Test**: Generate phrases, verify correct substitution.

#### 8.4: Implement ATIS (1 hour)
**File**: `src/airborne/plugins/radio/atis.py`

**Requirements**:
- Generate ATIS based on weather, runway in use
- Update letter code (Alpha, Bravo, etc.)
- TTS playback

**ATIS Format**:
```
"Palo Alto Airport information Bravo.
Time 1455 Zulu.
Wind 310 at 8 knots.
Visibility 10 statute miles.
Sky clear.
Temperature 22, dewpoint 14.
Altimeter 30.12.
Landing and departing runway 31.
Advise on initial contact you have information Bravo."
```

**Test**: Generate ATIS, verify format correct.

#### 8.5: Create Radio Plugin (2-3 hours)
**File**: `src/airborne/plugins/radio/radio_plugin.py`

**Requirements**:
- Integrate frequency manager, ATC manager, ATIS
- Handle push-to-talk input
- Multiple radio support (COM1, COM2)
- Transmit/receive on correct frequency

**Key Classes**:
- `RadioPlugin(IPlugin)`

**Metadata**:
- Type: AVIONICS
- Provides: ["radio", "atc"]
- Dependencies: ["audio"]

**Test**: Tune to Ground frequency, request taxi, hear response.

### Success Criteria
- ✅ Can tune radio frequencies
- ✅ ATIS plays on correct frequency
- ✅ ATC responds to requests
- ✅ Phraseology sounds realistic
- ✅ Different voice for ATC vs cockpit
- ✅ Push-to-talk works

---

## Phase 9: AI Traffic & TCAS (6-8 hours)

### Objective
Implement AI aircraft, traffic patterns, TCAS collision avoidance.

### Tasks

#### 9.1: Implement AI Aircraft (2 hours)
**File**: `src/airborne/plugins/traffic/ai_aircraft.py`

**Requirements**:
- AI aircraft entity (position, velocity, heading)
- Simple flight plan (waypoints)
- Basic autopilot (follows flight plan)
- Realistic performance (climb rate, speed)

**Key Classes**:
- `AIAircraft` (dataclass)
- `FlightPlan` (list of waypoints)
- `AIAutopilot` (follows waypoints)

**Test**: Create AI aircraft, verify it follows waypoints.

#### 9.2: Implement Traffic Patterns (2 hours)
**File**: `src/airborne/plugins/traffic/traffic_patterns.py`

**Requirements**:
- Generate AI traffic around airports
- Departures, arrivals, pattern work
- Realistic spacing
- Traffic density configurable

**Key Classes**:
- `TrafficGenerator`

**Methods**:
- `generate_departure(airport: Airport) -> AIAircraft`
- `generate_arrival(airport: Airport) -> AIAircraft`
- `generate_pattern_traffic(airport: Airport) -> List[AIAircraft]`

**Test**: Generate traffic at KPAO, verify aircraft spawn.

#### 9.3: Implement TCAS (3-4 hours)
**File**: `src/airborne/plugins/avionics/tcas_plugin.py`

**Requirements**:
- Track nearby traffic (from AI traffic plugin or network)
- Calculate closure rate, time to closest approach
- Issue alerts: Traffic Advisory (TA), Resolution Advisory (RA)
- Audio alerts

**Key Classes**:
- `TCASPlugin(IPlugin)`
- `TrafficTarget` (position, velocity, altitude, closure_rate)

**Metadata**:
- Type: AVIONICS
- Provides: ["tcas"]
- Dependencies: ["electrical"]

**Alert Logic**:
```
TA: 20-48 seconds to collision
RA: 15-35 seconds to collision
```

**Audio**:
- TA: "Traffic, traffic"
- RA: "Climb, climb" or "Descend, descend"

**Test**: Spawn AI traffic on collision course, verify alerts.

#### 9.4: Create AI Traffic Plugin (1 hour)
**File**: `src/airborne/plugins/traffic/ai_traffic_plugin.py`

**Requirements**:
- Manage all AI aircraft
- Update positions every frame
- Broadcast traffic data
- Remove aircraft when far away

**Key Classes**:
- `AITrafficPlugin(IPlugin)`

**Metadata**:
- Type: WORLD
- Provides: ["ai_traffic"]

**Messages Published**:
- `MessageTopic.TRAFFIC_UPDATE` (list of traffic)

**Test**: Spawn traffic, verify positions broadcast.

### Success Criteria
- ✅ AI aircraft spawn at airports
- ✅ AI aircraft follow flight plans
- ✅ Traffic patterns look realistic
- ✅ TCAS detects nearby traffic
- ✅ TCAS issues TA/RA alerts
- ✅ Audio warnings play correctly

---

## Phase 10: Cabin Simulation & Boarding (6-8 hours)

### Objective
Implement passenger boarding, cabin services, weight/balance.

### Tasks

#### 10.1: Implement Passenger System (2 hours)
**File**: `src/airborne/plugins/cabin/passenger_plugin.py`

**Requirements**:
- Track passenger count
- Passenger weight (affects aircraft weight)
- Boarding/deboarding simulation
- Passenger events (optional: complaints, medical, etc.)

**Key Classes**:
- `PassengerPlugin(IPlugin)`
- `Passenger` (seat, weight, class)

**Test**: Board passengers, verify weight increases.

#### 10.2: Implement Boarding System (2 hours)
**File**: `src/airborne/plugins/cabin/boarding_plugin.py`

**Requirements**:
- Boarding rate (passengers per minute)
- Door state (must be open)
- Progress tracking
- Audio announcements

**Key Classes**:
- `BoardingPlugin(IPlugin)`

**Metadata**:
- Dependencies: ["cabin"]

**Messages Published**:
- `MessageTopic.BOARDING_PROGRESS` (passengers boarded, remaining)

**Test**: Start boarding, verify passengers increase over time.

#### 10.3: Implement Cabin Services (1-2 hours)
**File**: `src/airborne/plugins/cabin/service_plugin.py`

**Requirements**:
- Catering
- Cleaning
- Refueling (already in fuel plugin)
- Ground power
- Service time tracking

**Key Classes**:
- `ServicePlugin(IPlugin)`

**Test**: Request services, verify completion time.

#### 10.4: Implement Weight & Balance (2-3 hours)
**File**: `src/airborne/physics/weight_balance.py`

**Requirements**:
- Calculate total weight (fuel + passengers + cargo)
- Calculate center of gravity
- Affect flight performance (heavier = slower climb)
- Out-of-envelope warnings

**Key Classes**:
- `WeightBalance`

**Methods**:
- `calculate_weight() -> float`
- `calculate_cg() -> Vector3`
- `is_within_envelope() -> bool`

**Test**: Load passengers, verify CG changes.

#### 10.5: Create Cabin Plugin (1 hour)
**File**: `src/airborne/plugins/cabin/cabin_plugin.py`

**Requirements**:
- Integrate passengers, boarding, services
- Door management
- Cabin announcements

**Key Classes**:
- `CabinPlugin(IPlugin)`

**Metadata**:
- Type: CABIN
- Provides: ["cabin"]

**Test**: Open door, board passengers, close door, verify sequence.

### Success Criteria
- ✅ Passengers board over time
- ✅ Weight increases with passengers
- ✅ CG calculated correctly
- ✅ Services complete after time
- ✅ Cabin announcements play
- ✅ Door state affects boarding

---

## Phase 11: Network Layer & Multiplayer (8-10 hours)

### Objective
Implement network abstraction, local mode, multiplayer support.

### Tasks

#### 11.1: Define Network Protocol (2 hours)
**File**: `src/airborne/plugins/network/protocol.py`

**Requirements**:
- Aircraft state sync (position, velocity, rotation)
- Radio messages
- Traffic updates
- Efficient serialization (MessagePack or JSON)

**Key Classes**:
- `NetworkMessage` (dataclass)
- `MessageType` (enum: AIRCRAFT_STATE, RADIO_TX, TRAFFIC_UPDATE)

**Test**: Serialize/deserialize messages, verify integrity.

#### 11.2: Implement Network Interface (1 hour)
**File**: `src/airborne/plugins/network/base.py`

**Requirements**:
- Abstract network provider interface
- Connect, disconnect
- Send/receive messages

**Key Classes**:
- `INetworkProvider` (abstract)

#### 11.3: Implement Local Network Provider (1 hour)
**File**: `src/airborne/plugins/network/local_provider.py`

**Requirements**:
- Offline mode (no network)
- Returns empty traffic list

**Key Classes**:
- `LocalNetworkProvider(INetworkProvider)`

**Test**: Connect, verify no errors in offline mode.

#### 11.4: Implement Multiplayer Network Provider (4-6 hours)
**File**: `src/airborne/plugins/network/multiplayer_provider.py`

**Requirements**:
- WebSocket or UDP connection
- Send aircraft state (10 Hz)
- Receive traffic updates
- Handle disconnections
- Simple server (optional: separate project)

**Key Classes**:
- `MultiplayerNetworkProvider(INetworkProvider)`

**Test**: Run two clients, verify they see each other.

#### 11.5: Create Network Plugin (1-2 hours)
**File**: `src/airborne/plugins/network/network_plugin.py`

**Requirements**:
- Wrap network provider as plugin
- Publish traffic from network
- Subscribe to local aircraft state, broadcast

**Key Classes**:
- `NetworkPlugin(IPlugin)`

**Metadata**:
- Type: NETWORK
- Provides: ["network"]

**Test**: Load plugin, verify traffic from network appears.

### Success Criteria
- ✅ Offline mode works (no network needed)
- ✅ Multiplayer mode connects to server
- ✅ Aircraft states sync between clients
- ✅ See other players' aircraft
- ✅ Radio messages broadcast to others

---

## Phase 12: Advanced Avionics (8-10 hours)

### Objective
Implement FMC, autopilot, navigation systems.

### Tasks

#### 12.1: Implement Navigation Database (2 hours)
**File**: `src/airborne/plugins/avionics/navdata.py`

**Requirements**:
- Load VOR, NDB, waypoints (from OurAirports or X-Plane data)
- Query by identifier or position
- Calculate bearing/distance to navaids

**Key Classes**:
- `Navaid` (type, id, frequency, position)
- `NavDatabase`

**Test**: Query SFO VOR, verify position correct.

#### 12.2: Implement Flight Management Computer (4-5 hours)
**File**: `src/airborne/plugins/avionics/fmc_plugin.py`

**Requirements**:
- Flight plan management (waypoints, airways)
- Performance calculations (fuel, time)
- VNAV (vertical navigation)
- LNAV (lateral navigation)

**Key Classes**:
- `FMCPlugin(IPlugin)`
- `FlightPlan` (list of waypoints, constraints)

**Metadata**:
- Type: AVIONICS
- Provides: ["fmc"]
- Dependencies: ["electrical"]

**Test**: Enter flight plan, verify navigation calculations.

#### 12.3: Implement Autopilot (3-4 hours)
**File**: `src/airborne/plugins/avionics/autopilot_plugin.py`

**Requirements**:
- Heading hold
- Altitude hold
- Vertical speed mode
- Nav mode (follow FMC flight plan)
- Approach mode (ILS)

**Key Classes**:
- `AutopilotPlugin(IPlugin)`
- `AutopilotMode` (enum)

**Metadata**:
- Type: AVIONICS
- Provides: ["autopilot"]
- Dependencies: ["fmc", "electrical"]

**Control Logic**:
- PID controllers for pitch, roll, throttle

**Test**: Engage altitude hold, verify aircraft maintains altitude.

#### 12.4: Create Autopilot Plugin (1 hour)
**File**: `src/airborne/plugins/avionics/autopilot_plugin.py`

**Requirements**:
- Integrate with flight controls
- Audio annunciations (mode changes)

**Test**: Engage autopilot, verify hands-off flight.

### Success Criteria
- ✅ Can enter flight plan in FMC
- ✅ Autopilot follows flight plan
- ✅ Altitude hold maintains altitude ±50ft
- ✅ Heading hold maintains heading ±2°
- ✅ ILS approach captures localizer/glideslope

---

## Phase 13: Additional Aircraft (6-8 hours)

### Objective
Create Boeing 737-800 as complex aircraft example.

### Tasks

#### 13.1: Create CFM56 Engine Plugin (2 hours)
**File**: `src/airborne/plugins/engines/cfm56_plugin.py`

**Requirements**:
- Turbofan model (different from piston)
- Spool time (takes time to spool up/down)
- N1, N2, EGT, fuel flow

**Key Classes**:
- `CFM56EnginePlugin(IPlugin)`

**Test**: Apply throttle, verify realistic spool time.

#### 13.2: Create Hydraulic System Plugin (2 hours)
**File**: `src/airborne/plugins/systems/hydraulic_plugin.py`

**Requirements**:
- Multiple hydraulic systems (A, B)
- Pressure calculation
- Pump sources (engine-driven, electric)
- Failures

**Key Classes**:
- `HydraulicSystemPlugin(IPlugin)`

**Test**: Start engines, verify hydraulic pressure builds.

#### 13.3: Create Fly-by-Wire Plugin (2 hours)
**File**: `src/airborne/plugins/systems/fly_by_wire_plugin.py`

**Requirements**:
- Flight control computer
- Envelope protection
- Control law modes (normal, alternate, direct)

**Key Classes**:
- `FlyByWirePlugin(IPlugin)`

**Test**: Pitch aircraft, verify envelope protection prevents stall.

#### 13.4: Create Boeing 737 Configuration (1-2 hours)
**File**: `config/aircraft/boeing737.yaml`

**Content**: Full system definition with 2x CFM56 engines, APU, hydraulics, FBW, etc.

#### 13.5: Test Boeing 737 (1 hour)
**Requirements**:
- Load aircraft
- Verify all systems load
- Test flight

### Success Criteria
- ✅ Boeing 737 loads without errors
- ✅ All systems functional
- ✅ Hydraulics, electrical, fuel work
- ✅ Engines spool realistically
- ✅ Fly-by-wire prevents dangerous inputs

---

## Phase 14: Polish & Optimization (Ongoing)

### Objective
Improve audio design, performance, accessibility.

### Tasks

#### 14.1: Audio Design
- Source/record realistic sounds
- Mix and balance levels
- Create audio cues for all interactions
- Stereo/3D positioning refinement

#### 14.2: Performance Optimization
- Profile frame time
- Optimize message queue processing
- Spatial index optimization
- Plugin update ordering

#### 14.3: Accessibility Testing
- Test with blind users
- Navigation flow improvements
- Audio clarity
- Response timing

#### 14.4: Documentation
- User manual (audio format)
- Keyboard reference
- Tutorial system
- Developer docs for plugins

---

## Testing Strategy

### Unit Tests
- Each plugin tested independently
- Mock dependencies
- Test message passing

### Integration Tests
- Multi-plugin scenarios
- Aircraft loading
- System interactions

### End-to-End Tests
- Full flight scenarios
- Startup → taxi → takeoff → flight → landing
- Checklist completion
- ATC interactions

---

## Milestones

### M1: Core Framework Complete (End of Phase 1)
- Event bus, message queue, plugin system working

### M2: First Flight (End of Phase 4)
- Can fly Cessna 172, hear engine, audio working

### M3: Ground Operations (End of Phase 5)
- Taxi with audio cues, airport database working

### M4: Complete Cessna 172 (End of Phase 7)
- Checklists, control panel, full systems

### M5: Complex Aircraft (End of Phase 13)
- Boeing 737 fully functional

### M6: Multiplayer (End of Phase 11)
- Network mode working, see other players

---

## Development Notes

### Code Style
- Use `black` for formatting
- Type hints required
- Docstrings for all public methods
- Max line length: 100

### Git Workflow
- Feature branches
- Descriptive commit messages
- Tag releases

### Configuration
- YAML for all configs
- JSON for data files
- Validate schemas

### Error Handling
- Graceful degradation (missing plugins → warning, not crash)
- Log errors to file
- User-friendly messages

---

## Future Enhancements (Post-MVP)

- Weather simulation (rain, turbulence, icing)
- Failures simulation (engine failure, electrical fire)
- VATSIM integration
- VR support (audio-only VR?)
- Mobile app for panel control
- Replay system
- Instructor mode (inject failures)
- Achievements/progression
- Liveries (audio descriptions)
- Custom aircraft creation tools

---

## End of Plan

This plan provides a clear, phased approach to building AirBorne. Each phase builds on the previous, with clear success criteria. The plugin architecture ensures flexibility and maintainability.

**Estimated Total Development Time**: 80-120 hours

**Next Step**: Begin Phase 0 - Project Setup

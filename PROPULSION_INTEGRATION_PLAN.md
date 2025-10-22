# Propulsion & Performance System Integration Plan

## Problem Assessment

### Current Issues

1. **No Engine-Physics Integration**
   - SimplePistonEngine calculates power (160 HP) but doesn't feed it to physics
   - Simple6DOFFlightModel uses static `max_thrust` from config (180 lbs = 801N)
   - Engine power and physics thrust are completely disconnected
   - Result: Aircraft accelerates based on throttle × static thrust, ignoring engine RPM, mixture, temperature

2. **Missing Propeller Model**
   - No propeller efficiency calculation
   - No static vs dynamic thrust modeling
   - No propeller pitch/RPM relationship
   - Engine HP cannot be converted to thrust without propeller

3. **Incorrect Weight Calculation**
   - Physics uses `weight_lbs` from config (2450 lbs = 1111 kg)
   - This is a static value, doesn't account for:
     - Fuel consumption (C172 carries 52 gal × 6 lb/gal = 312 lbs)
     - Passengers/crew (pilot + 3 passengers = up to 800 lbs)
     - Cargo (up to 120 lbs)
   - Total weight variation: 1600-2550 lbs (empty to max gross)

4. **Missing Performance Calculations**
   - No V1/VR/V2 calculation system
   - No takeoff distance calculation
   - No weight & balance system
   - No performance degradation with weight increase

### Root Cause

The current architecture treats:
- **Engine** as standalone (calculates RPM, power, temperatures)
- **Physics** as standalone (calculates forces from static thrust)
- **Weight** as static configuration value

They should be:
- **Integrated propulsion chain**: Engine → Propeller → Thrust → Physics
- **Dynamic weight system**: Empty + Fuel + Souls + Cargo = Total weight
- **Performance calculator**: Uses weight, thrust, drag to compute V-speeds and distances

---

## Technical Analysis

### A. Engine Power to Thrust Conversion

**Propeller Thrust Equation:**
```
Static thrust (v=0):  T_static = (prop_efficiency × P × ρ × A)^0.5
Dynamic thrust (v>0): T = (P × prop_efficiency) / v

Where:
  P = engine power (Watts)
  ρ = air density (kg/m³)
  A = propeller disc area (m²)
  v = airspeed (m/s)
  prop_efficiency = typically 0.7-0.85 for fixed-pitch prop
```

**For Cessna 172:**
- Engine: Lycoming O-360, 180 HP (134 kW)
- Propeller: Fixed-pitch, 75" diameter (1.905m)
- Propeller disc area: π × (0.9525m)² ≈ 2.85 m²
- Prop efficiency: ~0.80 at cruise, ~0.50 at static

**Example calculation (full power, static):**
```
P = 134,000 W
ρ = 1.225 kg/m³
A = 2.85 m²
prop_eff = 0.50

T_static = sqrt(0.50 × 134000 × 1.225 × 2.85) ≈ 785 N (176 lbf)
```

This matches the configured 180 lbf, but should vary with:
- RPM (power output varies)
- Airspeed (prop efficiency changes)
- Air density (altitude, temperature)

### B. Weight & Balance System

**C172 Weight Stations (from config):**
```
Empty weight:        1600 lbs @ 85" (CG reference)
Fuel (52 gal max):    312 lbs @ 95"
Pilot:                200 lbs @ 85"
Copilot:              200 lbs @ 85"
Rear passengers (2):  400 lbs @ 118"
Cargo:                120 lbs @ 142"
-------------------------
Max gross weight:    2550 lbs (regulatory limit)
CG limits:           82.9" to 95.5"
```

**Dynamic mass calculation:**
```python
total_mass = empty_mass + fuel_mass + occupant_mass + cargo_mass
cg_position = Σ(mass_i × arm_i) / total_mass
```

### C. Takeoff Performance Calculations

**V-Speeds (for light aircraft like C172):**

V-speeds depend on weight, configuration (flaps), density altitude:

```
V_stall = V_stall_ref × sqrt(actual_weight / ref_weight)
V_R = 1.1 × V_stall  (rotation speed)
V_2 = 1.2 × V_stall  (safe climb speed)
V_1 = not applicable  (only for multi-engine, one-engine-out decision speed)
```

**Cessna 172 Reference:**
- V_stall (clean): 47 KIAS @ 2550 lbs
- V_R: ~55 KIAS (1.17 × V_stall)
- V_X (best angle of climb): 59 KIAS
- V_Y (best rate of climb): 73 KIAS

**Takeoff Distance:**
```
Ground roll distance = (V_R)² / (2 × a_ground)

Where:
  a_ground = (T_avg - D_avg - R_friction) / mass
  T_avg = average thrust during roll
  D_avg = average drag (increases with v²)
  R_friction = rolling resistance = μ × weight × g
  μ = 0.04 for paved runway, 0.1-0.2 for grass
```

**C172 Published Performance (sea level, 2550 lbs, ISA):**
- Ground roll: 960 ft (paved)
- Distance to clear 50 ft: 1685 ft
- Rate of climb: 730 fpm

### D. Multi-Engine Aircraft (A380, B787)

**Airbus A380:**
- Empty weight: 610,200 lbs (276,800 kg)
- Max takeoff weight: 1,268,000 lbs (575,000 kg)
- Engines: 4 × Rolls-Royce Trent 900 (70,000 lbf each = 280,000 lbf total)
- V_R: ~160 KIAS (varies with weight)
- Takeoff distance: ~9800 ft @ MTOW

**Boeing 787-9:**
- Empty weight: 254,000 lbs (115,200 kg)
- Max takeoff weight: 557,000 lbs (252,700 kg)
- Engines: 2 × GEnx-1B (74,000 lbf each = 148,000 lbf total)
- V_R: ~150 KIAS (varies with weight)
- Takeoff distance: ~8500 ft @ MTOW

**Key differences:**
- Jet engines: Thrust is relatively constant with airspeed (unlike props)
- Multi-engine: Need to model each engine separately
- V1 speed: Critical for multi-engine (one-engine-out decision)
- Complex flap settings affect V-speeds

---

## Proposed Architecture

### 1. Propeller System (`src/airborne/systems/propeller/`)

**New files:**
```
base.py               - IPropeller interface
fixed_pitch.py        - FixedPitchPropeller (C172)
constant_speed.py     - ConstantSpeedPropeller (advanced aircraft)
```

**FixedPitchPropeller class:**
```python
class FixedPitchPropeller:
    """Fixed-pitch propeller model for thrust calculation."""

    def __init__(self, diameter_m: float, pitch_ratio: float):
        self.diameter = diameter_m
        self.pitch_ratio = pitch_ratio  # pitch / diameter
        self.disc_area = math.pi * (diameter_m / 2) ** 2

    def calculate_thrust(
        self,
        power_hp: float,
        rpm: float,
        airspeed_mps: float,
        air_density_kgm3: float
    ) -> float:
        """Calculate thrust in Newtons."""
        # Convert HP to Watts
        power_watts = power_hp * 745.7

        # Calculate advance ratio: J = v / (n × D)
        if rpm > 0:
            rps = rpm / 60.0
            advance_ratio = airspeed_mps / (rps * self.diameter)
        else:
            advance_ratio = 0.0

        # Estimate propeller efficiency (simplified model)
        # Real props have efficiency curves based on J and blade angle
        if advance_ratio < 0.1:  # Static or very low speed
            efficiency = 0.50
        elif advance_ratio < 0.8:  # Normal cruise
            efficiency = 0.80
        else:  # High speed (prop stalling)
            efficiency = max(0.3, 0.80 - (advance_ratio - 0.8) * 0.5)

        # Calculate thrust
        if airspeed_mps < 1.0:
            # Static thrust approximation
            thrust = math.sqrt(efficiency * power_watts * air_density_kgm3 * self.disc_area)
        else:
            # Dynamic thrust
            thrust = (power_watts * efficiency) / airspeed_mps

        return thrust
```

### 2. Weight & Balance System (`src/airborne/systems/weight_balance/`)

**New files:**
```
weight_balance_system.py  - WeightBalanceSystem class
station.py                - LoadStation (fuel, seats, cargo)
```

**WeightBalanceSystem class:**
```python
class WeightBalanceSystem:
    """Dynamic weight and balance calculation."""

    def __init__(self, config: dict):
        self.empty_weight = config["empty_weight"]
        self.empty_moment = config["empty_moment"]
        self.max_gross_weight = config["max_gross_weight"]
        self.cg_forward_limit = config["cg_limits"]["forward"]
        self.cg_aft_limit = config["cg_limits"]["aft"]
        self.stations = self._load_stations(config["stations"])

    def calculate_total_weight(self) -> float:
        """Calculate current total weight."""
        total = self.empty_weight
        for station in self.stations.values():
            total += station.current_weight
        return total

    def calculate_cg(self) -> float:
        """Calculate current CG position (inches from datum)."""
        total_moment = self.empty_moment
        for station in self.stations.values():
            total_moment += station.current_weight * station.arm

        total_weight = self.calculate_total_weight()
        return total_moment / total_weight if total_weight > 0 else 0.0

    def is_within_limits(self) -> tuple[bool, str]:
        """Check if current W&B is within limits."""
        weight = self.calculate_total_weight()
        cg = self.calculate_cg()

        if weight > self.max_gross_weight:
            return False, f"Overweight: {weight:.0f} lbs > {self.max_gross_weight:.0f} lbs"

        if cg < self.cg_forward_limit:
            return False, f"CG too far forward: {cg:.1f}\" < {self.cg_forward_limit:.1f}\""

        if cg > self.cg_aft_limit:
            return False, f"CG too far aft: {cg:.1f}\" > {self.cg_aft_limit:.1f}\""

        return True, "Within limits"
```

### 3. Performance Calculator (`src/airborne/systems/performance/`)

**New files:**
```
performance_calculator.py  - TakeoffPerformanceCalculator
vspeeds.py                 - V-speed calculations
```

**TakeoffPerformanceCalculator class:**
```python
class TakeoffPerformanceCalculator:
    """Calculate takeoff performance parameters."""

    def calculate_vstall(
        self,
        weight_lbs: float,
        wing_area_sqft: float,
        cl_max: float,
        density_altitude_ft: float
    ) -> float:
        """Calculate stall speed in KIAS."""
        # V_stall = sqrt(2 × W / (ρ × S × CL_max))
        weight_n = weight_lbs * 4.44822
        wing_area_m2 = wing_area_sqft * 0.092903
        air_density = self._density_at_altitude(density_altitude_ft)

        vstall_mps = math.sqrt(2 * weight_n / (air_density * wing_area_m2 * cl_max))
        vstall_kias = vstall_mps * 1.94384  # m/s to knots
        return vstall_kias

    def calculate_vspeeds(
        self,
        weight_lbs: float,
        config: dict  # aircraft config
    ) -> dict[str, float]:
        """Calculate all V-speeds."""
        vstall = self.calculate_vstall(weight_lbs, ...)

        return {
            "V_S": vstall,          # Stall speed
            "V_SO": vstall * 0.94,  # Stall speed landing config (more flaps)
            "V_R": vstall * 1.1,    # Rotation speed
            "V_X": vstall * 1.2,    # Best angle of climb
            "V_Y": vstall * 1.3,    # Best rate of climb
            "V_2": vstall * 1.2,    # Safe climb speed (multi-engine)
        }

    def calculate_takeoff_distance(
        self,
        weight_lbs: float,
        thrust_lbf: float,
        runway_surface: str,
        wind_headwind_kts: float,
        density_altitude_ft: float
    ) -> dict[str, float]:
        """Calculate takeoff distances."""
        # Simplified model - real calculation is complex
        # Returns ground roll and distance to clear 50 ft obstacle
        pass
```

### 4. Multi-Function Display (MFD) / Performance Page (`src/airborne/ui/performance_display.py`)

**New UI menu system for in-game performance data:**

```python
class PerformanceDisplay:
    """In-game performance display and calculator."""

    def __init__(self, weight_balance: WeightBalanceSystem, perf_calc: TakeoffPerformanceCalculator):
        self.wb = weight_balance
        self.perf = perf_calc
        self.menu_state = "main"  # main, weight, vspeeds, takeoff
        self.editable_fields = {}  # Field name → current value
        self.editing_field = None  # Currently editing field
        self.input_buffer = ""     # Text input buffer

    def render(self) -> str:
        """Render current page as text menu."""
        if self.menu_state == "main":
            return self._render_main_menu()
        elif self.menu_state == "weight":
            return self._render_weight_page()
        elif self.menu_state == "vspeeds":
            return self._render_vspeeds_page()
        elif self.menu_state == "takeoff":
            return self._render_takeoff_page()

    def _render_weight_page(self) -> str:
        """Weight & Balance page."""
        total_weight = self.wb.calculate_total_weight()
        cg = self.wb.calculate_cg()
        within_limits, msg = self.wb.is_within_limits()

        output = []
        output.append("═══ WEIGHT & BALANCE ═══")
        output.append(f"Empty Weight:    {self.wb.empty_weight:6.0f} lbs")
        output.append(f"Fuel:            {self.wb.stations['fuel'].current_weight:6.0f} lbs")
        output.append(f"Pilot:           {self.wb.stations['pilot'].current_weight:6.0f} lbs")
        output.append(f"Passengers:      {self._calc_passenger_weight():6.0f} lbs")
        output.append(f"Cargo:           {self.wb.stations['cargo'].current_weight:6.0f} lbs")
        output.append("─────────────────────────")
        output.append(f"Total Weight:    {total_weight:6.0f} lbs")
        output.append(f"Max Gross:       {self.wb.max_gross_weight:6.0f} lbs")
        output.append(f"CG Position:     {cg:6.1f} in")
        output.append(f"CG Limits:       {self.wb.cg_forward_limit:.1f} - {self.wb.cg_aft_limit:.1f} in")
        output.append(f"Status:          {msg}")
        output.append("")
        output.append("[Press ENTER on value to edit]")
        return "\n".join(output)

    def _render_vspeeds_page(self) -> str:
        """V-speeds page."""
        weight = self.wb.calculate_total_weight()
        vspeeds = self.perf.calculate_vspeeds(weight, self.aircraft_config)

        output = []
        output.append("═══ V-SPEEDS ═══")
        output.append(f"Aircraft Weight: {weight:.0f} lbs")
        output.append("")
        output.append(f"V_S  (Stall):           {vspeeds['V_S']:3.0f} KIAS")
        output.append(f"V_SO (Stall landing):   {vspeeds['V_SO']:3.0f} KIAS")
        output.append(f"V_R  (Rotation):        {vspeeds['V_R']:3.0f} KIAS")
        output.append(f"V_X  (Best angle):      {vspeeds['V_X']:3.0f} KIAS")
        output.append(f"V_Y  (Best rate):       {vspeeds['V_Y']:3.0f} KIAS")
        return "\n".join(output)

    def handle_key_input(self, key: str):
        """Handle keyboard input."""
        if self.editing_field:
            # Text input mode
            if key == "ENTER":
                self._commit_edit()
            elif key == "BACKSPACE":
                self.input_buffer = self.input_buffer[:-1]
            elif key.isdigit() or key == ".":
                self.input_buffer += key
                # Speak character
                self._speak_character(key)
        else:
            # Navigation mode
            if key == "UP":
                self._navigate_up()
            elif key == "DOWN":
                self._navigate_down()
            elif key == "ENTER":
                self._start_edit()
```

### 5. Integration with Physics

**Modify PhysicsPlugin to:**
1. Subscribe to ENGINE_STATE messages
2. Receive engine power (HP) and RPM
3. Use propeller model to convert power → thrust
4. Subscribe to WEIGHT_BALANCE_UPDATED messages
5. Update aircraft mass dynamically

**Modified physics_plugin.py:**
```python
def initialize(self, context: PluginContext) -> None:
    # ... existing code ...

    # Subscribe to engine state (to get actual power)
    context.message_queue.subscribe(MessageTopic.ENGINE_STATE, self.handle_message)

    # Subscribe to weight & balance updates
    context.message_queue.subscribe("weight_balance.updated", self.handle_message)

    # Create propeller model
    prop_config = physics_config.get("propeller", {})
    self.propeller = FixedPitchPropeller(
        diameter_m=prop_config.get("diameter_m", 1.905),  # 75" = 1.905m for C172
        pitch_ratio=prop_config.get("pitch_ratio", 0.6)
    )

def handle_message(self, message: Message) -> None:
    # ... existing code ...

    elif message.topic == MessageTopic.ENGINE_STATE:
        # Update engine state
        data = message.data
        self._engine_power_hp = data.get("power_hp", 0.0)
        self._engine_rpm = data.get("rpm", 0.0)

    elif message.topic == "weight_balance.updated":
        # Update aircraft mass
        data = message.data
        new_mass_lbs = data.get("total_weight_lbs", 0.0)
        new_mass_kg = new_mass_lbs * 0.453592
        if self.flight_model:
            self.flight_model.state.mass = new_mass_kg

def _calculate_forces(self, inputs: ControlInputs) -> None:
    # ... existing aerodynamic calculations ...

    # Calculate thrust from engine + propeller
    if self.propeller and self._engine_power_hp > 0:
        airspeed = self.state.get_airspeed()
        thrust_newtons = self.propeller.calculate_thrust(
            power_hp=self._engine_power_hp,
            rpm=self._engine_rpm,
            airspeed_mps=airspeed,
            air_density_kgm3=AIR_DENSITY_SEA_LEVEL
        )

        # Apply thrust in forward direction
        if airspeed > 0.1:
            thrust_dir = self.state.velocity.normalized()
        else:
            # Static: thrust in yaw direction
            thrust_dir = Vector3(math.sin(yaw), 0.0, math.cos(yaw))

        self.forces.thrust = thrust_dir * thrust_newtons
```

---

## Implementation Plan

### Phase 1: Propeller Integration (3-5 hours)

**Goal:** Connect engine power to physics thrust via propeller model

**Tasks:**
1. Create `src/airborne/systems/propeller/base.py` with IPropeller interface
2. Create `src/airborne/systems/propeller/fixed_pitch.py` with FixedPitchPropeller
3. Add propeller config to cessna172.yaml
4. Modify PhysicsPlugin to:
   - Subscribe to ENGINE_STATE messages
   - Create propeller instance
   - Use propeller.calculate_thrust() instead of static thrust
5. Write unit tests:
   - Test thrust calculation at v=0 (static)
   - Test thrust calculation at v=cruise (dynamic)
   - Test advance ratio and efficiency curve
   - Test with different aircraft (C172, A380 - multi-engine)

**Success criteria:**
- Engine RPM affects thrust (low RPM = low thrust even with full throttle)
- Mixture affects thrust (via engine power)
- Airspeed affects thrust (propeller efficiency changes)
- Aircraft acceleration feels realistic

### Phase 2: Weight & Balance System (4-6 hours)

**Goal:** Dynamic weight calculation based on fuel, passengers, cargo

**Tasks:**
1. Create `src/airborne/systems/weight_balance/weight_balance_system.py`
2. Create `src/airborne/systems/weight_balance/station.py` for load stations
3. Create plugin wrapper `src/airborne/plugins/systems/weight_balance_plugin.py`
4. Integrate with:
   - Fuel system (fuel weight updates)
   - Initial state loading (read passenger/cargo from config)
   - Physics system (publish weight updates)
5. Add weight_balance config to cessna172.yaml
6. Write unit tests:
   - Test total weight calculation (empty + fuel + pax + cargo)
   - Test CG calculation (moment / weight)
   - Test limit checking (overweight, CG forward/aft)
   - Test fuel consumption affecting weight
   - Test with extreme cases (empty vs max gross)

**Success criteria:**
- Weight decreases as fuel is consumed
- CG shifts as fuel burns (fuel is aft of CG)
- Physics receives updated mass via messages
- Aircraft performance changes with weight (heavier = slower acceleration)

### Phase 3: Performance Calculator (4-6 hours)

**Goal:** Calculate V-speeds and takeoff distances

**Tasks:**
1. Create `src/airborne/systems/performance/vspeeds.py`
2. Create `src/airborne/systems/performance/performance_calculator.py`
3. Implement V-speed calculations:
   - V_stall (weight-dependent)
   - V_R, V_X, V_Y (derived from V_stall)
   - V1, V2 for multi-engine (future)
4. Implement takeoff distance calculation:
   - Ground roll distance
   - Distance to clear 50 ft obstacle
   - Account for weight, thrust, drag, runway surface, wind
5. Write unit tests:
   - Test V_stall at different weights
   - Test V_speeds scale correctly with weight
   - Test takeoff distance with different conditions
   - Test with C172, A380, B787 configurations

**Success criteria:**
- V_stall increases with weight (sqrt relationship)
- Calculated V-speeds match published C172 POH
- Takeoff distance increases with weight
- Headwind reduces takeoff distance

### Phase 4: Multi-Function Display UI (6-8 hours)

**Goal:** In-game menu to view and edit performance data

**Tasks:**
1. Create `src/airborne/ui/performance_display.py` with menu system
2. Implement pages:
   - Weight & Balance page (view/edit weights)
   - V-speeds page (calculated based on current weight)
   - Takeoff Performance page (distances, wind, runway)
3. Implement keyboard navigation:
   - Arrow keys to navigate fields
   - Enter to edit field
   - Type numbers (spoken via TTS)
   - Enter again to commit
4. Integrate TTS for:
   - Character echo during typing
   - Field name when navigating
   - Value readout
5. Add key binding for performance display (e.g., P key or Shift+P)
6. Write unit tests for UI state machine

**Success criteria:**
- Can open performance display with hotkey
- Can navigate between pages
- Can edit values (e.g., passenger weight)
- Typed characters are spoken
- Calculated values update when inputs change

### Phase 5: Multi-Engine Support (3-4 hours)

**Goal:** Support aircraft with multiple engines (A380, B787)

**Tasks:**
1. Modify propeller system to support:
   - Multiple propellers (piston aircraft)
   - Jet engines (thrust-based, not prop)
2. Create `src/airborne/systems/propeller/turbofan.py` for jets
3. Add engine count and positions to aircraft config
4. Modify physics to sum thrust from all engines
5. Add asymmetric thrust modeling (one engine out)
6. Write unit tests:
   - Test twin-engine piston (thrust = 2 × single engine)
   - Test quad turbofan (A380)
   - Test engine failure (asymmetric thrust → yaw moment)

**Success criteria:**
- A380 config with 4 engines produces 4× single engine thrust
- Engine failure causes yaw (need rudder to compensate)
- V1 speed calculation for multi-engine

### Phase 6: Wind Integration (2-3 hours)

**Goal:** Add wind to performance calculations

**Tasks:**
1. Add wind state to weather/environment system
2. Modify performance calculator to accept wind:
   - Headwind reduces takeoff distance
   - Tailwind increases takeoff distance
   - Crosswind affects ground roll (requires rudder)
3. Display wind on performance page
4. Write unit tests for wind effects

**Success criteria:**
- 10 kt headwind reduces takeoff distance by ~10%
- 10 kt tailwind increases takeoff distance by ~10%

---

## Testing Strategy

### Unit Tests

**Per-component tests:**
- `tests/systems/propeller/test_fixed_pitch.py` (propeller thrust)
- `tests/systems/weight_balance/test_weight_balance.py` (W&B calculations)
- `tests/systems/performance/test_vspeeds.py` (V-speed calculations)
- `tests/systems/performance/test_takeoff.py` (takeoff distances)
- `tests/ui/test_performance_display.py` (UI state machine)

**Integration tests:**
- `tests/integration/test_propulsion_chain.py` (engine → prop → physics)
- `tests/integration/test_weight_dynamics.py` (fuel burn → weight → performance)
- `tests/integration/test_performance_accuracy.py` (compare to POH data)

**Test data sets:**

1. **Cessna 172**
   - Empty weight: 1600 lbs
   - Test weights: 1600, 2000, 2400, 2550 lbs
   - Expected V_R: 47, 51, 54, 56 KIAS
   - Expected ground roll: 720, 840, 960, 1020 ft

2. **Airbus A380**
   - Empty weight: 610,200 lbs
   - Test weights: 800,000, 1,000,000, 1,268,000 lbs
   - Expected V_R: ~140, ~155, ~165 KIAS
   - Expected ground roll: ~6500, ~8500, ~9800 ft

3. **Boeing 787-9**
   - Empty weight: 254,000 lbs
   - Test weights: 400,000, 500,000, 557,000 lbs
   - Expected V_R: ~130, ~145, ~155 KIAS
   - Expected ground roll: ~6000, ~7500, ~8500 ft

### Manual Testing Scenarios

1. **Light takeoff (C172, 1800 lbs)**
   - Should rotate at ~48 KIAS
   - Should lift off quickly (<800 ft)

2. **Heavy takeoff (C172, 2550 lbs)**
   - Should rotate at ~56 KIAS
   - Should require longer roll (~1000 ft)

3. **Fuel burn test**
   - Start at max gross (2550 lbs)
   - Fly for 30 min (consume ~5 gal = 30 lbs)
   - Check weight decreased to 2520 lbs
   - Check climb rate improved

4. **Multi-engine jet (A380)**
   - Should produce massive thrust (280,000 lbf)
   - Should rotate at ~165 KIAS @ MTOW
   - Should require long runway (~10,000 ft)

---

## Configuration Schema

### Aircraft Config Extensions

**cessna172.yaml additions:**
```yaml
# Propulsion configuration
propulsion:
  type: "piston_prop"
  engine_count: 1
  engines:
    - instance_id: "engine"
      position: [10.0, 0.0, 0.0]  # Forward of CG
  propellers:
    - type: "fixed_pitch"
      diameter_m: 1.905             # 75 inches
      pitch_ratio: 0.6              # Pitch/diameter
      position: [10.5, 0.0, 0.0]    # Prop disc location
      efficiency_static: 0.50
      efficiency_cruise: 0.80

# Performance reference data (from POH)
performance:
  reference_weight_lbs: 2550
  cl_max_clean: 1.4
  cl_max_landing: 2.0
  vspeeds_reference:
    V_S: 47    # KIAS @ 2550 lbs
    V_R: 55
    V_X: 59
    V_Y: 73
  takeoff_reference:
    ground_roll_ft: 960           # @ 2550 lbs, sea level, ISA, paved
    distance_50ft: 1685
    climb_rate_fpm: 730
```

**a380.yaml (for testing):**
```yaml
aircraft:
  name: "Airbus A380-800"
  icao_code: "A388"
  manufacturer: "Airbus"
  fixed_gear: false

propulsion:
  type: "turbofan"
  engine_count: 4
  engines:
    - instance_id: "engine_1"
      position: [-20.0, -4.0, -25.0]  # Left inner
      max_thrust_lbf: 70000
    - instance_id: "engine_2"
      position: [-20.0, -4.0, -45.0]  # Left outer
      max_thrust_lbf: 70000
    - instance_id: "engine_3"
      position: [-20.0, -4.0, 25.0]   # Right inner
      max_thrust_lbf: 70000
    - instance_id: "engine_4"
      position: [-20.0, -4.0, 45.0]   # Right outer
      max_thrust_lbf: 70000

weight_balance:
  empty_weight: 610200
  max_gross_weight: 1268000
  # ... detailed station config ...

performance:
  reference_weight_lbs: 1268000
  vspeeds_reference:
    V_S: 110
    V_R: 165
    V_2: 175
  takeoff_reference:
    ground_roll_ft: 9800
    distance_50ft: 11800
```

---

## Risk Assessment

### Technical Risks

1. **Propeller model accuracy**
   - Risk: Simplified efficiency curve may not match real props
   - Mitigation: Validate against published POH data, allow tuning via config

2. **Numerical stability**
   - Risk: Division by zero when airspeed = 0
   - Mitigation: Add epsilon checks, use static thrust formula at low speeds

3. **Performance calculation complexity**
   - Risk: Real takeoff calculations are very complex (flaps, ground effect, etc.)
   - Mitigation: Start with simplified model, document assumptions, iterate

4. **UI accessibility**
   - Risk: TTS during text entry may be annoying or confusing
   - Mitigation: Make TTS configurable, test with actual users

### Schedule Risks

1. **Scope creep**
   - Risk: Features like autopilot integration, flight planning could expand scope
   - Mitigation: Stick to core features in this plan, defer enhancements

2. **Testing time**
   - Risk: Manual testing with large aircraft (A380) may be time-consuming
   - Mitigation: Focus on C172 first, A380/B787 as stretch goals

---

## Success Metrics

### Quantitative

1. **Thrust accuracy:** Calculated thrust within 5% of expected (180 lbf for C172 @ full power, static)
2. **Weight tracking:** Weight updates every frame, matches fuel consumption rate
3. **V-speed accuracy:** Calculated V_R within 3 KIAS of POH for C172
4. **Takeoff distance:** Calculated ground roll within 10% of POH for C172
5. **Test coverage:** >80% for all new systems (propeller, W&B, performance, UI)
6. **Performance:** UI renders at 60 FPS, calculations < 1ms per frame

### Qualitative

1. **Realism:** Aircraft acceleration feels realistic (pilot feedback)
2. **Weight effect:** Heavier aircraft noticeably slower to accelerate/climb
3. **Usability:** Performance display is easy to navigate and understand
4. **Accessibility:** TTS during text entry is helpful, not annoying

---

## Next Steps

### Immediate Actions

1. **Review this plan** with user for approval/modifications
2. **Prioritize phases** (can skip A380/B787 if not needed immediately)
3. **Start Phase 1** (propeller integration) - highest impact for fixing slow acceleration

### Questions for User

1. **Aircraft priority:** Focus on C172 only, or also implement A380/B787?
2. **UI style:** Text-based menu OK, or prefer graphical display?
3. **Wind system:** Already implemented? Or need to build from scratch?
4. **Autopilot integration:** Should performance system interact with autopilot?
5. **Flight planning:** Out of scope for now, or include basic runway analysis?

---

## Estimated Timeline

| Phase | Tasks | Time Estimate |
|-------|-------|---------------|
| Phase 1: Propeller Integration | 5 tasks | 3-5 hours |
| Phase 2: Weight & Balance | 6 tasks | 4-6 hours |
| Phase 3: Performance Calculator | 5 tasks | 4-6 hours |
| Phase 4: Multi-Function Display | 6 tasks | 6-8 hours |
| Phase 5: Multi-Engine (optional) | 6 tasks | 3-4 hours |
| Phase 6: Wind Integration (optional) | 4 tasks | 2-3 hours |
| **Total (core)** | **22 tasks** | **17-25 hours** |
| **Total (with optional)** | **32 tasks** | **22-32 hours** |

**Recommended approach:** Implement Phases 1-4 first (core functionality), then assess if Phases 5-6 are needed.

---

## Conclusion

The root cause of slow acceleration is the **disconnection between engine power and physics thrust**. The engine calculates realistic power (varies with RPM, mixture, temperature), but the physics model uses a static thrust value.

**Key insight:** We need a **propeller model** to bridge the gap. Propeller efficiency varies with airspeed, so static thrust (v=0) is much lower than the power would suggest. This is why the aircraft accelerates slowly - the simplified physics model assumes constant thrust, but real props are much less efficient at low speeds.

By implementing the propulsion chain (Engine → Propeller → Thrust → Physics) along with dynamic weight tracking and performance calculations, we'll achieve:
1. **Realistic acceleration** (depends on engine RPM, prop efficiency, aircraft weight)
2. **Weight-dependent performance** (heavier = slower)
3. **Accurate V-speeds and distances** (critical for safe operations)
4. **In-game performance calculator** (useful for flight planning)

This plan provides a **complete, testable, and extensible solution** that works for light aircraft (C172) and scales to heavy jets (A380, B787).

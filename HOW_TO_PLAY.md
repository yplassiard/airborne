# How to Play AirBorne Flight Simulator

## Quick Start

AirBorne is a blind-accessible flight simulator built for keyboard-only control. This guide will help you get started flying the Cessna 172 Skyhawk.

## Running the Game

```bash
uv run python -m airborne.main
```

## Understanding the Display

When the game starts, you'll see:

**Central Flight Instruments:**
- **AIRSPEED**: Your speed through the air (in knots)
- **ALTITUDE**: Your height above ground (in feet)
- **VS** (Vertical Speed): How fast you're climbing or descending (feet per minute)

**Control Status:** (below instruments)
- Throttle percentage
- Flaps position
- Gear status (UP/DOWN)
- Brakes (ON/OFF)

## Basic Controls

### Flight Controls
- **Arrow Up/Down**: Pitch (nose up/down)
- **Arrow Left/Right**: Roll (bank left/right)
- **A / D**: Yaw (rudder left/right)

### Power & Configuration
- **+ / =**: Increase throttle
- **- / _**: Decrease throttle
- **[ **: Retract flaps
- **]**: Extend flaps
- **G**: Toggle landing gear
- **B**: Apply brakes (hold for continuous braking)

### General
- **Space**: Pause/Resume
- **Esc**: Quit simulator

## Your First Flight

### Before Takeoff

1. **Start the game** - The Cessna 172 begins on the ground with engine running
2. **Check instruments**:
   - Altitude should be near 0 FT
   - Airspeed should be 0 KTS
3. **Set full throttle**: Press `+` or `=` repeatedly until throttle shows 100%

### Takeoff

1. **Release brakes**: The aircraft will start rolling
2. **Build speed**: Watch airspeed increase to ~60 knots
3. **Rotate**: At 60 knots, press Arrow Up to raise the nose slightly
4. **Liftoff**: Aircraft will leave the ground around 65-70 knots
5. **Climb**: Maintain slight nose-up attitude, watch altitude increase

### Level Flight

1. **Reduce throttle**: Press `-` to reduce to 75% throttle
2. **Level off**: Press Arrow Down until vertical speed reads near 0 FPM
3. **Trim**: Make small adjustments to maintain altitude
4. **Cruise**: Maintain 90-110 knots airspeed

### Landing (Advanced)

1. **Reduce power**: Lower throttle to 50%
2. **Descend**: Gentle nose down to achieve -500 FPM descent
3. **Extend flaps**: Press `]` to lower flaps for more lift
4. **Lower gear**: Press `G` to put gear down
5. **Final approach**: Aim for 70-80 knots, -300 to -500 FPM descent
6. **Touchdown**: Gently flare (nose up) just before ground contact
7. **Brake**: Press `B` to slow down after landing

## Tips for Success

### For New Pilots

- **Start simple**: Just practice taking off and climbing straight ahead
- **Small inputs**: Make small, gentle control movements
- **Watch instruments**: Keep monitoring airspeed and altitude
- **Don't panic**: If you're climbing or descending too fast, make gentle corrections
- **Practice patience**: Flying takes practice - crashes are part of learning!

### Flight Envelope

**Cessna 172 Performance:**
- Stall speed (flaps up): ~48 knots
- Normal climb speed: 70-80 knots
- Cruise speed: 90-110 knots
- Maximum speed: 158 knots (don't exceed!)
- Best rate of climb: 400-700 FPM

### Common Mistakes

1. **Too much nose up on takeoff**: Results in slow climb and possible stall
2. **Forgetting to reduce power**: Engine will overrev at full throttle in level flight
3. **Landing too fast**: Try to be at 70-80 knots for landing
4. **Forgetting landing gear**: Always put gear down before landing!

## Accessibility Features

AirBorne is designed to be fully playable without visual feedback:

- **Audio cues** (when enabled): Engine sounds, TTS announcements
- **Keyboard-only control**: No mouse required
- **Clear instrument readouts**: Large, centered flight instruments
- **Status feedback**: All critical information displayed on screen

## Advanced Features

Once you're comfortable with basic flight:

- **Autopilot** (coming soon): Automatic altitude/heading hold
- **Radio communications**: Interact with ATC
- **Navigation**: Fly to airports using navigation aids
- **Checklist system**: Follow standard procedures

## Troubleshooting

### Game won't start
- Make sure you ran `uv sync` to install dependencies
- Check that you're in the project directory

### Controls not working
- Make sure the game window has focus
- Try clicking on the window first

### Aircraft falling immediately
- You may have started in the air - add throttle quickly!
- Check that you haven't accidentally deployed full flaps

## Practice Exercises

### Exercise 1: Straight and Level
1. Take off and climb to 3000 feet
2. Level off and maintain altitude within ±100 feet
3. Maintain airspeed at 100 knots ±5 knots
4. Hold for 2 minutes

### Exercise 2: Climbing and Descending
1. From level flight at 2000 feet
2. Climb to 3000 feet at +500 FPM
3. Level off at 3000 feet
4. Descend to 2000 feet at -500 FPM
5. Level off at 2000 feet

### Exercise 3: Pattern Work
1. Take off from runway
2. Climb straight ahead to 1000 feet
3. Turn left 90 degrees
4. Level off, fly for 30 seconds
5. Turn left 90 degrees (now flying opposite direction)
6. Turn left 90 degrees (now flying toward runway)
7. Descend and attempt landing

## Getting Help

- Check logs in the console output for error messages
- Review this guide for control references
- Experiment! The simulator is forgiving - you can always restart

## Have Fun!

Remember: Real pilots make hundreds of practice flights before becoming proficient. Take your time, enjoy the learning process, and happy flying!

---

**Note**: AirBorne is in active development. Some features may change or be added in future updates.

#!/usr/bin/env python3
"""Debug script to test propeller thrust calculation."""

from airborne.systems.propeller.fixed_pitch import FixedPitchPropeller

# Create C172 propeller
prop = FixedPitchPropeller(
    diameter_m=1.905,  # 75 inches
    pitch_ratio=0.6,
    efficiency_static=0.50,
    efficiency_cruise=0.80,
)

print("=" * 60)
print("PROPELLER THRUST CALCULATION TEST")
print("=" * 60)

# Test conditions
test_conditions = [
    {"power_hp": 0, "rpm": 0, "airspeed_mps": 0, "desc": "Engine off"},
    {"power_hp": 180, "rpm": 2700, "airspeed_mps": 0, "desc": "Full power, static (v=0)"},
    {"power_hp": 180, "rpm": 2700, "airspeed_mps": 10, "desc": "Full power, 10 m/s (19 kts)"},
    {"power_hp": 180, "rpm": 2700, "airspeed_mps": 30, "desc": "Full power, 30 m/s (58 kts)"},
    {"power_hp": 160, "rpm": 2400, "airspeed_mps": 0, "desc": "75% power, static"},
    {"power_hp": 90, "rpm": 1800, "airspeed_mps": 0, "desc": "50% power, static"},
]

for cond in test_conditions:
    thrust_n = prop.calculate_thrust(
        power_hp=cond["power_hp"],
        rpm=cond["rpm"],
        airspeed_mps=cond["airspeed_mps"],
        air_density_kgm3=1.225,
    )
    thrust_lbf = thrust_n * 0.224809  # Convert N to lbf

    print(f"\n{cond['desc']}:")
    print(f"  Power: {cond['power_hp']} HP @ {cond['rpm']} RPM")
    print(f"  Airspeed: {cond['airspeed_mps']:.1f} m/s")
    print(f"  → Thrust: {thrust_n:.1f} N ({thrust_lbf:.1f} lbf)")

print("\n" + "=" * 60)
print("EXPECTED: C172 should produce ~785N (176 lbf) static thrust")
print("=" * 60)

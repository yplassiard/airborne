#!/usr/bin/env python3
"""Analyze drag and deceleration for C172."""

import math

# C172 parameters
wing_area_m2 = 174 * 0.092903  # 174 sqft to m²
drag_coefficient = 0.027
air_density = 1.225  # kg/m³
mass_kg = 2550 * 0.453592  # 2550 lbs to kg
thrust_static_n = 581  # From propeller calculation

print("=" * 70)
print("C172 DRAG AND DECELERATION ANALYSIS")
print("=" * 70)
print(f"Wing area: {wing_area_m2:.2f} m²")
print(f"Drag coefficient (Cd0): {drag_coefficient}")
print(f"Mass: {mass_kg:.0f} kg")
print(f"Static thrust: {thrust_static_n:.0f} N")
print()

# Test at different airspeeds
speeds_kts = [0, 10, 20, 30, 40, 50, 60]

print(f"{'V (kts)':<10} {'V (m/s)':<10} {'Drag (N)':<12} {'Decel (m/s²)':<15} {'T-D (N)':<12}")
print("-" * 70)

for v_kts in speeds_kts:
    v_ms = v_kts * 0.514444  # knots to m/s

    # Dynamic pressure: q = 0.5 * ρ * v²
    q = 0.5 * air_density * v_ms * v_ms

    # Drag force: D = q * S * Cd
    drag_n = q * wing_area_m2 * drag_coefficient

    # Deceleration if throttle = 0: a = -D / m
    decel_ms2 = -drag_n / mass_kg

    # Net force with full throttle (at static thrust)
    # Note: thrust decreases with speed, but using static for comparison
    net_force_static = thrust_static_n - drag_n

    print(f"{v_kts:<10} {v_ms:<10.2f} {drag_n:<12.1f} {decel_ms2:<15.4f} {net_force_static:<12.1f}")

print()
print("=" * 70)
print("GROUND FRICTION ANALYSIS")
print("=" * 70)

# Check ground rolling resistance
weight_n = mass_kg * 9.81
mu_rolling = 0.02  # Typical for paved runway with wheels
friction_force_n = mu_rolling * weight_n

print(f"Weight: {weight_n:.0f} N")
print(f"Rolling friction coefficient (μ): {mu_rolling}")
print(f"Rolling friction force: {friction_force_n:.0f} N")
print(f"Deceleration from friction alone: {-friction_force_n/mass_kg:.3f} m/s²")

print()
print("=" * 70)
print("FINDINGS")
print("=" * 70)
print(f"1. At 40 knots ({40*0.514444:.1f} m/s):")
v_40_ms = 40 * 0.514444
q_40 = 0.5 * air_density * v_40_ms * v_40_ms
drag_40 = q_40 * wing_area_m2 * drag_coefficient
decel_40 = -drag_40 / mass_kg
print(f"   - Aerodynamic drag: {drag_40:.1f} N")
print(f"   - Deceleration (aero only): {decel_40:.3f} m/s² ({decel_40*3.6:.2f} km/h/s)")
print(f"   - Deceleration (with ground friction): {(decel_40 - friction_force_n/mass_kg):.3f} m/s²")
print()
print(f"2. Time to decelerate from 40 to 0 knots (aero drag only):")
time_to_stop = v_40_ms / abs(decel_40)
print(f"   - {time_to_stop:.1f} seconds")
print()
print(f"3. Time to decelerate from 40 to 0 knots (with ground friction):")
total_decel = abs(decel_40) + friction_force_n/mass_kg
time_to_stop_total = v_40_ms / total_decel
print(f"   - {time_to_stop_total:.1f} seconds")
print()
print("**ISSUE**: If no deceleration observed, possible causes:")
print("  - Ground friction not applied when on ground")
print("  - Aerodynamic drag too small (Cd might need increase)")
print("  - Propeller producing residual thrust at idle (should be ~0 at idle)")
print("=" * 70)

"""Propeller system for thrust generation.

This module provides propeller models that convert engine power to thrust.
Different propeller types (fixed-pitch, constant-speed, jet) have different
efficiency characteristics.
"""

from airborne.systems.propeller.base import IPropeller
from airborne.systems.propeller.fixed_pitch import FixedPitchPropeller

__all__ = ["IPropeller", "FixedPitchPropeller"]

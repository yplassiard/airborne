"""Performance calculation systems.

This module provides aircraft performance calculations including:
- V-speeds (stall, rotation, climb speeds)
- Takeoff distances (ground roll, obstacle clearance)
- Climb performance
- Weight-dependent performance adjustments
"""

from airborne.systems.performance.performance_calculator import PerformanceCalculator
from airborne.systems.performance.vspeeds import VSpeedCalculator

__all__ = ["PerformanceCalculator", "VSpeedCalculator"]

"""Fuel systems package.

Provides abstract interfaces and concrete implementations for aircraft
fuel systems including tanks, pumps, fuel management, and consumption.
"""

from airborne.systems.fuel.base import (
    FuelSelectorPosition,
    FuelState,
    FuelTank,
    FuelType,
    IFuelSystem,
)
from airborne.systems.fuel.simple_gravity import SimpleGravityFuelSystem

__all__ = [
    "FuelSelectorPosition",
    "FuelState",
    "FuelTank",
    "FuelType",
    "IFuelSystem",
    "SimpleGravityFuelSystem",
]

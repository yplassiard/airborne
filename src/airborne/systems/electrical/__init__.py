"""Electrical systems package.

Provides abstract interfaces and concrete implementations for aircraft
electrical systems including batteries, alternators/generators, buses, and loads.
"""

from airborne.systems.electrical.base import (
    BatteryType,
    ElectricalBus,
    ElectricalLoad,
    ElectricalState,
    IElectricalSystem,
    PowerSource,
)
from airborne.systems.electrical.simple_12v import Simple12VElectricalSystem

__all__ = [
    "BatteryType",
    "ElectricalBus",
    "ElectricalLoad",
    "ElectricalState",
    "IElectricalSystem",
    "PowerSource",
    "Simple12VElectricalSystem",
]

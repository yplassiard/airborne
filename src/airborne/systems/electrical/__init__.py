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

__all__ = [
    "BatteryType",
    "ElectricalBus",
    "ElectricalLoad",
    "ElectricalState",
    "IElectricalSystem",
    "PowerSource",
]

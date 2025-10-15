"""Engine systems package.

Provides abstract interfaces and concrete implementations for aircraft
engines including piston, turboprop, turbofan, and turbojet engines.
"""

from airborne.systems.engines.base import (
    EngineControls,
    EngineIgnitionType,
    EngineState,
    EngineType,
    IEngine,
)
from airborne.systems.engines.piston_simple import SimplePistonEngine

__all__ = [
    "EngineControls",
    "EngineIgnitionType",
    "EngineState",
    "EngineType",
    "IEngine",
    "SimplePistonEngine",
]

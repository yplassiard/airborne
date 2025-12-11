"""Aerodynamic systems for aircraft.

This package contains systems for high-lift devices and other
aerodynamic control surfaces.

Systems:
- Slats: Leading-edge slats (automatic or manual)
- Flaperons: Combined flap/aileron surfaces
"""

from airborne.systems.aerodynamics.flaperons import FlaperonState, FlaperonSystem, IFlaperons
from airborne.systems.aerodynamics.slats import AutomaticSlats, ISlats, SlatsState

__all__ = [
    "ISlats",
    "AutomaticSlats",
    "SlatsState",
    "IFlaperons",
    "FlaperonSystem",
    "FlaperonState",
]

"""Safety plugins for flight safety monitoring and crash detection."""

from airborne.plugins.safety.damage_model import CrashReport, DamageModel, DamageType
from airborne.plugins.safety.gpws_plugin import GPWSPlugin
from airborne.plugins.safety.landing_monitor import LandingMonitorPlugin

__all__ = [
    "GPWSPlugin",
    "DamageModel",
    "DamageType",
    "CrashReport",
    "LandingMonitorPlugin",
]

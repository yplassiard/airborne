"""Radio communications system for AirBorne.

This package provides radio communications functionality including:
- Frequency management (COM/NAV radios)
- ATC communications with realistic phraseology
- ATIS information broadcasts
- Push-to-talk mechanics
"""

from airborne.plugins.radio.frequency_manager import FrequencyManager, RadioType

__all__ = ["FrequencyManager", "RadioType"]

"""Aviation-related utilities and standards.

This module provides aviation-specific functionality including callsign
management, ICAO standards, and aviation regulations.

Typical usage:
    from airborne.aviation import CallsignGenerator

    generator = CallsignGenerator()
    callsign = generator.generate_ga_callsign(country_code="N")
"""

from airborne.aviation.callsign import Callsign, CallsignGenerator, CallsignType

__all__ = [
    "Callsign",
    "CallsignGenerator",
    "CallsignType",
]

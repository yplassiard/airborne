"""Terrain and elevation subsystem for AirBorne."""

from airborne.terrain.elevation_service import (
    ElevationCache,
    ElevationQuery,
    ElevationService,
    IElevationProvider,
)
from airborne.terrain.srtm_provider import (
    ConstantElevationProvider,
    SimpleFlatEarthProvider,
    SRTMProvider,
)

__all__ = [
    "ConstantElevationProvider",
    "ElevationCache",
    "ElevationQuery",
    "ElevationService",
    "IElevationProvider",
    "SimpleFlatEarthProvider",
    "SRTMProvider",
]

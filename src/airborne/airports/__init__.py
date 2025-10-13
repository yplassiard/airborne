"""Airport database and navigation systems.

This module provides functionality for working with airport data from
the OurAirports database, including spatial queries, runway information,
and frequencies.

Typical usage:
    from airborne.airports import AirportDatabase

    db = AirportDatabase()
    db.load_from_csv("data/airports")

    airport = db.get_airport("KPAO")
    nearby = db.get_airports_near(position, radius_nm=50)
"""

from airborne.airports.classifier import AirportCategory, AirportClassifier
from airborne.airports.database import (
    Airport,
    AirportDatabase,
    AirportType,
    Frequency,
    FrequencyType,
    Runway,
    SurfaceType,
)
from airborne.airports.spatial_index import SpatialIndex

__all__ = [
    "Airport",
    "AirportCategory",
    "AirportClassifier",
    "AirportDatabase",
    "AirportType",
    "Frequency",
    "FrequencyType",
    "Runway",
    "SpatialIndex",
    "SurfaceType",
]

"""Airport database parser and query system.

This module provides functionality for loading and querying the OurAirports
database, including airports, runways, and frequencies.

Typical usage:
    db = AirportDatabase()
    db.load_from_csv("data/airports")

    airport = db.get_airport("KPAO")
    runways = db.get_runways("KPAO")
    nearby = db.get_airports_near(position, radius_nm=50)
"""

import csv
import logging
import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from airborne.physics.vectors import Vector3

logger = logging.getLogger(__name__)


class AirportType(Enum):
    """Airport type classification."""

    HELIPORT = "heliport"
    SMALL_AIRPORT = "small_airport"
    SEAPLANE_BASE = "seaplane_base"
    MEDIUM_AIRPORT = "medium_airport"
    LARGE_AIRPORT = "large_airport"
    CLOSED = "closed"
    BALLOONPORT = "balloonport"


class SurfaceType(Enum):
    """Runway surface type."""

    ASPH = "asphalt"
    CONC = "concrete"
    TURF = "turf"
    DIRT = "dirt"
    GRVL = "gravel"
    GRASS = "grass"
    SAND = "sand"
    WATER = "water"
    UNKNOWN = "unknown"


class FrequencyType(Enum):
    """Radio frequency type."""

    TWR = "tower"
    GND = "ground"
    ATIS = "atis"
    UNICOM = "unicom"
    CTAF = "ctaf"
    APPROACH = "approach"
    DEPARTURE = "departure"
    CLEARANCE = "clearance"
    MULTICOM = "multicom"
    FSS = "fss"
    OTHER = "other"


@dataclass
class Airport:
    """Airport information from OurAirports database.

    Attributes:
        icao: ICAO code (e.g., "KPAO")
        name: Airport name
        position: Geographic position (lat, lon, elevation in meters)
        airport_type: Type classification
        municipality: City/town name
        iso_country: ISO country code
        scheduled_service: Whether airport has scheduled airline service
        iata_code: IATA code (3-letter, if exists)
        gps_code: GPS code
        home_link: Airport website URL
        wikipedia_link: Wikipedia URL
    """

    icao: str
    name: str
    position: Vector3  # x=longitude, y=elevation, z=latitude
    airport_type: AirportType
    municipality: str
    iso_country: str
    scheduled_service: bool
    iata_code: str | None = None
    gps_code: str | None = None
    home_link: str | None = None
    wikipedia_link: str | None = None


@dataclass
class Runway:
    """Runway information.

    Attributes:
        airport_icao: Parent airport ICAO code
        runway_id: Runway identifier (e.g., "09/27")
        length_ft: Runway length in feet
        width_ft: Runway width in feet
        surface: Surface type
        lighted: Whether runway is lighted
        closed: Whether runway is closed
        le_ident: Low-end identifier (e.g., "09")
        le_latitude: Low-end latitude
        le_longitude: Low-end longitude
        le_elevation_ft: Low-end elevation in feet
        le_heading_deg: Low-end magnetic heading
        he_ident: High-end identifier (e.g., "27")
        he_latitude: High-end latitude
        he_longitude: High-end longitude
        he_elevation_ft: High-end elevation in feet
        he_heading_deg: High-end magnetic heading
    """

    airport_icao: str
    runway_id: str
    length_ft: float
    width_ft: float
    surface: SurfaceType
    lighted: bool
    closed: bool
    le_ident: str
    le_latitude: float
    le_longitude: float
    le_elevation_ft: float
    le_heading_deg: float
    he_ident: str
    he_latitude: float
    he_longitude: float
    he_elevation_ft: float
    he_heading_deg: float


@dataclass
class Frequency:
    """Radio frequency information.

    Attributes:
        airport_icao: Parent airport ICAO code
        freq_type: Frequency type
        description: Frequency description
        frequency_mhz: Frequency in MHz
    """

    airport_icao: str
    freq_type: FrequencyType
    description: str
    frequency_mhz: float


class AirportDatabase:
    """Airport database with spatial querying capability.

    Loads airport, runway, and frequency data from OurAirports CSV files
    and provides fast spatial queries.

    Examples:
        >>> db = AirportDatabase()
        >>> db.load_from_csv("data/airports")
        >>> airport = db.get_airport("KPAO")
        >>> print(f"{airport.name} at {airport.position}")
        >>> nearby = db.get_airports_near(airport.position, radius_nm=10)
    """

    def __init__(self) -> None:
        """Initialize empty database."""
        self.airports: dict[str, Airport] = {}
        self.runways: dict[str, list[Runway]] = {}  # Keyed by airport ICAO
        self.frequencies: dict[str, list[Frequency]] = {}  # Keyed by airport ICAO

    def load_from_csv(self, data_dir: str | Path) -> None:
        """Load airport data from CSV files.

        Args:
            data_dir: Directory containing airports.csv, runways.csv,
                     and airport-frequencies.csv

        Raises:
            FileNotFoundError: If required CSV files not found
            ValueError: If CSV data is invalid

        Examples:
            >>> db = AirportDatabase()
            >>> db.load_from_csv("data/airports")
        """
        data_dir = Path(data_dir)

        # Load airports
        airports_file = data_dir / "airports.csv"
        if not airports_file.exists():
            raise FileNotFoundError(f"Airports file not found: {airports_file}")

        logger.info("Loading airports from %s", airports_file)
        self._load_airports(airports_file)
        logger.info("Loaded %d airports", len(self.airports))

        # Load runways
        runways_file = data_dir / "runways.csv"
        if runways_file.exists():
            logger.info("Loading runways from %s", runways_file)
            self._load_runways(runways_file)
            runway_count = sum(len(rws) for rws in self.runways.values())
            logger.info("Loaded %d runways for %d airports", runway_count, len(self.runways))

        # Load frequencies
        frequencies_file = data_dir / "airport-frequencies.csv"
        if frequencies_file.exists():
            logger.info("Loading frequencies from %s", frequencies_file)
            self._load_frequencies(frequencies_file)
            freq_count = sum(len(freqs) for freqs in self.frequencies.values())
            logger.info("Loaded %d frequencies for %d airports", freq_count, len(self.frequencies))

    def _load_airports(self, csv_path: Path) -> None:
        """Load airports from CSV file."""
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                try:
                    # Only load airports with ICAO codes
                    icao = row.get("icao_code", "").strip()
                    if not icao:
                        continue

                    # Parse coordinates
                    lat = float(row["latitude_deg"])
                    lon = float(row["longitude_deg"])
                    elevation_ft = float(row["elevation_ft"]) if row["elevation_ft"] else 0.0
                    elevation_m = elevation_ft * 0.3048  # Convert feet to meters

                    # Parse type
                    try:
                        airport_type = AirportType(row["type"])
                    except ValueError:
                        airport_type = AirportType.SMALL_AIRPORT

                    # Create airport
                    airport = Airport(
                        icao=icao,
                        name=row["name"],
                        position=Vector3(lon, elevation_m, lat),
                        airport_type=airport_type,
                        municipality=row.get("municipality", ""),
                        iso_country=row.get("iso_country", ""),
                        scheduled_service=row.get("scheduled_service", "no") == "yes",
                        iata_code=row.get("iata_code") or None,
                        gps_code=row.get("gps_code") or None,
                        home_link=row.get("home_link") or None,
                        wikipedia_link=row.get("wikipedia_link") or None,
                    )

                    self.airports[icao] = airport

                except (ValueError, KeyError) as e:
                    logger.debug("Skipping invalid airport row: %s", e)
                    continue

    def _load_runways(self, csv_path: Path) -> None:
        """Load runways from CSV file."""
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                try:
                    # Get airport identifier
                    airport_ident = row.get("airport_ident", "").strip()

                    # Try to find airport by ident
                    if airport_ident not in self.airports:
                        continue

                    # Parse surface type
                    surface_str = row.get("surface", "").upper()
                    surface = SurfaceType.UNKNOWN
                    for surf_type in SurfaceType:
                        if surf_type.name in surface_str:
                            surface = surf_type
                            break

                    # Create runway
                    runway = Runway(
                        airport_icao=airport_ident,
                        runway_id=row.get("le_ident", "") + "/" + row.get("he_ident", ""),
                        length_ft=float(row.get("length_ft", 0) or 0),
                        width_ft=float(row.get("width_ft", 0) or 0),
                        surface=surface,
                        lighted=row.get("lighted", "0") == "1",
                        closed=row.get("closed", "0") == "1",
                        le_ident=row.get("le_ident", ""),
                        le_latitude=float(row.get("le_latitude_deg", 0) or 0),
                        le_longitude=float(row.get("le_longitude_deg", 0) or 0),
                        le_elevation_ft=float(row.get("le_elevation_ft", 0) or 0),
                        le_heading_deg=float(row.get("le_heading_degT", 0) or 0),
                        he_ident=row.get("he_ident", ""),
                        he_latitude=float(row.get("he_latitude_deg", 0) or 0),
                        he_longitude=float(row.get("he_longitude_deg", 0) or 0),
                        he_elevation_ft=float(row.get("he_elevation_ft", 0) or 0),
                        he_heading_deg=float(row.get("he_heading_degT", 0) or 0),
                    )

                    # Add to runway list for airport
                    if airport_ident not in self.runways:
                        self.runways[airport_ident] = []
                    self.runways[airport_ident].append(runway)

                except (ValueError, KeyError) as e:
                    logger.debug("Skipping invalid runway row: %s", e)
                    continue

    def _load_frequencies(self, csv_path: Path) -> None:
        """Load frequencies from CSV file."""
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                try:
                    # Get airport reference
                    airport_ident = row.get("airport_ident", "").strip()
                    if airport_ident not in self.airports:
                        continue

                    # Parse frequency type
                    type_str = row.get("type", "").upper()
                    freq_type = FrequencyType.OTHER
                    for ftype in FrequencyType:
                        if ftype.name in type_str:
                            freq_type = ftype
                            break

                    # Create frequency
                    frequency = Frequency(
                        airport_icao=airport_ident,
                        freq_type=freq_type,
                        description=row.get("description", ""),
                        frequency_mhz=float(row.get("frequency_mhz", 0)),
                    )

                    # Add to frequency list for airport
                    if airport_ident not in self.frequencies:
                        self.frequencies[airport_ident] = []
                    self.frequencies[airport_ident].append(frequency)

                except (ValueError, KeyError) as e:
                    logger.debug("Skipping invalid frequency row: %s", e)
                    continue

    def get_airport(self, icao: str) -> Airport | None:
        """Get airport by ICAO code.

        Args:
            icao: ICAO code (e.g., "KPAO")

        Returns:
            Airport if found, None otherwise

        Examples:
            >>> airport = db.get_airport("KPAO")
            >>> if airport:
            ...     print(airport.name)
        """
        return self.airports.get(icao.upper())

    def get_runways(self, icao: str) -> list[Runway]:
        """Get runways for an airport.

        Args:
            icao: Airport ICAO code

        Returns:
            List of runways (empty if none found)

        Examples:
            >>> runways = db.get_runways("KPAO")
            >>> for runway in runways:
            ...     print(f"{runway.runway_id}: {runway.length_ft}ft")
        """
        return self.runways.get(icao.upper(), [])

    def get_frequencies(self, icao: str) -> list[Frequency]:
        """Get frequencies for an airport.

        Args:
            icao: Airport ICAO code

        Returns:
            List of frequencies (empty if none found)

        Examples:
            >>> freqs = db.get_frequencies("KPAO")
            >>> for freq in freqs:
            ...     print(f"{freq.freq_type.value}: {freq.frequency_mhz:.3f}")
        """
        return self.frequencies.get(icao.upper(), [])

    def get_airports_near(self, position: Vector3, radius_nm: float) -> list[tuple[Airport, float]]:
        """Get airports within radius of position.

        Args:
            position: Center position (x=lon, y=elev, z=lat)
            radius_nm: Search radius in nautical miles

        Returns:
            List of (airport, distance_nm) tuples, sorted by distance

        Examples:
            >>> nearby = db.get_airports_near(Vector3(-122.05, 0, 37.36), 10)
            >>> for airport, distance in nearby:
            ...     print(f"{airport.icao}: {distance:.1f} nm")
        """
        results = []

        for airport in self.airports.values():
            distance_nm = self._haversine_distance_nm(position, airport.position)
            if distance_nm <= radius_nm:
                results.append((airport, distance_nm))

        # Sort by distance
        results.sort(key=lambda x: x[1])
        return results

    @staticmethod
    def _haversine_distance_nm(pos1: Vector3, pos2: Vector3) -> float:
        """Calculate great circle distance between two positions.

        Args:
            pos1: First position (x=lon, y=elev, z=lat)
            pos2: Second position (x=lon, y=elev, z=lat)

        Returns:
            Distance in nautical miles
        """
        # Extract lat/lon from Vector3 (z=lat, x=lon)
        lat1, lon1 = math.radians(pos1.z), math.radians(pos1.x)
        lat2, lon2 = math.radians(pos2.z), math.radians(pos2.x)

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))

        # Earth radius in nautical miles
        radius_nm = 3440.065

        return c * radius_nm

    def get_airport_count(self) -> int:
        """Get total number of airports in database.

        Returns:
            Number of airports

        Examples:
            >>> count = db.get_airport_count()
            >>> print(f"Database contains {count} airports")
        """
        return len(self.airports)

    def get_countries(self) -> list[str]:
        """Get list of all countries with airports.

        Returns:
            Sorted list of ISO country codes

        Examples:
            >>> countries = db.get_countries()
            >>> print(f"Airports in {len(countries)} countries")
        """
        countries = {airport.iso_country for airport in self.airports.values()}
        return sorted(countries)

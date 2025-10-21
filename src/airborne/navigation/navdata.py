"""Navigation database for managing navaids and waypoints.

This module provides functionality for loading, querying, and managing
navigation aids (VOR, NDB, waypoints, etc.) from various data sources.

Typical usage:
    db = NavDatabase()
    db.load_from_csv("data/navigation/navaids.csv")

    vor = db.find_navaid("SFO")
    nearby = db.find_navaids_near(position, radius_nm=50)
"""

import csv
import logging
import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from airborne.physics.vectors import Vector3

logger = logging.getLogger(__name__)


class NavaidType(Enum):
    """Navigation aid type classification.

    Attributes:
        VOR: VHF Omnidirectional Range
        NDB: Non-Directional Beacon
        DME: Distance Measuring Equipment
        WAYPOINT: GPS waypoint / fix
        FIX: Named intersection point
        AIRPORT: Airport reference point
    """

    VOR = "VOR"
    NDB = "NDB"
    DME = "DME"
    WAYPOINT = "WAYPOINT"
    FIX = "FIX"
    AIRPORT = "AIRPORT"


@dataclass
class Navaid:
    """Navigation aid information.

    Represents a single navigation aid with position, frequency (if applicable),
    and service volume.

    Attributes:
        identifier: Unique identifier (e.g., "SFO", "KSFO", "MODET")
        name: Human-readable name (e.g., "San Francisco VOR")
        type: Type of navaid (VOR, NDB, WAYPOINT, etc.)
        position: 3D position (x=longitude, y=elevation_m, z=latitude)
        frequency: Frequency in MHz for VOR/NDB, None for waypoints
        range_nm: Service volume radius in nautical miles

    Examples:
        >>> vor = Navaid(
        ...     identifier="SFO",
        ...     name="San Francisco VOR",
        ...     type=NavaidType.VOR,
        ...     position=Vector3(-122.3790, 13, 37.6213),
        ...     frequency=115.8,
        ...     range_nm=40
        ... )
    """

    identifier: str
    name: str
    type: NavaidType
    position: Vector3  # x=longitude, y=elevation_m, z=latitude
    frequency: float | None = None
    range_nm: float = 0.0

    def __str__(self) -> str:
        """Return string representation of navaid.

        Returns:
            String with identifier, type, and frequency if applicable
        """
        if self.frequency:
            return f"{self.identifier} ({self.type.value} {self.frequency:.2f})"
        return f"{self.identifier} ({self.type.value})"


class NavDatabase:
    """Database for navigation aids and waypoints.

    Manages a collection of navaids with spatial indexing for efficient
    queries by identifier or proximity.

    Attributes:
        navaids: Dictionary mapping identifier to Navaid

    Examples:
        >>> db = NavDatabase()
        >>> db.load_from_csv("data/navigation/navaids.csv")
        >>> vor = db.find_navaid("SFO")
        >>> nearby = db.find_navaids_near(position, radius_nm=50)
    """

    def __init__(self) -> None:
        """Initialize empty navigation database."""
        self.navaids: dict[str, Navaid] = {}
        logger.info("Initialized navigation database")

    def add_navaid(self, navaid: Navaid) -> None:
        """Add a navaid to the database.

        Args:
            navaid: Navaid to add

        Note:
            If a navaid with the same identifier exists, it will be replaced.
        """
        self.navaids[navaid.identifier] = navaid
        logger.debug(f"Added navaid: {navaid}")

    def find_navaid(self, identifier: str) -> Navaid | None:
        """Find navaid by identifier.

        Args:
            identifier: Navaid identifier (case-sensitive)

        Returns:
            Navaid if found, None otherwise

        Examples:
            >>> db = NavDatabase()
            >>> vor = db.find_navaid("SFO")
        """
        return self.navaids.get(identifier)

    def find_navaids_near(
        self, position: Vector3, radius_nm: float, navaid_type: NavaidType | None = None
    ) -> list[Navaid]:
        """Find navaids within radius of position.

        Args:
            position: Center position to search from (x=lon, y=elev, z=lat)
            radius_nm: Search radius in nautical miles
            navaid_type: Optional filter by navaid type

        Returns:
            List of navaids within radius, sorted by distance (closest first)

        Examples:
            >>> navaids = db.find_navaids_near(position, radius_nm=50)
            >>> vors = db.find_navaids_near(position, 50, NavaidType.VOR)
        """
        results = []

        for navaid in self.navaids.values():
            # Filter by type if specified
            if navaid_type and navaid.type != navaid_type:
                continue

            # Calculate great circle distance using Haversine formula
            distance_nm = self._haversine_distance_nm(position, navaid.position)

            if distance_nm <= radius_nm:
                results.append((distance_nm, navaid))

        # Sort by distance (closest first)
        results.sort(key=lambda x: x[0])

        return [navaid for _, navaid in results]

    def find_navaids_by_type(self, navaid_type: NavaidType) -> list[Navaid]:
        """Find all navaids of a specific type.

        Args:
            navaid_type: Type of navaid to find

        Returns:
            List of all navaids of the specified type

        Examples:
            >>> vors = db.find_navaids_by_type(NavaidType.VOR)
        """
        return [n for n in self.navaids.values() if n.type == navaid_type]

    def calculate_route_distance(self, waypoints: list[Navaid]) -> float:
        """Calculate total distance along a route.

        Args:
            waypoints: List of navaids defining the route

        Returns:
            Total distance in nautical miles

        Examples:
            >>> route = [db.find_navaid("SFO"), db.find_navaid("OAK")]
            >>> distance = db.calculate_route_distance(route)
        """
        if len(waypoints) < 2:
            return 0.0

        total_distance_nm = 0.0
        for i in range(len(waypoints) - 1):
            distance_nm = self._haversine_distance_nm(
                waypoints[i].position, waypoints[i + 1].position
            )
            total_distance_nm += distance_nm

        return total_distance_nm

    def load_from_csv(self, csv_path: str) -> int:
        """Load navaids from CSV file.

        Expected CSV format:
            identifier,name,type,latitude,longitude,elevation_ft,frequency,range_nm

        Args:
            csv_path: Path to CSV file

        Returns:
            Number of navaids loaded

        Raises:
            FileNotFoundError: If CSV file doesn't exist
            ValueError: If CSV format is invalid

        Examples:
            >>> db = NavDatabase()
            >>> count = db.load_from_csv("data/navigation/navaids.csv")
        """
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"Navaid CSV not found: {csv_path}")

        count = 0
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                try:
                    # Parse navaid type
                    navaid_type = NavaidType[row["type"].upper()]

                    # Parse position
                    lat = float(row["latitude"])
                    lon = float(row["longitude"])
                    elevation_ft = float(row.get("elevation_ft", 0))

                    # Convert elevation from feet to meters for Vector3
                    elevation_m = elevation_ft * 0.3048
                    # Vector3 convention: x=longitude, y=elevation, z=latitude
                    position = Vector3(lon, elevation_m, lat)

                    # Parse optional frequency
                    frequency = None
                    if "frequency" in row and row["frequency"]:
                        frequency = float(row["frequency"])

                    # Parse optional range
                    range_nm = float(row.get("range_nm", 0))

                    navaid = Navaid(
                        identifier=row["identifier"],
                        name=row["name"],
                        type=navaid_type,
                        position=position,
                        frequency=frequency,
                        range_nm=range_nm,
                    )

                    self.add_navaid(navaid)
                    count += 1

                except (KeyError, ValueError) as e:
                    logger.warning(f"Skipping invalid navaid row: {e}")
                    continue

        logger.info(f"Loaded {count} navaids from {csv_path}")
        return count

    def count(self) -> int:
        """Return total number of navaids in database.

        Returns:
            Number of navaids
        """
        return len(self.navaids)

    def clear(self) -> None:
        """Remove all navaids from database."""
        self.navaids.clear()
        logger.info("Cleared navigation database")

    @staticmethod
    def _haversine_distance_nm(pos1: Vector3, pos2: Vector3) -> float:
        """Calculate great circle distance between two positions.

        Uses the Haversine formula for accuracy over large distances.

        Args:
            pos1: First position (x=longitude, y=elevation, z=latitude)
            pos2: Second position (x=longitude, y=elevation, z=latitude)

        Returns:
            Distance in nautical miles
        """
        # Convert to radians
        lat1, lon1 = math.radians(pos1.z), math.radians(pos1.x)
        lat2, lon2 = math.radians(pos2.z), math.radians(pos2.x)

        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))

        # Convert to nautical miles
        radius_nm = 3440.065  # Earth radius in nautical miles
        return c * radius_nm

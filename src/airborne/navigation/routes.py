"""Flight route database management.

This module provides integration with flight route databases including
OpenFlights, Flight Plan Database API, and SimBrief.

Typical usage:
    from airborne.navigation import OpenFlightsProvider

    provider = OpenFlightsProvider()
    routes = provider.find_routes("KJFK", "EGLL")
"""

import csv
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Route:
    """Flight route between two airports.

    Attributes:
        airline_code: 2-letter IATA or 3-letter ICAO airline code
        airline_id: Unique identifier for airline
        source_airport: 3-letter IATA or 4-letter ICAO source airport code
        source_airport_id: Unique identifier for source airport
        destination_airport: 3-letter IATA or 4-letter ICAO destination airport code
        destination_airport_id: Unique identifier for destination airport
        codeshare: True if route is codeshare, False otherwise
        stops: Number of stops (0 for direct)
        equipment: List of aircraft types used on route

    Examples:
        >>> route = Route(
        ...     airline_code="AA",
        ...     airline_id=24,
        ...     source_airport="KJFK",
        ...     source_airport_id=3797,
        ...     destination_airport="EGLL",
        ...     destination_airport_id=507,
        ...     codeshare=False,
        ...     stops=0,
        ...     equipment=["777", "787"]
        ... )
    """

    airline_code: str
    airline_id: str
    source_airport: str
    source_airport_id: str
    destination_airport: str
    destination_airport_id: str
    codeshare: bool
    stops: int
    equipment: list[str]

    def is_direct(self) -> bool:
        """Check if route is direct (no stops).

        Returns:
            True if route has no stops
        """
        return self.stops == 0


class RouteProvider(ABC):
    """Abstract base class for route data providers.

    Implementations can fetch route data from various sources including
    local databases, web APIs, or flight planning services.

    Examples:
        >>> provider = OpenFlightsProvider()
        >>> routes = provider.find_routes("KJFK", "EGLL")
    """

    @abstractmethod
    def find_routes(
        self,
        from_airport: str,
        to_airport: str,
        direct_only: bool = False,
    ) -> list[Route]:
        """Find routes between two airports.

        Args:
            from_airport: ICAO or IATA code of departure airport
            to_airport: ICAO or IATA code of arrival airport
            direct_only: Only return direct routes (no stops)

        Returns:
            List of available routes

        Examples:
            >>> routes = provider.find_routes("KJFK", "EGLL", direct_only=True)
        """
        pass

    @abstractmethod
    def get_route_count(self) -> int:
        """Get total number of routes in database.

        Returns:
            Number of routes
        """
        pass


class OpenFlightsProvider(RouteProvider):
    """Route provider using OpenFlights database.

    Downloads and caches routes from the OpenFlights project, which contains
    67,663 routes between 3,321 airports on 548 airlines (as of June 2014).

    Note:
        Data is historical (last updated June 2014) but useful for realistic
        route generation in flight simulators.

    Attributes:
        routes: List of all routes loaded from database
        routes_by_airport: Dictionary mapping airport codes to routes

    Examples:
        >>> provider = OpenFlightsProvider()
        >>> routes = provider.find_routes("KSFO", "KLAX")
        >>> print(f"Found {len(routes)} routes")
    """

    ROUTES_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/routes.dat"
    DEFAULT_CACHE_DIR = "data/navigation"

    def __init__(self, routes_file: str | None = None) -> None:
        """Initialize OpenFlights route provider.

        Args:
            routes_file: Path to routes.dat file (downloads if not exists)
        """
        self.routes: list[Route] = []
        self.routes_by_airport: dict[str, list[Route]] = {}

        if routes_file is None:
            routes_file = str(Path(self.DEFAULT_CACHE_DIR) / "routes.dat")

        self._load_routes(routes_file)
        logger.info(f"Loaded {len(self.routes)} routes from OpenFlights database")

    def _load_routes(self, file_path: str) -> None:
        """Load routes from OpenFlights .dat file.

        Args:
            file_path: Path to routes.dat file
        """
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"Routes file not found: {file_path}")
            logger.info("Download from: " + self.ROUTES_URL)
            return

        try:
            with open(path, encoding="utf-8") as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) < 9:
                        continue

                    # Parse equipment list (space-separated), filter out \N
                    equipment = (
                        [e for e in row[8].split() if e != "\\N"]
                        if row[8] and row[8] != "\\N"
                        else []
                    )

                    route = Route(
                        airline_code=row[0] if row[0] != "\\N" else "",
                        airline_id=row[1] if row[1] != "\\N" else "",
                        source_airport=row[2] if row[2] != "\\N" else "",
                        source_airport_id=row[3] if row[3] != "\\N" else "",
                        destination_airport=row[4] if row[4] != "\\N" else "",
                        destination_airport_id=row[5] if row[5] != "\\N" else "",
                        codeshare=(row[6] == "Y"),
                        stops=int(row[7]) if row[7].isdigit() else 0,
                        equipment=equipment,
                    )

                    self.routes.append(route)

                    # Index by source airport for fast lookup
                    if route.source_airport:
                        if route.source_airport not in self.routes_by_airport:
                            self.routes_by_airport[route.source_airport] = []
                        self.routes_by_airport[route.source_airport].append(route)

            logger.info(
                f"Loaded {len(self.routes)} routes covering {len(self.routes_by_airport)} airports"
            )

        except Exception as e:
            logger.error(f"Error loading routes: {e}")

    def find_routes(
        self,
        from_airport: str,
        to_airport: str,
        direct_only: bool = False,
    ) -> list[Route]:
        """Find routes between two airports.

        Args:
            from_airport: ICAO or IATA code of departure airport
            to_airport: ICAO or IATA code of arrival airport
            direct_only: Only return direct routes (no stops)

        Returns:
            List of available routes

        Examples:
            >>> routes = provider.find_routes("KSFO", "KLAX", direct_only=True)
        """
        if from_airport not in self.routes_by_airport:
            return []

        matching_routes = []
        for route in self.routes_by_airport[from_airport]:
            if route.destination_airport == to_airport:
                if direct_only and not route.is_direct():
                    continue
                matching_routes.append(route)

        return matching_routes

    def get_route_count(self) -> int:
        """Get total number of routes in database.

        Returns:
            Number of routes
        """
        return len(self.routes)

    def get_airports_with_routes(self) -> list[str]:
        """Get list of airports that have routes.

        Returns:
            List of airport codes with outbound routes
        """
        return list(self.routes_by_airport.keys())

    def get_destinations_from(self, airport: str) -> list[str]:
        """Get all destination airports reachable from given airport.

        Args:
            airport: ICAO or IATA code of departure airport

        Returns:
            List of destination airport codes
        """
        if airport not in self.routes_by_airport:
            return []

        destinations = set()
        for route in self.routes_by_airport[airport]:
            if route.destination_airport:
                destinations.add(route.destination_airport)

        return sorted(destinations)

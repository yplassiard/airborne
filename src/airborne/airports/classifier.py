"""Airport classification system.

Classifies airports by size based on runway configuration, length, and surface type.
Used for determining appropriate audio cues and navigation assistance.

Typical usage:
    from airborne.airports import AirportClassifier, AirportCategory

    classifier = AirportClassifier()
    category = classifier.classify(airport, runways)
    print(f"{airport.name} is {category.value}")
"""

import logging
from enum import Enum

from airborne.airports.database import Airport, Runway, SurfaceType

logger = logging.getLogger(__name__)


class AirportCategory(Enum):
    """Airport size category."""

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    XL = "extra_large"


# Major hub airports (always classified as XL)
MAJOR_HUBS = {
    # North America
    "KATL",  # Atlanta Hartsfield-Jackson
    "KLAX",  # Los Angeles International
    "KORD",  # Chicago O'Hare
    "KDFW",  # Dallas/Fort Worth
    "KJFK",  # New York JFK
    "KDEN",  # Denver International
    "KSFO",  # San Francisco International
    "KLAS",  # Las Vegas McCarran
    "KSEA",  # Seattle-Tacoma
    "KMCO",  # Orlando International
    "KMIA",  # Miami International
    "KPHX",  # Phoenix Sky Harbor
    "KIAH",  # Houston George Bush
    "KBOS",  # Boston Logan
    "KCLT",  # Charlotte Douglas
    "KMSP",  # Minneapolis-St. Paul
    "KDTW",  # Detroit Metropolitan
    "KFLL",  # Fort Lauderdale
    "KEWR",  # Newark Liberty
    "KLGA",  # New York LaGuardia
    # Europe
    "EGLL",  # London Heathrow
    "LFPG",  # Paris Charles de Gaulle
    "EDDF",  # Frankfurt
    "EHAM",  # Amsterdam Schiphol
    "LEMD",  # Madrid Barajas
    "LIRF",  # Rome Fiumicino
    "EDDM",  # Munich
    "LEBL",  # Barcelona El Prat
    "EGKK",  # London Gatwick
    "LFPO",  # Paris Orly
    "LSZH",  # Zurich
    "LOWW",  # Vienna International
    "EKCH",  # Copenhagen
    "ESSA",  # Stockholm Arlanda
    "EBBR",  # Brussels
    "EIDW",  # Dublin
    "LPPT",  # Lisbon
    # Asia
    "RJTT",  # Tokyo Haneda
    "RJAA",  # Tokyo Narita
    "VHHH",  # Hong Kong
    "WSSS",  # Singapore Changi
    "ZBAA",  # Beijing Capital
    "ZSPD",  # Shanghai Pudong
    "RKSI",  # Seoul Incheon
    "VTBS",  # Bangkok Suvarnabhumi
    "VIDP",  # Delhi Indira Gandhi
    "VABB",  # Mumbai Chhatrapati Shivaji
    "OMDB",  # Dubai International
    # Australia
    "YSSY",  # Sydney Kingsford Smith
    "YMML",  # Melbourne
}


class AirportClassifier:
    """Classifies airports by size and capability.

    Uses runway count, length, surface type, and known major hubs
    to determine airport category.

    Examples:
        >>> classifier = AirportClassifier()
        >>> category = classifier.classify(airport, runways)
        >>> if category == AirportCategory.LARGE:
        ...     print("Major airport - expect complex taxiways")
    """

    def __init__(self) -> None:
        """Initialize classifier."""
        self.major_hubs = MAJOR_HUBS.copy()

    def classify(self, airport: Airport, runways: list[Runway]) -> AirportCategory:
        """Classify an airport by size.

        Args:
            airport: Airport to classify
            runways: List of runways at the airport

        Returns:
            Airport category (SMALL, MEDIUM, LARGE, or XL)

        Classification logic:
            - XL: In major hubs list, or 4+ runways, or 2+ runways with 12000+ ft
            - LARGE: 2+ paved runways, or runway > 7000 ft
            - MEDIUM: 1-2 paved runways < 7000 ft
            - SMALL: 1 runway < 3000 ft, or grass/dirt surface

        Examples:
            >>> category = classifier.classify(kpao_airport, kpao_runways)
            >>> print(category.value)  # "small"
        """
        # Check if it's a known major hub
        if airport.icao in self.major_hubs:
            logger.debug("Airport %s classified as XL (major hub)", airport.icao)
            return AirportCategory.XL

        # No runways = small
        if not runways:
            logger.debug("Airport %s classified as SMALL (no runways)", airport.icao)
            return AirportCategory.SMALL

        # Analyze runways
        paved_runways = self._get_paved_runways(runways)
        longest_runway = self._get_longest_runway(runways)
        runway_count = len(runways)

        # XL: 4+ runways OR 2+ runways with one being 12000+ ft
        if runway_count >= 4:
            logger.debug("Airport %s classified as XL (%d runways)", airport.icao, runway_count)
            return AirportCategory.XL

        if len(paved_runways) >= 2 and longest_runway and longest_runway.length_ft >= 12000:
            logger.debug(
                "Airport %s classified as XL (2+ runways, %d ft longest)",
                airport.icao,
                longest_runway.length_ft,
            )
            return AirportCategory.XL

        # LARGE: 2+ paved runways OR runway > 7000 ft
        if len(paved_runways) >= 2:
            logger.debug(
                "Airport %s classified as LARGE (%d paved runways)",
                airport.icao,
                len(paved_runways),
            )
            return AirportCategory.LARGE

        if longest_runway and longest_runway.length_ft > 7000:
            logger.debug(
                "Airport %s classified as LARGE (%d ft runway)",
                airport.icao,
                longest_runway.length_ft,
            )
            return AirportCategory.LARGE

        # SMALL: Single runway < 3000 ft OR grass/dirt surface
        if runway_count == 1 and longest_runway:
            if longest_runway.length_ft < 3000:
                logger.debug(
                    "Airport %s classified as SMALL (%d ft runway)",
                    airport.icao,
                    longest_runway.length_ft,
                )
                return AirportCategory.SMALL

            if longest_runway.surface in (SurfaceType.GRASS, SurfaceType.DIRT, SurfaceType.TURF):
                logger.debug(
                    "Airport %s classified as SMALL (%s surface)",
                    airport.icao,
                    longest_runway.surface.value,
                )
                return AirportCategory.SMALL

        # Default: MEDIUM
        logger.debug("Airport %s classified as MEDIUM (default)", airport.icao)
        return AirportCategory.MEDIUM

    def _get_paved_runways(self, runways: list[Runway]) -> list[Runway]:
        """Get list of paved runways.

        Args:
            runways: List of all runways

        Returns:
            List of paved runways (asphalt or concrete)
        """
        return [
            rw
            for rw in runways
            if rw.surface in (SurfaceType.ASPH, SurfaceType.CONC) and not rw.closed
        ]

    def _get_longest_runway(self, runways: list[Runway]) -> Runway | None:
        """Get longest runway.

        Args:
            runways: List of runways

        Returns:
            Longest runway, or None if no runways
        """
        if not runways:
            return None

        return max(runways, key=lambda rw: rw.length_ft)

    def add_major_hub(self, icao: str) -> None:
        """Add an airport to the major hubs list.

        Args:
            icao: ICAO code of airport to add

        Examples:
            >>> classifier.add_major_hub("KPDX")  # Portland becomes XL
        """
        self.major_hubs.add(icao.upper())
        logger.info("Added %s to major hubs list", icao.upper())

    def remove_major_hub(self, icao: str) -> None:
        """Remove an airport from the major hubs list.

        Args:
            icao: ICAO code of airport to remove

        Examples:
            >>> classifier.remove_major_hub("KPDX")
        """
        self.major_hubs.discard(icao.upper())
        logger.info("Removed %s from major hubs list", icao.upper())

    def is_major_hub(self, icao: str) -> bool:
        """Check if an airport is a major hub.

        Args:
            icao: ICAO code to check

        Returns:
            True if airport is in major hubs list

        Examples:
            >>> if classifier.is_major_hub("KLAX"):
            ...     print("LAX is a major hub")
        """
        return icao.upper() in self.major_hubs

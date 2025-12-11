"""X-Plane Gateway airport data loader.

Fetches detailed airport data from the X-Plane Scenery Gateway API,
including taxiway networks, parking positions, and frequencies.

The data is cached locally to avoid repeated API calls.

Typical usage:
    from airborne.services.atc.gateway_loader import GatewayAirportLoader

    loader = GatewayAirportLoader()
    airport_data = loader.get_airport("KPAO")
    if airport_data:
        print(f"Taxi nodes: {len(airport_data.taxi_nodes)}")
"""

import contextlib
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _get_default_cache_dir() -> Path:
    """Get the default cache directory for gateway data.

    Returns a writable cache directory:
    - When bundled: ~/.airborne/cache/airports/gateway_cache
    - When running from source: data/airports/gateway_cache (relative to project root)
    """
    if hasattr(sys, "_MEIPASS"):
        # Bundled app - use user's home directory
        cache_dir = Path.home() / ".airborne" / "cache" / "airports" / "gateway_cache"
    else:
        # Development - use project data directory
        # Import here to avoid circular imports
        from airborne.core.resource_path import get_data_path

        cache_dir = get_data_path("airports/gateway_cache")
    return cache_dir

# Try to import xplane_airports
try:
    from xplane_airports import gateway
    from xplane_airports.AptDat import Airport as XPlaneAirport
    from xplane_airports.AptDat import TaxiRouteNetwork

    XPLANE_AIRPORTS_AVAILABLE = True
except ImportError:
    XPLANE_AIRPORTS_AVAILABLE = False
    gateway = None
    XPlaneAirport = None
    TaxiRouteNetwork = None
    logger.warning("xplane-airports not installed, Gateway loader disabled")


@dataclass
class TaxiNode:
    """A node in the taxiway network.

    Attributes:
        id: Unique node identifier.
        latitude: Node latitude.
        longitude: Node longitude.
        name: Optional node name (for named intersections).
        is_hold_short: Whether this is a runway hold short point.
        on_runway: Runway ID if node is on a runway.
    """

    id: int
    latitude: float
    longitude: float
    name: str = ""
    is_hold_short: bool = False
    on_runway: str = ""


@dataclass
class TaxiEdge:
    """An edge (segment) in the taxiway network.

    Attributes:
        node_begin: Starting node ID.
        node_end: Ending node ID.
        name: Taxiway name (e.g., "A", "B", "J").
        is_runway: Whether this edge is on a runway.
        one_way: Whether this is a one-way taxiway.
        width_code: ICAO width code (A-F).
    """

    node_begin: int
    node_end: int
    name: str
    is_runway: bool = False
    one_way: bool = False
    width_code: str = "E"


@dataclass
class ParkingPosition:
    """A parking/ramp start position.

    Attributes:
        id: Position identifier (e.g., "N17", "Gate 5").
        latitude: Position latitude.
        longitude: Position longitude.
        heading: Aircraft heading when parked.
        type: Parking type (tie_down, gate, hangar).
        aircraft_types: Supported aircraft types.
    """

    id: str
    latitude: float
    longitude: float
    heading: float
    type: str = "tie_down"
    aircraft_types: list[str] = field(default_factory=list)


@dataclass
class GatewayFrequency:
    """Radio frequency from X-Plane Gateway.

    Attributes:
        type: Frequency type (ATIS, Tower, Ground, Approach, etc.).
        frequency_mhz: Frequency in MHz.
        name: Frequency name/description.
    """

    type: str
    frequency_mhz: float
    name: str


@dataclass
class GatewayRunway:
    """Runway data from X-Plane Gateway.

    Attributes:
        id1: First end identifier (e.g., "13").
        id2: Second end identifier (e.g., "31").
        width_m: Runway width in meters.
        lat1: First end latitude.
        lon1: First end longitude.
        lat2: Second end latitude.
        lon2: Second end longitude.
        heading1: Magnetic heading for first end.
        heading2: Magnetic heading for second end.
        surface: Surface type code.
    """

    id1: str
    id2: str
    width_m: float
    lat1: float
    lon1: float
    lat2: float
    lon2: float
    heading1: float = 0.0
    heading2: float = 0.0
    surface: int = 1


@dataclass
class GatewayAirportData:
    """Complete airport data from X-Plane Gateway.

    Attributes:
        icao: ICAO code.
        name: Airport name.
        latitude: Airport latitude.
        longitude: Airport longitude.
        elevation_ft: Elevation in feet.
        transition_altitude: Transition altitude in feet.
        taxi_nodes: Dictionary of taxi nodes by ID.
        taxi_edges: List of taxi edges.
        parking_positions: List of parking positions.
        frequencies: List of frequencies.
        runways: List of runways.
        has_atc: Whether airport has ATC.
    """

    icao: str
    name: str
    latitude: float
    longitude: float
    elevation_ft: float
    transition_altitude: int
    taxi_nodes: dict[int, TaxiNode] = field(default_factory=dict)
    taxi_edges: list[TaxiEdge] = field(default_factory=list)
    parking_positions: list[ParkingPosition] = field(default_factory=list)
    frequencies: list[GatewayFrequency] = field(default_factory=list)
    runways: list[GatewayRunway] = field(default_factory=list)
    has_atc: bool = False


# Frequency type codes from apt.dat specification
FREQ_TYPE_MAP = {
    "1050": "ATIS",
    "1051": "UNICOM",
    "1052": "CLEARANCE",
    "1053": "GROUND",
    "1054": "TOWER",
    "1055": "APPROACH",
    "1056": "DEPARTURE",
}


class GatewayAirportLoader:
    """Load airport data from X-Plane Scenery Gateway.

    Fetches detailed airport scenery data including taxiway networks,
    parking positions, and frequencies. Data is cached locally.

    Examples:
        >>> loader = GatewayAirportLoader()
        >>> data = loader.get_airport("KPAO")
        >>> if data:
        ...     print(f"Nodes: {len(data.taxi_nodes)}, Edges: {len(data.taxi_edges)}")
    """

    def __init__(self, cache_dir: str | Path | None = None) -> None:
        """Initialize the Gateway loader.

        Args:
            cache_dir: Directory for caching fetched data.
                      Defaults to ~/.airborne/cache/airports/gateway_cache when bundled,
                      or data/airports/gateway_cache when running from source.
        """
        if cache_dir is None:
            self.cache_dir = _get_default_cache_dir()
        else:
            self.cache_dir = Path(cache_dir)

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: dict[str, GatewayAirportData] = {}

    def get_airport(self, icao: str) -> GatewayAirportData | None:
        """Get airport data, fetching from Gateway if not cached.

        Args:
            icao: Airport ICAO code.

        Returns:
            GatewayAirportData if available, None otherwise.

        Examples:
            >>> data = loader.get_airport("LFLY")
            >>> print(f"Lyon Bron has {len(data.taxi_nodes)} taxi nodes")
        """
        icao = icao.upper()

        # Check memory cache first
        if icao in self._memory_cache:
            return self._memory_cache[icao]

        # Check disk cache
        cache_file = self.cache_dir / f"{icao}.json"
        if cache_file.exists():
            try:
                data = self._load_from_cache(cache_file)
                if data:
                    self._memory_cache[icao] = data
                    return data
            except Exception as e:
                logger.warning("Failed to load cached data for %s: %s", icao, e)

        # Fetch from Gateway
        if not XPLANE_AIRPORTS_AVAILABLE:
            logger.warning("Cannot fetch %s: xplane-airports not installed", icao)
            return None

        try:
            data = self._fetch_from_gateway(icao)
            if data:
                self._memory_cache[icao] = data
                self._save_to_cache(cache_file, data)
                return data
        except Exception as e:
            logger.error("Failed to fetch %s from Gateway: %s", icao, e)

        return None

    def _fetch_from_gateway(self, icao: str) -> GatewayAirportData | None:
        """Fetch airport data from X-Plane Gateway API.

        Args:
            icao: Airport ICAO code.

        Returns:
            Parsed airport data or None if not available.
        """
        if not XPLANE_AIRPORTS_AVAILABLE or gateway is None:
            return None

        logger.info("Fetching %s from X-Plane Gateway...", icao)

        try:
            pack = gateway.scenery_pack(icao)
            apt: XPlaneAirport = pack.apt
        except Exception as e:
            logger.warning("Airport %s not found in Gateway: %s", icao, e)
            return None

        # Parse basic info
        data = GatewayAirportData(
            icao=icao,
            name=apt.name,
            latitude=apt.latitude,
            longitude=apt.longitude,
            elevation_ft=apt.elevation_ft_amsl or 0.0,
            transition_altitude=18000,  # Default, will be overridden if found
            has_atc=apt.has_atc,
        )

        # Parse taxi network
        if apt.taxi_network:
            self._parse_taxi_network(apt.taxi_network, data)

        # Parse raw lines for additional data
        self._parse_raw_lines(apt.raw_lines, data)

        logger.info(
            "Loaded %s: %d nodes, %d edges, %d parking, %d frequencies",
            icao,
            len(data.taxi_nodes),
            len(data.taxi_edges),
            len(data.parking_positions),
            len(data.frequencies),
        )

        return data

    def _parse_taxi_network(self, network: "TaxiRouteNetwork", data: GatewayAirportData) -> None:
        """Parse taxi network from xplane_airports structure.

        Args:
            network: TaxiRouteNetwork from xplane_airports.
            data: GatewayAirportData to populate.
        """
        # Parse nodes
        for node_id, node in network.nodes.items():
            taxi_node = TaxiNode(
                id=node_id,
                latitude=node.lat,
                longitude=node.lon,
            )
            data.taxi_nodes[node_id] = taxi_node

        # Parse edges
        for edge in network.edges:
            taxi_edge = TaxiEdge(
                node_begin=edge.node_begin,
                node_end=edge.node_end,
                name=edge.name or "",
                is_runway=edge.is_runway,
                one_way=edge.one_way,
                width_code=edge.icao_width.value if edge.icao_width else "E",
            )
            data.taxi_edges.append(taxi_edge)

    def _parse_raw_lines(self, raw_lines: list[str], data: GatewayAirportData) -> None:
        """Parse additional data from raw apt.dat lines.

        Args:
            raw_lines: Raw apt.dat lines.
            data: GatewayAirportData to populate.
        """
        for line in raw_lines:
            parts = line.strip().split()
            if not parts:
                continue

            row_code = parts[0]

            # Frequencies (1050-1056)
            if row_code in FREQ_TYPE_MAP:
                self._parse_frequency_line(parts, row_code, data)

            # Runway (100)
            elif row_code == "100":
                self._parse_runway_line(parts, data)

            # Parking position (1300)
            elif row_code == "1300":
                self._parse_parking_line(parts, line, data)

            # Metadata - transition altitude (1302)
            elif row_code == "1302" and len(parts) >= 3:
                if parts[1] == "transition_alt":
                    with contextlib.suppress(ValueError):
                        data.transition_altitude = int(parts[2])

            # Hold short line (1204)
            elif row_code == "1204" and len(parts) >= 3:
                try:
                    node_id = int(parts[1])
                    runway_id = parts[2] if len(parts) > 2 else ""
                    if node_id in data.taxi_nodes:
                        data.taxi_nodes[node_id].is_hold_short = True
                        data.taxi_nodes[node_id].on_runway = runway_id
                except (ValueError, IndexError):
                    pass

    def _parse_frequency_line(
        self, parts: list[str], row_code: str, data: GatewayAirportData
    ) -> None:
        """Parse a frequency line from apt.dat.

        Args:
            parts: Split line parts.
            row_code: Row code (1050-1056).
            data: GatewayAirportData to populate.
        """
        if len(parts) < 3:
            return

        try:
            # Frequency is in kHz, convert to MHz
            freq_khz = int(parts[1])
            freq_mhz = freq_khz / 1000.0

            # Name is remaining parts
            name = " ".join(parts[2:])

            freq = GatewayFrequency(
                type=FREQ_TYPE_MAP[row_code],
                frequency_mhz=freq_mhz,
                name=name,
            )
            data.frequencies.append(freq)
        except (ValueError, IndexError):
            pass

    def _parse_runway_line(self, parts: list[str], data: GatewayAirportData) -> None:
        """Parse a runway line from apt.dat.

        Row code 100 format:
        100 width surface ... id1 lat1 lon1 ... id2 lat2 lon2 ...

        Args:
            parts: Split line parts.
            data: GatewayAirportData to populate.
        """
        if len(parts) < 22:
            return

        try:
            runway = GatewayRunway(
                width_m=float(parts[1]),
                surface=int(parts[2]),
                id1=parts[8],
                lat1=float(parts[9]),
                lon1=float(parts[10]),
                id2=parts[17],
                lat2=float(parts[18]),
                lon2=float(parts[19]),
            )

            # Calculate headings from coordinates
            import math

            dlat = runway.lat2 - runway.lat1
            dlon = runway.lon2 - runway.lon1
            heading = math.degrees(math.atan2(dlon, dlat))
            if heading < 0:
                heading += 360

            runway.heading1 = heading
            runway.heading2 = (heading + 180) % 360

            data.runways.append(runway)
        except (ValueError, IndexError):
            pass

    def _parse_parking_line(self, parts: list[str], line: str, data: GatewayAirportData) -> None:
        """Parse a parking position line from apt.dat.

        Row code 1300 format:
        1300 lat lon heading type aircraft_types name

        Args:
            parts: Split line parts.
            line: Original line for reference.
            data: GatewayAirportData to populate.
        """
        if len(parts) < 6:
            return

        try:
            parking = ParkingPosition(
                latitude=float(parts[1]),
                longitude=float(parts[2]),
                heading=float(parts[3]),
                type=parts[4],
                aircraft_types=parts[5].split("|") if len(parts) > 5 else [],
                id=parts[6] if len(parts) > 6 else f"P{len(data.parking_positions)}",
            )
            data.parking_positions.append(parking)
        except (ValueError, IndexError):
            pass

    def _save_to_cache(self, cache_file: Path, data: GatewayAirportData) -> None:
        """Save airport data to cache file.

        Args:
            cache_file: Path to cache file.
            data: Airport data to save.
        """
        cache_dict = {
            "icao": data.icao,
            "name": data.name,
            "latitude": data.latitude,
            "longitude": data.longitude,
            "elevation_ft": data.elevation_ft,
            "transition_altitude": data.transition_altitude,
            "has_atc": data.has_atc,
            "taxi_nodes": [
                {
                    "id": n.id,
                    "latitude": n.latitude,
                    "longitude": n.longitude,
                    "name": n.name,
                    "is_hold_short": n.is_hold_short,
                    "on_runway": n.on_runway,
                }
                for n in data.taxi_nodes.values()
            ],
            "taxi_edges": [
                {
                    "node_begin": e.node_begin,
                    "node_end": e.node_end,
                    "name": e.name,
                    "is_runway": e.is_runway,
                    "one_way": e.one_way,
                    "width_code": e.width_code,
                }
                for e in data.taxi_edges
            ],
            "parking_positions": [
                {
                    "id": p.id,
                    "latitude": p.latitude,
                    "longitude": p.longitude,
                    "heading": p.heading,
                    "type": p.type,
                    "aircraft_types": p.aircraft_types,
                }
                for p in data.parking_positions
            ],
            "frequencies": [
                {
                    "type": f.type,
                    "frequency_mhz": f.frequency_mhz,
                    "name": f.name,
                }
                for f in data.frequencies
            ],
            "runways": [
                {
                    "id1": r.id1,
                    "id2": r.id2,
                    "width_m": r.width_m,
                    "lat1": r.lat1,
                    "lon1": r.lon1,
                    "lat2": r.lat2,
                    "lon2": r.lon2,
                    "heading1": r.heading1,
                    "heading2": r.heading2,
                    "surface": r.surface,
                }
                for r in data.runways
            ],
        }

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_dict, f, indent=2)

    def _load_from_cache(self, cache_file: Path) -> GatewayAirportData | None:
        """Load airport data from cache file.

        Args:
            cache_file: Path to cache file.

        Returns:
            Loaded airport data or None if invalid.
        """
        with open(cache_file, encoding="utf-8") as f:
            cache_dict: dict[str, Any] = json.load(f)

        data = GatewayAirportData(
            icao=cache_dict["icao"],
            name=cache_dict["name"],
            latitude=cache_dict["latitude"],
            longitude=cache_dict["longitude"],
            elevation_ft=cache_dict.get("elevation_ft", 0.0),
            transition_altitude=cache_dict.get("transition_altitude", 18000),
            has_atc=cache_dict.get("has_atc", False),
        )

        # Load taxi nodes
        for node_dict in cache_dict.get("taxi_nodes", []):
            node = TaxiNode(
                id=node_dict["id"],
                latitude=node_dict["latitude"],
                longitude=node_dict["longitude"],
                name=node_dict.get("name", ""),
                is_hold_short=node_dict.get("is_hold_short", False),
                on_runway=node_dict.get("on_runway", ""),
            )
            data.taxi_nodes[node.id] = node

        # Load taxi edges
        for edge_dict in cache_dict.get("taxi_edges", []):
            edge = TaxiEdge(
                node_begin=edge_dict["node_begin"],
                node_end=edge_dict["node_end"],
                name=edge_dict.get("name", ""),
                is_runway=edge_dict.get("is_runway", False),
                one_way=edge_dict.get("one_way", False),
                width_code=edge_dict.get("width_code", "E"),
            )
            data.taxi_edges.append(edge)

        # Load parking positions
        for parking_dict in cache_dict.get("parking_positions", []):
            parking = ParkingPosition(
                id=parking_dict["id"],
                latitude=parking_dict["latitude"],
                longitude=parking_dict["longitude"],
                heading=parking_dict["heading"],
                type=parking_dict.get("type", "tie_down"),
                aircraft_types=parking_dict.get("aircraft_types", []),
            )
            data.parking_positions.append(parking)

        # Load frequencies
        for freq_dict in cache_dict.get("frequencies", []):
            freq = GatewayFrequency(
                type=freq_dict["type"],
                frequency_mhz=freq_dict["frequency_mhz"],
                name=freq_dict.get("name", ""),
            )
            data.frequencies.append(freq)

        # Load runways
        for runway_dict in cache_dict.get("runways", []):
            runway = GatewayRunway(
                id1=runway_dict["id1"],
                id2=runway_dict["id2"],
                width_m=runway_dict["width_m"],
                lat1=runway_dict["lat1"],
                lon1=runway_dict["lon1"],
                lat2=runway_dict["lat2"],
                lon2=runway_dict["lon2"],
                heading1=runway_dict.get("heading1", 0.0),
                heading2=runway_dict.get("heading2", 0.0),
                surface=runway_dict.get("surface", 1),
            )
            data.runways.append(runway)

        return data

    def clear_cache(self, icao: str | None = None) -> None:
        """Clear cached airport data.

        Args:
            icao: Specific airport to clear, or None to clear all.

        Examples:
            >>> loader.clear_cache("KPAO")  # Clear one airport
            >>> loader.clear_cache()  # Clear all
        """
        if icao:
            icao = icao.upper()
            self._memory_cache.pop(icao, None)
            cache_file = self.cache_dir / f"{icao}.json"
            if cache_file.exists():
                cache_file.unlink()
        else:
            self._memory_cache.clear()
            for cache_file in self.cache_dir.glob("*.json"):
                cache_file.unlink()

    def prefetch_airports(self, icao_list: list[str]) -> int:
        """Prefetch multiple airports in batch.

        Args:
            icao_list: List of ICAO codes to fetch.

        Returns:
            Number of successfully fetched airports.

        Examples:
            >>> count = loader.prefetch_airports(["KPAO", "KSFO", "LFLY"])
            >>> print(f"Prefetched {count} airports")
        """
        success_count = 0
        for icao in icao_list:
            if self.get_airport(icao):
                success_count += 1
        return success_count

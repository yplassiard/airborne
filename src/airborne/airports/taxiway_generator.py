"""Procedural taxiway generator for airports.

Generates realistic taxiway networks based on airport size and runway layout.
Uses simplified procedural generation inspired by real-world airports.

Typical usage:
    from airborne.airports import TaxiwayGenerator, AirportCategory

    generator = TaxiwayGenerator()
    graph = generator.generate(airport, runways, AirportCategory.LARGE)
"""

import logging
import math
from typing import Optional

from airborne.airports.classifier import AirportCategory
from airborne.airports.database import Airport, Runway
from airborne.airports.taxiway import TaxiwayGraph
from airborne.physics.vectors import Vector3

logger = logging.getLogger(__name__)


class TaxiwayGenerator:
    """Procedural taxiway network generator.

    Generates taxiway graphs based on airport category and runway layout.
    Uses simplified algorithms inspired by real-world airport designs.

    Examples:
        >>> generator = TaxiwayGenerator()
        >>> graph = generator.generate(airport, runways, AirportCategory.LARGE)
        >>> print(f"Generated {graph.get_node_count()} taxiway nodes")
    """

    def __init__(self) -> None:
        """Initialize taxiway generator."""
        self.node_counter = 0

    def generate(
        self,
        airport: Airport,
        runways: list[Runway],
        category: AirportCategory,
    ) -> TaxiwayGraph:
        """Generate taxiway network for an airport.

        Args:
            airport: Airport to generate taxiways for
            runways: List of runways at the airport
            category: Airport size category

        Returns:
            TaxiwayGraph with generated nodes and edges

        Examples:
            >>> graph = generator.generate(ksfo, ksfo_runways, AirportCategory.XL)
        """
        self.node_counter = 0
        graph = TaxiwayGraph()

        if not runways:
            logger.warning("No runways provided for %s, generating empty graph", airport.icao)
            return graph

        logger.info(
            "Generating taxiways for %s (%s, %d runways)",
            airport.icao,
            category.value,
            len(runways),
        )

        # Generate based on airport size
        if category == AirportCategory.SMALL:
            self._generate_small_airport(graph, airport, runways)
        elif category == AirportCategory.MEDIUM:
            self._generate_medium_airport(graph, airport, runways)
        elif category == AirportCategory.LARGE:
            self._generate_large_airport(graph, airport, runways)
        elif category == AirportCategory.XL:
            self._generate_xl_airport(graph, airport, runways)

        logger.info(
            "Generated %d nodes and %d edges for %s",
            graph.get_node_count(),
            graph.get_edge_count(),
            airport.icao,
        )

        return graph

    def _generate_small_airport(
        self,
        graph: TaxiwayGraph,
        airport: Airport,
        runways: list[Runway],
    ) -> None:
        """Generate simple taxiway network for small airport.

        Small airports have minimal taxiways - typically just runway access
        and a parking apron with direct connections.

        Args:
            graph: Graph to populate
            airport: Airport information
            runways: List of runways
        """
        # For small airports, create simple access to runway ends
        runway = runways[0]  # Use first/primary runway

        # Create nodes at runway ends
        rwy_le = self._add_node(
            graph,
            airport,
            f"RWY{runway.le_ident}",
            Vector3(runway.le_longitude, runway.le_elevation_ft * 0.3048, runway.le_latitude),
            "runway",
            f"Runway {runway.le_ident}",
        )

        rwy_he = self._add_node(
            graph,
            airport,
            f"RWY{runway.he_ident}",
            Vector3(runway.he_longitude, runway.he_elevation_ft * 0.3048, runway.he_latitude),
            "runway",
            f"Runway {runway.he_ident}",
        )

        # Create apron node near midpoint
        mid_lon = (runway.le_longitude + runway.he_longitude) / 2
        mid_lat = (runway.le_latitude + runway.he_latitude) / 2
        mid_elev = (runway.le_elevation_ft + runway.he_elevation_ft) / 2 * 0.3048

        # Offset apron slightly from runway
        apron_offset = 0.001  # ~100m
        apron = self._add_node(
            graph,
            airport,
            "APRON",
            Vector3(mid_lon + apron_offset, mid_elev, mid_lat + apron_offset),
            "parking",
            "Apron",
        )

        # Connect apron to both runway ends
        graph.add_edge(rwy_le, apron, "taxiway", "A", bidirectional=True)
        graph.add_edge(apron, rwy_he, "taxiway", "A", bidirectional=True)

    def _generate_medium_airport(
        self,
        graph: TaxiwayGraph,
        airport: Airport,
        runways: list[Runway],
    ) -> None:
        """Generate taxiway network for medium airport.

        Medium airports have parallel taxiways along runways with multiple
        access points and a dedicated apron area.

        Args:
            graph: Graph to populate
            airport: Airport information
            runways: List of runways
        """
        runway = runways[0]  # Use first/primary runway

        # Create nodes at runway ends
        rwy_le = self._add_node(
            graph,
            airport,
            f"RWY{runway.le_ident}",
            Vector3(runway.le_longitude, runway.le_elevation_ft * 0.3048, runway.le_latitude),
            "runway",
            f"Runway {runway.le_ident}",
        )

        rwy_he = self._add_node(
            graph,
            airport,
            f"RWY{runway.he_ident}",
            Vector3(runway.he_longitude, runway.he_elevation_ft * 0.3048, runway.he_latitude),
            "runway",
            f"Runway {runway.he_ident}",
        )

        # Create parallel taxiway with 3 segments
        # Calculate perpendicular offset for parallel taxiway
        heading_rad = math.radians(runway.le_heading_deg)
        perp_offset = 0.002  # ~200m perpendicular offset

        # Create 3 taxiway nodes along runway
        taxiway_nodes = []
        for i, ratio in enumerate([0.25, 0.5, 0.75]):
            lon = runway.le_longitude + (runway.he_longitude - runway.le_longitude) * ratio
            lat = runway.le_latitude + (runway.he_latitude - runway.le_latitude) * ratio
            elev = (
                runway.le_elevation_ft + (runway.he_elevation_ft - runway.le_elevation_ft) * ratio
            ) * 0.3048

            # Offset perpendicular to runway
            lon += perp_offset * math.cos(heading_rad + math.pi / 2)
            lat += perp_offset * math.sin(heading_rad + math.pi / 2)

            node_id = self._add_node(
                graph,
                airport,
                f"A{i+1}",
                Vector3(lon, elev, lat),
                "intersection",
                f"Alpha {i+1}",
            )
            taxiway_nodes.append(node_id)

        # Connect parallel taxiway segments
        for i in range(len(taxiway_nodes) - 1):
            graph.add_edge(taxiway_nodes[i], taxiway_nodes[i + 1], "taxiway", "A", bidirectional=True)

        # Connect taxiway to runway ends
        graph.add_edge(rwy_le, taxiway_nodes[0], "taxiway", "L1", bidirectional=True)
        graph.add_edge(taxiway_nodes[-1], rwy_he, "taxiway", "L2", bidirectional=True)

        # Add apron connected to middle taxiway node
        apron_offset = 0.002
        mid_node = taxiway_nodes[1]
        mid_pos = graph.get_node(mid_node).position

        apron = self._add_node(
            graph,
            airport,
            "APRON",
            Vector3(
                mid_pos.x + apron_offset * math.cos(heading_rad + math.pi / 2),
                mid_pos.y,
                mid_pos.z + apron_offset * math.sin(heading_rad + math.pi / 2),
            ),
            "parking",
            "Apron",
        )

        graph.add_edge(mid_node, apron, "taxiway", "L3", bidirectional=True)

    def _generate_large_airport(
        self,
        graph: TaxiwayGraph,
        airport: Airport,
        runways: list[Runway],
    ) -> None:
        """Generate taxiway network for large airport.

        Large airports have multiple parallel taxiways, high-speed exits,
        and dedicated terminal areas. Inspired by airports like KSJC.

        Args:
            graph: Graph to populate
            airport: Airport information
            runways: List of runways
        """
        # Sort runways by length (use longest as primary)
        sorted_runways = sorted(runways, key=lambda r: r.length_ft, reverse=True)
        primary_runway = sorted_runways[0]

        # Create runway end nodes
        rwy_le = self._add_node(
            graph,
            airport,
            f"RWY{primary_runway.le_ident}",
            Vector3(
                primary_runway.le_longitude,
                primary_runway.le_elevation_ft * 0.3048,
                primary_runway.le_latitude,
            ),
            "runway",
            f"Runway {primary_runway.le_ident}",
        )

        rwy_he = self._add_node(
            graph,
            airport,
            f"RWY{primary_runway.he_ident}",
            Vector3(
                primary_runway.he_longitude,
                primary_runway.he_elevation_ft * 0.3048,
                primary_runway.he_latitude,
            ),
            "runway",
            f"Runway {primary_runway.he_ident}",
        )

        heading_rad = math.radians(primary_runway.le_heading_deg)

        # Create TWO parallel taxiways (inner and outer)
        inner_offset = 0.0015  # ~150m
        outer_offset = 0.0030  # ~300m

        # Generate 5 segments along runway for better connectivity
        segments = 5
        inner_nodes = []
        outer_nodes = []

        for i in range(segments):
            ratio = (i + 1) / (segments + 1)
            lon = primary_runway.le_longitude + (
                primary_runway.he_longitude - primary_runway.le_longitude
            ) * ratio
            lat = primary_runway.le_latitude + (
                primary_runway.he_latitude - primary_runway.le_latitude
            ) * ratio
            elev = (
                primary_runway.le_elevation_ft
                + (primary_runway.he_elevation_ft - primary_runway.le_elevation_ft) * ratio
            ) * 0.3048

            # Inner taxiway (closer to runway) - "W1" series
            inner_lon = lon + inner_offset * math.cos(heading_rad + math.pi / 2)
            inner_lat = lat + inner_offset * math.sin(heading_rad + math.pi / 2)
            inner_node = self._add_node(
                graph,
                airport,
                f"W1{chr(65+i)}",  # W1A, W1B, etc.
                Vector3(inner_lon, elev, inner_lat),
                "intersection",
                f"Whiskey 1 {chr(65+i)}",
            )
            inner_nodes.append(inner_node)

            # Outer taxiway (farther from runway) - "W2" series
            outer_lon = lon + outer_offset * math.cos(heading_rad + math.pi / 2)
            outer_lat = lat + outer_offset * math.sin(heading_rad + math.pi / 2)
            outer_node = self._add_node(
                graph,
                airport,
                f"W2{chr(65+i)}",  # W2A, W2B, etc.
                Vector3(outer_lon, elev, outer_lat),
                "intersection",
                f"Whiskey 2 {chr(65+i)}",
            )
            outer_nodes.append(outer_node)

        # Connect inner taxiway segments (W1)
        for i in range(len(inner_nodes) - 1):
            graph.add_edge(inner_nodes[i], inner_nodes[i + 1], "taxiway", "W1", bidirectional=True)

        # Connect outer taxiway segments (W2)
        for i in range(len(outer_nodes) - 1):
            graph.add_edge(outer_nodes[i], outer_nodes[i + 1], "taxiway", "W2", bidirectional=True)

        # Connect inner to runway ends
        graph.add_edge(rwy_le, inner_nodes[0], "taxiway", "L1", bidirectional=True)
        graph.add_edge(inner_nodes[-1], rwy_he, "taxiway", "L2", bidirectional=True)

        # Connect inner to outer taxiways with link taxiways (L series)
        for i in range(len(inner_nodes)):
            graph.add_edge(
                inner_nodes[i], outer_nodes[i], "taxiway", f"L{i+3}", bidirectional=True
            )

        # Add terminal area connected to middle outer taxiway
        mid_outer = outer_nodes[len(outer_nodes) // 2]
        mid_pos = graph.get_node(mid_outer).position

        terminal_offset = 0.002
        terminal = self._add_node(
            graph,
            airport,
            "TERM",
            Vector3(
                mid_pos.x + terminal_offset * math.cos(heading_rad + math.pi / 2),
                mid_pos.y,
                mid_pos.z + terminal_offset * math.sin(heading_rad + math.pi / 2),
            ),
            "gate",
            "Terminal",
        )

        graph.add_edge(mid_outer, terminal, "taxiway", "W3", bidirectional=True)

    def _generate_xl_airport(
        self,
        graph: TaxiwayGraph,
        airport: Airport,
        runways: list[Runway],
    ) -> None:
        """Generate complex taxiway network for extra-large airport.

        XL airports have multiple parallel taxiways, high-speed exits,
        multiple terminal areas, and complex routing. Inspired by major
        hubs like LFPO (Paris Orly), KLAX, KSFO.

        Key features:
        - W1, W2: Main parallel taxiways (like Orly)
        - W3: Pushback/terminal access taxiway
        - L-series: Short link taxiways
        - Multiple terminal areas

        Args:
            graph: Graph to populate
            airport: Airport information
            runways: List of runways
        """
        # Sort runways by length
        sorted_runways = sorted(runways, key=lambda r: r.length_ft, reverse=True)
        primary_runway = sorted_runways[0]

        # Create runway end nodes
        rwy_le = self._add_node(
            graph,
            airport,
            f"RWY{primary_runway.le_ident}",
            Vector3(
                primary_runway.le_longitude,
                primary_runway.le_elevation_ft * 0.3048,
                primary_runway.le_latitude,
            ),
            "runway",
            f"Runway {primary_runway.le_ident}",
        )

        rwy_he = self._add_node(
            graph,
            airport,
            f"RWY{primary_runway.he_ident}",
            Vector3(
                primary_runway.he_longitude,
                primary_runway.he_elevation_ft * 0.3048,
                primary_runway.he_latitude,
            ),
            "runway",
            f"Runway {primary_runway.he_ident}",
        )

        heading_rad = math.radians(primary_runway.le_heading_deg)

        # THREE parallel taxiway systems (inspired by LFPO):
        # W1: Inner taxiway (closest to runway)
        # W2: Middle taxiway (main circulation)
        # W3: Outer taxiway (terminal access/pushback)
        w1_offset = 0.0015  # ~150m
        w2_offset = 0.0030  # ~300m
        w3_offset = 0.0045  # ~450m

        # Generate 7 segments for XL airports (more nodes = more routing options)
        segments = 7
        w1_nodes = []
        w2_nodes = []
        w3_nodes = []

        for i in range(segments):
            ratio = (i + 1) / (segments + 1)
            lon = primary_runway.le_longitude + (
                primary_runway.he_longitude - primary_runway.le_longitude
            ) * ratio
            lat = primary_runway.le_latitude + (
                primary_runway.he_latitude - primary_runway.le_latitude
            ) * ratio
            elev = (
                primary_runway.le_elevation_ft
                + (primary_runway.he_elevation_ft - primary_runway.le_elevation_ft) * ratio
            ) * 0.3048

            # W1: Inner taxiway (high-speed exits)
            w1_lon = lon + w1_offset * math.cos(heading_rad + math.pi / 2)
            w1_lat = lat + w1_offset * math.sin(heading_rad + math.pi / 2)
            w1_node = self._add_node(
                graph,
                airport,
                f"W1{chr(65+i)}",
                Vector3(w1_lon, elev, w1_lat),
                "intersection",
                f"Whiskey 1 {chr(65+i)}",
            )
            w1_nodes.append(w1_node)

            # W2: Middle taxiway (main circulation)
            w2_lon = lon + w2_offset * math.cos(heading_rad + math.pi / 2)
            w2_lat = lat + w2_offset * math.sin(heading_rad + math.pi / 2)
            w2_node = self._add_node(
                graph,
                airport,
                f"W2{chr(65+i)}",
                Vector3(w2_lon, elev, w2_lat),
                "intersection",
                f"Whiskey 2 {chr(65+i)}",
            )
            w2_nodes.append(w2_node)

            # W3: Outer taxiway (terminal/pushback)
            w3_lon = lon + w3_offset * math.cos(heading_rad + math.pi / 2)
            w3_lat = lat + w3_offset * math.sin(heading_rad + math.pi / 2)
            w3_node = self._add_node(
                graph,
                airport,
                f"W3{chr(65+i)}",
                Vector3(w3_lon, elev, w3_lat),
                "intersection",
                f"Whiskey 3 {chr(65+i)}",
            )
            w3_nodes.append(w3_node)

        # Connect W1 taxiway segments
        for i in range(len(w1_nodes) - 1):
            graph.add_edge(w1_nodes[i], w1_nodes[i + 1], "taxiway", "W1", bidirectional=True)

        # Connect W2 taxiway segments
        for i in range(len(w2_nodes) - 1):
            graph.add_edge(w2_nodes[i], w2_nodes[i + 1], "taxiway", "W2", bidirectional=True)

        # Connect W3 taxiway segments
        for i in range(len(w3_nodes) - 1):
            graph.add_edge(w3_nodes[i], w3_nodes[i + 1], "taxiway", "W3", bidirectional=True)

        # Connect W1 to runway ends
        graph.add_edge(rwy_le, w1_nodes[0], "taxiway", "LE", bidirectional=True)
        graph.add_edge(w1_nodes[-1], rwy_he, "taxiway", "HE", bidirectional=True)

        # Link taxiways (L series) connecting W1->W2->W3
        link_counter = 1
        for i in range(len(w1_nodes)):
            # W1 to W2
            graph.add_edge(
                w1_nodes[i], w2_nodes[i], "taxiway", f"L{link_counter}", bidirectional=True
            )
            link_counter += 1

            # W2 to W3
            graph.add_edge(
                w2_nodes[i], w3_nodes[i], "taxiway", f"L{link_counter}", bidirectional=True
            )
            link_counter += 1

        # Add multiple terminal areas along W3
        terminal_positions = [1, 3, 5]  # Three terminal areas
        for idx, pos in enumerate(terminal_positions):
            w3_node = w3_nodes[pos]
            w3_pos = graph.get_node(w3_node).position

            terminal_offset = 0.0015
            terminal = self._add_node(
                graph,
                airport,
                f"T{idx+1}",
                Vector3(
                    w3_pos.x + terminal_offset * math.cos(heading_rad + math.pi / 2),
                    w3_pos.y,
                    w3_pos.z + terminal_offset * math.sin(heading_rad + math.pi / 2),
                ),
                "gate",
                f"Terminal {idx+1}",
            )

            # Connect terminal to W3 with gate taxiway
            graph.add_edge(w3_node, terminal, "taxiway", f"G{idx+1}", bidirectional=True)

            # Add parking stands at each terminal
            for stand_idx in range(3):
                stand_offset = 0.0008 * (stand_idx - 1)  # Spread stands along terminal
                terminal_pos = graph.get_node(terminal).position

                stand = self._add_node(
                    graph,
                    airport,
                    f"T{idx+1}S{stand_idx+1}",
                    Vector3(
                        terminal_pos.x + stand_offset,
                        terminal_pos.y,
                        terminal_pos.z,
                    ),
                    "parking",
                    f"Terminal {idx+1} Stand {stand_idx+1}",
                )

                graph.add_edge(terminal, stand, "taxiway", "", bidirectional=True)

        # If multiple runways, connect them with cross-taxiways
        if len(sorted_runways) > 1:
            secondary_runway = sorted_runways[1]

            # Add secondary runway end nodes
            rwy2_le = self._add_node(
                graph,
                airport,
                f"RWY{secondary_runway.le_ident}",
                Vector3(
                    secondary_runway.le_longitude,
                    secondary_runway.le_elevation_ft * 0.3048,
                    secondary_runway.le_latitude,
                ),
                "runway",
                f"Runway {secondary_runway.le_ident}",
            )

            rwy2_he = self._add_node(
                graph,
                airport,
                f"RWY{secondary_runway.he_ident}",
                Vector3(
                    secondary_runway.he_longitude,
                    secondary_runway.he_elevation_ft * 0.3048,
                    secondary_runway.he_latitude,
                ),
                "runway",
                f"Runway {secondary_runway.he_ident}",
            )

            # Connect secondary runway to W2 taxiway system
            # Find nearest W2 node to each runway end
            rwy2_le_pos = graph.get_node(rwy2_le).position
            nearest_to_le = min(
                w2_nodes,
                key=lambda n: self._distance(graph.get_node(n).position, rwy2_le_pos),
            )
            graph.add_edge(rwy2_le, nearest_to_le, "taxiway", "X1", bidirectional=True)

            rwy2_he_pos = graph.get_node(rwy2_he).position
            nearest_to_he = min(
                w2_nodes,
                key=lambda n: self._distance(graph.get_node(n).position, rwy2_he_pos),
            )
            graph.add_edge(rwy2_he, nearest_to_he, "taxiway", "X2", bidirectional=True)

    def _add_node(
        self,
        graph: TaxiwayGraph,
        airport: Airport,
        node_id: str,
        position: Vector3,
        node_type: str,
        name: str,
    ) -> str:
        """Add a node to the graph with airport prefix.

        Args:
            graph: Graph to add node to
            airport: Airport information
            node_id: Node identifier (will be prefixed with ICAO)
            position: Node position
            node_type: Type of node
            name: Human-readable name

        Returns:
            Full node ID with airport prefix
        """
        full_id = f"{airport.icao}_{node_id}"
        graph.add_node(full_id, position, node_type, name)
        self.node_counter += 1
        return full_id

    @staticmethod
    def _distance(pos1: Vector3, pos2: Vector3) -> float:
        """Calculate simple Euclidean distance between positions.

        Args:
            pos1: First position
            pos2: Second position

        Returns:
            Distance in degrees (approximate)
        """
        dx = pos2.x - pos1.x
        dy = pos2.y - pos1.y
        dz = pos2.z - pos1.z
        return math.sqrt(dx * dx + dy * dy + dz * dz)

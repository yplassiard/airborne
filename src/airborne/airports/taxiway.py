"""Taxiway navigation system.

Provides graph-based taxiway navigation for ground operations.
Supports taxiway nodes, edges, and pathfinding between locations.

Typical usage:
    from airborne.airports import TaxiwayGraph, TaxiwayNode

    graph = TaxiwayGraph()
    node1 = graph.add_node("A1", position)
    node2 = graph.add_node("A2", position)
    graph.add_edge("A1", "A2", bidirectional=True)

    path = graph.find_path("A1", "A2")
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

from airborne.physics.vectors import Vector3

logger = logging.getLogger(__name__)


@dataclass
class TaxiwayNode:
    """A node in the taxiway graph.

    Represents a point on the airport surface where taxiways intersect
    or change direction. Can be a taxiway intersection, runway entrance,
    gate, or any significant ground navigation point.

    Attributes:
        node_id: Unique identifier (e.g., "A1", "B", "RWY31")
        position: Position in world coordinates (x=lon, y=elev, z=lat)
        node_type: Type of node (intersection, runway, gate, parking)
        name: Human-readable name (optional)

    Examples:
        >>> node = TaxiwayNode("A1", Vector3(-122.0, 2.1, 37.5), "intersection")
        >>> print(node.node_id)
        A1
    """

    node_id: str
    position: Vector3
    node_type: str = "intersection"
    name: str = ""


@dataclass
class TaxiwayEdge:
    """A directed edge in the taxiway graph.

    Represents a taxiway segment connecting two nodes. Can be one-way
    or bidirectional (depending on whether reverse edge exists).

    Attributes:
        from_node: Source node ID
        to_node: Destination node ID
        distance_m: Length of segment in meters
        edge_type: Type of edge (taxiway, runway, apron)
        name: Human-readable name (e.g., "A", "B1", "31")

    Examples:
        >>> edge = TaxiwayEdge("A1", "A2", 150.0, "taxiway", "A")
        >>> print(f"{edge.name}: {edge.distance_m}m")
        A: 150.0m
    """

    from_node: str
    to_node: str
    distance_m: float
    edge_type: str = "taxiway"
    name: str = ""


class TaxiwayGraph:
    """Graph-based taxiway navigation system.

    Provides a directed graph structure for airport ground navigation.
    Supports adding nodes/edges, pathfinding, and distance calculations.

    Examples:
        >>> graph = TaxiwayGraph()
        >>> graph.add_node("A1", Vector3(-122.0, 2.1, 37.5))
        >>> graph.add_node("A2", Vector3(-122.001, 2.1, 37.5))
        >>> graph.add_edge("A1", "A2", bidirectional=True)
        >>> path = graph.find_path("A1", "A2")
        >>> print(path)  # ["A1", "A2"]
    """

    def __init__(self) -> None:
        """Initialize empty taxiway graph."""
        self.nodes: dict[str, TaxiwayNode] = {}
        self.edges: dict[str, list[TaxiwayEdge]] = {}  # from_node -> list of edges

    def add_node(
        self,
        node_id: str,
        position: Vector3,
        node_type: str = "intersection",
        name: str = "",
    ) -> TaxiwayNode:
        """Add a node to the graph.

        Args:
            node_id: Unique identifier for the node
            position: Position in world coordinates
            node_type: Type of node (intersection, runway, gate, parking)
            name: Human-readable name (optional)

        Returns:
            The created TaxiwayNode

        Raises:
            ValueError: If node_id already exists

        Examples:
            >>> node = graph.add_node("A1", Vector3(-122.0, 2.1, 37.5))
            >>> print(node.node_id)
            A1
        """
        if node_id in self.nodes:
            raise ValueError(f"Node {node_id} already exists")

        node = TaxiwayNode(node_id, position, node_type, name)
        self.nodes[node_id] = node
        self.edges[node_id] = []

        logger.debug("Added node %s at (%.6f, %.6f)", node_id, position.x, position.z)
        return node

    def add_edge(
        self,
        from_node: str,
        to_node: str,
        edge_type: str = "taxiway",
        name: str = "",
        bidirectional: bool = False,
    ) -> TaxiwayEdge:
        """Add an edge between two nodes.

        Args:
            from_node: Source node ID
            to_node: Destination node ID
            edge_type: Type of edge (taxiway, runway, apron)
            name: Human-readable name (optional)
            bidirectional: If True, also add reverse edge

        Returns:
            The created TaxiwayEdge

        Raises:
            ValueError: If either node does not exist

        Examples:
            >>> edge = graph.add_edge("A1", "A2", bidirectional=True)
            >>> print(f"{edge.distance_m:.1f}m")
            150.0m
        """
        if from_node not in self.nodes:
            raise ValueError(f"Node {from_node} does not exist")
        if to_node not in self.nodes:
            raise ValueError(f"Node {to_node} does not exist")

        # Calculate distance
        from_pos = self.nodes[from_node].position
        to_pos = self.nodes[to_node].position
        distance_m = self._calculate_distance_m(from_pos, to_pos)

        # Create edge
        edge = TaxiwayEdge(from_node, to_node, distance_m, edge_type, name)
        self.edges[from_node].append(edge)

        logger.debug(
            "Added edge %s -> %s (%.1fm, %s)",
            from_node,
            to_node,
            distance_m,
            edge_type,
        )

        # Add reverse edge if bidirectional
        if bidirectional:
            reverse_edge = TaxiwayEdge(to_node, from_node, distance_m, edge_type, name)
            self.edges[to_node].append(reverse_edge)
            logger.debug("Added reverse edge %s -> %s", to_node, from_node)

        return edge

    def get_node(self, node_id: str) -> Optional[TaxiwayNode]:
        """Get a node by ID.

        Args:
            node_id: Node identifier

        Returns:
            TaxiwayNode if found, None otherwise

        Examples:
            >>> node = graph.get_node("A1")
            >>> if node:
            ...     print(node.position)
        """
        return self.nodes.get(node_id)

    def get_edges_from(self, node_id: str) -> list[TaxiwayEdge]:
        """Get all edges originating from a node.

        Args:
            node_id: Source node ID

        Returns:
            List of edges (empty if node not found)

        Examples:
            >>> edges = graph.get_edges_from("A1")
            >>> for edge in edges:
            ...     print(f"-> {edge.to_node}")
        """
        return self.edges.get(node_id, [])

    def get_neighbors(self, node_id: str) -> list[str]:
        """Get IDs of all nodes directly connected from this node.

        Args:
            node_id: Node to get neighbors of

        Returns:
            List of neighbor node IDs

        Examples:
            >>> neighbors = graph.get_neighbors("A1")
            >>> print(neighbors)  # ["A2", "B1"]
        """
        edges = self.get_edges_from(node_id)
        return [edge.to_node for edge in edges]

    def find_path(self, start_id: str, goal_id: str) -> Optional[list[str]]:
        """Find shortest path between two nodes using Dijkstra's algorithm.

        Args:
            start_id: Starting node ID
            goal_id: Goal node ID

        Returns:
            List of node IDs forming the path (including start and goal),
            or None if no path exists

        Examples:
            >>> path = graph.find_path("A1", "B3")
            >>> if path:
            ...     print(" -> ".join(path))
            A1 -> A2 -> B1 -> B3
        """
        if start_id not in self.nodes or goal_id not in self.nodes:
            logger.warning("Cannot find path: start or goal node does not exist")
            return None

        if start_id == goal_id:
            return [start_id]

        # Dijkstra's algorithm
        distances: dict[str, float] = {start_id: 0.0}
        previous: dict[str, Optional[str]] = {start_id: None}
        unvisited: set[str] = set(self.nodes.keys())

        while unvisited:
            # Find unvisited node with smallest distance
            current: Optional[str] = None
            current_distance = float("inf")
            for node_id in unvisited:
                if node_id in distances and distances[node_id] < current_distance:
                    current = node_id
                    current_distance = distances[node_id]

            if current is None:
                # No more reachable nodes
                break

            # Found goal?
            if current == goal_id:
                # Reconstruct path
                path: list[str] = []
                node: Optional[str] = goal_id
                while node is not None:
                    path.append(node)
                    node = previous.get(node)
                path.reverse()

                logger.info(
                    "Found path from %s to %s: %s (%.1fm)",
                    start_id,
                    goal_id,
                    " -> ".join(path),
                    distances[goal_id],
                )
                return path

            unvisited.remove(current)

            # Update neighbors
            for edge in self.get_edges_from(current):
                neighbor = edge.to_node
                if neighbor not in unvisited:
                    continue

                new_distance = distances[current] + edge.distance_m
                if neighbor not in distances or new_distance < distances[neighbor]:
                    distances[neighbor] = new_distance
                    previous[neighbor] = current

        logger.warning("No path found from %s to %s", start_id, goal_id)
        return None

    def find_nearest_node(self, position: Vector3, max_distance_m: float = 100.0) -> Optional[str]:
        """Find the nearest node to a given position.

        Args:
            position: Position to search from
            max_distance_m: Maximum search distance in meters

        Returns:
            Node ID of nearest node, or None if no nodes within distance

        Examples:
            >>> nearest = graph.find_nearest_node(Vector3(-122.0, 2.1, 37.5))
            >>> if nearest:
            ...     print(f"Nearest node: {nearest}")
        """
        nearest_id: Optional[str] = None
        nearest_distance = max_distance_m

        for node_id, node in self.nodes.items():
            distance = self._calculate_distance_m(position, node.position)
            if distance < nearest_distance:
                nearest_distance = distance
                nearest_id = node_id

        if nearest_id:
            logger.debug(
                "Found nearest node %s at %.1fm from (%.6f, %.6f)",
                nearest_id,
                nearest_distance,
                position.x,
                position.z,
            )

        return nearest_id

    def get_node_count(self) -> int:
        """Get total number of nodes in graph.

        Returns:
            Number of nodes

        Examples:
            >>> count = graph.get_node_count()
            >>> print(f"Graph has {count} nodes")
        """
        return len(self.nodes)

    def get_edge_count(self) -> int:
        """Get total number of edges in graph.

        Returns:
            Number of edges

        Examples:
            >>> count = graph.get_edge_count()
            >>> print(f"Graph has {count} edges")
        """
        return sum(len(edges) for edges in self.edges.values())

    def clear(self) -> None:
        """Remove all nodes and edges from the graph.

        Examples:
            >>> graph.clear()
            >>> print(graph.get_node_count())  # 0
        """
        self.nodes.clear()
        self.edges.clear()
        logger.info("Cleared taxiway graph")

    @staticmethod
    def _calculate_distance_m(pos1: Vector3, pos2: Vector3) -> float:
        """Calculate straight-line distance between two positions.

        Uses Euclidean distance for simplicity (assumes local coordinates).
        For large distances, use haversine distance instead.

        Args:
            pos1: First position
            pos2: Second position

        Returns:
            Distance in meters
        """
        # For taxiways, use simple Euclidean distance
        # Convert lat/lon degrees to approximate meters at mid-latitude
        # 1 degree latitude ≈ 111,000 meters
        # 1 degree longitude ≈ 111,000 * cos(latitude) meters

        mid_lat = (pos1.z + pos2.z) / 2.0
        lat_scale = 111000.0  # meters per degree latitude
        lon_scale = 111000.0 * math.cos(math.radians(mid_lat))

        dx = (pos2.x - pos1.x) * lon_scale
        dy = pos2.y - pos1.y  # Elevation difference
        dz = (pos2.z - pos1.z) * lat_scale

        return math.sqrt(dx * dx + dy * dy + dz * dz)

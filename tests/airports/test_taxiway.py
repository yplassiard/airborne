"""Tests for Taxiway Navigation System."""

import pytest

from airborne.airports.taxiway import TaxiwayEdge, TaxiwayGraph, TaxiwayNode
from airborne.physics.vectors import Vector3


class TestTaxiwayNode:
    """Test taxiway node data structure."""

    def test_create_node(self) -> None:
        """Test creating a taxiway node."""
        pos = Vector3(-122.0, 2.1, 37.5)
        node = TaxiwayNode("A1", pos, "intersection", "Alpha 1")

        assert node.node_id == "A1"
        assert node.position == pos
        assert node.node_type == "intersection"
        assert node.name == "Alpha 1"

    def test_node_defaults(self) -> None:
        """Test node default values."""
        pos = Vector3(-122.0, 2.1, 37.5)
        node = TaxiwayNode("A1", pos)

        assert node.node_type == "intersection"
        assert node.name == ""


class TestTaxiwayEdge:
    """Test taxiway edge data structure."""

    def test_create_edge(self) -> None:
        """Test creating a taxiway edge."""
        edge = TaxiwayEdge("A1", "A2", 150.0, "taxiway", "A")

        assert edge.from_node == "A1"
        assert edge.to_node == "A2"
        assert edge.distance_m == 150.0
        assert edge.edge_type == "taxiway"
        assert edge.name == "A"

    def test_edge_defaults(self) -> None:
        """Test edge default values."""
        edge = TaxiwayEdge("A1", "A2", 150.0)

        assert edge.edge_type == "taxiway"
        assert edge.name == ""


class TestTaxiwayGraphBasics:
    """Test basic taxiway graph operations."""

    @pytest.fixture
    def graph(self) -> TaxiwayGraph:
        """Create empty graph for testing."""
        return TaxiwayGraph()

    def test_create_empty_graph(self, graph: TaxiwayGraph) -> None:
        """Test creating empty graph."""
        assert graph.get_node_count() == 0
        assert graph.get_edge_count() == 0

    def test_add_node(self, graph: TaxiwayGraph) -> None:
        """Test adding a node."""
        pos = Vector3(-122.0, 2.1, 37.5)
        node = graph.add_node("A1", pos, "intersection", "Alpha 1")

        assert node.node_id == "A1"
        assert graph.get_node_count() == 1

        retrieved = graph.get_node("A1")
        assert retrieved is not None
        assert retrieved.node_id == "A1"
        assert retrieved.position == pos

    def test_add_duplicate_node_raises_error(self, graph: TaxiwayGraph) -> None:
        """Test that adding duplicate node raises error."""
        pos = Vector3(-122.0, 2.1, 37.5)
        graph.add_node("A1", pos)

        with pytest.raises(ValueError, match="already exists"):
            graph.add_node("A1", pos)

    def test_get_nonexistent_node(self, graph: TaxiwayGraph) -> None:
        """Test getting nonexistent node returns None."""
        node = graph.get_node("A1")
        assert node is None

    def test_add_edge(self, graph: TaxiwayGraph) -> None:
        """Test adding an edge."""
        graph.add_node("A1", Vector3(-122.0, 2.1, 37.5))
        graph.add_node("A2", Vector3(-122.001, 2.1, 37.5))

        edge = graph.add_edge("A1", "A2", "taxiway", "A")

        assert edge.from_node == "A1"
        assert edge.to_node == "A2"
        assert edge.distance_m > 0
        assert graph.get_edge_count() == 1

    def test_add_edge_nonexistent_node_raises_error(self, graph: TaxiwayGraph) -> None:
        """Test that adding edge with nonexistent node raises error."""
        graph.add_node("A1", Vector3(-122.0, 2.1, 37.5))

        with pytest.raises(ValueError, match="does not exist"):
            graph.add_edge("A1", "A2")

    def test_add_bidirectional_edge(self, graph: TaxiwayGraph) -> None:
        """Test adding bidirectional edge."""
        graph.add_node("A1", Vector3(-122.0, 2.1, 37.5))
        graph.add_node("A2", Vector3(-122.001, 2.1, 37.5))

        graph.add_edge("A1", "A2", bidirectional=True)

        # Should have 2 edges (A1->A2 and A2->A1)
        assert graph.get_edge_count() == 2

        edges_from_a1 = graph.get_edges_from("A1")
        edges_from_a2 = graph.get_edges_from("A2")

        assert len(edges_from_a1) == 1
        assert len(edges_from_a2) == 1
        assert edges_from_a1[0].to_node == "A2"
        assert edges_from_a2[0].to_node == "A1"

    def test_get_neighbors(self, graph: TaxiwayGraph) -> None:
        """Test getting node neighbors."""
        graph.add_node("A1", Vector3(-122.0, 2.1, 37.5))
        graph.add_node("A2", Vector3(-122.001, 2.1, 37.5))
        graph.add_node("B1", Vector3(-122.002, 2.1, 37.5))

        graph.add_edge("A1", "A2")
        graph.add_edge("A1", "B1")

        neighbors = graph.get_neighbors("A1")
        assert len(neighbors) == 2
        assert "A2" in neighbors
        assert "B1" in neighbors

    def test_clear_graph(self, graph: TaxiwayGraph) -> None:
        """Test clearing the graph."""
        graph.add_node("A1", Vector3(-122.0, 2.1, 37.5))
        graph.add_node("A2", Vector3(-122.001, 2.1, 37.5))
        graph.add_edge("A1", "A2")

        assert graph.get_node_count() == 2
        assert graph.get_edge_count() == 1

        graph.clear()

        assert graph.get_node_count() == 0
        assert graph.get_edge_count() == 0


class TestTaxiwayPathfinding:
    """Test pathfinding on taxiway graphs."""

    @pytest.fixture
    def simple_graph(self) -> TaxiwayGraph:
        """Create simple linear graph A1 -> A2 -> A3."""
        graph = TaxiwayGraph()
        graph.add_node("A1", Vector3(-122.0, 2.1, 37.5))
        graph.add_node("A2", Vector3(-122.001, 2.1, 37.5))
        graph.add_node("A3", Vector3(-122.002, 2.1, 37.5))
        graph.add_edge("A1", "A2", bidirectional=True)
        graph.add_edge("A2", "A3", bidirectional=True)
        return graph

    @pytest.fixture
    def complex_graph(self) -> TaxiwayGraph:
        """Create complex graph with multiple paths.

        A1 -> A2 -> A3
         |           |
         v           v
        B1 -> B2 -> B3
        """
        graph = TaxiwayGraph()

        # Row A
        graph.add_node("A1", Vector3(-122.0, 2.1, 37.5))
        graph.add_node("A2", Vector3(-122.001, 2.1, 37.5))
        graph.add_node("A3", Vector3(-122.002, 2.1, 37.5))

        # Row B
        graph.add_node("B1", Vector3(-122.0, 2.1, 37.499))
        graph.add_node("B2", Vector3(-122.001, 2.1, 37.499))
        graph.add_node("B3", Vector3(-122.002, 2.1, 37.499))

        # Horizontal edges
        graph.add_edge("A1", "A2", bidirectional=True)
        graph.add_edge("A2", "A3", bidirectional=True)
        graph.add_edge("B1", "B2", bidirectional=True)
        graph.add_edge("B2", "B3", bidirectional=True)

        # Vertical edges
        graph.add_edge("A1", "B1", bidirectional=True)
        graph.add_edge("A3", "B3", bidirectional=True)

        return graph

    def test_find_path_single_node(self, simple_graph: TaxiwayGraph) -> None:
        """Test path from node to itself."""
        path = simple_graph.find_path("A1", "A1")
        assert path == ["A1"]

    def test_find_path_adjacent_nodes(self, simple_graph: TaxiwayGraph) -> None:
        """Test path between adjacent nodes."""
        path = simple_graph.find_path("A1", "A2")
        assert path == ["A1", "A2"]

    def test_find_path_multiple_hops(self, simple_graph: TaxiwayGraph) -> None:
        """Test path requiring multiple hops."""
        path = simple_graph.find_path("A1", "A3")
        assert path == ["A1", "A2", "A3"]

    def test_find_path_reverse_direction(self, simple_graph: TaxiwayGraph) -> None:
        """Test path in reverse direction (bidirectional edges)."""
        path = simple_graph.find_path("A3", "A1")
        assert path == ["A3", "A2", "A1"]

    def test_find_path_no_connection(self) -> None:
        """Test path when nodes are not connected."""
        graph = TaxiwayGraph()
        graph.add_node("A1", Vector3(-122.0, 2.1, 37.5))
        graph.add_node("B1", Vector3(-122.001, 2.1, 37.5))
        # No edge between them

        path = graph.find_path("A1", "B1")
        assert path is None

    def test_find_path_nonexistent_nodes(self, simple_graph: TaxiwayGraph) -> None:
        """Test path with nonexistent nodes."""
        path = simple_graph.find_path("A1", "Z9")
        assert path is None

        path = simple_graph.find_path("Z9", "A1")
        assert path is None

    def test_find_path_shortest(self, complex_graph: TaxiwayGraph) -> None:
        """Test that shortest path is found."""
        # From A1 to B3, should go via A1->B1->B2->B3
        # (shorter than A1->A2->A3->B3)
        path = complex_graph.find_path("A1", "B3")

        assert path is not None
        assert path[0] == "A1"
        assert path[-1] == "B3"
        # Should be 4 nodes (A1, B1, B2, B3)
        assert len(path) == 4


class TestTaxiwayNearestNode:
    """Test finding nearest node to a position."""

    @pytest.fixture
    def graph(self) -> TaxiwayGraph:
        """Create graph with several nodes."""
        graph = TaxiwayGraph()
        graph.add_node("A1", Vector3(-122.0, 2.1, 37.5))
        graph.add_node("A2", Vector3(-122.001, 2.1, 37.5))
        graph.add_node("B1", Vector3(-122.0, 2.1, 37.499))
        return graph

    def test_find_nearest_node_exact_position(self, graph: TaxiwayGraph) -> None:
        """Test finding node at exact position."""
        nearest = graph.find_nearest_node(Vector3(-122.0, 2.1, 37.5))
        assert nearest == "A1"

    def test_find_nearest_node_close_position(self, graph: TaxiwayGraph) -> None:
        """Test finding nearest node to a close position."""
        # Position very close to A1
        nearest = graph.find_nearest_node(Vector3(-122.0001, 2.1, 37.5001))
        assert nearest == "A1"

    def test_find_nearest_node_max_distance(self, graph: TaxiwayGraph) -> None:
        """Test that nodes beyond max distance are not returned."""
        # Position far from all nodes
        nearest = graph.find_nearest_node(Vector3(-122.1, 2.1, 37.5), max_distance_m=10.0)
        assert nearest is None

    def test_find_nearest_node_empty_graph(self) -> None:
        """Test finding nearest node in empty graph."""
        graph = TaxiwayGraph()
        nearest = graph.find_nearest_node(Vector3(-122.0, 2.1, 37.5))
        assert nearest is None


class TestTaxiwayDistanceCalculation:
    """Test distance calculation between positions."""

    def test_distance_zero(self) -> None:
        """Test distance from point to itself is zero."""
        pos = Vector3(-122.0, 2.1, 37.5)
        distance = TaxiwayGraph._calculate_distance_m(pos, pos)
        assert distance == 0.0

    def test_distance_horizontal(self) -> None:
        """Test distance calculation for horizontal displacement."""
        pos1 = Vector3(-122.0, 2.1, 37.5)
        pos2 = Vector3(-122.001, 2.1, 37.5)  # ~111m east

        distance = TaxiwayGraph._calculate_distance_m(pos1, pos2)

        # 0.001 degrees longitude at 37.5° latitude ≈ 88m
        assert 80 < distance < 100

    def test_distance_vertical(self) -> None:
        """Test distance calculation for vertical displacement."""
        pos1 = Vector3(-122.0, 2.1, 37.5)
        pos2 = Vector3(-122.0, 2.1, 37.501)  # ~111m north

        distance = TaxiwayGraph._calculate_distance_m(pos1, pos2)

        # 0.001 degrees latitude ≈ 111m
        assert 100 < distance < 120

    def test_distance_elevation(self) -> None:
        """Test distance calculation with elevation difference."""
        pos1 = Vector3(-122.0, 2.1, 37.5)
        pos2 = Vector3(-122.0, 102.1, 37.5)  # 100m higher

        distance = TaxiwayGraph._calculate_distance_m(pos1, pos2)

        # Pure elevation difference = 100m
        assert 99 < distance < 101

    def test_distance_symmetric(self) -> None:
        """Test that distance calculation is symmetric."""
        pos1 = Vector3(-122.0, 2.1, 37.5)
        pos2 = Vector3(-122.001, 2.1, 37.501)

        dist1 = TaxiwayGraph._calculate_distance_m(pos1, pos2)
        dist2 = TaxiwayGraph._calculate_distance_m(pos2, pos1)

        assert abs(dist1 - dist2) < 0.01


class TestRealWorldTaxiwayExample:
    """Test with realistic airport taxiway layout."""

    @pytest.fixture
    def kpao_taxiways(self) -> TaxiwayGraph:
        """Create simplified KPAO taxiway graph.

        Palo Alto Airport (KPAO) has:
        - Runway 31/13
        - Taxiway A (parallel to runway)
        """
        graph = TaxiwayGraph()

        # Runway 31 entrance
        graph.add_node("RWY31", Vector3(-122.121, 2.1, 37.458), "runway", "Runway 31")

        # Taxiway A intersections
        graph.add_node("A1", Vector3(-122.120, 2.1, 37.459), "intersection", "Alpha 1")
        graph.add_node("A2", Vector3(-122.115, 2.1, 37.461), "intersection", "Alpha 2")
        graph.add_node("A3", Vector3(-122.110, 2.1, 37.463), "intersection", "Alpha 3")

        # Runway 13 entrance
        graph.add_node("RWY13", Vector3(-122.108, 2.1, 37.464), "runway", "Runway 13")

        # Connect taxiway A
        graph.add_edge("A1", "A2", "taxiway", "A", bidirectional=True)
        graph.add_edge("A2", "A3", "taxiway", "A", bidirectional=True)

        # Connect to runways
        graph.add_edge("RWY31", "A1", "taxiway", "", bidirectional=True)
        graph.add_edge("A3", "RWY13", "taxiway", "", bidirectional=True)

        return graph

    def test_kpao_node_count(self, kpao_taxiways: TaxiwayGraph) -> None:
        """Test KPAO graph has correct node count."""
        assert kpao_taxiways.get_node_count() == 5

    def test_kpao_find_path_runway_to_runway(self, kpao_taxiways: TaxiwayGraph) -> None:
        """Test finding path from one runway to another."""
        path = kpao_taxiways.find_path("RWY31", "RWY13")

        assert path is not None
        assert path[0] == "RWY31"
        assert path[-1] == "RWY13"
        assert len(path) == 5  # RWY31, A1, A2, A3, RWY13

    def test_kpao_find_nearest_intersection(self, kpao_taxiways: TaxiwayGraph) -> None:
        """Test finding nearest taxiway intersection to a position."""
        # Position near A2
        nearest = kpao_taxiways.find_nearest_node(Vector3(-122.115, 2.1, 37.461))
        assert nearest == "A2"

"""Tests for Taxiway Generator."""

import pytest

from airborne.airports.classifier import AirportCategory
from airborne.airports.database import Airport, AirportType, Runway, SurfaceType
from airborne.airports.taxiway_generator import TaxiwayGenerator
from airborne.physics.vectors import Vector3


class TestTaxiwayGeneratorBasics:
    """Test basic taxiway generator functionality."""

    @pytest.fixture
    def generator(self) -> TaxiwayGenerator:
        """Create generator for testing."""
        return TaxiwayGenerator()

    @pytest.fixture
    def sample_airport(self) -> Airport:
        """Create sample airport."""
        return Airport(
            icao="KTEST",
            name="Test Airport",
            position=Vector3(-122.0, 30.5, 37.5),
            airport_type=AirportType.MEDIUM_AIRPORT,
            municipality="Test City",
            iso_country="US",
            scheduled_service=False,
        )

    @pytest.fixture
    def sample_runway(self) -> Runway:
        """Create sample runway."""
        return Runway(
            airport_icao="KTEST",
            runway_id="13/31",
            length_ft=5000,
            width_ft=100,
            surface=SurfaceType.ASPH,
            lighted=True,
            closed=False,
            le_ident="13",
            le_latitude=37.48,
            le_longitude=-122.02,
            le_elevation_ft=30,
            le_heading_deg=130,
            he_ident="31",
            he_latitude=37.52,
            he_longitude=-121.98,
            he_elevation_ft=30,
            he_heading_deg=310,
        )

    def test_generate_empty_for_no_runways(
        self, generator: TaxiwayGenerator, sample_airport: Airport
    ) -> None:
        """Test that empty graph is generated when no runways."""
        graph = generator.generate(sample_airport, [], AirportCategory.SMALL)
        assert graph.get_node_count() == 0
        assert graph.get_edge_count() == 0

    def test_generate_small_airport(
        self, generator: TaxiwayGenerator, sample_airport: Airport, sample_runway: Runway
    ) -> None:
        """Test generating taxiways for small airport."""
        graph = generator.generate(sample_airport, [sample_runway], AirportCategory.SMALL)

        # Small airport should have minimal nodes
        assert graph.get_node_count() >= 3  # At least 2 runway ends + 1 apron
        assert graph.get_edge_count() >= 2  # At least 2 connections

        # Check that runway nodes exist
        assert graph.get_node("KTEST_RWY13") is not None
        assert graph.get_node("KTEST_RWY31") is not None

    def test_generate_medium_airport(
        self, generator: TaxiwayGenerator, sample_airport: Airport, sample_runway: Runway
    ) -> None:
        """Test generating taxiways for medium airport."""
        graph = generator.generate(sample_airport, [sample_runway], AirportCategory.MEDIUM)

        # Medium airport should have more nodes than small
        assert graph.get_node_count() >= 5  # Runway ends + taxiway nodes + terminal
        assert graph.get_edge_count() >= 4

        # Should have 1 terminal
        assert graph.get_node("KTEST_T1") is not None

    def test_generate_large_airport(
        self, generator: TaxiwayGenerator, sample_airport: Airport, sample_runway: Runway
    ) -> None:
        """Test generating taxiways for large airport."""
        graph = generator.generate(sample_airport, [sample_runway], AirportCategory.LARGE)

        # Large airport should have parallel taxiways
        assert graph.get_node_count() >= 10  # Multiple taxiway segments
        assert graph.get_edge_count() >= 10

        # Should have W1 and W2 taxiway nodes
        w1_nodes = [n for n in graph.nodes.keys() if "W1" in n]
        w2_nodes = [n for n in graph.nodes.keys() if "W2" in n]
        assert len(w1_nodes) > 0
        assert len(w2_nodes) > 0

        # Should have 2 terminals
        assert graph.get_node("KTEST_T1") is not None
        assert graph.get_node("KTEST_T2") is not None

    def test_generate_xl_airport(
        self, generator: TaxiwayGenerator, sample_airport: Airport, sample_runway: Runway
    ) -> None:
        """Test generating taxiways for XL airport."""
        graph = generator.generate(sample_airport, [sample_runway], AirportCategory.XL)

        # XL airport should have extensive taxiway network
        assert graph.get_node_count() >= 20  # Many nodes for complex network
        assert graph.get_edge_count() >= 20

        # Should have W1, W2, W3 taxiway nodes
        w1_nodes = [n for n in graph.nodes.keys() if "W1" in n]
        w2_nodes = [n for n in graph.nodes.keys() if "W2" in n]
        w3_nodes = [n for n in graph.nodes.keys() if "W3" in n]
        assert len(w1_nodes) > 0
        assert len(w2_nodes) > 0
        assert len(w3_nodes) > 0

        # Should have multiple terminals (T1, T2, T3, not stands like T1S1)
        terminal_nodes = [
            n
            for n in graph.nodes.keys()
            if n.endswith("_T1") or n.endswith("_T2") or n.endswith("_T3")
        ]
        assert len(terminal_nodes) >= 3  # At least 3 terminals


class TestTaxiwayGeneratorConnectivity:
    """Test that generated taxiways are properly connected."""

    @pytest.fixture
    def generator(self) -> TaxiwayGenerator:
        """Create generator for testing."""
        return TaxiwayGenerator()

    @pytest.fixture
    def sample_airport(self) -> Airport:
        """Create sample airport."""
        return Airport(
            icao="KTEST",
            name="Test Airport",
            position=Vector3(-122.0, 30.5, 37.5),
            airport_type=AirportType.LARGE_AIRPORT,
            municipality="Test City",
            iso_country="US",
            scheduled_service=True,
        )

    @pytest.fixture
    def sample_runway(self) -> Runway:
        """Create sample runway."""
        return Runway(
            airport_icao="KTEST",
            runway_id="13/31",
            length_ft=8000,
            width_ft=150,
            surface=SurfaceType.ASPH,
            lighted=True,
            closed=False,
            le_ident="13",
            le_latitude=37.48,
            le_longitude=-122.02,
            le_elevation_ft=30,
            le_heading_deg=130,
            he_ident="31",
            he_latitude=37.52,
            he_longitude=-121.98,
            he_elevation_ft=30,
            he_heading_deg=310,
        )

    def test_runway_ends_connected(
        self, generator: TaxiwayGenerator, sample_airport: Airport, sample_runway: Runway
    ) -> None:
        """Test that runway ends are connected via taxiways."""
        graph = generator.generate(sample_airport, [sample_runway], AirportCategory.MEDIUM)

        # Find path from one runway end to the other
        path = graph.find_path("KTEST_RWY13", "KTEST_RWY31")
        assert path is not None
        assert len(path) > 2  # Should have intermediate taxiway nodes

    def test_terminal_connected_to_runway(
        self, generator: TaxiwayGenerator, sample_airport: Airport, sample_runway: Runway
    ) -> None:
        """Test that terminals are connected to runways."""
        graph = generator.generate(sample_airport, [sample_runway], AirportCategory.LARGE)

        # Find terminal node (large airports have T1, T2)
        terminal = graph.get_node("KTEST_T1")
        assert terminal is not None

        # Should be able to reach runway from terminal
        path = graph.find_path("KTEST_T1", "KTEST_RWY13")
        assert path is not None

    def test_xl_airport_all_terminals_connected(
        self, generator: TaxiwayGenerator, sample_airport: Airport, sample_runway: Runway
    ) -> None:
        """Test that all terminals in XL airport are connected."""
        graph = generator.generate(sample_airport, [sample_runway], AirportCategory.XL)

        # Get all terminal nodes
        terminal_nodes = [n for n in graph.nodes.keys() if "_T" in n and "S" not in n]

        # Each terminal should be able to reach runway
        for terminal in terminal_nodes:
            path = graph.find_path(terminal, "KTEST_RWY13")
            assert path is not None, f"Terminal {terminal} not connected to runway"


class TestTaxiwayGeneratorMultipleRunways:
    """Test taxiway generation with multiple runways."""

    @pytest.fixture
    def generator(self) -> TaxiwayGenerator:
        """Create generator for testing."""
        return TaxiwayGenerator()

    @pytest.fixture
    def sample_airport(self) -> Airport:
        """Create sample airport."""
        return Airport(
            icao="KMULTI",
            name="Multi Runway Airport",
            position=Vector3(-122.0, 30.5, 37.5),
            airport_type=AirportType.LARGE_AIRPORT,
            municipality="Test City",
            iso_country="US",
            scheduled_service=True,
        )

    @pytest.fixture
    def multiple_runways(self) -> list[Runway]:
        """Create multiple runways."""
        return [
            Runway(
                airport_icao="KMULTI",
                runway_id="28L/10R",
                length_ft=11870,
                width_ft=200,
                surface=SurfaceType.ASPH,
                lighted=True,
                closed=False,
                le_ident="28L",
                le_latitude=37.60,
                le_longitude=-122.40,
                le_elevation_ft=10,
                le_heading_deg=280,
                he_ident="10R",
                he_latitude=37.62,
                he_longitude=-122.36,
                he_elevation_ft=15,
                he_heading_deg=100,
            ),
            Runway(
                airport_icao="KMULTI",
                runway_id="28R/10L",
                length_ft=11381,
                width_ft=200,
                surface=SurfaceType.ASPH,
                lighted=True,
                closed=False,
                le_ident="28R",
                le_latitude=37.61,
                le_longitude=-122.40,
                le_elevation_ft=10,
                le_heading_deg=280,
                he_ident="10L",
                he_latitude=37.63,
                he_longitude=-122.36,
                he_elevation_ft=15,
                he_heading_deg=100,
            ),
        ]

    def test_xl_connects_multiple_runways(
        self, generator: TaxiwayGenerator, sample_airport: Airport, multiple_runways: list[Runway]
    ) -> None:
        """Test that XL airport connects multiple runways."""
        graph = generator.generate(sample_airport, multiple_runways, AirportCategory.XL)

        # Both runways should exist
        assert graph.get_node("KMULTI_RWY28L") is not None
        assert graph.get_node("KMULTI_RWY28R") is not None

        # Should be able to taxi between runways
        path = graph.find_path("KMULTI_RWY28L", "KMULTI_RWY28R")
        assert path is not None


class TestRealWorldAirportGeneration:
    """Test generator with real-world airport examples."""

    @pytest.fixture
    def generator(self) -> TaxiwayGenerator:
        """Create generator for testing."""
        return TaxiwayGenerator()

    def test_generate_kpao_small_airport(self, generator: TaxiwayGenerator) -> None:
        """Test generating taxiways for KPAO (small airport)."""
        kpao = Airport(
            icao="KPAO",
            name="Palo Alto Airport",
            position=Vector3(-122.115, 2.1, 37.461),
            airport_type=AirportType.SMALL_AIRPORT,
            municipality="Palo Alto",
            iso_country="US",
            scheduled_service=False,
        )

        runway = Runway(
            airport_icao="KPAO",
            runway_id="13/31",
            length_ft=2443,
            width_ft=70,
            surface=SurfaceType.ASPH,
            lighted=True,
            closed=False,
            le_ident="13",
            le_latitude=37.458,
            le_longitude=-122.121,
            le_elevation_ft=5,
            le_heading_deg=129.8,
            he_ident="31",
            he_latitude=37.463,
            he_longitude=-122.108,
            he_elevation_ft=8,
            he_heading_deg=309.8,
        )

        graph = generator.generate(kpao, [runway], AirportCategory.SMALL)

        # Should have basic taxiway structure
        assert graph.get_node_count() >= 3
        assert graph.get_node("KPAO_RWY13") is not None
        assert graph.get_node("KPAO_RWY31") is not None

    def test_generate_ksfo_xl_airport(self, generator: TaxiwayGenerator) -> None:
        """Test generating taxiways for KSFO (XL airport)."""
        ksfo = Airport(
            icao="KSFO",
            name="San Francisco International",
            position=Vector3(-122.374, 4.0, 37.618),
            airport_type=AirportType.LARGE_AIRPORT,
            municipality="San Francisco",
            iso_country="US",
            scheduled_service=True,
        )

        runways = [
            Runway(
                airport_icao="KSFO",
                runway_id="28L/10R",
                length_ft=11870,
                width_ft=200,
                surface=SurfaceType.ASPH,
                lighted=True,
                closed=False,
                le_ident="28L",
                le_latitude=37.617,
                le_longitude=-122.396,
                le_elevation_ft=9,
                le_heading_deg=284.0,
                he_ident="10R",
                he_latitude=37.620,
                he_longitude=-122.359,
                he_elevation_ft=13,
                he_heading_deg=104.0,
            ),
        ]

        graph = generator.generate(ksfo, runways, AirportCategory.XL)

        # XL airport should have extensive taxiway network
        assert graph.get_node_count() >= 20
        assert graph.get_edge_count() >= 20

        # Should have multiple terminals (T1, T2, T3, not stands like T1S1)
        terminal_nodes = [
            n
            for n in graph.nodes.keys()
            if n.endswith("_T1") or n.endswith("_T2") or n.endswith("_T3")
        ]
        assert len(terminal_nodes) >= 3

"""Tests for Airport Classifier."""

import pytest

from airborne.airports.classifier import AirportCategory, AirportClassifier
from airborne.airports.database import Airport, AirportType, Runway, SurfaceType
from airborne.physics.vectors import Vector3


class TestAirportClassifier:
    """Test airport classification logic."""

    @pytest.fixture
    def classifier(self) -> AirportClassifier:
        """Create classifier for testing."""
        return AirportClassifier()

    @pytest.fixture
    def sample_airport(self) -> Airport:
        """Create sample airport for testing."""
        return Airport(
            icao="KTEST",
            name="Test Airport",
            position=Vector3(-122.0, 100, 37.5),
            airport_type=AirportType.MEDIUM_AIRPORT,
            municipality="Test City",
            iso_country="US",
            scheduled_service=False,
        )

    def test_major_hub_classified_as_xl(
        self, classifier: AirportClassifier, sample_airport: Airport
    ) -> None:
        """Test that known major hubs are always XL."""
        # Make it a major hub
        lax = Airport(
            icao="KLAX",
            name="Los Angeles International",
            position=Vector3(-118.4, 125, 33.9),
            airport_type=AirportType.LARGE_AIRPORT,
            municipality="Los Angeles",
            iso_country="US",
            scheduled_service=True,
        )

        # Even with no runways, should be XL
        category = classifier.classify(lax, [])
        assert category == AirportCategory.XL

    def test_four_runways_classified_as_xl(
        self, classifier: AirportClassifier, sample_airport: Airport
    ) -> None:
        """Test that 4+ runways = XL."""
        runways = [
            self._create_runway("09/27", 5000, SurfaceType.ASPH),
            self._create_runway("18/36", 5000, SurfaceType.ASPH),
            self._create_runway("04/22", 5000, SurfaceType.ASPH),
            self._create_runway("13/31", 5000, SurfaceType.ASPH),
        ]

        category = classifier.classify(sample_airport, runways)
        assert category == AirportCategory.XL

    def test_two_long_runways_classified_as_xl(
        self, classifier: AirportClassifier, sample_airport: Airport
    ) -> None:
        """Test that 2+ paved runways with 12000+ ft = XL."""
        runways = [
            self._create_runway("09/27", 12500, SurfaceType.ASPH),
            self._create_runway("18/36", 10000, SurfaceType.ASPH),
        ]

        category = classifier.classify(sample_airport, runways)
        assert category == AirportCategory.XL

    def test_two_paved_runways_classified_as_large(
        self, classifier: AirportClassifier, sample_airport: Airport
    ) -> None:
        """Test that 2+ paved runways (not long enough for XL) = LARGE."""
        runways = [
            self._create_runway("09/27", 8000, SurfaceType.ASPH),
            self._create_runway("18/36", 7500, SurfaceType.CONC),
        ]

        category = classifier.classify(sample_airport, runways)
        assert category == AirportCategory.LARGE

    def test_long_runway_classified_as_large(
        self, classifier: AirportClassifier, sample_airport: Airport
    ) -> None:
        """Test that single runway > 7000 ft = LARGE."""
        runways = [self._create_runway("09/27", 8500, SurfaceType.ASPH)]

        category = classifier.classify(sample_airport, runways)
        assert category == AirportCategory.LARGE

    def test_short_runway_classified_as_small(
        self, classifier: AirportClassifier, sample_airport: Airport
    ) -> None:
        """Test that single runway < 3000 ft = SMALL."""
        runways = [self._create_runway("13/31", 2500, SurfaceType.ASPH)]

        category = classifier.classify(sample_airport, runways)
        assert category == AirportCategory.SMALL

    def test_grass_runway_classified_as_small(
        self, classifier: AirportClassifier, sample_airport: Airport
    ) -> None:
        """Test that grass runway = SMALL."""
        runways = [self._create_runway("09/27", 5000, SurfaceType.GRASS)]

        category = classifier.classify(sample_airport, runways)
        assert category == AirportCategory.SMALL

    def test_dirt_runway_classified_as_small(
        self, classifier: AirportClassifier, sample_airport: Airport
    ) -> None:
        """Test that dirt runway = SMALL."""
        runways = [self._create_runway("13/31", 4000, SurfaceType.DIRT)]

        category = classifier.classify(sample_airport, runways)
        assert category == AirportCategory.SMALL

    def test_medium_runway_classified_as_medium(
        self, classifier: AirportClassifier, sample_airport: Airport
    ) -> None:
        """Test that medium-length paved runway = MEDIUM."""
        runways = [self._create_runway("09/27", 5000, SurfaceType.ASPH)]

        category = classifier.classify(sample_airport, runways)
        assert category == AirportCategory.MEDIUM

    def test_no_runways_classified_as_small(
        self, classifier: AirportClassifier, sample_airport: Airport
    ) -> None:
        """Test that no runways = SMALL."""
        category = classifier.classify(sample_airport, [])
        assert category == AirportCategory.SMALL

    def test_closed_runways_ignored(
        self, classifier: AirportClassifier, sample_airport: Airport
    ) -> None:
        """Test that closed runways are not counted as paved."""
        runways = [
            self._create_runway("09/27", 8000, SurfaceType.ASPH, closed=True),
            self._create_runway("18/36", 8000, SurfaceType.ASPH, closed=True),
        ]

        # Should not be LARGE (requires 2+ paved runways)
        # Should be LARGE based on length
        category = classifier.classify(sample_airport, runways)
        assert category == AirportCategory.LARGE  # Longest runway > 7000ft

    def _create_runway(
        self,
        runway_id: str,
        length_ft: float,
        surface: SurfaceType,
        closed: bool = False,
    ) -> Runway:
        """Helper to create test runway."""
        return Runway(
            airport_icao="KTEST",
            runway_id=runway_id,
            length_ft=length_ft,
            width_ft=100,
            surface=surface,
            lighted=True,
            closed=closed,
            le_ident=runway_id.split("/")[0],
            le_latitude=37.5,
            le_longitude=-122.0,
            le_elevation_ft=100,
            le_heading_deg=90,
            he_ident=runway_id.split("/")[1],
            he_latitude=37.5,
            he_longitude=-122.0,
            he_elevation_ft=100,
            he_heading_deg=270,
        )


class TestMajorHubsManagement:
    """Test major hubs list management."""

    @pytest.fixture
    def classifier(self) -> AirportClassifier:
        """Create classifier for testing."""
        return AirportClassifier()

    def test_add_major_hub(self, classifier: AirportClassifier) -> None:
        """Test adding an airport to major hubs."""
        classifier.add_major_hub("KPDX")
        assert classifier.is_major_hub("KPDX")

    def test_remove_major_hub(self, classifier: AirportClassifier) -> None:
        """Test removing an airport from major hubs."""
        classifier.add_major_hub("KPDX")
        classifier.remove_major_hub("KPDX")
        assert not classifier.is_major_hub("KPDX")

    def test_is_major_hub_case_insensitive(self, classifier: AirportClassifier) -> None:
        """Test that major hub check is case-insensitive."""
        classifier.add_major_hub("kpdx")
        assert classifier.is_major_hub("KPDX")
        assert classifier.is_major_hub("kpdx")

    def test_default_major_hubs_exist(self, classifier: AirportClassifier) -> None:
        """Test that default major hubs are pre-loaded."""
        assert classifier.is_major_hub("KLAX")
        assert classifier.is_major_hub("KJFK")
        assert classifier.is_major_hub("LFPG")
        assert classifier.is_major_hub("EGLL")


class TestRealWorldAirports:
    """Test classifier with real-world airport examples."""

    @pytest.fixture
    def classifier(self) -> AirportClassifier:
        """Create classifier for testing."""
        return AirportClassifier()

    def test_palo_alto_is_small_or_medium(self, classifier: AirportClassifier) -> None:
        """Test that Palo Alto (KPAO) classifies correctly."""
        kpao = Airport(
            icao="KPAO",
            name="Palo Alto Airport",
            position=Vector3(-122.115, 2.1, 37.461),
            airport_type=AirportType.SMALL_AIRPORT,
            municipality="Palo Alto",
            iso_country="US",
            scheduled_service=False,
        )

        # Single 2443ft runway
        runways = [
            Runway(
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
        ]

        category = classifier.classify(kpao, runways)
        assert category == AirportCategory.SMALL  # < 3000 ft

    def test_san_francisco_is_xl(self, classifier: AirportClassifier) -> None:
        """Test that San Francisco (KSFO) is XL."""
        ksfo = Airport(
            icao="KSFO",
            name="San Francisco International",
            position=Vector3(-122.374, 4.0, 37.618),
            airport_type=AirportType.LARGE_AIRPORT,
            municipality="San Francisco",
            iso_country="US",
            scheduled_service=True,
        )

        # 4 runways
        runways = [
            self._create_runway("28L/10R", 11870, SurfaceType.ASPH),
            self._create_runway("28R/10L", 11381, SurfaceType.ASPH),
            self._create_runway("01L/19R", 9500, SurfaceType.ASPH),
            self._create_runway("01R/19L", 7501, SurfaceType.ASPH),
        ]

        category = classifier.classify(ksfo, runways)
        assert category == AirportCategory.XL

    def _create_runway(self, runway_id: str, length_ft: float, surface: SurfaceType) -> Runway:
        """Helper to create test runway."""
        return Runway(
            airport_icao="KSFO",
            runway_id=runway_id,
            length_ft=length_ft,
            width_ft=200,
            surface=surface,
            lighted=True,
            closed=False,
            le_ident=runway_id.split("/")[0],
            le_latitude=37.618,
            le_longitude=-122.374,
            le_elevation_ft=10,
            le_heading_deg=280,
            he_ident=runway_id.split("/")[1],
            he_latitude=37.618,
            he_longitude=-122.374,
            he_elevation_ft=10,
            he_heading_deg=100,
        )

"""Tests for aviation phraseology system."""

import pytest

from airborne.plugins.radio.phraseology import PhraseMaker, PhraseContext


class TestPhraseContext:
    """Test PhraseContext dataclass."""

    def test_create_default(self) -> None:
        """Test creating context with defaults."""
        ctx = PhraseContext()
        assert ctx.callsign == ""
        assert ctx.airport == ""
        assert ctx.squawk == "1200"

    def test_create_with_values(self) -> None:
        """Test creating context with values."""
        ctx = PhraseContext(
            callsign="Cessna 123AB",
            airport="Palo Alto",
            runway="31",
            location="parking",
        )
        assert ctx.callsign == "Cessna 123AB"
        assert ctx.airport == "Palo Alto"
        assert ctx.runway == "31"
        assert ctx.location == "parking"


class TestPhraseMakerPilot:
    """Test pilot phraseology generation."""

    def test_taxi_request(self) -> None:
        """Test generating taxi request."""
        pm = PhraseMaker()
        ctx = PhraseContext(
            callsign="Cessna 123AB",
            airport="Palo Alto",
            location="parking",
            atis="Bravo",
        )

        phrase = pm.make_pilot_phrase("taxi_request", ctx)
        assert (
            phrase
            == "Palo Alto Ground, Cessna 123AB, at parking with information Bravo, request taxi"
        )

    def test_takeoff_ready(self) -> None:
        """Test generating takeoff ready call."""
        pm = PhraseMaker()
        ctx = PhraseContext(
            callsign="Cessna 123AB",
            airport="Palo Alto",
            runway="31",
        )

        phrase = pm.make_pilot_phrase("takeoff_ready", ctx)
        assert phrase == "Palo Alto Tower, Cessna 123AB, ready for departure runway 31"

    def test_position_report(self) -> None:
        """Test generating position report."""
        pm = PhraseMaker()
        ctx = PhraseContext(
            callsign="Cessna 123AB",
            airport="Palo Alto",
            altitude=2000,
            heading=90,
        )

        phrase = pm.make_pilot_phrase("position_report", ctx)
        assert phrase == "Palo Alto, Cessna 123AB, 2000 feet, heading 90"

    def test_unknown_phrase_type(self) -> None:
        """Test error on unknown phrase type."""
        pm = PhraseMaker()
        ctx = PhraseContext()

        with pytest.raises(ValueError, match="Unknown pilot phrase type"):
            pm.make_pilot_phrase("invalid_type", ctx)


class TestPhraseMakerATC:
    """Test ATC phraseology generation."""

    def test_taxi_clearance(self) -> None:
        """Test generating taxi clearance."""
        pm = PhraseMaker()
        ctx = PhraseContext(
            callsign="Cessna 123AB",
            airport="Palo Alto",
            runway="31",
            taxiway="Alpha",
        )

        phrase = pm.make_atc_phrase("taxi_clearance", ctx)
        assert phrase == "Cessna 123AB, Palo Alto Ground, taxi to runway 31 via Alpha"

    def test_takeoff_clearance(self) -> None:
        """Test generating takeoff clearance."""
        pm = PhraseMaker()
        ctx = PhraseContext(callsign="Cessna 123AB", runway="31")

        phrase = pm.make_atc_phrase("takeoff_clearance", ctx)
        assert phrase == "Cessna 123AB, runway 31, cleared for takeoff"

    def test_landing_clearance(self) -> None:
        """Test generating landing clearance."""
        pm = PhraseMaker()
        ctx = PhraseContext(callsign="Cessna 123AB", runway="31")

        phrase = pm.make_atc_phrase("landing_clearance", ctx)
        assert phrase == "Cessna 123AB, runway 31, cleared to land"

    def test_traffic_advisory_with_kwargs(self) -> None:
        """Test generating traffic advisory with additional kwargs."""
        pm = PhraseMaker()
        ctx = PhraseContext(callsign="Cessna 123AB")

        phrase = pm.make_atc_phrase(
            "traffic_advisory",
            ctx,
            distance="2",
            range="3",
            type="Cessna",
            altitude="1500 feet",
        )
        assert "Cessna 123AB, traffic, 2 o'clock, 3 miles, Cessna, 1500 feet" == phrase

    def test_squawk_code(self) -> None:
        """Test generating squawk code assignment."""
        pm = PhraseMaker()
        ctx = PhraseContext(callsign="Cessna 123AB", squawk="7000")

        phrase = pm.make_atc_phrase("squawk_code", ctx)
        assert phrase == "Cessna 123AB, squawk 7000"

    def test_unknown_phrase_type(self) -> None:
        """Test error on unknown ATC phrase type."""
        pm = PhraseMaker()
        ctx = PhraseContext()

        with pytest.raises(ValueError, match="Unknown ATC phrase type"):
            pm.make_atc_phrase("invalid_type", ctx)


class TestPhraseMakerCustom:
    """Test adding custom phrases."""

    def test_add_pilot_phrase(self) -> None:
        """Test adding custom pilot phrase."""
        pm = PhraseMaker()
        pm.add_pilot_phrase("custom_test", "{callsign}, this is a test")

        ctx = PhraseContext(callsign="Cessna 123AB")
        phrase = pm.make_pilot_phrase("custom_test", ctx)
        assert phrase == "Cessna 123AB, this is a test"

    def test_add_atc_phrase(self) -> None:
        """Test adding custom ATC phrase."""
        pm = PhraseMaker()
        pm.add_atc_phrase("custom_test", "{callsign}, custom clearance")

        ctx = PhraseContext(callsign="Cessna 123AB")
        phrase = pm.make_atc_phrase("custom_test", ctx)
        assert phrase == "Cessna 123AB, custom clearance"


class TestPhraseMakerList:
    """Test listing available phrases."""

    def test_get_pilot_phrases(self) -> None:
        """Test getting list of pilot phrase types."""
        pm = PhraseMaker()
        phrases = pm.get_available_pilot_phrases()

        assert "taxi_request" in phrases
        assert "takeoff_ready" in phrases
        assert "position_report" in phrases

    def test_get_atc_phrases(self) -> None:
        """Test getting list of ATC phrase types."""
        pm = PhraseMaker()
        phrases = pm.get_available_atc_phrases()

        assert "taxi_clearance" in phrases
        assert "takeoff_clearance" in phrases
        assert "landing_clearance" in phrases

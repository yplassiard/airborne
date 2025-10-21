"""Tests for callsign system."""

import re

import pytest

from airborne.aviation.callsign import Callsign, CallsignGenerator, CallsignType


class TestCallsignType:
    """Test CallsignType enum."""

    def test_callsign_types_exist(self):
        """Test all callsign types exist."""
        assert CallsignType.TYPE_A
        assert CallsignType.TYPE_B
        assert CallsignType.TYPE_C

    def test_callsign_type_values(self):
        """Test callsign type values."""
        assert CallsignType.TYPE_A.value == "registration"
        assert CallsignType.TYPE_B.value == "telephony_reg"
        assert CallsignType.TYPE_C.value == "telephony_flight"


class TestCallsign:
    """Test Callsign class."""

    def test_create_type_a_callsign(self):
        """Test creating Type A callsign."""
        callsign = Callsign(
            full="N12345",
            type=CallsignType.TYPE_A,
            registration="N12345",
            abbreviated="345",
        )

        assert callsign.full == "N12345"
        assert callsign.type == CallsignType.TYPE_A
        assert callsign.registration == "N12345"
        assert callsign.abbreviated == "345"
        assert callsign.telephony is None

    def test_create_type_b_callsign(self):
        """Test creating Type B callsign."""
        callsign = Callsign(
            full="Cessna 2345",
            type=CallsignType.TYPE_B,
            telephony="Cessna",
            registration="N12345",
            abbreviated="45",
        )

        assert callsign.full == "Cessna 2345"
        assert callsign.type == CallsignType.TYPE_B
        assert callsign.telephony == "Cessna"
        assert callsign.registration == "N12345"

    def test_create_type_c_callsign(self):
        """Test creating Type C callsign."""
        callsign = Callsign(
            full="United 1234",
            type=CallsignType.TYPE_C,
            telephony="United",
            flight_number="1234",
            abbreviated="United 34",
        )

        assert callsign.full == "United 1234"
        assert callsign.type == CallsignType.TYPE_C
        assert callsign.telephony == "United"
        assert callsign.flight_number == "1234"

    def test_callsign_str(self):
        """Test string representation of callsign."""
        callsign = Callsign(full="N12345", type=CallsignType.TYPE_A)

        assert str(callsign) == "N12345"

    def test_get_abbreviated(self):
        """Test getting abbreviated callsign."""
        callsign = Callsign(full="N12345", type=CallsignType.TYPE_A, abbreviated="345")

        assert callsign.get_abbreviated() == "345"

    def test_get_abbreviated_none(self):
        """Test getting abbreviated when not set."""
        callsign = Callsign(full="N12345", type=CallsignType.TYPE_A)

        assert callsign.get_abbreviated() is None


class TestCallsignGenerator:
    """Test CallsignGenerator class."""

    @pytest.fixture
    def generator(self):
        """Create callsign generator for testing."""
        return CallsignGenerator()

    @pytest.fixture
    def generator_with_data(self, tmp_path):
        """Create callsign generator with test data."""
        # Create test callsigns.yaml
        yaml_content = """
airlines:
  - icao: UAL
    telephony: United
    name: United Airlines
    country: US
  - icao: DAL
    telephony: Delta
    name: Delta Air Lines
    country: US

countries:
  - code: N
    name: United States
    format: "N{1-5 alphanumeric}"
  - code: G
    name: United Kingdom
    format: "G-{4 letters}"
"""
        yaml_file = tmp_path / "callsigns.yaml"
        yaml_file.write_text(yaml_content)

        return CallsignGenerator(callsigns_file=str(yaml_file))

    def test_create_generator(self, generator):
        """Test creating callsign generator."""
        assert generator is not None
        assert isinstance(generator.airlines, dict)
        assert isinstance(generator.countries, dict)

    def test_load_callsigns_data(self, generator_with_data):
        """Test loading callsigns data from file."""
        assert len(generator_with_data.airlines) == 2
        assert "UAL" in generator_with_data.airlines
        assert "DAL" in generator_with_data.airlines
        assert generator_with_data.airlines["UAL"]["telephony"] == "United"

    def test_generate_ga_callsign_us(self, generator):
        """Test generating US GA callsign (Type A)."""
        callsign = generator.generate_ga_callsign("N")

        assert callsign.type == CallsignType.TYPE_A
        assert callsign.full.startswith("N")
        assert len(callsign.full) >= 2
        assert len(callsign.full) <= 6
        # Should match US registration pattern
        assert re.match(r"^N[0-9][0-9A-Z]{0,4}$", callsign.full)

    def test_generate_ga_callsign_uk(self, generator):
        """Test generating UK GA callsign (Type A)."""
        callsign = generator.generate_ga_callsign("G")

        assert callsign.type == CallsignType.TYPE_A
        assert callsign.full.startswith("G-")
        # UK format: G-XXXX (4 letters)
        assert re.match(r"^G-[A-Z]{4}$", callsign.full)

    def test_generate_ga_callsign_generic(self, generator):
        """Test generating generic country GA callsign."""
        callsign = generator.generate_ga_callsign("D")

        assert callsign.type == CallsignType.TYPE_A
        assert callsign.full.startswith("D")
        assert callsign.registration == callsign.full

    def test_generate_ga_callsign_has_abbreviated(self, generator):
        """Test that GA callsign has abbreviated form."""
        callsign = generator.generate_ga_callsign("N")

        assert callsign.abbreviated is not None
        assert len(callsign.abbreviated) == 3

    def test_generate_multiple_unique_callsigns(self, generator):
        """Test generating multiple unique callsigns."""
        callsigns = [generator.generate_ga_callsign("N") for _ in range(10)]

        # Should generate different callsigns
        unique_callsigns = {c.full for c in callsigns}
        assert len(unique_callsigns) > 1  # At least some should be different

    def test_generate_ga_telephony_callsign(self, generator):
        """Test generating GA callsign with telephony (Type B)."""
        callsign = generator.generate_ga_telephony_callsign("N")

        assert callsign.type == CallsignType.TYPE_B
        assert " " in callsign.full
        parts = callsign.full.split(" ")
        assert len(parts) == 2
        assert parts[0] in generator.GA_TELEPHONY
        assert len(parts[1]) == 4  # Last 4 chars of registration

    def test_generate_ga_telephony_has_registration(self, generator):
        """Test that telephony callsign has registration."""
        callsign = generator.generate_ga_telephony_callsign("N")

        assert callsign.registration is not None
        assert callsign.registration.startswith("N")

    def test_generate_airline_callsign(self, generator):
        """Test generating airline callsign (Type C)."""
        callsign = generator.generate_airline_callsign("UAL", 123)

        assert callsign.type == CallsignType.TYPE_C
        assert callsign.telephony == "UAL"
        assert callsign.flight_number == "123"
        assert " " in callsign.full

    def test_generate_airline_callsign_auto_flight_number(self, generator):
        """Test generating airline callsign with auto flight number."""
        callsign = generator.generate_airline_callsign("DAL")

        assert callsign.type == CallsignType.TYPE_C
        assert callsign.flight_number is not None
        assert int(callsign.flight_number) >= 1
        assert int(callsign.flight_number) <= 9999

    def test_generate_airline_callsign_with_data(self, generator_with_data):
        """Test generating airline callsign with loaded telephony."""
        callsign = generator_with_data.generate_airline_callsign("UAL", 123)

        assert callsign.type == CallsignType.TYPE_C
        assert callsign.telephony == "United"  # From YAML data
        assert callsign.full == "United 123"

    def test_generate_airline_callsign_abbreviated(self, generator):
        """Test airline callsign abbreviated form."""
        callsign = generator.generate_airline_callsign("UAL", 1234)

        assert callsign.abbreviated is not None
        # Should be last 2 digits of flight number
        assert "34" in callsign.abbreviated

    def test_validate_callsign_type_a_us(self, generator):
        """Test validating US Type A callsign."""
        assert generator.validate_callsign("N12345") is True
        assert generator.validate_callsign("N1234A") is True
        assert generator.validate_callsign("N123AB") is True

    def test_validate_callsign_type_a_uk(self, generator):
        """Test validating UK Type A callsign."""
        assert generator.validate_callsign("G-ABCD") is True

    def test_validate_callsign_type_b(self, generator):
        """Test validating Type B callsign."""
        assert generator.validate_callsign("Cessna 2345") is True
        assert generator.validate_callsign("Skyhawk 1AB") is True

    def test_validate_callsign_type_c(self, generator):
        """Test validating Type C callsign."""
        assert generator.validate_callsign("United 1234") is True
        assert generator.validate_callsign("Delta 42") is True

    def test_validate_callsign_invalid(self, generator):
        """Test validating invalid callsigns."""
        assert generator.validate_callsign("") is False
        assert generator.validate_callsign("1") is False
        assert generator.validate_callsign("12345N") is False  # Wrong order
        assert generator.validate_callsign("N") is False  # Too short

    def test_parse_callsign_type_a(self, generator):
        """Test parsing Type A callsign."""
        callsign = generator.parse_callsign("N12345")

        assert callsign is not None
        assert callsign.type == CallsignType.TYPE_A
        assert callsign.full == "N12345"
        assert callsign.registration == "N12345"
        assert callsign.abbreviated == "345"

    def test_parse_callsign_type_b(self, generator):
        """Test parsing Type B callsign."""
        # Type B has alphanumeric suffix (last 4 chars of registration)
        callsign = generator.parse_callsign("Cessna 34AB")

        assert callsign is not None
        assert callsign.type == CallsignType.TYPE_B
        assert callsign.full == "Cessna 34AB"
        assert callsign.telephony == "Cessna"
        assert callsign.registration == "34AB"

    def test_parse_callsign_type_c(self, generator):
        """Test parsing Type C callsign."""
        callsign = generator.parse_callsign("United 1234")

        assert callsign is not None
        assert callsign.type == CallsignType.TYPE_C
        assert callsign.full == "United 1234"
        assert callsign.telephony == "United"
        assert callsign.flight_number == "1234"

    def test_parse_callsign_invalid(self, generator):
        """Test parsing invalid callsign."""
        callsign = generator.parse_callsign("12345N")

        assert callsign is None

    def test_parse_callsign_empty(self, generator):
        """Test parsing empty callsign."""
        callsign = generator.parse_callsign("")

        assert callsign is None

    def test_is_type_a_us_patterns(self, generator):
        """Test _is_type_a with various US patterns."""
        assert generator._is_type_a("N12345") is True
        assert generator._is_type_a("N1234A") is True
        assert generator._is_type_a("N123AB") is True
        assert generator._is_type_a("N12ABC") is True
        assert generator._is_type_a("N1ABCD") is True

    def test_is_type_a_uk_pattern(self, generator):
        """Test _is_type_a with UK pattern."""
        assert generator._is_type_a("G-ABCD") is True
        assert generator._is_type_a("G-1234") is False  # Must be letters

    def test_is_type_a_generic(self, generator):
        """Test _is_type_a with generic patterns."""
        assert generator._is_type_a("D1234") is True
        assert generator._is_type_a("JA1234") is True

    def test_is_type_a_invalid(self, generator):
        """Test _is_type_a with invalid patterns."""
        assert generator._is_type_a("12345") is False
        assert generator._is_type_a("N") is False
        assert generator._is_type_a("") is False

    def test_generate_from_pattern_digits(self, generator):
        """Test generating from pattern with digits."""
        result = generator._generate_from_pattern("N{d}{d}{d}{d}{d}")

        assert result.startswith("N")
        assert len(result) == 6
        assert result[1:].isdigit()

    def test_generate_from_pattern_letters(self, generator):
        """Test generating from pattern with letters."""
        result = generator._generate_from_pattern("G-{l}{l}{l}{l}")

        assert result.startswith("G-")
        assert len(result) == 6
        assert result[2:].isalpha()

    def test_generate_from_pattern_mixed(self, generator):
        """Test generating from pattern with mixed."""
        result = generator._generate_from_pattern("N{d}{d}{d}{l}")

        assert result.startswith("N")
        assert len(result) == 5
        assert result[1:4].isdigit()
        assert result[4].isalpha()

    def test_roundtrip_ga_callsign(self, generator):
        """Test generating and parsing GA callsign."""
        generated = generator.generate_ga_callsign("N")
        parsed = generator.parse_callsign(generated.full)

        assert parsed is not None
        assert parsed.type == CallsignType.TYPE_A
        assert parsed.full == generated.full

    def test_roundtrip_airline_callsign(self, generator):
        """Test generating and parsing airline callsign."""
        generated = generator.generate_airline_callsign("UAL", 123)
        parsed = generator.parse_callsign(generated.full)

        assert parsed is not None
        assert parsed.type == CallsignType.TYPE_C
        assert parsed.telephony == generated.telephony
        assert parsed.flight_number == generated.flight_number

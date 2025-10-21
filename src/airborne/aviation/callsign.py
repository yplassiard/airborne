"""Aircraft callsign management with ICAO compliance.

This module provides ICAO-compliant callsign generation and validation
following Annex 10 standards for Type A, B, and C callsigns.

Typical usage:
    from airborne.aviation import CallsignGenerator

    generator = CallsignGenerator()
    ga_callsign = generator.generate_ga_callsign()  # Type A: N12345
    airline_callsign = generator.generate_airline_callsign("UAL")  # Type C: UAL123
"""

import logging
import random
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class CallsignType(Enum):
    """ICAO callsign type classification.

    According to ICAO Annex 10, Volume II, Chapter 5.

    Attributes:
        TYPE_A: Registration marking only (e.g., N12345, G-ABCD)
        TYPE_B: Telephony designator + last 4 chars of registration (e.g., Cessna 2345)
        TYPE_C: Telephony designator + flight identification (e.g., United 1234)
    """

    TYPE_A = "registration"
    TYPE_B = "telephony_reg"
    TYPE_C = "telephony_flight"


@dataclass
class Callsign:
    """Aircraft callsign with ICAO formatting.

    Attributes:
        full: Full callsign (e.g., "N12345", "United 1234")
        abbreviated: Abbreviated form used after initial contact (optional)
        type: Callsign type (A, B, or C)
        telephony: Telephony designator (e.g., "United", "Cessna") for Type B/C
        registration: Registration marking for Type A/B
        flight_number: Flight number for Type C

    Examples:
        >>> callsign = Callsign(
        ...     full="N12345",
        ...     type=CallsignType.TYPE_A,
        ...     registration="N12345"
        ... )
    """

    full: str
    type: CallsignType
    telephony: str | None = None
    registration: str | None = None
    flight_number: str | None = None
    abbreviated: str | None = None

    def __str__(self) -> str:
        """Return full callsign string.

        Returns:
            Full callsign
        """
        return self.full

    def get_abbreviated(self) -> str | None:
        """Get abbreviated callsign form.

        Only available after ATC uses abbreviated form first.

        Returns:
            Abbreviated callsign or None if not available
        """
        return self.abbreviated


class CallsignGenerator:
    """Generate and validate ICAO-compliant callsigns.

    Provides methods for generating realistic callsigns for general aviation,
    airlines, and validating callsign formats.

    Examples:
        >>> generator = CallsignGenerator()
        >>> ga_callsign = generator.generate_ga_callsign("N")
        >>> print(ga_callsign.full)  # N12345
    """

    # US registration patterns
    US_PATTERNS = [
        "N{d}{d}{d}{d}{d}",  # N12345
        "N{d}{d}{d}{d}{l}",  # N1234A
        "N{d}{d}{d}{l}{l}",  # N123AB
        "N{d}{d}{l}{l}{l}",  # N12ABC
        "N{d}{l}{l}{l}{l}",  # N1ABCD
    ]

    # UK registration pattern
    UK_PATTERN = "G-{l}{l}{l}{l}"  # G-ABCD

    # Common telephony designators for GA aircraft
    GA_TELEPHONY = [
        "Cessna",
        "Skyhawk",
        "Skylane",
        "Cherokee",
        "Piper",
        "Cirrus",
        "Beech",
        "Bonanza",
    ]

    def __init__(self, callsigns_file: str | None = None) -> None:
        """Initialize callsign generator.

        Args:
            callsigns_file: Path to callsigns.yaml file (optional)
        """
        self.airlines: dict[str, dict] = {}
        self.countries: dict[str, dict] = {}

        # Load callsigns data if file provided
        if callsigns_file:
            self._load_callsigns_data(callsigns_file)

        logger.info("Initialized callsign generator")

    def _load_callsigns_data(self, file_path: str) -> None:
        """Load airline and country callsign data from YAML file.

        Args:
            file_path: Path to callsigns.yaml file
        """
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"Callsigns data file not found: {file_path}")
            return

        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if "airlines" in data:
                for airline in data["airlines"]:
                    self.airlines[airline["icao"]] = airline

            if "countries" in data:
                for country in data["countries"]:
                    self.countries[country["code"]] = country

            logger.info(f"Loaded {len(self.airlines)} airlines and {len(self.countries)} countries")

        except Exception as e:
            logger.error(f"Error loading callsigns data: {e}")

    def generate_ga_callsign(self, country_code: str = "N") -> Callsign:
        """Generate general aviation callsign (Type A).

        Args:
            country_code: Country registration prefix (default: "N" for US)

        Returns:
            Type A callsign with registration marking

        Examples:
            >>> callsign = generator.generate_ga_callsign("N")
            >>> print(callsign.full)  # N12345 or similar
        """
        if country_code == "N":
            # US registration
            pattern = random.choice(self.US_PATTERNS)
            registration = self._generate_from_pattern(pattern)
        elif country_code == "G":
            # UK registration
            registration = self._generate_from_pattern(self.UK_PATTERN)
        else:
            # Generic format: Country + 4-5 alphanumeric
            registration = f"{country_code}{random.randint(1000, 99999)}"

        # Type A callsigns can use abbreviated form (last 3 chars) after initial contact
        abbreviated = registration[-3:] if len(registration) >= 3 else None

        return Callsign(
            full=registration,
            type=CallsignType.TYPE_A,
            registration=registration,
            abbreviated=abbreviated,
        )

    def generate_ga_telephony_callsign(self, country_code: str = "N") -> Callsign:
        """Generate general aviation callsign with telephony (Type B).

        Args:
            country_code: Country registration prefix (default: "N" for US)

        Returns:
            Type B callsign with telephony + last 4 chars of registration

        Examples:
            >>> callsign = generator.generate_ga_telephony_callsign("N")
            >>> print(callsign.full)  # Cessna 2345
        """
        # Generate base registration
        base_callsign = self.generate_ga_callsign(country_code)
        registration = base_callsign.full

        # Get last 4 characters
        last_four = registration[-4:] if len(registration) >= 4 else registration

        # Choose random telephony designator
        telephony = random.choice(self.GA_TELEPHONY)

        full = f"{telephony} {last_four}"

        # Type B callsigns can be abbreviated to just last 2-3 chars
        abbreviated = last_four[-2:] if len(last_four) >= 2 else None

        return Callsign(
            full=full,
            type=CallsignType.TYPE_B,
            telephony=telephony,
            registration=registration,
            abbreviated=abbreviated,
        )

    def generate_airline_callsign(
        self, airline_icao: str, flight_number: int | None = None
    ) -> Callsign:
        """Generate airline callsign (Type C).

        Args:
            airline_icao: 3-letter ICAO airline code (e.g., "UAL", "DAL")
            flight_number: Flight number (auto-generated if not provided)

        Returns:
            Type C callsign with telephony + flight number

        Examples:
            >>> callsign = generator.generate_airline_callsign("UAL", 123)
            >>> print(callsign.full)  # United 123
        """
        # Generate flight number if not provided
        if flight_number is None:
            flight_number = random.randint(1, 9999)

        # Get telephony from loaded data or use ICAO code
        telephony = airline_icao
        if airline_icao in self.airlines:
            telephony = self.airlines[airline_icao].get("telephony", airline_icao)

        full = f"{telephony} {flight_number}"

        # Type C abbreviated form: last 2 digits of flight number
        # Only used if ATC initiates abbreviation
        if flight_number < 100:
            abbreviated = f"{telephony} {flight_number}"
        else:
            abbreviated = f"{telephony} {flight_number % 100:02d}"

        return Callsign(
            full=full,
            type=CallsignType.TYPE_C,
            telephony=telephony,
            flight_number=str(flight_number),
            abbreviated=abbreviated,
        )

    def validate_callsign(self, callsign_str: str) -> bool:
        """Validate callsign format.

        Args:
            callsign_str: Callsign string to validate

        Returns:
            True if callsign format is valid

        Examples:
            >>> generator.validate_callsign("N12345")
            True
            >>> generator.validate_callsign("12345N")
            False
        """
        if not callsign_str or len(callsign_str) < 2:
            return False

        # Type A: Registration only (starts with letter)
        if self._is_type_a(callsign_str):
            return True

        # Type B/C: Contains space (telephony designator)
        if " " in callsign_str:
            parts = callsign_str.split(" ", 1)
            if len(parts) == 2:
                telephony, suffix = parts
                # Telephony should be alphabetic, suffix can be alphanumeric
                if telephony.replace("-", "").isalpha() and suffix.replace(
                    "-", ""
                ).replace(".", "").isalnum():
                    return True

        return False

    def parse_callsign(self, callsign_str: str) -> Callsign | None:
        """Parse callsign string into Callsign object.

        Args:
            callsign_str: Callsign string to parse

        Returns:
            Callsign object or None if invalid

        Examples:
            >>> callsign = generator.parse_callsign("N12345")
            >>> print(callsign.type)  # CallsignType.TYPE_A
        """
        if not self.validate_callsign(callsign_str):
            return None

        # Type A: Registration only
        if self._is_type_a(callsign_str):
            return Callsign(
                full=callsign_str,
                type=CallsignType.TYPE_A,
                registration=callsign_str,
                abbreviated=callsign_str[-3:] if len(callsign_str) >= 3 else None,
            )

        # Type B/C: Has telephony designator
        if " " in callsign_str:
            parts = callsign_str.split(" ", 1)
            telephony, suffix = parts

            # Determine if Type B or Type C based on suffix format
            # Type B: Last 4 chars of registration (alphanumeric)
            # Type C: Flight number (numeric)
            if suffix.isdigit():
                # Type C: Airline callsign
                return Callsign(
                    full=callsign_str,
                    type=CallsignType.TYPE_C,
                    telephony=telephony,
                    flight_number=suffix,
                )
            else:
                # Type B: GA with telephony
                return Callsign(
                    full=callsign_str,
                    type=CallsignType.TYPE_B,
                    telephony=telephony,
                    registration=suffix,
                )

        return None

    def _is_type_a(self, callsign_str: str) -> bool:
        """Check if callsign is Type A format.

        Args:
            callsign_str: Callsign string to check

        Returns:
            True if Type A format (registration only)
        """
        # US registration: N followed by 1-5 alphanumeric
        if re.match(r"^N[0-9][0-9A-Z]{0,4}$", callsign_str):
            return True

        # UK registration: G- followed by 4 letters (must be letters, not digits)
        if re.match(r"^G-[A-Z]{4}$", callsign_str) and callsign_str[2:].isalpha():
            return True

        # Generic: 1-2 letter country code + alphanumeric (but not UK)
        return not callsign_str.startswith("G-") and bool(
            re.match(r"^[A-Z]{1,2}[0-9A-Z-]{2,6}$", callsign_str)
        )

    def _generate_from_pattern(self, pattern: str) -> str:
        """Generate registration from pattern.

        Pattern format:
            {d} - random digit (0-9)
            {l} - random letter (A-Z)

        Args:
            pattern: Pattern string

        Returns:
            Generated registration string
        """
        result = pattern
        while "{d}" in result:
            result = result.replace("{d}", str(random.randint(0, 9)), 1)
        while "{l}" in result:
            result = result.replace("{l}", random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ"), 1)
        return result

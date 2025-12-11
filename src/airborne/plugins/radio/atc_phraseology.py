"""ATC phraseology generator for realistic radio communications.

This module generates realistic ATC phraseology with proper ICAO/FAA format
including callsigns, frequencies, runways, altitudes, and all required elements.

The system supports dynamic message generation with placeholders that are
filled at runtime based on current flight context (airport, callsign, runway, etc).

Typical usage:
    phraseology = ATCPhraseology(
        callsign="N12345",
        aircraft_type="cessna172",
        airport_icao="KPAO"
    )

    # Generate pilot message
    pilot_msg = phraseology.pilot_request_startup()
    # "Palo Alto Ground, Skyhawk November one two three four five,
    #  at north ramp with information Alpha, request startup"

    # Generate ATC response
    atc_msg = phraseology.atc_startup_approved()
    # "Skyhawk one two three four five, Palo Alto Ground, startup approved"
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from airborne.core.i18n import t
from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


def _facility_name(facility: str) -> str:
    """Get translated facility name."""
    key = f"atc.{facility.lower()}"
    translated = t(key)
    # If translation not found, return original
    return translated if translated != key else facility


class ATCFacility(Enum):
    """ATC facility types."""

    GROUND = "ground"
    TOWER = "tower"
    DEPARTURE = "departure"
    APPROACH = "approach"
    CENTER = "center"
    CLEARANCE = "clearance"
    UNICOM = "unicom"
    CTAF = "Traffic"


# Aircraft type to telephony mapping
AIRCRAFT_TELEPHONY = {
    "cessna172": "Skyhawk",
    "cessna182": "Skylane",
    "cessna152": "Cessna",
    "cessna150": "Cessna",
    "cessna206": "Centurion",
    "cessna210": "Centurion",
    "pa28": "Cherokee",
    "pa32": "Saratoga",
    "pa34": "Seneca",
    "pa44": "Seminole",
    "pa46": "Malibu",
    "cirrus_sr20": "Cirrus",
    "cirrus_sr22": "Cirrus",
    "beech_a36": "Bonanza",
    "beech_g36": "Bonanza",
    "beech_58": "Baron",
    "mooney_m20": "Mooney",
    "diamond_da40": "Diamond Star",
    "diamond_da42": "Diamond Twin Star",
}


@dataclass
class FlightContext:
    """Current flight context for phraseology generation.

    Attributes:
        callsign: Aircraft callsign (e.g., "N12345")
        aircraft_type: Aircraft type identifier (e.g., "cessna172")
        airport_icao: Current airport ICAO code (e.g., "KPAO")
        airport_name: Airport name for radio (e.g., "Palo Alto")
        runway: Active runway (e.g., "31")
        parking_location: Current parking location (e.g., "north ramp")
        atis_info: Current ATIS information letter (e.g., "Alpha")
        atis_received: Whether ATIS has been listened to
        ground_freq: Ground frequency (e.g., "121.9")
        tower_freq: Tower frequency (e.g., "118.3")
        departure_freq: Departure frequency (e.g., "125.35")
        altitude: Current altitude in feet
        destination: Destination airport or direction (optional)
        squawk: Assigned squawk code (optional)
        passengers: Number of passengers on board (optional)
    """

    callsign: str
    aircraft_type: str = "cessna172"
    airport_icao: str = "KPAO"
    airport_name: str = "Palo Alto"
    runway: str = "31"
    parking_location: str = "ramp"
    atis_info: str = "Alpha"
    atis_received: bool = False
    ground_freq: str = "121.9"
    tower_freq: str = "118.3"
    departure_freq: str = "125.35"
    altitude: int = 0
    destination: str | None = None
    squawk: str | None = None
    passengers: int = 1  # Default 1 passenger (pilot)


class ATCPhraseology:
    """Generate realistic ATC phraseology.

    Creates properly formatted radio communications for both pilot
    and ATC sides, following ICAO/FAA phraseology standards.

    Examples:
        >>> phraseology = ATCPhraseology(FlightContext(
        ...     callsign="N12345",
        ...     aircraft_type="cessna172",
        ...     airport_name="Palo Alto"
        ... ))
        >>> print(phraseology.pilot_request_startup())
        'Palo Alto Ground, Skyhawk November one two three four five, ...'
    """

    def __init__(self, context: FlightContext):
        """Initialize phraseology generator.

        Args:
            context: Flight context with callsign, airport, etc.
        """
        self.context = context

    def update_context(self, **kwargs: Any) -> None:
        """Update flight context.

        Args:
            **kwargs: Context fields to update.
        """
        for key, value in kwargs.items():
            if hasattr(self.context, key):
                setattr(self.context, key, value)

    # --- Callsign formatting ---

    def _get_telephony(self) -> str:
        """Get aircraft telephony designator.

        Returns:
            Telephony designator (e.g., "Skyhawk", "Cherokee")
        """
        return AIRCRAFT_TELEPHONY.get(self.context.aircraft_type, "Aircraft")

    def _format_callsign_phonetic(self, callsign: str) -> str:
        """Format callsign with phonetic pronunciation.

        Args:
            callsign: Raw callsign (e.g., "N12345")

        Returns:
            Phonetic callsign (e.g., "November one two three four five")
        """
        phonetic_letters = {
            "A": "Alpha",
            "B": "Bravo",
            "C": "Charlie",
            "D": "Delta",
            "E": "Echo",
            "F": "Foxtrot",
            "G": "Golf",
            "H": "Hotel",
            "I": "India",
            "J": "Juliet",
            "K": "Kilo",
            "L": "Lima",
            "M": "Mike",
            "N": "November",
            "O": "Oscar",
            "P": "Papa",
            "Q": "Quebec",
            "R": "Romeo",
            "S": "Sierra",
            "T": "Tango",
            "U": "Uniform",
            "V": "Victor",
            "W": "Whiskey",
            "X": "X-ray",
            "Y": "Yankee",
            "Z": "Zulu",
        }

        phonetic_numbers = {
            "0": "zero",
            "1": "one",
            "2": "two",
            "3": "three",
            "4": "four",
            "5": "five",
            "6": "six",
            "7": "seven",
            "8": "eight",
            "9": "niner",
        }

        parts = []
        for char in callsign.upper():
            if char in phonetic_letters:
                parts.append(phonetic_letters[char])
            elif char in phonetic_numbers:
                parts.append(phonetic_numbers[char])
            elif char == "-":
                # Skip hyphens (UK registrations)
                continue
            else:
                parts.append(char)

        return " ".join(parts)

    def _format_callsign_abbreviated(self, callsign: str) -> str:
        """Format abbreviated callsign (last 3 characters).

        Args:
            callsign: Raw callsign

        Returns:
            Abbreviated callsign
        """
        # Remove hyphens for abbreviation
        clean = callsign.replace("-", "")
        if len(clean) >= 3:
            return self._format_callsign_phonetic(clean[-3:])
        return self._format_callsign_phonetic(clean)

    def _full_pilot_callsign(self) -> str:
        """Get full pilot callsign with telephony.

        Returns:
            Full callsign (e.g., "Skyhawk November one two three four five")
        """
        telephony = self._get_telephony()
        phonetic = self._format_callsign_phonetic(self.context.callsign)
        return f"{telephony} {phonetic}"

    def _abbreviated_callsign(self) -> str:
        """Get abbreviated callsign for subsequent communications.

        Returns:
            Abbreviated callsign (e.g., "Skyhawk four five")
        """
        telephony = self._get_telephony()
        abbreviated = self._format_callsign_abbreviated(self.context.callsign)
        return f"{telephony} {abbreviated}"

    # --- Number/Frequency formatting ---

    def _format_frequency(self, freq: str) -> str:
        """Format frequency for radio readout.

        Args:
            freq: Frequency string (e.g., "121.9")

        Returns:
            Formatted frequency (e.g., "one two one point niner")
        """
        parts = []
        for char in freq:
            if char == ".":
                parts.append("point")
            elif char == "9":
                parts.append("niner")
            elif char.isdigit():
                phonetic = {
                    "0": "zero",
                    "1": "one",
                    "2": "two",
                    "3": "three",
                    "4": "four",
                    "5": "five",
                    "6": "six",
                    "7": "seven",
                    "8": "eight",
                }
                parts.append(phonetic.get(char, char))
        return " ".join(parts)

    def _format_runway(self, runway: str) -> str:
        """Format runway designator.

        Args:
            runway: Runway string (e.g., "31L", "04R")

        Returns:
            Formatted runway (e.g., "three one left", "zero four right")
        """
        parts = []
        for char in runway:
            if char.isdigit():
                phonetic = {
                    "0": "zero",
                    "1": "one",
                    "2": "two",
                    "3": "three",
                    "4": "four",
                    "5": "five",
                    "6": "six",
                    "7": "seven",
                    "8": "eight",
                    "9": "niner",
                }
                parts.append(phonetic.get(char, char))
            elif char.upper() == "L":
                parts.append("left")
            elif char.upper() == "R":
                parts.append("right")
            elif char.upper() == "C":
                parts.append("center")
        return " ".join(parts)

    def _format_altitude(self, altitude: int) -> str:
        """Format altitude for radio readout.

        Args:
            altitude: Altitude in feet

        Returns:
            Formatted altitude (e.g., "three thousand five hundred")
        """
        if altitude >= 18000:
            # Flight level
            fl = altitude // 100
            return f"flight level {self._format_number(fl)}"

        # Regular altitude
        thousands = altitude // 1000
        hundreds = (altitude % 1000) // 100

        parts = []
        if thousands > 0:
            parts.append(self._format_number(thousands))
            parts.append("thousand")
        if hundreds > 0:
            parts.append(self._format_number(hundreds))
            parts.append("hundred")

        return " ".join(parts) if parts else "field elevation"

    def _format_number(self, num: int) -> str:
        """Format number for radio readout.

        Args:
            num: Number to format

        Returns:
            Formatted number
        """
        word_numbers = {
            0: "zero",
            1: "one",
            2: "two",
            3: "three",
            4: "four",
            5: "five",
            6: "six",
            7: "seven",
            8: "eight",
            9: "niner",
            10: "ten",
            11: "eleven",
            12: "twelve",
        }

        if num in word_numbers:
            return word_numbers[num]

        # For larger numbers, read digit by digit
        return " ".join(word_numbers.get(int(d), d) for d in str(num))

    def _format_passengers(self, count: int) -> str:
        """Format passenger count for radio readout.

        Args:
            count: Number of passengers

        Returns:
            Formatted passenger count (localized)
        """
        if count == 1:
            return f"{self._format_number(count)} {t('atc.soul_on_board')}"
        return f"{self._format_number(count)} {t('atc.souls_on_board')}"

    # --- Radio Check ---

    def pilot_radio_check(self) -> str:
        """Generate pilot radio check request.

        Returns:
            Radio check message
        """
        return f"{self.context.airport_name} {_facility_name('ground')}, {self._full_pilot_callsign()}, {t('atc.radio_check')}"

    def atc_radio_check_response(self) -> str:
        """Generate ATC radio check response.

        Returns:
            ATC radio check response
        """
        return (
            f"{self._abbreviated_callsign()}, "
            f"{self.context.airport_name} {_facility_name('ground')}, "
            f"{t('atc.reading_you_five_by_five')}"
        )

    # --- Pilot Messages ---

    def pilot_request_startup(self) -> str:
        """Generate pilot startup request.

        Includes ATIS info if received, passengers count.

        Returns:
            Pilot message: "[Airport] Ground, [Callsign], at [location]
            with information [ATIS], [passengers] on board, request startup"
        """
        parts = [
            f"{self.context.airport_name} {_facility_name('ground')}",
            self._full_pilot_callsign(),
            f"{t('atc.at')} {self.context.parking_location}",
        ]

        # Include ATIS info only if received
        if self.context.atis_received and self.context.atis_info:
            parts.append(f"{t('atc.with_information')} {self.context.atis_info}")

        # Include passenger count
        parts.append(self._format_passengers(self.context.passengers))
        parts.append(t("atc.request_startup"))

        return ", ".join(parts)

    def pilot_request_startup_no_atis(self) -> str:
        """Generate pilot startup request without ATIS.

        Returns:
            Startup request without ATIS info
        """
        return (
            f"{self.context.airport_name} {_facility_name('ground')}, "
            f"{self._full_pilot_callsign()}, "
            f"{t('atc.at')} {self.context.parking_location}, "
            f"{self._format_passengers(self.context.passengers)}, "
            f"{t('atc.request_startup')}"
        )

    def pilot_request_taxi(self) -> str:
        """Generate pilot taxi request.

        Returns:
            Pilot message requesting taxi clearance
        """
        return (
            f"{self.context.airport_name} {_facility_name('ground')}, "
            f"{self._full_pilot_callsign()}, "
            f"{t('atc.at')} {self.context.parking_location} "
            f"{t('atc.with_information')} {self.context.atis_info}, "
            f"{t('atc.request_taxi')}"
        )

    def pilot_ready_for_departure(self, intersection: str | None = None) -> str:
        """Generate pilot ready for departure message.

        Args:
            intersection: Intersection departure request (optional)

        Returns:
            Pilot ready message
        """
        base = (
            f"{self.context.airport_name} {_facility_name('tower')}, "
            f"{self._abbreviated_callsign()}, "
            f"{t('atc.hold_short')} {t('atc.runway')} {self._format_runway(self.context.runway)}, "
            f"{t('atc.ready_for_departure')}"
        )
        if intersection:
            base += f" {t('atc.at')} {intersection}"
        return base

    def pilot_request_takeoff(self) -> str:
        """Generate pilot takeoff clearance request.

        Returns:
            Pilot takeoff request
        """
        return (
            f"{self.context.airport_name} {_facility_name('tower')}, "
            f"{self._abbreviated_callsign()}, "
            f"{t('atc.runway')} {self._format_runway(self.context.runway)}, "
            f"{t('atc.ready_for_departure')}"
        )

    def pilot_departure_checkin(self, altitude: int | None = None) -> str:
        """Generate pilot check-in with departure control.

        Args:
            altitude: Current altitude (optional)

        Returns:
            Pilot departure check-in message
        """
        alt = altitude or self.context.altitude
        return (
            f"{self.context.airport_name} Departure, "
            f"{self._full_pilot_callsign()}, "
            f"departing runway {self._format_runway(self.context.runway)}, "
            f"climbing through {self._format_altitude(alt)}"
        )

    def pilot_readback_taxi(self, taxiway: str) -> str:
        """Generate pilot taxi clearance readback.

        Args:
            taxiway: Assigned taxiway

        Returns:
            Pilot readback message
        """
        return (
            f"Taxi runway {self._format_runway(self.context.runway)} "
            f"via {taxiway}, "
            f"{self._abbreviated_callsign()}"
        )

    def pilot_readback_takeoff(self) -> str:
        """Generate pilot takeoff clearance readback.

        Returns:
            Pilot readback message
        """
        return (
            f"Cleared for takeoff, "
            f"runway {self._format_runway(self.context.runway)}, "
            f"{self._abbreviated_callsign()}"
        )

    def pilot_acknowledge(self) -> str:
        """Generate simple pilot acknowledgment.

        Returns:
            Simple acknowledgment with callsign
        """
        return f"Roger, {self._abbreviated_callsign()}"

    def pilot_wilco(self) -> str:
        """Generate will comply acknowledgment.

        Returns:
            Wilco message with callsign
        """
        return f"{t('atc.wilco')}, {self._abbreviated_callsign()}"

    # --- ATC Messages ---

    def atc_startup_approved(self) -> str:
        """Generate ATC startup approval.

        Returns:
            ATC startup approval message
        """
        return (
            f"{self._abbreviated_callsign()}, "
            f"{self.context.airport_name} {_facility_name('ground')}, "
            f"{t('atc.startup_approved')}"
        )

    def atc_startup_denied_no_atis(self) -> str:
        """Generate ATC startup denial due to missing ATIS.

        Returns:
            ATC startup denied message
        """
        return (
            f"{self._abbreviated_callsign()}, {self.context.airport_name} {_facility_name('ground')}, "
            f"{t('atc.startup_denied')}"
        )

    def pilot_readback_startup(self) -> str:
        """Generate pilot startup approval readback.

        Returns:
            Pilot readback message
        """
        return f"{t('atc.readback_startup')}, {self._abbreviated_callsign()}"

    def atc_taxi_clearance(self, taxiway: str = "Alpha") -> str:
        """Generate ATC taxi clearance.

        Args:
            taxiway: Assigned taxiway

        Returns:
            ATC taxi clearance message
        """
        return (
            f"{self._abbreviated_callsign()}, "
            f"{t('atc.taxi')} {t('atc.runway')} {self._format_runway(self.context.runway)} "
            f"{t('atc.taxi_via')} {taxiway}, "
            f"{t('atc.hold_short')} {t('atc.runway')} {self._format_runway(self.context.runway)}"
        )

    def atc_hold_short(self) -> str:
        """Generate ATC hold short instruction.

        Returns:
            ATC hold short message
        """
        return (
            f"{self._abbreviated_callsign()}, "
            f"{t('atc.hold_short')} {self._format_runway(self.context.runway)}"
        )

    def atc_cleared_takeoff(self, wind: str | None = None) -> str:
        """Generate ATC takeoff clearance.

        Args:
            wind: Current wind information (optional)

        Returns:
            ATC takeoff clearance message
        """
        base = (
            f"{self._abbreviated_callsign()}, "
            f"{self._format_runway(self.context.runway)}, "
            f"{t('atc.cleared_takeoff')}"
        )
        if wind:
            base += f", {t('atc.wind')} {wind}"
        return base

    def atc_lineup_wait(self) -> str:
        """Generate ATC line up and wait instruction.

        Returns:
            ATC lineup and wait message
        """
        return (
            f"{self._abbreviated_callsign()}, "
            f"{self._format_runway(self.context.runway)}, "
            f"{t('atc.lineup_wait')}"
        )

    def atc_contact_tower(self) -> str:
        """Generate ATC contact tower instruction.

        Returns:
            ATC contact tower message
        """
        return (
            f"{self._abbreviated_callsign()}, "
            f"{t('atc.contact_tower')} {self._format_frequency(self.context.tower_freq)}"
        )

    def atc_contact_departure(self) -> str:
        """Generate ATC contact departure instruction.

        Returns:
            ATC contact departure message
        """
        return (
            f"{self._abbreviated_callsign()}, "
            f"{t('atc.contact_departure')} {self._format_frequency(self.context.departure_freq)}"
        )

    def atc_radar_contact(self, altitude: int | None = None) -> str:
        """Generate ATC radar contact call.

        Args:
            altitude: Verified altitude (optional)

        Returns:
            ATC radar contact message
        """
        alt = altitude or self.context.altitude
        return f"{self._abbreviated_callsign()}, radar contact, {self._format_altitude(alt)}"

    def atc_frequency_change_approved(self) -> str:
        """Generate ATC frequency change approval.

        Returns:
            ATC frequency change approval message
        """
        return f"{self._abbreviated_callsign()}, frequency change approved"

    def atc_squawk(self, code: str) -> str:
        """Generate ATC squawk instruction.

        Args:
            code: Squawk code

        Returns:
            ATC squawk message
        """
        formatted_code = " ".join(self._format_number(int(d)) for d in code)
        return f"{self._abbreviated_callsign()}, squawk {formatted_code}"

    def atc_roger(self) -> str:
        """Generate simple ATC roger.

        Returns:
            ATC roger message
        """
        return f"{self._abbreviated_callsign()}, roger"

    def atc_stand_by(self) -> str:
        """Generate ATC stand by instruction.

        Returns:
            ATC stand by message
        """
        return f"{self._abbreviated_callsign()}, stand by"


def create_phraseology_from_context(
    callsign: str,
    aircraft_type: str,
    airport_icao: str,
    airport_name: str,
    runway: str = "31",
    atis_info: str = "Alpha",
    ground_freq: str = "121.9",
    tower_freq: str = "118.3",
    departure_freq: str = "125.35",
    parking_location: str = "ramp",
) -> ATCPhraseology:
    """Create phraseology generator from parameters.

    Args:
        callsign: Aircraft callsign
        aircraft_type: Aircraft type identifier
        airport_icao: Airport ICAO code
        airport_name: Airport name for radio
        runway: Active runway
        atis_info: Current ATIS info letter
        ground_freq: Ground frequency
        tower_freq: Tower frequency
        departure_freq: Departure frequency
        parking_location: Current parking location

    Returns:
        Configured ATCPhraseology instance
    """
    context = FlightContext(
        callsign=callsign,
        aircraft_type=aircraft_type,
        airport_icao=airport_icao,
        airport_name=airport_name,
        runway=runway,
        atis_info=atis_info,
        ground_freq=ground_freq,
        tower_freq=tower_freq,
        departure_freq=departure_freq,
        parking_location=parking_location,
    )
    return ATCPhraseology(context)

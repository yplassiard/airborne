"""ATC communication handler for realistic radio communications.

Manages ATC interactions based on flight phase and current frequency,
generating appropriate responses using proper phraseology.

Now supports any airport in the database by dynamically loading
airport data from the X-Plane Gateway.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

from airborne.core.i18n import t
from airborne.core.logging_system import get_logger
from airborne.services.atc.atis_generator import ATISBroadcast, DynamicATISGenerator
from airborne.services.atc.flight_phase import FlightPhase, FlightPhaseManager
from airborne.services.atc.frequency_resolver import FrequencyResolver
from airborne.services.atc.gateway_loader import GatewayAirportLoader
from airborne.services.atc.phraseology import PhoneticConverter, PhraseBuilder
from airborne.services.atc.runway_selector import AircraftCategory, RunwaySelector
from airborne.services.atc.taxiway_graph import TaxiwayGraph
from airborne.services.weather import WeatherService

if TYPE_CHECKING:
    from airborne.airports.database import AirportDatabase

logger = get_logger(__name__)


class ATCRequestType(Enum):
    """Types of ATC requests that can be made."""

    REQUEST_ATIS = auto()
    REQUEST_STARTUP = auto()
    REQUEST_PUSHBACK = auto()
    REQUEST_TAXI = auto()
    READY_DEPARTURE = auto()
    REQUEST_TAKEOFF = auto()
    CHECKIN_DEPARTURE = auto()
    REQUEST_FLIGHT_FOLLOWING = auto()
    REPORT_POSITION = auto()
    REPORT_ALTITUDE = auto()
    REQUEST_APPROACH = auto()
    REQUEST_LANDING = auto()
    REPORT_FINAL = auto()
    GO_AROUND = auto()
    REPORT_CLEAR = auto()
    REQUEST_PARKING = auto()


@dataclass
class ATCRequest:
    """An ATC request with associated data.

    Attributes:
        request_type: Type of request being made.
        callsign: Aircraft callsign.
        airport_icao: Airport ICAO code.
        runway: Runway identifier (if applicable).
        data: Additional request-specific data.
    """

    request_type: ATCRequestType
    callsign: str
    airport_icao: str
    runway: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ATCResponse:
    """An ATC response to a request.

    Attributes:
        request_type: Original request type.
        approved: Whether the request was approved.
        callsign: Aircraft callsign.
        text: Full text of the ATC response.
        words: List of words for audio concatenation.
        instructions: List of specific instructions.
        next_frequency: Frequency to contact next (if applicable).
    """

    request_type: ATCRequestType
    approved: bool
    callsign: str
    text: str
    words: list[str] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    next_frequency: float | None = None


# Default CTAF frequency for uncontrolled airports
DEFAULT_CTAF = 122.8


class ATCHandler:
    """Handles ATC communications with proper phraseology.

    Manages requests and responses based on flight phase,
    generating realistic radio communications.

    Now supports ANY airport by dynamically loading data from
    the X-Plane Scenery Gateway.
    """

    def __init__(
        self,
        callsign: str,
        airport_icao: str,
        airport_name: str | None = None,
        audio_base_path: str = "data/speech/en",
        gateway_loader: GatewayAirportLoader | None = None,
        airport_database: "AirportDatabase | None" = None,
        language: str = "en",
    ) -> None:
        """Initialize ATC handler.

        Args:
            callsign: Aircraft callsign (e.g., "N123AB").
            airport_icao: Airport ICAO code (any valid ICAO).
            airport_name: Full airport name (auto-loaded if None).
            audio_base_path: Base path for audio files.
            gateway_loader: Gateway loader for X-Plane data.
            airport_database: OurAirports database for fallback.
            language: Language code for phraseology.
        """
        self.callsign = callsign
        self.airport_icao = airport_icao.upper()
        self.language = language

        # Initialize services
        self._gateway_loader = gateway_loader or GatewayAirportLoader()
        self._weather_service = WeatherService()
        # Start background METAR fetch early (non-blocking)
        self._weather_service.prefetch_weather(airport_icao)
        self._frequency_resolver = FrequencyResolver(
            gateway_loader=self._gateway_loader,
            airport_database=airport_database,
        )
        self._runway_selector = RunwaySelector()
        self._phase_manager = FlightPhaseManager()
        self._phrase_builder = PhraseBuilder(audio_base_path)

        # Load airport data
        self._gateway_data = self._gateway_loader.get_airport(airport_icao)
        self._taxiway_graph: TaxiwayGraph | None = None

        # Set airport name
        if airport_name:
            self.airport_name = airport_name
        elif self._gateway_data:
            self.airport_name = self._gateway_data.name
        else:
            self.airport_name = f"{airport_icao} Airport"

        # Build taxiway graph if data available
        if self._gateway_data:
            self._taxiway_graph = TaxiwayGraph.from_gateway_data(self._gateway_data)

        # Load frequencies
        self._frequencies = self._load_frequencies()

        # Initialize ATIS generator
        self._atis_generator = DynamicATISGenerator(
            weather_service=self._weather_service,
            audio_base_path=audio_base_path,
        )

        # Register the airport with ATIS generator
        self._atis_generator.register_airport(
            airport_icao,
            self.airport_name,
            self._get_airport_runways(),
            tower_freq=self._frequencies.get("tower", DEFAULT_CTAF),
            ground_freq=self._frequencies.get("ground", DEFAULT_CTAF),
            atis_freq=self._frequencies.get("atis", DEFAULT_CTAF),
        )

        # Current ATIS information
        self._current_atis: ATISBroadcast | None = None
        self._assigned_runway: str = ""
        self._squawk_code: str = "1200"  # VFR squawk
        self._assigned_taxiway_route: list[str] = []

        logger.info(
            "ATCHandler initialized for %s (%s), towered=%s",
            self.airport_name,
            airport_icao,
            self.is_towered,
        )

    def _load_frequencies(self) -> dict[str, float]:
        """Load frequencies for the current airport.

        Returns:
            Dictionary of frequency type to MHz.
        """
        freqs = self._frequency_resolver.get_all_frequencies(self.airport_icao)

        result = {}
        if freqs.ground:
            result["ground"] = freqs.ground.frequency_mhz
        if freqs.tower:
            result["tower"] = freqs.tower.frequency_mhz
        if freqs.atis:
            result["atis"] = freqs.atis.frequency_mhz
        if freqs.approach:
            result["approach"] = freqs.approach.frequency_mhz
        if freqs.departure:
            result["departure"] = freqs.departure.frequency_mhz
        if freqs.ctaf:
            result["ctaf"] = freqs.ctaf.frequency_mhz

        # Default to CTAF for missing frequencies
        if "tower" not in result:
            result["tower"] = result.get("ctaf", DEFAULT_CTAF)
        if "ground" not in result:
            result["ground"] = result.get("ctaf", DEFAULT_CTAF)

        return result

    @property
    def is_towered(self) -> bool:
        """Check if airport is towered."""
        return self._frequency_resolver.is_towered(self.airport_icao)

    @property
    def current_phase(self) -> FlightPhase:
        """Get current flight phase."""
        return self._phase_manager.current_phase

    @property
    def current_frequency(self) -> str:
        """Get expected frequency type for current phase."""
        return self._phase_manager.current_frequency

    @property
    def available_requests(self) -> list[str]:
        """Get list of available request names for current phase."""
        return self._phase_manager.available_requests

    @property
    def frequencies(self) -> dict[str, float]:
        """Get all frequencies for the airport."""
        return self._frequencies.copy()

    def get_frequency(self, freq_type: str) -> float:
        """Get a specific frequency.

        Args:
            freq_type: Frequency type (ground, tower, atis, etc.).

        Returns:
            Frequency in MHz, or CTAF if not found.
        """
        return self._frequencies.get(freq_type.lower(), DEFAULT_CTAF)

    def get_atis(self, force_update: bool = False) -> ATISBroadcast:
        """Get current ATIS broadcast.

        Args:
            force_update: Force regeneration of ATIS.

        Returns:
            Current ATIS broadcast.
        """
        if self._current_atis is None or force_update:
            self._current_atis = self._atis_generator.generate(
                self.airport_icao, force_new_letter=force_update
            )
            self._assigned_runway = self._current_atis.active_runway

        return self._current_atis

    def select_runway(
        self,
        wind_direction: float,
        wind_speed: float,
        aircraft_category: AircraftCategory = AircraftCategory.LIGHT_GA,
    ) -> str:
        """Select the best runway for current conditions.

        Args:
            wind_direction: Wind direction in degrees.
            wind_speed: Wind speed in knots.
            aircraft_category: Aircraft type for length requirements.

        Returns:
            Selected runway identifier.
        """
        if self._gateway_data and self._gateway_data.runways:
            result = self._runway_selector.select_runway_from_gateway(
                self._gateway_data.runways,
                wind_direction,
                wind_speed,
                aircraft_category,
            )
            if result:
                return result.runway_id

        # Fallback to ATIS assigned runway
        return self._assigned_runway or "36"

    def get_taxi_route(
        self,
        start_lat: float,
        start_lon: float,
        runway: str | None = None,
    ) -> list[str]:
        """Get taxi route from position to runway.

        Args:
            start_lat: Starting latitude.
            start_lon: Starting longitude.
            runway: Target runway (uses assigned runway if None).

        Returns:
            List of taxiway names for the route.
        """
        if not self._taxiway_graph:
            return ["Alpha"]  # Generic fallback

        target_runway = runway or self._assigned_runway

        # Find nearest node to start position
        start_node = self._taxiway_graph.find_nearest_node(start_lat, start_lon)
        if start_node is None:
            return ["Alpha"]

        # Find runway hold node
        end_node = self._taxiway_graph.find_runway_hold_node(target_runway)
        if end_node is None:
            # Try to find any node near the runway
            runway_entries = self._taxiway_graph.find_runway_entry_nodes(target_runway)
            if runway_entries:
                end_node = runway_entries[0]
            else:
                return ["Alpha"]

        # Find route
        route = self._taxiway_graph.find_route(start_node, end_node)
        if route:
            taxiways = self._taxiway_graph.route_to_taxiway_names(route)
            self._assigned_taxiway_route = taxiways
            return taxiways if taxiways else ["Alpha"]

        return ["Alpha"]

    def handle_request(self, request: ATCRequest) -> ATCResponse:
        """Handle an ATC request.

        Args:
            request: The ATC request to handle.

        Returns:
            ATC response to the request.
        """
        request_type = request.request_type

        # Map request types to handlers
        handlers = {
            ATCRequestType.REQUEST_ATIS: self._handle_atis_request,
            ATCRequestType.REQUEST_STARTUP: self._handle_startup_request,
            ATCRequestType.REQUEST_TAXI: self._handle_taxi_request,
            ATCRequestType.READY_DEPARTURE: self._handle_ready_departure,
            ATCRequestType.REQUEST_TAKEOFF: self._handle_takeoff_request,
            ATCRequestType.CHECKIN_DEPARTURE: self._handle_departure_checkin,
            ATCRequestType.REQUEST_LANDING: self._handle_landing_request,
            ATCRequestType.REPORT_POSITION: self._handle_position_report,
            ATCRequestType.GO_AROUND: self._handle_go_around,
            ATCRequestType.REPORT_CLEAR: self._handle_clear_report,
        }

        handler = handlers.get(request_type)
        if handler:
            return handler(request)

        # Default response for unhandled requests
        return ATCResponse(
            request_type=request_type,
            approved=False,
            callsign=request.callsign,
            text=f"{self._abbreviated_callsign(request.callsign)}, {t('atc.standby')}",
            words=self._build_abbreviated_callsign_words(request.callsign) + ["STANDBY"],
        )

    def _handle_atis_request(self, request: ATCRequest) -> ATCResponse:
        """Handle ATIS request."""
        atis = self.get_atis()

        return ATCResponse(
            request_type=request.request_type,
            approved=True,
            callsign=request.callsign,
            text=atis.text,
            words=atis.words,
        )

    def _handle_startup_request(self, request: ATCRequest) -> ATCResponse:
        """Handle startup clearance request."""
        atis = self.get_atis()
        callsign_words = self._build_abbreviated_callsign_words(request.callsign)

        # Build facility name based on whether towered (use chunk IDs)
        facility = "GROUND" if self.is_towered else "traffic"
        facility_name = t("atc.ground") if self.is_towered else "traffic"

        words = (
            callsign_words
            + self._airport_name_words()
            + [facility]
            + ["STARTUP_APPROVED"]
            + ["ALTIMETER"]
            + PhoneticConverter.number_to_individual_digits(int(atis.weather.altimeter * 100))
            + ["ADVISE_READY_TO_TAXI"]
        )

        text = (
            f"{self._abbreviated_callsign(request.callsign)}, "
            f"{self.airport_name} {facility_name}, {t('atc.startup_approved')}, "
            f"{t('atc.altimeter')} {atis.weather.altimeter:.2f}, "
            f"{t('atc.advise_ready_taxi')}"
        )

        # Transition to parked hot
        self._phase_manager.transition_to(FlightPhase.PARKED_HOT, force=True)

        return ATCResponse(
            request_type=request.request_type,
            approved=True,
            callsign=request.callsign,
            text=text,
            words=words,
            instructions=[t('atc.startup_approved'), t('atc.advise_ready_taxi')],
        )

    def _handle_taxi_request(self, request: ATCRequest) -> ATCResponse:
        """Handle taxi clearance request."""
        self.get_atis()  # Ensure ATIS is current
        runway = self._assigned_runway
        runway_words = PhoneticConverter.runway_to_phonetic(runway)
        callsign_words = self._build_abbreviated_callsign_words(request.callsign)

        # Get taxi route if position provided
        taxiways = self._assigned_taxiway_route or ["Alpha"]
        if "start_lat" in request.data and "start_lon" in request.data:
            taxiways = self.get_taxi_route(
                request.data["start_lat"],
                request.data["start_lon"],
                runway,
            )

        # Build taxiway words
        taxiway_words = []
        for taxiway in taxiways:
            for char in taxiway.upper():
                if char.isalpha():
                    taxiway_words.append(PhoneticConverter.letter_to_phonetic(char))
                elif char.isdigit():
                    taxiway_words.append(PhoneticConverter.digit_to_phonetic(char))

        words = (
            callsign_words
            + ["TAXI_TO_RUNWAY"]
            + runway_words
            + ["VIA"]
            + taxiway_words
            + ["HOLD_SHORT_OF_RUNWAY"]
        )

        taxiway_str = ", ".join(taxiways)
        text = (
            f"{self._abbreviated_callsign(request.callsign)}, "
            f"{t('atc.taxi')} {t('atc.runway')} {' '.join(runway_words)} {t('atc.taxi_via')} {taxiway_str}, "
            f"{t('atc.hold_short')} {t('atc.runway')}"
        )

        # Transition to taxi out
        self._phase_manager.transition_to(FlightPhase.TAXI_OUT, force=True)

        return ATCResponse(
            request_type=request.request_type,
            approved=True,
            callsign=request.callsign,
            text=text,
            words=words,
            instructions=[
                f"{t('atc.taxi')} {t('atc.runway')} {runway} {t('atc.taxi_via')} {taxiway_str}",
                f"{t('atc.hold_short')} {t('atc.runway')}",
            ],
        )

    def _handle_ready_departure(self, request: ATCRequest) -> ATCResponse:
        """Handle ready for departure report."""
        runway = self._assigned_runway
        runway_words = PhoneticConverter.runway_to_phonetic(runway)
        callsign_words = self._build_abbreviated_callsign_words(request.callsign)

        # Get current wind
        atis = self.get_atis()
        wind_dir = atis.weather.wind.direction
        wind_speed = atis.weather.wind.speed

        # Build facility name (use chunk IDs)
        facility = "TOWER" if self.is_towered else "traffic"
        facility_name = t("atc.tower") if self.is_towered else "traffic"

        words = (
            callsign_words
            + self._airport_name_words()
            + [facility]
            + ["RUNWAY"]
            + runway_words
            + ["CLEARED_FOR_TAKEOFF"]
            + ["WIND"]
            + PhoneticConverter.number_to_individual_digits(wind_dir)
            + ["AT"]
            + PhoneticConverter.number_to_individual_digits(wind_speed)
        )

        text = (
            f"{self._abbreviated_callsign(request.callsign)}, "
            f"{self.airport_name} {facility_name}, "
            f"{t('atc.runway')} {' '.join(runway_words)}, {t('atc.cleared_for_takeoff')}, "
            f"{t('atc.wind')} {wind_dir:03d} {t('atc.at')} {wind_speed}"
        )

        # Transition to lineup
        self._phase_manager.transition_to(FlightPhase.HOLDING_SHORT, force=True)
        self._phase_manager.transition_to(FlightPhase.LINEUP, force=True)

        return ATCResponse(
            request_type=request.request_type,
            approved=True,
            callsign=request.callsign,
            text=text,
            words=words,
            instructions=[f"{t('atc.runway')} {runway} {t('atc.cleared_for_takeoff')}"],
            next_frequency=self._frequencies.get("tower"),
        )

    def _handle_takeoff_request(self, request: ATCRequest) -> ATCResponse:
        """Handle explicit takeoff clearance request."""
        return self._handle_ready_departure(request)

    def _handle_departure_checkin(self, request: ATCRequest) -> ATCResponse:
        """Handle check-in with departure control."""
        callsign_words = self._build_abbreviated_callsign_words(request.callsign)

        words = (
            callsign_words
            + self._airport_name_words()
            + ["DEPARTURE"]
            + ["RADAR_CONTACT"]
            + ["CLIMB_AND_MAINTAIN"]
            + ["three", "THOUSAND"]
        )

        text = (
            f"{self._abbreviated_callsign(request.callsign)}, "
            f"{self.airport_name} {t('atc.departure')}, {t('atc.radar_contact')}, "
            f"{t('atc.climb_and_maintain')} 3000"
        )

        # Transition to departure
        self._phase_manager.transition_to(FlightPhase.DEPARTURE, force=True)

        return ATCResponse(
            request_type=request.request_type,
            approved=True,
            callsign=request.callsign,
            text=text,
            words=words,
            instructions=[t("atc.radar_contact"), f"{t('atc.climb_and_maintain')} 3000"],
            next_frequency=self._frequencies.get("departure"),
        )

    def _handle_landing_request(self, request: ATCRequest) -> ATCResponse:
        """Handle landing clearance request."""
        runway = self._assigned_runway
        runway_words = PhoneticConverter.runway_to_phonetic(runway)
        callsign_words = self._build_abbreviated_callsign_words(request.callsign)

        # Get current wind
        atis = self.get_atis()
        wind_dir = atis.weather.wind.direction
        wind_speed = atis.weather.wind.speed

        # Build facility name (use chunk IDs)
        facility = "TOWER" if self.is_towered else "traffic"
        facility_name = t("atc.tower") if self.is_towered else "traffic"

        words = (
            callsign_words
            + self._airport_name_words()
            + [facility]
            + ["RUNWAY"]
            + runway_words
            + ["CLEARED_TO_LAND"]
            + ["WIND"]
            + PhoneticConverter.number_to_individual_digits(wind_dir)
            + ["AT"]
            + PhoneticConverter.number_to_individual_digits(wind_speed)
        )

        text = (
            f"{self._abbreviated_callsign(request.callsign)}, "
            f"{self.airport_name} {facility_name}, "
            f"{t('atc.runway')} {' '.join(runway_words)}, {t('atc.cleared_to_land')}, "
            f"{t('atc.wind')} {wind_dir:03d} {t('atc.at')} {wind_speed}"
        )

        # Transition to final
        self._phase_manager.transition_to(FlightPhase.FINAL, force=True)

        return ATCResponse(
            request_type=request.request_type,
            approved=True,
            callsign=request.callsign,
            text=text,
            words=words,
            instructions=[f"{t('atc.runway')} {runway} {t('atc.cleared_to_land')}"],
            next_frequency=self._frequencies.get("tower"),
        )

    def _handle_position_report(self, request: ATCRequest) -> ATCResponse:
        """Handle position report."""
        callsign_words = self._build_abbreviated_callsign_words(request.callsign)

        words = callsign_words + ["ROGER"]

        text = f"{self._abbreviated_callsign(request.callsign)}, {t('atc.roger')}"

        return ATCResponse(
            request_type=request.request_type,
            approved=True,
            callsign=request.callsign,
            text=text,
            words=words,
        )

    def _handle_go_around(self, request: ATCRequest) -> ATCResponse:
        """Handle go-around."""
        callsign_words = self._build_abbreviated_callsign_words(request.callsign)

        words = callsign_words + ["ROGER", "GO_AROUND", "FLY_RUNWAY_HEADING"]

        text = f"{self._abbreviated_callsign(request.callsign)}, {t('atc.roger')}, {t('atc.fly_runway_heading')}"

        # Transition back to pattern
        self._phase_manager.transition_to(FlightPhase.INITIAL_CLIMB, force=True)

        return ATCResponse(
            request_type=request.request_type,
            approved=True,
            callsign=request.callsign,
            text=text,
            words=words,
            instructions=[t("atc.fly_runway_heading")],
        )

    def _handle_clear_report(self, request: ATCRequest) -> ATCResponse:
        """Handle report clear of runway."""
        callsign_words = self._build_abbreviated_callsign_words(request.callsign)
        ground_freq = self._frequencies.get("ground", DEFAULT_CTAF)

        words = (
            callsign_words
            + ["ROGER"]
            + ["CONTACT_GROUND", "ON"]
            + PhoneticConverter.frequency_to_phonetic(ground_freq)
        )

        text = (
            f"{self._abbreviated_callsign(request.callsign)}, {t('atc.roger')}, "
            f"{t('atc.contact_ground')} {t('atc.on')} {ground_freq:.1f}"
        )

        # Transition to taxi in
        self._phase_manager.transition_to(FlightPhase.LANDING_ROLL, force=True)
        self._phase_manager.transition_to(FlightPhase.TAXI_IN, force=True)

        return ATCResponse(
            request_type=request.request_type,
            approved=True,
            callsign=request.callsign,
            text=text,
            words=words,
            instructions=[f"{t('atc.contact_ground')} {t('atc.on')} {ground_freq:.1f}"],
            next_frequency=ground_freq,
        )

    def _abbreviated_callsign(self, callsign: str) -> str:
        """Get abbreviated callsign (last 3 characters)."""
        phonetic = PhoneticConverter.callsign_to_phonetic(callsign)
        if len(phonetic) > 3:
            phonetic = phonetic[-3:]
        return " ".join(phonetic)

    def _build_abbreviated_callsign_words(self, callsign: str) -> list[str]:
        """Build abbreviated callsign word list."""
        phonetic = PhoneticConverter.callsign_to_phonetic(callsign)
        if len(phonetic) > 3:
            return phonetic[-3:]
        return phonetic

    def _airport_name_words(self) -> list[str]:
        """Get airport name as word list.

        Returns the ICAO code as a single chunk identifier for audio playback.
        The audio file (e.g., LFLY.ogg) contains the full airport name.
        """
        # Use ICAO code as chunk identifier for phrase-based audio
        return [self.airport_icao.upper()]

    def _get_airport_runways(self) -> list[tuple[str, int]]:
        """Get runways for the current airport."""
        runways = []

        # Try Gateway data first
        if self._gateway_data and self._gateway_data.runways:
            for rwy in self._gateway_data.runways:
                runways.append((rwy.id1, int(rwy.heading1)))
                runways.append((rwy.id2, int(rwy.heading2)))
            return runways

        # Default fallback
        return [("36", 360), ("18", 180)]

    def transition_phase(self, new_phase: FlightPhase, force: bool = False) -> bool:
        """Manually transition flight phase.

        Args:
            new_phase: Phase to transition to.
            force: Force invalid transitions.

        Returns:
            True if transition succeeded.
        """
        return self._phase_manager.transition_to(new_phase, force=force)

    def reset(self) -> None:
        """Reset ATC handler to initial state."""
        self._phase_manager.reset()
        self._current_atis = None
        self._assigned_runway = ""
        self._assigned_taxiway_route = []

    def change_airport(self, airport_icao: str, airport_name: str | None = None) -> None:
        """Change to a different airport.

        Args:
            airport_icao: New airport ICAO code.
            airport_name: New airport name (auto-loaded if None).
        """
        self.airport_icao = airport_icao.upper()

        # Load new airport data
        self._gateway_data = self._gateway_loader.get_airport(airport_icao)

        # Update name
        if airport_name:
            self.airport_name = airport_name
        elif self._gateway_data:
            self.airport_name = self._gateway_data.name
        else:
            self.airport_name = f"{airport_icao} Airport"

        # Rebuild taxiway graph
        if self._gateway_data:
            self._taxiway_graph = TaxiwayGraph.from_gateway_data(self._gateway_data)
        else:
            self._taxiway_graph = None

        # Reload frequencies
        self._frequencies = self._load_frequencies()

        # Re-register airport with ATIS generator
        self._atis_generator.register_airport(
            airport_icao,
            self.airport_name,
            self._get_airport_runways(),
            tower_freq=self._frequencies.get("tower", DEFAULT_CTAF),
            ground_freq=self._frequencies.get("ground", DEFAULT_CTAF),
            atis_freq=self._frequencies.get("atis", DEFAULT_CTAF),
        )

        # Reset state
        self.reset()

        logger.info(
            "ATCHandler changed to %s (%s), towered=%s",
            self.airport_name,
            airport_icao,
            self.is_towered,
        )

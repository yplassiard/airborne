"""ATC Manager for realistic air traffic control communications."""

from dataclasses import dataclass
from enum import Enum

from airborne.physics.vectors import Vector3
from airborne.plugins.radio.phraseology import PhraseContext, PhraseMaker


class ATCType(Enum):
    """Types of ATC controllers."""

    GROUND = "ground"
    TOWER = "tower"
    DEPARTURE = "departure"
    APPROACH = "approach"
    CENTER = "center"
    CLEARANCE = "clearance"


@dataclass
class ATCController:
    """Represents an ATC controller.

    Attributes:
        type: Type of controller (Ground, Tower, etc.)
        airport_icao: Airport ICAO code (e.g., "KPAO")
        airport_name: Airport name (e.g., "Palo Alto")
        frequency: Controller frequency in MHz
        position: Geographic position of the controller
        active_runway: Currently active runway identifier
    """

    type: ATCType
    airport_icao: str
    airport_name: str
    frequency: float
    position: Vector3
    active_runway: str = "31"


@dataclass
class ATCRequest:
    """Represents a request made to ATC.

    Attributes:
        request_type: Type of request (taxi, takeoff, etc.)
        callsign: Aircraft callsign
        location: Current location (for Ground)
        atis_letter: ATIS information letter received
        altitude: Current altitude in feet (for airborne requests)
        heading: Current heading in degrees (for airborne requests)
    """

    request_type: str
    callsign: str
    location: str = ""
    atis_letter: str = ""
    altitude: int = 0
    heading: int = 0


class ATCManager:
    """Manages ATC communications with context awareness.

    Provides realistic ATC responses based on aircraft state,
    location, and current operations phase.

    Examples:
        >>> atc = ATCManager()
        >>> controller = ATCController(
        ...     type=ATCType.GROUND,
        ...     airport_icao="KPAO",
        ...     airport_name="Palo Alto",
        ...     frequency=121.7,
        ...     position=Vector3(0, 0, 0)
        ... )
        >>> atc.add_controller(controller)
        >>> request = ATCRequest(
        ...     request_type="taxi",
        ...     callsign="Cessna 123AB",
        ...     location="parking",
        ...     atis_letter="Bravo"
        ... )
        >>> response = atc.process_request(ATCType.GROUND, request)
    """

    def __init__(self) -> None:
        """Initialize ATC manager."""
        self.phrase_maker = PhraseMaker()
        self.controllers: dict[ATCType, ATCController] = {}
        self._last_taxiway = "Alpha"  # Track for clearances

    def add_controller(self, controller: ATCController) -> None:
        """Add an ATC controller to the system.

        Args:
            controller: Controller to add
        """
        self.controllers[controller.type] = controller

    def remove_controller(self, controller_type: ATCType) -> None:
        """Remove an ATC controller from the system.

        Args:
            controller_type: Type of controller to remove
        """
        if controller_type in self.controllers:
            del self.controllers[controller_type]

    def get_controller(self, controller_type: ATCType) -> ATCController | None:
        """Get a controller by type.

        Args:
            controller_type: Type of controller to retrieve

        Returns:
            Controller if found, None otherwise
        """
        return self.controllers.get(controller_type)

    def process_request(self, controller_type: ATCType, request: ATCRequest) -> str:
        """Process an ATC request and generate response.

        Args:
            controller_type: Type of controller to contact
            request: Details of the request

        Returns:
            ATC response phraseology

        Raises:
            ValueError: If controller type not found or request type unknown
        """
        controller = self.controllers.get(controller_type)
        if not controller:
            raise ValueError(f"No controller of type {controller_type}")

        # Build phrase context
        context = PhraseContext(
            callsign=request.callsign,
            airport=controller.airport_name,
            runway=controller.active_runway,
            taxiway=self._last_taxiway,
            altitude=request.altitude,
            heading=request.heading,
            location=request.location,
            atis=request.atis_letter,
        )

        # Route to appropriate handler
        if controller_type == ATCType.GROUND:
            return self._handle_ground_request(request, context)
        elif controller_type == ATCType.TOWER:
            return self._handle_tower_request(request, context)
        elif controller_type == ATCType.DEPARTURE:
            return self._handle_departure_request(request, context)
        elif controller_type == ATCType.APPROACH:
            return self._handle_approach_request(request, context)
        elif controller_type == ATCType.CENTER:
            return self._handle_center_request(request, context)
        elif controller_type == ATCType.CLEARANCE:
            return self._handle_clearance_request(request, context)
        else:
            raise ValueError(f"Unknown controller type: {controller_type}")

    def _handle_ground_request(self, request: ATCRequest, context: PhraseContext) -> str:
        """Handle Ground controller requests.

        Args:
            request: Request details
            context: Phrase context

        Returns:
            ATC response

        Raises:
            ValueError: If request type is unknown
        """
        if request.request_type == "taxi":
            return self.phrase_maker.make_atc_phrase("taxi_clearance", context)
        elif request.request_type == "pushback":
            return self.phrase_maker.make_atc_phrase(
                "pushback_approved", context, direction="north"
            )
        elif request.request_type == "taxi_complete":
            # Switch to tower
            tower = self.controllers.get(ATCType.TOWER)
            if tower:
                return self.phrase_maker.make_atc_phrase(
                    "contact_tower", context, frequency=tower.frequency
                )
            return self.phrase_maker.make_atc_phrase("roger", context)
        else:
            raise ValueError(f"Unknown ground request: {request.request_type}")

    def _handle_tower_request(self, request: ATCRequest, context: PhraseContext) -> str:
        """Handle Tower controller requests.

        Args:
            request: Request details
            context: Phrase context

        Returns:
            ATC response

        Raises:
            ValueError: If request type is unknown
        """
        if request.request_type == "takeoff_ready":
            return self.phrase_maker.make_atc_phrase("takeoff_clearance", context)
        elif request.request_type == "landing_request":
            return self.phrase_maker.make_atc_phrase("landing_clearance", context)
        elif request.request_type == "pattern_entry":
            return self.phrase_maker.make_atc_phrase(
                "pattern_clearance", context, pattern="left traffic"
            )
        elif request.request_type == "airborne":
            # Switch to departure if available
            departure = self.controllers.get(ATCType.DEPARTURE)
            if departure:
                return self.phrase_maker.make_atc_phrase(
                    "departure_clearance",
                    context,
                    altitude=3000,
                    frequency=departure.frequency,
                )
            return self.phrase_maker.make_atc_phrase("roger", context)
        elif request.request_type == "clear_runway":
            # Switch back to ground
            ground = self.controllers.get(ATCType.GROUND)
            if ground:
                return self.phrase_maker.make_atc_phrase(
                    "contact_ground", context, frequency=ground.frequency
                )
            return self.phrase_maker.make_atc_phrase("roger", context)
        elif request.request_type == "radio_check":
            return self.phrase_maker.make_atc_phrase("radio_check_ok", context)
        else:
            raise ValueError(f"Unknown tower request: {request.request_type}")

    def _handle_departure_request(self, request: ATCRequest, context: PhraseContext) -> str:
        """Handle Departure controller requests.

        Args:
            request: Request details
            context: Phrase context

        Returns:
            ATC response

        Raises:
            ValueError: If request type is unknown
        """
        if request.request_type == "check_in":
            return self.phrase_maker.make_atc_phrase("roger", context)
        elif request.request_type == "altitude_request":
            return self.phrase_maker.make_atc_phrase(
                "departure_clearance", context, altitude=request.altitude, frequency=0
            )
        else:
            raise ValueError(f"Unknown departure request: {request.request_type}")

    def _handle_approach_request(self, request: ATCRequest, context: PhraseContext) -> str:
        """Handle Approach controller requests.

        Args:
            request: Request details
            context: Phrase context

        Returns:
            ATC response

        Raises:
            ValueError: If request type is unknown
        """
        if request.request_type == "approach_request":
            return self.phrase_maker.make_atc_phrase("landing_clearance", context)
        else:
            raise ValueError(f"Unknown approach request: {request.request_type}")

    def _handle_center_request(self, request: ATCRequest, context: PhraseContext) -> str:
        """Handle Center controller requests.

        Args:
            request: Request details
            context: Phrase context

        Returns:
            ATC response

        Raises:
            ValueError: If request type is unknown
        """
        if request.request_type == "check_in":
            return self.phrase_maker.make_atc_phrase("roger", context)
        else:
            raise ValueError(f"Unknown center request: {request.request_type}")

    def _handle_clearance_request(self, request: ATCRequest, context: PhraseContext) -> str:
        """Handle Clearance Delivery requests.

        Args:
            request: Request details
            context: Phrase context

        Returns:
            ATC response

        Raises:
            ValueError: If request type is unknown
        """
        if request.request_type == "ifr_clearance":
            return self.phrase_maker.make_atc_phrase(
                "departure_clearance", context, altitude=5000, frequency=0
            )
        else:
            raise ValueError(f"Unknown clearance request: {request.request_type}")

    def issue_traffic_advisory(
        self,
        callsign: str,
        distance_clock: str,
        range_miles: int,
        aircraft_type: str,
        altitude: int,
    ) -> str:
        """Issue a traffic advisory.

        Args:
            callsign: Aircraft callsign
            distance_clock: Clock position (e.g., "2 o'clock")
            range_miles: Distance in nautical miles
            aircraft_type: Type of traffic aircraft
            altitude: Traffic altitude in feet

        Returns:
            Traffic advisory phraseology

        Examples:
            >>> atc = ATCManager()
            >>> advisory = atc.issue_traffic_advisory(
            ...     "Cessna 123AB", "2", 3, "Piper", 2500
            ... )
        """
        context = PhraseContext(callsign=callsign, altitude=altitude)
        return self.phrase_maker.make_atc_phrase(
            "traffic_advisory",
            context,
            distance=distance_clock,
            range=range_miles,
            type=aircraft_type,
        )

    def set_active_runway(self, runway: str) -> None:
        """Set the active runway for all controllers.

        Args:
            runway: Runway identifier (e.g., "31")
        """
        for controller in self.controllers.values():
            controller.active_runway = runway

    def get_nearest_controller(
        self, position: Vector3, controller_types: list[ATCType] | None = None
    ) -> ATCController | None:
        """Get the nearest controller to a position.

        Args:
            position: Aircraft position
            controller_types: Optional list of controller types to consider

        Returns:
            Nearest controller, or None if no controllers available
        """
        if not self.controllers:
            return None

        available_list = list(self.controllers.values())
        if controller_types:
            available_list = [c for c in available_list if c.type in controller_types]

        if not available_list:
            return None

        # Find nearest by distance
        nearest = min(available_list, key=lambda c: position.distance_to(c.position))
        return nearest

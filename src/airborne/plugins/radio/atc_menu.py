"""ATC menu system for interactive radio communications.

This module provides a context-aware menu system for player-initiated
ATC communications. The menu displays options based on aircraft state
(on ground, airborne, engine state, etc.) and handles player input.

Typical usage example:
    menu = ATCMenu(tts_provider, atc_queue)

    # Check if menu should be available
    if menu.is_available(aircraft_state):
        menu.open(aircraft_state)

    # Handle key press
    menu.select_option("1")
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


class FlightPhase(Enum):
    """Flight phase for context-aware menu options."""

    ON_GROUND_ENGINE_OFF = "on_ground_engine_off"
    ON_GROUND_ENGINE_RUNNING = "on_ground_engine_running"
    HOLDING_SHORT = "holding_short"
    ON_RUNWAY = "on_runway"
    AIRBORNE_DEPARTURE = "airborne_departure"
    AIRBORNE_CRUISE = "airborne_cruise"
    AIRBORNE_APPROACH = "airborne_approach"
    UNKNOWN = "unknown"


@dataclass
class ATCMenuOption:
    """Represents a single ATC menu option.

    Attributes:
        key: Key to select this option (e.g., "1", "2").
        label: Human-readable label shown in menu.
        pilot_message: Message key(s) pilot transmits when selected.
        expected_atc_response: Message key(s) ATC responds with.
        callback: Optional callback function called when option selected.
        enabled: Whether this option is currently available.
    """

    key: str
    label: str
    pilot_message: str | list[str]
    expected_atc_response: str | list[str]
    callback: Optional[Callable[[], None]] = None
    enabled: bool = True


class ATCMenu:
    """Context-aware ATC menu system.

    Provides interactive menu for ATC communications with options that
    change based on aircraft state and flight phase.

    The menu uses a state machine:
    - CLOSED: Menu not visible
    - OPEN: Menu displayed, waiting for selection
    - WAITING_RESPONSE: Pilot message sent, waiting for ATC response

    Examples:
        >>> menu = ATCMenu(tts, queue)
        >>> state = {"on_ground": True, "engine_running": True}
        >>> menu.open(state)
        >>> options = menu.get_current_options()
        >>> print(options[0].label)
        'Request Taxi'
    """

    def __init__(self, tts_provider: Any, atc_queue: Any):
        """Initialize ATC menu.

        Args:
            tts_provider: TTS provider for reading menu options.
            atc_queue: ATCMessageQueue for enqueueing messages.
        """
        self._tts = tts_provider
        self._atc_queue = atc_queue
        self._state = "CLOSED"  # CLOSED, OPEN, WAITING_RESPONSE
        self._current_options: list[ATCMenuOption] = []
        self._current_phase: FlightPhase = FlightPhase.UNKNOWN
        self._last_aircraft_state: dict[str, Any] = {}

        logger.info("ATC menu initialized")

    def open(self, aircraft_state: dict[str, Any]) -> None:
        """Open the ATC menu with context-aware options.

        Args:
            aircraft_state: Dictionary containing aircraft state:
                - on_ground: bool
                - engine_running: bool
                - altitude_agl: float (feet)
                - airspeed: float (knots)
                - position: dict with lat/lon
                - holding_short: bool (optional)
                - on_runway: bool (optional)

        Note:
            If menu is already open, this will update options based on new state.
        """
        self._last_aircraft_state = aircraft_state
        self._current_phase = self._determine_flight_phase(aircraft_state)
        self._current_options = self._get_context_options(self._current_phase)

        if not self._current_options:
            logger.warning(f"No menu options available for phase: {self._current_phase}")
            return

        self._state = "OPEN"
        logger.info(f"ATC menu opened (phase: {self._current_phase.value})")

        # Read menu to player
        self.read_menu()

    def close(self) -> None:
        """Close the ATC menu."""
        if self._state != "CLOSED":
            self._state = "CLOSED"
            self._current_options = []
            logger.debug("ATC menu closed")

            # Provide audio feedback
            if self._tts:
                self._tts.speak("Menu closed")

    def select_option(self, key: str) -> bool:
        """Select a menu option by key.

        Args:
            key: Option key (e.g., "1", "2", "3").

        Returns:
            True if option was found and selected, False otherwise.
        """
        if self._state != "OPEN":
            logger.warning(f"Cannot select option, menu state is: {self._state}")
            return False

        # Find option by key
        selected_option = None
        for option in self._current_options:
            if option.key == key and option.enabled:
                selected_option = option
                break

        if not selected_option:
            logger.debug(f"Invalid or disabled option selected: {key}")
            # Provide audio feedback
            if self._tts:
                self._tts.speak("Invalid option")
            return False

        logger.info(f"Selected menu option: {selected_option.label}")

        # Execute the option
        self._execute_option(selected_option)

        return True

    def read_menu(self) -> None:
        """Read menu options aloud using TTS."""
        if self._state != "OPEN" or not self._current_options:
            return

        # Build menu text
        menu_text = "ATC Menu. "
        for option in self._current_options:
            if option.enabled:
                menu_text += f"{option.key}. {option.label}. "

        menu_text += "Press escape to close."

        logger.debug(f"Reading menu: {menu_text}")

        # Speak menu
        if self._tts:
            self._tts.speak(menu_text)

    def get_current_options(self) -> list[ATCMenuOption]:
        """Get current menu options.

        Returns:
            List of ATCMenuOption for current flight phase.
        """
        return self._current_options.copy()

    def is_open(self) -> bool:
        """Check if menu is currently open.

        Returns:
            True if menu is open.
        """
        return self._state == "OPEN"

    def is_waiting_response(self) -> bool:
        """Check if waiting for ATC response.

        Returns:
            True if waiting for ATC response.
        """
        return self._state == "WAITING_RESPONSE"

    def is_available(self, aircraft_state: dict[str, Any]) -> bool:
        """Check if ATC menu should be available for current state.

        Args:
            aircraft_state: Aircraft state dictionary.

        Returns:
            True if ATC communications are appropriate for current state.
        """
        # ATC not available if queue is busy
        if self._atc_queue and self._atc_queue.is_busy():
            return False

        # ATC available in most phases
        phase = self._determine_flight_phase(aircraft_state)
        return phase != FlightPhase.UNKNOWN

    def _determine_flight_phase(self, aircraft_state: dict[str, Any]) -> FlightPhase:
        """Determine current flight phase from aircraft state.

        Args:
            aircraft_state: Aircraft state dictionary.

        Returns:
            FlightPhase enum value.
        """
        on_ground = aircraft_state.get("on_ground", True)
        engine_running = aircraft_state.get("engine_running", False)
        altitude_agl = aircraft_state.get("altitude_agl", 0.0)
        holding_short = aircraft_state.get("holding_short", False)
        on_runway = aircraft_state.get("on_runway", False)

        # On ground phases
        if on_ground:
            if not engine_running:
                return FlightPhase.ON_GROUND_ENGINE_OFF
            elif holding_short:
                return FlightPhase.HOLDING_SHORT
            elif on_runway:
                return FlightPhase.ON_RUNWAY
            else:
                return FlightPhase.ON_GROUND_ENGINE_RUNNING

        # Airborne phases
        if altitude_agl > 0:
            if altitude_agl < 3000:
                return FlightPhase.AIRBORNE_DEPARTURE
            elif altitude_agl > 10000:
                return FlightPhase.AIRBORNE_CRUISE
            else:
                # Could be climbing or descending, default to cruise
                return FlightPhase.AIRBORNE_CRUISE

        return FlightPhase.UNKNOWN

    def _get_context_options(self, phase: FlightPhase) -> list[ATCMenuOption]:
        """Get menu options for given flight phase.

        Args:
            phase: Current flight phase.

        Returns:
            List of ATCMenuOption appropriate for phase.
        """
        options = []

        if phase == FlightPhase.ON_GROUND_ENGINE_OFF:
            options = [
                ATCMenuOption(
                    key="1",
                    label="Request Startup Clearance",
                    pilot_message="PILOT_REQUEST_STARTUP",
                    expected_atc_response="ATC_CLEARED",
                ),
                ATCMenuOption(
                    key="2",
                    label="Request ATIS",
                    pilot_message="PILOT_REQUEST_ATIS",
                    expected_atc_response=["ATIS_AIRPORT_INFO", "ATIS_INFO_ALPHA"],
                ),
            ]

        elif phase == FlightPhase.ON_GROUND_ENGINE_RUNNING:
            options = [
                ATCMenuOption(
                    key="1",
                    label="Request Taxi",
                    pilot_message="PILOT_REQUEST_TAXI",
                    expected_atc_response="ATC_GROUND_TAXI_RWY_31",
                ),
                ATCMenuOption(
                    key="2",
                    label="Request ATIS",
                    pilot_message="PILOT_REQUEST_ATIS",
                    expected_atc_response=["ATIS_AIRPORT_INFO", "ATIS_INFO_ALPHA"],
                ),
            ]

        elif phase == FlightPhase.HOLDING_SHORT:
            options = [
                ATCMenuOption(
                    key="1",
                    label="Request Takeoff Clearance",
                    pilot_message="PILOT_REQUEST_TAKEOFF",
                    expected_atc_response="ATC_TOWER_CLEARED_TAKEOFF_31",
                ),
                ATCMenuOption(
                    key="2",
                    label="Report Ready for Departure",
                    pilot_message="PILOT_READY_FOR_DEPARTURE",
                    expected_atc_response="ATC_ROGER",
                ),
            ]

        elif phase == FlightPhase.ON_RUNWAY:
            options = [
                ATCMenuOption(
                    key="1",
                    label="Report Ready for Departure",
                    pilot_message="PILOT_READY_FOR_DEPARTURE",
                    expected_atc_response="ATC_TOWER_CLEARED_TAKEOFF_31",
                ),
            ]

        elif phase == FlightPhase.AIRBORNE_DEPARTURE:
            options = [
                ATCMenuOption(
                    key="1",
                    label="Check In with Departure",
                    pilot_message="PILOT_CHECKIN_DEPARTURE",
                    expected_atc_response="ATC_DEPARTURE_RADAR_CONTACT",
                ),
                ATCMenuOption(
                    key="2",
                    label="Report Altitude",
                    pilot_message="PILOT_REPORT_ALTITUDE",
                    expected_atc_response="ATC_ROGER",
                ),
            ]

        elif phase == FlightPhase.AIRBORNE_CRUISE:
            options = [
                ATCMenuOption(
                    key="1",
                    label="Request Flight Following",
                    pilot_message="PILOT_REQUEST_FLIGHT_FOLLOWING",
                    expected_atc_response="ATC_ROGER",
                ),
                ATCMenuOption(
                    key="2",
                    label="Report Position",
                    pilot_message="PILOT_REPORT_POSITION",
                    expected_atc_response="ATC_ROGER",
                ),
            ]

        return options

    def _execute_option(self, option: ATCMenuOption) -> None:
        """Execute selected menu option.

        Args:
            option: Selected ATCMenuOption.
        """
        from airborne.plugins.radio.atc_queue import ATCMessage

        # Close menu
        self.close()
        self._state = "WAITING_RESPONSE"

        # Enqueue pilot message
        pilot_msg = ATCMessage(
            message_key=option.pilot_message,
            sender="PILOT",
            priority=0,
            delay_after=2.0,  # Wait 2 seconds after pilot transmission
        )
        self._atc_queue.enqueue(pilot_msg)

        # Enqueue ATC response
        atc_msg = ATCMessage(
            message_key=option.expected_atc_response,
            sender="ATC",
            priority=0,
            delay_after=0.0,  # ATC gets random delay from queue
            callback=self._on_atc_response_complete,
        )
        self._atc_queue.enqueue(atc_msg)

        # Execute callback if provided
        if option.callback:
            try:
                option.callback()
            except Exception as e:
                logger.error(f"Error in option callback: {e}")

        logger.debug(f"Enqueued pilot and ATC messages for: {option.label}")

    def _on_atc_response_complete(self) -> None:
        """Callback when ATC response completes."""
        if self._state == "WAITING_RESPONSE":
            self._state = "CLOSED"
            logger.debug("ATC response complete, menu returned to closed state")

    def get_state(self) -> str:
        """Get current menu state.

        Returns:
            Current state string (CLOSED, OPEN, WAITING_RESPONSE).
        """
        return self._state

    def get_current_phase(self) -> FlightPhase:
        """Get current flight phase.

        Returns:
            Current FlightPhase enum value.
        """
        return self._current_phase

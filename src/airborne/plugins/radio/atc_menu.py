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

from collections.abc import Callable
from enum import Enum
from typing import Any

from airborne.core.logging_system import get_logger
from airborne.ui.menu import Menu, MenuOption

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


class ATCMenu(Menu):
    """Context-aware ATC menu system.

    Extends the generic Menu base class to provide ATC-specific functionality.
    Provides interactive menu for ATC communications with options that
    change based on aircraft state and flight phase.

    The menu uses a state machine:
    - CLOSED: Menu not visible
    - OPEN: Menu displayed, waiting for selection
    - WAITING_RESPONSE: Pilot message sent, waiting for ATC response (additional state)

    Examples:
        >>> menu = ATCMenu(tts, queue)
        >>> state = {"on_ground": True, "engine_running": True}
        >>> menu.open(state)
        >>> options = menu.get_current_options()
        >>> print(options[0].label)
        'Request Taxi'
    """

    def __init__(self, tts_provider: Any, atc_queue: Any, message_queue: Any = None):
        """Initialize ATC menu.

        Args:
            tts_provider: TTS provider for reading menu options.
            atc_queue: ATCMessageQueue for enqueueing messages.
            message_queue: Message queue for sending TTS requests (optional).
        """
        super().__init__(message_queue, sender_name="atc_menu")

        self._tts = tts_provider
        self._atc_queue = atc_queue
        self._waiting_response = False
        self._current_phase: FlightPhase = FlightPhase.UNKNOWN
        self._last_aircraft_state: dict[str, Any] = {}

        logger.info("ATC menu initialized")

    # Public API methods

    def is_available(self, aircraft_state: dict[str, Any] | None = None) -> bool:
        """Check if ATC menu should be available.

        Args:
            aircraft_state: Aircraft state dictionary.

        Returns:
            True if ATC communications are appropriate for current state.
        """
        return self._is_available(aircraft_state)

    # Override get_state to handle WAITING_RESPONSE state

    def get_state(self) -> str:
        """Get current menu state.

        Returns:
            Current state string (CLOSED, OPEN, WAITING_RESPONSE).
        """
        if self._waiting_response:
            return "WAITING_RESPONSE"
        return super().get_state()

    def is_waiting_response(self) -> bool:
        """Check if waiting for ATC response.

        Returns:
            True if waiting for ATC response.
        """
        return self._waiting_response

    def get_current_phase(self) -> FlightPhase:
        """Get current flight phase.

        Returns:
            Current FlightPhase enum value.
        """
        return self._current_phase

    # Implement abstract methods from Menu base class

    def _build_options(self, context: Any) -> list[MenuOption]:
        """Build menu options based on aircraft state.

        Args:
            context: Aircraft state dictionary.

        Returns:
            List of MenuOption for current flight phase.
        """
        # Store aircraft state
        self._last_aircraft_state = context if context else {}

        # Determine flight phase
        self._current_phase = self._determine_flight_phase(self._last_aircraft_state)

        # Get context-specific options
        return self._get_context_options(self._current_phase)

    def _handle_selection(self, option: MenuOption) -> None:
        """Handle selection of an ATC menu option.

        Args:
            option: The selected MenuOption.
        """
        from airborne.plugins.radio.atc_queue import ATCMessage

        # Extract ATC-specific data from option
        pilot_message = option.data.get("pilot_message")
        expected_atc_response = option.data.get("expected_atc_response")
        callback = option.data.get("callback")

        # Close menu silently (don't speak "menu closed" when selecting option)
        super().close(speak=False)
        self._waiting_response = True

        # Enqueue pilot message
        pilot_msg = ATCMessage(
            message_key=pilot_message,
            sender="PILOT",
            priority=0,
            delay_after=2.0,  # Wait 2 seconds after pilot transmission
        )
        self._atc_queue.enqueue(pilot_msg)

        # Enqueue ATC response
        atc_msg = ATCMessage(
            message_key=expected_atc_response,
            sender="ATC",
            priority=0,
            delay_after=0.0,  # ATC gets random delay from queue
            callback=self._on_atc_response_complete,
        )
        self._atc_queue.enqueue(atc_msg)

        # Execute callback if provided
        if callback:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in option callback: {e}")

        logger.debug(f"Enqueued pilot and ATC messages for: {option.label}")

    def _get_menu_opened_message(self) -> str:
        """Get TTS message key for menu opened.

        Returns:
            Message key string.
        """
        return "MSG_ATC_MENU_OPENED"

    def _get_menu_closed_message(self) -> str:
        """Get TTS message key for menu closed.

        Returns:
            Message key string.
        """
        return "MSG_ATC_MENU_CLOSED"

    def _get_invalid_option_message(self) -> str:
        """Get TTS message key for invalid option.

        Returns:
            Message key string.
        """
        return "MSG_ATC_INVALID_OPTION"

    def _is_available(self, context: Any) -> bool:
        """Check if ATC menu should be available for current state.

        Args:
            context: Aircraft state dictionary.

        Returns:
            True if ATC communications are appropriate for current state.
        """
        # ATC not available if queue is busy
        if self._atc_queue and self._atc_queue.is_busy():
            return False

        # ATC available in most phases
        if context:
            phase = self._determine_flight_phase(context)
            return phase != FlightPhase.UNKNOWN

        return True

    # ATC-specific helper methods

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

    def _get_context_options(self, phase: FlightPhase) -> list[MenuOption]:
        """Get menu options for given flight phase.

        Args:
            phase: Current flight phase.

        Returns:
            List of MenuOption appropriate for phase.
        """
        options = []

        if phase == FlightPhase.ON_GROUND_ENGINE_OFF:
            options = [
                MenuOption(
                    key="1",
                    label="Request Startup Clearance",
                    message_key="MSG_ATC_OPTION_REQUEST_STARTUP",
                    data={
                        "pilot_message": "PILOT_REQUEST_STARTUP",
                        "expected_atc_response": "ATC_CLEARED",
                    },
                ),
                MenuOption(
                    key="2",
                    label="Request ATIS",
                    message_key="MSG_ATC_OPTION_REQUEST_ATIS",
                    data={
                        "pilot_message": "PILOT_REQUEST_ATIS",
                        "expected_atc_response": ["ATIS_AIRPORT_INFO", "ATIS_INFO_ALPHA"],
                    },
                ),
            ]

        elif phase == FlightPhase.ON_GROUND_ENGINE_RUNNING:
            options = [
                MenuOption(
                    key="1",
                    label="Request Taxi",
                    message_key="MSG_ATC_OPTION_REQUEST_TAXI",
                    data={
                        "pilot_message": "PILOT_REQUEST_TAXI",
                        "expected_atc_response": "ATC_GROUND_TAXI_RWY_31",
                    },
                ),
                MenuOption(
                    key="2",
                    label="Request ATIS",
                    message_key="MSG_ATC_OPTION_REQUEST_ATIS",
                    data={
                        "pilot_message": "PILOT_REQUEST_ATIS",
                        "expected_atc_response": ["ATIS_AIRPORT_INFO", "ATIS_INFO_ALPHA"],
                    },
                ),
            ]

        elif phase == FlightPhase.HOLDING_SHORT:
            options = [
                MenuOption(
                    key="1",
                    label="Request Takeoff Clearance",
                    message_key="MSG_ATC_OPTION_REQUEST_TAKEOFF",
                    data={
                        "pilot_message": "PILOT_REQUEST_TAKEOFF",
                        "expected_atc_response": "ATC_TOWER_CLEARED_TAKEOFF_31",
                    },
                ),
                MenuOption(
                    key="2",
                    label="Report Ready for Departure",
                    message_key="MSG_ATC_OPTION_READY_DEPARTURE",
                    data={
                        "pilot_message": "PILOT_READY_FOR_DEPARTURE",
                        "expected_atc_response": "ATC_ROGER",
                    },
                ),
            ]

        elif phase == FlightPhase.ON_RUNWAY:
            options = [
                MenuOption(
                    key="1",
                    label="Report Ready for Departure",
                    message_key="MSG_ATC_OPTION_READY_DEPARTURE",
                    data={
                        "pilot_message": "PILOT_READY_FOR_DEPARTURE",
                        "expected_atc_response": "ATC_TOWER_CLEARED_TAKEOFF_31",
                    },
                ),
            ]

        elif phase == FlightPhase.AIRBORNE_DEPARTURE:
            options = [
                MenuOption(
                    key="1",
                    label="Check In with Departure",
                    message_key="MSG_ATC_OPTION_CHECKIN_DEPARTURE",
                    data={
                        "pilot_message": "PILOT_CHECKIN_DEPARTURE",
                        "expected_atc_response": "ATC_DEPARTURE_RADAR_CONTACT",
                    },
                ),
                MenuOption(
                    key="2",
                    label="Report Altitude",
                    message_key="MSG_ATC_OPTION_REPORT_ALTITUDE",
                    data={
                        "pilot_message": "PILOT_REPORT_ALTITUDE",
                        "expected_atc_response": "ATC_ROGER",
                    },
                ),
            ]

        elif phase == FlightPhase.AIRBORNE_CRUISE:
            options = [
                MenuOption(
                    key="1",
                    label="Request Flight Following",
                    message_key="MSG_ATC_OPTION_REQUEST_FLIGHT_FOLLOWING",
                    data={
                        "pilot_message": "PILOT_REQUEST_FLIGHT_FOLLOWING",
                        "expected_atc_response": "ATC_ROGER",
                    },
                ),
                MenuOption(
                    key="2",
                    label="Report Position",
                    message_key="MSG_ATC_OPTION_REPORT_POSITION",
                    data={
                        "pilot_message": "PILOT_REPORT_POSITION",
                        "expected_atc_response": "ATC_ROGER",
                    },
                ),
            ]

        return options

    def _on_atc_response_complete(self) -> None:
        """Callback when ATC response completes."""
        if self._waiting_response:
            self._waiting_response = False
            logger.debug("ATC response complete, menu returned to closed state")

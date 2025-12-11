"""ATC menu system for interactive radio communications.

This module provides a context-aware menu system for player-initiated
ATC communications. The menu displays options based on aircraft state
(on ground, airborne, engine state, etc.) and handles player input.

Generates realistic phraseology dynamically based on flight context.

Typical usage example:
    menu = ATCMenu(tts_provider, atc_queue, phraseology)

    # Check if menu should be available
    if menu.is_available(aircraft_state):
        menu.open(aircraft_state)

    # Handle key press
    menu.select_option("1")
"""

from enum import Enum
from typing import Any

from airborne.core.i18n import t
from airborne.core.logging_system import get_logger
from airborne.plugins.radio.atc_phraseology import ATCPhraseology, FlightContext
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
    """Context-aware ATC menu system with realistic phraseology.

    Extends the generic Menu base class to provide ATC-specific functionality.
    Provides interactive menu for ATC communications with options that
    change based on aircraft state and flight phase.

    Generates realistic radio phraseology dynamically using ATCPhraseology.

    The menu uses a state machine:
    - CLOSED: Menu not visible
    - OPEN: Menu displayed, waiting for selection
    - WAITING_RESPONSE: Pilot message sent, waiting for ATC response

    Examples:
        >>> menu = ATCMenu(tts, queue, message_queue)
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
        self._readback_system: Any = None  # ATCReadbackSystem for Shift+F1 functionality

        # V2 callback for sending text to NLU after TTS plays
        self._v2_text_callback: Any = None

        # Flight context for phraseology generation
        self._flight_context = FlightContext(
            callsign="N12345",
            aircraft_type="cessna172",
            airport_icao="KPAO",
            airport_name="Palo Alto",
            runway="31",
            parking_location="ramp",
            atis_info="Alpha",
            atis_received=False,
            passengers=1,
        )
        self._phraseology: ATCPhraseology | None = None

        logger.info("ATC menu initialized")

    def set_flight_context(
        self,
        callsign: str | None = None,
        aircraft_type: str | None = None,
        airport_icao: str | None = None,
        airport_name: str | None = None,
        runway: str | None = None,
        parking_location: str | None = None,
        atis_info: str | None = None,
        atis_received: bool | None = None,
        ground_freq: str | None = None,
        tower_freq: str | None = None,
        departure_freq: str | None = None,
        passengers: int | None = None,
    ) -> None:
        """Set flight context for phraseology generation.

        Args:
            callsign: Aircraft callsign
            aircraft_type: Aircraft type (e.g., "cessna172")
            airport_icao: Airport ICAO code
            airport_name: Airport name for radio calls
            runway: Active runway
            parking_location: Current parking location
            atis_info: Current ATIS information letter
            atis_received: Whether ATIS has been listened to
            ground_freq: Ground frequency
            tower_freq: Tower frequency
            departure_freq: Departure frequency
            passengers: Number of passengers on board
        """
        if callsign:
            self._flight_context.callsign = callsign
        if aircraft_type:
            self._flight_context.aircraft_type = aircraft_type
        if airport_icao:
            self._flight_context.airport_icao = airport_icao
        if airport_name:
            self._flight_context.airport_name = airport_name
        if runway:
            self._flight_context.runway = runway
        if parking_location:
            self._flight_context.parking_location = parking_location
        if atis_info:
            self._flight_context.atis_info = atis_info
        if atis_received is not None:
            self._flight_context.atis_received = atis_received
        if ground_freq:
            self._flight_context.ground_freq = ground_freq
        if tower_freq:
            self._flight_context.tower_freq = tower_freq
        if departure_freq:
            self._flight_context.departure_freq = departure_freq
        if passengers is not None:
            self._flight_context.passengers = passengers

        # Recreate phraseology with updated context
        self._phraseology = ATCPhraseology(self._flight_context)
        logger.debug(f"Flight context updated: callsign={callsign}, airport={airport_icao}")

    def set_readback_system(self, readback_system: Any) -> None:
        """Set the readback system for Shift+F1 acknowledge functionality.

        Args:
            readback_system: ATCReadbackSystem instance.
        """
        self._readback_system = readback_system
        logger.debug("Readback system connected to ATC menu")

    def set_v2_callback(self, callback: Any) -> None:
        """Set callback for V2 integration (sends text to NLU after TTS).

        Args:
            callback: Function that takes pilot_text string as argument.
        """
        self._v2_text_callback = callback
        logger.debug("V2 callback set for ATC menu")

    def get_phraseology(self) -> ATCPhraseology | None:
        """Get the phraseology generator.

        Returns:
            ATCPhraseology instance or None if not initialized.
        """
        if not self._phraseology:
            self._phraseology = ATCPhraseology(self._flight_context)
        return self._phraseology

    def mark_atis_received(self, atis_letter: str) -> None:
        """Mark ATIS as received with the given information letter.

        Args:
            atis_letter: ATIS information letter (e.g., "Alpha", "Bravo")
        """
        self._flight_context.atis_info = atis_letter
        self._flight_context.atis_received = True
        # Recreate phraseology with updated context
        self._phraseology = ATCPhraseology(self._flight_context)
        logger.info(f"ATIS received: information {atis_letter}")

    def is_atis_received(self) -> bool:
        """Check if ATIS has been received.

        Returns:
            True if ATIS has been listened to.
        """
        return self._flight_context.atis_received

    def get_atis_info(self) -> str:
        """Get current ATIS information letter.

        Returns:
            ATIS information letter (e.g., "Alpha").
        """
        return self._flight_context.atis_info

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

        # Update altitude in flight context
        if context and "altitude_agl" in context:
            self._flight_context.altitude = int(context.get("altitude_agl", 0))

        # Determine flight phase
        self._current_phase = self._determine_flight_phase(self._last_aircraft_state)

        # Ensure phraseology is initialized
        if not self._phraseology:
            self._phraseology = ATCPhraseology(self._flight_context)

        # Get context-specific options
        return self._get_context_options(self._current_phase)

    def _handle_selection(self, option: MenuOption) -> None:
        """Handle selection of an ATC menu option.

        Args:
            option: The selected MenuOption.
        """
        from airborne.core.messaging import Message
        from airborne.plugins.radio.atc_queue import ATCMessage

        # Extract ATC-specific data from option
        data = option.data or {}
        pilot_text_func = data.get("pilot_text_func")
        atc_text_func = data.get("atc_text_func")
        readback_text_func = data.get("readback_text_func")  # Pilot readback
        callback = data.get("callback")

        # Close menu silently (don't speak "menu closed" when selecting option)
        super().close(speak=False)

        # Special handling for ATIS request - uses dynamic TTS
        if data.get("is_atis_request"):
            logger.info("ATIS request - using dynamic TTS")
            # Publish to input.atis_request for radio_plugin to handle
            if self._message_queue:
                self._message_queue.publish(
                    Message(
                        sender="atc_menu",
                        recipients=["*"],
                        topic="input.atis_request",
                        data={},
                    )
                )
            # Execute callback if provided
            if callback:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Error in option callback: {e}")
            return

        # Generate dynamic pilot and ATC messages
        pilot_text = ""
        atc_text = ""
        readback_text = ""

        if pilot_text_func and self._phraseology:
            try:
                pilot_text = pilot_text_func(self._phraseology)
            except Exception as e:
                logger.error(f"Error generating pilot text: {e}")
                pilot_text = "Request acknowledged"

        if atc_text_func and self._phraseology:
            try:
                atc_text = atc_text_func(self._phraseology)
            except Exception as e:
                logger.error(f"Error generating ATC text: {e}")
                atc_text = "Roger"

        if readback_text_func and self._phraseology:
            try:
                readback_text = readback_text_func(self._phraseology)
            except Exception as e:
                logger.error(f"Error generating readback text: {e}")
                readback_text = ""

        # Handle CTAF announcements (no ATC response expected)
        if pilot_text and not atc_text:
            self._waiting_response = True

            # Create callback that handles V2 and completion
            def ctaf_callback() -> None:
                # Send to V2 NLU if callback is set
                if self._v2_text_callback:
                    try:
                        self._v2_text_callback(pilot_text)
                    except Exception as e:
                        logger.error(f"Error in V2 callback: {e}")
                self._on_atc_response_complete()

            pilot_msg = ATCMessage(
                message_key=pilot_text,
                sender="PILOT",
                priority=0,
                delay_after=0.5,
                callback=ctaf_callback,
            )
            self._atc_queue.enqueue(pilot_msg)
            logger.info(f"Enqueued CTAF: PILOT='{pilot_text[:50]}...'")
            return

        if not pilot_text or not atc_text:
            logger.warning("Missing pilot or ATC text, skipping transmission")
            return

        self._waiting_response = True

        # Create callback for after pilot message plays - sends to V2 NLU
        def pilot_callback() -> None:
            if self._v2_text_callback:
                try:
                    self._v2_text_callback(pilot_text)
                except Exception as e:
                    logger.error(f"Error in V2 callback: {e}")

        # Enqueue pilot message with dynamic text
        pilot_msg = ATCMessage(
            message_key=pilot_text,  # Dynamic text instead of key
            sender="PILOT",
            priority=0,
            delay_after=2.0,
            callback=pilot_callback,
        )
        self._atc_queue.enqueue(pilot_msg)

        # Enqueue ATC response with dynamic text
        # Record ATC message for Shift+F1 readback functionality
        atc_msg = ATCMessage(
            message_key=atc_text,  # Dynamic text instead of key
            sender="ATC",
            priority=0,
            delay_after=0.0,  # No auto-delay - user uses Shift+F1 to readback
            callback=self._on_atc_response_complete,
        )
        self._atc_queue.enqueue(atc_msg)

        # Record ATC instruction for Shift+F1 acknowledge and Option+F1 repeat
        if self._readback_system and readback_text:
            # Store the readback text along with the ATC message for later use
            self._readback_system.record_atc_instruction(
                message_key=atc_text,
                full_text=atc_text,
                readback_text=readback_text,  # Store the readback for Shift+F1
            )
            logger.info(
                f"Enqueued ATC exchange (use Shift+F1 to readback): "
                f"PILOT='{pilot_text[:40]}...' ATC='{atc_text[:40]}...'"
            )
        else:
            logger.info(
                f"Enqueued ATC exchange: PILOT='{pilot_text[:50]}...' ATC='{atc_text[:50]}...'"
            )

        # Execute callback if provided
        if callback:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in option callback: {e}")

    def _get_menu_opened_message(self) -> str:
        """Get translated text for menu opened.

        Returns:
            Translated menu opened message.
        """
        return t("atc_menu.opened")

    def _get_menu_closed_message(self) -> str:
        """Get translated text for menu closed.

        Returns:
            Translated menu closed message.
        """
        return t("atc_menu.closed")

    def _get_invalid_option_message(self) -> str:
        """Get translated text for invalid option.

        Returns:
            Translated invalid option message.
        """
        return t("atc_menu.invalid_option")

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
        options: list[MenuOption] = []

        if phase == FlightPhase.ON_GROUND_ENGINE_OFF:
            # Check if ATIS has been received for startup request
            atis_received = self._flight_context.atis_received

            options = [
                MenuOption(
                    key="1",
                    label=t("atc_menu.listen_atis"),
                    message_key=t("atc_menu.listen_atis"),
                    data={"is_atis_request": True},
                ),
                MenuOption(
                    key="2",
                    label=t("atc_menu.radio_check"),
                    message_key=t("atc_menu.radio_check"),
                    data={
                        "pilot_text_func": lambda p: p.pilot_radio_check(),
                        "atc_text_func": lambda p: p.atc_radio_check_response(),
                    },
                ),
            ]

            # Add startup option - depends on ATIS status
            if atis_received:
                options.append(
                    MenuOption(
                        key="3",
                        label=t("atc_menu.request_startup"),
                        message_key=t("atc_menu.request_startup"),
                        data={
                            "pilot_text_func": lambda p: p.pilot_request_startup(),
                            "atc_text_func": lambda p: p.atc_startup_approved(),
                            "readback_text_func": lambda p: p.pilot_readback_startup(),
                        },
                    )
                )
            else:
                # Startup without ATIS - ATC will ask for information
                options.append(
                    MenuOption(
                        key="3",
                        label=t("atc_menu.request_startup_no_atis"),
                        message_key=t("atc_menu.request_startup_no_atis"),
                        data={
                            "pilot_text_func": lambda p: p.pilot_request_startup_no_atis(),
                            "atc_text_func": lambda p: p.atc_startup_denied_no_atis(),
                        },
                    )
                )

        elif phase == FlightPhase.ON_GROUND_ENGINE_RUNNING:
            options = [
                MenuOption(
                    key="1",
                    label=t("atc_menu.listen_atis"),
                    message_key=t("atc_menu.listen_atis"),
                    data={"is_atis_request": True},
                ),
                MenuOption(
                    key="2",
                    label=t("atc_menu.request_taxi"),
                    message_key=t("atc_menu.request_taxi"),
                    data={
                        "pilot_text_func": lambda p: p.pilot_request_taxi(),
                        "atc_text_func": lambda p: p.atc_taxi_clearance("Alpha"),
                        "readback_text_func": lambda p: p.pilot_readback_taxi("Alpha"),
                    },
                ),
                MenuOption(
                    key="3",
                    label=t("atc_menu.announce_taxi"),
                    message_key=t("atc_menu.announce_taxi"),
                    data={
                        "pilot_text_func": lambda p: (
                            f"{p.context.airport_name} Traffic, "
                            f"{p._full_pilot_callsign()}, "
                            f"taxiing to runway {p._format_runway(p.context.runway)}, "
                            f"{p.context.airport_name}"
                        ),
                        "atc_text_func": lambda p: "",  # No ATC response at uncontrolled
                    },
                ),
            ]

        elif phase == FlightPhase.HOLDING_SHORT:
            options = [
                MenuOption(
                    key="1",
                    label=t("atc_menu.ready_departure"),
                    message_key=t("atc_menu.ready_departure"),
                    data={
                        "pilot_text_func": lambda p: p.pilot_ready_for_departure(),
                        "atc_text_func": lambda p: p.atc_cleared_takeoff(),
                        "readback_text_func": lambda p: p.pilot_readback_takeoff(),
                    },
                ),
                MenuOption(
                    key="2",
                    label=t("atc_menu.request_takeoff"),
                    message_key=t("atc_menu.request_takeoff"),
                    data={
                        "pilot_text_func": lambda p: p.pilot_request_takeoff(),
                        "atc_text_func": lambda p: p.atc_cleared_takeoff(),
                        "readback_text_func": lambda p: p.pilot_readback_takeoff(),
                    },
                ),
                MenuOption(
                    key="3",
                    label=t("atc_menu.announce_departure"),
                    message_key=t("atc_menu.announce_departure"),
                    data={
                        "pilot_text_func": lambda p: (
                            f"{p.context.airport_name} Traffic, "
                            f"{p._full_pilot_callsign()}, "
                            f"departing runway {p._format_runway(p.context.runway)}, "
                            f"straight out departure, "
                            f"{p.context.airport_name}"
                        ),
                        "atc_text_func": lambda p: "",  # No response at CTAF
                    },
                ),
            ]

        elif phase == FlightPhase.ON_RUNWAY:
            options = [
                MenuOption(
                    key="1",
                    label=t("atc_menu.report_ready"),
                    message_key=t("atc_menu.report_ready"),
                    data={
                        "pilot_text_func": lambda p: p.pilot_request_takeoff(),
                        "atc_text_func": lambda p: p.atc_cleared_takeoff(),
                    },
                ),
                MenuOption(
                    key="2",
                    label=t("atc_menu.announce_takeoff"),
                    message_key=t("atc_menu.announce_takeoff"),
                    data={
                        "pilot_text_func": lambda p: (
                            f"{p.context.airport_name} Traffic, "
                            f"{p._abbreviated_callsign()}, "
                            f"rolling runway {p._format_runway(p.context.runway)}, "
                            f"{p.context.airport_name}"
                        ),
                        "atc_text_func": lambda p: "",  # No response
                    },
                ),
            ]

        elif phase == FlightPhase.AIRBORNE_DEPARTURE:
            options = [
                MenuOption(
                    key="1",
                    label=t("atc_menu.checkin_departure"),
                    message_key=t("atc_menu.checkin_departure"),
                    data={
                        "pilot_text_func": lambda p: p.pilot_departure_checkin(),
                        "atc_text_func": lambda p: p.atc_radar_contact(),
                    },
                ),
                MenuOption(
                    key="2",
                    label=t("atc_menu.request_freq_change"),
                    message_key=t("atc_menu.request_freq_change"),
                    data={
                        "pilot_text_func": lambda p: (
                            f"{p.context.airport_name} Tower, "
                            f"{p._abbreviated_callsign()}, "
                            f"request frequency change"
                        ),
                        "atc_text_func": lambda p: p.atc_frequency_change_approved(),
                    },
                ),
                MenuOption(
                    key="3",
                    label=t("atc_menu.announce_departure"),
                    message_key=t("atc_menu.announce_departure"),
                    data={
                        "pilot_text_func": lambda p: (
                            f"{p.context.airport_name} Traffic, "
                            f"{p._abbreviated_callsign()}, "
                            f"departing to the north, "
                            f"climbing through {p._format_altitude(p.context.altitude)}, "
                            f"{p.context.airport_name}"
                        ),
                        "atc_text_func": lambda p: "",  # No response
                    },
                ),
            ]

        elif phase == FlightPhase.AIRBORNE_CRUISE:
            options = [
                MenuOption(
                    key="1",
                    label=t("atc_menu.request_flight_following"),
                    message_key=t("atc_menu.request_flight_following"),
                    data={
                        "pilot_text_func": lambda p: (
                            f"NorCal Approach, {p._full_pilot_callsign()}, request flight following"
                        ),
                        "atc_text_func": lambda p: (
                            f"{p._abbreviated_callsign()}, "
                            f"NorCal Approach, "
                            f"squawk {p._format_number(4521)}, "
                            f"say altitude and destination"
                        ),
                    },
                ),
                MenuOption(
                    key="2",
                    label=t("atc_menu.position_report"),
                    message_key=t("atc_menu.position_report"),
                    data={
                        "pilot_text_func": lambda p: (
                            f"NorCal Approach, "
                            f"{p._abbreviated_callsign()}, "
                            f"level {p._format_altitude(p.context.altitude)}"
                        ),
                        "atc_text_func": lambda p: p.atc_roger(),
                    },
                ),
                MenuOption(
                    key="3",
                    label=t("atc_menu.request_higher"),
                    message_key=t("atc_menu.request_higher"),
                    data={
                        "pilot_text_func": lambda p: (
                            f"NorCal Approach, {p._abbreviated_callsign()}, request higher"
                        ),
                        "atc_text_func": lambda p: (
                            f"{p._abbreviated_callsign()}, "
                            f"climb and maintain {p._format_altitude(p.context.altitude + 2000)}"
                        ),
                    },
                ),
            ]

        # Filter out options with empty ATC responses (CTAF announcements)
        # These are valid but don't need a response
        return options

    def _on_atc_response_complete(self) -> None:
        """Callback when ATC response completes."""
        if self._waiting_response:
            self._waiting_response = False
            logger.debug("ATC response complete, menu returned to closed state")

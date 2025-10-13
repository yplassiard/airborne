"""Aviation phraseology system for ATC communications.

Provides template-based generation of realistic ICAO standard phraseology
for pilot-ATC communications.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class PhraseContext:
    """Context information for phrase generation.

    Attributes:
        callsign: Aircraft callsign (e.g., "Cessna 123AB")
        airport: Airport name (e.g., "Palo Alto")
        runway: Runway identifier (e.g., "31")
        taxiway: Taxiway identifier (e.g., "Alpha")
        altitude: Current altitude in feet
        heading: Current heading in degrees
        location: Current location (e.g., "parking", "gate 5")
        atis: Current ATIS information letter (e.g., "Bravo")
        squawk: Transponder code (e.g., "1200")
    """

    callsign: str = ""
    airport: str = ""
    runway: str = ""
    taxiway: str = ""
    altitude: int = 0
    heading: int = 0
    location: str = ""
    atis: str = ""
    squawk: str = "1200"


# Pilot phraseology templates
PILOT_PHRASES = {
    # Ground operations
    "taxi_request": "{airport} Ground, {callsign}, at {location} with information {atis}, request taxi",
    "taxi_ready": "{airport} Ground, {callsign}, ready to taxi",
    "pushback_request": "{airport} Ground, {callsign}, request pushback",
    "taxi_complete": "{airport} Ground, {callsign}, holding short of runway {runway}",
    # Takeoff
    "takeoff_ready": "{airport} Tower, {callsign}, ready for departure runway {runway}",
    "takeoff_request": "{airport} Tower, {callsign}, request takeoff runway {runway}",
    "departure_report": "{airport} Tower, {callsign}, airborne",
    # Landing
    "inbound_report": "{airport} Tower, {callsign}, {altitude} feet, inbound for landing",
    "pattern_entry": "{airport} Tower, {callsign}, entering {pattern} for runway {runway}",
    "final_approach": "{airport} Tower, {callsign}, final runway {runway}",
    "go_around": "{airport} Tower, {callsign}, going around",
    "landing_cleared": "{airport} Tower, {callsign}, clear of runway {runway}",
    # Radio check
    "radio_check": "{airport}, {callsign}, radio check",
    # Position report
    "position_report": "{airport}, {callsign}, {altitude} feet, heading {heading}",
}

# ATC phraseology templates
ATC_PHRASES = {
    # Ground clearances
    "taxi_clearance": "{callsign}, {airport} Ground, taxi to runway {runway} via {taxiway}",
    "taxi_hold_short": "{callsign}, taxi via {taxiway}, hold short of runway {runway}",
    "pushback_approved": "{callsign}, pushback approved, facing {direction}",
    "cross_runway": "{callsign}, cross runway {runway}",
    "contact_tower": "{callsign}, contact Tower on {frequency}",
    # Tower clearances
    "takeoff_clearance": "{callsign}, runway {runway}, cleared for takeoff",
    "takeoff_hold": "{callsign}, runway {runway}, line up and wait",
    "departure_clearance": "{callsign}, fly runway heading, maintain {altitude}, departure frequency {frequency}",
    "landing_clearance": "{callsign}, runway {runway}, cleared to land",
    "pattern_clearance": "{callsign}, cleared {pattern} runway {runway}",
    "go_around_instruction": "{callsign}, go around",
    "extend_downwind": "{callsign}, extend downwind, I'll call your base",
    "turn_base": "{callsign}, turn base",
    "report_final": "{callsign}, report final",
    "contact_ground": "{callsign}, contact Ground on {frequency}",
    # Radio responses
    "roger": "{callsign}, roger",
    "affirm": "{callsign}, affirmative",
    "negative": "{callsign}, negative",
    "standby": "{callsign}, standby",
    "say_again": "{callsign}, say again",
    "radio_check_ok": "{callsign}, loud and clear",
    # Traffic advisories
    "traffic_advisory": "{callsign}, traffic, {distance} o'clock, {range} miles, {type}, {altitude}",
    "traffic_in_sight": "{callsign}, traffic in sight",
    # Squawk codes
    "squawk_code": "{callsign}, squawk {squawk}",
    "squawk_ident": "{callsign}, squawk ident",
}


class PhraseMaker:
    """Generates aviation phraseology from templates.

    Uses context substitution to create realistic ATC communications
    following ICAO standards.
    """

    def __init__(self) -> None:
        """Initialize phrase maker with standard templates."""
        self.pilot_phrases = PILOT_PHRASES
        self.atc_phrases = ATC_PHRASES

    def make_pilot_phrase(self, phrase_type: str, context: PhraseContext) -> str:
        """Generate pilot phraseology.

        Args:
            phrase_type: Type of phrase (e.g., "taxi_request")
            context: Context with values for template substitution

        Returns:
            Formatted phraseology string

        Examples:
            >>> pm = PhraseMaker()
            >>> ctx = PhraseContext(
            ...     callsign="Cessna 123AB",
            ...     airport="Palo Alto",
            ...     location="parking",
            ...     atis="Bravo"
            ... )
            >>> pm.make_pilot_phrase("taxi_request", ctx)
            'Palo Alto Ground, Cessna 123AB, at parking with information Bravo, request taxi'
        """
        if phrase_type not in self.pilot_phrases:
            raise ValueError(f"Unknown pilot phrase type: {phrase_type}")

        template = self.pilot_phrases[phrase_type]
        return self._substitute(template, context)

    def make_atc_phrase(self, phrase_type: str, context: PhraseContext, **kwargs: Any) -> str:
        """Generate ATC phraseology.

        Args:
            phrase_type: Type of phrase (e.g., "taxi_clearance")
            context: Context with values for template substitution
            **kwargs: Additional keyword arguments for substitution

        Returns:
            Formatted phraseology string

        Examples:
            >>> pm = PhraseMaker()
            >>> ctx = PhraseContext(
            ...     callsign="Cessna 123AB",
            ...     airport="Palo Alto",
            ...     runway="31",
            ...     taxiway="Alpha"
            ... )
            >>> pm.make_atc_phrase("taxi_clearance", ctx)
            'Cessna 123AB, Palo Alto Ground, taxi to runway 31 via Alpha'
        """
        if phrase_type not in self.atc_phrases:
            raise ValueError(f"Unknown ATC phrase type: {phrase_type}")

        template = self.atc_phrases[phrase_type]
        return self._substitute(template, context, **kwargs)

    def _substitute(self, template: str, context: PhraseContext, **kwargs: Any) -> str:
        """Substitute template placeholders with context values.

        Args:
            template: Template string with {placeholder} markers
            context: Context object with attribute values
            **kwargs: Additional keyword arguments override context

        Returns:
            Template with placeholders replaced
        """
        # Build substitution dict from context
        values = {
            "callsign": context.callsign,
            "airport": context.airport,
            "runway": context.runway,
            "taxiway": context.taxiway,
            "altitude": context.altitude,
            "heading": context.heading,
            "location": context.location,
            "atis": context.atis,
            "squawk": context.squawk,
        }

        # Override with any kwargs
        values.update(kwargs)

        # Format template
        try:
            return template.format(**values)
        except KeyError as e:
            raise ValueError(f"Missing required context value: {e}")

    def add_pilot_phrase(self, phrase_type: str, template: str) -> None:
        """Add a custom pilot phrase template.

        Args:
            phrase_type: Identifier for the phrase
            template: Template string with {placeholder} markers

        Examples:
            >>> pm = PhraseMaker()
            >>> pm.add_pilot_phrase("custom", "{callsign}, custom phrase")
        """
        self.pilot_phrases[phrase_type] = template

    def add_atc_phrase(self, phrase_type: str, template: str) -> None:
        """Add a custom ATC phrase template.

        Args:
            phrase_type: Identifier for the phrase
            template: Template string with {placeholder} markers

        Examples:
            >>> pm = PhraseMaker()
            >>> pm.add_atc_phrase("custom", "{callsign}, custom clearance")
        """
        self.atc_phrases[phrase_type] = template

    def get_available_pilot_phrases(self) -> list[str]:
        """Get list of available pilot phrase types.

        Returns:
            List of phrase type identifiers

        Examples:
            >>> pm = PhraseMaker()
            >>> "taxi_request" in pm.get_available_pilot_phrases()
            True
        """
        return list(self.pilot_phrases.keys())

    def get_available_atc_phrases(self) -> list[str]:
        """Get list of available ATC phrase types.

        Returns:
            List of phrase type identifiers

        Examples:
            >>> pm = PhraseMaker()
            >>> "taxi_clearance" in pm.get_available_atc_phrases()
            True
        """
        return list(self.atc_phrases.keys())

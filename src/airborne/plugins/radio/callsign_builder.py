"""Callsign builder for aviation phonetic alphabet.

Converts callsigns and numbers to spoken text using the ICAO phonetic alphabet
and aviation number pronunciation.

Examples:
    >>> builder = CallsignBuilder()
    >>> builder.build_callsign("N123AB")
    'November One Two Three Alpha Bravo'
"""


class CallsignBuilder:
    """Build phonetic callsigns from registration numbers.

    Converts aircraft callsigns into spoken text that can be passed to the
    TTS cache service for audio generation.

    Examples:
        >>> builder = CallsignBuilder()
        >>> text = builder.build_callsign("N123AB")
        >>> # Returns "November One Two Three Alpha Bravo"
    """

    # ICAO phonetic alphabet mapping
    PHONETIC_MAP = {
        "A": "Alpha",
        "B": "Bravo",
        "C": "Charlie",
        "D": "Delta",
        "E": "Echo",
        "F": "Foxtrot",
        "G": "Golf",
        "H": "Hotel",
        "I": "India",
        "J": "Juliett",  # ICAO spelling with two T's
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

    # Digit pronunciation
    DIGIT_WORDS = {
        "0": "Zero",
        "1": "One",
        "2": "Two",
        "3": "Three",
        "4": "Four",
        "5": "Five",
        "6": "Six",
        "7": "Seven",
        "8": "Eight",
        "9": "Niner",  # Aviation pronunciation
    }

    def __init__(self) -> None:
        """Initialize callsign builder."""
        pass

    def build_callsign(self, callsign: str) -> str:
        """Convert callsign to spoken text.

        Args:
            callsign: Aircraft callsign (e.g., "N123AB", "C-GABC")

        Returns:
            Spoken text for the callsign.

        Examples:
            >>> builder.build_callsign("N123AB")
            'November One Two Three Alpha Bravo'
        """
        words = []
        callsign = callsign.upper().strip()

        for char in callsign:
            if char in self.PHONETIC_MAP:
                words.append(self.PHONETIC_MAP[char])
            elif char in self.DIGIT_WORDS:
                words.append(self.DIGIT_WORDS[char])
            # Skip spaces, hyphens, and other characters

        return " ".join(words)

    def build_frequency(self, frequency: float) -> str:
        """Convert frequency to spoken text.

        Args:
            frequency: Frequency in MHz (e.g., 121.5, 118.875)

        Returns:
            Spoken text for the frequency.

        Examples:
            >>> builder.build_frequency(121.5)
            'One Two One decimal Five'
            >>> builder.build_frequency(118.875)
            'One One Eight decimal Eight Seven Five'
        """
        # Split into integer and decimal parts
        freq_str = f"{frequency:.3f}"
        parts = freq_str.split(".")
        integer_part = parts[0]
        decimal_part = parts[1].rstrip("0") if len(parts) > 1 else ""

        words = []

        # Build integer part digit by digit
        for digit in integer_part:
            if digit in self.DIGIT_WORDS:
                words.append(self.DIGIT_WORDS[digit])

        # Add decimal point and decimal digits
        if decimal_part:
            words.append("decimal")
            for digit in decimal_part:
                if digit in self.DIGIT_WORDS:
                    words.append(self.DIGIT_WORDS[digit])

        return " ".join(words)

    def build_altitude(self, altitude_ft: int) -> str:
        """Convert altitude to spoken text.

        Args:
            altitude_ft: Altitude in feet

        Returns:
            Spoken text for the altitude.

        Examples:
            >>> builder.build_altitude(3500)
            'Three Five Zero Zero'
            >>> builder.build_altitude(10000)
            'One Zero Zero Zero Zero'
        """
        words = []
        alt_str = str(altitude_ft)

        for digit in alt_str:
            if digit in self.DIGIT_WORDS:
                words.append(self.DIGIT_WORDS[digit])

        return " ".join(words)

    def build_heading(self, heading: int) -> str:
        """Convert heading to spoken text.

        Args:
            heading: Heading in degrees (0-360)

        Returns:
            Spoken text for the heading.

        Examples:
            >>> builder.build_heading(270)
            'Two Seven Zero'
            >>> builder.build_heading(90)
            'Zero Niner Zero'
        """
        words = []
        # Pad to 3 digits
        heading_str = f"{heading:03d}"

        for digit in heading_str:
            if digit in self.DIGIT_WORDS:
                words.append(self.DIGIT_WORDS[digit])

        return " ".join(words)

    def build_runway(self, runway: str) -> str:
        """Convert runway identifier to spoken text.

        Args:
            runway: Runway identifier (e.g., "27L", "09R", "36")

        Returns:
            Spoken text for the runway.

        Examples:
            >>> builder.build_runway("27L")
            'Two Seven Left'
            >>> builder.build_runway("09R")
            'Zero Niner Right'
        """
        words = []
        runway = runway.upper().strip()

        for char in runway:
            if char in self.DIGIT_WORDS:
                words.append(self.DIGIT_WORDS[char])
            elif char == "L":
                words.append("Left")
            elif char == "R":
                words.append("Right")
            elif char == "C":
                words.append("Center")

        return " ".join(words)

    def build_transponder(self, code: str) -> str:
        """Convert transponder code to spoken text.

        Args:
            code: 4-digit transponder code (e.g., "7000", "1200")

        Returns:
            Spoken text for the transponder code.

        Examples:
            >>> builder.build_transponder("7000")
            'Seven Zero Zero Zero'
        """
        words = []
        code = code.strip()

        for digit in code:
            if digit in self.DIGIT_WORDS:
                words.append(self.DIGIT_WORDS[digit])

        return " ".join(words)

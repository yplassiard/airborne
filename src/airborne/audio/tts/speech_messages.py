"""Speech message key constants.

This module defines constants for all speech messages used in the application.
These keys map to audio files defined in config/speech_{language}.yaml.

Usage:
    from airborne.audio.tts.speech_messages import SpeechMessages
    from airborne.audio.tts.speech_messages import MSG_STARTUP

    tts.speak(SpeechMessages.MSG_STARTUP)
    # or
    tts.speak(MSG_STARTUP)
"""


class SpeechMessages:
    """Speech message key constants."""

    # System messages
    MSG_STARTUP = "MSG_STARTUP"
    MSG_READY = "MSG_READY"
    MSG_ERROR = "MSG_ERROR"
    MSG_ERROR_MESSAGE = "MSG_ERROR_MESSAGE"
    MSG_NOT_FOUND = "MSG_NOT_FOUND"

    # Action confirmations
    MSG_GEAR_DOWN = "MSG_GEAR_DOWN"
    MSG_GEAR_UP = "MSG_GEAR_UP"
    MSG_FLAPS_EXTENDING = "MSG_FLAPS_EXTENDING"
    MSG_FLAPS_RETRACTING = "MSG_FLAPS_RETRACTING"
    MSG_THROTTLE_INCREASED = "MSG_THROTTLE_INCREASED"
    MSG_THROTTLE_DECREASED = "MSG_THROTTLE_DECREASED"
    MSG_FULL_THROTTLE = "MSG_FULL_THROTTLE"
    MSG_THROTTLE_IDLE = "MSG_THROTTLE_IDLE"
    MSG_BRAKES_ON = "MSG_BRAKES_ON"
    MSG_PAUSED = "MSG_PAUSED"
    MSG_NEXT = "MSG_NEXT"

    # Vertical speed
    MSG_LEVEL_FLIGHT = "MSG_LEVEL_FLIGHT"

    # Attitude
    MSG_LEVEL_ATTITUDE = "MSG_LEVEL_ATTITUDE"

    # Individual digits
    MSG_DIGIT_0 = "MSG_DIGIT_0"
    MSG_DIGIT_1 = "MSG_DIGIT_1"
    MSG_DIGIT_2 = "MSG_DIGIT_2"
    MSG_DIGIT_3 = "MSG_DIGIT_3"
    MSG_DIGIT_4 = "MSG_DIGIT_4"
    MSG_DIGIT_5 = "MSG_DIGIT_5"
    MSG_DIGIT_6 = "MSG_DIGIT_6"
    MSG_DIGIT_7 = "MSG_DIGIT_7"
    MSG_DIGIT_8 = "MSG_DIGIT_8"
    MSG_DIGIT_9 = "MSG_DIGIT_9"

    # Common words
    MSG_WORD_HEADING = "MSG_WORD_HEADING"
    MSG_WORD_FLIGHT_LEVEL = "MSG_WORD_FLIGHT_LEVEL"
    MSG_WORD_FEET = "MSG_WORD_FEET"
    MSG_WORD_KNOTS = "MSG_WORD_KNOTS"

    @staticmethod
    def _digits_to_keys(number: int, num_digits: int = 0) -> list[str]:
        """Convert number to list of digit message keys.

        Args:
            number: Number to convert.
            num_digits: Minimum number of digits (pad with zeros).

        Returns:
            List of MSG_DIGIT_X keys.
        """
        # Format with leading zeros if needed
        num_str = f"{number:0{num_digits}d}" if num_digits > 0 else str(number)

        # Map digit 9 to use DIGIT_9 (which will be "niner")
        return [f"MSG_DIGIT_{d}" for d in num_str]

    @staticmethod
    def airspeed(knots: int) -> str | list[str]:
        """Get message key(s) for airspeed readout.

        Args:
            knots: Airspeed in knots (0-300).

        Returns:
            Message key or list of keys to assemble the message.
        """
        # Round to nearest 5 knots
        rounded = round(knots / 5) * 5
        rounded = max(0, min(300, rounded))

        # Use pre-recorded for common speeds
        if rounded in [0, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180]:
            return f"MSG_AIRSPEED_{rounded}"

        # Assemble from digits + "knots"
        return SpeechMessages._digits_to_keys(rounded) + [SpeechMessages.MSG_WORD_KNOTS]

    @staticmethod
    def altitude(feet: int) -> str:
        """Get message key for altitude readout.

        Args:
            feet: Altitude in feet.

        Returns:
            Message key (e.g., "MSG_ALTITUDE_5000" or "MSG_FL_180").
        """
        # Use flight levels for altitudes above 18,000 feet
        if feet >= 18000:
            # Convert to flight level (round to nearest 1000 feet, then divide by 100)
            fl = round(feet / 1000) * 10
            fl = max(10, min(600, fl))  # Clamp to FL010-FL600
            return f"MSG_FL_{fl}"

        # Define available altitude levels for lower altitudes
        levels = [0, 100, 200, 300, 400, 500, 1000, 1500, 2000, 2500, 3000,
                  4000, 5000, 6000, 7000, 8000, 9000, 10000, 12000, 15000, 20000]

        # Find closest level
        closest = min(levels, key=lambda x: abs(x - feet))
        return f"MSG_ALTITUDE_{closest}"

    @staticmethod
    def heading(degrees: int) -> list[str]:
        """Get message keys for heading readout.

        Args:
            degrees: Heading in degrees (0-359).

        Returns:
            List of message keys to assemble heading (e.g., ["MSG_WORD_HEADING", "MSG_DIGIT_0", "MSG_DIGIT_9", "MSG_DIGIT_0"]).
        """
        # Normalize to 0-359
        degrees = degrees % 360

        # Assemble: "heading" + 3 digits
        return [SpeechMessages.MSG_WORD_HEADING] + SpeechMessages._digits_to_keys(degrees, 3)

    @staticmethod
    def vertical_speed(fpm: int) -> str:
        """Get message key for vertical speed readout.

        Args:
            fpm: Vertical speed in feet per minute.

        Returns:
            Message key (e.g., "MSG_CLIMBING_500").
        """
        if abs(fpm) < 50:
            return "MSG_LEVEL_FLIGHT"

        # Define available VS levels
        levels = [100, 200, 300, 500, 1000, 1500, 2000]

        # Find closest level
        abs_fpm = abs(fpm)
        closest = min(levels, key=lambda x: abs(x - abs_fpm))

        direction = "CLIMBING" if fpm > 0 else "DESCENDING"
        return f"MSG_{direction}_{closest}"

    @staticmethod
    def pitch(degrees: int) -> str:
        """Get message key for pitch attitude readout.

        Args:
            degrees: Pitch in degrees (negative = down, positive = up).

        Returns:
            Message key (e.g., "MSG_PITCH_10_UP").
        """
        if abs(degrees) < 3:
            return "MSG_LEVEL_ATTITUDE"

        # Define available pitch levels
        levels = [5, 10, 15, 20, 30, 45]

        abs_pitch = abs(degrees)
        closest = min(levels, key=lambda x: abs(x - abs_pitch))

        direction = "UP" if degrees > 0 else "DOWN"
        return f"MSG_PITCH_{closest}_{direction}"

    @staticmethod
    def bank(degrees: int) -> str:
        """Get message key for bank attitude readout.

        Args:
            degrees: Bank in degrees (negative = left, positive = right).

        Returns:
            Message key (e.g., "MSG_BANK_15_LEFT").
        """
        if abs(degrees) < 3:
            return "MSG_LEVEL_ATTITUDE"

        # Define available bank levels
        levels = [5, 10, 15, 20, 30, 45]

        abs_bank = abs(degrees)
        closest = min(levels, key=lambda x: abs(x - abs_bank))

        direction = "LEFT" if degrees < 0 else "RIGHT"
        return f"MSG_BANK_{closest}_{direction}"

    @staticmethod
    def flight_level(fl: int) -> list[str]:
        """Get message keys for flight level readout.

        Args:
            fl: Flight level (e.g., 180 for FL180 = 18,000 feet).

        Returns:
            List of message keys (e.g., ["MSG_WORD_FLIGHT_LEVEL", "MSG_DIGIT_1", "MSG_DIGIT_8", "MSG_DIGIT_0"]).
        """
        # Round to nearest 10
        fl_rounded = round(fl / 10) * 10
        fl_rounded = max(10, min(600, fl_rounded))  # Clamp to FL010-FL600

        # Assemble: "flight level" + 3 digits
        return [SpeechMessages.MSG_WORD_FLIGHT_LEVEL] + SpeechMessages._digits_to_keys(fl_rounded, 3)


# Export commonly used constants at module level for convenience
MSG_STARTUP = SpeechMessages.MSG_STARTUP
MSG_READY = SpeechMessages.MSG_READY
MSG_ERROR = SpeechMessages.MSG_ERROR
MSG_ERROR_MESSAGE = SpeechMessages.MSG_ERROR_MESSAGE
MSG_NOT_FOUND = SpeechMessages.MSG_NOT_FOUND
MSG_GEAR_DOWN = SpeechMessages.MSG_GEAR_DOWN
MSG_GEAR_UP = SpeechMessages.MSG_GEAR_UP
MSG_FLAPS_EXTENDING = SpeechMessages.MSG_FLAPS_EXTENDING
MSG_FLAPS_RETRACTING = SpeechMessages.MSG_FLAPS_RETRACTING
MSG_THROTTLE_INCREASED = SpeechMessages.MSG_THROTTLE_INCREASED
MSG_THROTTLE_DECREASED = SpeechMessages.MSG_THROTTLE_DECREASED
MSG_FULL_THROTTLE = SpeechMessages.MSG_FULL_THROTTLE
MSG_THROTTLE_IDLE = SpeechMessages.MSG_THROTTLE_IDLE
MSG_BRAKES_ON = SpeechMessages.MSG_BRAKES_ON
MSG_PAUSED = SpeechMessages.MSG_PAUSED
MSG_NEXT = SpeechMessages.MSG_NEXT
MSG_LEVEL_FLIGHT = SpeechMessages.MSG_LEVEL_FLIGHT
MSG_LEVEL_ATTITUDE = SpeechMessages.MSG_LEVEL_ATTITUDE

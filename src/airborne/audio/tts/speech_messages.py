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

    # Engine instruments
    MSG_ENGINE_STOPPED = "MSG_ENGINE_STOPPED"
    MSG_WORD_ENGINE_RPM = "MSG_WORD_ENGINE_RPM"
    MSG_WORD_MANIFOLD_PRESSURE = "MSG_WORD_MANIFOLD_PRESSURE"
    MSG_WORD_INCHES = "MSG_WORD_INCHES"
    MSG_WORD_OIL_PRESSURE = "MSG_WORD_OIL_PRESSURE"
    MSG_WORD_PSI = "MSG_WORD_PSI"
    MSG_WORD_OIL_TEMPERATURE = "MSG_WORD_OIL_TEMPERATURE"
    MSG_WORD_DEGREES = "MSG_WORD_DEGREES"
    MSG_WORD_FUEL_FLOW = "MSG_WORD_FUEL_FLOW"
    MSG_WORD_GALLONS_PER_HOUR = "MSG_WORD_GALLONS_PER_HOUR"

    # Electrical instruments
    MSG_WORD_BATTERY = "MSG_WORD_BATTERY"
    MSG_WORD_VOLTS = "MSG_WORD_VOLTS"
    MSG_WORD_PERCENT = "MSG_WORD_PERCENT"
    MSG_BATTERY_CHARGING = "MSG_BATTERY_CHARGING"
    MSG_BATTERY_DISCHARGING = "MSG_BATTERY_DISCHARGING"
    MSG_BATTERY_STABLE = "MSG_BATTERY_STABLE"
    MSG_WORD_AT = "MSG_WORD_AT"
    MSG_WORD_AMPS = "MSG_WORD_AMPS"
    MSG_WORD_ALTERNATOR_OUTPUT = "MSG_WORD_ALTERNATOR_OUTPUT"

    # Fuel instruments
    MSG_WORD_FUEL_QUANTITY = "MSG_WORD_FUEL_QUANTITY"
    MSG_WORD_GALLONS = "MSG_WORD_GALLONS"
    MSG_WORD_FUEL_REMAINING = "MSG_WORD_FUEL_REMAINING"
    MSG_WORD_HOURS = "MSG_WORD_HOURS"
    MSG_WORD_MINUTES = "MSG_WORD_MINUTES"

    # Panel navigation
    MSG_PANEL_INSTRUMENT_PANEL = "MSG_PANEL_INSTRUMENT_PANEL"
    MSG_PANEL_PEDESTAL = "MSG_PANEL_PEDESTAL"
    MSG_PANEL_ENGINE_CONTROLS = "MSG_PANEL_ENGINE_CONTROLS"
    MSG_PANEL_OVERHEAD_PANEL = "MSG_PANEL_OVERHEAD_PANEL"
    MSG_PANEL_FLIGHT_CONTROLS = "MSG_PANEL_FLIGHT_CONTROLS"

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
        levels = [
            0,
            100,
            200,
            300,
            400,
            500,
            1000,
            1500,
            2000,
            2500,
            3000,
            4000,
            5000,
            6000,
            7000,
            8000,
            9000,
            10000,
            12000,
            15000,
            20000,
        ]

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
        return [SpeechMessages.MSG_WORD_FLIGHT_LEVEL] + SpeechMessages._digits_to_keys(
            fl_rounded, 3
        )

    @staticmethod
    def engine_rpm(rpm: int, running: bool) -> str | list[str]:
        """Get message key(s) for engine RPM readout.

        Args:
            rpm: Engine RPM.
            running: Whether engine is running.

        Returns:
            Message key or list of keys.
        """
        if not running:
            return SpeechMessages.MSG_ENGINE_STOPPED

        # Round to nearest 100
        rpm_rounded = round(rpm / 100) * 100

        # Use pre-recorded if available
        if 500 <= rpm_rounded <= 3000:
            return [
                SpeechMessages.MSG_WORD_ENGINE_RPM,
                f"MSG_NUMBER_{rpm_rounded}",
            ]

        # Fallback: spell out digits
        return [SpeechMessages.MSG_WORD_ENGINE_RPM] + SpeechMessages._digits_to_keys(rpm)

    @staticmethod
    def manifold_pressure(inches: float) -> list[str]:
        """Get message keys for manifold pressure readout.

        Args:
            inches: Manifold pressure in inches Hg.

        Returns:
            List of message keys.
        """
        value = int(round(inches))
        value = max(0, min(100, value))

        if value <= 100:
            return [
                SpeechMessages.MSG_WORD_MANIFOLD_PRESSURE,
                f"MSG_NUMBER_{value}",
                SpeechMessages.MSG_WORD_INCHES,
            ]

        return (
            [SpeechMessages.MSG_WORD_MANIFOLD_PRESSURE]
            + SpeechMessages._digits_to_keys(value)
            + [SpeechMessages.MSG_WORD_INCHES]
        )

    @staticmethod
    def oil_pressure(psi: int) -> list[str]:
        """Get message keys for oil pressure readout.

        Args:
            psi: Oil pressure in PSI.

        Returns:
            List of message keys.
        """
        psi = max(0, min(100, psi))

        if psi <= 100:
            return [
                SpeechMessages.MSG_WORD_OIL_PRESSURE,
                f"MSG_NUMBER_{psi}",
                SpeechMessages.MSG_WORD_PSI,
            ]

        return (
            [SpeechMessages.MSG_WORD_OIL_PRESSURE]
            + SpeechMessages._digits_to_keys(psi)
            + [SpeechMessages.MSG_WORD_PSI]
        )

    @staticmethod
    def oil_temperature(fahrenheit: int) -> list[str]:
        """Get message keys for oil temperature readout.

        Args:
            fahrenheit: Oil temperature in Fahrenheit.

        Returns:
            List of message keys.
        """
        temp = max(0, min(100, fahrenheit))

        if temp <= 100:
            return [
                SpeechMessages.MSG_WORD_OIL_TEMPERATURE,
                f"MSG_NUMBER_{temp}",
                SpeechMessages.MSG_WORD_DEGREES,
            ]

        return (
            [SpeechMessages.MSG_WORD_OIL_TEMPERATURE]
            + SpeechMessages._digits_to_keys(temp)
            + [SpeechMessages.MSG_WORD_DEGREES]
        )

    @staticmethod
    def fuel_flow(gph: float) -> list[str]:
        """Get message keys for fuel flow readout.

        Args:
            gph: Fuel flow in gallons per hour.

        Returns:
            List of message keys.
        """
        value = int(round(gph))
        value = max(0, min(100, value))

        if value <= 100:
            return [
                SpeechMessages.MSG_WORD_FUEL_FLOW,
                f"MSG_NUMBER_{value}",
                SpeechMessages.MSG_WORD_GALLONS_PER_HOUR,
            ]

        return (
            [SpeechMessages.MSG_WORD_FUEL_FLOW]
            + SpeechMessages._digits_to_keys(value)
            + [SpeechMessages.MSG_WORD_GALLONS_PER_HOUR]
        )

    @staticmethod
    def battery_voltage(volts: float) -> list[str]:
        """Get message keys for battery voltage readout.

        Args:
            volts: Battery voltage.

        Returns:
            List of message keys.
        """
        value = int(round(volts))
        value = max(0, min(100, value))

        if value <= 100:
            return [
                SpeechMessages.MSG_WORD_BATTERY,
                f"MSG_NUMBER_{value}",
                SpeechMessages.MSG_WORD_VOLTS,
            ]

        return (
            [SpeechMessages.MSG_WORD_BATTERY]
            + SpeechMessages._digits_to_keys(value)
            + [SpeechMessages.MSG_WORD_VOLTS]
        )

    @staticmethod
    def battery_percent(percent: int) -> list[str]:
        """Get message keys for battery percentage readout.

        Args:
            percent: Battery state of charge percentage.

        Returns:
            List of message keys.
        """
        value = max(0, min(100, percent))

        return [
            SpeechMessages.MSG_WORD_BATTERY,
            f"MSG_NUMBER_{value}",
            SpeechMessages.MSG_WORD_PERCENT,
        ]

    @staticmethod
    def battery_status(amps: float) -> str | list[str]:
        """Get message keys for battery charging status.

        Args:
            amps: Battery current in amps (positive = charging, negative = discharging).

        Returns:
            Message key or list of keys.
        """
        if amps > 1.0:
            amp_value = int(round(abs(amps)))
            amp_value = max(0, min(100, amp_value))
            if amp_value <= 100:
                return [
                    SpeechMessages.MSG_BATTERY_CHARGING,
                    SpeechMessages.MSG_WORD_AT,
                    f"MSG_NUMBER_{amp_value}",
                    SpeechMessages.MSG_WORD_AMPS,
                ]
            return (
                [
                    SpeechMessages.MSG_BATTERY_CHARGING,
                    SpeechMessages.MSG_WORD_AT,
                ]
                + SpeechMessages._digits_to_keys(amp_value)
                + [SpeechMessages.MSG_WORD_AMPS]
            )
        elif amps < -1.0:
            amp_value = int(round(abs(amps)))
            amp_value = max(0, min(100, amp_value))
            if amp_value <= 100:
                return [
                    SpeechMessages.MSG_BATTERY_DISCHARGING,
                    SpeechMessages.MSG_WORD_AT,
                    f"MSG_NUMBER_{amp_value}",
                    SpeechMessages.MSG_WORD_AMPS,
                ]
            return (
                [
                    SpeechMessages.MSG_BATTERY_DISCHARGING,
                    SpeechMessages.MSG_WORD_AT,
                ]
                + SpeechMessages._digits_to_keys(amp_value)
                + [SpeechMessages.MSG_WORD_AMPS]
            )
        else:
            return SpeechMessages.MSG_BATTERY_STABLE

    @staticmethod
    def alternator_output(amps: float) -> list[str]:
        """Get message keys for alternator output readout.

        Args:
            amps: Alternator output in amps.

        Returns:
            List of message keys.
        """
        value = int(round(amps))
        value = max(0, min(100, value))

        if value <= 100:
            return [
                SpeechMessages.MSG_WORD_ALTERNATOR_OUTPUT,
                f"MSG_NUMBER_{value}",
                SpeechMessages.MSG_WORD_AMPS,
            ]

        return (
            [SpeechMessages.MSG_WORD_ALTERNATOR_OUTPUT]
            + SpeechMessages._digits_to_keys(value)
            + [SpeechMessages.MSG_WORD_AMPS]
        )

    @staticmethod
    def fuel_quantity(gallons: float) -> list[str]:
        """Get message keys for fuel quantity readout.

        Args:
            gallons: Fuel quantity in gallons.

        Returns:
            List of message keys.
        """
        value = int(round(gallons))
        value = max(0, min(100, value))

        if value <= 100:
            return [
                SpeechMessages.MSG_WORD_FUEL_QUANTITY,
                f"MSG_NUMBER_{value}",
                SpeechMessages.MSG_WORD_GALLONS,
            ]

        return (
            [SpeechMessages.MSG_WORD_FUEL_QUANTITY]
            + SpeechMessages._digits_to_keys(value)
            + [SpeechMessages.MSG_WORD_GALLONS]
        )

    @staticmethod
    def fuel_remaining(minutes: float) -> list[str]:
        """Get message keys for fuel remaining time readout.

        Args:
            minutes: Fuel remaining time in minutes.

        Returns:
            List of message keys.
        """
        hours = int(minutes / 60)
        mins = int(minutes % 60)

        if hours > 0:
            result = [
                SpeechMessages.MSG_WORD_FUEL_REMAINING,
                f"MSG_NUMBER_{hours}",
                SpeechMessages.MSG_WORD_HOURS,
            ]
            if mins > 0:
                result.extend(
                    [
                        f"MSG_NUMBER_{mins}",
                        SpeechMessages.MSG_WORD_MINUTES,
                    ]
                )
            return result
        else:
            return [
                SpeechMessages.MSG_WORD_FUEL_REMAINING,
                f"MSG_NUMBER_{mins}",
                SpeechMessages.MSG_WORD_MINUTES,
            ]


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
MSG_PANEL_INSTRUMENT_PANEL = SpeechMessages.MSG_PANEL_INSTRUMENT_PANEL
MSG_PANEL_PEDESTAL = SpeechMessages.MSG_PANEL_PEDESTAL
MSG_PANEL_ENGINE_CONTROLS = SpeechMessages.MSG_PANEL_ENGINE_CONTROLS
MSG_PANEL_OVERHEAD_PANEL = SpeechMessages.MSG_PANEL_OVERHEAD_PANEL
MSG_PANEL_FLIGHT_CONTROLS = SpeechMessages.MSG_PANEL_FLIGHT_CONTROLS

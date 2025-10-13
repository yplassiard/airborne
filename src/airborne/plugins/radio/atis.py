"""Automatic Terminal Information Service (ATIS) system."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class WeatherInfo:
    """Weather information for ATIS broadcast.

    Attributes:
        wind_direction: Wind direction in degrees (magnetic)
        wind_speed: Wind speed in knots
        wind_gusts: Gust speed in knots (None if no gusts)
        visibility: Visibility in statute miles
        sky_condition: Sky condition (e.g., "clear", "few clouds", "overcast")
        temperature_c: Temperature in Celsius
        dewpoint_c: Dewpoint in Celsius
        altimeter: Altimeter setting in inches Hg
    """

    wind_direction: int
    wind_speed: int
    wind_gusts: int | None = None
    visibility: int = 10
    sky_condition: str = "clear"
    temperature_c: int = 20
    dewpoint_c: int = 15
    altimeter: float = 29.92


@dataclass
class ATISInfo:
    """Complete ATIS information.

    Attributes:
        airport_name: Full airport name
        information_letter: ATIS information letter (A-Z)
        time_zulu: Time in Zulu (UTC) format (HHMM)
        weather: Weather information
        active_runway: Active runway for arrivals/departures
        remarks: Additional remarks (optional)
    """

    airport_name: str
    information_letter: str
    time_zulu: str
    weather: WeatherInfo
    active_runway: str
    remarks: str = ""


class ATISGenerator:
    """Generates ATIS broadcasts with realistic phraseology.

    Follows standard ATIS format:
    1. Airport name and information letter
    2. Time (Zulu)
    3. Wind
    4. Visibility
    5. Sky condition
    6. Temperature/dewpoint
    7. Altimeter
    8. Active runway(s)
    9. Remarks
    10. Advise on initial contact

    Examples:
        >>> weather = WeatherInfo(
        ...     wind_direction=310,
        ...     wind_speed=8,
        ...     visibility=10,
        ...     sky_condition="clear",
        ...     temperature_c=22,
        ...     dewpoint_c=14,
        ...     altimeter=30.12
        ... )
        >>> atis_info = ATISInfo(
        ...     airport_name="Palo Alto Airport",
        ...     information_letter="Bravo",
        ...     time_zulu="1455",
        ...     weather=weather,
        ...     active_runway="31"
        ... )
        >>> generator = ATISGenerator()
        >>> broadcast = generator.generate(atis_info)
    """

    # Phonetic alphabet for information letters
    PHONETIC_ALPHABET = [
        "Alpha",
        "Bravo",
        "Charlie",
        "Delta",
        "Echo",
        "Foxtrot",
        "Golf",
        "Hotel",
        "India",
        "Juliet",
        "Kilo",
        "Lima",
        "Mike",
        "November",
        "Oscar",
        "Papa",
        "Quebec",
        "Romeo",
        "Sierra",
        "Tango",
        "Uniform",
        "Victor",
        "Whiskey",
        "X-ray",
        "Yankee",
        "Zulu",
    ]

    def __init__(self) -> None:
        """Initialize ATIS generator."""
        self._current_letter_index = 0

    def generate(self, atis_info: ATISInfo) -> str:
        """Generate ATIS broadcast text.

        Args:
            atis_info: Complete ATIS information

        Returns:
            Formatted ATIS broadcast text

        Examples:
            >>> weather = WeatherInfo(310, 8, None, 10, "clear", 22, 14, 30.12)
            >>> info = ATISInfo("Palo Alto Airport", "Bravo", "1455", weather, "31")
            >>> generator = ATISGenerator()
            >>> broadcast = generator.generate(info)
            >>> "Palo Alto Airport" in broadcast
            True
        """
        parts = []

        # 1. Introduction
        parts.append(f"{atis_info.airport_name} information {atis_info.information_letter}.")

        # 2. Time
        parts.append(f"Time {atis_info.time_zulu} Zulu.")

        # 3. Wind
        wind_text = self._format_wind(atis_info.weather)
        parts.append(wind_text)

        # 4. Visibility
        parts.append(f"Visibility {atis_info.weather.visibility} statute miles.")

        # 5. Sky condition
        parts.append(f"Sky {atis_info.weather.sky_condition}.")

        # 6. Temperature and dewpoint
        temp_text = self._format_temperature(atis_info.weather)
        parts.append(temp_text)

        # 7. Altimeter
        altimeter_text = self._format_altimeter(atis_info.weather.altimeter)
        parts.append(altimeter_text)

        # 8. Active runway
        parts.append(f"Landing and departing runway {atis_info.active_runway}.")

        # 9. Remarks (if any)
        if atis_info.remarks:
            parts.append(f"Remarks. {atis_info.remarks}.")

        # 10. Advise on contact
        parts.append(
            f"Advise on initial contact you have information {atis_info.information_letter}."
        )

        return " ".join(parts)

    def _format_wind(self, weather: WeatherInfo) -> str:
        """Format wind information.

        Args:
            weather: Weather information

        Returns:
            Formatted wind text
        """
        if weather.wind_speed == 0:
            return "Wind calm."

        wind_text = f"Wind {weather.wind_direction:03d} at {weather.wind_speed}"

        if weather.wind_gusts:
            wind_text += f", gusts {weather.wind_gusts}"

        wind_text += " knots."
        return wind_text

    def _format_temperature(self, weather: WeatherInfo) -> str:
        """Format temperature and dewpoint.

        Args:
            weather: Weather information

        Returns:
            Formatted temperature text
        """
        return f"Temperature {weather.temperature_c}, dewpoint {weather.dewpoint_c}."

    def _format_altimeter(self, altimeter: float) -> str:
        """Format altimeter setting.

        Args:
            altimeter: Altimeter in inches Hg

        Returns:
            Formatted altimeter text
        """
        return f"Altimeter {altimeter:.2f}."

    def get_next_information_letter(self) -> str:
        """Get the next information letter in sequence.

        Returns:
            Next phonetic letter (Alpha, Bravo, etc.)

        Examples:
            >>> generator = ATISGenerator()
            >>> generator.get_next_information_letter()
            'Alpha'
            >>> generator.get_next_information_letter()
            'Bravo'
        """
        letter = self.PHONETIC_ALPHABET[self._current_letter_index]
        self._current_letter_index = (self._current_letter_index + 1) % len(self.PHONETIC_ALPHABET)
        return letter

    def create_default_atis(
        self,
        airport_name: str,
        active_runway: str,
        wind_direction: int | None = None,
        wind_speed: int | None = None,
    ) -> ATISInfo:
        """Create ATIS with default/current conditions.

        Args:
            airport_name: Name of the airport
            active_runway: Active runway identifier
            wind_direction: Optional wind direction (defaults to runway heading)
            wind_speed: Optional wind speed (defaults to 5 knots)

        Returns:
            ATISInfo with default conditions

        Examples:
            >>> generator = ATISGenerator()
            >>> atis = generator.create_default_atis("Palo Alto Airport", "31")
            >>> atis.airport_name
            'Palo Alto Airport'
        """
        # Default wind from runway direction if not specified
        if wind_direction is None:
            wind_direction = int(active_runway.lstrip("0")) * 10

        if wind_speed is None:
            wind_speed = 5

        # Get current time
        now = datetime.utcnow()
        time_zulu = now.strftime("%H%M")

        # Create default weather
        weather = WeatherInfo(
            wind_direction=wind_direction,
            wind_speed=wind_speed,
            wind_gusts=None,
            visibility=10,
            sky_condition="clear",
            temperature_c=20,
            dewpoint_c=15,
            altimeter=29.92,
        )

        # Get next information letter
        info_letter = self.get_next_information_letter()

        return ATISInfo(
            airport_name=airport_name,
            information_letter=info_letter,
            time_zulu=time_zulu,
            weather=weather,
            active_runway=active_runway,
            remarks="",
        )

    def update_atis(
        self,
        current_atis: ATISInfo,
        wind_changed: bool = False,
        runway_changed: bool = False,
        weather_changed: bool = False,
    ) -> ATISInfo:
        """Update ATIS and increment information letter if conditions changed.

        Args:
            current_atis: Current ATIS information
            wind_changed: Whether wind has changed significantly
            runway_changed: Whether active runway changed
            weather_changed: Whether weather changed significantly

        Returns:
            Updated ATISInfo with new letter if conditions changed

        Examples:
            >>> generator = ATISGenerator()
            >>> old_atis = generator.create_default_atis("Palo Alto Airport", "31")
            >>> new_atis = generator.update_atis(old_atis, runway_changed=True)
            >>> old_atis.information_letter != new_atis.information_letter
            True
        """
        # If conditions changed, get new letter
        if wind_changed or runway_changed or weather_changed:
            new_letter = self.get_next_information_letter()
            current_atis.information_letter = new_letter

            # Update time
            now = datetime.utcnow()
            current_atis.time_zulu = now.strftime("%H%M")

        return current_atis

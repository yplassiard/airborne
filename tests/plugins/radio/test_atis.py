"""Unit tests for ATIS system."""

import pytest

from airborne.plugins.radio.atis import ATISGenerator, ATISInfo, WeatherInfo


@pytest.fixture
def atis_generator():
    """Provide ATIS generator instance."""
    return ATISGenerator()


@pytest.fixture
def sample_weather():
    """Provide sample weather information."""
    return WeatherInfo(
        wind_direction=310,
        wind_speed=8,
        wind_gusts=None,
        visibility=10,
        sky_condition="clear",
        temperature_c=22,
        dewpoint_c=14,
        altimeter=30.12,
    )


def test_generator_initialization(atis_generator):
    """Test ATIS generator initializes correctly."""
    assert atis_generator is not None
    assert atis_generator._current_letter_index == 0


def test_weather_info_creation(sample_weather):
    """Test WeatherInfo dataclass creation."""
    assert sample_weather.wind_direction == 310
    assert sample_weather.wind_speed == 8
    assert sample_weather.wind_gusts is None
    assert sample_weather.visibility == 10
    assert sample_weather.sky_condition == "clear"
    assert sample_weather.temperature_c == 22
    assert sample_weather.dewpoint_c == 14
    assert sample_weather.altimeter == 30.12


def test_atis_info_creation(sample_weather):
    """Test ATISInfo dataclass creation."""
    atis_info = ATISInfo(
        airport_name="Palo Alto Airport",
        information_letter="Bravo",
        time_zulu="1455",
        weather=sample_weather,
        active_runway="31",
        remarks="VFR traffic pattern in effect",
        include_parking_instructions=True,
    )

    assert atis_info.airport_name == "Palo Alto Airport"
    assert atis_info.information_letter == "Bravo"
    assert atis_info.time_zulu == "1455"
    assert atis_info.weather == sample_weather
    assert atis_info.active_runway == "31"
    assert atis_info.remarks == "VFR traffic pattern in effect"
    assert atis_info.include_parking_instructions is True


def test_generate_basic_atis(atis_generator, sample_weather):
    """Test generating basic ATIS broadcast."""
    atis_info = ATISInfo(
        airport_name="Palo Alto Airport",
        information_letter="Bravo",
        time_zulu="1455",
        weather=sample_weather,
        active_runway="31",
    )

    broadcast = atis_generator.generate(atis_info)

    # Check all required components present
    assert "Palo Alto Airport" in broadcast
    assert "information Bravo" in broadcast
    assert "Time 1455 Zulu" in broadcast
    assert "Wind 310 at 8 knots" in broadcast
    assert "Visibility 10 statute miles" in broadcast
    assert "Sky clear" in broadcast
    assert "Temperature 22, dewpoint 14" in broadcast
    assert "Altimeter 30.12" in broadcast
    assert "Landing and departing runway 31" in broadcast
    assert "Advise on initial contact you have information Bravo" in broadcast


def test_generate_atis_with_parking_instructions(atis_generator, sample_weather):
    """Test ATIS includes parking assignment instructions when enabled."""
    atis_info = ATISInfo(
        airport_name="Palo Alto Airport",
        information_letter="Bravo",
        time_zulu="1455",
        weather=sample_weather,
        active_runway="31",
        include_parking_instructions=True,
    )

    broadcast = atis_generator.generate(atis_info)

    # Parking instructions should be included
    assert "Inbound aircraft contact ground on 121.7 for parking assignment" in broadcast


def test_generate_atis_without_parking_instructions(atis_generator, sample_weather):
    """Test ATIS excludes parking assignment instructions when disabled."""
    atis_info = ATISInfo(
        airport_name="Palo Alto Airport",
        information_letter="Bravo",
        time_zulu="1455",
        weather=sample_weather,
        active_runway="31",
        include_parking_instructions=False,
    )

    broadcast = atis_generator.generate(atis_info)

    # Parking instructions should NOT be included
    assert "parking assignment" not in broadcast
    assert "contact ground on 121.7" not in broadcast


def test_generate_atis_default_parking_instructions(atis_generator, sample_weather):
    """Test ATIS includes parking instructions by default."""
    # Don't specify include_parking_instructions (defaults to True)
    atis_info = ATISInfo(
        airport_name="Palo Alto Airport",
        information_letter="Bravo",
        time_zulu="1455",
        weather=sample_weather,
        active_runway="31",
    )

    broadcast = atis_generator.generate(atis_info)

    # Should include parking instructions by default
    assert "Inbound aircraft contact ground on 121.7 for parking assignment" in broadcast


def test_format_wind_calm(atis_generator):
    """Test formatting calm wind conditions."""
    weather = WeatherInfo(
        wind_direction=0,
        wind_speed=0,
        wind_gusts=None,
        visibility=10,
        sky_condition="clear",
        temperature_c=20,
        dewpoint_c=15,
        altimeter=29.92,
    )

    wind_text = atis_generator._format_wind(weather)
    assert wind_text == "Wind calm."


def test_format_wind_with_gusts(atis_generator):
    """Test formatting wind with gusts."""
    weather = WeatherInfo(
        wind_direction=270,
        wind_speed=15,
        wind_gusts=22,
        visibility=10,
        sky_condition="clear",
        temperature_c=20,
        dewpoint_c=15,
        altimeter=29.92,
    )

    wind_text = atis_generator._format_wind(weather)
    assert "Wind 270 at 15" in wind_text
    assert "gusts 22 knots" in wind_text


def test_format_wind_without_gusts(atis_generator):
    """Test formatting wind without gusts."""
    weather = WeatherInfo(
        wind_direction=180,
        wind_speed=10,
        wind_gusts=None,
        visibility=10,
        sky_condition="clear",
        temperature_c=20,
        dewpoint_c=15,
        altimeter=29.92,
    )

    wind_text = atis_generator._format_wind(weather)
    assert wind_text == "Wind 180 at 10 knots."
    assert "gusts" not in wind_text


def test_format_temperature(atis_generator):
    """Test formatting temperature and dewpoint."""
    weather = WeatherInfo(
        wind_direction=0,
        wind_speed=0,
        visibility=10,
        sky_condition="clear",
        temperature_c=25,
        dewpoint_c=18,
        altimeter=29.92,
    )

    temp_text = atis_generator._format_temperature(weather)
    assert temp_text == "Temperature 25, dewpoint 18."


def test_format_altimeter(atis_generator):
    """Test formatting altimeter setting."""
    altimeter_text = atis_generator._format_altimeter(29.92)
    assert altimeter_text == "Altimeter 29.92."

    altimeter_text = atis_generator._format_altimeter(30.15)
    assert altimeter_text == "Altimeter 30.15."


def test_get_next_information_letter(atis_generator):
    """Test cycling through information letters."""
    # Should start with Alpha
    letter1 = atis_generator.get_next_information_letter()
    assert letter1 == "Alpha"

    # Should progress through alphabet
    letter2 = atis_generator.get_next_information_letter()
    assert letter2 == "Bravo"

    letter3 = atis_generator.get_next_information_letter()
    assert letter3 == "Charlie"


def test_information_letter_wraps_around(atis_generator):
    """Test information letter cycles back to Alpha after Zulu."""
    # Advance through all 26 letters
    for _ in range(26):
        atis_generator.get_next_information_letter()

    # Next should be Alpha again
    letter = atis_generator.get_next_information_letter()
    assert letter == "Alpha"


def test_create_default_atis(atis_generator):
    """Test creating ATIS with default conditions."""
    atis = atis_generator.create_default_atis(
        airport_name="Palo Alto Airport",
        active_runway="31",
    )

    assert atis.airport_name == "Palo Alto Airport"
    assert atis.active_runway == "31"
    assert atis.information_letter == "Alpha"  # First call
    assert atis.weather.wind_direction == 310  # Runway 31 = 310 degrees
    assert atis.weather.wind_speed == 5
    assert atis.weather.visibility == 10
    assert atis.weather.sky_condition == "clear"
    assert atis.weather.temperature_c == 20
    assert atis.weather.dewpoint_c == 15
    assert atis.weather.altimeter == 29.92


def test_create_default_atis_custom_wind(atis_generator):
    """Test creating ATIS with custom wind."""
    atis = atis_generator.create_default_atis(
        airport_name="Palo Alto Airport",
        active_runway="31",
        wind_direction=280,
        wind_speed=12,
    )

    assert atis.weather.wind_direction == 280
    assert atis.weather.wind_speed == 12


def test_update_atis_no_changes(atis_generator):
    """Test updating ATIS with no condition changes."""
    original_atis = atis_generator.create_default_atis("Palo Alto Airport", "31")
    original_letter = original_atis.information_letter

    # Update with no changes
    updated_atis = atis_generator.update_atis(
        original_atis,
        wind_changed=False,
        runway_changed=False,
        weather_changed=False,
    )

    # Letter should remain the same
    assert updated_atis.information_letter == original_letter


def test_update_atis_wind_changed(atis_generator):
    """Test updating ATIS when wind changes."""
    original_atis = atis_generator.create_default_atis("Palo Alto Airport", "31")
    original_letter = original_atis.information_letter

    # Update with wind change
    updated_atis = atis_generator.update_atis(
        original_atis,
        wind_changed=True,
    )

    # Letter should advance
    assert updated_atis.information_letter != original_letter


def test_update_atis_runway_changed(atis_generator):
    """Test updating ATIS when runway changes."""
    original_atis = atis_generator.create_default_atis("Palo Alto Airport", "31")
    original_letter = original_atis.information_letter

    # Update with runway change
    updated_atis = atis_generator.update_atis(
        original_atis,
        runway_changed=True,
    )

    # Letter should advance
    assert updated_atis.information_letter != original_letter


def test_update_atis_weather_changed(atis_generator):
    """Test updating ATIS when weather changes."""
    original_atis = atis_generator.create_default_atis("Palo Alto Airport", "31")
    original_letter = original_atis.information_letter

    # Update with weather change
    updated_atis = atis_generator.update_atis(
        original_atis,
        weather_changed=True,
    )

    # Letter should advance
    assert updated_atis.information_letter != original_letter


def test_generate_with_remarks(atis_generator, sample_weather):
    """Test generating ATIS with remarks."""
    atis_info = ATISInfo(
        airport_name="Palo Alto Airport",
        information_letter="Bravo",
        time_zulu="1455",
        weather=sample_weather,
        active_runway="31",
        remarks="Birds reported in the vicinity of the airport",
    )

    broadcast = atis_generator.generate(atis_info)

    # Remarks should be included
    assert "Remarks. Birds reported in the vicinity of the airport." in broadcast


def test_generate_without_remarks(atis_generator, sample_weather):
    """Test generating ATIS without remarks."""
    atis_info = ATISInfo(
        airport_name="Palo Alto Airport",
        information_letter="Bravo",
        time_zulu="1455",
        weather=sample_weather,
        active_runway="31",
        remarks="",
    )

    broadcast = atis_generator.generate(atis_info)

    # Remarks section should not appear
    assert "Remarks." not in broadcast


def test_multiple_airports_independent_letters():
    """Test multiple ATIS generators maintain independent letter sequences."""
    gen1 = ATISGenerator()
    gen2 = ATISGenerator()

    # Both start at Alpha
    assert gen1.get_next_information_letter() == "Alpha"
    assert gen2.get_next_information_letter() == "Alpha"

    # Advance gen1
    gen1.get_next_information_letter()  # Bravo
    gen1.get_next_information_letter()  # Charlie

    # gen2 should still be at Bravo
    assert gen2.get_next_information_letter() == "Bravo"


def test_atis_broadcast_order(atis_generator, sample_weather):
    """Test ATIS broadcast components are in correct order."""
    atis_info = ATISInfo(
        airport_name="Palo Alto Airport",
        information_letter="Bravo",
        time_zulu="1455",
        weather=sample_weather,
        active_runway="31",
        remarks="Test remark",
        include_parking_instructions=True,
    )

    broadcast = atis_generator.generate(atis_info)
    parts = broadcast.split(".")

    # Verify order (approximate - each part ends with a period)
    # 1. Airport + info letter
    # 2. Time
    # 3. Wind
    # 4. Visibility
    # 5. Sky
    # 6. Temperature
    # 7. Altimeter
    # 8. Runway
    # 9. Remarks
    # 10. Parking
    # 11. Advise

    assert "Palo Alto Airport information Bravo" in parts[0]
    assert "Time 1455 Zulu" in broadcast
    assert "Wind" in broadcast
    assert "Visibility" in broadcast
    assert broadcast.index("Time") < broadcast.index("Wind")
    assert broadcast.index("Wind") < broadcast.index("Visibility")
    assert broadcast.index("Visibility") < broadcast.index("Sky")
    assert broadcast.index("Altimeter") < broadcast.index("Landing and departing")
    assert broadcast.index("Remarks") < broadcast.index("parking assignment")
    assert broadcast.index("parking assignment") < broadcast.index("Advise")

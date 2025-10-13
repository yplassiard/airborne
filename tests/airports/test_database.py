"""Tests for Airport Database."""

import tempfile
from pathlib import Path

import pytest

from airborne.airports.database import (
    AirportDatabase,
    AirportType,
    FrequencyType,
    SurfaceType,
)
from airborne.physics.vectors import Vector3


class TestAirportDatabaseLoading:
    """Test loading airport data from CSV files."""

    @pytest.fixture
    def temp_data_dir(self) -> Path:
        """Create temporary data directory with sample CSV files."""
        temp_dir = Path(tempfile.mkdtemp())

        # Create sample airports.csv
        airports_csv = temp_dir / "airports.csv"
        with open(airports_csv, "w", encoding="utf-8") as f:
            f.write(
                '"id","ident","type","name","latitude_deg","longitude_deg",'
                '"elevation_ft","continent","iso_country","iso_region","municipality",'
                '"scheduled_service","icao_code","iata_code","gps_code","local_code",'
                '"home_link","wikipedia_link","keywords"\n'
            )
            f.write(
                '1,"KPAO","small_airport","Palo Alto Airport",37.461111,-122.115000,7,'
                '"NA","US","US-CA","Palo Alto","no","KPAO","PAO","KPAO","PAO",'
                '"http://paloaltoairport.org","https://en.wikipedia.org/wiki/Palo_Alto_Airport",""\n'
            )
            f.write(
                '2,"KSFO","large_airport","San Francisco Intl",37.618972,-122.374889,13,'
                '"NA","US","US-CA","San Francisco","yes","KSFO","SFO","KSFO","SFO",'
                '"http://flysfo.com","https://en.wikipedia.org/wiki/San_Francisco_International_Airport",""\n'
            )

        # Create sample runways.csv
        runways_csv = temp_dir / "runways.csv"
        with open(runways_csv, "w", encoding="utf-8") as f:
            f.write(
                '"id","airport_ref","airport_ident","length_ft","width_ft","surface",'
                '"lighted","closed","le_ident","le_latitude_deg","le_longitude_deg",'
                '"le_elevation_ft","le_heading_degT","le_displaced_threshold_ft",'
                '"he_ident","he_latitude_deg","he_longitude_deg","he_elevation_ft",'
                '"he_heading_degT","he_displaced_threshold_ft"\n'
            )
            f.write(
                '1,"1","KPAO",2443,75,"ASPH",1,0,"13",37.458611,-122.121111,5,129.8,0,'
                '"31",37.463611,-122.108889,8,309.8,0\n'
            )
            f.write(
                '2,"2","KSFO",11870,200,"ASPH",1,0,"28L",37.617222,-122.396111,9,284.0,0,'
                '"10R",37.620278,-122.359444,13,104.0,0\n'
            )

        # Create sample frequencies.csv
        frequencies_csv = temp_dir / "airport-frequencies.csv"
        with open(frequencies_csv, "w", encoding="utf-8") as f:
            f.write('"id","airport_ref","airport_ident","type","description","frequency_mhz"\n')
            f.write('1,"1","KPAO","UNICOM","UNICOM",122.950\n')
            f.write('2,"2","KSFO","TWR","SFO Tower",120.500\n')
            f.write('3,"2","KSFO","GND","SFO Ground",121.800\n')
            f.write('4,"2","KSFO","ATIS","SFO ATIS",118.850\n')

        return temp_dir

    def test_load_airports(self, temp_data_dir: Path) -> None:
        """Test loading airports from CSV."""
        db = AirportDatabase()
        db.load_from_csv(temp_data_dir)

        assert db.get_airport_count() == 2
        assert "KPAO" in db.airports
        assert "KSFO" in db.airports

    def test_load_missing_file_raises_error(self) -> None:
        """Test loading from nonexistent directory raises error."""
        db = AirportDatabase()
        with pytest.raises(FileNotFoundError):
            db.load_from_csv("nonexistent_directory")

    def test_airport_data_parsed_correctly(self, temp_data_dir: Path) -> None:
        """Test airport data is parsed correctly."""
        db = AirportDatabase()
        db.load_from_csv(temp_data_dir)

        pao = db.get_airport("KPAO")
        assert pao is not None
        assert pao.name == "Palo Alto Airport"
        assert pao.airport_type == AirportType.SMALL_AIRPORT
        assert pao.municipality == "Palo Alto"
        assert pao.iso_country == "US"
        assert pao.scheduled_service is False
        assert pao.iata_code == "PAO"

    def test_airport_position_parsed_correctly(self, temp_data_dir: Path) -> None:
        """Test airport position is parsed correctly."""
        db = AirportDatabase()
        db.load_from_csv(temp_data_dir)

        pao = db.get_airport("KPAO")
        assert pao is not None

        # Check lat/lon (x=lon, z=lat)
        assert abs(pao.position.x - (-122.115)) < 0.001
        assert abs(pao.position.z - 37.461111) < 0.001

        # Check elevation (y=elevation in meters)
        elevation_m = 7 * 0.3048  # 7 feet to meters
        assert abs(pao.position.y - elevation_m) < 0.01


class TestAirportDatabaseQueries:
    """Test airport database query operations."""

    @pytest.fixture
    def loaded_db(self, temp_data_dir: Path) -> AirportDatabase:
        """Create loaded database for testing."""
        db = AirportDatabase()
        db.load_from_csv(temp_data_dir)
        return db

    @pytest.fixture
    def temp_data_dir(self) -> Path:
        """Create temporary data directory with sample CSV files."""
        temp_dir = Path(tempfile.mkdtemp())

        # Create sample airports.csv with several airports
        airports_csv = temp_dir / "airports.csv"
        with open(airports_csv, "w", encoding="utf-8") as f:
            f.write(
                '"id","ident","type","name","latitude_deg","longitude_deg",'
                '"elevation_ft","continent","iso_country","iso_region","municipality",'
                '"scheduled_service","icao_code","iata_code","gps_code","local_code",'
                '"home_link","wikipedia_link","keywords"\n'
            )
            # Palo Alto (reference point)
            f.write(
                '1,"KPAO","small_airport","Palo Alto Airport",37.461111,-122.115000,7,'
                '"NA","US","US-CA","Palo Alto","no","KPAO","PAO","KPAO","PAO","","",""\n'
            )
            # San Francisco (nearby)
            f.write(
                '2,"KSFO","large_airport","San Francisco Intl",37.618972,-122.374889,13,'
                '"NA","US","US-CA","San Francisco","yes","KSFO","SFO","KSFO","SFO","","",""\n'
            )
            # San Jose (nearby)
            f.write(
                '3,"KSJC","medium_airport","San Jose Intl",37.362500,-121.929167,62,'
                '"NA","US","US-CA","San Jose","yes","KSJC","SJC","KSJC","SJC","","",""\n'
            )
            # Los Angeles (far away)
            f.write(
                '4,"KLAX","large_airport","Los Angeles Intl",33.942536,-118.408075,125,'
                '"NA","US","US-CA","Los Angeles","yes","KLAX","LAX","KLAX","LAX","","",""\n'
            )

        # Create empty runways and frequencies files
        (temp_dir / "runways.csv").write_text(
            '"id","airport_ref","airport_ident","length_ft","width_ft","surface",'
            '"lighted","closed","le_ident","le_latitude_deg","le_longitude_deg",'
            '"le_elevation_ft","le_heading_degT","le_displaced_threshold_ft",'
            '"he_ident","he_latitude_deg","he_longitude_deg","he_elevation_ft",'
            '"he_heading_degT","he_displaced_threshold_ft"\n'
        )
        (temp_dir / "airport-frequencies.csv").write_text(
            '"id","airport_ref","airport_ident","type","description","frequency_mhz"\n'
        )

        return temp_dir

    def test_get_airport_by_icao(self, loaded_db: AirportDatabase) -> None:
        """Test getting airport by ICAO code."""
        pao = loaded_db.get_airport("KPAO")
        assert pao is not None
        assert pao.icao == "KPAO"
        assert pao.name == "Palo Alto Airport"

    def test_get_nonexistent_airport(self, loaded_db: AirportDatabase) -> None:
        """Test getting nonexistent airport returns None."""
        airport = loaded_db.get_airport("XXXX")
        assert airport is None

    def test_get_airports_near(self, loaded_db: AirportDatabase) -> None:
        """Test spatial query for nearby airports."""
        # Use KPAO position as reference
        pao = loaded_db.get_airport("KPAO")
        assert pao is not None

        # Query 30nm radius (should include KPAO, KSFO, KSJC but not KLAX)
        nearby = loaded_db.get_airports_near(pao.position, radius_nm=30)

        # Extract ICAOs
        icaos = [airport.icao for airport, _ in nearby]

        assert "KPAO" in icaos  # Should include itself
        assert "KSFO" in icaos  # ~15nm away
        assert "KSJC" in icaos  # ~10nm away
        assert "KLAX" not in icaos  # ~300nm away

    def test_get_airports_near_sorted_by_distance(self, loaded_db: AirportDatabase) -> None:
        """Test that nearby airports are sorted by distance."""
        pao = loaded_db.get_airport("KPAO")
        assert pao is not None

        nearby = loaded_db.get_airports_near(pao.position, radius_nm=50)

        # Check that distances are sorted
        distances = [distance for _, distance in nearby]
        assert distances == sorted(distances)

        # KPAO should be first (distance ~0)
        assert nearby[0][0].icao == "KPAO"
        assert nearby[0][1] < 0.1  # Very close to zero

    def test_get_countries(self, loaded_db: AirportDatabase) -> None:
        """Test getting list of countries."""
        countries = loaded_db.get_countries()
        assert "US" in countries
        assert isinstance(countries, list)
        assert countries == sorted(countries)


class TestRunwaysAndFrequencies:
    """Test runway and frequency queries."""

    @pytest.fixture
    def temp_data_dir(self) -> Path:
        """Create temporary data directory."""
        temp_dir = Path(tempfile.mkdtemp())

        # Create airports
        airports_csv = temp_dir / "airports.csv"
        with open(airports_csv, "w", encoding="utf-8") as f:
            f.write(
                '"id","ident","type","name","latitude_deg","longitude_deg",'
                '"elevation_ft","continent","iso_country","iso_region","municipality",'
                '"scheduled_service","icao_code","iata_code","gps_code","local_code",'
                '"home_link","wikipedia_link","keywords"\n'
            )
            f.write(
                '1,"KPAO","small_airport","Palo Alto Airport",37.461111,-122.115000,7,'
                '"NA","US","US-CA","Palo Alto","no","KPAO","PAO","KPAO","PAO","","",""\n'
            )

        # Create runways
        runways_csv = temp_dir / "runways.csv"
        with open(runways_csv, "w", encoding="utf-8") as f:
            f.write(
                '"id","airport_ref","airport_ident","length_ft","width_ft","surface",'
                '"lighted","closed","le_ident","le_latitude_deg","le_longitude_deg",'
                '"le_elevation_ft","le_heading_degT","le_displaced_threshold_ft",'
                '"he_ident","he_latitude_deg","he_longitude_deg","he_elevation_ft",'
                '"he_heading_degT","he_displaced_threshold_ft"\n'
            )
            f.write(
                '1,"1","KPAO",2443,75,"ASPH",1,0,"13",37.458611,-122.121111,5,129.8,0,'
                '"31",37.463611,-122.108889,8,309.8,0\n'
            )

        # Create frequencies
        frequencies_csv = temp_dir / "airport-frequencies.csv"
        with open(frequencies_csv, "w", encoding="utf-8") as f:
            f.write('"id","airport_ref","airport_ident","type","description","frequency_mhz"\n')
            f.write('1,"1","KPAO","UNICOM","UNICOM",122.950\n')
            f.write('2,"1","KPAO","CTAF","CTAF",122.950\n')

        return temp_dir

    def test_get_runways(self, temp_data_dir: Path) -> None:
        """Test getting runways for an airport."""
        db = AirportDatabase()
        db.load_from_csv(temp_data_dir)

        runways = db.get_runways("KPAO")
        assert len(runways) == 1
        assert runways[0].runway_id == "13/31"
        assert runways[0].length_ft == 2443
        assert runways[0].surface == SurfaceType.ASPH
        assert runways[0].lighted is True

    def test_get_runways_nonexistent_airport(self, temp_data_dir: Path) -> None:
        """Test getting runways for nonexistent airport returns empty list."""
        db = AirportDatabase()
        db.load_from_csv(temp_data_dir)

        runways = db.get_runways("XXXX")
        assert runways == []

    def test_get_frequencies(self, temp_data_dir: Path) -> None:
        """Test getting frequencies for an airport."""
        db = AirportDatabase()
        db.load_from_csv(temp_data_dir)

        freqs = db.get_frequencies("KPAO")
        assert len(freqs) == 2

        # Check UNICOM frequency
        unicom = next(f for f in freqs if f.freq_type == FrequencyType.UNICOM)
        assert unicom.frequency_mhz == 122.950

    def test_get_frequencies_nonexistent_airport(self, temp_data_dir: Path) -> None:
        """Test getting frequencies for nonexistent airport returns empty list."""
        db = AirportDatabase()
        db.load_from_csv(temp_data_dir)

        freqs = db.get_frequencies("XXXX")
        assert freqs == []


class TestHaversineDistance:
    """Test haversine distance calculation."""

    def test_distance_between_known_points(self) -> None:
        """Test distance calculation between known airports."""
        # KPAO: 37.461111, -122.115000
        # KSFO: 37.618972, -122.374889
        # Known distance: ~15 nm

        kpao_pos = Vector3(-122.115, 0, 37.461111)
        ksfo_pos = Vector3(-122.374889, 0, 37.618972)

        distance = AirportDatabase._haversine_distance_nm(kpao_pos, ksfo_pos)

        # Should be approximately 15 nm
        assert 14 < distance < 16

    def test_distance_to_self_is_zero(self) -> None:
        """Test distance from point to itself is zero."""
        pos = Vector3(-122.115, 0, 37.461111)
        distance = AirportDatabase._haversine_distance_nm(pos, pos)
        assert distance < 0.01  # Very close to zero

    def test_distance_symmetric(self) -> None:
        """Test distance is symmetric."""
        pos1 = Vector3(-122.115, 0, 37.461111)
        pos2 = Vector3(-122.374889, 0, 37.618972)

        dist1 = AirportDatabase._haversine_distance_nm(pos1, pos2)
        dist2 = AirportDatabase._haversine_distance_nm(pos2, pos1)

        assert abs(dist1 - dist2) < 0.001

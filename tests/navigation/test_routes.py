"""Tests for route database system."""

from pathlib import Path

import pytest

from airborne.navigation.routes import OpenFlightsProvider, Route, RouteProvider


class TestRoute:
    """Test Route dataclass."""

    def test_create_route(self):
        """Test creating a route."""
        route = Route(
            airline_code="AA",
            airline_id="24",
            source_airport="KJFK",
            source_airport_id="3797",
            destination_airport="EGLL",
            destination_airport_id="507",
            codeshare=False,
            stops=0,
            equipment=["777", "787"],
        )

        assert route.airline_code == "AA"
        assert route.source_airport == "KJFK"
        assert route.destination_airport == "EGLL"
        assert route.stops == 0
        assert len(route.equipment) == 2

    def test_is_direct(self):
        """Test checking if route is direct."""
        direct_route = Route(
            airline_code="AA",
            airline_id="24",
            source_airport="KJFK",
            source_airport_id="3797",
            destination_airport="EGLL",
            destination_airport_id="507",
            codeshare=False,
            stops=0,
            equipment=["777"],
        )

        indirect_route = Route(
            airline_code="AA",
            airline_id="24",
            source_airport="KJFK",
            source_airport_id="3797",
            destination_airport="EGLL",
            destination_airport_id="507",
            codeshare=False,
            stops=1,
            equipment=["777"],
        )

        assert direct_route.is_direct() is True
        assert indirect_route.is_direct() is False

    def test_codeshare_route(self):
        """Test codeshare route."""
        route = Route(
            airline_code="AA",
            airline_id="24",
            source_airport="KJFK",
            source_airport_id="3797",
            destination_airport="EGLL",
            destination_airport_id="507",
            codeshare=True,
            stops=0,
            equipment=["777"],
        )

        assert route.codeshare is True

    def test_equipment_list(self):
        """Test route with multiple equipment types."""
        route = Route(
            airline_code="AA",
            airline_id="24",
            source_airport="KJFK",
            source_airport_id="3797",
            destination_airport="EGLL",
            destination_airport_id="507",
            codeshare=False,
            stops=0,
            equipment=["777", "787", "A350"],
        )

        assert len(route.equipment) == 3
        assert "777" in route.equipment
        assert "787" in route.equipment
        assert "A350" in route.equipment


class TestRouteProvider:
    """Test RouteProvider abstract base class."""

    def test_route_provider_is_abstract(self):
        """Test that RouteProvider cannot be instantiated."""
        with pytest.raises(TypeError):
            RouteProvider()  # type: ignore


class TestOpenFlightsProvider:
    """Test OpenFlightsProvider class."""

    @pytest.fixture
    def provider(self):
        """Create OpenFlights provider with test data."""
        # Use actual OpenFlights data if available
        routes_file = "data/navigation/routes.dat"
        if not Path(routes_file).exists():
            pytest.skip("OpenFlights routes.dat not found")
        return OpenFlightsProvider(routes_file=routes_file)

    @pytest.fixture
    def provider_with_test_data(self, tmp_path):
        """Create provider with minimal test data."""
        # Create test routes file
        routes_content = """AA,24,JFK,3797,LAX,3484,,0,738
AA,24,JFK,3797,LHR,507,,0,777 787
UA,591,SFO,3469,LAX,3484,,0,737
UA,591,SFO,3469,ORD,3830,Y,0,738 739
DL,2009,LAX,3484,JFK,3797,,0,739
BA,1355,LHR,507,JFK,3797,,0,777
BA,1355,LHR,507,JFK,3797,,1,320
"""
        routes_file = tmp_path / "routes.dat"
        routes_file.write_text(routes_content)

        return OpenFlightsProvider(routes_file=str(routes_file))

    def test_create_provider(self, provider_with_test_data):
        """Test creating OpenFlights provider."""
        assert provider_with_test_data is not None
        assert isinstance(provider_with_test_data, RouteProvider)

    def test_load_routes(self, provider_with_test_data):
        """Test loading routes from file."""
        assert provider_with_test_data.get_route_count() == 7

    def test_find_routes_basic(self, provider_with_test_data):
        """Test finding routes between airports."""
        routes = provider_with_test_data.find_routes("JFK", "LAX")

        assert len(routes) == 1
        assert routes[0].airline_code == "AA"
        assert routes[0].source_airport == "JFK"
        assert routes[0].destination_airport == "LAX"

    def test_find_routes_multiple(self, provider_with_test_data):
        """Test finding multiple routes to same destination."""
        routes = provider_with_test_data.find_routes("LHR", "JFK")

        assert len(routes) == 2
        assert all(r.airline_code == "BA" for r in routes)

    def test_find_routes_direct_only(self, provider_with_test_data):
        """Test finding only direct routes."""
        routes = provider_with_test_data.find_routes("LHR", "JFK", direct_only=True)

        assert len(routes) == 1
        assert routes[0].stops == 0

    def test_find_routes_not_found(self, provider_with_test_data):
        """Test finding routes when none exist."""
        routes = provider_with_test_data.find_routes("JFK", "SFO")

        assert len(routes) == 0

    def test_find_routes_unknown_airport(self, provider_with_test_data):
        """Test finding routes from unknown airport."""
        routes = provider_with_test_data.find_routes("ZZZZ", "JFK")

        assert len(routes) == 0

    def test_get_airports_with_routes(self, provider_with_test_data):
        """Test getting list of airports with routes."""
        airports = provider_with_test_data.get_airports_with_routes()

        assert "JFK" in airports
        assert "SFO" in airports
        assert "LAX" in airports
        assert "LHR" in airports

    def test_get_destinations_from_airport(self, provider_with_test_data):
        """Test getting destinations from airport."""
        destinations = provider_with_test_data.get_destinations_from("JFK")

        assert len(destinations) == 2
        assert "LAX" in destinations
        assert "LHR" in destinations

    def test_get_destinations_unknown_airport(self, provider_with_test_data):
        """Test getting destinations from unknown airport."""
        destinations = provider_with_test_data.get_destinations_from("ZZZZ")

        assert len(destinations) == 0

    def test_route_equipment_parsing(self, provider_with_test_data):
        """Test that equipment list is parsed correctly."""
        routes = provider_with_test_data.find_routes("JFK", "LHR")

        assert len(routes) == 1
        assert len(routes[0].equipment) == 2
        assert "777" in routes[0].equipment
        assert "787" in routes[0].equipment

    def test_codeshare_detection(self, provider_with_test_data):
        """Test that codeshare routes are detected."""
        routes = provider_with_test_data.find_routes("SFO", "ORD")

        assert len(routes) == 1
        assert routes[0].codeshare is True

    def test_non_codeshare_detection(self, provider_with_test_data):
        """Test that non-codeshare routes are detected."""
        routes = provider_with_test_data.find_routes("JFK", "LAX")

        assert len(routes) == 1
        assert routes[0].codeshare is False

    def test_stops_parsing(self, provider_with_test_data):
        """Test that stops are parsed correctly."""
        routes = provider_with_test_data.find_routes("LHR", "JFK", direct_only=False)

        direct = [r for r in routes if r.stops == 0]
        indirect = [r for r in routes if r.stops > 0]

        assert len(direct) == 1
        assert len(indirect) == 1
        assert indirect[0].stops == 1

    def test_real_data_loaded(self, provider):
        """Test loading real OpenFlights data."""
        # Should have loaded ~67k routes
        assert provider.get_route_count() > 60000
        assert provider.get_route_count() < 70000

    def test_real_data_find_us_routes(self, provider):
        """Test finding routes in real data (US routes)."""
        # Find routes from San Francisco to Los Angeles
        routes = provider.find_routes("SFO", "LAX")

        # Should have multiple airlines flying this route
        assert len(routes) > 0

    def test_real_data_find_transatlantic_routes(self, provider):
        """Test finding transatlantic routes in real data."""
        # JFK to London has multiple routes
        routes = provider.find_routes("JFK", "LHR")

        # Should have multiple airlines
        assert len(routes) > 0

    def test_real_data_airports_with_routes(self, provider):
        """Test getting airports with routes from real data."""
        airports = provider.get_airports_with_routes()

        # Should have thousands of airports
        assert len(airports) > 3000

        # Major airports should be included
        assert "JFK" in airports or "KJFK" in airports
        assert "LHR" in airports or "EGLL" in airports

    def test_real_data_destinations_from_major_hub(self, provider):
        """Test getting destinations from major hub."""
        # Try both IATA and ICAO codes
        destinations_jfk = provider.get_destinations_from("JFK")
        destinations_kjfk = provider.get_destinations_from("KJFK")

        # At least one should have many destinations
        total_destinations = max(len(destinations_jfk), len(destinations_kjfk))
        assert total_destinations > 50

    def test_provider_without_file(self, tmp_path):
        """Test provider when file doesn't exist."""
        missing_file = str(tmp_path / "missing.dat")
        provider = OpenFlightsProvider(routes_file=missing_file)

        # Should create empty provider
        assert provider.get_route_count() == 0
        assert len(provider.get_airports_with_routes()) == 0

    def test_null_value_handling(self, tmp_path):
        """Test handling of \\N null values in data."""
        routes_content = """\\N,\\N,JFK,3797,LAX,3484,,0,\\N
"""
        routes_file = tmp_path / "routes.dat"
        routes_file.write_text(routes_content)

        provider = OpenFlightsProvider(routes_file=str(routes_file))

        assert provider.get_route_count() == 1
        routes = provider.find_routes("JFK", "LAX")
        assert len(routes) == 1
        assert routes[0].airline_code == ""
        assert routes[0].equipment == []

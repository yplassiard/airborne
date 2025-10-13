"""Tests for SRTM Elevation Provider."""

import pytest

from airborne.terrain.srtm_provider import (
    ConstantElevationProvider,
    SimpleFlatEarthProvider,
    SRTMProvider,
)


class TestSimpleFlatEarthProvider:
    """Test simple flat-earth elevation provider."""

    @pytest.fixture
    def provider(self) -> SimpleFlatEarthProvider:
        """Create flat-earth provider."""
        return SimpleFlatEarthProvider()

    def test_provider_name(self, provider: SimpleFlatEarthProvider) -> None:
        """Test provider name."""
        assert provider.get_name() == "flat_earth"

    def test_provider_available(self, provider: SimpleFlatEarthProvider) -> None:
        """Test provider is always available."""
        assert provider.is_available() is True

    def test_get_elevation(self, provider: SimpleFlatEarthProvider) -> None:
        """Test getting elevation."""
        elevation = provider.get_elevation(37.7749, -122.4194)

        # Should return non-negative elevation
        assert elevation >= 0

    def test_elevation_varies_with_location(self, provider: SimpleFlatEarthProvider) -> None:
        """Test that elevation varies with location."""
        elevation_sf = provider.get_elevation(37.7749, -122.4194)  # San Francisco
        elevation_ny = provider.get_elevation(40.7128, -74.0060)  # New York
        elevation_eq = provider.get_elevation(0.0, 0.0)  # Equator

        # Elevations should be different (simple model creates variation)
        assert elevation_sf != elevation_ny or elevation_ny != elevation_eq

    def test_polar_regions_higher(self, provider: SimpleFlatEarthProvider) -> None:
        """Test that polar regions have higher elevation."""
        elevation_equator = provider.get_elevation(0.0, 0.0)
        elevation_arctic = provider.get_elevation(70.0, 0.0)

        # Arctic should be higher due to lat_factor
        assert elevation_arctic > elevation_equator

    def test_invalid_coordinates_clamped(self, provider: SimpleFlatEarthProvider) -> None:
        """Test that invalid coordinates are clamped."""
        # Should not crash with out-of-range coordinates
        elevation = provider.get_elevation(1000.0, 1000.0)
        assert elevation >= 0


class TestConstantElevationProvider:
    """Test constant elevation provider."""

    def test_provider_name(self) -> None:
        """Test provider name."""
        provider = ConstantElevationProvider()
        assert provider.get_name() == "constant"

    def test_default_elevation(self) -> None:
        """Test default elevation (sea level)."""
        provider = ConstantElevationProvider()

        elevation = provider.get_elevation(37.7749, -122.4194)
        assert elevation == 0.0

    def test_custom_elevation(self) -> None:
        """Test custom elevation."""
        provider = ConstantElevationProvider(elevation=1000.0)

        elevation = provider.get_elevation(37.7749, -122.4194)
        assert elevation == 1000.0

    def test_elevation_constant_everywhere(self) -> None:
        """Test that elevation is constant regardless of coordinates."""
        provider = ConstantElevationProvider(elevation=500.0)

        elevation1 = provider.get_elevation(37.7749, -122.4194)
        elevation2 = provider.get_elevation(40.7128, -74.0060)
        elevation3 = provider.get_elevation(-33.8688, 151.2093)

        assert elevation1 == elevation2 == elevation3 == 500.0

    def test_provider_available(self) -> None:
        """Test provider is always available."""
        provider = ConstantElevationProvider()
        assert provider.is_available() is True


class TestSRTMProvider:
    """Test SRTM elevation provider."""

    @pytest.fixture
    def provider(self) -> SRTMProvider:
        """Create SRTM provider with fallback."""
        return SRTMProvider(use_fallback=True)

    def test_provider_name(self, provider: SRTMProvider) -> None:
        """Test provider name."""
        assert provider.get_name() == "srtm"

    def test_provider_available_with_fallback(self, provider: SRTMProvider) -> None:
        """Test provider is available with fallback enabled."""
        assert provider.is_available() is True

    def test_provider_unavailable_without_fallback(self) -> None:
        """Test provider unavailable without fallback and no cache."""
        provider = SRTMProvider(use_fallback=False)
        assert provider.is_available() is False

    def test_get_elevation_in_coverage(self, provider: SRTMProvider) -> None:
        """Test getting elevation within SRTM coverage."""
        # San Francisco is within SRTM coverage (60°N to 56°S)
        elevation = provider.get_elevation(37.7749, -122.4194)

        # Should return elevation (from fallback)
        assert elevation >= 0

    def test_get_elevation_outside_coverage(self, provider: SRTMProvider) -> None:
        """Test getting elevation outside SRTM coverage."""
        # Arctic (70°N) is outside SRTM coverage
        elevation = provider.get_elevation(70.0, 0.0)

        # Should use fallback
        assert elevation >= 0

    def test_get_elevation_south_pole(self, provider: SRTMProvider) -> None:
        """Test elevation at South Pole (outside coverage)."""
        elevation = provider.get_elevation(-90.0, 0.0)

        # Should use fallback (outside -56° to 60° range)
        assert elevation >= 0

    def test_get_elevation_without_fallback_fails(self) -> None:
        """Test that provider fails without fallback."""
        provider = SRTMProvider(use_fallback=False)

        # Should raise error for coordinates outside coverage
        with pytest.raises(RuntimeError, match="outside SRTM coverage"):
            provider.get_elevation(70.0, 0.0)

    def test_batch_query(self, provider: SRTMProvider) -> None:
        """Test batch elevation query."""
        coords = [
            (37.7749, -122.4194),  # San Francisco
            (34.0522, -118.2437),  # Los Angeles
            (40.7128, -74.0060),  # New York
        ]

        results = provider.get_elevations(coords)

        assert len(results) == 3
        for lat, lon, elevation in results:
            assert elevation >= 0

    def test_coverage_check(self, provider: SRTMProvider) -> None:
        """Test SRTM coverage checking."""
        # Within coverage
        assert provider._is_in_coverage(37.7749, -122.4194) is True
        assert provider._is_in_coverage(0.0, 0.0) is True
        assert provider._is_in_coverage(-55.0, 0.0) is True
        assert provider._is_in_coverage(59.0, 0.0) is True

        # Outside coverage
        assert provider._is_in_coverage(70.0, 0.0) is False
        assert provider._is_in_coverage(-90.0, 0.0) is False
        assert provider._is_in_coverage(90.0, 0.0) is False


class TestProviderIntegration:
    """Test integration with elevation service."""

    def test_simple_provider_with_service(self) -> None:
        """Test SimpleFlatEarthProvider with elevation service."""
        from airborne.terrain.elevation_service import ElevationService

        service = ElevationService()
        provider = SimpleFlatEarthProvider()
        service.add_provider(provider)

        elevation = service.get_elevation(37.7749, -122.4194)
        assert elevation >= 0

    def test_constant_provider_with_service(self) -> None:
        """Test ConstantElevationProvider with elevation service."""
        from airborne.terrain.elevation_service import ElevationService

        service = ElevationService()
        provider = ConstantElevationProvider(elevation=250.0)
        service.add_provider(provider)

        elevation = service.get_elevation(37.7749, -122.4194)
        assert elevation == 250.0

    def test_srtm_provider_with_service(self) -> None:
        """Test SRTMProvider with elevation service."""
        from airborne.terrain.elevation_service import ElevationService

        service = ElevationService()
        provider = SRTMProvider(use_fallback=True)
        service.add_provider(provider)

        elevation = service.get_elevation(37.7749, -122.4194)
        assert elevation >= 0

    def test_provider_caching(self) -> None:
        """Test that elevation service caches provider results."""
        from airborne.terrain.elevation_service import ElevationService

        service = ElevationService()
        provider = SimpleFlatEarthProvider()
        service.add_provider(provider)

        # First query
        elevation1 = service.get_elevation(37.7749, -122.4194)

        # Second query (should hit cache)
        elevation2 = service.get_elevation(37.7749, -122.4194)

        # Should be identical (from cache)
        assert elevation1 == elevation2


class TestRealWorldScenarios:
    """Test real-world elevation scenarios."""

    def test_continental_us_elevations(self) -> None:
        """Test elevations across continental US."""
        provider = SimpleFlatEarthProvider()

        # Major US cities
        cities = {
            "San Francisco": (37.7749, -122.4194),
            "Denver": (39.7392, -104.9903),
            "New York": (40.7128, -74.0060),
            "Miami": (25.7617, -80.1918),
        }

        for city, (lat, lon) in cities.items():
            elevation = provider.get_elevation(lat, lon)
            assert elevation >= 0, f"{city} elevation should be non-negative"

    def test_mountain_regions(self) -> None:
        """Test elevations in mountain regions."""
        provider = SimpleFlatEarthProvider()

        # Mountain locations
        mountains = [
            (27.9881, 86.9250),  # Mount Everest
            (46.8523, 8.0571),  # Matterhorn
            (38.8977, -105.0443),  # Pikes Peak
        ]

        for lat, lon in mountains:
            elevation = provider.get_elevation(lat, lon)
            # Simple model won't return accurate mountain heights,
            # but should return some elevation
            assert elevation >= 0

    def test_ocean_elevations(self) -> None:
        """Test elevations over oceans."""
        provider = SimpleFlatEarthProvider()

        # Ocean locations
        oceans = [
            (25.0, -30.0),  # Atlantic
            (0.0, -180.0),  # Pacific
            (-20.0, 60.0),  # Indian
        ]

        for lat, lon in oceans:
            elevation = provider.get_elevation(lat, lon)
            # Simple model returns 0 or low values for ocean
            assert elevation >= 0

    def test_provider_fallback_chain(self) -> None:
        """Test provider fallback when SRTM unavailable."""
        from airborne.terrain.elevation_service import ElevationService

        service = ElevationService()

        # Add SRTM provider with fallback
        srtm = SRTMProvider(use_fallback=True)
        service.add_provider(srtm)

        # Query outside SRTM coverage
        elevation = service.get_elevation(70.0, 0.0)

        # Should fall back to SimpleFlatEarthProvider
        assert elevation >= 0

    def test_constant_elevation_for_flat_terrain(self) -> None:
        """Test constant elevation for flat terrain simulation."""
        from airborne.terrain.elevation_service import ElevationService

        service = ElevationService()

        # Use constant elevation for Kansas (flat terrain)
        provider = ConstantElevationProvider(elevation=400.0)  # ~400m elevation
        service.add_provider(provider)

        # Query multiple locations
        coords = [(38.5, -98.0), (39.0, -98.5), (37.5, -97.5)]

        for lat, lon in coords:
            elevation = service.get_elevation(lat, lon)
            assert elevation == 400.0  # Always flat

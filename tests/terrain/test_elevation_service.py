"""Tests for Elevation Service."""

import pytest

from airborne.physics.vectors import Vector3
from airborne.terrain.elevation_service import (
    ElevationCache,
    ElevationQuery,
    ElevationService,
    IElevationProvider,
)


class MockElevationProvider(IElevationProvider):
    """Mock elevation provider for testing."""

    def __init__(self, name: str = "mock", elevation: float = 100.0, should_fail: bool = False):
        """Initialize mock provider."""
        self.name = name
        self.elevation = elevation
        self.should_fail = should_fail
        self.query_count = 0

    def get_name(self) -> str:
        """Get provider name."""
        return self.name

    def get_elevation(self, latitude: float, longitude: float) -> float:
        """Get mock elevation."""
        self.query_count += 1

        if self.should_fail:
            raise RuntimeError("Mock provider failure")

        # Return elevation based on latitude (for testing)
        return self.elevation + latitude

    def is_available(self) -> bool:
        """Check if provider is available."""
        return not self.should_fail


class TestElevationCache:
    """Test elevation cache."""

    @pytest.fixture
    def cache(self) -> ElevationCache:
        """Create elevation cache."""
        return ElevationCache(max_size=100, precision=4)

    def test_cache_set_and_get(self, cache: ElevationCache) -> None:
        """Test caching elevation."""
        cache.set(37.7749, -122.4194, 10.0)

        elevation = cache.get(37.7749, -122.4194)
        assert elevation == 10.0

    def test_cache_miss(self, cache: ElevationCache) -> None:
        """Test cache miss."""
        elevation = cache.get(37.7749, -122.4194)
        assert elevation is None

    def test_cache_rounding(self, cache: ElevationCache) -> None:
        """Test coordinate rounding for cache keys."""
        cache.set(37.77491, -122.41941, 10.0)

        # Should find with slightly different coordinates
        elevation = cache.get(37.77489, -122.41939)
        assert elevation == 10.0

    def test_cache_eviction(self) -> None:
        """Test LRU eviction when cache is full."""
        cache = ElevationCache(max_size=3)

        cache.set(1.0, 1.0, 10.0)
        cache.set(2.0, 2.0, 20.0)
        cache.set(3.0, 3.0, 30.0)

        # Cache is full, adding new entry should evict oldest
        cache.set(4.0, 4.0, 40.0)

        # First entry should be evicted
        assert cache.get(1.0, 1.0) is None
        assert cache.get(4.0, 4.0) == 40.0

    def test_cache_lru_order(self) -> None:
        """Test LRU access order update."""
        cache = ElevationCache(max_size=3)

        cache.set(1.0, 1.0, 10.0)
        cache.set(2.0, 2.0, 20.0)
        cache.set(3.0, 3.0, 30.0)

        # Access first entry (moves to end of LRU)
        cache.get(1.0, 1.0)

        # Add new entry, should evict second entry (not first)
        cache.set(4.0, 4.0, 40.0)

        assert cache.get(1.0, 1.0) == 10.0  # Still cached
        assert cache.get(2.0, 2.0) is None  # Evicted

    def test_clear_cache(self, cache: ElevationCache) -> None:
        """Test clearing cache."""
        cache.set(37.7749, -122.4194, 10.0)
        cache.set(34.0522, -118.2437, 20.0)

        cache.clear()

        assert cache.get(37.7749, -122.4194) is None
        assert cache.get(34.0522, -118.2437) is None
        assert cache.get_size() == 0

    def test_cache_size(self, cache: ElevationCache) -> None:
        """Test getting cache size."""
        assert cache.get_size() == 0

        cache.set(37.7749, -122.4194, 10.0)
        assert cache.get_size() == 1

        cache.set(34.0522, -118.2437, 20.0)
        assert cache.get_size() == 2


class TestElevationService:
    """Test elevation service."""

    @pytest.fixture
    def service(self) -> ElevationService:
        """Create elevation service."""
        return ElevationService(cache_size=100)

    def test_no_providers_error(self, service: ElevationService) -> None:
        """Test error when no providers available."""
        with pytest.raises(ValueError, match="No elevation providers available"):
            service.get_elevation(37.7749, -122.4194)

    def test_add_provider(self, service: ElevationService) -> None:
        """Test adding provider."""
        provider = MockElevationProvider()
        service.add_provider(provider)

        assert len(service.providers) == 1

    def test_remove_provider(self, service: ElevationService) -> None:
        """Test removing provider."""
        provider = MockElevationProvider(name="test_provider")
        service.add_provider(provider)

        service.remove_provider("test_provider")

        assert len(service.providers) == 0

    def test_get_elevation(self, service: ElevationService) -> None:
        """Test getting elevation."""
        provider = MockElevationProvider(elevation=100.0)
        service.add_provider(provider)

        elevation = service.get_elevation(37.7749, -122.4194)

        # Should return elevation + latitude
        assert elevation == pytest.approx(137.7749, rel=0.001)

    def test_caching(self, service: ElevationService) -> None:
        """Test that results are cached."""
        provider = MockElevationProvider(elevation=100.0)
        service.add_provider(provider)

        # First query
        elevation1 = service.get_elevation(37.7749, -122.4194)
        assert provider.query_count == 1

        # Second query (should hit cache)
        elevation2 = service.get_elevation(37.7749, -122.4194)
        assert provider.query_count == 1  # No additional query

        assert elevation1 == elevation2

    def test_provider_fallback(self, service: ElevationService) -> None:
        """Test fallback to next provider on failure."""
        failing_provider = MockElevationProvider(name="failing", should_fail=True)
        working_provider = MockElevationProvider(name="working", elevation=200.0)

        service.add_provider(failing_provider)
        service.add_provider(working_provider)

        # Should fall back to working provider
        elevation = service.get_elevation(37.7749, -122.4194)
        assert elevation == pytest.approx(237.7749, rel=0.001)

    def test_all_providers_fail(self, service: ElevationService) -> None:
        """Test error when all providers fail."""
        failing_provider1 = MockElevationProvider(name="fail1", should_fail=True)
        failing_provider2 = MockElevationProvider(name="fail2", should_fail=True)

        service.add_provider(failing_provider1)
        service.add_provider(failing_provider2)

        with pytest.raises(RuntimeError, match="All elevation providers failed"):
            service.get_elevation(37.7749, -122.4194)

    def test_get_elevations_batch(self, service: ElevationService) -> None:
        """Test batch elevation queries."""
        provider = MockElevationProvider(elevation=100.0)
        service.add_provider(provider)

        coords = [(37.7749, -122.4194), (34.0522, -118.2437), (40.7128, -74.0060)]

        results = service.get_elevations(coords)

        assert len(results) == 3
        assert isinstance(results[0], ElevationQuery)
        assert results[0].latitude == 37.7749
        assert results[0].longitude == -122.4194
        assert results[0].elevation_m == pytest.approx(137.7749, rel=0.001)

    def test_get_elevation_at_position(self, service: ElevationService) -> None:
        """Test getting elevation from Vector3 position."""
        provider = MockElevationProvider(elevation=100.0)
        service.add_provider(provider)

        position = Vector3(-122.4194, 0, 37.7749)  # x=lon, z=lat

        elevation = service.get_elevation_at_position(position)

        assert elevation == pytest.approx(137.7749, rel=0.001)

    def test_clear_cache(self, service: ElevationService) -> None:
        """Test clearing cache."""
        provider = MockElevationProvider(elevation=100.0)
        service.add_provider(provider)

        # Query to populate cache
        service.get_elevation(37.7749, -122.4194)
        assert provider.query_count == 1

        # Clear cache
        service.clear_cache()

        # Query again (should hit provider, not cache)
        service.get_elevation(37.7749, -122.4194)
        assert provider.query_count == 2

    def test_cache_stats(self, service: ElevationService) -> None:
        """Test getting cache statistics."""
        provider = MockElevationProvider()
        service.add_provider(provider)

        service.get_elevation(37.7749, -122.4194)
        service.get_elevation(34.0522, -118.2437)

        stats = service.get_cache_stats()

        assert stats["size"] == 2
        assert stats["max_size"] == 100
        assert stats["providers"] == 1
        assert "mock" in stats["provider_names"]


class TestMockProvider:
    """Test mock provider behavior."""

    def test_provider_name(self) -> None:
        """Test provider name."""
        provider = MockElevationProvider(name="test")
        assert provider.get_name() == "test"

    def test_provider_elevation(self) -> None:
        """Test provider elevation calculation."""
        provider = MockElevationProvider(elevation=100.0)

        elevation = provider.get_elevation(37.0, -122.0)
        assert elevation == 137.0  # 100 + 37

    def test_provider_availability(self) -> None:
        """Test provider availability."""
        working = MockElevationProvider(should_fail=False)
        failing = MockElevationProvider(should_fail=True)

        assert working.is_available() is True
        assert failing.is_available() is False

    def test_provider_batch_query(self) -> None:
        """Test provider batch query."""
        provider = MockElevationProvider(elevation=100.0)

        coords = [(37.0, -122.0), (34.0, -118.0)]
        results = provider.get_elevations(coords)

        assert len(results) == 2
        assert results[0] == (37.0, -122.0, 137.0)
        assert results[1] == (34.0, -118.0, 134.0)


class TestRealWorldScenarios:
    """Test real-world elevation scenarios."""

    def test_san_francisco_elevation(self) -> None:
        """Test San Francisco elevation query."""
        service = ElevationService()
        provider = MockElevationProvider(elevation=10.0)  # SF is ~10m above sea level
        service.add_provider(provider)

        elevation = service.get_elevation(37.7749, -122.4194)

        # Mock returns 10 + 37.7749 = 47.7749
        assert elevation == pytest.approx(47.7749, rel=0.001)

    def test_mount_everest_elevation(self) -> None:
        """Test Mount Everest elevation query."""
        service = ElevationService()
        provider = MockElevationProvider(elevation=8848.0)  # Everest height
        service.add_provider(provider)

        elevation = service.get_elevation(27.9881, 86.9250)

        # Mock returns 8848 + 27.9881 = 8875.9881
        assert elevation == pytest.approx(8875.9881, rel=0.001)

    def test_death_valley_elevation(self) -> None:
        """Test Death Valley elevation (below sea level)."""
        service = ElevationService()
        provider = MockElevationProvider(elevation=-86.0)  # Death Valley
        service.add_provider(provider)

        elevation = service.get_elevation(36.5323, -116.9325)

        # Mock returns -86 + 36.5323 = -49.4677
        assert elevation == pytest.approx(-49.4677, rel=0.001)

    def test_flight_path_elevations(self) -> None:
        """Test elevation queries along a flight path."""
        service = ElevationService()
        provider = MockElevationProvider(elevation=500.0)
        service.add_provider(provider)

        # Simulate flight path from KSFO to KLAX
        waypoints = [
            (37.6213, -122.3790),  # KSFO
            (37.0, -121.0),  # Waypoint 1
            (36.0, -120.0),  # Waypoint 2
            (35.0, -119.0),  # Waypoint 3
            (33.9425, -118.4081),  # KLAX
        ]

        results = service.get_elevations(waypoints)

        assert len(results) == 5
        # All should succeed
        for result in results:
            assert result.elevation_m > 0

"""Elevation service for terrain queries.

Provides elevation data for aircraft navigation and terrain collision detection.
Supports multiple elevation providers with caching for performance.

Typical usage:
    from airborne.terrain.elevation_service import ElevationService

    service = ElevationService()
    elevation = service.get_elevation(37.7749, -122.4194)  # San Francisco
    print(f"Elevation: {elevation:.1f}m")
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from airborne.physics.vectors import Vector3

logger = logging.getLogger(__name__)


@dataclass
class ElevationQuery:
    """Elevation query result.

    Attributes:
        latitude: Latitude in degrees
        longitude: Longitude in degrees
        elevation_m: Elevation in meters above sea level
        provider: Provider name that returned this elevation
        cached: Whether this result was from cache
    """

    latitude: float
    longitude: float
    elevation_m: float
    provider: str
    cached: bool = False


class IElevationProvider(ABC):
    """Abstract interface for elevation data providers.

    Elevation providers fetch elevation data from various sources
    (SRTM, USGS, Open-Elevation API, etc.) and return elevation in meters.

    Examples:
        >>> class MyProvider(IElevationProvider):
        ...     def get_name(self) -> str:
        ...         return "my_provider"
        ...     def get_elevation(self, lat: float, lon: float) -> float:
        ...         return 100.0  # meters
    """

    @abstractmethod
    def get_name(self) -> str:
        """Get provider name.

        Returns:
            Provider identifier (e.g., "srtm", "open_elevation")
        """

    @abstractmethod
    def get_elevation(self, latitude: float, longitude: float) -> float:
        """Get elevation at a specific coordinate.

        Args:
            latitude: Latitude in degrees (-90 to 90)
            longitude: Longitude in degrees (-180 to 180)

        Returns:
            Elevation in meters above sea level

        Raises:
            ValueError: If coordinates are invalid
            RuntimeError: If elevation data unavailable

        Examples:
            >>> elevation = provider.get_elevation(37.7749, -122.4194)
            >>> print(f"Elevation: {elevation:.1f}m")
        """

    def get_elevations(
        self, coordinates: list[tuple[float, float]]
    ) -> list[tuple[float, float, float]]:
        """Get elevations for multiple coordinates (batch query).

        Default implementation calls get_elevation() for each coordinate.
        Providers can override for more efficient batch processing.

        Args:
            coordinates: List of (latitude, longitude) tuples

        Returns:
            List of (latitude, longitude, elevation) tuples

        Examples:
            >>> coords = [(37.7749, -122.4194), (34.0522, -118.2437)]
            >>> results = provider.get_elevations(coords)
            >>> for lat, lon, elev in results:
            ...     print(f"({lat}, {lon}): {elev:.1f}m")
        """
        results = []
        for lat, lon in coordinates:
            try:
                elevation = self.get_elevation(lat, lon)
                results.append((lat, lon, elevation))
            except Exception as e:
                logger.warning("Failed to get elevation for (%f, %f): %s", lat, lon, e)
                results.append((lat, lon, 0.0))  # Default to sea level on error

        return results

    def is_available(self) -> bool:
        """Check if provider is available and functional.

        Returns:
            True if provider can be used, False otherwise

        Examples:
            >>> if provider.is_available():
            ...     elevation = provider.get_elevation(37.7749, -122.4194)
        """
        return True


class ElevationCache:
    """Cache for elevation queries.

    Simple in-memory cache using lat/lon as key. Uses LRU eviction
    when cache exceeds max size.

    Examples:
        >>> cache = ElevationCache(max_size=1000)
        >>> cache.set(37.7749, -122.4194, 10.0)
        >>> elevation = cache.get(37.7749, -122.4194)
        >>> print(f"Cached: {elevation}m")
    """

    def __init__(self, max_size: int = 10000, precision: int = 4) -> None:
        """Initialize elevation cache.

        Args:
            max_size: Maximum number of cached entries
            precision: Decimal places for coordinate rounding (for cache key)
        """
        self.max_size = max_size
        self.precision = precision
        self.cache: dict[tuple[float, float], float] = {}
        self.access_order: list[tuple[float, float]] = []

    def _make_key(self, latitude: float, longitude: float) -> tuple[float, float]:
        """Create cache key from coordinates.

        Args:
            latitude: Latitude in degrees
            longitude: Longitude in degrees

        Returns:
            Rounded (lat, lon) tuple
        """
        return (round(latitude, self.precision), round(longitude, self.precision))

    def get(self, latitude: float, longitude: float) -> float | None:
        """Get cached elevation.

        Args:
            latitude: Latitude in degrees
            longitude: Longitude in degrees

        Returns:
            Cached elevation in meters, or None if not found
        """
        key = self._make_key(latitude, longitude)

        if key in self.cache:
            # Move to end of access order (LRU)
            if key in self.access_order:
                self.access_order.remove(key)
            self.access_order.append(key)

            return self.cache[key]

        return None

    def set(self, latitude: float, longitude: float, elevation: float) -> None:
        """Cache elevation.

        Args:
            latitude: Latitude in degrees
            longitude: Longitude in degrees
            elevation: Elevation in meters
        """
        key = self._make_key(latitude, longitude)

        # Evict oldest entry if cache is full
        if len(self.cache) >= self.max_size and key not in self.cache:
            if self.access_order:
                oldest_key = self.access_order.pop(0)
                del self.cache[oldest_key]

        self.cache[key] = elevation

        # Update access order
        if key in self.access_order:
            self.access_order.remove(key)
        self.access_order.append(key)

    def clear(self) -> None:
        """Clear all cached elevations."""
        self.cache.clear()
        self.access_order.clear()

    def get_size(self) -> int:
        """Get current cache size.

        Returns:
            Number of cached entries
        """
        return len(self.cache)


class ElevationService:
    """Elevation service with provider management and caching.

    Manages multiple elevation providers and provides a unified interface
    for querying elevation data. Includes caching for performance.

    Examples:
        >>> from airborne.terrain.elevation_service import ElevationService
        >>> service = ElevationService()
        >>> service.add_provider(my_provider)
        >>> elevation = service.get_elevation(37.7749, -122.4194)
        >>> print(f"Elevation: {elevation:.1f}m")
    """

    def __init__(self, cache_size: int = 10000) -> None:
        """Initialize elevation service.

        Args:
            cache_size: Maximum number of cached elevation queries
        """
        self.providers: list[IElevationProvider] = []
        self.cache = ElevationCache(max_size=cache_size)
        logger.info("ElevationService initialized (cache_size=%d)", cache_size)

    def add_provider(self, provider: IElevationProvider) -> None:
        """Add an elevation provider.

        Args:
            provider: Elevation provider to add

        Examples:
            >>> service.add_provider(SRTMProvider())
            >>> service.add_provider(OpenElevationProvider())
        """
        self.providers.append(provider)
        logger.info("Added elevation provider: %s", provider.get_name())

    def remove_provider(self, provider_name: str) -> None:
        """Remove an elevation provider by name.

        Args:
            provider_name: Name of provider to remove
        """
        self.providers = [p for p in self.providers if p.get_name() != provider_name]
        logger.info("Removed elevation provider: %s", provider_name)

    def get_elevation(self, latitude: float, longitude: float) -> float:
        """Get elevation at a specific coordinate.

        Checks cache first, then queries providers in order.

        Args:
            latitude: Latitude in degrees (-90 to 90)
            longitude: Longitude in degrees (-180 to 180)

        Returns:
            Elevation in meters above sea level

        Raises:
            ValueError: If no providers available
            RuntimeError: If all providers fail

        Examples:
            >>> elevation = service.get_elevation(37.7749, -122.4194)
            >>> print(f"San Francisco elevation: {elevation:.1f}m")
        """
        # Check cache first
        cached_elevation = self.cache.get(latitude, longitude)
        if cached_elevation is not None:
            logger.debug("Cache hit for (%f, %f): %.1fm", latitude, longitude, cached_elevation)
            return cached_elevation

        # No providers available
        if not self.providers:
            raise ValueError("No elevation providers available")

        # Try providers in order
        for provider in self.providers:
            if not provider.is_available():
                continue

            try:
                elevation = provider.get_elevation(latitude, longitude)
                self.cache.set(latitude, longitude, elevation)
                logger.debug(
                    "Provider %s: (%f, %f) = %.1fm",
                    provider.get_name(),
                    latitude,
                    longitude,
                    elevation,
                )
                return elevation
            except Exception as e:
                logger.warning(
                    "Provider %s failed for (%f, %f): %s",
                    provider.get_name(),
                    latitude,
                    longitude,
                    e,
                )
                continue

        # All providers failed
        raise RuntimeError(f"All elevation providers failed for ({latitude}, {longitude})")

    def get_elevations(self, coordinates: list[tuple[float, float]]) -> list[ElevationQuery]:
        """Get elevations for multiple coordinates.

        Args:
            coordinates: List of (latitude, longitude) tuples

        Returns:
            List of ElevationQuery results

        Examples:
            >>> coords = [(37.7749, -122.4194), (34.0522, -118.2437)]
            >>> results = service.get_elevations(coords)
            >>> for query in results:
            ...     print(f"{query.latitude}, {query.longitude}: {query.elevation_m:.1f}m")
        """
        results = []

        for lat, lon in coordinates:
            try:
                # Check cache
                cached_elevation = self.cache.get(lat, lon)
                if cached_elevation is not None:
                    results.append(
                        ElevationQuery(
                            latitude=lat,
                            longitude=lon,
                            elevation_m=cached_elevation,
                            provider="cache",
                            cached=True,
                        )
                    )
                    continue

                # Query providers
                elevation = self.get_elevation(lat, lon)
                results.append(
                    ElevationQuery(
                        latitude=lat,
                        longitude=lon,
                        elevation_m=elevation,
                        provider=self.providers[0].get_name() if self.providers else "unknown",
                        cached=False,
                    )
                )
            except Exception as e:
                logger.warning("Failed to get elevation for (%f, %f): %s", lat, lon, e)
                results.append(
                    ElevationQuery(
                        latitude=lat,
                        longitude=lon,
                        elevation_m=0.0,
                        provider="none",
                        cached=False,
                    )
                )

        return results

    def get_elevation_at_position(self, position: Vector3) -> float:
        """Get elevation at a Vector3 position.

        Assumes position uses ECEF or similar coordinate system where
        x=longitude, z=latitude (in degrees).

        Args:
            position: Position vector (x=lon, z=lat in degrees)

        Returns:
            Elevation in meters

        Examples:
            >>> position = Vector3(-122.4194, 0, 37.7749)
            >>> elevation = service.get_elevation_at_position(position)
        """
        return self.get_elevation(position.z, position.x)

    def clear_cache(self) -> None:
        """Clear elevation cache.

        Examples:
            >>> service.clear_cache()
        """
        self.cache.clear()
        logger.info("Elevation cache cleared")

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics

        Examples:
            >>> stats = service.get_cache_stats()
            >>> print(f"Cache size: {stats['size']}/{stats['max_size']}")
        """
        return {
            "size": self.cache.get_size(),
            "max_size": self.cache.max_size,
            "providers": len(self.providers),
            "provider_names": [p.get_name() for p in self.providers],
        }

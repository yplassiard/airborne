"""SRTM elevation provider for terrain queries.

Provides elevation data from SRTM (Shuttle Radar Topography Mission) dataset.
Supports local tile caching and simple flat-earth fallback for testing.

Typical usage:
    from airborne.terrain.srtm_provider import SRTMProvider

    provider = SRTMProvider(cache_dir="data/terrain/cache")
    elevation = provider.get_elevation(37.7749, -122.4194)
    print(f"Elevation: {elevation:.1f}m")
"""

import logging
import math
from pathlib import Path

from airborne.terrain.elevation_service import IElevationProvider

logger = logging.getLogger(__name__)


class SimpleFlatEarthProvider(IElevationProvider):
    """Simple flat-earth elevation provider for testing/fallback.

    Returns elevation based on a simple mathematical model without
    requiring external data. Useful for testing and offline operation.

    The model returns:
    - 0m for oceans (rough latitude-based approximation)
    - Elevation based on distance from coast
    - Higher elevation near mountainous regions

    This is NOT geographically accurate! Use SRTMProvider for real data.

    Examples:
        >>> provider = SimpleFlatEarthProvider()
        >>> elevation = provider.get_elevation(37.7749, -122.4194)
        >>> print(f"Approximate elevation: {elevation:.1f}m")
    """

    def __init__(self) -> None:
        """Initialize simple flat-earth provider."""
        logger.info("SimpleFlatEarthProvider initialized")

    def get_name(self) -> str:
        """Get provider name."""
        return "flat_earth"

    def get_elevation(self, latitude: float, longitude: float) -> float:
        """Get approximate elevation using simple model.

        Args:
            latitude: Latitude in degrees (-90 to 90)
            longitude: Longitude in degrees (-180 to 180)

        Returns:
            Approximate elevation in meters

        Examples:
            >>> provider = SimpleFlatEarthProvider()
            >>> elevation = provider.get_elevation(37.7749, -122.4194)
        """
        # Very simple model based on latitude and longitude
        # This is for testing only - NOT geographically accurate!

        # Normalize coordinates
        lat = max(-90, min(90, latitude))
        lon = max(-180, min(180, longitude))

        # Simple heuristic: higher elevations near mountain ranges
        # Use sine waves to create some variation

        # Base elevation (sea level most places)
        base = 0.0

        # Add elevation based on latitude (polar regions and mountains)
        lat_factor = abs(lat) / 90.0  # 0 to 1
        base += lat_factor * 200  # Up to 200m based on latitude

        # Add some longitude variation (simulate mountain ranges)
        lon_variation = math.sin(lon * math.pi / 30) * 100

        # Combine factors
        elevation = base + lon_variation

        # Ensure non-negative
        elevation = max(0.0, elevation)

        return float(elevation)

    def is_available(self) -> bool:
        """Check if provider is available."""
        return True


class SRTMProvider(IElevationProvider):
    """SRTM elevation provider with local tile caching.

    Provides elevation data from SRTM dataset. Falls back to
    SimpleFlatEarthProvider if SRTM data is unavailable.

    SRTM Coverage:
    - Global coverage between 60°N and 56°S
    - 30m resolution (SRTM1) or 90m resolution (SRTM3)
    - Void-filled dataset available

    Note: This implementation uses a fallback provider by default.
    For production use with actual SRTM data, integrate with
    libraries like `elevation` or `srtm.py`.

    Examples:
        >>> provider = SRTMProvider(cache_dir="data/terrain/cache")
        >>> elevation = provider.get_elevation(37.7749, -122.4194)
        >>> print(f"Elevation: {elevation:.1f}m")
    """

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        use_fallback: bool = True,
    ) -> None:
        """Initialize SRTM provider.

        Args:
            cache_dir: Directory for caching SRTM tiles
            use_fallback: Use SimpleFlatEarthProvider as fallback
        """
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.use_fallback = use_fallback
        self.fallback_provider = SimpleFlatEarthProvider() if use_fallback else None

        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info("SRTMProvider initialized (cache_dir=%s)", self.cache_dir)
        else:
            logger.info("SRTMProvider initialized (no cache, fallback=%s)", use_fallback)

    def get_name(self) -> str:
        """Get provider name."""
        return "srtm"

    def get_elevation(self, latitude: float, longitude: float) -> float:
        """Get elevation from SRTM data.

        Args:
            latitude: Latitude in degrees (-90 to 90)
            longitude: Longitude in degrees (-180 to 180)

        Returns:
            Elevation in meters above sea level

        Raises:
            RuntimeError: If SRTM data unavailable and no fallback

        Examples:
            >>> provider = SRTMProvider()
            >>> elevation = provider.get_elevation(37.7749, -122.4194)
        """
        # Check if coordinates are in SRTM coverage area
        if not self._is_in_coverage(latitude, longitude):
            if self.fallback_provider:
                logger.debug(
                    "Coordinates (%f, %f) outside SRTM coverage, using fallback",
                    latitude,
                    longitude,
                )
                return self.fallback_provider.get_elevation(latitude, longitude)
            else:
                raise RuntimeError(
                    f"Coordinates ({latitude}, {longitude}) outside SRTM coverage area"
                )

        # Try to get SRTM elevation
        try:
            elevation = self._get_srtm_elevation(latitude, longitude)
            return elevation
        except Exception as e:
            logger.warning("SRTM query failed for (%f, %f): %s", latitude, longitude, e)

            # Fall back to simple provider
            if self.fallback_provider:
                logger.debug("Using fallback provider")
                return self.fallback_provider.get_elevation(latitude, longitude)
            else:
                raise RuntimeError(
                    f"Failed to get SRTM elevation for ({latitude}, {longitude}): {e}"
                ) from e

    def _is_in_coverage(self, latitude: float, longitude: float) -> bool:
        """Check if coordinates are within SRTM coverage.

        SRTM covers 60°N to 56°S.

        Args:
            latitude: Latitude in degrees
            longitude: Longitude in degrees

        Returns:
            True if within coverage area
        """
        return -56.0 <= latitude <= 60.0

    def _get_srtm_elevation(self, latitude: float, longitude: float) -> float:
        """Get elevation from SRTM tiles.

        This is a placeholder implementation. For production use,
        integrate with SRTM data libraries.

        Args:
            latitude: Latitude in degrees
            longitude: Longitude in degrees

        Returns:
            Elevation in meters

        Raises:
            RuntimeError: If SRTM data not available
        """
        # TODO: Integrate with actual SRTM library
        # Options:
        # 1. Use `elevation` Python library
        # 2. Use `srtm.py` library
        # 3. Query Open-Elevation API
        # 4. Use pre-downloaded SRTM tiles

        # For now, use fallback
        if self.fallback_provider:
            return self.fallback_provider.get_elevation(latitude, longitude)

        raise RuntimeError("SRTM data integration not yet implemented")

    def get_elevations(
        self, coordinates: list[tuple[float, float]]
    ) -> list[tuple[float, float, float]]:
        """Get elevations for multiple coordinates (batch query).

        Args:
            coordinates: List of (latitude, longitude) tuples

        Returns:
            List of (latitude, longitude, elevation) tuples

        Examples:
            >>> coords = [(37.7749, -122.4194), (34.0522, -118.2437)]
            >>> results = provider.get_elevations(coords)
        """
        # Batch queries could be optimized by loading SRTM tiles once
        # For now, use default implementation
        return super().get_elevations(coordinates)

    def is_available(self) -> bool:
        """Check if provider is available.

        Returns:
            True if provider can be used
        """
        # Provider is available if fallback is enabled
        return self.use_fallback or (self.cache_dir is not None and self.cache_dir.exists())


class ConstantElevationProvider(IElevationProvider):
    """Provider that returns a constant elevation.

    Useful for testing and flat terrain scenarios.

    Examples:
        >>> provider = ConstantElevationProvider(elevation=100.0)
        >>> elevation = provider.get_elevation(37.7749, -122.4194)
        >>> assert elevation == 100.0
    """

    def __init__(self, elevation: float = 0.0) -> None:
        """Initialize constant elevation provider.

        Args:
            elevation: Constant elevation to return (meters)
        """
        self.elevation = elevation
        logger.info("ConstantElevationProvider initialized (elevation=%.1fm)", elevation)

    def get_name(self) -> str:
        """Get provider name."""
        return "constant"

    def get_elevation(self, latitude: float, longitude: float) -> float:
        """Get constant elevation.

        Args:
            latitude: Latitude in degrees (ignored)
            longitude: Longitude in degrees (ignored)

        Returns:
            Constant elevation
        """
        return self.elevation

    def is_available(self) -> bool:
        """Check if provider is available."""
        return True

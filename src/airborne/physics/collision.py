"""Terrain collision detection and prevention.

Provides collision detection for terrain (ground/mountains) and other obstacles.
Integrates with elevation service to prevent aircraft from flying below terrain.

Typical usage:
    from airborne.physics.collision import TerrainCollisionDetector

    detector = TerrainCollisionDetector(elevation_service)
    collision = detector.check_terrain_collision(position, altitude_msl)
    if collision.is_colliding:
        print(f"TERRAIN WARNING: {collision.distance_to_terrain:.0f}m")
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from airborne.physics.vectors import Vector3

logger = logging.getLogger(__name__)


class CollisionType(Enum):
    """Types of collisions."""

    NONE = "none"  # No collision
    TERRAIN = "terrain"  # Terrain collision (ground/mountain)
    WATER = "water"  # Water collision (ocean/lake)
    OBSTACLE = "obstacle"  # Obstacle collision (building, etc.)


class CollisionSeverity(Enum):
    """Collision severity levels."""

    SAFE = "safe"  # Safe distance from terrain
    WARNING = "warning"  # Warning zone (< 500ft AGL)
    CAUTION = "caution"  # Caution zone (< 200ft AGL)
    CRITICAL = "critical"  # Critical zone (< 100ft AGL)
    COLLISION = "collision"  # Collision detected (< 0ft AGL)


@dataclass
class CollisionResult:
    """Result of collision detection.

    Attributes:
        is_colliding: True if collision detected
        collision_type: Type of collision
        severity: Collision severity
        terrain_elevation_m: Terrain elevation at position (MSL)
        aircraft_altitude_m: Aircraft altitude (MSL)
        distance_to_terrain: Distance to terrain (negative = below terrain)
        agl_altitude: Altitude above ground level (AGL)
        position: Position where collision was checked
    """

    is_colliding: bool
    collision_type: CollisionType
    severity: CollisionSeverity
    terrain_elevation_m: float
    aircraft_altitude_m: float
    distance_to_terrain: float
    agl_altitude: float
    position: Vector3


class TerrainCollisionDetector:
    """Terrain collision detector with elevation integration.

    Detects terrain collisions by comparing aircraft altitude with
    terrain elevation from elevation service.

    Examples:
        >>> from airborne.terrain import ElevationService, SimpleFlatEarthProvider
        >>> service = ElevationService()
        >>> service.add_provider(SimpleFlatEarthProvider())
        >>> detector = TerrainCollisionDetector(service)
        >>> result = detector.check_terrain_collision(
        ...     Vector3(-122.4194, 100, 37.7749),  # Position
        ...     100  # Altitude MSL
        ... )
        >>> if result.is_colliding:
        ...     print("TERRAIN COLLISION!")
    """

    def __init__(self, elevation_service: Any = None) -> None:
        """Initialize terrain collision detector.

        Args:
            elevation_service: ElevationService for terrain elevation queries
        """
        self.elevation_service = elevation_service
        self.collision_buffer_m = 0.0  # Safety buffer (default: ground level)
        self.warning_threshold_ft = 500.0  # Warning at 500ft AGL
        self.caution_threshold_ft = 200.0  # Caution at 200ft AGL
        self.critical_threshold_ft = 100.0  # Critical at 100ft AGL

        logger.info("TerrainCollisionDetector initialized")

    def check_terrain_collision(
        self,
        position: Vector3,
        altitude_msl: float,
        velocity: Vector3 | None = None,
    ) -> CollisionResult:
        """Check for terrain collision at current position.

        Args:
            position: Aircraft position (x=lon, y=alt, z=lat in degrees)
            altitude_msl: Aircraft altitude in meters (MSL)
            velocity: Aircraft velocity (optional, for predictive collision)

        Returns:
            CollisionResult with collision details

        Examples:
            >>> result = detector.check_terrain_collision(
            ...     Vector3(-122.4194, 100, 37.7749),
            ...     100
            ... )
            >>> print(f"AGL: {result.agl_altitude:.0f}m")
        """
        # Get terrain elevation at position
        terrain_elevation = 0.0
        if self.elevation_service:
            try:
                terrain_elevation = self.elevation_service.get_elevation_at_position(position)
            except Exception as e:
                logger.warning("Failed to get terrain elevation: %s", e)
                terrain_elevation = 0.0  # Default to sea level

        # Calculate distance to terrain
        distance_to_terrain = altitude_msl - terrain_elevation
        agl_altitude = distance_to_terrain  # AGL = MSL - terrain elevation

        # Determine if colliding
        is_colliding = distance_to_terrain <= self.collision_buffer_m

        # Determine collision type
        collision_type = CollisionType.NONE
        if is_colliding:
            if terrain_elevation <= 0:
                collision_type = CollisionType.WATER
            else:
                collision_type = CollisionType.TERRAIN

        # Determine severity
        severity = self._calculate_severity(agl_altitude)

        return CollisionResult(
            is_colliding=is_colliding,
            collision_type=collision_type,
            severity=severity,
            terrain_elevation_m=terrain_elevation,
            aircraft_altitude_m=altitude_msl,
            distance_to_terrain=distance_to_terrain,
            agl_altitude=agl_altitude,
            position=position,
        )

    def check_flight_path_collision(
        self,
        position: Vector3,
        altitude_msl: float,
        velocity: Vector3,
        lookahead_seconds: float = 30.0,
        num_samples: int = 10,
    ) -> list[CollisionResult]:
        """Check for terrain collisions along flight path.

        Predictive collision detection by sampling positions along
        the flight path.

        Args:
            position: Current aircraft position
            altitude_msl: Current altitude (MSL)
            velocity: Aircraft velocity (m/s)
            lookahead_seconds: How far ahead to check (seconds)
            num_samples: Number of sample points along path

        Returns:
            List of CollisionResults along flight path

        Examples:
            >>> results = detector.check_flight_path_collision(
            ...     Vector3(-122.4194, 100, 37.7749),
            ...     1000,
            ...     Vector3(0, -5, 50),  # Descending
            ...     lookahead_seconds=60
            ... )
            >>> for result in results:
            ...     if result.severity != CollisionSeverity.SAFE:
            ...         print(f"Warning at {result.agl_altitude:.0f}m AGL")
        """
        results = []

        for i in range(num_samples):
            # Calculate future position
            time_ahead = (lookahead_seconds / num_samples) * i
            future_position = Vector3(
                position.x + (velocity.x * time_ahead) / 111320,  # Approximate lon change
                position.y + (velocity.y * time_ahead),
                position.z + (velocity.z * time_ahead) / 110540,  # Approximate lat change
            )
            future_altitude = altitude_msl + (velocity.y * time_ahead)

            # Check collision at future position
            result = self.check_terrain_collision(future_position, future_altitude)
            results.append(result)

        return results

    def get_minimum_safe_altitude(self, position: Vector3, buffer_ft: float = 1000.0) -> float:
        """Get minimum safe altitude at position.

        Returns terrain elevation plus safety buffer.

        Args:
            position: Position to check
            buffer_ft: Safety buffer above terrain (feet)

        Returns:
            Minimum safe altitude in meters (MSL)

        Examples:
            >>> min_alt = detector.get_minimum_safe_altitude(
            ...     Vector3(-122.4194, 0, 37.7749),
            ...     buffer_ft=1000
            ... )
            >>> print(f"Minimum safe altitude: {min_alt:.0f}m MSL")
        """
        terrain_elevation = 0.0
        if self.elevation_service:
            try:
                terrain_elevation = self.elevation_service.get_elevation_at_position(position)
            except Exception as e:
                logger.warning("Failed to get terrain elevation: %s", e)
                terrain_elevation = 0.0

        buffer_m = buffer_ft * 0.3048  # Convert feet to meters
        return terrain_elevation + buffer_m

    def is_safe_to_descend(
        self,
        position: Vector3,
        current_altitude_msl: float,
        target_altitude_msl: float,
    ) -> bool:
        """Check if it's safe to descend to target altitude.

        Args:
            position: Current position
            current_altitude_msl: Current altitude (MSL)
            target_altitude_msl: Target altitude (MSL)

        Returns:
            True if safe to descend, False otherwise

        Examples:
            >>> safe = detector.is_safe_to_descend(
            ...     Vector3(-122.4194, 0, 37.7749),
            ...     current_altitude_msl=3000,
            ...     target_altitude_msl=1000
            ... )
            >>> if not safe:
            ...     print("Unsafe to descend - terrain too high")
        """
        min_safe_altitude = self.get_minimum_safe_altitude(position)
        return target_altitude_msl >= min_safe_altitude

    def set_warning_thresholds(
        self,
        warning_ft: float = 500.0,
        caution_ft: float = 200.0,
        critical_ft: float = 100.0,
    ) -> None:
        """Set warning threshold altitudes.

        Args:
            warning_ft: Warning threshold in feet AGL
            caution_ft: Caution threshold in feet AGL
            critical_ft: Critical threshold in feet AGL

        Examples:
            >>> detector.set_warning_thresholds(
            ...     warning_ft=1000,
            ...     caution_ft=500,
            ...     critical_ft=200
            ... )
        """
        self.warning_threshold_ft = warning_ft
        self.caution_threshold_ft = caution_ft
        self.critical_threshold_ft = critical_ft

    def _calculate_severity(self, agl_altitude: float) -> CollisionSeverity:
        """Calculate collision severity based on AGL altitude.

        Args:
            agl_altitude: Altitude above ground level (meters)

        Returns:
            CollisionSeverity level
        """
        agl_feet = agl_altitude * 3.28084  # Convert to feet

        if agl_feet <= 0:
            return CollisionSeverity.COLLISION
        elif agl_feet <= self.critical_threshold_ft:
            return CollisionSeverity.CRITICAL
        elif agl_feet <= self.caution_threshold_ft:
            return CollisionSeverity.CAUTION
        elif agl_feet <= self.warning_threshold_ft:
            return CollisionSeverity.WARNING
        else:
            return CollisionSeverity.SAFE


def prevent_terrain_collision(
    position: Vector3,
    altitude_msl: float,
    terrain_elevation_m: float,
    min_clearance_m: float = 10.0,
) -> float:
    """Prevent terrain collision by adjusting altitude.

    Utility function to clamp altitude above terrain.

    Args:
        position: Aircraft position
        altitude_msl: Desired altitude (MSL)
        terrain_elevation_m: Terrain elevation (MSL)
        min_clearance_m: Minimum clearance above terrain

    Returns:
        Safe altitude (MSL) that maintains clearance

    Examples:
        >>> safe_alt = prevent_terrain_collision(
        ...     Vector3(-122.4194, 0, 37.7749),
        ...     altitude_msl=50,
        ...     terrain_elevation_m=100,
        ...     min_clearance_m=10
        ... )
        >>> print(f"Safe altitude: {safe_alt:.0f}m")
    """
    min_safe_altitude = terrain_elevation_m + min_clearance_m

    if altitude_msl < min_safe_altitude:
        logger.warning(
            "Terrain collision prevented: adjusted altitude from %.1fm to %.1fm",
            altitude_msl,
            min_safe_altitude,
        )
        return min_safe_altitude

    return altitude_msl

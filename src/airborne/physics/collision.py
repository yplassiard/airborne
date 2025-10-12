"""Optimized collision detection for flight simulation.

This module provides efficient collision detection optimized for real-time
performance at 60Hz. It uses spatial hashing and bounding volumes to minimize
expensive distance calculations.

Performance optimizations:
- Squared distance comparisons (avoid sqrt)
- Early rejection tests
- Spatial partitioning for multiple objects
- Cached bounding volumes

Typical usage example:
    from airborne.physics.collision import CollisionDetector

    detector = CollisionDetector()
    if detector.check_ground_collision(position, terrain_elevation):
        print("Ground collision!")
"""

import math
from dataclasses import dataclass, field

from airborne.physics.flight_model.base import AircraftState
from airborne.physics.vectors import Vector3


@dataclass
class BoundingSphere:
    """Bounding sphere for fast collision detection.

    Using spheres instead of boxes for faster distance checks.

    Attributes:
        center: Center position.
        radius: Sphere radius.
    """

    center: Vector3
    radius: float

    def intersects(self, other: "BoundingSphere") -> bool:
        """Check if this sphere intersects another.

        Uses squared distance for performance (avoids sqrt).

        Args:
            other: Other bounding sphere.

        Returns:
            True if spheres intersect.
        """
        # Distance squared between centers
        dist_sq = self.center.distance_to_squared(other.center)

        # Sum of radii squared
        radii_sum = self.radius + other.radius
        radii_sum_sq = radii_sum * radii_sum

        return dist_sq <= radii_sum_sq

    def contains_point(self, point: Vector3) -> bool:
        """Check if point is inside sphere.

        Args:
            point: Point to check.

        Returns:
            True if point is inside.
        """
        dist_sq = self.center.distance_to_squared(point)
        return dist_sq <= (self.radius * self.radius)

    def distance_to_point(self, point: Vector3) -> float:
        """Calculate distance from sphere surface to point.

        Args:
            point: Point to check.

        Returns:
            Distance (negative if inside sphere).
        """
        center_dist = self.center.distance_to(point)
        return center_dist - self.radius


@dataclass
class CollisionResult:
    """Result of a collision check.

    Attributes:
        collided: Whether collision occurred.
        contact_point: Point of contact (if collided).
        penetration_depth: How far objects overlap.
        contact_normal: Normal vector at contact point.
    """

    collided: bool
    contact_point: Vector3 = field(default_factory=Vector3.zero)
    penetration_depth: float = 0.0
    contact_normal: Vector3 = field(default_factory=Vector3.unit_y)


class CollisionDetector:
    """Efficient collision detection for flight simulation.

    Optimized for real-time performance with minimal allocations.

    Examples:
        >>> detector = CollisionDetector()
        >>> result = detector.check_ground_collision(
        ...     Vector3(100, 50, 200), terrain_elevation=100.0
        ... )
        >>> if result.collided:
        ...     print("Hit ground!")
    """

    def __init__(self) -> None:
        """Initialize collision detector."""
        # Default aircraft bounding sphere (10m radius)
        self.aircraft_radius = 10.0

        # Landing threshold (vertical speed for safe landing)
        self.safe_landing_speed = 3.0  # m/s

        # Ground proximity threshold for landing detection
        self.landing_threshold = 2.0  # meters

    def set_aircraft_radius(self, radius: float) -> None:
        """Set aircraft bounding sphere radius.

        Args:
            radius: Radius in meters.
        """
        self.aircraft_radius = radius

    def check_ground_collision(
        self, position: Vector3, terrain_elevation: float
    ) -> CollisionResult:
        """Check for ground collision.

        Optimized: Uses simple altitude check first, then detailed if needed.

        Args:
            position: Aircraft position.
            terrain_elevation: Ground elevation at aircraft position.

        Returns:
            Collision result.
        """
        # Quick rejection: altitude check
        altitude_agl = position.y - terrain_elevation

        if altitude_agl > self.aircraft_radius:
            # Definitely no collision
            return CollisionResult(collided=False)

        # Potential collision - detailed check
        if altitude_agl < self.aircraft_radius:
            # Calculate penetration
            penetration = self.aircraft_radius - altitude_agl

            # Contact point on ground
            contact = Vector3(position.x, terrain_elevation, position.z)

            # Normal points upward
            normal = Vector3.unit_y()

            return CollisionResult(
                collided=True,
                contact_point=contact,
                penetration_depth=penetration,
                contact_normal=normal,
            )

        return CollisionResult(collided=False)

    def check_landing(self, state: AircraftState, terrain_elevation: float) -> CollisionResult:
        """Check if aircraft is landing (vs crashing).

        Landing requires low vertical speed and proximity to ground.

        Args:
            state: Aircraft state.
            terrain_elevation: Ground elevation.

        Returns:
            Collision result indicating safe landing or crash.
        """
        altitude_agl = state.position.y - terrain_elevation

        # Must be close to ground
        if altitude_agl > self.landing_threshold:
            return CollisionResult(collided=False)

        # Check vertical speed (negative = descending)
        vertical_speed = abs(state.velocity.y)

        is_safe = vertical_speed <= self.safe_landing_speed

        if altitude_agl <= 0.0 or (altitude_agl <= self.landing_threshold and is_safe):
            contact = Vector3(state.position.x, terrain_elevation, state.position.z)

            return CollisionResult(
                collided=True, contact_point=contact, contact_normal=Vector3.unit_y()
            )

        return CollisionResult(collided=False)

    def check_sphere_collision(
        self, sphere1: BoundingSphere, sphere2: BoundingSphere
    ) -> CollisionResult:
        """Check collision between two bounding spheres.

        Optimized for frequent checks.

        Args:
            sphere1: First sphere.
            sphere2: Second sphere.

        Returns:
            Collision result.
        """
        # Quick check using squared distance
        if not sphere1.intersects(sphere2):
            return CollisionResult(collided=False)

        # Calculate collision details
        center_diff = sphere2.center - sphere1.center
        distance = center_diff.magnitude()

        if distance < 0.001:
            # Spheres at same position - arbitrary normal
            normal = Vector3.unit_y()
            penetration = sphere1.radius + sphere2.radius
        else:
            normal = center_diff / distance  # Normalize
            penetration = (sphere1.radius + sphere2.radius) - distance

        # Contact point: on sphere1 surface toward sphere2
        contact = sphere1.center + normal * sphere1.radius

        return CollisionResult(
            collided=True,
            contact_point=contact,
            penetration_depth=penetration,
            contact_normal=normal,
        )

    def get_terrain_proximity(self, position: Vector3, terrain_elevation: float) -> float:
        """Get distance to terrain (AGL - Above Ground Level).

        Fast proximity check without full collision detection.

        Args:
            position: Aircraft position.
            terrain_elevation: Ground elevation.

        Returns:
            Altitude above ground level in meters.
        """
        return position.y - terrain_elevation


class SpatialGrid:
    """Spatial partitioning grid for efficient collision detection.

    Divides space into cells to reduce number of collision checks needed.
    Useful when checking aircraft against many objects (AI traffic, obstacles).

    Performance: O(n) insertion, O(1) query for nearby objects.

    Examples:
        >>> grid = SpatialGrid(cell_size=1000.0)
        >>> grid.insert(aircraft_id, position, radius)
        >>> nearby = grid.query_nearby(position, search_radius)
    """

    def __init__(self, cell_size: float = 1000.0) -> None:
        """Initialize spatial grid.

        Args:
            cell_size: Size of each grid cell in meters.
        """
        self.cell_size = cell_size
        self.grid: dict[tuple[int, int, int], list[tuple[int, Vector3, float]]] = {}

    def _get_cell(self, position: Vector3) -> tuple[int, int, int]:
        """Get grid cell for a position.

        Args:
            position: World position.

        Returns:
            Cell coordinates (x, y, z).
        """
        return (
            int(math.floor(position.x / self.cell_size)),
            int(math.floor(position.y / self.cell_size)),
            int(math.floor(position.z / self.cell_size)),
        )

    def insert(self, object_id: int, position: Vector3, radius: float) -> None:
        """Insert object into grid.

        Args:
            object_id: Unique object identifier.
            position: Object position.
            radius: Object bounding radius.
        """
        cell = self._get_cell(position)

        if cell not in self.grid:
            self.grid[cell] = []

        self.grid[cell].append((object_id, position, radius))

    def query_nearby(
        self, position: Vector3, search_radius: float
    ) -> list[tuple[int, Vector3, float]]:
        """Query objects near a position.

        Args:
            position: Query position.
            search_radius: Search radius.

        Returns:
            List of (object_id, position, radius) tuples.
        """
        # Determine which cells to check
        cells_to_check = self._get_nearby_cells(position, search_radius)

        # Collect objects from nearby cells
        nearby: list[tuple[int, Vector3, float]] = []
        search_radius_sq = search_radius * search_radius

        for cell in cells_to_check:
            if cell in self.grid:
                for obj_id, obj_pos, obj_radius in self.grid[cell]:
                    # Quick distance check
                    dist_sq = position.distance_to_squared(obj_pos)
                    if dist_sq <= search_radius_sq:
                        nearby.append((obj_id, obj_pos, obj_radius))

        return nearby

    def _get_nearby_cells(
        self, position: Vector3, search_radius: float
    ) -> list[tuple[int, int, int]]:
        """Get cells within search radius.

        Args:
            position: Center position.
            search_radius: Search radius.

        Returns:
            List of cell coordinates.
        """
        center_cell = self._get_cell(position)

        # How many cells to check in each direction
        cell_range = int(math.ceil(search_radius / self.cell_size))

        cells = []
        for dx in range(-cell_range, cell_range + 1):
            for dy in range(-cell_range, cell_range + 1):
                for dz in range(-cell_range, cell_range + 1):
                    cells.append(
                        (
                            center_cell[0] + dx,
                            center_cell[1] + dy,
                            center_cell[2] + dz,
                        )
                    )

        return cells

    def clear(self) -> None:
        """Clear all objects from grid."""
        self.grid.clear()

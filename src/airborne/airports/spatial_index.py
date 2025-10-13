"""Spatial index for fast airport queries.

Provides efficient spatial queries using a grid-based index.
Optimizes O(n) queries to O(1) average case for radius searches.

Typical usage:
    from airborne.airports import SpatialIndex

    index = SpatialIndex(cell_size_deg=1.0)
    for airport in airports:
        index.insert(airport.position, airport)

    nearby = index.query_radius(position, radius_nm=50)
"""

import logging
import math
from collections import defaultdict
from typing import Any, TypeVar

from airborne.physics.vectors import Vector3

logger = logging.getLogger(__name__)

T = TypeVar("T")


class SpatialIndex:
    """Grid-based spatial index for fast geographic queries.

    Divides world into grid cells for efficient spatial queries.
    Each cell is a lat/lon square of configurable size.

    Performance:
        - Insert: O(1)
        - Query radius: O(k) where k = cells overlapping query circle
        - Memory: O(n) where n = number of items

    Examples:
        >>> index = SpatialIndex(cell_size_deg=1.0)
        >>> index.insert(Vector3(-122.0, 0, 37.5), "KPAO")
        >>> nearby = index.query_radius(Vector3(-122.0, 0, 37.5), 10)
        >>> print(len(nearby))  # Items within 10 nm
    """

    def __init__(self, cell_size_deg: float = 1.0) -> None:
        """Initialize spatial index.

        Args:
            cell_size_deg: Size of grid cells in degrees (lat/lon).
                          Smaller = more memory, faster queries.
                          Larger = less memory, slower queries.
                          Recommended: 0.5-2.0 degrees.
        """
        self.cell_size_deg = cell_size_deg
        self.grid: dict[tuple[int, int], list[tuple[Vector3, Any]]] = defaultdict(list)
        self.item_count = 0

    def insert(self, position: Vector3, data: Any) -> None:
        """Insert an item into the spatial index.

        Args:
            position: Position (x=longitude, y=elevation, z=latitude)
            data: Associated data (e.g., Airport object)

        Examples:
            >>> index.insert(Vector3(-122.115, 2.1, 37.461), airport)
        """
        cell = self._get_cell(position)
        self.grid[cell].append((position, data))
        self.item_count += 1
        logger.debug("Inserted item at cell %s (total items: %d)", cell, self.item_count)

    def query_radius(self, position: Vector3, radius_nm: float) -> list[tuple[Any, float]]:
        """Query all items within radius of position.

        Args:
            position: Center position (x=longitude, y=elevation, z=latitude)
            radius_nm: Radius in nautical miles

        Returns:
            List of (data, distance_nm) tuples, sorted by distance

        Examples:
            >>> nearby = index.query_radius(Vector3(-122.0, 0, 37.5), 50)
            >>> for airport, distance in nearby:
            ...     print(f"{airport.name}: {distance:.1f} nm")
        """
        # Get all cells that could contain items within radius
        cells = self._get_cells_in_radius(position, radius_nm)

        logger.debug(
            "Querying %d cells for radius %.1f nm around (%.3f, %.3f)",
            len(cells),
            radius_nm,
            position.x,
            position.z,
        )

        # Check all items in those cells
        results: list[tuple[Any, float]] = []
        for cell in cells:
            if cell not in self.grid:
                continue

            for item_pos, item_data in self.grid[cell]:
                distance = self._haversine_distance_nm(position, item_pos)
                if distance <= radius_nm:
                    results.append((item_data, distance))

        # Sort by distance
        results.sort(key=lambda x: x[1])

        logger.debug("Found %d items within %.1f nm", len(results), radius_nm)
        return results

    def query_all(self) -> list[tuple[Vector3, Any]]:
        """Query all items in the index.

        Returns:
            List of (position, data) tuples for all items

        Examples:
            >>> all_items = index.query_all()
            >>> print(f"Total airports: {len(all_items)}")
        """
        results: list[tuple[Vector3, Any]] = []
        for items in self.grid.values():
            results.extend(items)
        return results

    def clear(self) -> None:
        """Remove all items from the index.

        Examples:
            >>> index.clear()
            >>> print(index.get_item_count())  # 0
        """
        self.grid.clear()
        self.item_count = 0
        logger.info("Cleared spatial index")

    def get_item_count(self) -> int:
        """Get total number of items in the index.

        Returns:
            Total number of items

        Examples:
            >>> count = index.get_item_count()
            >>> print(f"Index contains {count} items")
        """
        return self.item_count

    def get_cell_count(self) -> int:
        """Get number of cells with items.

        Returns:
            Number of non-empty cells

        Examples:
            >>> cells = index.get_cell_count()
            >>> items = index.get_item_count()
            >>> print(f"Average {items/cells:.1f} items per cell")
        """
        return len(self.grid)

    def _get_cell(self, position: Vector3) -> tuple[int, int]:
        """Get grid cell for a position.

        Args:
            position: Position (x=longitude, z=latitude)

        Returns:
            (cell_x, cell_z) tuple
        """
        cell_x = int(math.floor(position.x / self.cell_size_deg))
        cell_z = int(math.floor(position.z / self.cell_size_deg))
        return (cell_x, cell_z)

    def _get_cells_in_radius(self, position: Vector3, radius_nm: float) -> list[tuple[int, int]]:
        """Get all cells that could contain items within radius.

        Args:
            position: Center position
            radius_nm: Radius in nautical miles

        Returns:
            List of (cell_x, cell_z) tuples
        """
        # Convert radius from nautical miles to approximate degrees
        # At equator: 1 nm ≈ 0.0166667 degrees
        # Use slightly larger radius to ensure we don't miss edge cases
        radius_deg = (radius_nm / 60.0) * 1.5

        # Get center cell
        center_cell = self._get_cell(position)

        # Calculate cell range to check
        # Add 1 to ensure we check surrounding cells
        cell_radius = int(math.ceil(radius_deg / self.cell_size_deg)) + 1

        # Generate all cells in range
        cells: list[tuple[int, int]] = []
        for dx in range(-cell_radius, cell_radius + 1):
            for dz in range(-cell_radius, cell_radius + 1):
                cell = (center_cell[0] + dx, center_cell[1] + dz)
                cells.append(cell)

        return cells

    @staticmethod
    def _haversine_distance_nm(pos1: Vector3, pos2: Vector3) -> float:
        """Calculate great circle distance between two positions.

        Uses the Haversine formula for accuracy over large distances.

        Args:
            pos1: First position (x=longitude, z=latitude)
            pos2: Second position (x=longitude, z=latitude)

        Returns:
            Distance in nautical miles
        """
        # Convert to radians
        lat1, lon1 = math.radians(pos1.z), math.radians(pos1.x)
        lat2, lon2 = math.radians(pos2.z), math.radians(pos2.x)

        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))

        # Convert to nautical miles
        radius_nm = 3440.065  # Earth radius in nautical miles
        return c * radius_nm

"""Navigation waypoint definition.

This module provides the Waypoint class for defining points along a route
with altitude and speed constraints.
"""

from dataclasses import dataclass

from airborne.physics.vectors import Vector3


@dataclass
class Waypoint:
    """Navigation waypoint.

    A waypoint represents a point along a route with position and optional
    altitude and speed targets.

    Attributes:
        position: 3D position (lat/lon/alt in Vector3)
        altitude_ft: Target altitude at waypoint in feet MSL
        speed_kts: Target speed at waypoint in knots
        name: Optional waypoint name or identifier

    Examples:
        >>> waypoint = Waypoint(
        ...     position=Vector3(37.6213, -122.3790, 0),
        ...     altitude_ft=3000,
        ...     speed_kts=120,
        ...     name="KPAO"
        ... )
    """

    position: Vector3
    altitude_ft: float
    speed_kts: float
    name: str = ""

    def __str__(self) -> str:
        """Return string representation of waypoint.

        Returns:
            String with name and altitude/speed if set
        """
        if self.name:
            return f"{self.name} ({self.altitude_ft:.0f}ft, {self.speed_kts:.0f}kts)"
        return f"WPT ({self.altitude_ft:.0f}ft, {self.speed_kts:.0f}kts)"

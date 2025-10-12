"""Vector mathematics utilities for 3D physics.

This module provides vector operations used throughout the physics system,
including position, velocity, acceleration, and force calculations.

Typical usage example:
    from airborne.physics.vectors import Vector3

    position = Vector3(100.0, 500.0, 200.0)
    velocity = Vector3(50.0, 0.0, 10.0)
    new_position = position + velocity * dt
"""

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass
class Vector3:
    """3D vector with common operations.

    Represents a point or direction in 3D space. Used for positions,
    velocities, accelerations, and forces.

    Attributes:
        x: X component (east-west).
        y: Y component (altitude, up-down).
        z: Z component (north-south).

    Examples:
        >>> v1 = Vector3(1.0, 2.0, 3.0)
        >>> v2 = Vector3(4.0, 5.0, 6.0)
        >>> v3 = v1 + v2
        >>> print(v3)
        Vector3(x=5.0, y=7.0, z=9.0)
    """

    x: float
    y: float
    z: float

    def __add__(self, other: "Vector3") -> "Vector3":
        """Add two vectors component-wise.

        Args:
            other: Vector to add.

        Returns:
            Sum of the two vectors.

        Examples:
            >>> v1 = Vector3(1.0, 2.0, 3.0)
            >>> v2 = Vector3(4.0, 5.0, 6.0)
            >>> v3 = v1 + v2
        """
        return Vector3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vector3") -> "Vector3":
        """Subtract two vectors component-wise.

        Args:
            other: Vector to subtract.

        Returns:
            Difference of the two vectors.
        """
        return Vector3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> "Vector3":
        """Multiply vector by scalar.

        Args:
            scalar: Scalar value.

        Returns:
            Scaled vector.

        Examples:
            >>> v = Vector3(1.0, 2.0, 3.0)
            >>> v2 = v * 2.0
        """
        return Vector3(self.x * scalar, self.y * scalar, self.z * scalar)

    def __rmul__(self, scalar: float) -> "Vector3":
        """Multiply scalar by vector (reverse multiplication).

        Args:
            scalar: Scalar value.

        Returns:
            Scaled vector.
        """
        return self.__mul__(scalar)

    def __truediv__(self, scalar: float) -> "Vector3":
        """Divide vector by scalar.

        Args:
            scalar: Scalar value.

        Returns:
            Scaled vector.

        Raises:
            ZeroDivisionError: If scalar is zero.
        """
        if scalar == 0:
            raise ZeroDivisionError("Cannot divide vector by zero")
        return Vector3(self.x / scalar, self.y / scalar, self.z / scalar)

    def __neg__(self) -> "Vector3":
        """Negate vector (reverse direction).

        Returns:
            Negated vector.
        """
        return Vector3(-self.x, -self.y, -self.z)

    def magnitude(self) -> float:
        """Calculate the magnitude (length) of the vector.

        Returns:
            Vector magnitude.

        Examples:
            >>> v = Vector3(3.0, 4.0, 0.0)
            >>> v.magnitude()
            5.0
        """
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def magnitude_squared(self) -> float:
        """Calculate the squared magnitude (avoids sqrt for performance).

        Returns:
            Squared magnitude.

        Note:
            Useful for distance comparisons without expensive sqrt.
        """
        return self.x * self.x + self.y * self.y + self.z * self.z

    def normalized(self) -> "Vector3":
        """Return a unit vector in the same direction.

        Returns:
            Normalized vector with magnitude 1.0.

        Raises:
            ValueError: If magnitude is zero.

        Examples:
            >>> v = Vector3(3.0, 4.0, 0.0)
            >>> unit = v.normalized()
            >>> unit.magnitude()
            1.0
        """
        mag = self.magnitude()
        if mag == 0:
            raise ValueError("Cannot normalize zero vector")
        return self / mag

    def dot(self, other: "Vector3") -> float:
        """Calculate dot product with another vector.

        Args:
            other: Other vector.

        Returns:
            Dot product.

        Examples:
            >>> v1 = Vector3(1.0, 0.0, 0.0)
            >>> v2 = Vector3(0.0, 1.0, 0.0)
            >>> v1.dot(v2)
            0.0
        """
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: "Vector3") -> "Vector3":
        """Calculate cross product with another vector.

        Args:
            other: Other vector.

        Returns:
            Cross product vector (perpendicular to both).

        Examples:
            >>> v1 = Vector3(1.0, 0.0, 0.0)
            >>> v2 = Vector3(0.0, 1.0, 0.0)
            >>> v3 = v1.cross(v2)
            >>> # v3 points in z direction
        """
        return Vector3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def distance_to(self, other: "Vector3") -> float:
        """Calculate distance to another vector.

        Args:
            other: Other vector (point).

        Returns:
            Euclidean distance.

        Examples:
            >>> p1 = Vector3(0.0, 0.0, 0.0)
            >>> p2 = Vector3(3.0, 4.0, 0.0)
            >>> p1.distance_to(p2)
            5.0
        """
        diff = self - other
        return diff.magnitude()

    def distance_to_squared(self, other: "Vector3") -> float:
        """Calculate squared distance (avoids sqrt for performance).

        Args:
            other: Other vector (point).

        Returns:
            Squared distance.
        """
        diff = self - other
        return diff.magnitude_squared()

    def lerp(self, other: "Vector3", t: float) -> "Vector3":
        """Linear interpolation between this vector and another.

        Args:
            other: Target vector.
            t: Interpolation factor (0.0 to 1.0).

        Returns:
            Interpolated vector.

        Examples:
            >>> v1 = Vector3(0.0, 0.0, 0.0)
            >>> v2 = Vector3(10.0, 10.0, 10.0)
            >>> mid = v1.lerp(v2, 0.5)
            >>> # mid = Vector3(5.0, 5.0, 5.0)
        """
        return self + (other - self) * t

    def to_array(self) -> npt.NDArray[np.float64]:
        """Convert to numpy array.

        Returns:
            Numpy array [x, y, z].

        Examples:
            >>> v = Vector3(1.0, 2.0, 3.0)
            >>> arr = v.to_array()
        """
        return np.array([self.x, self.y, self.z], dtype=np.float64)

    @classmethod
    def from_array(cls, arr: npt.NDArray[np.float64]) -> "Vector3":
        """Create vector from numpy array.

        Args:
            arr: Numpy array with at least 3 elements.

        Returns:
            Vector3 instance.

        Examples:
            >>> arr = np.array([1.0, 2.0, 3.0])
            >>> v = Vector3.from_array(arr)
        """
        return cls(float(arr[0]), float(arr[1]), float(arr[2]))

    @classmethod
    def zero(cls) -> "Vector3":
        """Create a zero vector (0, 0, 0).

        Returns:
            Zero vector.
        """
        return cls(0.0, 0.0, 0.0)

    @classmethod
    def one(cls) -> "Vector3":
        """Create a vector with all components set to 1.

        Returns:
            Vector (1, 1, 1).
        """
        return cls(1.0, 1.0, 1.0)

    @classmethod
    def unit_x(cls) -> "Vector3":
        """Create a unit vector in X direction.

        Returns:
            Vector (1, 0, 0).
        """
        return cls(1.0, 0.0, 0.0)

    @classmethod
    def unit_y(cls) -> "Vector3":
        """Create a unit vector in Y direction (up).

        Returns:
            Vector (0, 1, 0).
        """
        return cls(0.0, 1.0, 0.0)

    @classmethod
    def unit_z(cls) -> "Vector3":
        """Create a unit vector in Z direction.

        Returns:
            Vector (0, 0, 1).
        """
        return cls(0.0, 0.0, 1.0)

    def __str__(self) -> str:
        """String representation of the vector."""
        return f"Vector3(x={self.x:.2f}, y={self.y:.2f}, z={self.z:.2f})"

    def __repr__(self) -> str:
        """Detailed representation of the vector."""
        return f"Vector3(x={self.x}, y={self.y}, z={self.z})"

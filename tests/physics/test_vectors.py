"""Tests for Vector3 class."""


import numpy as np
import pytest

from airborne.physics.vectors import Vector3


class TestVector3Creation:
    """Test Vector3 creation and factory methods."""

    def test_constructor_with_values(self) -> None:
        """Test constructor with explicit values."""
        v = Vector3(1.0, 2.0, 3.0)
        assert v.x == 1.0
        assert v.y == 2.0
        assert v.z == 3.0

    def test_zero_factory(self) -> None:
        """Test zero() factory method."""
        v = Vector3.zero()
        assert v.x == 0.0
        assert v.y == 0.0
        assert v.z == 0.0

    def test_one_factory(self) -> None:
        """Test one() factory method."""
        v = Vector3.one()
        assert v.x == 1.0
        assert v.y == 1.0
        assert v.z == 1.0

    def test_unit_x_factory(self) -> None:
        """Test unit_x() factory method."""
        v = Vector3.unit_x()
        assert v.x == 1.0
        assert v.y == 0.0
        assert v.z == 0.0

    def test_unit_y_factory(self) -> None:
        """Test unit_y() factory method."""
        v = Vector3.unit_y()
        assert v.x == 0.0
        assert v.y == 1.0
        assert v.z == 0.0

    def test_unit_z_factory(self) -> None:
        """Test unit_z() factory method."""
        v = Vector3.unit_z()
        assert v.x == 0.0
        assert v.y == 0.0
        assert v.z == 1.0


class TestVector3Operations:
    """Test Vector3 arithmetic operations."""

    def test_addition(self) -> None:
        """Test vector addition."""
        v1 = Vector3(1.0, 2.0, 3.0)
        v2 = Vector3(4.0, 5.0, 6.0)
        result = v1 + v2
        assert result.x == 5.0
        assert result.y == 7.0
        assert result.z == 9.0

    def test_subtraction(self) -> None:
        """Test vector subtraction."""
        v1 = Vector3(4.0, 5.0, 6.0)
        v2 = Vector3(1.0, 2.0, 3.0)
        result = v1 - v2
        assert result.x == 3.0
        assert result.y == 3.0
        assert result.z == 3.0

    def test_scalar_multiplication(self) -> None:
        """Test vector-scalar multiplication."""
        v = Vector3(1.0, 2.0, 3.0)
        result = v * 2.0
        assert result.x == 2.0
        assert result.y == 4.0
        assert result.z == 6.0

    def test_scalar_division(self) -> None:
        """Test vector-scalar division."""
        v = Vector3(2.0, 4.0, 6.0)
        result = v / 2.0
        assert result.x == 1.0
        assert result.y == 2.0
        assert result.z == 3.0

    def test_negation(self) -> None:
        """Test vector negation."""
        v = Vector3(1.0, -2.0, 3.0)
        result = -v
        assert result.x == -1.0
        assert result.y == 2.0
        assert result.z == -3.0

    def test_equality(self) -> None:
        """Test vector equality."""
        v1 = Vector3(1.0, 2.0, 3.0)
        v2 = Vector3(1.0, 2.0, 3.0)
        v3 = Vector3(1.0, 2.0, 3.1)
        assert v1 == v2
        assert v1 != v3


class TestVector3Magnitude:
    """Test Vector3 magnitude calculations."""

    def test_magnitude_squared(self) -> None:
        """Test squared magnitude calculation."""
        v = Vector3(3.0, 4.0, 0.0)
        assert v.magnitude_squared() == 25.0

    def test_magnitude(self) -> None:
        """Test magnitude calculation."""
        v = Vector3(3.0, 4.0, 0.0)
        assert v.magnitude() == 5.0

    def test_magnitude_3d(self) -> None:
        """Test magnitude with 3D vector."""
        v = Vector3(1.0, 2.0, 2.0)
        assert v.magnitude() == pytest.approx(3.0)

    def test_normalize(self) -> None:
        """Test vector normalization."""
        v = Vector3(3.0, 4.0, 0.0)
        normalized = v.normalized()
        assert normalized.magnitude() == pytest.approx(1.0)
        assert normalized.x == pytest.approx(0.6)
        assert normalized.y == pytest.approx(0.8)

    def test_normalize_zero_vector(self) -> None:
        """Test normalizing zero vector raises error."""
        v = Vector3.zero()
        with pytest.raises(ValueError):
            v.normalized()


class TestVector3Products:
    """Test Vector3 dot and cross products."""

    def test_dot_product(self) -> None:
        """Test dot product calculation."""
        v1 = Vector3(1.0, 2.0, 3.0)
        v2 = Vector3(4.0, 5.0, 6.0)
        result = v1.dot(v2)
        assert result == 32.0  # 1*4 + 2*5 + 3*6

    def test_dot_product_perpendicular(self) -> None:
        """Test dot product of perpendicular vectors is zero."""
        v1 = Vector3(1.0, 0.0, 0.0)
        v2 = Vector3(0.0, 1.0, 0.0)
        result = v1.dot(v2)
        assert result == pytest.approx(0.0)

    def test_cross_product(self) -> None:
        """Test cross product calculation."""
        v1 = Vector3(1.0, 0.0, 0.0)
        v2 = Vector3(0.0, 1.0, 0.0)
        result = v1.cross(v2)
        assert result == Vector3(0.0, 0.0, 1.0)

    def test_cross_product_anticommutative(self) -> None:
        """Test cross product anti-commutativity."""
        v1 = Vector3(1.0, 2.0, 3.0)
        v2 = Vector3(4.0, 5.0, 6.0)
        result1 = v1.cross(v2)
        result2 = v2.cross(v1)
        assert result1 == -result2


class TestVector3Distance:
    """Test Vector3 distance calculations."""

    def test_distance_to(self) -> None:
        """Test distance calculation."""
        v1 = Vector3(0.0, 0.0, 0.0)
        v2 = Vector3(3.0, 4.0, 0.0)
        assert v1.distance_to(v2) == 5.0

    def test_distance_to_squared(self) -> None:
        """Test squared distance calculation (performance optimization)."""
        v1 = Vector3(0.0, 0.0, 0.0)
        v2 = Vector3(3.0, 4.0, 0.0)
        assert v1.distance_to_squared(v2) == 25.0

    def test_distance_symmetric(self) -> None:
        """Test distance is symmetric."""
        v1 = Vector3(1.0, 2.0, 3.0)
        v2 = Vector3(4.0, 5.0, 6.0)
        assert v1.distance_to(v2) == v2.distance_to(v1)


class TestVector3Interpolation:
    """Test Vector3 interpolation methods."""

    def test_lerp_at_start(self) -> None:
        """Test lerp at t=0 returns start vector."""
        start = Vector3(0.0, 0.0, 0.0)
        end = Vector3(10.0, 10.0, 10.0)
        result = start.lerp(end, 0.0)
        assert result == start

    def test_lerp_at_end(self) -> None:
        """Test lerp at t=1 returns end vector."""
        start = Vector3(0.0, 0.0, 0.0)
        end = Vector3(10.0, 10.0, 10.0)
        result = start.lerp(end, 1.0)
        assert result == end

    def test_lerp_midpoint(self) -> None:
        """Test lerp at t=0.5 returns midpoint."""
        start = Vector3(0.0, 0.0, 0.0)
        end = Vector3(10.0, 10.0, 10.0)
        result = start.lerp(end, 0.5)
        assert result == Vector3(5.0, 5.0, 5.0)

    def test_lerp_arbitrary(self) -> None:
        """Test lerp with arbitrary t value."""
        start = Vector3(0.0, 0.0, 0.0)
        end = Vector3(10.0, 20.0, 30.0)
        result = start.lerp(end, 0.25)
        assert result == Vector3(2.5, 5.0, 7.5)


class TestVector3Conversion:
    """Test Vector3 conversion methods."""

    def test_to_array(self) -> None:
        """Test conversion to numpy array."""
        v = Vector3(1.0, 2.0, 3.0)
        arr = v.to_array()
        assert isinstance(arr, np.ndarray)
        assert arr.shape == (3,)
        assert arr[0] == 1.0
        assert arr[1] == 2.0
        assert arr[2] == 3.0

    def test_from_array(self) -> None:
        """Test creation from numpy array."""
        arr = np.array([1.0, 2.0, 3.0])
        v = Vector3.from_array(arr)
        assert v.x == 1.0
        assert v.y == 2.0
        assert v.z == 3.0

    def test_round_trip_conversion(self) -> None:
        """Test round-trip conversion to/from array."""
        original = Vector3(1.5, 2.7, 3.9)
        arr = original.to_array()
        converted = Vector3.from_array(arr)
        assert converted == original

    def test_str_representation(self) -> None:
        """Test string representation."""
        v = Vector3(1.0, 2.0, 3.0)
        s = str(v)
        assert "1.0" in s
        assert "2.0" in s
        assert "3.0" in s


class TestVector3EdgeCases:
    """Test Vector3 edge cases and error handling."""

    def test_division_by_zero(self) -> None:
        """Test division by zero raises error."""
        v = Vector3(1.0, 2.0, 3.0)
        with pytest.raises(ZeroDivisionError):
            _ = v / 0.0

    def test_from_array_wrong_size(self) -> None:
        """Test from_array with wrong size raises error."""
        arr = np.array([1.0, 2.0])  # Only 2 elements
        with pytest.raises((ValueError, IndexError)):
            Vector3.from_array(arr)

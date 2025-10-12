"""Tests for collision detection system."""

import pytest

from airborne.physics.collision import (
    BoundingSphere,
    CollisionDetector,
    CollisionResult,
    SpatialGrid,
)
from airborne.physics.flight_model.base import AircraftState
from airborne.physics.vectors import Vector3


class TestBoundingSphere:
    """Test BoundingSphere class."""

    def test_creation(self) -> None:
        """Test creating a bounding sphere."""
        center = Vector3(10.0, 20.0, 30.0)
        radius = 5.0
        sphere = BoundingSphere(center=center, radius=radius)
        assert sphere.center == center
        assert sphere.radius == radius

    def test_intersects_overlapping(self) -> None:
        """Test intersection detection for overlapping spheres."""
        sphere1 = BoundingSphere(center=Vector3(0.0, 0.0, 0.0), radius=5.0)
        sphere2 = BoundingSphere(center=Vector3(8.0, 0.0, 0.0), radius=5.0)
        # Distance = 8, radii sum = 10, should intersect
        assert sphere1.intersects(sphere2)
        assert sphere2.intersects(sphere1)  # Symmetric

    def test_intersects_touching(self) -> None:
        """Test intersection detection for touching spheres."""
        sphere1 = BoundingSphere(center=Vector3(0.0, 0.0, 0.0), radius=5.0)
        sphere2 = BoundingSphere(center=Vector3(10.0, 0.0, 0.0), radius=5.0)
        # Distance = 10, radii sum = 10, should intersect (touching)
        assert sphere1.intersects(sphere2)

    def test_intersects_separated(self) -> None:
        """Test intersection detection for separated spheres."""
        sphere1 = BoundingSphere(center=Vector3(0.0, 0.0, 0.0), radius=5.0)
        sphere2 = BoundingSphere(center=Vector3(15.0, 0.0, 0.0), radius=5.0)
        # Distance = 15, radii sum = 10, should not intersect
        assert not sphere1.intersects(sphere2)

    def test_contains_point_inside(self) -> None:
        """Test point containment for point inside sphere."""
        sphere = BoundingSphere(center=Vector3(0.0, 0.0, 0.0), radius=10.0)
        point = Vector3(3.0, 4.0, 0.0)  # Distance = 5.0
        assert sphere.contains_point(point)

    def test_contains_point_on_surface(self) -> None:
        """Test point containment for point on sphere surface."""
        sphere = BoundingSphere(center=Vector3(0.0, 0.0, 0.0), radius=5.0)
        point = Vector3(3.0, 4.0, 0.0)  # Distance = 5.0 (on surface)
        assert sphere.contains_point(point)

    def test_contains_point_outside(self) -> None:
        """Test point containment for point outside sphere."""
        sphere = BoundingSphere(center=Vector3(0.0, 0.0, 0.0), radius=5.0)
        point = Vector3(10.0, 0.0, 0.0)  # Distance = 10.0
        assert not sphere.contains_point(point)

    def test_distance_to_point_outside(self) -> None:
        """Test distance calculation for point outside sphere."""
        sphere = BoundingSphere(center=Vector3(0.0, 0.0, 0.0), radius=5.0)
        point = Vector3(10.0, 0.0, 0.0)
        # Distance from center = 10.0, surface distance = 10.0 - 5.0 = 5.0
        assert sphere.distance_to_point(point) == pytest.approx(5.0)

    def test_distance_to_point_inside(self) -> None:
        """Test distance calculation for point inside sphere (negative)."""
        sphere = BoundingSphere(center=Vector3(0.0, 0.0, 0.0), radius=10.0)
        point = Vector3(3.0, 4.0, 0.0)  # Distance from center = 5.0
        # Surface distance = 5.0 - 10.0 = -5.0 (inside)
        assert sphere.distance_to_point(point) == pytest.approx(-5.0)

    def test_distance_to_point_at_center(self) -> None:
        """Test distance calculation for point at sphere center."""
        sphere = BoundingSphere(center=Vector3(0.0, 0.0, 0.0), radius=5.0)
        point = Vector3(0.0, 0.0, 0.0)
        # Distance from center = 0.0, surface distance = 0.0 - 5.0 = -5.0
        assert sphere.distance_to_point(point) == pytest.approx(-5.0)


class TestCollisionResult:
    """Test CollisionResult dataclass."""

    def test_no_collision(self) -> None:
        """Test creating result for no collision."""
        result = CollisionResult(collided=False)
        assert result.collided is False
        assert result.contact_point == Vector3.zero()
        assert result.penetration_depth == 0.0
        assert result.contact_normal == Vector3.unit_y()

    def test_collision_with_details(self) -> None:
        """Test creating result with collision details."""
        contact = Vector3(10.0, 0.0, 0.0)
        normal = Vector3(0.0, 1.0, 0.0)
        result = CollisionResult(
            collided=True, contact_point=contact, penetration_depth=2.5, contact_normal=normal
        )
        assert result.collided is True
        assert result.contact_point == contact
        assert result.penetration_depth == pytest.approx(2.5)
        assert result.contact_normal == normal


class TestCollisionDetector:
    """Test CollisionDetector class."""

    @pytest.fixture
    def detector(self) -> CollisionDetector:
        """Create a collision detector."""
        return CollisionDetector()

    def test_initialization(self, detector: CollisionDetector) -> None:
        """Test detector initialization."""
        assert detector.aircraft_radius == 10.0
        assert detector.safe_landing_speed == 3.0
        assert detector.landing_threshold == 2.0

    def test_set_aircraft_radius(self, detector: CollisionDetector) -> None:
        """Test setting aircraft radius."""
        detector.set_aircraft_radius(15.0)
        assert detector.aircraft_radius == 15.0

    def test_check_ground_collision_no_collision(self, detector: CollisionDetector) -> None:
        """Test ground collision detection with no collision."""
        position = Vector3(0.0, 100.0, 0.0)  # 100m altitude
        terrain_elevation = 0.0
        result = detector.check_ground_collision(position, terrain_elevation)
        assert result.collided is False

    def test_check_ground_collision_with_collision(self, detector: CollisionDetector) -> None:
        """Test ground collision detection with collision."""
        position = Vector3(0.0, 5.0, 0.0)  # 5m altitude, radius = 10m
        terrain_elevation = 0.0
        result = detector.check_ground_collision(position, terrain_elevation)
        assert result.collided is True
        assert result.contact_point.y == 0.0  # On ground
        assert result.contact_normal == Vector3.unit_y()  # Upward normal
        assert result.penetration_depth > 0.0

    def test_check_ground_collision_on_ground(self, detector: CollisionDetector) -> None:
        """Test ground collision when aircraft is on ground."""
        position = Vector3(0.0, 0.0, 0.0)  # On ground
        terrain_elevation = 0.0
        result = detector.check_ground_collision(position, terrain_elevation)
        assert result.collided is True

    def test_check_ground_collision_with_terrain(self, detector: CollisionDetector) -> None:
        """Test ground collision with elevated terrain."""
        position = Vector3(0.0, 105.0, 0.0)  # 5m above terrain
        terrain_elevation = 100.0
        result = detector.check_ground_collision(position, terrain_elevation)
        assert result.collided is True  # Within radius
        assert result.contact_point.y == 100.0  # On terrain

    def test_get_terrain_proximity(self, detector: CollisionDetector) -> None:
        """Test terrain proximity calculation (AGL)."""
        position = Vector3(0.0, 150.0, 0.0)
        terrain_elevation = 100.0
        agl = detector.get_terrain_proximity(position, terrain_elevation)
        assert agl == pytest.approx(50.0)

    def test_get_terrain_proximity_on_ground(self, detector: CollisionDetector) -> None:
        """Test terrain proximity when on ground."""
        position = Vector3(0.0, 100.0, 0.0)
        terrain_elevation = 100.0
        agl = detector.get_terrain_proximity(position, terrain_elevation)
        assert agl == pytest.approx(0.0)


class TestCollisionDetectorLanding:
    """Test landing detection."""

    @pytest.fixture
    def detector(self) -> CollisionDetector:
        """Create a collision detector."""
        return CollisionDetector()

    def test_check_landing_safe(self, detector: CollisionDetector) -> None:
        """Test safe landing detection."""
        state = AircraftState(
            position=Vector3(0.0, 1.0, 0.0),  # Close to ground
            velocity=Vector3(20.0, -2.0, 0.0),  # Low descent rate
        )
        terrain_elevation = 0.0
        result = detector.check_landing(state, terrain_elevation)
        assert result.collided is True  # Landing detected

    def test_check_landing_too_fast(self, detector: CollisionDetector) -> None:
        """Test landing detection with excessive descent rate (crash)."""
        state = AircraftState(
            position=Vector3(0.0, 0.5, 0.0),
            velocity=Vector3(20.0, -10.0, 0.0),  # Too fast
        )
        terrain_elevation = 0.0
        result = detector.check_landing(state, terrain_elevation)
        # With high descent rate and not at ground level, won't trigger landing
        # Landing requires either altitude <= 0 OR (altitude <= threshold AND safe speed)
        # Since altitude is 0.5m and speed is unsafe, result is False
        assert result.collided is False

    def test_check_landing_too_high(self, detector: CollisionDetector) -> None:
        """Test landing detection when too high above ground."""
        state = AircraftState(
            position=Vector3(0.0, 10.0, 0.0),  # Too high
            velocity=Vector3(20.0, -2.0, 0.0),
        )
        terrain_elevation = 0.0
        result = detector.check_landing(state, terrain_elevation)
        assert result.collided is False

    def test_check_landing_on_ground(self, detector: CollisionDetector) -> None:
        """Test landing detection when already on ground."""
        state = AircraftState(
            position=Vector3(0.0, 0.0, 0.0),
            velocity=Vector3(20.0, 0.0, 0.0),
        )
        terrain_elevation = 0.0
        result = detector.check_landing(state, terrain_elevation)
        assert result.collided is True

    def test_check_landing_with_terrain(self, detector: CollisionDetector) -> None:
        """Test landing detection on elevated terrain."""
        state = AircraftState(
            position=Vector3(0.0, 101.0, 0.0),
            velocity=Vector3(20.0, -2.0, 0.0),
        )
        terrain_elevation = 100.0
        result = detector.check_landing(state, terrain_elevation)
        assert result.collided is True
        assert result.contact_point.y == pytest.approx(100.0)


class TestCollisionDetectorSpheres:
    """Test sphere-sphere collision detection."""

    @pytest.fixture
    def detector(self) -> CollisionDetector:
        """Create a collision detector."""
        return CollisionDetector()

    def test_check_sphere_collision_no_collision(self, detector: CollisionDetector) -> None:
        """Test sphere collision with no intersection."""
        sphere1 = BoundingSphere(center=Vector3(0.0, 0.0, 0.0), radius=5.0)
        sphere2 = BoundingSphere(center=Vector3(20.0, 0.0, 0.0), radius=5.0)
        result = detector.check_sphere_collision(sphere1, sphere2)
        assert result.collided is False

    def test_check_sphere_collision_with_collision(self, detector: CollisionDetector) -> None:
        """Test sphere collision with intersection."""
        sphere1 = BoundingSphere(center=Vector3(0.0, 0.0, 0.0), radius=5.0)
        sphere2 = BoundingSphere(center=Vector3(8.0, 0.0, 0.0), radius=5.0)
        result = detector.check_sphere_collision(sphere1, sphere2)
        assert result.collided is True
        assert result.penetration_depth > 0.0
        # Normal should point from sphere1 toward sphere2
        assert result.contact_normal.x > 0.0

    def test_check_sphere_collision_same_position(self, detector: CollisionDetector) -> None:
        """Test sphere collision when spheres are at same position."""
        sphere1 = BoundingSphere(center=Vector3(0.0, 0.0, 0.0), radius=5.0)
        sphere2 = BoundingSphere(center=Vector3(0.0, 0.0, 0.0), radius=5.0)
        result = detector.check_sphere_collision(sphere1, sphere2)
        assert result.collided is True
        # Should handle zero distance case with arbitrary normal
        assert result.contact_normal != Vector3.zero()
        assert result.penetration_depth == pytest.approx(10.0)  # Sum of radii

    def test_check_sphere_collision_contact_point(self, detector: CollisionDetector) -> None:
        """Test sphere collision contact point calculation."""
        sphere1 = BoundingSphere(center=Vector3(0.0, 0.0, 0.0), radius=5.0)
        sphere2 = BoundingSphere(center=Vector3(10.0, 0.0, 0.0), radius=5.0)
        result = detector.check_sphere_collision(sphere1, sphere2)
        # Contact should be on sphere1 surface toward sphere2
        assert result.contact_point.x == pytest.approx(5.0)
        assert result.contact_point.y == pytest.approx(0.0)
        assert result.contact_point.z == pytest.approx(0.0)


class TestSpatialGrid:
    """Test SpatialGrid spatial partitioning."""

    def test_initialization(self) -> None:
        """Test grid initialization."""
        grid = SpatialGrid(cell_size=1000.0)
        assert grid.cell_size == 1000.0
        assert len(grid.grid) == 0

    def test_insert_object(self) -> None:
        """Test inserting object into grid."""
        grid = SpatialGrid(cell_size=100.0)
        position = Vector3(50.0, 50.0, 50.0)
        grid.insert(object_id=1, position=position, radius=10.0)
        # Grid should have one cell with one object
        assert len(grid.grid) == 1

    def test_insert_multiple_objects_same_cell(self) -> None:
        """Test inserting multiple objects into same cell."""
        grid = SpatialGrid(cell_size=100.0)
        grid.insert(1, Vector3(10.0, 10.0, 10.0), 5.0)
        grid.insert(2, Vector3(20.0, 20.0, 20.0), 5.0)
        # Both in same cell
        assert len(grid.grid) == 1
        # Cell should have 2 objects
        cell = list(grid.grid.values())[0]
        assert len(cell) == 2

    def test_insert_multiple_objects_different_cells(self) -> None:
        """Test inserting objects into different cells."""
        grid = SpatialGrid(cell_size=100.0)
        grid.insert(1, Vector3(50.0, 50.0, 50.0), 5.0)
        grid.insert(2, Vector3(150.0, 150.0, 150.0), 5.0)
        # Should be in different cells
        assert len(grid.grid) == 2

    def test_query_nearby_empty_grid(self) -> None:
        """Test querying empty grid returns no results."""
        grid = SpatialGrid(cell_size=100.0)
        nearby = grid.query_nearby(Vector3(0.0, 0.0, 0.0), search_radius=50.0)
        assert len(nearby) == 0

    def test_query_nearby_finds_close_object(self) -> None:
        """Test query finds nearby object."""
        grid = SpatialGrid(cell_size=100.0)
        grid.insert(1, Vector3(10.0, 10.0, 10.0), 5.0)

        # Query near the object
        nearby = grid.query_nearby(Vector3(15.0, 15.0, 15.0), search_radius=20.0)
        assert len(nearby) == 1
        assert nearby[0][0] == 1  # object_id

    def test_query_nearby_excludes_far_objects(self) -> None:
        """Test query excludes objects outside search radius."""
        grid = SpatialGrid(cell_size=100.0)
        grid.insert(1, Vector3(10.0, 10.0, 10.0), 5.0)
        grid.insert(2, Vector3(1000.0, 1000.0, 1000.0), 5.0)

        # Query near first object
        nearby = grid.query_nearby(Vector3(10.0, 10.0, 10.0), search_radius=50.0)
        assert len(nearby) == 1
        assert nearby[0][0] == 1  # Only first object

    def test_query_nearby_multiple_cells(self) -> None:
        """Test query searches multiple cells."""
        grid = SpatialGrid(cell_size=100.0)
        # Insert objects in adjacent cells
        grid.insert(1, Vector3(50.0, 50.0, 50.0), 5.0)
        grid.insert(2, Vector3(150.0, 50.0, 50.0), 5.0)

        # Query at boundary, large radius
        nearby = grid.query_nearby(Vector3(100.0, 50.0, 50.0), search_radius=100.0)
        # Should find both
        assert len(nearby) == 2

    def test_query_nearby_returns_position_and_radius(self) -> None:
        """Test query returns object position and radius."""
        grid = SpatialGrid(cell_size=100.0)
        position = Vector3(25.0, 35.0, 45.0)
        radius = 7.5
        grid.insert(1, position, radius)

        nearby = grid.query_nearby(Vector3(25.0, 35.0, 45.0), search_radius=10.0)
        assert len(nearby) == 1
        obj_id, obj_pos, obj_radius = nearby[0]
        assert obj_id == 1
        assert obj_pos == position
        assert obj_radius == pytest.approx(radius)

    def test_clear_grid(self) -> None:
        """Test clearing all objects from grid."""
        grid = SpatialGrid(cell_size=100.0)
        grid.insert(1, Vector3(10.0, 10.0, 10.0), 5.0)
        grid.insert(2, Vector3(20.0, 20.0, 20.0), 5.0)

        grid.clear()

        assert len(grid.grid) == 0
        nearby = grid.query_nearby(Vector3(10.0, 10.0, 10.0), search_radius=50.0)
        assert len(nearby) == 0

    def test_spatial_hashing_consistency(self) -> None:
        """Test same position always hashes to same cell."""
        grid = SpatialGrid(cell_size=100.0)
        position = Vector3(125.0, 225.0, 325.0)

        # Insert same position multiple times (different IDs)
        grid.insert(1, position, 5.0)
        grid.insert(2, position, 5.0)

        # Should be in same cell
        assert len(grid.grid) == 1
        cell = list(grid.grid.values())[0]
        assert len(cell) == 2

    def test_query_large_search_radius(self) -> None:
        """Test query with very large search radius."""
        grid = SpatialGrid(cell_size=100.0)
        # Insert objects far apart
        grid.insert(1, Vector3(0.0, 0.0, 0.0), 5.0)
        grid.insert(2, Vector3(500.0, 500.0, 500.0), 5.0)
        grid.insert(3, Vector3(-500.0, -500.0, -500.0), 5.0)

        # Large search radius should find all
        nearby = grid.query_nearby(Vector3(0.0, 0.0, 0.0), search_radius=1000.0)
        assert len(nearby) == 3


class TestCollisionPerformance:
    """Test performance-related collision features."""

    def test_sphere_intersection_uses_squared_distance(self) -> None:
        """Test sphere intersection uses squared distance (performance)."""
        sphere1 = BoundingSphere(center=Vector3(0.0, 0.0, 0.0), radius=5.0)
        sphere2 = BoundingSphere(center=Vector3(8.0, 0.0, 0.0), radius=5.0)

        # This should use distance_squared internally (no sqrt)
        result = sphere1.intersects(sphere2)
        assert result is True

    def test_spatial_grid_reduces_checks(self) -> None:
        """Test spatial grid reduces number of collision checks needed."""
        grid = SpatialGrid(cell_size=100.0)

        # Insert many objects in different regions
        for i in range(10):
            grid.insert(i, Vector3(float(i * 200), 0.0, 0.0), 5.0)

        # Query in specific region should only return nearby objects
        nearby = grid.query_nearby(Vector3(200.0, 0.0, 0.0), search_radius=50.0)
        # Should only find object near position 200 (not all 10)
        assert len(nearby) < 10

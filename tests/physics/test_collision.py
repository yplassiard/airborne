"""Tests for Terrain Collision Detection."""

import pytest

from airborne.physics.collision import (
    CollisionResult,
    CollisionSeverity,
    CollisionType,
    TerrainCollisionDetector,
    prevent_terrain_collision,
)
from airborne.physics.vectors import Vector3
from airborne.terrain.elevation_service import ElevationService
from airborne.terrain.srtm_provider import ConstantElevationProvider, SimpleFlatEarthProvider


class TestCollisionResult:
    """Test CollisionResult dataclass."""

    def test_create_collision_result(self) -> None:
        """Test creating collision result."""
        result = CollisionResult(
            is_colliding=True,
            collision_type=CollisionType.TERRAIN,
            severity=CollisionSeverity.COLLISION,
            terrain_elevation_m=100.0,
            aircraft_altitude_m=50.0,
            distance_to_terrain=-50.0,
            agl_altitude=-50.0,
            position=Vector3(-122.4194, 50, 37.7749),
        )

        assert result.is_colliding is True
        assert result.collision_type == CollisionType.TERRAIN
        assert result.severity == CollisionSeverity.COLLISION
        assert result.terrain_elevation_m == 100.0
        assert result.aircraft_altitude_m == 50.0
        assert result.distance_to_terrain == -50.0
        assert result.agl_altitude == -50.0


class TestTerrainCollisionDetector:
    """Test terrain collision detector."""

    @pytest.fixture
    def elevation_service(self) -> ElevationService:
        """Create elevation service with flat earth provider."""
        service = ElevationService()
        provider = SimpleFlatEarthProvider()
        service.add_provider(provider)
        return service

    @pytest.fixture
    def detector(self, elevation_service: ElevationService) -> TerrainCollisionDetector:
        """Create terrain collision detector."""
        return TerrainCollisionDetector(elevation_service)

    def test_detector_initialization(self, detector: TerrainCollisionDetector) -> None:
        """Test detector initializes correctly."""
        assert detector.elevation_service is not None
        assert detector.collision_buffer_m == 0.0
        assert detector.warning_threshold_ft == 500.0
        assert detector.caution_threshold_ft == 200.0
        assert detector.critical_threshold_ft == 100.0

    def test_no_collision_above_terrain(self, detector: TerrainCollisionDetector) -> None:
        """Test no collision when well above terrain."""
        position = Vector3(-122.4194, 0, 37.7749)
        altitude_msl = 1000.0  # High altitude

        result = detector.check_terrain_collision(position, altitude_msl)

        assert result.is_colliding is False
        assert result.collision_type == CollisionType.NONE
        assert result.severity == CollisionSeverity.SAFE
        assert result.aircraft_altitude_m == 1000.0
        assert result.distance_to_terrain > 0

    def test_collision_below_terrain(self) -> None:
        """Test collision when below terrain."""
        # Create service with constant 100m terrain
        service = ElevationService()
        service.add_provider(ConstantElevationProvider(elevation=100.0))
        detector = TerrainCollisionDetector(service)

        position = Vector3(-122.4194, 0, 37.7749)
        altitude_msl = 50.0  # Below terrain

        result = detector.check_terrain_collision(position, altitude_msl)

        assert result.is_colliding is True
        assert result.collision_type == CollisionType.TERRAIN
        assert result.severity == CollisionSeverity.COLLISION
        assert result.terrain_elevation_m == 100.0
        assert result.aircraft_altitude_m == 50.0
        assert result.distance_to_terrain == -50.0
        assert result.agl_altitude == -50.0

    def test_collision_at_terrain_level(self) -> None:
        """Test collision at terrain level."""
        service = ElevationService()
        service.add_provider(ConstantElevationProvider(elevation=100.0))
        detector = TerrainCollisionDetector(service)

        position = Vector3(-122.4194, 0, 37.7749)
        altitude_msl = 100.0  # At terrain level

        result = detector.check_terrain_collision(position, altitude_msl)

        assert result.is_colliding is True
        assert result.severity == CollisionSeverity.COLLISION

    def test_water_collision_detection(self) -> None:
        """Test water collision when terrain is at/below sea level."""
        service = ElevationService()
        service.add_provider(ConstantElevationProvider(elevation=0.0))  # Sea level
        detector = TerrainCollisionDetector(service)

        position = Vector3(-122.4194, 0, 37.7749)
        altitude_msl = -10.0  # Below sea level

        result = detector.check_terrain_collision(position, altitude_msl)

        assert result.is_colliding is True
        assert result.collision_type == CollisionType.WATER

    def test_severity_safe(self, detector: TerrainCollisionDetector) -> None:
        """Test SAFE severity at high altitude."""
        position = Vector3(-122.4194, 0, 37.7749)
        altitude_msl = 1000.0

        result = detector.check_terrain_collision(position, altitude_msl)

        assert result.severity == CollisionSeverity.SAFE
        assert result.is_colliding is False

    def test_severity_warning(self) -> None:
        """Test WARNING severity at 400ft AGL."""
        service = ElevationService()
        service.add_provider(ConstantElevationProvider(elevation=0.0))
        detector = TerrainCollisionDetector(service)

        position = Vector3(-122.4194, 0, 37.7749)
        altitude_msl = 400.0 * 0.3048  # 400ft in meters (~122m)

        result = detector.check_terrain_collision(position, altitude_msl)

        assert result.severity == CollisionSeverity.WARNING
        assert result.is_colliding is False

    def test_severity_caution(self) -> None:
        """Test CAUTION severity at 150ft AGL."""
        service = ElevationService()
        service.add_provider(ConstantElevationProvider(elevation=0.0))
        detector = TerrainCollisionDetector(service)

        position = Vector3(-122.4194, 0, 37.7749)
        altitude_msl = 150.0 * 0.3048  # 150ft in meters (~46m)

        result = detector.check_terrain_collision(position, altitude_msl)

        assert result.severity == CollisionSeverity.CAUTION
        assert result.is_colliding is False

    def test_severity_critical(self) -> None:
        """Test CRITICAL severity at 50ft AGL."""
        service = ElevationService()
        service.add_provider(ConstantElevationProvider(elevation=0.0))
        detector = TerrainCollisionDetector(service)

        position = Vector3(-122.4194, 0, 37.7749)
        altitude_msl = 50.0 * 0.3048  # 50ft in meters (~15m)

        result = detector.check_terrain_collision(position, altitude_msl)

        assert result.severity == CollisionSeverity.CRITICAL
        assert result.is_colliding is False

    def test_agl_calculation(self) -> None:
        """Test AGL altitude calculation."""
        service = ElevationService()
        service.add_provider(ConstantElevationProvider(elevation=500.0))
        detector = TerrainCollisionDetector(service)

        position = Vector3(-122.4194, 0, 37.7749)
        altitude_msl = 1500.0  # 1500m MSL

        result = detector.check_terrain_collision(position, altitude_msl)

        # AGL = MSL - terrain elevation
        assert result.agl_altitude == 1000.0  # 1500 - 500
        assert result.terrain_elevation_m == 500.0
        assert result.distance_to_terrain == 1000.0

    def test_check_terrain_collision_without_service(self) -> None:
        """Test collision check without elevation service."""
        detector = TerrainCollisionDetector(elevation_service=None)

        position = Vector3(-122.4194, 0, 37.7749)
        altitude_msl = 100.0

        result = detector.check_terrain_collision(position, altitude_msl)

        # Should assume sea level (0m) terrain
        assert result.terrain_elevation_m == 0.0
        assert result.agl_altitude == 100.0
        assert result.is_colliding is False

    def test_get_minimum_safe_altitude(self) -> None:
        """Test minimum safe altitude calculation."""
        service = ElevationService()
        service.add_provider(ConstantElevationProvider(elevation=500.0))
        detector = TerrainCollisionDetector(service)

        position = Vector3(-122.4194, 0, 37.7749)
        min_safe_alt = detector.get_minimum_safe_altitude(position, buffer_ft=1000.0)

        # Should be terrain (500m) + 1000ft buffer
        buffer_m = 1000.0 * 0.3048  # ~304.8m
        expected = 500.0 + buffer_m  # ~804.8m
        assert min_safe_alt == pytest.approx(expected, abs=1.0)

    def test_is_safe_to_descend_safe(self) -> None:
        """Test safe descent check."""
        service = ElevationService()
        service.add_provider(ConstantElevationProvider(elevation=100.0))
        detector = TerrainCollisionDetector(service)

        position = Vector3(-122.4194, 0, 37.7749)
        current_altitude = 2000.0
        target_altitude = 1000.0

        is_safe = detector.is_safe_to_descend(position, current_altitude, target_altitude)

        assert is_safe is True

    def test_is_safe_to_descend_unsafe(self) -> None:
        """Test unsafe descent check."""
        service = ElevationService()
        service.add_provider(ConstantElevationProvider(elevation=500.0))
        detector = TerrainCollisionDetector(service)

        position = Vector3(-122.4194, 0, 37.7749)
        current_altitude = 2000.0
        target_altitude = 300.0  # Below terrain

        is_safe = detector.is_safe_to_descend(position, current_altitude, target_altitude)

        assert is_safe is False

    def test_set_warning_thresholds(self, detector: TerrainCollisionDetector) -> None:
        """Test setting custom warning thresholds."""
        detector.set_warning_thresholds(warning_ft=1000.0, caution_ft=500.0, critical_ft=200.0)

        assert detector.warning_threshold_ft == 1000.0
        assert detector.caution_threshold_ft == 500.0
        assert detector.critical_threshold_ft == 200.0

    def test_check_flight_path_collision(self) -> None:
        """Test predictive flight path collision."""
        service = ElevationService()
        service.add_provider(ConstantElevationProvider(elevation=500.0))
        detector = TerrainCollisionDetector(service)

        position = Vector3(-122.4194, 0, 37.7749)
        altitude_msl = 1000.0
        velocity = Vector3(0, -10, 0)  # Descending at 10 m/s

        results = detector.check_flight_path_collision(
            position, altitude_msl, velocity, lookahead_seconds=30, num_samples=5
        )

        assert len(results) == 5

        # Should show increasing collision risk as aircraft descends
        # First sample should be safe, later samples should show warnings
        assert results[0].severity in [CollisionSeverity.SAFE, CollisionSeverity.WARNING]

    def test_flight_path_collision_level_flight(self) -> None:
        """Test flight path collision with level flight."""
        service = ElevationService()
        service.add_provider(ConstantElevationProvider(elevation=100.0))
        detector = TerrainCollisionDetector(service)

        position = Vector3(-122.4194, 0, 37.7749)
        altitude_msl = 1000.0
        velocity = Vector3(50, 0, 0)  # Level flight, moving east

        results = detector.check_flight_path_collision(
            position, altitude_msl, velocity, lookahead_seconds=60, num_samples=10
        )

        # All results should be safe (level flight at high altitude)
        for result in results:
            assert result.severity == CollisionSeverity.SAFE
            assert result.is_colliding is False


class TestPreventTerrainCollision:
    """Test terrain collision prevention utility."""

    def test_prevent_collision_when_below_terrain(self) -> None:
        """Test altitude adjustment when below terrain."""
        position = Vector3(-122.4194, 0, 37.7749)
        altitude_msl = 50.0
        terrain_elevation_m = 100.0
        min_clearance_m = 10.0

        safe_altitude = prevent_terrain_collision(
            position, altitude_msl, terrain_elevation_m, min_clearance_m
        )

        # Should be adjusted to terrain + clearance
        assert safe_altitude == 110.0  # 100 + 10

    def test_prevent_collision_when_too_close(self) -> None:
        """Test altitude adjustment when too close to terrain."""
        position = Vector3(-122.4194, 0, 37.7749)
        altitude_msl = 105.0
        terrain_elevation_m = 100.0
        min_clearance_m = 10.0

        safe_altitude = prevent_terrain_collision(
            position, altitude_msl, terrain_elevation_m, min_clearance_m
        )

        # Should be adjusted to maintain clearance
        assert safe_altitude == 110.0

    def test_prevent_collision_when_safe(self) -> None:
        """Test no adjustment when altitude is safe."""
        position = Vector3(-122.4194, 0, 37.7749)
        altitude_msl = 500.0
        terrain_elevation_m = 100.0
        min_clearance_m = 10.0

        safe_altitude = prevent_terrain_collision(
            position, altitude_msl, terrain_elevation_m, min_clearance_m
        )

        # Should remain unchanged
        assert safe_altitude == 500.0


class TestRealWorldScenarios:
    """Test real-world collision scenarios."""

    def test_mountain_approach_scenario(self) -> None:
        """Test approaching mountainous terrain."""
        # Simulate approaching 2000m mountain
        service = ElevationService()
        service.add_provider(ConstantElevationProvider(elevation=2000.0))
        detector = TerrainCollisionDetector(service)

        # Aircraft at 2500m MSL (500m AGL)
        position = Vector3(-122.4194, 0, 37.7749)
        altitude_msl = 2500.0

        result = detector.check_terrain_collision(position, altitude_msl)

        # 500m = ~1640ft AGL, should be safe but might trigger warning
        assert result.agl_altitude == pytest.approx(500.0, abs=1.0)
        assert result.is_colliding is False
        assert result.severity in [CollisionSeverity.SAFE, CollisionSeverity.WARNING]

    def test_high_altitude_airport_takeoff(self) -> None:
        """Test takeoff from high-altitude airport."""
        # Denver airport at ~1650m elevation
        service = ElevationService()
        service.add_provider(ConstantElevationProvider(elevation=1650.0))
        detector = TerrainCollisionDetector(service)

        # Aircraft just after takeoff at 1700m MSL (50m AGL)
        position = Vector3(-104.9903, 0, 39.7392)
        altitude_msl = 1700.0

        result = detector.check_terrain_collision(position, altitude_msl)

        # 50m = ~164ft AGL, should be CAUTION or CRITICAL
        assert result.agl_altitude == pytest.approx(50.0, abs=1.0)
        assert result.severity in [CollisionSeverity.CAUTION, CollisionSeverity.CRITICAL]

    def test_landing_approach_scenario(self) -> None:
        """Test landing approach."""
        service = ElevationService()
        service.add_provider(ConstantElevationProvider(elevation=10.0))  # Airport near sea level
        detector = TerrainCollisionDetector(service)

        # Aircraft on final approach at 50ft AGL (CRITICAL threshold)
        position = Vector3(-122.4194, 0, 37.7749)
        altitude_msl = 10.0 + (50.0 * 0.3048)  # 10m + 50ft

        result = detector.check_terrain_collision(position, altitude_msl)

        # Should be CRITICAL (< 100ft)
        agl_ft = result.agl_altitude * 3.28084
        assert 40 < agl_ft < 60  # Approximately 50ft
        assert result.severity == CollisionSeverity.CRITICAL

    def test_cfit_scenario(self) -> None:
        """Test Controlled Flight Into Terrain (CFIT) scenario."""
        service = ElevationService()
        service.add_provider(ConstantElevationProvider(elevation=1000.0))
        detector = TerrainCollisionDetector(service)

        # Aircraft descending into terrain
        position = Vector3(-122.4194, 0, 37.7749)
        altitude_msl = 950.0  # 50m below terrain
        velocity = Vector3(50, -5, 0)  # Descending

        result = detector.check_terrain_collision(position, altitude_msl, velocity)

        # Should detect collision
        assert result.is_colliding is True
        assert result.collision_type == CollisionType.TERRAIN
        assert result.severity == CollisionSeverity.COLLISION
        assert result.distance_to_terrain < 0

    def test_terrain_avoidance_maneuver(self) -> None:
        """Test terrain avoidance maneuver."""
        service = ElevationService()
        service.add_provider(ConstantElevationProvider(elevation=1000.0))
        detector = TerrainCollisionDetector(service)

        # Aircraft approaching terrain
        position = Vector3(-122.4194, 0, 37.7749)
        altitude_msl = 1050.0  # 50m above terrain
        terrain_elevation = 1000.0

        # Check if it's safe to descend
        is_safe = detector.is_safe_to_descend(position, altitude_msl, 950.0)
        assert is_safe is False

        # Calculate safe altitude
        min_safe_alt = detector.get_minimum_safe_altitude(position, buffer_ft=500.0)
        assert min_safe_alt > terrain_elevation

        # Apply terrain avoidance
        safe_altitude = prevent_terrain_collision(position, altitude_msl, terrain_elevation, 50.0)
        assert safe_altitude >= 1050.0  # Should maintain current altitude

    def test_ocean_flight_scenario(self) -> None:
        """Test flight over ocean."""
        service = ElevationService()
        service.add_provider(ConstantElevationProvider(elevation=0.0))  # Sea level
        detector = TerrainCollisionDetector(service)

        # Aircraft at cruise altitude over ocean
        position = Vector3(-155.0, 0, 20.0)  # Mid-Pacific
        altitude_msl = 10000.0  # 10km altitude

        result = detector.check_terrain_collision(position, altitude_msl)

        assert result.is_colliding is False
        assert result.severity == CollisionSeverity.SAFE
        assert result.terrain_elevation_m == 0.0

    def test_varying_terrain_flight_path(self) -> None:
        """Test flight path over varying terrain."""
        service = ElevationService()
        service.add_provider(SimpleFlatEarthProvider())
        detector = TerrainCollisionDetector(service)

        # Aircraft flying level over varying terrain
        position = Vector3(-122.4194, 0, 37.7749)
        altitude_msl = 500.0
        velocity = Vector3(50, 0, 50)  # Moving northeast

        results = detector.check_flight_path_collision(
            position, altitude_msl, velocity, lookahead_seconds=60, num_samples=10
        )

        # Should get varying collision results as terrain changes
        assert len(results) == 10
        for result in results:
            # Terrain elevation should vary with position
            assert result.terrain_elevation_m >= 0

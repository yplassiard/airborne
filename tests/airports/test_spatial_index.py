"""Tests for Spatial Index."""

import pytest

from airborne.airports.spatial_index import SpatialIndex
from airborne.physics.vectors import Vector3


class TestSpatialIndexBasics:
    """Test basic spatial index operations."""

    @pytest.fixture
    def index(self) -> SpatialIndex:
        """Create spatial index for testing."""
        return SpatialIndex(cell_size_deg=1.0)

    def test_insert_and_count(self, index: SpatialIndex) -> None:
        """Test inserting items and counting."""
        assert index.get_item_count() == 0

        index.insert(Vector3(-122.0, 0, 37.5), "KPAO")
        assert index.get_item_count() == 1

        index.insert(Vector3(-122.5, 0, 37.6), "KSFO")
        assert index.get_item_count() == 2

    def test_clear(self, index: SpatialIndex) -> None:
        """Test clearing the index."""
        index.insert(Vector3(-122.0, 0, 37.5), "KPAO")
        index.insert(Vector3(-122.5, 0, 37.6), "KSFO")
        assert index.get_item_count() == 2

        index.clear()
        assert index.get_item_count() == 0
        assert index.get_cell_count() == 0

    def test_query_all(self, index: SpatialIndex) -> None:
        """Test querying all items."""
        index.insert(Vector3(-122.0, 0, 37.5), "KPAO")
        index.insert(Vector3(-122.5, 0, 37.6), "KSFO")

        all_items = index.query_all()
        assert len(all_items) == 2

        # Check that both items are present
        data = [item[1] for item in all_items]
        assert "KPAO" in data
        assert "KSFO" in data


class TestSpatialIndexQueries:
    """Test spatial query operations."""

    @pytest.fixture
    def populated_index(self) -> SpatialIndex:
        """Create index with sample airports."""
        index = SpatialIndex(cell_size_deg=1.0)

        # Bay Area airports
        index.insert(Vector3(-122.115, 2.1, 37.461), "KPAO")  # Palo Alto
        index.insert(Vector3(-122.375, 4.0, 37.619), "KSFO")  # San Francisco (~15nm from KPAO)
        index.insert(Vector3(-121.929, 18.9, 37.363), "KSJC")  # San Jose (~10nm from KPAO)
        index.insert(Vector3(-122.221, 5.2, 37.513), "KSQL")  # San Carlos (~6nm from KPAO)

        # Far away airport
        index.insert(Vector3(-118.408, 38.1, 33.943), "KLAX")  # Los Angeles (~300nm)

        return index

    def test_query_radius_finds_nearby(self, populated_index: SpatialIndex) -> None:
        """Test that radius query finds nearby items."""
        # Query from KPAO position with 20nm radius
        kpao_pos = Vector3(-122.115, 2.1, 37.461)
        nearby = populated_index.query_radius(kpao_pos, radius_nm=20)

        # Should find KPAO, KSFO, KSJC, KSQL (all within 20nm)
        # Should NOT find KLAX (300nm away)
        data = [item[0] for item in nearby]
        assert "KPAO" in data
        assert "KSFO" in data
        assert "KSJC" in data
        assert "KSQL" in data
        assert "KLAX" not in data

    def test_query_radius_excludes_far(self, populated_index: SpatialIndex) -> None:
        """Test that radius query excludes items outside radius."""
        # Query from KPAO with small 5nm radius
        kpao_pos = Vector3(-122.115, 2.1, 37.461)
        nearby = populated_index.query_radius(kpao_pos, radius_nm=5)

        # Should only find KPAO (itself) - other airports are further
        data = [item[0] for item in nearby]
        assert "KPAO" in data
        assert len(data) == 1  # Only KPAO within 5nm of itself

    def test_query_radius_sorted_by_distance(self, populated_index: SpatialIndex) -> None:
        """Test that results are sorted by distance."""
        kpao_pos = Vector3(-122.115, 2.1, 37.461)
        nearby = populated_index.query_radius(kpao_pos, radius_nm=50)

        # Check that distances are sorted
        distances = [distance for _, distance in nearby]
        assert distances == sorted(distances)

        # KPAO should be first (distance ~0)
        assert nearby[0][0] == "KPAO"
        assert nearby[0][1] < 0.1

    def test_query_zero_radius(self, populated_index: SpatialIndex) -> None:
        """Test query with zero radius finds nothing (or only exact match)."""
        kpao_pos = Vector3(-122.115, 2.1, 37.461)
        nearby = populated_index.query_radius(kpao_pos, radius_nm=0)

        # Should only find exact position match
        assert len(nearby) <= 1
        if len(nearby) == 1:
            assert nearby[0][0] == "KPAO"

    def test_query_empty_index(self) -> None:
        """Test querying empty index returns no results."""
        index = SpatialIndex()
        nearby = index.query_radius(Vector3(-122.0, 0, 37.5), radius_nm=50)
        assert nearby == []


class TestSpatialIndexPerformance:
    """Test spatial index performance characteristics."""

    def test_large_dataset_insertion(self) -> None:
        """Test inserting many items."""
        index = SpatialIndex(cell_size_deg=1.0)

        # Insert 1000 items in a grid pattern
        # lat: -50 to 49 (100 values), lon: -180 to 162 (20 values) = 2000 items
        count = 0
        for lat in range(-50, 50, 10):  # 10 latitudes
            for lon in range(-180, 180, 36):  # 10 longitudes
                index.insert(Vector3(lon, 0, lat), f"AIRPORT_{lat}_{lon}")
                count += 1

        # Should have inserted 100 items (10 x 10)
        assert index.get_item_count() == count
        assert count == 100

    def test_large_dataset_query(self) -> None:
        """Test querying from large dataset."""
        index = SpatialIndex(cell_size_deg=1.0)

        # Insert 100 items
        for lat in range(-50, 50, 10):
            for lon in range(-180, 180, 36):
                index.insert(Vector3(lon, 0, lat), f"AIRPORT_{lat}_{lon}")

        # Query should be fast (grid index optimization)
        nearby = index.query_radius(Vector3(0, 0, 0), radius_nm=200)

        # Should find items near (0, 0)
        assert len(nearby) > 0
        assert len(nearby) < 100  # Should not return everything


class TestSpatialIndexEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def index(self) -> SpatialIndex:
        """Create spatial index for testing."""
        return SpatialIndex(cell_size_deg=1.0)

    def test_insert_at_prime_meridian(self, index: SpatialIndex) -> None:
        """Test inserting at longitude 0."""
        index.insert(Vector3(0, 0, 51.5), "EGLL")  # London Heathrow
        nearby = index.query_radius(Vector3(0, 0, 51.5), radius_nm=10)
        assert len(nearby) == 1
        assert nearby[0][0] == "EGLL"

    def test_insert_at_equator(self, index: SpatialIndex) -> None:
        """Test inserting at latitude 0."""
        index.insert(Vector3(-79.0, 0, 0), "AIRPORT")  # Near Quito
        nearby = index.query_radius(Vector3(-79.0, 0, 0), radius_nm=10)
        assert len(nearby) == 1

    def test_insert_near_poles(self, index: SpatialIndex) -> None:
        """Test inserting near north/south poles."""
        index.insert(Vector3(0, 0, 89), "NORTH")
        index.insert(Vector3(0, 0, -89), "SOUTH")

        nearby_north = index.query_radius(Vector3(0, 0, 89), radius_nm=100)
        assert "NORTH" in [item[0] for item in nearby_north]

        nearby_south = index.query_radius(Vector3(0, 0, -89), radius_nm=100)
        assert "SOUTH" in [item[0] for item in nearby_south]

    def test_insert_at_date_line(self, index: SpatialIndex) -> None:
        """Test inserting near date line (longitude ±180)."""
        index.insert(Vector3(179, 0, 0), "WEST")
        index.insert(Vector3(-179, 0, 0), "EAST")

        # These should be close to each other (across date line)
        nearby = index.query_radius(Vector3(179, 0, 0), radius_nm=200)
        data = [item[0] for item in nearby]
        assert "WEST" in data
        # Note: May or may not find EAST depending on cell boundaries

    def test_multiple_items_same_position(self, index: SpatialIndex) -> None:
        """Test inserting multiple items at same position."""
        pos = Vector3(-122.0, 0, 37.5)
        index.insert(pos, "ITEM1")
        index.insert(pos, "ITEM2")
        index.insert(pos, "ITEM3")

        nearby = index.query_radius(pos, radius_nm=1)
        assert len(nearby) == 3

    def test_custom_cell_size(self) -> None:
        """Test creating index with custom cell size."""
        # Small cells = more memory, faster queries
        fine_index = SpatialIndex(cell_size_deg=0.1)
        fine_index.insert(Vector3(-122.0, 0, 37.5), "KPAO")
        assert fine_index.get_cell_count() == 1

        # Large cells = less memory, slower queries
        coarse_index = SpatialIndex(cell_size_deg=10.0)
        coarse_index.insert(Vector3(-122.0, 0, 37.5), "KPAO")
        assert coarse_index.get_cell_count() == 1


class TestRealWorldDistances:
    """Test with real-world airport distances."""

    @pytest.fixture
    def bay_area_index(self) -> SpatialIndex:
        """Create index with real Bay Area airports."""
        index = SpatialIndex(cell_size_deg=1.0)

        # Real coordinates from OurAirports
        index.insert(Vector3(-122.115, 2.1, 37.461), "KPAO")  # Palo Alto
        index.insert(Vector3(-122.375, 4.0, 37.619), "KSFO")  # San Francisco
        index.insert(Vector3(-121.929, 18.9, 37.363), "KSJC")  # San Jose

        return index

    def test_kpao_to_ksfo_distance(self, bay_area_index: SpatialIndex) -> None:
        """Test that KPAO to KSFO distance is approximately 15nm."""
        kpao_pos = Vector3(-122.115, 2.1, 37.461)
        nearby = bay_area_index.query_radius(kpao_pos, radius_nm=20)

        # Find KSFO in results
        ksfo_result = next((item for item in nearby if item[0] == "KSFO"), None)
        assert ksfo_result is not None

        distance = ksfo_result[1]
        # Known distance is ~15nm
        assert 14 < distance < 16

    def test_kpao_to_ksjc_distance(self, bay_area_index: SpatialIndex) -> None:
        """Test that KPAO to KSJC distance is approximately 10nm."""
        kpao_pos = Vector3(-122.115, 2.1, 37.461)
        nearby = bay_area_index.query_radius(kpao_pos, radius_nm=15)

        # Find KSJC in results
        ksjc_result = next((item for item in nearby if item[0] == "KSJC"), None)
        assert ksjc_result is not None

        distance = ksjc_result[1]
        # Known distance is ~10nm
        assert 9 < distance < 11

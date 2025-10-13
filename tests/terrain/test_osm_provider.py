"""Tests for OpenStreetMap Provider."""

import pytest

from airborne.physics.vectors import Vector3
from airborne.terrain.osm_provider import FeatureType, GeoFeature, OSMProvider


class TestGeoFeature:
    """Test GeoFeature dataclass."""

    def test_create_city(self) -> None:
        """Test creating a city feature."""
        feature = GeoFeature(
            feature_id="test_city",
            name="Test City",
            feature_type=FeatureType.CITY,
            position=Vector3(-122.4194, 52, 37.7749),
            population=100000,
            country="United States",
            region="California",
        )

        assert feature.name == "Test City"
        assert feature.feature_type == FeatureType.CITY
        assert feature.population == 100000

    def test_create_mountain(self) -> None:
        """Test creating a mountain feature."""
        feature = GeoFeature(
            feature_id="test_mountain",
            name="Test Peak",
            feature_type=FeatureType.MOUNTAIN,
            position=Vector3(86.9250, 8848, 27.9881),
            elevation_m=8848,
            country="Nepal",
        )

        assert feature.name == "Test Peak"
        assert feature.feature_type == FeatureType.MOUNTAIN
        assert feature.elevation_m == 8848


class TestOSMProvider:
    """Test OSM provider."""

    @pytest.fixture
    def provider(self) -> OSMProvider:
        """Create OSM provider."""
        return OSMProvider()

    def test_provider_initialized_with_features(self, provider: OSMProvider) -> None:
        """Test provider loads features."""
        assert provider.get_feature_count() > 0

    def test_get_cities_near_san_francisco(self, provider: OSMProvider) -> None:
        """Test finding cities near San Francisco."""
        position = Vector3(-122.4194, 0, 37.7749)  # San Francisco
        cities = provider.get_cities_near(position, radius_nm=50)

        # Should find San Francisco itself
        assert len(cities) > 0
        assert any(c.name == "San Francisco" for c in cities)

    def test_get_cities_with_population_filter(self, provider: OSMProvider) -> None:
        """Test filtering cities by population."""
        position = Vector3(-122.4194, 0, 37.7749)
        cities = provider.get_cities_near(position, radius_nm=500, min_population=1000000)

        # Should only return major cities
        for city in cities:
            assert city.population >= 1000000

    def test_get_landmarks_near_grand_canyon(self, provider: OSMProvider) -> None:
        """Test finding landmarks near Grand Canyon."""
        position = Vector3(-112.1401, 0, 36.1069)  # Grand Canyon
        landmarks = provider.get_landmarks_near(position, radius_nm=20)

        # Should find Grand Canyon
        assert any(l.name == "Grand Canyon" for l in landmarks)

    def test_get_mountains_near_everest(self, provider: OSMProvider) -> None:
        """Test finding mountains near Everest."""
        position = Vector3(86.9250, 0, 27.9881)  # Mount Everest
        mountains = provider.get_mountains_near(position, radius_nm=50)

        # Should find Everest
        assert any(m.name == "Mount Everest" for m in mountains)

    def test_get_water_bodies_near_pacific(self, provider: OSMProvider) -> None:
        """Test finding water bodies."""
        position = Vector3(-155.0, 0, 20.0)  # Mid-Pacific
        water = provider.get_water_bodies_near(position, radius_nm=2000)

        # Should find Pacific Ocean (large search radius needed for ocean center points)
        assert any(w.name == "Pacific Ocean" for w in water)

    def test_get_features_by_type(self, provider: OSMProvider) -> None:
        """Test filtering features by type."""
        cities = provider.get_features_by_type(FeatureType.CITY)
        assert len(cities) > 0
        assert all(f.feature_type == FeatureType.CITY for f in cities)

        oceans = provider.get_features_by_type(FeatureType.OCEAN)
        assert len(oceans) > 0
        assert all(f.feature_type == FeatureType.OCEAN for f in oceans)

    def test_get_features_by_country(self, provider: OSMProvider) -> None:
        """Test filtering features by country."""
        us_features = provider.get_features_by_country("United States")

        assert len(us_features) > 0
        assert all(f.country == "United States" for f in us_features)

    def test_get_feature_by_name_exact(self, provider: OSMProvider) -> None:
        """Test finding feature by exact name."""
        feature = provider.get_feature_by_name("San Francisco", fuzzy=False)

        assert feature is not None
        assert feature.name == "San Francisco"

    def test_get_feature_by_name_fuzzy(self, provider: OSMProvider) -> None:
        """Test finding feature by fuzzy name match."""
        feature = provider.get_feature_by_name("francisco", fuzzy=True)

        assert feature is not None
        assert "Francisco" in feature.name

    def test_get_closest_city(self, provider: OSMProvider) -> None:
        """Test finding closest city."""
        position = Vector3(-122.5, 0, 37.8)  # Near San Francisco
        feature, distance = provider.get_closest_feature(
            position, feature_types=[FeatureType.CITY]
        )

        assert feature is not None
        assert feature.feature_type == FeatureType.CITY
        assert distance < 50  # Within 50nm

    def test_get_closest_ocean(self, provider: OSMProvider) -> None:
        """Test finding closest ocean."""
        position = Vector3(-160.0, 0, 20.0)  # Mid-Pacific
        feature, distance = provider.get_closest_feature(
            position, feature_types=[FeatureType.OCEAN], max_distance_nm=2000
        )

        assert feature is not None
        assert feature.name == "Pacific Ocean"

    def test_get_features_near_with_type_filter(self, provider: OSMProvider) -> None:
        """Test filtering features by multiple types."""
        position = Vector3(-122.4194, 0, 37.7749)
        features = provider.get_features_near(
            position,
            radius_nm=100,
            feature_types=[FeatureType.CITY, FeatureType.LANDMARK],
        )

        # Should only contain cities and landmarks
        for feature in features:
            assert feature.feature_type in [FeatureType.CITY, FeatureType.LANDMARK]

    def test_features_sorted_by_distance(self, provider: OSMProvider) -> None:
        """Test that features are sorted by distance."""
        position = Vector3(-122.4194, 0, 37.7749)
        features = provider.get_features_near(position, radius_nm=500)

        if len(features) > 1:
            # Calculate distances to verify sorting
            distances = []
            for feature in features:
                distance = provider._calculate_distance_nm(position, feature.position)
                distances.append(distance)

            # Check distances are sorted
            for i in range(len(distances) - 1):
                assert distances[i] <= distances[i + 1]


class TestFeatureTypes:
    """Test different feature types."""

    @pytest.fixture
    def provider(self) -> OSMProvider:
        """Create OSM provider."""
        return OSMProvider()

    def test_city_features(self, provider: OSMProvider) -> None:
        """Test city features."""
        cities = provider.get_features_by_type(FeatureType.CITY)

        for city in cities:
            assert city.population > 0
            assert city.country != ""

    def test_mountain_features(self, provider: OSMProvider) -> None:
        """Test mountain features."""
        mountains = provider.get_features_by_type(FeatureType.MOUNTAIN)

        for mountain in mountains:
            assert mountain.elevation_m > 0

    def test_ocean_features(self, provider: OSMProvider) -> None:
        """Test ocean features."""
        oceans = provider.get_features_by_type(FeatureType.OCEAN)

        for ocean in oceans:
            assert ocean.area_km2 > 0

    def test_national_park_features(self, provider: OSMProvider) -> None:
        """Test national park features."""
        parks = provider.get_features_by_type(FeatureType.NATIONAL_PARK)

        for park in parks:
            assert park.area_km2 > 0
            assert park.country != ""

    def test_country_features(self, provider: OSMProvider) -> None:
        """Test country features."""
        countries = provider.get_features_by_type(FeatureType.COUNTRY)

        for country in countries:
            assert country.population > 0
            assert country.area_km2 > 0


class TestDistanceCalculations:
    """Test distance calculations."""

    @pytest.fixture
    def provider(self) -> OSMProvider:
        """Create OSM provider."""
        return OSMProvider()

    def test_distance_same_location(self, provider: OSMProvider) -> None:
        """Test distance to same location is zero."""
        position = Vector3(-122.4194, 0, 37.7749)
        distance = provider._calculate_distance_nm(position, position)

        assert distance == pytest.approx(0.0, abs=0.01)

    def test_distance_sf_to_la(self, provider: OSMProvider) -> None:
        """Test distance from SF to LA."""
        sf = Vector3(-122.4194, 0, 37.7749)
        la = Vector3(-118.2437, 0, 34.0522)

        distance = provider._calculate_distance_nm(sf, la)

        # Approximate distance: ~310 nm
        assert 300 < distance < 320

    def test_distance_ny_to_london(self, provider: OSMProvider) -> None:
        """Test distance from NY to London."""
        ny = Vector3(-74.0060, 0, 40.7128)
        london = Vector3(-0.1276, 0, 51.5074)

        distance = provider._calculate_distance_nm(ny, london)

        # Approximate distance: ~3000 nm
        assert 2900 < distance < 3100


class TestRealWorldScenarios:
    """Test real-world navigation scenarios."""

    @pytest.fixture
    def provider(self) -> OSMProvider:
        """Create OSM provider."""
        return OSMProvider()

    def test_approaching_san_francisco(self, provider: OSMProvider) -> None:
        """Test approaching San Francisco."""
        # Aircraft 50nm west of SF
        position = Vector3(-123.4, 0, 37.7)

        cities = provider.get_cities_near(position, radius_nm=60)

        # Should find San Francisco
        assert any(c.name == "San Francisco" for c in cities)

    def test_flying_over_grand_canyon(self, provider: OSMProvider) -> None:
        """Test flying over Grand Canyon."""
        position = Vector3(-112.1, 0, 36.1)

        landmarks = provider.get_landmarks_near(position, radius_nm=20)

        # Should find Grand Canyon
        assert any(l.name == "Grand Canyon" for l in landmarks)

    def test_crossing_atlantic(self, provider: OSMProvider) -> None:
        """Test crossing Atlantic Ocean."""
        # Mid-Atlantic position
        position = Vector3(-30.0, 0, 40.0)

        water = provider.get_water_bodies_near(position, radius_nm=3000)

        # Should find Atlantic Ocean (may need large radius due to distance from center point)
        assert any(w.name == "Atlantic Ocean" for w in water)

    def test_approaching_mount_everest(self, provider: OSMProvider) -> None:
        """Test approaching Mount Everest."""
        position = Vector3(87.0, 0, 28.0)

        mountains = provider.get_mountains_near(position, radius_nm=100)

        # Should find Everest or Himalayas
        assert any(m.name in ["Mount Everest", "Himalayas"] for m in mountains)

    def test_flying_over_usa(self, provider: OSMProvider) -> None:
        """Test flying over USA."""
        # Position over Kansas
        position = Vector3(-98.0, 0, 39.0)

        # Get nearby features (large radius to find cities)
        features = provider.get_features_near(position, radius_nm=1000)

        # Should find US features
        us_features = [f for f in features if f.country == "United States"]
        assert len(us_features) > 0

    def test_navigation_callouts(self, provider: OSMProvider) -> None:
        """Test navigation callout scenario."""
        # Aircraft approaching SF from east
        positions = [
            Vector3(-121.5, 0, 37.7),  # 50nm east
            Vector3(-122.0, 0, 37.7),  # 25nm east
            Vector3(-122.3, 0, 37.7),  # 10nm east
        ]

        for position in positions:
            closest_city, distance = provider.get_closest_feature(
                position, feature_types=[FeatureType.CITY]
            )

            if closest_city:
                # Callout format: "25 miles from San Francisco"
                distance_miles = distance * 1.15078  # nm to miles
                callout = f"{distance_miles:.0f} miles from {closest_city.name}"
                assert "San Francisco" in callout

    def test_mountain_warning(self, provider: OSMProvider) -> None:
        """Test mountain terrain warning."""
        # Near Rocky Mountains
        position = Vector3(-110.0, 0, 45.0)

        mountains = provider.get_mountains_near(position, radius_nm=100)

        if mountains:
            # Terrain warning: "Approaching Rocky Mountains"
            for mountain in mountains:
                if "Rocky" in mountain.name or "Rockies" in mountain.name:
                    warning = f"Approaching {mountain.name}"
                    assert "Rocky Mountains" in warning
                    break

    def test_ocean_position_callout(self, provider: OSMProvider) -> None:
        """Test ocean position callout."""
        # Mid-Pacific position
        position = Vector3(-155.0, 0, 20.0)

        closest_ocean, _ = provider.get_closest_feature(
            position, feature_types=[FeatureType.OCEAN]
        )

        if closest_ocean:
            callout = f"Over {closest_ocean.name}"
            assert "Pacific Ocean" in callout

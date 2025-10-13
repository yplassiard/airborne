"""OpenStreetMap geographic features provider.

Provides cities, landmarks, regions, countries, oceans, and other geographic
features for navigation callouts and spatial awareness.

Typical usage:
    from airborne.terrain.osm_provider import OSMProvider

    provider = OSMProvider()
    cities = provider.get_cities_near(position, radius_nm=50)
    for city in cities:
        print(f"{city.name}: {city.population:,} people")
"""

import logging
from dataclasses import dataclass
from enum import Enum

from airborne.physics.vectors import Vector3

logger = logging.getLogger(__name__)


class FeatureType(Enum):
    """Geographic feature types."""

    CITY = "city"  # Major city
    TOWN = "town"  # Town
    VILLAGE = "village"  # Small village
    LANDMARK = "landmark"  # Notable landmark (mountains, monuments, etc.)
    AIRPORT = "airport"  # Airport
    REGION = "region"  # State/province region
    PROVINCE = "province"  # Province/state
    COUNTRY = "country"  # Country
    OCEAN = "ocean"  # Ocean
    SEA = "sea"  # Sea
    LAKE = "lake"  # Lake
    RIVER = "river"  # River
    MOUNTAIN = "mountain"  # Mountain peak
    MOUNTAIN_RANGE = "mountain_range"  # Mountain range
    NATIONAL_PARK = "national_park"  # National park
    ISLAND = "island"  # Island
    BAY = "bay"  # Bay
    GULF = "gulf"  # Gulf
    STRAIT = "strait"  # Strait
    CHANNEL = "channel"  # Channel


@dataclass
class GeoFeature:
    """Geographic feature (city, landmark, region, etc.).

    Attributes:
        feature_id: Unique identifier
        name: Feature name
        feature_type: Type of feature
        position: Geographic position (x=lon, y=alt, z=lat in degrees)
        population: Population (for cities/towns, 0 for others)
        elevation_m: Elevation in meters (for mountains, etc.)
        area_km2: Area in square kilometers (for regions, countries, etc.)
        country: Country name
        region: Region/state/province name
        metadata: Additional metadata
    """

    feature_id: str
    name: str
    feature_type: FeatureType
    position: Vector3
    population: int = 0
    elevation_m: float = 0.0
    area_km2: float = 0.0
    country: str = ""
    region: str = ""
    metadata: dict[str, str] | None = None


class OSMProvider:
    """OpenStreetMap geographic features provider.

    Provides access to cities, landmarks, regions, countries, oceans,
    and other geographic features for navigation and callouts.

    This is a simplified implementation with built-in data.
    For production use, integrate with Overpass API or offline OSM data.

    Examples:
        >>> provider = OSMProvider()
        >>> cities = provider.get_cities_near(Vector3(-122.4194, 0, 37.7749), radius_nm=50)
        >>> for city in cities:
        ...     print(f"{city.name}: {city.population:,} people")
    """

    def __init__(self) -> None:
        """Initialize OSM provider with built-in features."""
        self.features: dict[str, GeoFeature] = {}
        self._load_builtin_features()
        logger.info("OSMProvider initialized with %d features", len(self.features))

    def _load_builtin_features(self) -> None:
        """Load built-in geographic features.

        This is a simplified dataset for demonstration.
        Production systems should load from OSM database or API.
        """
        # Major US Cities
        self._add_feature(
            "us_san_francisco",
            "San Francisco",
            FeatureType.CITY,
            Vector3(-122.4194, 52, 37.7749),
            population=873965,
            country="United States",
            region="California",
        )
        self._add_feature(
            "us_los_angeles",
            "Los Angeles",
            FeatureType.CITY,
            Vector3(-118.2437, 71, 34.0522),
            population=3979576,
            country="United States",
            region="California",
        )
        self._add_feature(
            "us_new_york",
            "New York",
            FeatureType.CITY,
            Vector3(-74.0060, 10, 40.7128),
            population=8336817,
            country="United States",
            region="New York",
        )
        self._add_feature(
            "us_chicago",
            "Chicago",
            FeatureType.CITY,
            Vector3(-87.6298, 179, 41.8781),
            population=2693976,
            country="United States",
            region="Illinois",
        )
        self._add_feature(
            "us_seattle",
            "Seattle",
            FeatureType.CITY,
            Vector3(-122.3321, 56, 47.6062),
            population=737015,
            country="United States",
            region="Washington",
        )

        # European Cities
        self._add_feature(
            "fr_paris",
            "Paris",
            FeatureType.CITY,
            Vector3(2.3522, 35, 48.8566),
            population=2165423,
            country="France",
            region="Île-de-France",
        )
        self._add_feature(
            "uk_london",
            "London",
            FeatureType.CITY,
            Vector3(-0.1276, 11, 51.5074),
            population=8982000,
            country="United Kingdom",
            region="England",
        )
        self._add_feature(
            "de_berlin",
            "Berlin",
            FeatureType.CITY,
            Vector3(13.4050, 34, 52.5200),
            population=3645000,
            country="Germany",
            region="Berlin",
        )

        # Oceans
        self._add_feature(
            "ocean_pacific",
            "Pacific Ocean",
            FeatureType.OCEAN,
            Vector3(-155.0, 0, 0.0),
            area_km2=165200000,
        )
        self._add_feature(
            "ocean_atlantic",
            "Atlantic Ocean",
            FeatureType.OCEAN,
            Vector3(-30.0, 0, 0.0),
            area_km2=106460000,
        )
        self._add_feature(
            "ocean_indian",
            "Indian Ocean",
            FeatureType.OCEAN,
            Vector3(75.0, 0, -20.0),
            area_km2=70560000,
        )

        # Seas
        self._add_feature(
            "sea_mediterranean",
            "Mediterranean Sea",
            FeatureType.SEA,
            Vector3(18.0, 0, 35.0),
            area_km2=2500000,
        )
        self._add_feature(
            "sea_caribbean",
            "Caribbean Sea",
            FeatureType.SEA,
            Vector3(-75.0, 0, 15.0),
            area_km2=2754000,
        )

        # Mountains
        self._add_feature(
            "mountain_everest",
            "Mount Everest",
            FeatureType.MOUNTAIN,
            Vector3(86.9250, 8848, 27.9881),
            elevation_m=8848,
            country="Nepal",
        )
        self._add_feature(
            "mountain_kilimanjaro",
            "Mount Kilimanjaro",
            FeatureType.MOUNTAIN,
            Vector3(37.3556, 5895, -3.0674),
            elevation_m=5895,
            country="Tanzania",
        )
        self._add_feature(
            "mountain_denali",
            "Denali",
            FeatureType.MOUNTAIN,
            Vector3(-151.0074, 6190, 63.0695),
            elevation_m=6190,
            country="United States",
            region="Alaska",
        )

        # Mountain Ranges
        self._add_feature(
            "range_rockies",
            "Rocky Mountains",
            FeatureType.MOUNTAIN_RANGE,
            Vector3(-110.0, 3000, 45.0),
            elevation_m=4401,  # Highest peak
            country="United States",
            area_km2=600000,
        )
        self._add_feature(
            "range_alps",
            "Alps",
            FeatureType.MOUNTAIN_RANGE,
            Vector3(10.0, 3000, 46.5),
            elevation_m=4810,  # Mont Blanc
            area_km2=190000,
        )
        self._add_feature(
            "range_himalayas",
            "Himalayas",
            FeatureType.MOUNTAIN_RANGE,
            Vector3(85.0, 6000, 28.0),
            elevation_m=8848,  # Everest
            area_km2=612000,
        )

        # Landmarks
        self._add_feature(
            "landmark_grand_canyon",
            "Grand Canyon",
            FeatureType.LANDMARK,
            Vector3(-112.1401, 2133, 36.1069),
            elevation_m=2133,
            country="United States",
            region="Arizona",
        )
        self._add_feature(
            "landmark_statue_liberty",
            "Statue of Liberty",
            FeatureType.LANDMARK,
            Vector3(-74.0445, 93, 40.6892),
            elevation_m=93,
            country="United States",
            region="New York",
        )
        self._add_feature(
            "landmark_eiffel_tower",
            "Eiffel Tower",
            FeatureType.LANDMARK,
            Vector3(2.2945, 330, 48.8584),
            elevation_m=330,
            country="France",
            region="Île-de-France",
        )

        # National Parks
        self._add_feature(
            "park_yellowstone",
            "Yellowstone National Park",
            FeatureType.NATIONAL_PARK,
            Vector3(-110.5885, 2400, 44.4280),
            elevation_m=2400,
            country="United States",
            region="Wyoming",
            area_km2=8991,
        )
        self._add_feature(
            "park_yosemite",
            "Yosemite National Park",
            FeatureType.NATIONAL_PARK,
            Vector3(-119.5383, 1200, 37.8651),
            elevation_m=1200,
            country="United States",
            region="California",
            area_km2=3083,
        )

        # Countries
        self._add_feature(
            "country_usa",
            "United States",
            FeatureType.COUNTRY,
            Vector3(-98.5795, 0, 39.8283),
            population=331900000,
            area_km2=9833520,
        )
        self._add_feature(
            "country_france",
            "France",
            FeatureType.COUNTRY,
            Vector3(2.2137, 0, 46.2276),
            population=67390000,
            area_km2=643801,
        )
        self._add_feature(
            "country_japan",
            "Japan",
            FeatureType.COUNTRY,
            Vector3(138.2529, 0, 36.2048),
            population=125800000,
            area_km2=377975,
        )

    def _add_feature(
        self,
        feature_id: str,
        name: str,
        feature_type: FeatureType,
        position: Vector3,
        population: int = 0,
        elevation_m: float = 0.0,
        area_km2: float = 0.0,
        country: str = "",
        region: str = "",
        metadata: dict[str, str] | None = None,
    ) -> None:
        """Add a geographic feature.

        Args:
            feature_id: Unique identifier
            name: Feature name
            feature_type: Type of feature
            position: Position (x=lon, y=alt, z=lat)
            population: Population (for cities)
            elevation_m: Elevation in meters
            area_km2: Area in square kilometers
            country: Country name
            region: Region/state name
            metadata: Additional metadata
        """
        feature = GeoFeature(
            feature_id=feature_id,
            name=name,
            feature_type=feature_type,
            position=position,
            population=population,
            elevation_m=elevation_m,
            area_km2=area_km2,
            country=country,
            region=region,
            metadata=metadata,
        )
        self.features[feature_id] = feature

    def get_features_near(
        self,
        position: Vector3,
        radius_nm: float = 50.0,
        feature_types: list[FeatureType] | None = None,
    ) -> list[GeoFeature]:
        """Get features near a position.

        Args:
            position: Search position (x=lon, y=alt, z=lat in degrees)
            radius_nm: Search radius in nautical miles
            feature_types: Filter by feature types (None = all types)

        Returns:
            List of features within radius, sorted by distance

        Examples:
            >>> features = provider.get_features_near(
            ...     Vector3(-122.4194, 0, 37.7749),
            ...     radius_nm=100,
            ...     feature_types=[FeatureType.CITY, FeatureType.LANDMARK]
            ... )
        """
        nearby_features = []

        for feature in self.features.values():
            # Filter by type
            if feature_types and feature.feature_type not in feature_types:
                continue

            # Calculate distance
            distance_nm = self._calculate_distance_nm(position, feature.position)

            if distance_nm <= radius_nm:
                nearby_features.append((distance_nm, feature))

        # Sort by distance
        nearby_features.sort(key=lambda x: x[0])

        return [feature for _, feature in nearby_features]

    def get_cities_near(
        self, position: Vector3, radius_nm: float = 50.0, min_population: int = 0
    ) -> list[GeoFeature]:
        """Get cities near a position.

        Args:
            position: Search position
            radius_nm: Search radius in nautical miles
            min_population: Minimum population filter

        Returns:
            List of cities sorted by distance

        Examples:
            >>> cities = provider.get_cities_near(
            ...     Vector3(-122.4194, 0, 37.7749),
            ...     radius_nm=50,
            ...     min_population=100000
            ... )
        """
        cities = self.get_features_near(
            position,
            radius_nm=radius_nm,
            feature_types=[FeatureType.CITY, FeatureType.TOWN, FeatureType.VILLAGE],
        )

        # Filter by population
        if min_population > 0:
            cities = [c for c in cities if c.population >= min_population]

        return cities

    def get_landmarks_near(
        self, position: Vector3, radius_nm: float = 50.0
    ) -> list[GeoFeature]:
        """Get landmarks near a position.

        Args:
            position: Search position
            radius_nm: Search radius in nautical miles

        Returns:
            List of landmarks sorted by distance

        Examples:
            >>> landmarks = provider.get_landmarks_near(
            ...     Vector3(-112.1401, 0, 36.1069),
            ...     radius_nm=20
            ... )
        """
        return self.get_features_near(
            position, radius_nm=radius_nm, feature_types=[FeatureType.LANDMARK]
        )

    def get_mountains_near(
        self, position: Vector3, radius_nm: float = 100.0
    ) -> list[GeoFeature]:
        """Get mountains near a position.

        Args:
            position: Search position
            radius_nm: Search radius in nautical miles

        Returns:
            List of mountains sorted by distance

        Examples:
            >>> mountains = provider.get_mountains_near(
            ...     Vector3(-151.0074, 0, 63.0695),
            ...     radius_nm=50
            ... )
        """
        return self.get_features_near(
            position,
            radius_nm=radius_nm,
            feature_types=[FeatureType.MOUNTAIN, FeatureType.MOUNTAIN_RANGE],
        )

    def get_water_bodies_near(
        self, position: Vector3, radius_nm: float = 200.0
    ) -> list[GeoFeature]:
        """Get water bodies (oceans, seas, lakes) near a position.

        Args:
            position: Search position
            radius_nm: Search radius in nautical miles

        Returns:
            List of water bodies sorted by distance

        Examples:
            >>> water = provider.get_water_bodies_near(
            ...     Vector3(-155.0, 0, 20.0),
            ...     radius_nm=500
            ... )
        """
        return self.get_features_near(
            position,
            radius_nm=radius_nm,
            feature_types=[
                FeatureType.OCEAN,
                FeatureType.SEA,
                FeatureType.LAKE,
                FeatureType.RIVER,
                FeatureType.BAY,
                FeatureType.GULF,
            ],
        )

    def get_feature_by_name(self, name: str, fuzzy: bool = True) -> GeoFeature | None:
        """Get feature by name.

        Args:
            name: Feature name to search
            fuzzy: Allow fuzzy matching (case-insensitive, partial)

        Returns:
            First matching feature, or None

        Examples:
            >>> feature = provider.get_feature_by_name("San Francisco")
            >>> feature = provider.get_feature_by_name("francisco", fuzzy=True)
        """
        name_lower = name.lower()

        for feature in self.features.values():
            if fuzzy:
                if name_lower in feature.name.lower():
                    return feature
            else:
                if feature.name == name:
                    return feature

        return None

    def get_closest_feature(
        self,
        position: Vector3,
        feature_types: list[FeatureType] | None = None,
        max_distance_nm: float = 1000.0,
    ) -> tuple[GeoFeature | None, float]:
        """Get closest feature to a position.

        Args:
            position: Search position
            feature_types: Filter by feature types
            max_distance_nm: Maximum search distance

        Returns:
            Tuple of (closest_feature, distance_nm) or (None, inf)

        Examples:
            >>> feature, distance = provider.get_closest_feature(
            ...     Vector3(-122.4194, 0, 37.7749),
            ...     feature_types=[FeatureType.CITY]
            ... )
        """
        closest_feature = None
        closest_distance = float("inf")

        for feature in self.features.values():
            # Filter by type
            if feature_types and feature.feature_type not in feature_types:
                continue

            # Calculate distance
            distance_nm = self._calculate_distance_nm(position, feature.position)

            if distance_nm < closest_distance and distance_nm <= max_distance_nm:
                closest_distance = distance_nm
                closest_feature = feature

        return closest_feature, closest_distance

    def _calculate_distance_nm(self, pos1: Vector3, pos2: Vector3) -> float:
        """Calculate great circle distance in nautical miles.

        Uses haversine formula.

        Args:
            pos1: First position (x=lon, z=lat in degrees)
            pos2: Second position (x=lon, z=lat in degrees)

        Returns:
            Distance in nautical miles
        """
        import math

        # Extract lat/lon
        lat1, lon1 = math.radians(pos1.z), math.radians(pos1.x)
        lat2, lon2 = math.radians(pos2.z), math.radians(pos2.x)

        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))

        # Earth radius in nautical miles
        radius_nm = 3440.065

        return c * radius_nm

    def get_feature_count(self) -> int:
        """Get total number of features.

        Returns:
            Number of features loaded

        Examples:
            >>> count = provider.get_feature_count()
            >>> print(f"Loaded {count} features")
        """
        return len(self.features)

    def get_features_by_country(self, country: str) -> list[GeoFeature]:
        """Get all features in a country.

        Args:
            country: Country name

        Returns:
            List of features in the country

        Examples:
            >>> features = provider.get_features_by_country("United States")
        """
        return [f for f in self.features.values() if f.country.lower() == country.lower()]

    def get_features_by_type(self, feature_type: FeatureType) -> list[GeoFeature]:
        """Get all features of a specific type.

        Args:
            feature_type: Feature type to filter

        Returns:
            List of features of that type

        Examples:
            >>> cities = provider.get_features_by_type(FeatureType.CITY)
            >>> oceans = provider.get_features_by_type(FeatureType.OCEAN)
        """
        return [f for f in self.features.values() if f.feature_type == feature_type]

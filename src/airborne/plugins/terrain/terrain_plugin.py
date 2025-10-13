"""Terrain plugin for AirBorne flight simulator.

Provides terrain elevation data, geographic features, and collision detection
to other plugins through the component registry.

The plugin integrates:
- ElevationService: Terrain elevation queries with caching
- OSMProvider: Geographic features (cities, mountains, oceans, etc.)
- TerrainCollisionDetector: CFIT prevention and terrain awareness

Typical usage:
    The terrain plugin is loaded automatically and provides terrain services
    to other plugins via the component registry.
"""

from typing import Any

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType
from airborne.physics.collision import TerrainCollisionDetector
from airborne.physics.vectors import Vector3
from airborne.terrain import (
    ElevationService,
    OSMProvider,
    SimpleFlatEarthProvider,
    SRTMProvider,
)

logger = get_logger(__name__)


class TerrainPlugin(IPlugin):
    """Terrain plugin that provides elevation and geographic data.

    This plugin manages the terrain subsystem, providing elevation queries,
    geographic features, and terrain collision detection to other plugins.

    Components provided:
    - elevation_service: ElevationService for terrain elevation queries
    - osm_provider: OSMProvider for geographic features
    - terrain_collision_detector: TerrainCollisionDetector for CFIT prevention

    The plugin subscribes to position updates and publishes terrain elevation
    data for the current aircraft position.
    """

    def __init__(self) -> None:
        """Initialize terrain plugin."""
        self.context: PluginContext | None = None
        self.elevation_service: ElevationService | None = None
        self.osm_provider: OSMProvider | None = None
        self.collision_detector: TerrainCollisionDetector | None = None

        # Current aircraft position (updated via messages)
        self._current_position: Vector3 | None = None
        self._current_altitude: float = 0.0

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata.

        Returns:
            PluginMetadata describing this terrain plugin.
        """
        return PluginMetadata(
            name="terrain_plugin",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.CORE,
            dependencies=[],
            provides=["elevation_service", "osm_provider", "terrain_collision_detector"],
            optional=False,
            update_priority=15,  # Update after physics but before other systems
            requires_physics=False,
            description="Terrain elevation and geographic features plugin",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the terrain plugin.

        Args:
            context: Plugin context with access to core systems.
        """
        self.context = context

        # Get terrain config from context
        terrain_config = context.config.get("terrain", {})

        # Create elevation service
        self.elevation_service = ElevationService()

        # Add elevation providers based on config
        providers = terrain_config.get("providers", ["simple_flat_earth"])

        for provider_name in providers:
            if provider_name == "srtm":
                use_fallback = terrain_config.get("srtm_fallback", True)
                srtm_provider = SRTMProvider(use_fallback=use_fallback)
                self.elevation_service.add_provider(srtm_provider)
                logger.info("Added SRTM elevation provider (fallback=%s)", use_fallback)
            elif provider_name == "simple_flat_earth":
                flat_earth_provider = SimpleFlatEarthProvider()
                self.elevation_service.add_provider(flat_earth_provider)
                logger.info("Added SimpleFlatEarth elevation provider")

        # Create OSM provider
        self.osm_provider = OSMProvider()
        logger.info(
            "Initialized OSM provider with %d features", self.osm_provider.get_feature_count()
        )

        # Create collision detector with elevation service
        self.collision_detector = TerrainCollisionDetector(self.elevation_service)

        # Configure collision detector thresholds if specified
        if "collision_thresholds" in terrain_config:
            thresholds = terrain_config["collision_thresholds"]
            self.collision_detector.set_warning_thresholds(
                warning_ft=thresholds.get("warning_ft", 500.0),
                caution_ft=thresholds.get("caution_ft", 200.0),
                critical_ft=thresholds.get("critical_ft", 100.0),
            )
            logger.info("Configured collision thresholds: %s", thresholds)

        # Register components in registry
        if context.plugin_registry:
            context.plugin_registry.register("elevation_service", self.elevation_service)
            context.plugin_registry.register("osm_provider", self.osm_provider)
            context.plugin_registry.register("terrain_collision_detector", self.collision_detector)

            # Update physics plugin's collision detector if it exists
            try:
                physics_collision_detector = context.plugin_registry.get("collision_detector")
                if physics_collision_detector and hasattr(
                    physics_collision_detector, "elevation_service"
                ):
                    physics_collision_detector.elevation_service = self.elevation_service
                    logger.info("Updated physics collision detector with elevation service")
            except KeyError:
                pass  # Physics plugin not loaded yet

        # Subscribe to position updates
        context.message_queue.subscribe(MessageTopic.POSITION_UPDATED, self.handle_message)

        logger.info("Terrain plugin initialized")

    def update(self, dt: float) -> None:
        """Update terrain system.

        Args:
            dt: Delta time in seconds since last update.
        """
        if not self.context or not self._current_position or not self.elevation_service:
            return

        # Get terrain elevation at current position
        try:
            elevation = self.elevation_service.get_elevation_at_position(self._current_position)

            # Publish terrain update message
            self.context.message_queue.publish(
                Message(
                    sender="terrain_plugin",
                    recipients=["*"],
                    topic=MessageTopic.TERRAIN_UPDATED,
                    data={
                        "elevation": elevation,
                        "position": {
                            "x": self._current_position.x,
                            "y": self._current_position.y,
                            "z": self._current_position.z,
                        },
                    },
                    priority=MessagePriority.NORMAL,
                )
            )

        except Exception as e:
            logger.warning("Failed to get terrain elevation: %s", e)

    def shutdown(self) -> None:
        """Shutdown the terrain plugin."""
        if self.context:
            # Unsubscribe from messages
            self.context.message_queue.unsubscribe(
                MessageTopic.POSITION_UPDATED, self.handle_message
            )

            # Unregister components
            if self.context.plugin_registry:
                self.context.plugin_registry.unregister("elevation_service")
                self.context.plugin_registry.unregister("osm_provider")
                self.context.plugin_registry.unregister("terrain_collision_detector")

        logger.info("Terrain plugin shutdown")

    def handle_message(self, message: Message) -> None:
        """Handle messages from other plugins.

        Args:
            message: Message from the queue.
        """
        if message.topic == MessageTopic.POSITION_UPDATED:
            # Update current position
            data = message.data
            if "position" in data:
                pos = data["position"]
                self._current_position = Vector3(
                    float(pos.get("x", 0.0)), float(pos.get("y", 0.0)), float(pos.get("z", 0.0))
                )
                self._current_altitude = float(pos.get("y", 0.0))

    def on_config_changed(self, config: dict[str, Any]) -> None:
        """Handle configuration changes.

        Args:
            config: New configuration dictionary.
        """
        terrain_config = config.get("terrain", {})

        # Update collision thresholds if changed
        if self.collision_detector and "collision_thresholds" in terrain_config:
            thresholds = terrain_config["collision_thresholds"]
            self.collision_detector.set_warning_thresholds(
                warning_ft=thresholds.get("warning_ft", 500.0),
                caution_ft=thresholds.get("caution_ft", 200.0),
                critical_ft=thresholds.get("critical_ft", 100.0),
            )
            logger.info("Updated collision thresholds: %s", thresholds)

    def get_elevation_at(self, latitude: float, longitude: float) -> float:
        """Get terrain elevation at specific coordinates.

        Args:
            latitude: Latitude in degrees.
            longitude: Longitude in degrees.

        Returns:
            Elevation in meters (MSL).
        """
        if not self.elevation_service:
            return 0.0

        return self.elevation_service.get_elevation(latitude, longitude)

    def get_features_near(
        self, position: Vector3, radius_nm: float, feature_types: list | None = None
    ) -> list:
        """Get geographic features near position.

        Args:
            position: Center position (x=lon, z=lat).
            radius_nm: Search radius in nautical miles.
            feature_types: Optional list of FeatureType to filter by.

        Returns:
            List of GeoFeature objects near position.
        """
        if not self.osm_provider:
            return []

        return self.osm_provider.get_features_near(position, radius_nm, feature_types)

    def check_terrain_collision(self, position: Vector3, altitude_msl: float) -> Any:
        """Check for terrain collision at position.

        Args:
            position: Aircraft position.
            altitude_msl: Aircraft altitude (MSL).

        Returns:
            CollisionResult with collision details.
        """
        if not self.collision_detector:
            # Return a dummy result indicating no collision
            from airborne.physics.collision import CollisionResult, CollisionSeverity, CollisionType

            return CollisionResult(
                is_colliding=False,
                collision_type=CollisionType.NONE,
                severity=CollisionSeverity.SAFE,
                terrain_elevation_m=0.0,
                aircraft_altitude_m=altitude_msl,
                distance_to_terrain=altitude_msl,
                agl_altitude=altitude_msl,
                position=position,
            )

        return self.collision_detector.check_terrain_collision(position, altitude_msl)

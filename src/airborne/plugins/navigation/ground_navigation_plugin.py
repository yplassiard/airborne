"""Ground Navigation Plugin for AirBorne.

Provides ground navigation with proximity audio cues for taxiing without visual feedback.
Integrates airport database, taxiways, ground physics, and proximity beeping.

Configuration:
    enabled: true
    audio_enabled: true
    beep_style: "sine"  # sine, square, triangle, sawtooth, chirp
    beep_pattern: "exponential"  # linear, exponential, stepped, constant
    max_beep_frequency: 5.0  # Max beeps per second
    proximity_distance: 100.0  # Max proximity detection distance (m)
"""

import logging
from pathlib import Path
from typing import Any

from airborne.airports.database import AirportDatabase
from airborne.airports.spatial_index import SpatialIndex
from airborne.airports.taxiway_generator import TaxiwayGenerator
from airborne.audio.beeper import BeepStyle, ProximityBeeper
from airborne.audio.proximity import BeepPattern, ProximityCueManager
from airborne.core.plugin import IPlugin, PluginMetadata, PluginType
from airborne.physics.ground_physics import GroundPhysics
from airborne.physics.vectors import Vector3

logger = logging.getLogger(__name__)


class GroundNavigationPlugin(IPlugin):
    """Ground navigation plugin with proximity audio cues.

    Provides:
    - Airport/taxiway database loading
    - Nearest airport detection
    - Taxiway node proximity tracking
    - Ground physics simulation
    - Audio beeping cues for navigation

    Examples:
        In aircraft YAML:
            plugins:
              - name: ground_navigation
                config:
                  enabled: true
                  audio_enabled: true
                  beep_style: "sine"
    """

    def __init__(self) -> None:
        """Initialize ground navigation plugin."""
        super().__init__()

        # Components
        self.airport_db: AirportDatabase | None = None
        self.spatial_index: SpatialIndex | None = None
        self.taxiway_gen: TaxiwayGenerator | None = None
        self.ground_physics: GroundPhysics | None = None
        self.proximity_manager: ProximityCueManager | None = None
        self.beeper: ProximityBeeper | None = None

        # State
        self.current_airport_icao: str | None = None
        self.nearest_taxiway_node: str | None = None
        self.last_position: Vector3 | None = None

        # Config
        self.audio_enabled = True
        self.beep_style = BeepStyle.SINE
        self.beep_pattern = BeepPattern.EXPONENTIAL
        self.max_beep_frequency = 5.0
        self.proximity_distance = 100.0

        logger.info("Ground Navigation Plugin initialized")

    def get_metadata(self) -> PluginMetadata:
        """Get plugin metadata."""
        return PluginMetadata(
            name="ground_navigation",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.AVIONICS,
            dependencies=[],
            provides=["ground_navigation", "proximity_audio", "taxiway_routing"],
        )

    def handle_message(self, message: Any) -> None:
        """Handle plugin messages.

        Args:
            message: Message from plugin system
        """
        # Currently no message handling
        pass

    def initialize(self, context: Any) -> None:
        """Initialize the plugin.

        Args:
            context: Plugin context with configuration
        """
        config = context.get("config", {})

        # Load configuration
        self.audio_enabled = config.get("audio_enabled", True)
        beep_style_str = config.get("beep_style", "sine")
        beep_pattern_str = config.get("beep_pattern", "exponential")
        self.max_beep_frequency = config.get("max_beep_frequency", 5.0)
        self.proximity_distance = config.get("proximity_distance", 100.0)

        # Parse enums
        try:
            self.beep_style = BeepStyle(beep_style_str.lower())
        except ValueError:
            logger.warning("Invalid beep_style '%s', using SINE", beep_style_str)
            self.beep_style = BeepStyle.SINE

        try:
            self.beep_pattern = BeepPattern(beep_pattern_str.lower())
        except ValueError:
            logger.warning("Invalid beep_pattern '%s', using EXPONENTIAL", beep_pattern_str)
            self.beep_pattern = BeepPattern.EXPONENTIAL

        # Initialize components
        self.airport_db = AirportDatabase()
        self.spatial_index = SpatialIndex()
        self.taxiway_gen = TaxiwayGenerator()
        self.ground_physics = GroundPhysics()
        self.proximity_manager = ProximityCueManager()
        self.beeper = ProximityBeeper(sample_rate=44100)

        # Load airport data
        data_dir = Path(__file__).parent.parent.parent.parent.parent / "data" / "airports"

        # Only load if explicitly enabled in config (to avoid slow initialization in tests)
        if config.get("load_airport_data", False) and (data_dir / "airports.csv").exists():
            logger.info("Loading airport database from %s", data_dir)
            self.airport_db.load_from_csv(data_dir)

            # Build spatial index
            logger.info("Building spatial index...")
            for icao, airport in self.airport_db.airports.items():
                self.spatial_index.insert(icao, airport.position)

            logger.info(
                "Loaded %d airports with spatial indexing", self.airport_db.get_airport_count()
            )
        else:
            logger.debug("Airport database loading skipped (set load_airport_data=true to enable)")

        logger.info(
            "Ground Navigation initialized (audio=%s, beep_style=%s, pattern=%s)",
            self.audio_enabled,
            self.beep_style.value,
            self.beep_pattern.value,
        )

    def update(self, dt: float) -> None:
        """Update ground navigation.

        Args:
            dt: Time since last update (seconds)
        """
        if not self.airport_db or not self.spatial_index:
            return

        # Get aircraft position from last known position
        # Note: This plugin would need to subscribe to position updates
        # For now, skip if no position is available
        if not self.last_position:
            return

        position = self.last_position
        if not isinstance(position, Vector3):
            # Convert from dict if necessary
            position = Vector3(position.get("x", 0), position.get("y", 0), position.get("z", 0))

        self.last_position = position

        # Find nearest airport (within reasonable range)
        nearest_airports = self.spatial_index.query_radius(position, radius_nm=10.0)

        if nearest_airports:
            nearest_icao = nearest_airports[0]  # Closest airport

            # Check if we've changed airports
            if nearest_icao != self.current_airport_icao:
                self._switch_airport(nearest_icao)

            # Update proximity cues
            if self.audio_enabled and self.proximity_manager:
                should_beep = self.proximity_manager.update(position, dt)

                # Generate beep if needed
                if should_beep and self.beeper:
                    target_id, distance, frequency = self.proximity_manager.get_nearest_target(
                        position
                    )

                    if target_id and frequency > 0:
                        # Generate beep sound
                        beep_samples = self.beeper.get_beep_if_ready(
                            distance_m=distance,
                            beep_frequency_hz=min(frequency, self.max_beep_frequency),
                            delta_time=dt,
                            style=self.beep_style,
                        )

                        # TODO: Play beep_samples through audio engine
                        # For now, just log that we would beep
                        if beep_samples is not None:
                            logger.debug(
                                "Beep: target=%s, distance=%.1fm, frequency=%.2fHz",
                                target_id,
                                distance,
                                frequency,
                            )

        # TODO: Ground forces calculation
        # In real implementation, would subscribe to aircraft state messages
        # to get on_ground, velocity, heading, control inputs, etc.
        # For now, this functionality is stubbed out

    def shutdown(self) -> None:
        """Shutdown the plugin."""
        if self.proximity_manager:
            self.proximity_manager.clear_targets()

        logger.info("Ground Navigation Plugin shutdown")

    def _switch_airport(self, icao: str) -> None:
        """Switch to a new airport.

        Args:
            icao: Airport ICAO code
        """
        if not self.airport_db or not self.taxiway_gen or not self.proximity_manager:
            return

        logger.info("Switching to airport: %s", icao)
        self.current_airport_icao = icao

        # Clear existing proximity targets
        self.proximity_manager.clear_targets()

        # Get airport and runways
        airport = self.airport_db.get_airport(icao)
        if not airport:
            logger.warning("Airport %s not found", icao)
            return

        runways = self.airport_db.get_runways(icao)

        # Classify and generate taxiways
        from airborne.airports.classifier import AirportClassifier

        classifier = AirportClassifier()
        category = classifier.classify(airport, runways)

        logger.info("Airport %s classified as: %s", icao, category.value)

        # Generate taxiway network
        graph = self.taxiway_gen.generate(airport, runways, category)

        logger.info(
            "Generated taxiway network: %d nodes, %d edges",
            graph.get_node_count(),
            graph.get_edge_count(),
        )

        # Add proximity targets for taxiway nodes
        for node_id, node in graph.nodes.items():
            self.proximity_manager.add_target(
                target_id=node_id,
                position=node.position,
                pattern=self.beep_pattern,
                min_distance_m=5.0,
                max_distance_m=self.proximity_distance,
                min_frequency_hz=0.5,
                max_frequency_hz=self.max_beep_frequency,
            )

        logger.info("Added %d proximity targets", len(graph.nodes))

    def get_status(self) -> dict[str, Any]:
        """Get plugin status.

        Returns:
            Status dictionary
        """
        return {
            "current_airport": self.current_airport_icao,
            "nearest_node": self.nearest_taxiway_node,
            "audio_enabled": self.audio_enabled,
            "beep_style": self.beep_style.value,
            "beep_pattern": self.beep_pattern.value,
            "active_target": (
                self.proximity_manager.get_active_target_id() if self.proximity_manager else None
            ),
            "current_frequency": (
                self.proximity_manager.get_current_frequency() if self.proximity_manager else 0.0
            ),
            "target_count": (len(self.proximity_manager.targets) if self.proximity_manager else 0),
        }

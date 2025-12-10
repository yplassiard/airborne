"""Landing condition monitor plugin.

Monitors landing parameters and enforces aircraft limits.
Integrates with damage model to apply consequences for exceeded limits.

Monitors:
- Sink rate at touchdown
- Crosswind component
- Approach speed
- Pitch/bank at touchdown
- Runway surface compatibility
- On/off runway detection

Typical usage:
    monitor = LandingMonitorPlugin()
    monitor.initialize(context)
    # Plugin monitors landings automatically
"""

from typing import Any

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType
from airborne.plugins.safety.damage_model import (
    CrashReport,
    DamageModel,
    FlightState,
)

logger = get_logger(__name__)


class LandingMonitorPlugin(IPlugin):
    """Landing condition monitor plugin.

    Monitors aircraft during landing and applies damage/crash
    consequences when limits are exceeded.
    """

    def __init__(self) -> None:
        """Initialize landing monitor."""
        self.context: PluginContext | None = None
        self.enabled = True

        # Damage model
        self.damage_model: DamageModel | None = None

        # Current flight state
        self._on_ground = False
        self._was_on_ground = False
        self._on_runway = False
        self._current_runway: Any = None
        self._current_runway_end: str = ""

        # Flight parameters
        self._altitude_msl_ft = 0.0
        self._altitude_agl_ft = 0.0
        self._airspeed_kts = 0.0
        self._groundspeed_kts = 0.0
        self._vertical_speed_fpm = 0.0
        self._heading_deg = 0.0
        self._pitch_deg = 0.0
        self._roll_deg = 0.0
        self._latitude = 0.0
        self._longitude = 0.0
        self._flaps = 0.0
        self._throttle = 0.0
        self._fuel_gal = 0.0
        self._weight_lbs = 0.0
        self._terrain_elevation_ft = 0.0

        # Wind data
        self._wind_speed_kts = 0.0
        self._wind_direction_deg = 0.0
        self._crosswind_kts = 0.0

        # Airport database reference
        self._airport_db = None

        # Simulation time
        self._sim_time = 0.0

        # Crash report directory
        self._crash_report_dir = "crash_reports"

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return PluginMetadata(
            name="landing_monitor",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.AVIONICS,
            dependencies=[],
            provides=["landing_monitor", "damage_model"],
            optional=False,
            update_priority=25,  # After GPWS
            requires_physics=True,
            description="Monitors landing conditions and enforces aircraft limits",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the landing monitor.

        Args:
            context: Plugin context with access to core systems.
        """
        self.context = context

        # Get config
        monitor_config = context.config.get("landing_monitor", {})
        self.enabled = monitor_config.get("enabled", True)
        self._crash_report_dir = monitor_config.get("crash_report_dir", "crash_reports")

        # Get aircraft config for damage model
        aircraft_config = context.config.get("aircraft", {})
        self.damage_model = DamageModel(aircraft_config)

        # Set callsign if available
        callsign = context.config.get("callsign", "")
        if self.damage_model:
            self.damage_model.callsign = callsign

        # Get airport database from registry
        if context.plugin_registry:
            try:
                self._airport_db = context.plugin_registry.get("airport_database")
            except KeyError:
                logger.warning("Airport database not available")

        # Subscribe to messages
        context.message_queue.subscribe(MessageTopic.POSITION_UPDATED, self.handle_message)
        context.message_queue.subscribe(MessageTopic.TERRAIN_UPDATED, self.handle_message)
        context.message_queue.subscribe(MessageTopic.WEATHER_UPDATED, self.handle_message)

        # Register components
        if context.plugin_registry:
            context.plugin_registry.register("landing_monitor", self)
            context.plugin_registry.register("damage_model", self.damage_model)

        logger.info("Landing monitor initialized")

    def update(self, dt: float) -> None:
        """Update landing monitor.

        Args:
            dt: Delta time in seconds.
        """
        if not self.enabled or not self.context or not self.damage_model:
            return

        self._sim_time += dt

        # Check for crash
        if self.damage_model.is_crashed:
            return  # Already crashed, no more updates

        # Detect touchdown
        if self._on_ground and not self._was_on_ground:
            self._handle_touchdown()

        # Check off-runway operation
        if self._on_ground:
            self._check_runway_status()

        # Update previous state
        self._was_on_ground = self._on_ground

    def _handle_touchdown(self) -> None:
        """Handle touchdown event - check all landing parameters."""
        logger.info(
            "Touchdown detected: sink_rate=%.0f fpm, speed=%.0f kts",
            abs(self._vertical_speed_fpm),
            self._airspeed_kts,
        )

        location = (self._latitude, self._longitude)

        # Check sink rate
        self.damage_model.check_hard_landing(
            abs(self._vertical_speed_fpm), self._sim_time, location
        )

        if self.damage_model.is_crashed:
            self._handle_crash()
            return

        # Check crosswind
        self._update_crosswind()
        self.damage_model.check_crosswind(self._crosswind_kts, self._sim_time, location)

        if self.damage_model.is_crashed:
            self._handle_crash()
            return

        # Check runway status
        self._check_runway_at_touchdown()

        if self.damage_model.is_crashed:
            self._handle_crash()

    def _check_runway_at_touchdown(self) -> None:
        """Check if touchdown is on a runway and surface compatibility."""
        if not self._airport_db:
            return

        location = (self._latitude, self._longitude)

        # Check if on runway
        result = self._airport_db.get_runway_at_position(self._latitude, self._longitude)

        if result:
            runway, end_id = result
            self._on_runway = True
            self._current_runway = runway
            self._current_runway_end = end_id

            # Check surface compatibility
            surface_type = runway.surface.value if hasattr(runway.surface, "value") else str(runway.surface)
            self.damage_model.check_surface_compatibility(
                surface_type, self._sim_time, location
            )

            logger.info(
                "Touchdown on runway %s, surface: %s",
                runway.runway_id,
                surface_type,
            )
        else:
            # Off-runway landing
            self._on_runway = False
            self._current_runway = None

            logger.warning("Off-runway touchdown detected at %.6f, %.6f", *location)

            # Apply off-runway damage (unknown surface = prohibited)
            self.damage_model.check_surface_compatibility(
                "unknown", self._sim_time, location
            )

    def _check_runway_status(self) -> None:
        """Check current runway status while on ground."""
        if not self._airport_db or not self._on_ground:
            return

        # Update runway position
        result = self._airport_db.get_runway_at_position(self._latitude, self._longitude)

        if result:
            runway, end_id = result
            self._on_runway = True
            self._current_runway = runway
            self._current_runway_end = end_id
        else:
            # Check for runway excursion
            if self._on_runway and self._groundspeed_kts > 20:
                # Was on runway, now off - runway excursion
                location = (self._latitude, self._longitude)
                self.damage_model.check_off_runway(
                    on_runway=False,
                    on_ground=True,
                    groundspeed_kts=self._groundspeed_kts,
                    sim_time=self._sim_time,
                    location=location,
                )

                if self.damage_model.is_crashed:
                    self._handle_crash()
                    return

            self._on_runway = False
            self._current_runway = None

    def _update_crosswind(self) -> None:
        """Calculate crosswind component based on runway heading."""
        if not self._current_runway:
            self._crosswind_kts = 0.0
            return

        import math

        # Get runway heading
        runway_heading = self._current_runway.le_heading_deg
        if self._current_runway_end == self._current_runway.he_ident:
            runway_heading = self._current_runway.he_heading_deg

        # Calculate wind angle relative to runway
        wind_angle = self._wind_direction_deg - runway_heading
        wind_angle_rad = math.radians(wind_angle)

        # Crosswind = wind_speed * sin(angle)
        self._crosswind_kts = self._wind_speed_kts * math.sin(wind_angle_rad)

    def _handle_crash(self) -> None:
        """Handle crash event - generate report and notify."""
        if not self.damage_model or not self.context:
            return

        # Create flight state snapshot
        flight_state = FlightState(
            altitude_msl_ft=self._altitude_msl_ft,
            altitude_agl_ft=self._altitude_agl_ft,
            airspeed_kts=self._airspeed_kts,
            groundspeed_kts=self._groundspeed_kts,
            vertical_speed_fpm=self._vertical_speed_fpm,
            heading_deg=self._heading_deg,
            pitch_deg=self._pitch_deg,
            roll_deg=self._roll_deg,
            latitude=self._latitude,
            longitude=self._longitude,
            on_ground=self._on_ground,
            flaps_position=self._flaps,
            throttle_position=self._throttle,
            fuel_remaining_gal=self._fuel_gal,
            weight_lbs=self._weight_lbs,
            wind_speed_kts=self._wind_speed_kts,
            wind_direction_deg=self._wind_direction_deg,
            crosswind_component_kts=self._crosswind_kts,
        )

        # Get airport info
        airport_icao = None
        runway_id = None
        if self._current_runway:
            airport_icao = self._current_runway.airport_icao
            runway_id = self._current_runway.runway_id

        # Generate crash report
        report = self.damage_model.generate_crash_report(
            flight_state, airport_icao, runway_id
        )

        # Save report
        report_path = report.save_to_file(self._crash_report_dir)

        # Get audio summary
        audio_summary = self.damage_model.get_audio_crash_summary()

        logger.critical("CRASH: %s", audio_summary)

        # Publish crash event
        self.context.message_queue.publish(
            Message(
                sender="landing_monitor",
                recipients=["*"],
                topic=MessageTopic.SYSTEM_ALERT,
                data={
                    "type": "crash",
                    "cause": report.primary_cause.value,
                    "description": report.cause_description,
                    "audio_summary": audio_summary,
                    "report_path": str(report_path),
                },
                priority=MessagePriority.CRITICAL,
            )
        )

        # Request TTS for crash announcement
        self.context.message_queue.publish(
            Message(
                sender="landing_monitor",
                recipients=["tts_service"],
                topic=MessageTopic.TTS_REQUEST,
                data={
                    "text": audio_summary,
                    "priority": "critical",
                },
                priority=MessagePriority.CRITICAL,
            )
        )

    def handle_message(self, message: Message) -> None:
        """Handle messages from other plugins.

        Args:
            message: Message from queue.
        """
        if message.topic == MessageTopic.POSITION_UPDATED:
            data = message.data
            self._on_ground = data.get("on_ground", False)
            self._altitude_msl_ft = data.get("altitude_ft", 0.0)
            self._airspeed_kts = data.get("airspeed_kts", 0.0)
            self._groundspeed_kts = data.get("groundspeed_kts", 0.0)
            self._vertical_speed_fpm = data.get("vertical_speed_fpm", 0.0)
            self._heading_deg = data.get("heading_deg", 0.0)
            self._pitch_deg = data.get("pitch_deg", 0.0)
            self._roll_deg = data.get("roll_deg", 0.0)
            self._latitude = data.get("latitude", 0.0)
            self._longitude = data.get("longitude", 0.0)
            self._flaps = data.get("flaps", 0.0)
            self._throttle = data.get("throttle", 0.0)
            self._fuel_gal = data.get("fuel_gal", 0.0)
            self._weight_lbs = data.get("weight_lbs", 0.0)

            if "agl_altitude_ft" in data:
                self._altitude_agl_ft = data["agl_altitude_ft"]

        elif message.topic == MessageTopic.TERRAIN_UPDATED:
            data = message.data
            if "elevation" in data:
                self._terrain_elevation_ft = data["elevation"] * 3.28084
                self._altitude_agl_ft = self._altitude_msl_ft - self._terrain_elevation_ft

        elif message.topic == MessageTopic.WEATHER_UPDATED:
            data = message.data
            self._wind_speed_kts = data.get("wind_speed_kts", 0.0)
            self._wind_direction_deg = data.get("wind_direction_deg", 0.0)

    def shutdown(self) -> None:
        """Shutdown the landing monitor."""
        if self.context:
            self.context.message_queue.unsubscribe(
                MessageTopic.POSITION_UPDATED, self.handle_message
            )
            self.context.message_queue.unsubscribe(
                MessageTopic.TERRAIN_UPDATED, self.handle_message
            )
            self.context.message_queue.unsubscribe(
                MessageTopic.WEATHER_UPDATED, self.handle_message
            )

            if self.context.plugin_registry:
                self.context.plugin_registry.unregister("landing_monitor")
                self.context.plugin_registry.unregister("damage_model")

        logger.info("Landing monitor shutdown")

    def on_config_changed(self, config: dict[str, Any]) -> None:
        """Handle configuration changes.

        Args:
            config: New configuration dictionary.
        """
        monitor_config = config.get("landing_monitor", {})
        self.enabled = monitor_config.get("enabled", True)
        self._crash_report_dir = monitor_config.get("crash_report_dir", "crash_reports")

    def reset(self) -> None:
        """Reset the landing monitor and damage model."""
        if self.damage_model:
            self.damage_model.reset()

        self._on_runway = False
        self._current_runway = None
        self._was_on_ground = False

        logger.info("Landing monitor reset")

    def get_damage_status(self) -> dict[str, float]:
        """Get current damage status.

        Returns:
            Dictionary of damage type to damage level (0.0-1.0)
        """
        if not self.damage_model:
            return {}

        return {dt.value: level for dt, level in self.damage_model.damage.items()}

    def is_on_runway(self) -> bool:
        """Check if aircraft is currently on a runway.

        Returns:
            True if on a runway
        """
        return self._on_runway

    def get_current_runway(self) -> tuple[Any, str] | None:
        """Get current runway info.

        Returns:
            Tuple of (Runway, end_ident) if on runway, None otherwise
        """
        if self._current_runway:
            return (self._current_runway, self._current_runway_end)
        return None

"""Ground Proximity Warning System (GPWS) plugin.

Provides audio warnings for terrain proximity and excessive sink rate.
Integrates with terrain elevation service and TTS for spoken callouts.

Typical usage:
    gpws = GPWSPlugin()
    gpws.initialize(context)
    # Plugin updates automatically with terrain data

Warnings provided:
    - "TERRAIN" - Close to terrain
    - "PULL UP" - Imminent ground contact
    - "TOO LOW TERRAIN" - Low altitude with high sink rate
    - "SINK RATE" - Excessive descent rate
    - "DON'T SINK" - Losing altitude after takeoff
"""

from enum import Enum
from typing import Any

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType
from airborne.physics.collision import CollisionSeverity

logger = get_logger(__name__)


class GPWSWarning(Enum):
    """GPWS warning types based on real-world EGPWS modes."""

    # Mode 1: Excessive descent rate
    SINK_RATE = "sink_rate"
    PULL_UP_SINK = "pull_up_sink"

    # Mode 2: Excessive terrain closure rate
    TERRAIN = "terrain"
    PULL_UP_TERRAIN = "pull_up_terrain"

    # Mode 3: Altitude loss after takeoff
    DONT_SINK = "dont_sink"

    # Mode 4: Unsafe terrain clearance
    TOO_LOW_TERRAIN = "too_low_terrain"
    TOO_LOW_GEAR = "too_low_gear"
    TOO_LOW_FLAPS = "too_low_flaps"

    # Mode 5: Below glideslope (not implemented - needs ILS)
    # GLIDESLOPE = "glideslope"

    # Mode 6: Altitude callouts
    ALTITUDE_500 = "five_hundred"
    ALTITUDE_100 = "one_hundred"
    ALTITUDE_50 = "fifty"
    ALTITUDE_40 = "forty"
    ALTITUDE_30 = "thirty"
    ALTITUDE_20 = "twenty"
    ALTITUDE_10 = "ten"

    # Terrain awareness
    TERRAIN_AHEAD = "terrain_ahead"
    OBSTACLE_AHEAD = "obstacle_ahead"


class GPWSPlugin(IPlugin):
    """Ground Proximity Warning System plugin.

    Provides terrain proximity warnings and altitude callouts based on
    the Enhanced Ground Proximity Warning System (EGPWS) found in
    modern aircraft.

    Features:
    - Terrain proximity warnings based on AGL altitude
    - Excessive sink rate warnings
    - Altitude callouts on approach (500, 100, 50, 40, 30, 20, 10 ft)
    - Takeoff mode (don't sink after liftoff)
    """

    # Warning thresholds (feet)
    TERRAIN_WARNING_FT = 500  # "TERRAIN" warning
    PULL_UP_FT = 100  # "PULL UP" warning
    TOO_LOW_TERRAIN_FT = 200  # "TOO LOW TERRAIN" with high sink rate

    # Sink rate thresholds (fpm)
    SINK_RATE_WARNING_FPM = 1500  # "SINK RATE" warning
    SINK_RATE_PULL_UP_FPM = 2500  # "PULL UP" for sink rate
    DONT_SINK_THRESHOLD_FPM = 500  # Post-takeoff altitude loss

    # Altitude callouts (feet)
    ALTITUDE_CALLOUTS = [500, 100, 50, 40, 30, 20, 10]

    # Minimum time between repeated warnings (seconds)
    WARNING_COOLDOWN = 2.0
    ALTITUDE_CALLOUT_COOLDOWN = 5.0

    def __init__(self) -> None:
        """Initialize GPWS plugin."""
        self.context: PluginContext | None = None
        self.enabled = True

        # Current state
        self._agl_altitude_ft = 0.0
        self._sink_rate_fpm = 0.0
        self._airspeed_kts = 0.0
        self._on_ground = True
        self._gear_down = True
        self._flaps_position = 0.0
        self._latitude = 0.0
        self._longitude = 0.0

        # Takeoff mode
        self._takeoff_mode = False
        self._max_altitude_after_takeoff_ft = 0.0

        # Warning state
        self._last_warning: GPWSWarning | None = None
        self._last_warning_time = 0.0
        self._last_altitude_callout = 0
        self._last_altitude_callout_time = 0.0

        # TTS queue reference
        self._tts_queue = None

        # Terrain service reference
        self._elevation_service = None
        self._collision_detector = None

        # Simulation time tracking
        self._sim_time = 0.0

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return PluginMetadata(
            name="gpws_plugin",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.AVIONICS,
            dependencies=["terrain_plugin"],
            provides=["gpws"],
            optional=False,
            update_priority=20,  # After physics and terrain
            requires_physics=True,
            description="Ground Proximity Warning System with terrain and sink rate warnings",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the GPWS plugin.

        Args:
            context: Plugin context with access to core systems.
        """
        self.context = context

        # Get GPWS config
        gpws_config = context.config.get("gpws", {})
        self.enabled = gpws_config.get("enabled", True)

        # Customize thresholds if specified
        self.TERRAIN_WARNING_FT = gpws_config.get("terrain_warning_ft", 500)
        self.PULL_UP_FT = gpws_config.get("pull_up_ft", 100)
        self.SINK_RATE_WARNING_FPM = gpws_config.get("sink_rate_warning_fpm", 1500)

        # Get elevation service from registry
        if context.plugin_registry:
            try:
                self._elevation_service = context.plugin_registry.get("elevation_service")
                self._collision_detector = context.plugin_registry.get(
                    "terrain_collision_detector"
                )
            except KeyError:
                logger.warning("Terrain services not available - GPWS using basic mode")

        # Subscribe to relevant messages
        context.message_queue.subscribe(MessageTopic.POSITION_UPDATED, self.handle_message)
        context.message_queue.subscribe(MessageTopic.TERRAIN_UPDATED, self.handle_message)

        # Register in plugin registry
        if context.plugin_registry:
            context.plugin_registry.register("gpws", self)

        logger.info("GPWS plugin initialized (enabled=%s)", self.enabled)

    def update(self, dt: float) -> None:
        """Update GPWS system.

        Args:
            dt: Delta time in seconds.
        """
        if not self.enabled or not self.context:
            return

        self._sim_time += dt

        # Skip updates while on ground
        if self._on_ground:
            self._takeoff_mode = False
            self._max_altitude_after_takeoff_ft = 0.0
            return

        # Enter takeoff mode when leaving ground
        if not self._takeoff_mode and self._agl_altitude_ft > 50:
            self._takeoff_mode = True
            self._max_altitude_after_takeoff_ft = self._agl_altitude_ft
            logger.debug("GPWS: Entered takeoff mode")

        # Update max altitude in takeoff mode
        if self._takeoff_mode:
            if self._agl_altitude_ft > self._max_altitude_after_takeoff_ft:
                self._max_altitude_after_takeoff_ft = self._agl_altitude_ft

            # Exit takeoff mode above 1500ft AGL
            if self._agl_altitude_ft > 1500:
                self._takeoff_mode = False
                logger.debug("GPWS: Exited takeoff mode")

        # Check warnings
        self._check_terrain_warnings()
        self._check_sink_rate_warnings()
        self._check_takeoff_warnings()
        self._check_altitude_callouts()

    def _check_terrain_warnings(self) -> None:
        """Check for terrain proximity warnings."""
        if self._on_ground:
            return

        # Mode 4: Unsafe terrain clearance
        if self._agl_altitude_ft <= self.PULL_UP_FT:
            self._issue_warning(GPWSWarning.PULL_UP_TERRAIN, priority=MessagePriority.CRITICAL)
        elif self._agl_altitude_ft <= self.TOO_LOW_TERRAIN_FT and self._sink_rate_fpm > 500:
            self._issue_warning(GPWSWarning.TOO_LOW_TERRAIN)
        elif self._agl_altitude_ft <= self.TERRAIN_WARNING_FT:
            self._issue_warning(GPWSWarning.TERRAIN)

    def _check_sink_rate_warnings(self) -> None:
        """Check for excessive sink rate warnings."""
        if self._on_ground:
            return

        # Convert to positive for comparison (sink_rate is negative when descending)
        sink_rate = abs(self._sink_rate_fpm)

        # Mode 1: Excessive descent rate
        if sink_rate >= self.SINK_RATE_PULL_UP_FPM:
            # Scale with altitude - more urgent at lower altitudes
            if self._agl_altitude_ft < 2500:
                self._issue_warning(
                    GPWSWarning.PULL_UP_SINK, priority=MessagePriority.CRITICAL
                )
        elif sink_rate >= self.SINK_RATE_WARNING_FPM:
            if self._agl_altitude_ft < 2500:
                self._issue_warning(GPWSWarning.SINK_RATE)

    def _check_takeoff_warnings(self) -> None:
        """Check for altitude loss after takeoff."""
        if not self._takeoff_mode or self._on_ground:
            return

        # Mode 3: Altitude loss after takeoff
        altitude_loss = self._max_altitude_after_takeoff_ft - self._agl_altitude_ft

        if altitude_loss > 50 and self._sink_rate_fpm < -self.DONT_SINK_THRESHOLD_FPM:
            self._issue_warning(GPWSWarning.DONT_SINK)

    def _check_altitude_callouts(self) -> None:
        """Check for altitude callouts on approach."""
        if self._on_ground or self._takeoff_mode:
            return

        # Only call out during descent
        if self._sink_rate_fpm >= 0:
            return

        # Check each callout altitude
        for callout_alt in self.ALTITUDE_CALLOUTS:
            # Check if we just passed through this altitude
            if (
                self._agl_altitude_ft <= callout_alt
                and self._last_altitude_callout != callout_alt
            ):
                # Cooldown check
                if self._sim_time - self._last_altitude_callout_time < self.ALTITUDE_CALLOUT_COOLDOWN:
                    continue

                self._issue_altitude_callout(callout_alt)
                self._last_altitude_callout = callout_alt
                self._last_altitude_callout_time = self._sim_time
                break  # Only one callout at a time

    def _issue_warning(
        self, warning: GPWSWarning, priority: MessagePriority = MessagePriority.HIGH
    ) -> None:
        """Issue a GPWS warning.

        Args:
            warning: Warning type
            priority: Message priority
        """
        # Check cooldown
        if (
            warning == self._last_warning
            and self._sim_time - self._last_warning_time < self.WARNING_COOLDOWN
        ):
            return

        self._last_warning = warning
        self._last_warning_time = self._sim_time

        # Get warning text
        warning_text = self._get_warning_text(warning)

        logger.warning("GPWS: %s at %.0f ft AGL", warning_text, self._agl_altitude_ft)

        # Publish warning message
        if self.context:
            self.context.message_queue.publish(
                Message(
                    sender="gpws_plugin",
                    recipients=["*"],
                    topic=MessageTopic.SYSTEM_ALERT,
                    data={
                        "type": "gpws",
                        "warning": warning.value,
                        "text": warning_text,
                        "altitude_agl_ft": self._agl_altitude_ft,
                        "sink_rate_fpm": self._sink_rate_fpm,
                    },
                    priority=priority,
                )
            )

            # Queue TTS
            self._queue_tts(warning_text, priority)

    def _issue_altitude_callout(self, altitude_ft: int) -> None:
        """Issue an altitude callout.

        Args:
            altitude_ft: Altitude in feet
        """
        callout_text = self._altitude_to_text(altitude_ft)

        logger.debug("GPWS: Altitude callout %s", callout_text)

        if self.context:
            self.context.message_queue.publish(
                Message(
                    sender="gpws_plugin",
                    recipients=["*"],
                    topic=MessageTopic.SYSTEM_ALERT,
                    data={
                        "type": "gpws_callout",
                        "altitude_ft": altitude_ft,
                        "text": callout_text,
                    },
                    priority=MessagePriority.NORMAL,
                )
            )

            # Queue TTS
            self._queue_tts(callout_text, MessagePriority.NORMAL)

    def _get_warning_text(self, warning: GPWSWarning) -> str:
        """Get spoken text for a warning.

        Args:
            warning: Warning type

        Returns:
            Text to speak
        """
        texts = {
            GPWSWarning.SINK_RATE: "SINK RATE",
            GPWSWarning.PULL_UP_SINK: "PULL UP",
            GPWSWarning.TERRAIN: "TERRAIN",
            GPWSWarning.PULL_UP_TERRAIN: "PULL UP",
            GPWSWarning.DONT_SINK: "DON'T SINK",
            GPWSWarning.TOO_LOW_TERRAIN: "TOO LOW, TERRAIN",
            GPWSWarning.TOO_LOW_GEAR: "TOO LOW, GEAR",
            GPWSWarning.TOO_LOW_FLAPS: "TOO LOW, FLAPS",
            GPWSWarning.TERRAIN_AHEAD: "TERRAIN AHEAD",
            GPWSWarning.OBSTACLE_AHEAD: "OBSTACLE AHEAD",
        }
        return texts.get(warning, warning.value.upper())

    def _altitude_to_text(self, altitude_ft: int) -> str:
        """Convert altitude to spoken text.

        Args:
            altitude_ft: Altitude in feet

        Returns:
            Spoken text
        """
        texts = {
            500: "FIVE HUNDRED",
            100: "ONE HUNDRED",
            50: "FIFTY",
            40: "FORTY",
            30: "THIRTY",
            20: "TWENTY",
            10: "TEN",
        }
        return texts.get(altitude_ft, str(altitude_ft))

    def _queue_tts(self, text: str, priority: MessagePriority) -> None:
        """Queue text for TTS playback.

        Args:
            text: Text to speak
            priority: Message priority
        """
        if not self.context:
            return

        # Publish TTS request
        self.context.message_queue.publish(
            Message(
                sender="gpws_plugin",
                recipients=["tts_service"],
                topic=MessageTopic.TTS_REQUEST,
                data={
                    "text": text,
                    "voice": "gpws",  # Use GPWS voice if available
                    "priority": "critical" if priority == MessagePriority.CRITICAL else "high",
                },
                priority=priority,
            )
        )

    def handle_message(self, message: Message) -> None:
        """Handle messages from other plugins.

        Args:
            message: Message from queue.
        """
        if message.topic == MessageTopic.POSITION_UPDATED:
            data = message.data
            self._on_ground = data.get("on_ground", True)
            self._airspeed_kts = data.get("airspeed_kts", 0.0)
            self._gear_down = data.get("gear_down", True)
            self._flaps_position = data.get("flaps", 0.0)
            self._latitude = data.get("latitude", 0.0)
            self._longitude = data.get("longitude", 0.0)

            # Get AGL if provided
            if "agl_altitude_ft" in data:
                self._agl_altitude_ft = data["agl_altitude_ft"]
            elif "altitude_ft" in data and "terrain_elevation_ft" in data:
                self._agl_altitude_ft = data["altitude_ft"] - data["terrain_elevation_ft"]

            # Get sink rate
            if "vertical_speed_fpm" in data:
                self._sink_rate_fpm = data["vertical_speed_fpm"]

        elif message.topic == MessageTopic.TERRAIN_UPDATED:
            data = message.data
            if "elevation" in data:
                terrain_elev_m = data["elevation"]
                terrain_elev_ft = terrain_elev_m * 3.28084
                # Update AGL if we have altitude
                if "altitude_ft" in data:
                    self._agl_altitude_ft = data["altitude_ft"] - terrain_elev_ft

    def shutdown(self) -> None:
        """Shutdown the GPWS plugin."""
        if self.context:
            self.context.message_queue.unsubscribe(
                MessageTopic.POSITION_UPDATED, self.handle_message
            )
            self.context.message_queue.unsubscribe(
                MessageTopic.TERRAIN_UPDATED, self.handle_message
            )

            if self.context.plugin_registry:
                self.context.plugin_registry.unregister("gpws")

        logger.info("GPWS plugin shutdown")

    def on_config_changed(self, config: dict[str, Any]) -> None:
        """Handle configuration changes.

        Args:
            config: New configuration dictionary
        """
        gpws_config = config.get("gpws", {})
        self.enabled = gpws_config.get("enabled", True)
        self.TERRAIN_WARNING_FT = gpws_config.get("terrain_warning_ft", 500)
        self.PULL_UP_FT = gpws_config.get("pull_up_ft", 100)
        self.SINK_RATE_WARNING_FPM = gpws_config.get("sink_rate_warning_fpm", 1500)

        logger.info("GPWS config updated: enabled=%s", self.enabled)

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable GPWS.

        Args:
            enabled: Whether GPWS should be active
        """
        self.enabled = enabled
        logger.info("GPWS %s", "enabled" if enabled else "disabled")

    def test_warning(self, warning_type: str) -> None:
        """Test a GPWS warning (for ground testing).

        Args:
            warning_type: Warning type to test
        """
        try:
            warning = GPWSWarning(warning_type)
            self._issue_warning(warning)
            logger.info("GPWS test: %s", warning_type)
        except ValueError:
            logger.error("Unknown GPWS warning type: %s", warning_type)

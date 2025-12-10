"""Audio approach guidance plugin.

Provides audio tones for runway alignment during approach.
Manual activation via radio menu or voice command.

Features:
- Lateral deviation tones (left/right of centerline)
- Glideslope deviation tones (high/low)
- Tone frequency/rate changes based on deviation magnitude
- Manual activation/deactivation

Typical usage:
    guidance = ApproachGuidancePlugin()
    guidance.initialize(context)
    guidance.activate_guidance("KSFO", "28R")  # Manual activation
"""

import math
from enum import Enum
from typing import Any

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType

logger = get_logger(__name__)


class DeviationType(Enum):
    """Types of deviation from ideal approach path."""

    ON_COURSE = "on_course"
    LEFT = "left"
    RIGHT = "right"
    HIGH = "high"
    LOW = "low"


class ApproachGuidancePlugin(IPlugin):
    """Audio approach guidance plugin.

    Provides audio tones for runway alignment:
    - Lateral: Left/right deviation from extended centerline
    - Vertical: Above/below 3° glideslope

    Tones:
    - Centered: Steady tone
    - Deviation: Pulsing tone, rate increases with deviation
    - Left/Right: Different frequencies (left=lower, right=higher)
    - High/Low: Different frequencies (high=higher, low=lower)
    """

    # Tone parameters
    TONE_LATERAL_CENTER_HZ = 800  # Centered on localizer
    TONE_LATERAL_LEFT_HZ = 600  # Left of course
    TONE_LATERAL_RIGHT_HZ = 1000  # Right of course
    TONE_GLIDESLOPE_CENTER_HZ = 400  # On glideslope
    TONE_GLIDESLOPE_HIGH_HZ = 500  # Above glideslope
    TONE_GLIDESLOPE_LOW_HZ = 300  # Below glideslope

    # Deviation thresholds
    LATERAL_ON_COURSE_M = 10  # Within 10m = on course
    LATERAL_FULL_DEFLECTION_M = 300  # Full-scale deflection
    GLIDESLOPE_ON_COURSE_DEG = 0.5  # Within 0.5° = on glideslope
    GLIDESLOPE_FULL_DEFLECTION_DEG = 2.0  # Full-scale deflection

    # Standard glideslope angle
    GLIDESLOPE_ANGLE_DEG = 3.0

    # Tone timing
    MIN_PULSE_RATE_HZ = 0.5  # Minimum pulse rate (on course)
    MAX_PULSE_RATE_HZ = 4.0  # Maximum pulse rate (full deflection)
    CONTINUOUS_THRESHOLD = 0.1  # Deviation ratio below which tone is continuous

    def __init__(self) -> None:
        """Initialize approach guidance."""
        self.context: PluginContext | None = None
        self.enabled = False  # Must be manually activated

        # Target runway
        self._target_airport: str | None = None
        self._target_runway_id: str | None = None
        self._target_runway: Any = None
        self._target_runway_end: str = ""

        # Current position
        self._latitude = 0.0
        self._longitude = 0.0
        self._altitude_msl_ft = 0.0
        self._heading_deg = 0.0
        self._on_ground = False

        # Deviation state
        self._lateral_deviation_m = 0.0
        self._glideslope_deviation_deg = 0.0
        self._distance_to_threshold_m = 0.0

        # Audio state
        self._last_tone_time = 0.0
        self._tone_phase = 0.0
        self._lateral_tone_active = False
        self._glideslope_tone_active = False

        # Airport database reference
        self._airport_db = None

        # Simulation time
        self._sim_time = 0.0

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return PluginMetadata(
            name="approach_guidance",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.AVIONICS,
            dependencies=[],
            provides=["approach_guidance"],
            optional=True,
            update_priority=30,
            requires_physics=False,
            description="Audio approach guidance with runway alignment tones",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize approach guidance.

        Args:
            context: Plugin context.
        """
        self.context = context

        # Get config
        guidance_config = context.config.get("approach_guidance", {})
        # Note: enabled is False by default - must be manually activated

        # Get airport database
        if context.plugin_registry:
            try:
                self._airport_db = context.plugin_registry.get("airport_database")
            except KeyError:
                logger.warning("Airport database not available")

        # Subscribe to messages
        context.message_queue.subscribe(MessageTopic.POSITION_UPDATED, self.handle_message)

        # Register
        if context.plugin_registry:
            context.plugin_registry.register("approach_guidance", self)

        logger.info("Approach guidance initialized (inactive until manually activated)")

    def update(self, dt: float) -> None:
        """Update approach guidance.

        Args:
            dt: Delta time in seconds.
        """
        if not self.context:
            return

        self._sim_time += dt

        if not self.enabled or not self._target_runway:
            return

        # Don't provide guidance on ground
        if self._on_ground:
            return

        # Update deviation calculations
        self._update_deviations()

        # Generate tones based on deviation
        self._generate_tones(dt)

    def _update_deviations(self) -> None:
        """Update lateral and glideslope deviations."""
        if not self._airport_db or not self._target_runway:
            return

        # Get alignment data from database
        alignment = self._airport_db.get_runway_alignment(
            self._latitude,
            self._longitude,
            self._heading_deg,
            self._target_runway,
        )

        self._lateral_deviation_m = alignment["lateral_deviation_m"]
        self._distance_to_threshold_m = alignment["distance_to_threshold_m"]

        # Calculate glideslope deviation
        threshold_elev_ft = alignment["threshold_elevation_ft"]
        current_height_ft = self._altitude_msl_ft - threshold_elev_ft
        current_height_m = current_height_ft * 0.3048

        # Ideal height at this distance on 3° glideslope
        ideal_height_m = self._distance_to_threshold_m * math.tan(
            math.radians(self.GLIDESLOPE_ANGLE_DEG)
        )

        # Deviation in degrees (positive = above glideslope)
        if self._distance_to_threshold_m > 100:  # Only valid when not too close
            actual_angle = math.degrees(
                math.atan2(current_height_m, self._distance_to_threshold_m)
            )
            self._glideslope_deviation_deg = actual_angle - self.GLIDESLOPE_ANGLE_DEG
        else:
            self._glideslope_deviation_deg = 0.0

    def _generate_tones(self, dt: float) -> None:
        """Generate guidance tones.

        Args:
            dt: Delta time.
        """
        if not self.context:
            return

        # Calculate lateral deviation ratio (0 = on course, 1 = full deflection)
        lateral_ratio = min(
            1.0, abs(self._lateral_deviation_m) / self.LATERAL_FULL_DEFLECTION_M
        )

        # Calculate glideslope deviation ratio
        gs_ratio = min(
            1.0, abs(self._glideslope_deviation_deg) / self.GLIDESLOPE_FULL_DEFLECTION_DEG
        )

        # Determine lateral tone
        if abs(self._lateral_deviation_m) < self.LATERAL_ON_COURSE_M:
            lateral_type = DeviationType.ON_COURSE
        elif self._lateral_deviation_m < 0:
            lateral_type = DeviationType.LEFT
        else:
            lateral_type = DeviationType.RIGHT

        # Determine glideslope tone
        if abs(self._glideslope_deviation_deg) < self.GLIDESLOPE_ON_COURSE_DEG:
            gs_type = DeviationType.ON_COURSE
        elif self._glideslope_deviation_deg > 0:
            gs_type = DeviationType.HIGH
        else:
            gs_type = DeviationType.LOW

        # Update tone phase for pulsing
        pulse_rate = self.MIN_PULSE_RATE_HZ + (
            self.MAX_PULSE_RATE_HZ - self.MIN_PULSE_RATE_HZ
        ) * max(lateral_ratio, gs_ratio)
        self._tone_phase += pulse_rate * dt
        if self._tone_phase >= 1.0:
            self._tone_phase -= 1.0

        # Determine if tone should be on (for pulsing)
        deviation_ratio = max(lateral_ratio, gs_ratio)
        if deviation_ratio < self.CONTINUOUS_THRESHOLD:
            tone_on = True  # Continuous tone when on course
        else:
            tone_on = self._tone_phase < 0.5  # 50% duty cycle pulse

        # Request tone generation
        if tone_on:
            self._request_tone(lateral_type, gs_type, lateral_ratio, gs_ratio)

    def _request_tone(
        self,
        lateral: DeviationType,
        glideslope: DeviationType,
        lateral_ratio: float,
        gs_ratio: float,
    ) -> None:
        """Request audio tone generation.

        Args:
            lateral: Lateral deviation type
            glideslope: Glideslope deviation type
            lateral_ratio: Lateral deviation ratio (0-1)
            gs_ratio: Glideslope deviation ratio (0-1)
        """
        if not self.context:
            return

        # Determine lateral frequency
        if lateral == DeviationType.LEFT:
            lateral_freq = self.TONE_LATERAL_LEFT_HZ
        elif lateral == DeviationType.RIGHT:
            lateral_freq = self.TONE_LATERAL_RIGHT_HZ
        else:
            lateral_freq = self.TONE_LATERAL_CENTER_HZ

        # Determine glideslope frequency
        if glideslope == DeviationType.HIGH:
            gs_freq = self.TONE_GLIDESLOPE_HIGH_HZ
        elif glideslope == DeviationType.LOW:
            gs_freq = self.TONE_GLIDESLOPE_LOW_HZ
        else:
            gs_freq = self.TONE_GLIDESLOPE_CENTER_HZ

        # Publish tone request
        self.context.message_queue.publish(
            Message(
                sender="approach_guidance",
                recipients=["audio_service"],
                topic=MessageTopic.AUDIO_REQUEST,
                data={
                    "type": "approach_tone",
                    "lateral_freq": lateral_freq,
                    "glideslope_freq": gs_freq,
                    "lateral_deviation": lateral.value,
                    "glideslope_deviation": glideslope.value,
                    "lateral_ratio": lateral_ratio,
                    "gs_ratio": gs_ratio,
                    "distance_nm": self._distance_to_threshold_m / 1852,
                },
                priority=MessagePriority.HIGH,
            )
        )

    def activate_guidance(self, airport_icao: str, runway_id: str) -> bool:
        """Activate approach guidance for a specific runway.

        Args:
            airport_icao: Airport ICAO code (e.g., "KSFO")
            runway_id: Runway identifier (e.g., "28R")

        Returns:
            True if activation successful
        """
        if not self._airport_db:
            logger.error("Cannot activate guidance: airport database not available")
            return False

        # Load airport if needed
        self._airport_db.load_airport(airport_icao)

        # Find the runway
        runways = self._airport_db.get_runways(airport_icao)
        target_runway = None

        for runway in runways:
            if runway.le_ident == runway_id:
                target_runway = runway
                self._target_runway_end = runway.le_ident
                break
            elif runway.he_ident == runway_id:
                target_runway = runway
                self._target_runway_end = runway.he_ident
                break

        if not target_runway:
            logger.error("Runway %s not found at %s", runway_id, airport_icao)
            return False

        self._target_airport = airport_icao
        self._target_runway_id = runway_id
        self._target_runway = target_runway
        self.enabled = True

        logger.info(
            "Approach guidance activated for %s runway %s",
            airport_icao,
            runway_id,
        )

        # Announce activation
        if self.context:
            self.context.message_queue.publish(
                Message(
                    sender="approach_guidance",
                    recipients=["tts_service"],
                    topic=MessageTopic.TTS_REQUEST,
                    data={
                        "text": f"Approach guidance active for runway {runway_id}",
                        "priority": "normal",
                    },
                    priority=MessagePriority.NORMAL,
                )
            )

        return True

    def deactivate_guidance(self) -> None:
        """Deactivate approach guidance."""
        self.enabled = False
        self._target_airport = None
        self._target_runway_id = None
        self._target_runway = None

        logger.info("Approach guidance deactivated")

        if self.context:
            self.context.message_queue.publish(
                Message(
                    sender="approach_guidance",
                    recipients=["tts_service"],
                    topic=MessageTopic.TTS_REQUEST,
                    data={
                        "text": "Approach guidance deactivated",
                        "priority": "normal",
                    },
                    priority=MessagePriority.NORMAL,
                )
            )

    def get_nearest_runway_guidance(self, max_distance_nm: float = 10.0) -> bool:
        """Activate guidance for the nearest runway.

        Args:
            max_distance_nm: Maximum search distance

        Returns:
            True if a runway was found and guidance activated
        """
        if not self._airport_db:
            return False

        result = self._airport_db.get_nearest_runway(
            self._latitude, self._longitude, max_distance_nm
        )

        if result:
            runway, end_id, distance = result
            return self.activate_guidance(runway.airport_icao, end_id)

        logger.warning("No runway found within %.1f nm", max_distance_nm)
        return False

    def handle_message(self, message: Message) -> None:
        """Handle messages.

        Args:
            message: Message from queue.
        """
        if message.topic == MessageTopic.POSITION_UPDATED:
            data = message.data
            self._latitude = data.get("latitude", 0.0)
            self._longitude = data.get("longitude", 0.0)
            self._altitude_msl_ft = data.get("altitude_ft", 0.0)
            self._heading_deg = data.get("heading_deg", 0.0)
            self._on_ground = data.get("on_ground", False)

    def shutdown(self) -> None:
        """Shutdown approach guidance."""
        if self.context:
            self.context.message_queue.unsubscribe(
                MessageTopic.POSITION_UPDATED, self.handle_message
            )

            if self.context.plugin_registry:
                self.context.plugin_registry.unregister("approach_guidance")

        logger.info("Approach guidance shutdown")

    def on_config_changed(self, config: dict[str, Any]) -> None:
        """Handle configuration changes.

        Args:
            config: New config.
        """
        pass  # No configurable options currently

    def get_status(self) -> dict[str, Any]:
        """Get current guidance status.

        Returns:
            Dictionary with guidance state and deviations
        """
        return {
            "enabled": self.enabled,
            "target_airport": self._target_airport,
            "target_runway": self._target_runway_id,
            "lateral_deviation_m": self._lateral_deviation_m,
            "glideslope_deviation_deg": self._glideslope_deviation_deg,
            "distance_to_threshold_nm": self._distance_to_threshold_m / 1852,
            "on_course": abs(self._lateral_deviation_m) < self.LATERAL_ON_COURSE_M,
            "on_glideslope": abs(self._glideslope_deviation_deg)
            < self.GLIDESLOPE_ON_COURSE_DEG,
        }

    def get_verbal_guidance(self) -> str:
        """Get verbal guidance summary.

        Returns:
            Spoken guidance text
        """
        if not self.enabled:
            return "Approach guidance not active"

        parts = []

        # Lateral guidance
        if abs(self._lateral_deviation_m) < self.LATERAL_ON_COURSE_M:
            parts.append("on centerline")
        elif self._lateral_deviation_m < 0:
            parts.append(f"left of centerline {abs(self._lateral_deviation_m):.0f} meters")
        else:
            parts.append(f"right of centerline {self._lateral_deviation_m:.0f} meters")

        # Glideslope guidance
        if abs(self._glideslope_deviation_deg) < self.GLIDESLOPE_ON_COURSE_DEG:
            parts.append("on glideslope")
        elif self._glideslope_deviation_deg > 0:
            parts.append("above glideslope")
        else:
            parts.append("below glideslope")

        # Distance
        distance_nm = self._distance_to_threshold_m / 1852
        parts.append(f"{distance_nm:.1f} miles from threshold")

        return ", ".join(parts)

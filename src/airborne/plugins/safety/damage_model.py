"""Aircraft damage model and crash reporting system.

Tracks accumulated damage to aircraft components and generates detailed
crash reports when the aircraft is destroyed.

Typical usage:
    damage_model = DamageModel(aircraft_config)
    damage_model.apply_damage(DamageType.GEAR, severity=0.5)

    if damage_model.is_crashed:
        report = damage_model.generate_crash_report(flight_state)
        report.save_to_file("crash_reports/")
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


class DamageType(Enum):
    """Types of aircraft damage."""

    GEAR = "landing_gear"  # Landing gear damage
    PROPELLER = "propeller"  # Propeller strike/damage
    ENGINE = "engine"  # Engine damage
    AIRFRAME = "airframe"  # Structural damage
    WING = "wing"  # Wing damage
    TAIL = "tail"  # Empennage damage
    FUEL = "fuel_system"  # Fuel leak/fire
    ELECTRICAL = "electrical"  # Electrical system damage


class CrashCause(Enum):
    """Primary causes of crash."""

    HARD_LANDING = "hard_landing"
    TERRAIN_COLLISION = "terrain_collision"
    STALL_SPIN = "stall_spin"
    OVERSPEED = "overspeed"
    CROSSWIND_LOSS_OF_CONTROL = "crosswind_loss_of_control"
    RUNWAY_EXCURSION = "runway_excursion"
    OFF_RUNWAY_LANDING = "off_runway_landing"
    PROHIBITED_SURFACE = "prohibited_surface"
    STRUCTURAL_FAILURE = "structural_failure"
    FUEL_EXHAUSTION = "fuel_exhaustion"
    ENGINE_FAILURE = "engine_failure"


@dataclass
class DamageEvent:
    """Record of a single damage event."""

    timestamp: float  # Simulation time
    damage_type: DamageType
    severity: float  # 0.0 to 1.0
    description: str
    location: tuple[float, float] | None = None  # lat, lon if applicable


@dataclass
class FlightState:
    """Snapshot of flight state at time of crash."""

    altitude_msl_ft: float
    altitude_agl_ft: float
    airspeed_kts: float
    groundspeed_kts: float
    vertical_speed_fpm: float
    heading_deg: float
    pitch_deg: float
    roll_deg: float
    latitude: float
    longitude: float
    on_ground: bool
    flaps_position: float
    throttle_position: float
    fuel_remaining_gal: float
    weight_lbs: float
    wind_speed_kts: float = 0.0
    wind_direction_deg: float = 0.0
    crosswind_component_kts: float = 0.0


@dataclass
class CrashReport:
    """Comprehensive crash report with all relevant data."""

    # Identification
    report_id: str
    timestamp: datetime
    aircraft_type: str
    aircraft_callsign: str

    # Location
    latitude: float
    longitude: float
    airport_icao: str | None
    runway_id: str | None

    # Primary cause
    primary_cause: CrashCause
    cause_description: str

    # Flight state at impact
    flight_state: FlightState

    # Damage history
    damage_events: list[DamageEvent] = field(default_factory=list)

    # Contributing factors
    contributing_factors: list[str] = field(default_factory=list)

    # Recommendations
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary for serialization."""
        return {
            "report_id": self.report_id,
            "timestamp": self.timestamp.isoformat(),
            "aircraft": {
                "type": self.aircraft_type,
                "callsign": self.aircraft_callsign,
            },
            "location": {
                "latitude": self.latitude,
                "longitude": self.longitude,
                "airport_icao": self.airport_icao,
                "runway_id": self.runway_id,
            },
            "cause": {
                "primary": self.primary_cause.value,
                "description": self.cause_description,
            },
            "flight_state": {
                "altitude_msl_ft": self.flight_state.altitude_msl_ft,
                "altitude_agl_ft": self.flight_state.altitude_agl_ft,
                "airspeed_kts": self.flight_state.airspeed_kts,
                "groundspeed_kts": self.flight_state.groundspeed_kts,
                "vertical_speed_fpm": self.flight_state.vertical_speed_fpm,
                "heading_deg": self.flight_state.heading_deg,
                "pitch_deg": self.flight_state.pitch_deg,
                "roll_deg": self.flight_state.roll_deg,
                "on_ground": self.flight_state.on_ground,
                "flaps": self.flight_state.flaps_position,
                "throttle": self.flight_state.throttle_position,
                "fuel_gal": self.flight_state.fuel_remaining_gal,
                "weight_lbs": self.flight_state.weight_lbs,
                "wind_speed_kts": self.flight_state.wind_speed_kts,
                "wind_direction_deg": self.flight_state.wind_direction_deg,
                "crosswind_kts": self.flight_state.crosswind_component_kts,
            },
            "damage_history": [
                {
                    "time": e.timestamp,
                    "type": e.damage_type.value,
                    "severity": e.severity,
                    "description": e.description,
                }
                for e in self.damage_events
            ],
            "contributing_factors": self.contributing_factors,
            "recommendations": self.recommendations,
        }

    def to_markdown(self) -> str:
        """Generate markdown crash report for human reading."""
        lines = [
            f"# Crash Report: {self.report_id}",
            "",
            f"**Date/Time:** {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Aircraft:** {self.aircraft_type} ({self.aircraft_callsign})",
            "",
            "## Location",
            f"- **Coordinates:** {self.latitude:.6f}, {self.longitude:.6f}",
        ]

        if self.airport_icao:
            lines.append(f"- **Airport:** {self.airport_icao}")
        if self.runway_id:
            lines.append(f"- **Runway:** {self.runway_id}")

        lines.extend(
            [
                "",
                "## Primary Cause",
                f"**{self.primary_cause.value.replace('_', ' ').title()}**",
                "",
                self.cause_description,
                "",
                "## Flight State at Impact",
                "",
                "| Parameter | Value |",
                "|-----------|-------|",
                f"| Altitude MSL | {self.flight_state.altitude_msl_ft:.0f} ft |",
                f"| Altitude AGL | {self.flight_state.altitude_agl_ft:.0f} ft |",
                f"| Airspeed | {self.flight_state.airspeed_kts:.0f} kts |",
                f"| Vertical Speed | {self.flight_state.vertical_speed_fpm:.0f} fpm |",
                f"| Heading | {self.flight_state.heading_deg:.0f}° |",
                f"| Pitch | {self.flight_state.pitch_deg:.1f}° |",
                f"| Roll | {self.flight_state.roll_deg:.1f}° |",
                f"| Flaps | {self.flight_state.flaps_position * 100:.0f}% |",
                f"| Throttle | {self.flight_state.throttle_position * 100:.0f}% |",
                f"| Fuel Remaining | {self.flight_state.fuel_remaining_gal:.1f} gal |",
            ]
        )

        if self.flight_state.wind_speed_kts > 0:
            lines.extend(
                [
                    f"| Wind | {self.flight_state.wind_speed_kts:.0f} kts @ {self.flight_state.wind_direction_deg:.0f}° |",
                    f"| Crosswind Component | {self.flight_state.crosswind_component_kts:.0f} kts |",
                ]
            )

        if self.damage_events:
            lines.extend(
                [
                    "",
                    "## Damage History",
                    "",
                ]
            )
            for event in self.damage_events:
                severity_pct = event.severity * 100
                lines.append(
                    f"- **{event.damage_type.value}** ({severity_pct:.0f}%): {event.description}"
                )

        if self.contributing_factors:
            lines.extend(
                [
                    "",
                    "## Contributing Factors",
                    "",
                ]
            )
            for factor in self.contributing_factors:
                lines.append(f"- {factor}")

        if self.recommendations:
            lines.extend(
                [
                    "",
                    "## Recommendations",
                    "",
                ]
            )
            for rec in self.recommendations:
                lines.append(f"- {rec}")

        lines.extend(
            [
                "",
                "---",
                "*This report was automatically generated by the AirBorne flight simulator.*",
            ]
        )

        return "\n".join(lines)

    def save_to_file(self, directory: str | Path) -> Path:
        """Save crash report to markdown file.

        Args:
            directory: Directory to save report in

        Returns:
            Path to saved file
        """
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)

        filename = f"crash_{self.timestamp.strftime('%Y%m%d_%H%M%S')}_{self.report_id[:8]}.md"
        filepath = directory / filename

        with open(filepath, "w") as f:
            f.write(self.to_markdown())

        # Also save JSON for programmatic access
        json_filepath = filepath.with_suffix(".json")
        with open(json_filepath, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

        logger.info("Crash report saved to %s", filepath)
        return filepath


class DamageModel:
    """Tracks aircraft damage and determines crash conditions.

    The damage model accumulates damage to various aircraft systems
    based on flight events (hard landings, terrain contact, etc.)
    and determines when the aircraft has crashed.
    """

    # Damage thresholds
    CRASH_THRESHOLD = 1.0  # Total damage >= 1.0 = crash
    COMPONENT_FAILURE_THRESHOLD = 0.8  # Component fails at 80% damage

    def __init__(self, aircraft_config: dict | None = None) -> None:
        """Initialize damage model.

        Args:
            aircraft_config: Aircraft configuration dictionary
        """
        self.aircraft_config = aircraft_config or {}
        self.aircraft_type = aircraft_config.get("name", "Unknown") if aircraft_config else "Unknown"
        self.callsign = ""

        # Component damage levels (0.0 = pristine, 1.0 = destroyed)
        self.damage: dict[DamageType, float] = {dt: 0.0 for dt in DamageType}

        # Damage event history
        self.events: list[DamageEvent] = []

        # Crash state
        self._crashed = False
        self._crash_cause: CrashCause | None = None
        self._crash_description: str = ""

        # Load limits from config
        limits = aircraft_config.get("landing_limits", {}) if aircraft_config else {}
        self.max_sink_rate_fpm = limits.get("max_sink_rate_fpm", 600)
        self.hard_landing_fpm = limits.get("hard_landing_fpm", 400)
        self.max_crosswind_kts = limits.get("max_crosswind_kts", 15)

        # Load surface compatibility
        surfaces = aircraft_config.get("surface_compatibility", {}) if aircraft_config else {}
        self.allowed_surfaces = surfaces.get("allowed_surfaces", ["asphalt", "concrete"])
        self.restricted_surfaces = surfaces.get("restricted_surfaces", ["grass"])
        self.prohibited_surfaces = surfaces.get("prohibited_surfaces", ["water", "sand"])

        logger.info("DamageModel initialized for %s", self.aircraft_type)

    @property
    def is_crashed(self) -> bool:
        """Check if aircraft has crashed."""
        return self._crashed

    @property
    def total_damage(self) -> float:
        """Get total accumulated damage (0.0 to 1.0+)."""
        return sum(self.damage.values())

    def apply_damage(
        self,
        damage_type: DamageType,
        severity: float,
        description: str,
        sim_time: float = 0.0,
        location: tuple[float, float] | None = None,
    ) -> None:
        """Apply damage to an aircraft component.

        Args:
            damage_type: Type of damage
            severity: Damage severity (0.0 to 1.0, additive)
            description: Description of damage cause
            sim_time: Current simulation time
            location: Optional lat/lon where damage occurred
        """
        # Clamp severity
        severity = max(0.0, min(1.0, severity))

        # Apply damage (additive, capped at 1.0 per component)
        old_damage = self.damage[damage_type]
        self.damage[damage_type] = min(1.0, old_damage + severity)

        # Record event
        event = DamageEvent(
            timestamp=sim_time,
            damage_type=damage_type,
            severity=severity,
            description=description,
            location=location,
        )
        self.events.append(event)

        logger.warning(
            "Damage applied: %s +%.0f%% (total: %.0f%%) - %s",
            damage_type.value,
            severity * 100,
            self.damage[damage_type] * 100,
            description,
        )

    def check_hard_landing(
        self, sink_rate_fpm: float, sim_time: float, location: tuple[float, float] | None = None
    ) -> bool:
        """Check for hard landing damage.

        Args:
            sink_rate_fpm: Vertical speed at touchdown (positive = descending)
            sim_time: Current simulation time
            location: Optional lat/lon

        Returns:
            True if landing caused damage
        """
        if sink_rate_fpm < self.hard_landing_fpm:
            return False

        # Calculate damage based on how much sink rate exceeded limit
        excess = sink_rate_fpm - self.hard_landing_fpm
        max_excess = self.max_sink_rate_fpm - self.hard_landing_fpm

        if sink_rate_fpm >= self.max_sink_rate_fpm:
            # Catastrophic - crash
            self.apply_damage(
                DamageType.GEAR,
                1.0,
                f"Landing gear collapsed - sink rate {sink_rate_fpm:.0f} fpm exceeded limit of {self.max_sink_rate_fpm} fpm",
                sim_time,
                location,
            )
            self.apply_damage(
                DamageType.AIRFRAME,
                0.5,
                "Structural damage from hard impact",
                sim_time,
                location,
            )
            self._trigger_crash(
                CrashCause.HARD_LANDING,
                f"Landing gear collapsed due to excessive sink rate ({sink_rate_fpm:.0f} fpm). "
                f"Maximum survivable sink rate is {self.max_sink_rate_fpm} fpm.",
            )
        else:
            # Graduated damage
            damage_pct = excess / max_excess if max_excess > 0 else 0.5
            self.apply_damage(
                DamageType.GEAR,
                damage_pct * 0.5,  # Up to 50% gear damage for hard landings
                f"Hard landing - sink rate {sink_rate_fpm:.0f} fpm",
                sim_time,
                location,
            )

        return True

    def check_surface_compatibility(
        self,
        surface_type: str,
        sim_time: float,
        location: tuple[float, float] | None = None,
    ) -> bool:
        """Check if landing on this surface causes damage.

        Args:
            surface_type: Surface type (from SurfaceType enum value)
            sim_time: Current simulation time
            location: Optional lat/lon

        Returns:
            True if surface caused damage
        """
        surface_lower = surface_type.lower()

        if surface_lower in [s.lower() for s in self.prohibited_surfaces]:
            # Crash on prohibited surface
            self.apply_damage(
                DamageType.GEAR, 1.0, f"Landing gear failed on {surface_type}", sim_time, location
            )
            self.apply_damage(
                DamageType.PROPELLER,
                0.8,
                f"Propeller struck {surface_type}",
                sim_time,
                location,
            )
            self._trigger_crash(
                CrashCause.PROHIBITED_SURFACE,
                f"Aircraft is not designed to operate on {surface_type}. "
                f"This aircraft is approved for: {', '.join(self.allowed_surfaces)}.",
            )
            return True

        elif surface_lower in [s.lower() for s in self.restricted_surfaces]:
            # Moderate damage on restricted surface
            self.apply_damage(
                DamageType.GEAR,
                0.3,
                f"Landing gear stress on {surface_type}",
                sim_time,
                location,
            )
            # Possible prop damage
            self.apply_damage(
                DamageType.PROPELLER,
                0.2,
                f"Propeller debris damage on {surface_type}",
                sim_time,
                location,
            )
            return True

        return False

    def check_crosswind(
        self,
        crosswind_kts: float,
        sim_time: float,
        location: tuple[float, float] | None = None,
    ) -> bool:
        """Check for crosswind-related damage.

        Args:
            crosswind_kts: Crosswind component in knots
            sim_time: Current simulation time
            location: Optional lat/lon

        Returns:
            True if crosswind caused damage
        """
        if abs(crosswind_kts) <= self.max_crosswind_kts:
            return False

        excess = abs(crosswind_kts) - self.max_crosswind_kts

        if excess > 10:
            # Severe crosswind - loss of control
            self.apply_damage(
                DamageType.GEAR,
                0.8,
                f"Gear side-loaded in {crosswind_kts:.0f}kt crosswind",
                sim_time,
                location,
            )
            self.apply_damage(
                DamageType.WING,
                0.5,
                "Wing tip struck ground during crosswind landing",
                sim_time,
                location,
            )
            self._trigger_crash(
                CrashCause.CROSSWIND_LOSS_OF_CONTROL,
                f"Loss of directional control in {crosswind_kts:.0f}kt crosswind. "
                f"Maximum demonstrated crosswind is {self.max_crosswind_kts}kt.",
            )
        else:
            # Moderate crosswind stress
            damage = excess / 10 * 0.3
            self.apply_damage(
                DamageType.GEAR,
                damage,
                f"Gear stress from {crosswind_kts:.0f}kt crosswind",
                sim_time,
                location,
            )

        return True

    def check_terrain_collision(
        self,
        agl_altitude_m: float,
        vertical_speed_mps: float,
        sim_time: float,
        location: tuple[float, float] | None = None,
    ) -> bool:
        """Check for terrain collision (CFIT).

        Args:
            agl_altitude_m: Altitude above ground level in meters
            vertical_speed_mps: Vertical speed in m/s (negative = descending)
            sim_time: Current simulation time
            location: Optional lat/lon

        Returns:
            True if terrain collision occurred
        """
        if agl_altitude_m > 0:
            return False

        # Calculate impact severity based on vertical speed
        impact_speed_fpm = abs(vertical_speed_mps) * 196.85  # m/s to fpm

        self.apply_damage(DamageType.AIRFRAME, 1.0, "Terrain impact", sim_time, location)
        self.apply_damage(DamageType.GEAR, 1.0, "Gear destroyed on terrain", sim_time, location)
        self.apply_damage(DamageType.PROPELLER, 1.0, "Propeller destroyed", sim_time, location)

        self._trigger_crash(
            CrashCause.TERRAIN_COLLISION,
            f"Controlled flight into terrain (CFIT). Impact vertical speed: {impact_speed_fpm:.0f} fpm. "
            "Maintain awareness of terrain elevation and use GPWS warnings.",
        )

        return True

    def check_off_runway(
        self,
        on_runway: bool,
        on_ground: bool,
        groundspeed_kts: float,
        sim_time: float,
        location: tuple[float, float] | None = None,
    ) -> bool:
        """Check for off-runway operation.

        Args:
            on_runway: Whether aircraft is on a runway
            on_ground: Whether aircraft is on the ground
            groundspeed_kts: Ground speed in knots
            sim_time: Current simulation time
            location: Optional lat/lon

        Returns:
            True if off-runway caused damage
        """
        if not on_ground or on_runway:
            return False

        # Aircraft is on ground but not on runway
        if groundspeed_kts > 30:
            # High speed off-runway - likely runway excursion
            self.apply_damage(
                DamageType.GEAR,
                0.6,
                f"Runway excursion at {groundspeed_kts:.0f}kts",
                sim_time,
                location,
            )
            self.apply_damage(
                DamageType.PROPELLER,
                0.4,
                "Propeller damage from debris",
                sim_time,
                location,
            )

            if groundspeed_kts > 50:
                self._trigger_crash(
                    CrashCause.RUNWAY_EXCURSION,
                    f"Runway excursion at {groundspeed_kts:.0f}kts. "
                    "Maintain directional control and apply appropriate braking.",
                )
            return True

        return False

    def _trigger_crash(self, cause: CrashCause, description: str) -> None:
        """Trigger a crash event.

        Args:
            cause: Primary crash cause
            description: Detailed description
        """
        if self._crashed:
            return  # Already crashed

        self._crashed = True
        self._crash_cause = cause
        self._crash_description = description

        logger.critical("CRASH: %s - %s", cause.value, description)

    def generate_crash_report(
        self,
        flight_state: FlightState,
        airport_icao: str | None = None,
        runway_id: str | None = None,
    ) -> CrashReport:
        """Generate comprehensive crash report.

        Args:
            flight_state: Flight state at time of crash
            airport_icao: Nearby airport ICAO code
            runway_id: Runway identifier if applicable

        Returns:
            CrashReport with all crash data
        """
        import uuid

        report_id = str(uuid.uuid4())

        # Determine contributing factors
        factors = []
        if flight_state.vertical_speed_fpm < -self.hard_landing_fpm:
            factors.append(f"Excessive sink rate ({flight_state.vertical_speed_fpm:.0f} fpm)")
        if abs(flight_state.crosswind_component_kts) > self.max_crosswind_kts:
            factors.append(
                f"Crosswind beyond limits ({flight_state.crosswind_component_kts:.0f}kts)"
            )
        if flight_state.airspeed_kts < 40:
            factors.append("Low airspeed at impact")
        if abs(flight_state.roll_deg) > 10:
            factors.append(f"Excessive bank angle ({flight_state.roll_deg:.0f}°)")

        # Generate recommendations based on cause
        recommendations = self._get_recommendations(self._crash_cause)

        report = CrashReport(
            report_id=report_id,
            timestamp=datetime.now(),
            aircraft_type=self.aircraft_type,
            aircraft_callsign=self.callsign or "N/A",
            latitude=flight_state.latitude,
            longitude=flight_state.longitude,
            airport_icao=airport_icao,
            runway_id=runway_id,
            primary_cause=self._crash_cause or CrashCause.TERRAIN_COLLISION,
            cause_description=self._crash_description,
            flight_state=flight_state,
            damage_events=self.events.copy(),
            contributing_factors=factors,
            recommendations=recommendations,
        )

        return report

    def _get_recommendations(self, cause: CrashCause | None) -> list[str]:
        """Get recommendations based on crash cause."""
        recommendations = {
            CrashCause.HARD_LANDING: [
                "Practice flare timing to reduce sink rate at touchdown",
                "Monitor vertical speed indicator on final approach",
                "Aim for 100-200 fpm sink rate at touchdown",
            ],
            CrashCause.TERRAIN_COLLISION: [
                "Monitor altitude and terrain awareness",
                "Use GPWS warnings and respond immediately",
                "Maintain minimum safe altitudes in mountainous terrain",
            ],
            CrashCause.CROSSWIND_LOSS_OF_CONTROL: [
                "Practice crosswind landing techniques",
                "Know your aircraft's crosswind limits",
                "Consider diverting if crosswind exceeds limits",
            ],
            CrashCause.PROHIBITED_SURFACE: [
                "Verify runway surface type before landing",
                "Know your aircraft's surface limitations",
                "Use appropriate airport selection",
            ],
            CrashCause.RUNWAY_EXCURSION: [
                "Maintain directional control on rollout",
                "Apply brakes smoothly and symmetrically",
                "Consider go-around if approach is unstable",
            ],
        }

        return recommendations.get(cause, ["Review flight procedures and techniques"])

    def reset(self) -> None:
        """Reset damage model to pristine condition."""
        self.damage = {dt: 0.0 for dt in DamageType}
        self.events.clear()
        self._crashed = False
        self._crash_cause = None
        self._crash_description = ""
        logger.info("Damage model reset")

    def get_audio_crash_summary(self) -> str:
        """Generate audio-friendly crash summary for TTS.

        Returns:
            String suitable for text-to-speech
        """
        if not self._crashed:
            return "No crash detected."

        cause_phrases = {
            CrashCause.HARD_LANDING: "hard landing with gear collapse",
            CrashCause.TERRAIN_COLLISION: "controlled flight into terrain",
            CrashCause.CROSSWIND_LOSS_OF_CONTROL: "loss of control in crosswind",
            CrashCause.PROHIBITED_SURFACE: "landing on unsuitable surface",
            CrashCause.RUNWAY_EXCURSION: "runway excursion",
            CrashCause.STALL_SPIN: "stall and spin",
            CrashCause.OVERSPEED: "structural failure from overspeed",
        }

        cause_phrase = cause_phrases.get(
            self._crash_cause, self._crash_cause.value if self._crash_cause else "unknown cause"
        )

        return f"Crash. {cause_phrase.capitalize()}. {self._crash_description}"

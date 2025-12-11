"""Cockpit spatial audio manager.

This module manages 3D positions for cockpit sound sources based on
aircraft-specific configurations.

Typical usage example:
    from airborne.audio.spatial import CockpitSpatialManager

    spatial = CockpitSpatialManager()
    spatial.load_config("config/cockpit_positions.yaml")
    pos = spatial.get_control_position("master_switch")
    engine_sources = spatial.get_engine_sources()
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from airborne.audio.engine.base import Vector3
from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


@dataclass
class EngineSource:
    """Represents an engine sound source position and properties."""

    name: str
    position: Vector3
    volume_scale: float = 1.0


@dataclass
class ReverbConfig:
    """Configuration for cockpit reverb effect."""

    enabled: bool = True
    reverb_type: str = "fmod_reverb"  # "fmod_reverb" or "convolution"

    # FMOD reverb parameters
    decay_time: float = 0.3
    early_delay: float = 0.005
    late_delay: float = 0.015
    hf_reference: float = 5000.0
    hf_decay_ratio: float = 0.6
    diffusion: float = 80.0
    density: float = 100.0
    low_shelf_frequency: float = 250.0
    low_shelf_gain: float = 0.0
    high_cut: float = 8000.0
    early_late_mix: float = 50.0
    wet_level: float = -8.0  # dB
    dry_level: float = 0.0  # dB

    # Convolution reverb parameters
    ir_file: str = ""
    conv_wet_level: float = 0.15
    conv_dry_level: float = 0.85


class CockpitSpatialManager:
    """Manages 3D sound positions for cockpit elements.

    Loads aircraft-specific position configurations and provides
    methods to retrieve 3D positions for various cockpit components.

    Examples:
        >>> spatial = CockpitSpatialManager()
        >>> spatial.load_config("config/cockpit_positions.yaml")
        >>> switch_pos = spatial.get_control_position("master_switch")
        >>> print(switch_pos)  # Vector3(-0.45, 0.0, 0.45)
    """

    def __init__(self) -> None:
        """Initialize the spatial manager."""
        self._config: dict[str, Any] = {}
        self._controls: dict[str, Vector3] = {}
        self._panel_zones: dict[str, Vector3] = {}
        self._engine_sources: list[EngineSource] = []
        self._radio_speaker: Vector3 = Vector3(0.0, 0.15, 0.55)
        self._wind_sources: dict[str, Vector3] = {}
        self._wheel_positions: dict[str, Vector3] = {}
        self._reverb_config: ReverbConfig = ReverbConfig()
        self._reverb_categories: list[str] = ["switches", "buttons", "knobs", "mechanical"]
        self._no_reverb_categories: list[str] = ["radio", "engine", "wind", "warnings"]
        self._loaded = False

    def load_preset(self, aircraft_type: str, presets_dir: str = "config/cockpit_presets") -> bool:
        """Load cockpit positions from aircraft-specific preset.

        Looks for presets in order:
        1. Aircraft-specific: {aircraft_type}.yaml (e.g., cessna_172.yaml)
        2. Default: default.yaml

        Supports inheritance via 'base_preset' field in YAML.

        Args:
            aircraft_type: Aircraft type identifier (e.g., "cessna_172").
            presets_dir: Directory containing preset YAML files.

        Returns:
            True if loaded successfully, False otherwise.
        """
        presets_path = Path(presets_dir)

        # Try aircraft-specific preset first
        aircraft_preset = presets_path / f"{aircraft_type}.yaml"
        if aircraft_preset.exists():
            return self._load_preset_with_inheritance(aircraft_preset, presets_path)

        # Fall back to default preset
        default_preset = presets_path / "default.yaml"
        if default_preset.exists():
            logger.info(f"No preset for {aircraft_type}, using default")
            return self.load_config(str(default_preset))

        logger.warning(f"No cockpit preset found for {aircraft_type}")
        return False

    def _load_preset_with_inheritance(self, preset_path: Path, presets_dir: Path) -> bool:
        """Load preset with base_preset inheritance support.

        Args:
            preset_path: Path to the preset YAML file.
            presets_dir: Directory containing presets (for base lookup).

        Returns:
            True if loaded successfully, False otherwise.
        """
        try:
            with open(preset_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)

            # Check for base preset inheritance
            base_preset_name = config.get("base_preset")
            if base_preset_name:
                base_path = presets_dir / f"{base_preset_name}.yaml"
                if base_path.exists():
                    with open(base_path, encoding="utf-8") as f:
                        base_config = yaml.safe_load(f)
                    # Deep merge: base first, then override with specific
                    self._config = self._deep_merge(base_config, config)
                else:
                    logger.warning(f"Base preset not found: {base_preset_name}")
                    self._config = config
            else:
                self._config = config

            self._parse_config()
            self._loaded = True
            aircraft = config.get("aircraft", preset_path.stem)
            logger.info(f"Loaded cockpit preset: {aircraft} from {preset_path}")
            return True

        except Exception as e:
            logger.error(f"Error loading cockpit preset {preset_path}: {e}")
            return False

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Deep merge two dictionaries, with override taking precedence.

        Args:
            base: Base dictionary.
            override: Override dictionary (values take precedence).

        Returns:
            Merged dictionary.
        """
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def load_config(self, config_path: str) -> bool:
        """Load cockpit positions from YAML configuration.

        Args:
            config_path: Path to YAML configuration file.

        Returns:
            True if loaded successfully, False otherwise.
        """
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"Cockpit positions config not found: {config_path}")
            return False

        try:
            with open(path, encoding="utf-8") as f:
                self._config = yaml.safe_load(f)

            self._parse_config()
            self._loaded = True
            logger.info(f"Loaded cockpit positions from {config_path}")
            return True

        except Exception as e:
            logger.error(f"Error loading cockpit positions: {e}")
            return False

    def _parse_config(self) -> None:
        """Parse the loaded configuration into internal structures."""
        # Parse panel zones
        zones = self._config.get("panel_zones", {})
        for zone_name, zone_data in zones.items():
            if "center" in zone_data:
                self._panel_zones[zone_name] = self._parse_vector3(zone_data["center"])

        # Parse individual controls
        controls = self._config.get("controls", {})
        for control_name, control_data in controls.items():
            if "position" in control_data:
                self._controls[control_name] = self._parse_vector3(control_data["position"])

        # Parse radio speaker position
        if "radio_speaker" in self._config:
            pos = self._config["radio_speaker"].get("position")
            if pos:
                self._radio_speaker = self._parse_vector3(pos)

        # Parse engine sources
        engine = self._config.get("engine", {})
        self._engine_sources = []
        for source_name in ["primary", "vibration", "resonance"]:
            if source_name in engine:
                source_data = engine[source_name]
                self._engine_sources.append(
                    EngineSource(
                        name=source_name,
                        position=self._parse_vector3(source_data.get("position", [0, 0, 0])),
                        volume_scale=source_data.get("volume_scale", 1.0),
                    )
                )

        # Parse wind sources
        wind = self._config.get("wind", {})
        for source_name, source_data in wind.items():
            if "position" in source_data:
                self._wind_sources[source_name] = self._parse_vector3(source_data["position"])

        # Parse wheel positions
        wheels = self._config.get("wheels", {})
        for wheel_name, wheel_data in wheels.items():
            if "position" in wheel_data:
                self._wheel_positions[wheel_name] = self._parse_vector3(wheel_data["position"])

        # Parse reverb configuration
        reverb = self._config.get("reverb", {})
        if reverb.get("enabled", True):
            self._reverb_config = ReverbConfig(
                enabled=reverb.get("enabled", True),
                reverb_type=reverb.get("type", "fmod_reverb"),
            )

            # FMOD params
            fmod_params = reverb.get("fmod_params", {})
            if fmod_params:
                self._reverb_config.decay_time = fmod_params.get("decay_time", 0.3)
                self._reverb_config.early_delay = fmod_params.get("early_delay", 0.005)
                self._reverb_config.late_delay = fmod_params.get("late_delay", 0.015)
                self._reverb_config.hf_reference = fmod_params.get("hf_reference", 5000.0)
                self._reverb_config.hf_decay_ratio = fmod_params.get("hf_decay_ratio", 0.6)
                self._reverb_config.diffusion = fmod_params.get("diffusion", 80.0)
                self._reverb_config.density = fmod_params.get("density", 100.0)
                self._reverb_config.low_shelf_frequency = fmod_params.get(
                    "low_shelf_frequency", 250.0
                )
                self._reverb_config.low_shelf_gain = fmod_params.get("low_shelf_gain", 0.0)
                self._reverb_config.high_cut = fmod_params.get("high_cut", 8000.0)
                self._reverb_config.early_late_mix = fmod_params.get("early_late_mix", 50.0)
                self._reverb_config.wet_level = fmod_params.get("wet_level", -8.0)
                self._reverb_config.dry_level = fmod_params.get("dry_level", 0.0)

            # Convolution params
            conv_params = reverb.get("convolution", {})
            if conv_params:
                self._reverb_config.ir_file = conv_params.get("ir_file", "")
                self._reverb_config.conv_wet_level = conv_params.get("wet_level", 0.15)
                self._reverb_config.conv_dry_level = conv_params.get("dry_level", 0.85)

        # Parse reverb categories
        self._reverb_categories = self._config.get(
            "reverb_categories", ["switches", "buttons", "knobs", "mechanical"]
        )
        self._no_reverb_categories = self._config.get(
            "no_reverb_categories", ["radio", "engine", "wind", "warnings"]
        )

    def _parse_vector3(self, data: list[float] | tuple[float, ...]) -> Vector3:
        """Parse a list/tuple into a Vector3.

        Args:
            data: List or tuple of [x, y, z] coordinates.

        Returns:
            Vector3 with the parsed coordinates.
        """
        if len(data) >= 3:
            return Vector3(float(data[0]), float(data[1]), float(data[2]))
        return Vector3(0.0, 0.0, 0.0)

    @property
    def is_loaded(self) -> bool:
        """Check if configuration has been loaded."""
        return self._loaded

    def get_control_position(self, control_name: str) -> Vector3:
        """Get the 3D position of a named control.

        Args:
            control_name: Name of the control (e.g., "master_switch", "throttle").

        Returns:
            Vector3 position, or center panel position if not found.
        """
        if control_name in self._controls:
            return self._controls[control_name]

        # Fall back to panel zone center if control references a zone
        for control_data in self._config.get("controls", {}).values():
            if control_data.get("zone"):
                zone = control_data["zone"]
                if zone in self._panel_zones:
                    return self._panel_zones[zone]

        # Default to center panel
        return self._panel_zones.get("center_panel", Vector3(0.0, 0.05, 0.55))

    def get_zone_position(self, zone_name: str) -> Vector3:
        """Get the center position of a panel zone.

        Args:
            zone_name: Name of the zone (e.g., "left_panel", "pedestal").

        Returns:
            Vector3 position of zone center.
        """
        return self._panel_zones.get(zone_name, Vector3(0.0, 0.0, 0.5))

    def get_radio_speaker_position(self) -> Vector3:
        """Get the radio speaker position.

        Returns:
            Vector3 position of the radio speaker.
        """
        return self._radio_speaker

    def get_engine_sources(self) -> list[EngineSource]:
        """Get all engine sound sources.

        Returns:
            List of EngineSource objects with positions and volume scales.
        """
        if self._engine_sources:
            return self._engine_sources

        # Default engine sources if not configured
        return [
            EngineSource("primary", Vector3(0.0, -0.1, 2.0), 1.0),
            EngineSource("vibration", Vector3(0.0, -0.5, 0.3), 0.4),
            EngineSource("resonance", Vector3(0.0, 0.0, 0.0), 0.25),
        ]

    def get_wind_sources(self) -> dict[str, Vector3]:
        """Get wind sound source positions.

        Returns:
            Dictionary of wind source names to positions.
        """
        if self._wind_sources:
            return self._wind_sources

        # Defaults
        return {
            "primary": Vector3(0.0, 0.1, 0.6),
            "left_door": Vector3(-0.6, 0.0, -0.1),
        }

    def get_wheel_position(self, wheel_name: str) -> Vector3:
        """Get position of a wheel for ground contact sounds.

        Args:
            wheel_name: Name of wheel ("nose_wheel", "left_main", "right_main").

        Returns:
            Vector3 position of the wheel.
        """
        return self._wheel_positions.get(wheel_name, Vector3(0.0, -1.0, 0.0))

    def get_reverb_config(self) -> ReverbConfig:
        """Get the reverb configuration.

        Returns:
            ReverbConfig with all reverb parameters.
        """
        return self._reverb_config

    def should_apply_reverb(self, category: str) -> bool:
        """Check if reverb should be applied to a sound category.

        Args:
            category: Sound category (e.g., "switches", "radio", "engine").

        Returns:
            True if reverb should be applied to this category.
        """
        if not self._reverb_config.enabled:
            return False

        if category in self._no_reverb_categories:
            return False

        return category in self._reverb_categories

    def get_switch_position_for_type(self, switch_type: str) -> Vector3:
        """Get a position for a generic switch type.

        Maps common switch operations to appropriate panel positions.

        Args:
            switch_type: Type of switch ("switch", "button", "knob", "lever").

        Returns:
            Vector3 position appropriate for the switch type.
        """
        # Map switch types to default zones
        type_zones = {
            "switch": "left_panel",  # Most switches on left
            "button": "center_panel",  # Buttons often center
            "knob": "center_panel",  # Radio knobs center
            "lever": "pedestal",  # Levers on pedestal
            "breaker": "lower_left",  # Circuit breakers lower left
        }

        zone = type_zones.get(switch_type, "center_panel")
        return self.get_zone_position(zone)

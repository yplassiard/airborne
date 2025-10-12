"""Configuration loader for YAML files.

This module provides configuration loading with support for nested access,
defaults, and validation.

Typical usage example:
    from airborne.core.config import ConfigLoader

    config = ConfigLoader.load("config/settings.yaml")
    audio_volume = config.get("audio.master_volume", default=1.0)
"""

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when configuration operations fail."""


class ConfigLoader:
    """Configuration loader for YAML files.

    Provides loading, nested access, and default values for configuration.

    Examples:
        >>> config = ConfigLoader.load("config/settings.yaml")
        >>> volume = config.get("audio.volume", default=1.0)
    """

    def __init__(self, data: dict[str, Any]) -> None:
        """Initialize with configuration data.

        Args:
            data: Configuration dictionary.
        """
        self._data = data

    @classmethod
    def load(cls, path: str | Path) -> "ConfigLoader":
        """Load configuration from a YAML file.

        Args:
            path: Path to YAML configuration file.

        Returns:
            ConfigLoader instance with loaded data.

        Raises:
            ConfigError: If file cannot be loaded.

        Examples:
            >>> config = ConfigLoader.load("config/settings.yaml")
        """
        path = Path(path)

        if not path.exists():
            raise ConfigError(f"Configuration file not found: {path}")

        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if data is None:
                data = {}

            logger.info("Loaded configuration from: %s", path)
            return cls(data)

        except Exception as e:
            raise ConfigError(f"Failed to load configuration: {e}") from e

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value using dot notation.

        Supports nested access like "audio.master_volume".

        Args:
            key: Configuration key (supports dot notation).
            default: Default value if key not found.

        Returns:
            Configuration value or default.

        Examples:
            >>> volume = config.get("audio.volume", default=1.0)
            >>> engine_power = config.get("aircraft.engine.max_power_hp")
        """
        keys = key.split(".")
        value = self._data

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value using dot notation.

        Args:
            key: Configuration key (supports dot notation).
            value: Value to set.

        Examples:
            >>> config.set("audio.volume", 0.8)
        """
        keys = key.split(".")
        data = self._data

        for k in keys[:-1]:
            if k not in data:
                data[k] = {}
            data = data[k]

        data[keys[-1]] = value

    def get_section(self, key: str) -> dict[str, Any]:
        """Get an entire configuration section.

        Args:
            key: Section key (supports dot notation).

        Returns:
            Configuration section as dictionary.

        Raises:
            ConfigError: If section not found or not a dict.

        Examples:
            >>> audio_config = config.get_section("audio")
        """
        value = self.get(key)

        if value is None:
            raise ConfigError(f"Configuration section not found: {key}")

        if not isinstance(value, dict):
            raise ConfigError(f"Configuration key is not a section: {key}")

        return value

    def save(self, path: str | Path) -> None:
        """Save configuration to a YAML file.

        Args:
            path: Path to save configuration.

        Raises:
            ConfigError: If save fails.

        Examples:
            >>> config.save("config/settings.yaml")
        """
        path = Path(path)

        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            with path.open("w", encoding="utf-8") as f:
                yaml.safe_dump(self._data, f, default_flow_style=False, sort_keys=False)

            logger.info("Saved configuration to: %s", path)

        except Exception as e:
            raise ConfigError(f"Failed to save configuration: {e}") from e

    def merge(self, other: "ConfigLoader") -> None:
        """Merge another configuration into this one.

        Args:
            other: ConfigLoader to merge from.

        Note:
            Other config values override existing ones.
        """
        self._data = self._merge_dicts(self._data, other._data)

    def _merge_dicts(self, base: dict, override: dict) -> dict:
        """Recursively merge two dictionaries.

        Args:
            base: Base dictionary.
            override: Override dictionary.

        Returns:
            Merged dictionary.
        """
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_dicts(result[key], value)
            else:
                result[key] = value

        return result

    def to_dict(self) -> dict[str, Any]:
        """Get the configuration as a dictionary.

        Returns:
            Configuration dictionary.
        """
        return self._data.copy()

"""Aircraft builder for loading aircraft from YAML configuration.

The AircraftBuilder loads aircraft configurations from YAML files and
constructs fully configured Aircraft instances with all required plugins.

Typical usage:
    builder = AircraftBuilder(plugin_loader, context)
    aircraft = builder.build("config/aircraft/cessna172.yaml")
"""

from pathlib import Path
from typing import Any

import yaml

from airborne.aircraft.aircraft import Aircraft
from airborne.core.logging_system import get_logger
from airborne.core.plugin import IPlugin, PluginContext
from airborne.core.plugin_loader import PluginLoader

logger = get_logger(__name__)


class AircraftBuilder:
    """Builder for constructing aircraft from YAML configuration.

    The builder handles:
    - Loading YAML configuration files
    - Resolving plugin dependencies
    - Instantiating plugins with their configs
    - Creating the configured Aircraft instance

    Examples:
        >>> loader = PluginLoader(["src/airborne/plugins"])
        >>> context = PluginContext(event_bus, message_queue, config, registry)
        >>> builder = AircraftBuilder(loader, context)
        >>> aircraft = builder.build("config/aircraft/cessna172.yaml")
    """

    def __init__(self, plugin_loader: PluginLoader, context: PluginContext) -> None:
        """Initialize aircraft builder.

        Args:
            plugin_loader: Plugin loader for loading aircraft system plugins.
            context: Plugin context for initializing plugins.
        """
        self.plugin_loader = plugin_loader
        self.context = context

    def build(self, config_path: str | Path) -> Aircraft:
        """Build aircraft from YAML configuration file.

        Args:
            config_path: Path to aircraft YAML configuration file.

        Returns:
            Configured Aircraft instance.

        Raises:
            FileNotFoundError: If config file doesn't exist.
            ValueError: If config is invalid.

        Examples:
            >>> aircraft = builder.build("config/aircraft/cessna172.yaml")
        """
        config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Aircraft config not found: {config_path}")

        logger.info("Loading aircraft from: %s", config_path)

        # Load YAML config
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        if not config or "aircraft" not in config:
            raise ValueError(f"Invalid aircraft config: {config_path}")

        aircraft_config = config["aircraft"]

        # Extract aircraft metadata
        aircraft_name = aircraft_config.get("name", "Unknown Aircraft")
        metadata = {
            "icao_code": aircraft_config.get("icao_code"),
            "manufacturer": aircraft_config.get("manufacturer"),
            "flight_model": aircraft_config.get("flight_model"),
        }

        # Create aircraft instance
        aircraft = Aircraft(aircraft_name, metadata)

        # Load plugins
        plugins_config = aircraft_config.get("plugins", [])
        if not plugins_config:
            logger.warning("No plugins configured for aircraft '%s'", aircraft_name)
            return aircraft

        # Resolve dependencies and sort plugins
        sorted_plugins = self._resolve_dependencies(plugins_config)

        # Load and add each plugin
        for plugin_config in sorted_plugins:
            try:
                instance_id = plugin_config["instance_id"]
                plugin = self._load_plugin(plugin_config)
                aircraft.add_system(instance_id, plugin)
                logger.debug("Added system '%s' to aircraft", instance_id)
            except Exception as e:
                logger.error("Failed to load plugin '%s': %s", plugin_config.get("plugin"), e)
                raise

        logger.info(
            "Aircraft '%s' built successfully with %d systems",
            aircraft_name,
            len(aircraft.get_all_systems()),
        )

        return aircraft

    def _resolve_dependencies(self, plugins_config: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Resolve plugin dependencies and return sorted list.

        Performs topological sort to ensure plugins are loaded in dependency order.

        Args:
            plugins_config: List of plugin configurations.

        Returns:
            Sorted list of plugin configurations (dependencies first).

        Raises:
            ValueError: If circular dependency detected.

        Examples:
            >>> sorted_plugins = builder._resolve_dependencies(plugins)
        """
        # For now, simple approach: load in order specified
        # TODO: Implement proper topological sort based on plugin metadata
        # This would require querying plugin metadata before instantiation

        logger.debug("Resolving dependencies for %d plugins", len(plugins_config))

        # Just return in order for now
        # The plugin system should handle dependency ordering via update_priority
        return plugins_config

    def _load_plugin(self, plugin_config: dict[str, Any]) -> IPlugin:
        """Load and initialize a plugin from configuration.

        Args:
            plugin_config: Plugin configuration dictionary with keys:
                - plugin: Plugin name (e.g., "simple_piston_engine")
                - instance_id: Unique instance identifier
                - config: Plugin-specific configuration

        Returns:
            Initialized plugin instance.

        Raises:
            ValueError: If plugin config is invalid.
            RuntimeError: If plugin loading fails.

        Examples:
            >>> plugin = builder._load_plugin({
            ...     "plugin": "simple_piston_engine",
            ...     "instance_id": "engine",
            ...     "config": {"max_power_hp": 180}
            ... })
        """
        plugin_name = plugin_config.get("plugin")
        if not plugin_name:
            raise ValueError("Plugin config missing 'plugin' field")

        instance_id = plugin_config.get("instance_id")
        if not instance_id:
            raise ValueError("Plugin config missing 'instance_id' field")

        # Get plugin-specific config
        plugin_specific_config = plugin_config.get("config", {})

        # Create plugin context with plugin-specific config merged
        plugin_context = PluginContext(
            event_bus=self.context.event_bus,
            message_queue=self.context.message_queue,
            config={**self.context.config, **plugin_specific_config},
            plugin_registry=self.context.plugin_registry,
        )

        # Load plugin using plugin loader
        try:
            plugin = self.plugin_loader.load_plugin(plugin_name, plugin_context)
            logger.debug("Loaded plugin '%s' as '%s'", plugin_name, instance_id)
            return plugin
        except Exception as e:
            logger.error("Failed to load plugin '%s': %s", plugin_name, e)
            raise RuntimeError(f"Failed to load plugin '{plugin_name}': {e}") from e

    @staticmethod
    def load_config(config_path: str | Path) -> dict[str, Any]:
        """Load aircraft configuration from YAML file (without building).

        Utility method for reading aircraft configs without instantiating plugins.

        Args:
            config_path: Path to YAML configuration file.

        Returns:
            Parsed configuration dictionary.

        Raises:
            FileNotFoundError: If config file doesn't exist.
            ValueError: If YAML is invalid.

        Examples:
            >>> config = AircraftBuilder.load_config("config/aircraft/cessna172.yaml")
            >>> print(config["aircraft"]["name"])
        """
        config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        try:
            with open(config_path, encoding="utf-8") as f:
                config: dict[str, Any] = yaml.safe_load(f)

            if not config:
                raise ValueError("Empty configuration file")

            return config
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {config_path}: {e}") from e

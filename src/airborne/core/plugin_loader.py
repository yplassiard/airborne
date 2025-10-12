"""Plugin loader with dependency resolution.

This module handles dynamic loading of plugins, dependency resolution using
topological sorting, and lifecycle management.

Typical usage example:
    from airborne.core.plugin_loader import PluginLoader

    loader = PluginLoader([Path("src/airborne/plugins")])
    loader.discover_plugins()
    plugin = loader.load_plugin("my_plugin", context)
"""

import importlib.util
import logging
from pathlib import Path

from airborne.core.plugin import (
    IPlugin,
    PluginContext,
    PluginInfo,
    PluginMetadata,
    PluginState,
)

logger = logging.getLogger(__name__)


class PluginLoadError(Exception):
    """Raised when a plugin fails to load."""


class DependencyError(Exception):
    """Raised when plugin dependencies cannot be resolved."""


class PluginLoader:
    """Dynamic plugin loader with dependency resolution.

    The loader discovers plugins in specified directories, resolves their
    dependencies using topological sorting, and manages the plugin lifecycle.

    Examples:
        >>> loader = PluginLoader([Path("plugins")])
        >>> discovered = loader.discover_plugins()
        >>> print(f"Found {len(discovered)} plugins")
        >>> plugin = loader.load_plugin("engine_plugin", context)
        >>> loader.unload_plugin("engine_plugin")
    """

    def __init__(self, plugin_dirs: list[Path]) -> None:
        """Initialize the plugin loader.

        Args:
            plugin_dirs: List of directories to search for plugins.
        """
        self.plugin_dirs = plugin_dirs
        self.loaded_plugins: dict[str, PluginInfo] = {}
        self.plugin_classes: dict[str, type[IPlugin]] = {}
        self._metadata_cache: dict[str, PluginMetadata] = {}

    def discover_plugins(self) -> list[PluginMetadata]:
        """Discover all available plugins in the plugin directories.

        Scans the configured directories for Python files ending in
        '_plugin.py' and attempts to load their metadata.

        Returns:
            List of discovered plugin metadata.

        Examples:
            >>> loader = PluginLoader([Path("plugins")])
            >>> plugins = loader.discover_plugins()
            >>> for meta in plugins:
            ...     print(f"{meta.name} v{meta.version} by {meta.author}")
        """
        discovered = []

        for plugin_dir in self.plugin_dirs:
            if not plugin_dir.exists():
                logger.warning("Plugin directory does not exist: %s", plugin_dir)
                continue

            for plugin_file in plugin_dir.rglob("*_plugin.py"):
                try:
                    metadata = self._load_plugin_metadata(plugin_file)
                    if metadata:
                        discovered.append(metadata)
                        self._metadata_cache[metadata.name] = metadata
                        logger.info("Discovered plugin: %s v%s", metadata.name, metadata.version)
                except Exception as e:
                    logger.error("Failed to discover plugin %s: %s", plugin_file, e)

        return discovered

    def _load_plugin_metadata(self, plugin_file: Path) -> PluginMetadata | None:
        """Load metadata from a plugin file.

        Args:
            plugin_file: Path to the plugin Python file.

        Returns:
            PluginMetadata if successful, None otherwise.
        """
        try:
            # Import the module
            spec = importlib.util.spec_from_file_location(f"plugin_{plugin_file.stem}", plugin_file)
            if spec is None or spec.loader is None:
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find the plugin class (should have a class implementing IPlugin)
            for item_name in dir(module):
                item = getattr(module, item_name)
                if isinstance(item, type) and issubclass(item, IPlugin) and item is not IPlugin:
                    # Instantiate temporarily to get metadata
                    try:
                        instance = item()
                        metadata = instance.get_metadata()
                        self.plugin_classes[metadata.name] = item
                        return metadata
                    except Exception as e:
                        logger.error("Failed to get metadata from %s: %s", item_name, e)
                        return None

            return None

        except Exception as e:
            logger.error("Failed to load plugin file %s: %s", plugin_file, e)
            return None

    def load_plugin(self, plugin_name: str, context: PluginContext) -> IPlugin:
        """Load and initialize a plugin.

        Loads the plugin and all its dependencies in correct order.
        If the plugin is already loaded, returns the existing instance.

        Args:
            plugin_name: Name of the plugin to load.
            context: Context to pass to the plugin.

        Returns:
            Loaded and initialized plugin instance.

        Raises:
            PluginLoadError: If plugin cannot be found or loaded.
            DependencyError: If dependencies cannot be resolved.

        Examples:
            >>> context = PluginContext(event_bus, msg_queue, config, registry)
            >>> plugin = loader.load_plugin("cfm56_engine", context)
            >>> print(f"Loaded: {plugin.get_metadata().name}")
        """
        # Return if already loaded
        if plugin_name in self.loaded_plugins:
            return self.loaded_plugins[plugin_name].plugin

        # Check if plugin is known
        if plugin_name not in self.plugin_classes:
            raise PluginLoadError(f"Plugin not found: {plugin_name}")

        # Get metadata
        plugin_class = self.plugin_classes[plugin_name]
        temp_instance = plugin_class()
        metadata = temp_instance.get_metadata()

        # Load dependencies first
        for dep_name in metadata.dependencies:
            if dep_name not in self.loaded_plugins:
                logger.info("Loading dependency: %s for %s", dep_name, plugin_name)
                try:
                    self.load_plugin(dep_name, context)
                except Exception as e:
                    raise DependencyError(
                        f"Failed to load dependency {dep_name} for {plugin_name}: {e}"
                    ) from e

        # Create and initialize plugin
        try:
            plugin = plugin_class()
            plugin_info = PluginInfo(plugin=plugin, metadata=metadata, state=PluginState.LOADING)

            logger.info("Initializing plugin: %s", plugin_name)
            plugin.initialize(context)

            plugin_info.state = PluginState.LOADED
            self.loaded_plugins[plugin_name] = plugin_info

            logger.info("Successfully loaded plugin: %s", plugin_name)
            return plugin

        except Exception as e:
            error_msg = f"Failed to initialize plugin {plugin_name}: {e}"
            logger.error(error_msg)
            if plugin_name in self.loaded_plugins:
                self.loaded_plugins[plugin_name].state = PluginState.ERROR
                self.loaded_plugins[plugin_name].error = e
            raise PluginLoadError(error_msg) from e

    def unload_plugin(self, plugin_name: str) -> None:
        """Unload a plugin.

        Shuts down and removes the plugin from the loaded plugins.
        Checks for dependent plugins and warns if they exist.

        Args:
            plugin_name: Name of plugin to unload.

        Raises:
            PluginLoadError: If plugin is not loaded.

        Examples:
            >>> loader.unload_plugin("cfm56_engine")
        """
        if plugin_name not in self.loaded_plugins:
            raise PluginLoadError(f"Plugin not loaded: {plugin_name}")

        plugin_info = self.loaded_plugins[plugin_name]

        # Check for plugins that depend on this one
        dependents = self._find_dependents(plugin_name)
        if dependents:
            logger.warning(
                "Unloading %s which is required by: %s", plugin_name, ", ".join(dependents)
            )

        # Shutdown plugin
        try:
            plugin_info.state = PluginState.UNLOADING
            plugin_info.plugin.shutdown()
            plugin_info.state = PluginState.UNLOADED_AFTER_RUN
        except Exception as e:
            logger.error("Error shutting down plugin %s: %s", plugin_name, e)
            plugin_info.state = PluginState.ERROR
            plugin_info.error = e

        # Remove from loaded plugins
        del self.loaded_plugins[plugin_name]
        logger.info("Unloaded plugin: %s", plugin_name)

    def _find_dependents(self, plugin_name: str) -> list[str]:
        """Find plugins that depend on the given plugin.

        Args:
            plugin_name: Name of plugin to check.

        Returns:
            List of plugin names that depend on this plugin.
        """
        dependents = []
        for name, info in self.loaded_plugins.items():
            if plugin_name in info.metadata.dependencies:
                dependents.append(name)
        return dependents

    def resolve_dependencies(self, plugin_names: list[str]) -> list[str]:
        """Resolve plugin dependencies using topological sort.

        Returns plugins in dependency order (dependencies first).

        Args:
            plugin_names: List of plugin names to resolve.

        Returns:
            List of plugin names in load order.

        Raises:
            DependencyError: If circular dependencies detected.

        Examples:
            >>> plugins = ["engine", "fuel", "electrical"]
            >>> ordered = loader.resolve_dependencies(plugins)
            >>> print(ordered)  # ["electrical", "fuel", "engine"]
        """
        # Build dependency graph
        graph: dict[str, list[str]] = {}
        in_degree: dict[str, int] = {}

        # Initialize graph
        for name in plugin_names:
            if name not in self._metadata_cache:
                raise DependencyError(f"Plugin metadata not found: {name}")

            metadata = self._metadata_cache[name]
            graph[name] = list(metadata.dependencies)
            in_degree[name] = 0

        # Calculate in-degrees
        for name in plugin_names:
            for dep in graph[name]:
                if dep not in in_degree:
                    in_degree[dep] = 0
                in_degree[dep] += 1

        # Topological sort (Kahn's algorithm)
        queue = [name for name in plugin_names if in_degree[name] == 0]
        result = []

        while queue:
            current = queue.pop(0)
            result.append(current)

            for dep in graph.get(current, []):
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    queue.append(dep)

        # Check for circular dependencies
        if len(result) != len(plugin_names):
            raise DependencyError("Circular dependency detected in plugins")

        # Reverse to get dependencies-first order
        return list(reversed(result))

    def get_plugin(self, plugin_name: str) -> IPlugin | None:
        """Get a loaded plugin by name.

        Args:
            plugin_name: Name of plugin to retrieve.

        Returns:
            Plugin instance if loaded, None otherwise.
        """
        if plugin_name in self.loaded_plugins:
            return self.loaded_plugins[plugin_name].plugin
        return None

    def get_plugin_info(self, plugin_name: str) -> PluginInfo | None:
        """Get plugin info including state and errors.

        Args:
            plugin_name: Name of plugin.

        Returns:
            PluginInfo if loaded, None otherwise.
        """
        return self.loaded_plugins.get(plugin_name)

    def list_loaded_plugins(self) -> list[str]:
        """Get list of all loaded plugin names.

        Returns:
            List of loaded plugin names.
        """
        return list(self.loaded_plugins.keys())

    def reload_plugin(self, plugin_name: str, context: PluginContext) -> IPlugin:
        """Reload a plugin (unload then load).

        Args:
            plugin_name: Name of plugin to reload.
            context: Context to pass on reload.

        Returns:
            Reloaded plugin instance.

        Raises:
            PluginLoadError: If reload fails.
        """
        self.unload_plugin(plugin_name)
        return self.load_plugin(plugin_name, context)

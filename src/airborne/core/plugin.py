"""Plugin system for modular, extensible architecture.

This module provides the base plugin interface and metadata system that allows
dynamic loading of aircraft systems, avionics, and other components.

Typical usage example:
    from airborne.core.plugin import IPlugin, PluginMetadata, PluginType

    class MyPlugin(IPlugin):
        def get_metadata(self) -> PluginMetadata:
            return PluginMetadata(
                name="my_plugin",
                version="1.0.0",
                author="Author Name",
                plugin_type=PluginType.AIRCRAFT_SYSTEM,
                dependencies=[],
                provides=["my_service"]
            )

        def initialize(self, context: PluginContext) -> None:
            # Setup code here
            pass
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PluginType(Enum):
    """Types of plugins in the system.

    Plugins are categorized by their primary function to help with
    organization and loading order.
    """

    CORE = "core"  # Physics, audio, rendering, input
    AIRCRAFT_SYSTEM = "aircraft"  # Engine, electrical, hydraulics, fuel
    WORLD = "world"  # Terrain, weather, traffic, airports
    CABIN = "cabin"  # Passengers, boarding, services
    AVIONICS = "avionics"  # FMC, autopilot, TCAS, navigation
    NETWORK = "network"  # Multiplayer, live ATC


@dataclass
class PluginMetadata:
    """Metadata describing a plugin.

    This information is used for plugin discovery, dependency resolution,
    and future plugin store/auto-update functionality.

    Attributes:
        name: Unique plugin identifier (e.g., "cfm56_engine").
        version: Semantic version string (e.g., "1.0.0").
        author: Plugin author name or organization.
        plugin_type: Category of plugin.
        dependencies: List of plugin names this plugin requires.
        provides: List of services/capabilities this plugin provides.
        optional: Whether aircraft can function without this plugin.
        update_priority: Lower values update earlier in the frame (0-1000).
        requires_physics: Whether this plugin needs physics updates.
        requires_network: Whether this plugin needs network connectivity.
        config_schema: Optional JSON schema for configuration validation.
        url: Optional URL for plugin homepage/repository.
        description: Optional human-readable description.
    """

    name: str
    version: str
    author: str
    plugin_type: PluginType
    dependencies: list[str] = field(default_factory=list)
    provides: list[str] = field(default_factory=list)
    optional: bool = False
    update_priority: int = 100
    requires_physics: bool = True
    requires_network: bool = False
    config_schema: dict[str, Any] | None = None
    url: str | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        """Validate metadata after initialization."""
        if not self.name:
            raise ValueError("Plugin name cannot be empty")
        if not self.version:
            raise ValueError("Plugin version cannot be empty")
        if not self.author:
            raise ValueError("Plugin author cannot be empty")
        if self.update_priority < 0 or self.update_priority > 1000:
            raise ValueError("Update priority must be between 0 and 1000")


@dataclass
class PluginContext:
    """Context provided to plugins during initialization.

    This gives plugins access to core systems and other plugins without
    tight coupling.

    Attributes:
        event_bus: Global event bus for synchronous events.
        message_queue: Message queue for async plugin communication.
        config: Plugin-specific configuration dictionary.
        plugin_registry: Registry to access other loaded plugins.
    """

    event_bus: Any  # EventBus type (avoid circular import)
    message_queue: Any  # MessageQueue type
    config: dict[str, Any]
    plugin_registry: Any  # PluginRegistry type


class IPlugin(ABC):
    """Base interface for all plugins.

    All plugins must implement this interface. Plugins are the fundamental
    building blocks of the system - everything from engines to avionics
    to audio systems is a plugin.

    Examples:
        >>> class SimpleEnginePlugin(IPlugin):
        ...     def get_metadata(self) -> PluginMetadata:
        ...         return PluginMetadata(
        ...             name="simple_engine",
        ...             version="1.0.0",
        ...             author="AirBorne Team",
        ...             plugin_type=PluginType.AIRCRAFT_SYSTEM,
        ...             provides=["engine"]
        ...         )
        ...
        ...     def initialize(self, context: PluginContext) -> None:
        ...         self.context = context
        ...         print("Engine initialized")
        ...
        ...     def update(self, dt: float) -> None:
        ...         # Update engine state
        ...         pass
        ...
        ...     def shutdown(self) -> None:
        ...         print("Engine shutdown")
        ...
        ...     def handle_message(self, message: Any) -> None:
        ...         # Handle incoming messages
        ...         pass
    """

    @abstractmethod
    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata.

        This method must be implemented by all plugins. It should return
        a PluginMetadata instance describing the plugin.

        Returns:
            PluginMetadata describing this plugin.

        Note:
            This method should be fast and not perform initialization.
        """

    @abstractmethod
    def initialize(self, context: PluginContext) -> None:
        """Initialize the plugin.

        Called once when the plugin is loaded. Plugins should perform all
        setup here, including subscribing to events/messages.

        Args:
            context: Context providing access to core systems.

        Raises:
            RuntimeError: If initialization fails.

        Note:
            Dependencies are guaranteed to be loaded before this is called.
        """

    @abstractmethod
    def update(self, dt: float) -> None:
        """Update plugin state.

        Called every frame if the plugin needs updates. Perform time-based
        state updates here.

        Args:
            dt: Delta time in seconds since last update.

        Note:
            This is called in priority order based on update_priority.
            Keep this method fast - long operations should be async.
        """

    @abstractmethod
    def shutdown(self) -> None:
        """Shutdown the plugin.

        Called when the plugin is being unloaded. Clean up resources,
        unsubscribe from events, and save state here.

        Note:
            This may be called during error conditions, so handle gracefully.
        """

    @abstractmethod
    def handle_message(self, message: Any) -> None:
        """Handle a message from another plugin.

        Messages are delivered from the message queue to plugins that
        have subscribed to the message topic.

        Args:
            message: Message from the queue.

        Note:
            This is called during message queue processing, so keep it fast.
        """

    def on_config_changed(self, config: dict[str, Any]) -> None:
        """Handle configuration changes.

        Called when the plugin's configuration is updated at runtime.
        Override this if your plugin supports hot-reloading config.

        Args:
            config: New configuration dictionary.

        Note:
            Default implementation does nothing (config changes ignored).
        """

    def on_error(self, error: Exception) -> None:
        """Handle an error that occurred in the plugin.

        Called when an exception is caught during plugin execution.
        Override this to provide custom error handling.

        Args:
            error: Exception that was caught.

        Note:
            Default implementation logs the error and continues.
        """
        import logging

        logging.error(f"Error in plugin {self.get_metadata().name}: {error}")


class PluginState(Enum):
    """Plugin lifecycle states."""

    UNLOADED = "unloaded"  # Not yet loaded
    LOADING = "loading"  # Currently being loaded
    LOADED = "loaded"  # Loaded and initialized successfully
    RUNNING = "running"  # Active and updating
    ERROR = "error"  # Failed to load or runtime error
    UNLOADING = "unloading"  # Being shut down
    UNLOADED_AFTER_RUN = "unloaded_after_run"  # Cleanly shut down


@dataclass
class PluginInfo:
    """Information about a loaded plugin instance.

    Tracks plugin state and provides access to the plugin instance.

    Attributes:
        plugin: The plugin instance.
        metadata: Plugin metadata.
        state: Current lifecycle state.
        error: Last error that occurred (if any).
    """

    plugin: IPlugin
    metadata: PluginMetadata
    state: PluginState = PluginState.LOADED
    error: Exception | None = None

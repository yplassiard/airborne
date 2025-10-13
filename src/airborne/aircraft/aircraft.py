"""Aircraft class for composing and managing aircraft systems.

The Aircraft class provides a container for all aircraft systems (plugins)
and coordinates their updates. Each aircraft is composed of multiple plugins
that represent different systems like engine, fuel, electrical, etc.

Typical usage:
    aircraft = Aircraft("Cessna 172")
    aircraft.add_system("engine", engine_plugin)
    aircraft.add_system("fuel", fuel_plugin)
    aircraft.update(0.016)  # Update all systems
"""

from typing import Any

from airborne.core.logging_system import get_logger
from airborne.core.plugin import IPlugin

logger = get_logger(__name__)


class Aircraft:
    """Aircraft composed of multiple system plugins.

    An aircraft is a collection of plugins representing various aircraft
    systems. The aircraft manages the lifecycle and update of all systems.

    Examples:
        >>> aircraft = Aircraft("Cessna 172", {"type": "C172"})
        >>> aircraft.add_system("engine", SimplePistonEngine())
        >>> aircraft.add_system("fuel", SimpleFuelSystem())
        >>> aircraft.update(0.016)
        >>> engine = aircraft.get_system("engine")
    """

    def __init__(self, name: str, metadata: dict[str, Any] | None = None) -> None:
        """Initialize aircraft.

        Args:
            name: Aircraft name (e.g., "Cessna 172 Skyhawk").
            metadata: Optional metadata (icao_code, manufacturer, etc.).
        """
        self.name = name
        self.metadata = metadata or {}
        self._systems: dict[str, IPlugin] = {}

        logger.info("Created aircraft: %s", name)

    def add_system(self, instance_id: str, plugin: IPlugin) -> None:
        """Add a system plugin to the aircraft.

        Args:
            instance_id: Unique identifier for this system instance.
            plugin: Plugin instance to add.

        Raises:
            ValueError: If instance_id already exists.

        Examples:
            >>> aircraft.add_system("engine", SimplePistonEngine())
            >>> aircraft.add_system("left_fuel_tank", FuelTank())
        """
        if instance_id in self._systems:
            raise ValueError(f"System with instance_id '{instance_id}' already exists")

        self._systems[instance_id] = plugin
        logger.debug("Added system '%s' to aircraft '%s'", instance_id, self.name)

    def remove_system(self, instance_id: str) -> None:
        """Remove a system plugin from the aircraft.

        Args:
            instance_id: System identifier to remove.

        Raises:
            KeyError: If instance_id doesn't exist.

        Examples:
            >>> aircraft.remove_system("engine")
        """
        if instance_id not in self._systems:
            raise KeyError(f"System with instance_id '{instance_id}' not found")

        plugin = self._systems[instance_id]
        plugin.shutdown()
        del self._systems[instance_id]

        logger.debug("Removed system '%s' from aircraft '%s'", instance_id, self.name)

    def get_system(self, instance_id: str) -> IPlugin:
        """Get a system plugin by instance ID.

        Args:
            instance_id: System identifier.

        Returns:
            The plugin instance.

        Raises:
            KeyError: If instance_id doesn't exist.

        Examples:
            >>> engine = aircraft.get_system("engine")
            >>> rpm = engine.rpm
        """
        if instance_id not in self._systems:
            raise KeyError(f"System with instance_id '{instance_id}' not found")

        return self._systems[instance_id]

    def has_system(self, instance_id: str) -> bool:
        """Check if aircraft has a system with given ID.

        Args:
            instance_id: System identifier to check.

        Returns:
            True if system exists.

        Examples:
            >>> if aircraft.has_system("engine"):
            ...     engine = aircraft.get_system("engine")
        """
        return instance_id in self._systems

    def get_all_systems(self) -> dict[str, IPlugin]:
        """Get all systems in the aircraft.

        Returns:
            Dictionary mapping instance_id to plugin.

        Examples:
            >>> for system_id, plugin in aircraft.get_all_systems().items():
            ...     print(f"{system_id}: {plugin.get_metadata().name}")
        """
        return self._systems.copy()

    def update(self, dt: float) -> None:
        """Update all aircraft systems.

        Systems are updated in the order they were added. For proper
        dependency ordering, add systems in the correct sequence or use
        the AircraftBuilder which handles dependency resolution.

        Args:
            dt: Delta time in seconds since last update.

        Examples:
            >>> aircraft.update(0.016)  # 60 FPS
        """
        for instance_id, plugin in self._systems.items():
            try:
                plugin.update(dt)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error(
                    "Error updating system '%s' in aircraft '%s': %s",
                    instance_id,
                    self.name,
                    e,
                )
                # Notify plugin of error
                try:
                    plugin.on_error(e)
                except Exception:  # pylint: disable=broad-exception-caught
                    pass  # Plugin error handler failed, continue

    def shutdown(self) -> None:
        """Shutdown all aircraft systems.

        Calls shutdown() on all plugins in reverse order (LIFO).

        Examples:
            >>> aircraft.shutdown()
        """
        # Shutdown in reverse order
        for instance_id in reversed(list(self._systems.keys())):
            plugin = self._systems[instance_id]
            try:
                plugin.shutdown()
                logger.debug("Shutdown system '%s'", instance_id)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Error shutting down system '%s': %s", instance_id, e)

        self._systems.clear()
        logger.info("Aircraft '%s' shutdown complete", self.name)

    def __repr__(self) -> str:
        """String representation of aircraft.

        Returns:
            Aircraft description.
        """
        system_count = len(self._systems)
        return f"Aircraft(name='{self.name}', systems={system_count})"

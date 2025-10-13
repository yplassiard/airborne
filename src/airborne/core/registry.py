"""Component registry for pluggable implementations.

This module provides a registry pattern for managing multiple implementations
of the same interface, useful for swappable strategies and plugin factories.

Typical usage example:
    from airborne.core.registry import ComponentRegistry

    registry = ComponentRegistry()
    registry.register("audio_cue", BeepingProximityCue)
    cue = registry.create("audio_cue", config)
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class RegistryError(Exception):
    """Raised when registry operations fail."""


class ComponentRegistry:
    """Registry for pluggable component implementations.

    Provides a factory pattern for creating component instances based on
    registered types. Useful for swappable strategies and implementations.

    Examples:
        >>> registry = ComponentRegistry()
        >>> registry.register("engine_model", SimplePistonEngine)
        >>> engine = registry.create("engine_model", {"max_power_hp": 180})
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._components: dict[str, type | Any] = {}

    def register(self, name: str, implementation: type | Any) -> None:
        """Register an implementation for a component type.

        Args:
            name: Component type name (e.g., "audio_cue").
            implementation: Class or instance to register.

        Raises:
            RegistryError: If name is already registered.

        Examples:
            >>> registry.register("proximity_cue", BeepingProximityCue)
            >>> registry.register("flight_model", flight_model_instance)
        """
        if name in self._components:
            raise RegistryError(f"Component already registered: {name}")

        self._components[name] = implementation

        # Get name for logging (handle both classes and instances)
        if isinstance(implementation, type):
            impl_name = implementation.__name__
        else:
            impl_name = type(implementation).__name__

        logger.info("Registered component: %s -> %s", name, impl_name)

    def unregister(self, name: str) -> None:
        """Unregister a component type.

        Args:
            name: Component type name to remove.

        Raises:
            RegistryError: If name is not registered.
        """
        if name not in self._components:
            raise RegistryError(f"Component not registered: {name}")

        del self._components[name]
        logger.info("Unregistered component: %s", name)

    def create(self, name: str, config: dict[str, Any]) -> Any:
        """Create an instance of a registered component.

        Args:
            name: Component type name.
            config: Configuration dictionary passed to constructor.

        Returns:
            Instance of the registered component.

        Raises:
            RegistryError: If name is not registered or creation fails.

        Examples:
            >>> cue = registry.create("proximity_cue", {"warning_distance": 5.0})
        """
        if name not in self._components:
            raise RegistryError(f"Component not registered: {name}")

        try:
            implementation = self._components[name]
            return implementation(config)
        except Exception as e:
            raise RegistryError(f"Failed to create component {name}: {e}") from e

    def get(self, name: str) -> Any:
        """Get a registered component (class or instance).

        Args:
            name: Component type name.

        Returns:
            The registered component (class or instance).

        Raises:
            RegistryError: If name is not registered.

        Examples:
            >>> flight_model = registry.get("flight_model")
        """
        if name not in self._components:
            raise RegistryError(f"Component not registered: {name}")

        return self._components[name]

    def is_registered(self, name: str) -> bool:
        """Check if a component type is registered.

        Args:
            name: Component type name.

        Returns:
            True if registered, False otherwise.
        """
        return name in self._components

    def list_components(self) -> list[str]:
        """Get list of all registered component names.

        Returns:
            List of registered component type names.
        """
        return list(self._components.keys())

    def clear(self) -> None:
        """Remove all registered components."""
        self._components.clear()

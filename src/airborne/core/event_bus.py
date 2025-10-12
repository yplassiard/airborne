"""Event bus system for synchronous event dispatch.

This module provides a priority-based event bus for immediate, synchronous
event handling across the application. Events are dispatched to all subscribers
in priority order.

Typical usage example:
    from airborne.core.event_bus import EventBus, Event, EventPriority

    class MyEvent(Event):
        data: str

    bus = EventBus()
    bus.subscribe(MyEvent, handler_func, EventPriority.HIGH)
    bus.publish(MyEvent(data="test"))
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class EventPriority(Enum):
    """Priority levels for event handlers.

    Handlers are executed in order from CRITICAL to LOW.
    """

    CRITICAL = auto()  # Highest priority (executed first)
    HIGH = auto()
    NORMAL = auto()
    LOW = auto()  # Lowest priority (executed last)


@dataclass
class Event:
    """Base class for all events.

    All events must inherit from this class. Events are immutable data
    containers that carry information between components.

    Attributes:
        timestamp: Unix timestamp when the event was created.
    """

    timestamp: float = field(default_factory=time.time)


class EventBus:
    """Central event bus for synchronous event dispatch.

    The event bus allows components to communicate through events without
    tight coupling. Handlers are called synchronously in priority order.

    Examples:
        >>> bus = EventBus()
        >>> def handler(event: MyEvent) -> None:
        ...     print(f"Received: {event.data}")
        >>> bus.subscribe(MyEvent, handler)
        >>> bus.publish(MyEvent(data="hello"))
        Received: hello
    """

    def __init__(self) -> None:
        """Initialize an empty event bus."""
        self._handlers: dict[type[Event], list[tuple[Callable[[Any], None], EventPriority]]] = {}

    def subscribe(
        self,
        event_type: type[Event],
        handler: Callable[[Any], None],
        priority: EventPriority = EventPriority.NORMAL,
    ) -> None:
        """Subscribe a handler to an event type.

        The handler will be called whenever an event of the specified type
        is published. Handlers are called in priority order (CRITICAL first,
        LOW last).

        Args:
            event_type: The class of event to subscribe to.
            handler: Callable that accepts the event as its only parameter.
            priority: Priority level for this handler. Defaults to NORMAL.

        Examples:
            >>> def on_collision(event: CollisionEvent) -> None:
            ...     print("Collision detected!")
            >>> bus.subscribe(CollisionEvent, on_collision, EventPriority.HIGH)
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []

        self._handlers[event_type].append((handler, priority))

        # Sort by priority (CRITICAL=1, HIGH=2, NORMAL=3, LOW=4)
        self._handlers[event_type].sort(key=lambda x: x[1].value)

    def unsubscribe(self, event_type: type[Event], handler: Callable[[Any], None]) -> None:
        """Unsubscribe a handler from an event type.

        Removes the handler from the list of subscribers. If the handler
        is not subscribed, this is a no-op.

        Args:
            event_type: The event type to unsubscribe from.
            handler: The handler function to remove.

        Examples:
            >>> bus.unsubscribe(CollisionEvent, on_collision)
        """
        if event_type in self._handlers:
            self._handlers[event_type] = [
                (h, p) for h, p in self._handlers[event_type] if h != handler
            ]

            # Clean up empty handler lists
            if not self._handlers[event_type]:
                del self._handlers[event_type]

    def publish(self, event: Event) -> None:
        """Publish an event to all subscribers.

        Calls all registered handlers for this event type synchronously
        in priority order. If a handler raises an exception, it is
        propagated to the caller.

        Args:
            event: The event to publish.

        Examples:
            >>> bus.publish(CollisionEvent(position=Vector3(0, 0, 0)))

        Note:
            Handlers are called synchronously. Long-running handlers will
            block the caller.
        """
        event_type = type(event)

        if event_type in self._handlers:
            for handler, _ in self._handlers[event_type]:
                handler(event)

    def clear(self) -> None:
        """Remove all event handlers.

        This is primarily useful for testing or resetting the event bus.
        """
        self._handlers.clear()

    def get_subscriber_count(self, event_type: type[Event]) -> int:
        """Get the number of subscribers for an event type.

        Args:
            event_type: The event type to query.

        Returns:
            Number of handlers subscribed to this event type.
        """
        return len(self._handlers.get(event_type, []))

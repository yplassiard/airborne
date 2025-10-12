"""Message queue system for asynchronous inter-plugin communication.

This module provides a priority-based message queue for plugins to communicate
without tight coupling. Messages are processed asynchronously in batches.

Typical usage example:
    from airborne.core.messaging import MessageQueue, Message, MessagePriority

    queue = MessageQueue()
    queue.subscribe("engine.state", handler_func)
    queue.publish(Message(
        sender="engine_plugin",
        recipients=["fuel_plugin"],
        topic="engine.state",
        data={"rpm": 2400}
    ))
    queue.process()  # Process pending messages
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from queue import PriorityQueue
from typing import Any


class MessagePriority(Enum):
    """Priority levels for messages.

    Messages are processed in order from CRITICAL to LOW.
    """

    CRITICAL = 0  # Highest priority (processed first)
    HIGH = 1
    NORMAL = 2
    LOW = 3  # Lowest priority (processed last)


@dataclass(order=True)
class Message:
    """Inter-plugin message.

    Messages are the primary means of communication between plugins.
    They are processed asynchronously through the message queue.

    Attributes:
        priority: Message priority (affects processing order).
        timestamp: Unix timestamp when message was created.
        sender: Name of the plugin sending the message.
        recipients: List of recipient plugin names, or ["*"] for broadcast.
        topic: Message category/type (e.g., "engine.state").
        data: Arbitrary message payload.
    """

    priority: int = field(compare=True)  # Store as int for comparison
    timestamp: float = field(default_factory=time.time, compare=True)
    sender: str = field(default="", compare=False)
    recipients: list[str] = field(default_factory=list, compare=False)
    topic: str = field(default="", compare=False)
    data: dict[str, Any] = field(default_factory=dict, compare=False)

    def __init__(
        self,
        sender: str,
        recipients: list[str],
        topic: str,
        data: dict[str, Any],
        priority: MessagePriority = MessagePriority.NORMAL,
    ) -> None:
        """Initialize a message.

        Args:
            sender: Name of sending plugin.
            recipients: List of recipient plugin names.
            topic: Message topic/category.
            data: Message payload.
            priority: Message priority (defaults to NORMAL).
        """
        self.priority = priority.value  # Convert enum to int
        self.timestamp = time.time()
        self.sender = sender
        self.recipients = recipients
        self.topic = topic
        self.data = data


class MessageTopic:
    """Standard message topics used throughout the application.

    This class serves as a registry of well-known topic names to avoid
    typos and provide documentation.
    """

    # Environmental
    TEMPERATURE_CHANGED = "env.temperature_changed"
    PRESSURE_CHANGED = "env.pressure_changed"
    ALTITUDE_CHANGED = "env.altitude_changed"

    # Systems
    ELECTRICAL_STATE = "system.electrical.state"
    FUEL_STATE = "system.fuel.state"
    ENGINE_STATE = "system.engine.state"
    HYDRAULIC_STATE = "system.hydraulic.state"

    # Flight
    POSITION_UPDATED = "flight.position_updated"
    FLIGHT_MODE_CHANGED = "flight.mode_changed"
    AUTOPILOT_ENGAGED = "flight.autopilot.engaged"
    GEAR_POSITION = "flight.gear.position"
    CONTROL_INPUT = "flight.control_input"

    # Cabin
    DOOR_STATE = "cabin.door.state"
    BOARDING_PROGRESS = "cabin.boarding.progress"
    PASSENGER_EVENT = "cabin.passenger.event"

    # Network
    TRAFFIC_UPDATE = "network.traffic.update"
    ATC_MESSAGE = "network.atc.message"

    # Collision
    COLLISION_DETECTED = "physics.collision_detected"
    TERRAIN_ELEVATION = "terrain.elevation"
    TERRAIN_UPDATED = "terrain.updated"
    NEARBY_CITIES = "terrain.nearby_cities"


class MessageQueue:
    """Asynchronous message queue for plugin communication.

    The message queue processes messages in batches, ordered by priority.
    Plugins subscribe to topics and receive messages matching those topics.

    Examples:
        >>> queue = MessageQueue()
        >>> def handler(msg: Message) -> None:
        ...     print(f"Engine RPM: {msg.data['rpm']}")
        >>> queue.subscribe("engine.state", handler)
        >>> queue.publish(Message(
        ...     sender="engine",
        ...     recipients=["*"],
        ...     topic="engine.state",
        ...     data={"rpm": 2400},
        ...     priority=MessagePriority.NORMAL
        ... ))
        >>> queue.process()
        Engine RPM: 2400
    """

    def __init__(self) -> None:
        """Initialize an empty message queue."""
        self._queue: PriorityQueue[Message] = PriorityQueue()
        self._subscriptions: dict[str, list[Callable[[Message], None]]] = {}

    def subscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        """Subscribe a handler to a topic.

        The handler will be called for all messages with matching topics.
        Handlers are called during the process() method.

        Args:
            topic: Topic string to subscribe to (e.g., "engine.state").
            handler: Callable that accepts a Message as its only parameter.

        Examples:
            >>> def on_engine_state(msg: Message) -> None:
            ...     print(f"RPM: {msg.data['rpm']}")
            >>> queue.subscribe("engine.state", on_engine_state)
        """
        if topic not in self._subscriptions:
            self._subscriptions[topic] = []
        self._subscriptions[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        """Unsubscribe a handler from a topic.

        Removes the handler from the subscription list. If the handler
        is not subscribed, this is a no-op.

        Args:
            topic: Topic to unsubscribe from.
            handler: Handler function to remove.

        Examples:
            >>> queue.unsubscribe("engine.state", on_engine_state)
        """
        if topic in self._subscriptions:
            self._subscriptions[topic] = [h for h in self._subscriptions[topic] if h != handler]

            # Clean up empty subscription lists
            if not self._subscriptions[topic]:
                del self._subscriptions[topic]

    def publish(self, message: Message) -> None:
        """Publish a message to the queue.

        The message is added to the priority queue and will be processed
        during the next process() call.

        Args:
            message: Message to publish.

        Examples:
            >>> queue.publish(Message(
            ...     sender="engine_plugin",
            ...     recipients=["fuel_plugin"],
            ...     topic="engine.state",
            ...     data={"rpm": 2400},
            ...     priority=MessagePriority.HIGH
            ... ))
        """
        self._queue.put(message)

    def process(self, max_messages: int = 100) -> int:
        """Process queued messages.

        Processes up to max_messages from the queue in priority order,
        dispatching each to subscribed handlers.

        Args:
            max_messages: Maximum number of messages to process in this call.
                Prevents infinite loops if messages generate more messages.
                Defaults to 100.

        Returns:
            Number of messages processed.

        Examples:
            >>> processed = queue.process(max_messages=50)
            >>> print(f"Processed {processed} messages")

        Note:
            This should be called once per frame in the game loop.
        """
        processed = 0

        while not self._queue.empty() and processed < max_messages:
            message = self._queue.get()
            self._dispatch(message)
            processed += 1

        return processed

    def _dispatch(self, message: Message) -> None:
        """Dispatch a message to subscribers.

        Internal method that routes messages to subscribed handlers.
        Handles both targeted messages and broadcasts.

        Args:
            message: Message to dispatch.
        """
        if message.topic in self._subscriptions:
            for handler in self._subscriptions[message.topic]:
                handler(message)

    def clear(self) -> None:
        """Remove all pending messages and subscriptions.

        This is primarily useful for testing or resetting the queue.
        """
        # Clear the queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except Exception:
                break

        # Clear subscriptions
        self._subscriptions.clear()

    def pending_count(self) -> int:
        """Get the number of pending messages in the queue.

        Returns:
            Number of messages waiting to be processed.
        """
        return self._queue.qsize()

    def get_subscriber_count(self, topic: str) -> int:
        """Get the number of subscribers for a topic.

        Args:
            topic: Topic to query.

        Returns:
            Number of handlers subscribed to this topic.
        """
        return len(self._subscriptions.get(topic, []))

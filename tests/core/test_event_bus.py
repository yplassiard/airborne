"""Tests for the event bus system."""

from dataclasses import dataclass

import pytest

from airborne.core.event_bus import Event, EventBus, EventPriority


@dataclass
class TestEvent(Event):
    """Test event with data."""

    data: str = ""


@dataclass
class AnotherEvent(Event):
    """Another test event."""

    value: int = 0


class TestEventBus:
    """Test suite for EventBus."""

    def test_subscribe_and_publish(self) -> None:
        """Test that subscribed handlers receive published events."""
        bus = EventBus()
        received_events = []

        def handler(event: TestEvent) -> None:
            received_events.append(event)

        bus.subscribe(TestEvent, handler)
        event = TestEvent(data="test")
        bus.publish(event)

        assert len(received_events) == 1
        assert received_events[0] == event
        assert received_events[0].data == "test"

    def test_multiple_handlers_for_same_event(self) -> None:
        """Test that multiple handlers receive the same event."""
        bus = EventBus()
        handler1_called = False
        handler2_called = False

        def handler1(event: TestEvent) -> None:
            nonlocal handler1_called
            handler1_called = True

        def handler2(event: TestEvent) -> None:
            nonlocal handler2_called
            handler2_called = True

        bus.subscribe(TestEvent, handler1)
        bus.subscribe(TestEvent, handler2)
        bus.publish(TestEvent(data="test"))

        assert handler1_called
        assert handler2_called

    def test_priority_order(self) -> None:
        """Test that handlers are called in priority order."""
        bus = EventBus()
        call_order = []

        def critical_handler(event: TestEvent) -> None:
            call_order.append("critical")

        def high_handler(event: TestEvent) -> None:
            call_order.append("high")

        def normal_handler(event: TestEvent) -> None:
            call_order.append("normal")

        def low_handler(event: TestEvent) -> None:
            call_order.append("low")

        # Subscribe in random order
        bus.subscribe(TestEvent, normal_handler, EventPriority.NORMAL)
        bus.subscribe(TestEvent, critical_handler, EventPriority.CRITICAL)
        bus.subscribe(TestEvent, low_handler, EventPriority.LOW)
        bus.subscribe(TestEvent, high_handler, EventPriority.HIGH)

        bus.publish(TestEvent(data="test"))

        # Should be called in priority order
        assert call_order == ["critical", "high", "normal", "low"]

    def test_different_event_types_isolated(self) -> None:
        """Test that different event types don't interfere."""
        bus = EventBus()
        test_event_count = 0
        another_event_count = 0

        def test_handler(event: TestEvent) -> None:
            nonlocal test_event_count
            test_event_count += 1

        def another_handler(event: AnotherEvent) -> None:
            nonlocal another_event_count
            another_event_count += 1

        bus.subscribe(TestEvent, test_handler)
        bus.subscribe(AnotherEvent, another_handler)

        bus.publish(TestEvent(data="test"))
        bus.publish(AnotherEvent(value=42))
        bus.publish(TestEvent(data="test2"))

        assert test_event_count == 2
        assert another_event_count == 1

    def test_unsubscribe(self) -> None:
        """Test that unsubscribing removes a handler."""
        bus = EventBus()
        call_count = 0

        def handler(event: TestEvent) -> None:
            nonlocal call_count
            call_count += 1

        bus.subscribe(TestEvent, handler)
        bus.publish(TestEvent(data="test1"))
        assert call_count == 1

        bus.unsubscribe(TestEvent, handler)
        bus.publish(TestEvent(data="test2"))
        assert call_count == 1  # Should not have increased

    def test_unsubscribe_nonexistent_handler(self) -> None:
        """Test that unsubscribing a non-existent handler is safe."""
        bus = EventBus()

        def handler(event: TestEvent) -> None:
            pass

        # Should not raise an exception
        bus.unsubscribe(TestEvent, handler)

    def test_unsubscribe_cleans_up_empty_lists(self) -> None:
        """Test that unsubscribe removes empty handler lists."""
        bus = EventBus()

        def handler(event: TestEvent) -> None:
            pass

        bus.subscribe(TestEvent, handler)
        assert bus.get_subscriber_count(TestEvent) == 1

        bus.unsubscribe(TestEvent, handler)
        assert bus.get_subscriber_count(TestEvent) == 0

    def test_clear(self) -> None:
        """Test that clear removes all handlers."""
        bus = EventBus()
        call_count = 0

        def handler(event: TestEvent) -> None:
            nonlocal call_count
            call_count += 1

        bus.subscribe(TestEvent, handler)
        bus.clear()
        bus.publish(TestEvent(data="test"))

        assert call_count == 0

    def test_get_subscriber_count(self) -> None:
        """Test getting the number of subscribers."""
        bus = EventBus()

        def handler1(event: TestEvent) -> None:
            pass

        def handler2(event: TestEvent) -> None:
            pass

        assert bus.get_subscriber_count(TestEvent) == 0

        bus.subscribe(TestEvent, handler1)
        assert bus.get_subscriber_count(TestEvent) == 1

        bus.subscribe(TestEvent, handler2)
        assert bus.get_subscriber_count(TestEvent) == 2

    def test_event_has_timestamp(self) -> None:
        """Test that events have timestamps."""
        import time

        before = time.time()
        event = TestEvent(data="test")
        after = time.time()

        assert before <= event.timestamp <= after

    def test_handler_exception_propagates(self) -> None:
        """Test that exceptions in handlers propagate to caller."""
        bus = EventBus()

        def failing_handler(event: TestEvent) -> None:
            raise ValueError("Handler error")

        bus.subscribe(TestEvent, failing_handler)

        with pytest.raises(ValueError, match="Handler error"):
            bus.publish(TestEvent(data="test"))

    def test_multiple_subscriptions_same_priority(self) -> None:
        """Test multiple handlers with same priority."""
        bus = EventBus()
        calls = []

        def handler1(event: TestEvent) -> None:
            calls.append(1)

        def handler2(event: TestEvent) -> None:
            calls.append(2)

        bus.subscribe(TestEvent, handler1, EventPriority.NORMAL)
        bus.subscribe(TestEvent, handler2, EventPriority.NORMAL)
        bus.publish(TestEvent(data="test"))

        assert len(calls) == 2
        # Both should be called, order within same priority is maintained
        assert 1 in calls and 2 in calls

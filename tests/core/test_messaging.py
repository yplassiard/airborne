"""Tests for the message queue system."""

import pytest

from airborne.core.messaging import Message, MessagePriority, MessageQueue, MessageTopic


class TestMessageQueue:
    """Test suite for MessageQueue."""

    def test_subscribe_and_publish(self) -> None:
        """Test that subscribed handlers receive published messages."""
        queue = MessageQueue()
        received_messages = []

        def handler(msg: Message) -> None:
            received_messages.append(msg)

        queue.subscribe("test.topic", handler)
        message = Message(
            sender="test_sender",
            recipients=["test_recipient"],
            topic="test.topic",
            data={"key": "value"},
            priority=MessagePriority.NORMAL,
        )
        queue.publish(message)
        queue.process()

        assert len(received_messages) == 1
        assert received_messages[0].sender == "test_sender"
        assert received_messages[0].data["key"] == "value"

    def test_multiple_subscribers(self) -> None:
        """Test that multiple handlers receive the same message."""
        queue = MessageQueue()
        handler1_called = False
        handler2_called = False

        def handler1(msg: Message) -> None:
            nonlocal handler1_called
            handler1_called = True

        def handler2(msg: Message) -> None:
            nonlocal handler2_called
            handler2_called = True

        queue.subscribe("test.topic", handler1)
        queue.subscribe("test.topic", handler2)
        queue.publish(
            Message(
                sender="test",
                recipients=["*"],
                topic="test.topic",
                data={},
                priority=MessagePriority.NORMAL,
            )
        )
        queue.process()

        assert handler1_called
        assert handler2_called

    def test_priority_order(self) -> None:
        """Test that messages are processed in priority order."""
        queue = MessageQueue()
        processed_order = []

        def handler(msg: Message) -> None:
            processed_order.append(msg.data["priority_name"])

        queue.subscribe("test.topic", handler)

        # Publish in random order
        queue.publish(
            Message(
                sender="test",
                recipients=["*"],
                topic="test.topic",
                data={"priority_name": "normal"},
                priority=MessagePriority.NORMAL,
            )
        )
        queue.publish(
            Message(
                sender="test",
                recipients=["*"],
                topic="test.topic",
                data={"priority_name": "critical"},
                priority=MessagePriority.CRITICAL,
            )
        )
        queue.publish(
            Message(
                sender="test",
                recipients=["*"],
                topic="test.topic",
                data={"priority_name": "low"},
                priority=MessagePriority.LOW,
            )
        )
        queue.publish(
            Message(
                sender="test",
                recipients=["*"],
                topic="test.topic",
                data={"priority_name": "high"},
                priority=MessagePriority.HIGH,
            )
        )

        queue.process()

        # Should be processed in priority order
        assert processed_order == ["critical", "high", "normal", "low"]

    def test_different_topics_isolated(self) -> None:
        """Test that different topics don't interfere."""
        queue = MessageQueue()
        topic1_count = 0
        topic2_count = 0

        def handler1(msg: Message) -> None:
            nonlocal topic1_count
            topic1_count += 1

        def handler2(msg: Message) -> None:
            nonlocal topic2_count
            topic2_count += 1

        queue.subscribe("topic1", handler1)
        queue.subscribe("topic2", handler2)

        queue.publish(
            Message(
                sender="test",
                recipients=["*"],
                topic="topic1",
                data={},
                priority=MessagePriority.NORMAL,
            )
        )
        queue.publish(
            Message(
                sender="test",
                recipients=["*"],
                topic="topic2",
                data={},
                priority=MessagePriority.NORMAL,
            )
        )
        queue.publish(
            Message(
                sender="test",
                recipients=["*"],
                topic="topic1",
                data={},
                priority=MessagePriority.NORMAL,
            )
        )

        queue.process()

        assert topic1_count == 2
        assert topic2_count == 1

    def test_unsubscribe(self) -> None:
        """Test that unsubscribing removes a handler."""
        queue = MessageQueue()
        call_count = 0

        def handler(msg: Message) -> None:
            nonlocal call_count
            call_count += 1

        queue.subscribe("test.topic", handler)
        queue.publish(
            Message(
                sender="test",
                recipients=["*"],
                topic="test.topic",
                data={},
                priority=MessagePriority.NORMAL,
            )
        )
        queue.process()
        assert call_count == 1

        queue.unsubscribe("test.topic", handler)
        queue.publish(
            Message(
                sender="test",
                recipients=["*"],
                topic="test.topic",
                data={},
                priority=MessagePriority.NORMAL,
            )
        )
        queue.process()
        assert call_count == 1  # Should not have increased

    def test_max_messages_limit(self) -> None:
        """Test that process respects max_messages limit."""
        queue = MessageQueue()
        processed = []

        def handler(msg: Message) -> None:
            processed.append(msg)

        queue.subscribe("test.topic", handler)

        # Publish 10 messages
        for i in range(10):
            queue.publish(
                Message(
                    sender="test",
                    recipients=["*"],
                    topic="test.topic",
                    data={"index": i},
                    priority=MessagePriority.NORMAL,
                )
            )

        # Process only 5
        count = queue.process(max_messages=5)
        assert count == 5
        assert len(processed) == 5

        # Process remaining
        count = queue.process(max_messages=10)
        assert count == 5
        assert len(processed) == 10

    def test_pending_count(self) -> None:
        """Test getting the number of pending messages."""
        queue = MessageQueue()

        assert queue.pending_count() == 0

        queue.publish(
            Message(
                sender="test",
                recipients=["*"],
                topic="test.topic",
                data={},
                priority=MessagePriority.NORMAL,
            )
        )
        assert queue.pending_count() == 1

        queue.publish(
            Message(
                sender="test",
                recipients=["*"],
                topic="test.topic",
                data={},
                priority=MessagePriority.NORMAL,
            )
        )
        assert queue.pending_count() == 2

        queue.process()
        assert queue.pending_count() == 0

    def test_clear(self) -> None:
        """Test that clear removes all messages and subscriptions."""
        queue = MessageQueue()
        call_count = 0

        def handler(msg: Message) -> None:
            nonlocal call_count
            call_count += 1

        queue.subscribe("test.topic", handler)
        queue.publish(
            Message(
                sender="test",
                recipients=["*"],
                topic="test.topic",
                data={},
                priority=MessagePriority.NORMAL,
            )
        )

        queue.clear()
        queue.process()

        assert call_count == 0
        assert queue.pending_count() == 0

    def test_get_subscriber_count(self) -> None:
        """Test getting the number of subscribers."""
        queue = MessageQueue()

        def handler1(msg: Message) -> None:
            pass

        def handler2(msg: Message) -> None:
            pass

        assert queue.get_subscriber_count("test.topic") == 0

        queue.subscribe("test.topic", handler1)
        assert queue.get_subscriber_count("test.topic") == 1

        queue.subscribe("test.topic", handler2)
        assert queue.get_subscriber_count("test.topic") == 2

    def test_message_has_timestamp(self) -> None:
        """Test that messages have timestamps."""
        import time

        before = time.time()
        message = Message(
            sender="test",
            recipients=["*"],
            topic="test.topic",
            data={},
            priority=MessagePriority.NORMAL,
        )
        after = time.time()

        assert before <= message.timestamp <= after

    def test_message_topic_constants(self) -> None:
        """Test that MessageTopic constants are defined."""
        assert hasattr(MessageTopic, "ENGINE_STATE")
        assert hasattr(MessageTopic, "FUEL_STATE")
        assert hasattr(MessageTopic, "ELECTRICAL_STATE")
        assert MessageTopic.ENGINE_STATE == "system.engine.state"

    def test_handler_exception_propagates(self) -> None:
        """Test that exceptions in handlers propagate."""
        queue = MessageQueue()

        def failing_handler(msg: Message) -> None:
            raise ValueError("Handler error")

        queue.subscribe("test.topic", failing_handler)
        queue.publish(
            Message(
                sender="test",
                recipients=["*"],
                topic="test.topic",
                data={},
                priority=MessagePriority.NORMAL,
            )
        )

        with pytest.raises(ValueError, match="Handler error"):
            queue.process()

    def test_process_returns_count(self) -> None:
        """Test that process returns the number of messages processed."""
        queue = MessageQueue()

        def handler(msg: Message) -> None:
            pass

        queue.subscribe("test.topic", handler)

        for _ in range(5):
            queue.publish(
                Message(
                    sender="test",
                    recipients=["*"],
                    topic="test.topic",
                    data={},
                    priority=MessagePriority.NORMAL,
                )
            )

        count = queue.process()
        assert count == 5

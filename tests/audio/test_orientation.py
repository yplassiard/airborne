"""Unit tests for orientation audio manager."""

import time

import pytest

from airborne.audio.orientation import OrientationAudioManager, ProximityAlert
from airborne.core.messaging import Message, MessageQueue
from airborne.physics.vectors import Vector3
from airborne.plugins.navigation.position_tracker import LocationType


@pytest.fixture
def message_queue() -> MessageQueue:
    """Create a test message queue."""
    return MessageQueue()


@pytest.fixture
def manager(message_queue: MessageQueue) -> OrientationAudioManager:
    """Create a test orientation audio manager."""
    return OrientationAudioManager(message_queue, cooldown_seconds=2.0)


class TestProximityAlert:
    """Test ProximityAlert dataclass."""

    def test_create_proximity_alert(self) -> None:
        """Test creating a proximity alert."""
        alert = ProximityAlert("runway", "31", [100.0, 50.0, 20.0])

        assert alert.feature_type == "runway"
        assert alert.feature_id == "31"
        assert alert.distances_m == [100.0, 50.0, 20.0]
        assert alert.last_announced_distance is None
        assert alert.last_announce_time == 0.0


class TestOrientationAudioManager:
    """Test OrientationAudioManager class."""

    def test_create_manager(self, message_queue: MessageQueue) -> None:
        """Test creating an orientation audio manager."""
        manager = OrientationAudioManager(message_queue, cooldown_seconds=3.0)

        assert manager.message_queue == message_queue
        assert manager.cooldown_seconds == 3.0
        assert manager.last_location_type is None
        assert manager.last_location_id == ""
        assert len(manager.proximity_alerts) == 0

    def test_create_manager_without_queue(self) -> None:
        """Test creating manager without message queue."""
        manager = OrientationAudioManager(None)

        assert manager.message_queue is None
        assert manager.cooldown_seconds == 5.0

    def test_subscribe_to_events(self, manager: OrientationAudioManager) -> None:
        """Test subscribing to location events."""
        # Should not raise exception
        manager.subscribe_to_events()
        manager.unsubscribe_from_events()

    def test_handle_location_change_taxiway(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test handling taxiway location change."""
        manager.handle_location_change(LocationType.TAXIWAY, "A")

        # Should publish TTS message
        processed = message_queue.process()
        assert processed == 1

        # Verify state updated
        assert manager.last_location_type == LocationType.TAXIWAY
        assert manager.last_location_id == "A"

    def test_handle_location_change_runway(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test handling runway location change."""
        manager.handle_location_change(LocationType.RUNWAY, "31")

        # Should publish TTS message
        processed = message_queue.process()
        assert processed == 1

        assert manager.last_location_type == LocationType.RUNWAY
        assert manager.last_location_id == "31"

    def test_handle_location_change_parking(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test handling parking location change."""
        manager.handle_location_change(LocationType.PARKING, "G1")

        processed = message_queue.process()
        assert processed == 1

        assert manager.last_location_type == LocationType.PARKING
        assert manager.last_location_id == "G1"

    def test_handle_location_change_apron(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test handling apron location change."""
        manager.handle_location_change(LocationType.APRON, "APRON1")

        processed = message_queue.process()
        assert processed == 1

    def test_handle_location_change_grass(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test handling grass location change."""
        manager.handle_location_change(LocationType.GRASS, "")

        processed = message_queue.process()
        assert processed == 1

    def test_cooldown_suppresses_duplicate(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test that cooldown suppresses duplicate announcements."""
        # First announcement should work
        manager.handle_location_change(LocationType.TAXIWAY, "A")
        assert message_queue.process() == 1

        # Second announcement within cooldown should be suppressed
        manager.handle_location_change(LocationType.TAXIWAY, "B")
        assert message_queue.process() == 0

        # Wait for cooldown
        time.sleep(2.1)

        # Third announcement after cooldown should work
        manager.handle_location_change(LocationType.TAXIWAY, "C")
        assert message_queue.process() == 1

    def test_duplicate_location_suppressed(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test that exact duplicate locations are suppressed."""
        manager.handle_location_change(LocationType.TAXIWAY, "A")
        message_queue.process()

        # Wait for cooldown
        time.sleep(2.1)

        # Same location should be suppressed even after cooldown
        manager.handle_location_change(LocationType.TAXIWAY, "A")
        assert message_queue.process() == 0

    def test_handle_approaching_feature_runway(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test approaching runway announcements."""
        # Start at 150m - no announcement
        manager.handle_approaching_feature("runway", "31", 150.0)
        assert message_queue.process() == 0

        # At 100m - should announce
        manager.handle_approaching_feature("runway", "31", 100.0)
        assert message_queue.process() == 1

        # At 75m - no announcement (between thresholds)
        manager.handle_approaching_feature("runway", "31", 75.0)
        assert message_queue.process() == 0

        # At 50m - should announce
        manager.handle_approaching_feature("runway", "31", 50.0)
        assert message_queue.process() == 1

        # At 20m - should announce
        manager.handle_approaching_feature("runway", "31", 20.0)
        assert message_queue.process() == 1

        # At 10m - no announcement (passed all thresholds)
        manager.handle_approaching_feature("runway", "31", 10.0)
        assert message_queue.process() == 0

    def test_approaching_feature_creates_alert(self, manager: OrientationAudioManager) -> None:
        """Test that approaching feature creates proximity alert."""
        assert len(manager.proximity_alerts) == 0

        manager.handle_approaching_feature("runway", "31", 100.0)

        assert len(manager.proximity_alerts) == 1
        assert "runway:31" in manager.proximity_alerts

    def test_approaching_feature_clears_alert_when_passed(
        self, manager: OrientationAudioManager
    ) -> None:
        """Test that proximity alert is cleared after passing."""
        manager.handle_approaching_feature("runway", "31", 100.0)
        assert len(manager.proximity_alerts) == 1

        # Pass all thresholds
        manager.handle_approaching_feature("runway", "31", 10.0)

        # Alert should be cleared
        assert len(manager.proximity_alerts) == 0

    def test_announce_current_position(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test manual position announcement."""
        manager.announce_current_position(LocationType.TAXIWAY, "A")

        # Should publish high-priority message
        processed = message_queue.process()
        assert processed == 1

    def test_announce_current_position_with_vector(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test manual position announcement with position vector."""
        position = Vector3(-122.0, 10.0, 37.5)
        manager.announce_current_position(LocationType.TAXIWAY, "A", position)

        processed = message_queue.process()
        assert processed == 1

    def test_announce_directional_cue(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test directional taxiway announcement."""
        manager.announce_directional_cue("left", "B")

        processed = message_queue.process()
        assert processed == 1

    def test_phonetic_conversion_single_letter(self) -> None:
        """Test converting single letters to phonetic."""
        assert OrientationAudioManager._to_phonetic("A") == "Alpha"
        assert OrientationAudioManager._to_phonetic("B") == "Bravo"
        assert OrientationAudioManager._to_phonetic("C") == "Charlie"
        assert OrientationAudioManager._to_phonetic("Z") == "Zulu"

    def test_phonetic_conversion_lowercase(self) -> None:
        """Test phonetic conversion with lowercase."""
        assert OrientationAudioManager._to_phonetic("a") == "Alpha"
        assert OrientationAudioManager._to_phonetic("z") == "Zulu"

    def test_phonetic_conversion_multi_char(self) -> None:
        """Test phonetic conversion for multi-character identifiers."""
        result = OrientationAudioManager._to_phonetic("A1")
        assert "Alpha" in result
        assert "1" in result

    def test_phonetic_conversion_number(self) -> None:
        """Test phonetic conversion for numbers."""
        result = OrientationAudioManager._to_phonetic("31")
        assert "31" in result or "3 1" in result

    def test_generate_taxiway_message(self, manager: OrientationAudioManager) -> None:
        """Test generating taxiway location message."""
        message = manager._generate_location_message(LocationType.TAXIWAY, "A")
        assert "taxiway" in message.lower()
        assert "Alpha" in message

    def test_generate_runway_message(self, manager: OrientationAudioManager) -> None:
        """Test generating runway location message."""
        message = manager._generate_location_message(LocationType.RUNWAY, "31")
        assert "runway" in message.lower()
        # Runway numbers are converted to phonetic (digits separated by spaces)
        assert "3" in message and "1" in message

    def test_generate_parking_message(self, manager: OrientationAudioManager) -> None:
        """Test generating parking location message."""
        message = manager._generate_location_message(LocationType.PARKING, "G1")
        assert "parking" in message.lower()
        assert "G1" in message

    def test_generate_apron_message(self, manager: OrientationAudioManager) -> None:
        """Test generating apron location message."""
        message = manager._generate_location_message(LocationType.APRON, "")
        assert "apron" in message.lower()

    def test_generate_grass_message(self, manager: OrientationAudioManager) -> None:
        """Test generating grass location message."""
        message = manager._generate_location_message(LocationType.GRASS, "")
        assert "pavement" in message.lower() or "off" in message.lower()

    def test_generate_unknown_message(self, manager: OrientationAudioManager) -> None:
        """Test generating unknown location message."""
        message = manager._generate_location_message(LocationType.UNKNOWN, "")
        assert "unknown" in message.lower()

    def test_generate_approaching_runway_message(self, manager: OrientationAudioManager) -> None:
        """Test generating approaching runway message."""
        message = manager._generate_approaching_message("runway", "31", 50.0)
        assert "approaching" in message.lower()
        assert "runway" in message.lower()
        assert "50" in message

    def test_generate_approaching_intersection_message(
        self, manager: OrientationAudioManager
    ) -> None:
        """Test generating approaching intersection message."""
        message = manager._generate_approaching_message("intersection", "A", 100.0)
        assert "approaching" in message.lower()
        assert "intersection" in message.lower()
        assert "100" in message

    def test_on_location_changed_message(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test handling location changed message from queue."""
        # Create location change message
        msg = Message(
            sender="position_tracker",
            recipients=["orientation_audio"],
            topic="navigation.entered_taxiway",
            data={"location_type": "taxiway", "location_id": "A"},
        )

        # Handle message
        manager._on_location_changed(msg)

        # Should publish announcement
        processed = message_queue.process()
        assert processed == 1

    def test_on_location_changed_invalid_type(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test handling message with invalid location type."""
        msg = Message(
            sender="position_tracker",
            recipients=["orientation_audio"],
            topic="navigation.location_changed",
            data={"location_type": "invalid_type", "location_id": "X"},
        )

        # Should not crash
        manager._on_location_changed(msg)

        # Should not publish announcement
        assert message_queue.process() == 0

    def test_manager_without_queue_does_not_crash(self) -> None:
        """Test that manager without queue handles calls gracefully."""
        manager = OrientationAudioManager(None)

        # Should not crash
        manager.subscribe_to_events()
        manager.handle_location_change(LocationType.TAXIWAY, "A")
        manager.announce_current_position(LocationType.RUNWAY, "31")
        manager.unsubscribe_from_events()

    def test_multiple_proximity_alerts(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test multiple simultaneous proximity alerts."""
        # Add alerts for two different runways
        manager.handle_approaching_feature("runway", "31", 100.0)
        manager.handle_approaching_feature("runway", "13", 100.0)

        # Should have two alerts
        assert len(manager.proximity_alerts) == 2

        # Should publish two messages
        assert message_queue.process() == 2

    def test_approaching_same_feature_multiple_times(
        self, manager: OrientationAudioManager, message_queue: MessageQueue
    ) -> None:
        """Test approaching same feature multiple times."""
        # First approach at 100m
        manager.handle_approaching_feature("runway", "31", 100.0)
        assert message_queue.process() == 1

        # Still at 100m - should not announce again
        manager.handle_approaching_feature("runway", "31", 100.0)
        assert message_queue.process() == 0

        # Getting closer to 50m
        manager.handle_approaching_feature("runway", "31", 60.0)
        assert message_queue.process() == 0

        # Reached 50m threshold
        manager.handle_approaching_feature("runway", "31", 50.0)
        assert message_queue.process() == 1

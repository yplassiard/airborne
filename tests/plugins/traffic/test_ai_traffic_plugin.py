"""Tests for AI traffic plugin."""

import pytest

from airborne.core.event_bus import EventBus
from airborne.core.messaging import Message, MessageQueue, MessageTopic
from airborne.core.plugin import PluginContext
from airborne.core.registry import ComponentRegistry
from airborne.physics.vectors import Vector3
from airborne.plugins.traffic.ai_aircraft import AIAircraft
from airborne.plugins.traffic.ai_traffic_plugin import AITrafficPlugin


@pytest.fixture
def traffic_plugin():
    """Create AI traffic plugin with context."""
    plugin = AITrafficPlugin()

    event_bus = EventBus()
    message_queue = MessageQueue()
    registry = ComponentRegistry()

    context = PluginContext(
        event_bus=event_bus,
        message_queue=message_queue,
        config={},
        plugin_registry=registry,
    )

    plugin.initialize(context)
    return plugin


def test_traffic_plugin_metadata(traffic_plugin):
    """Test traffic plugin metadata."""
    metadata = traffic_plugin.get_metadata()

    assert metadata.name == "ai_traffic"
    assert "ai_traffic" in metadata.provides


def test_traffic_plugin_starts_empty(traffic_plugin):
    """Test traffic plugin starts with no aircraft."""
    assert traffic_plugin.get_aircraft_count() == 0


def test_traffic_plugin_add_aircraft(traffic_plugin):
    """Test adding aircraft to traffic plugin."""
    aircraft = AIAircraft(
        callsign="TEST123",
        aircraft_type="C172",
        position=Vector3(0, 1000, 0),
        heading=90,
        altitude_ft=5000,
        airspeed_kts=100,
    )

    traffic_plugin.add_aircraft(aircraft)

    assert traffic_plugin.get_aircraft_count() == 1
    assert traffic_plugin.get_aircraft("TEST123") == aircraft


def test_traffic_plugin_remove_aircraft(traffic_plugin):
    """Test removing aircraft from traffic plugin."""
    aircraft = AIAircraft(
        callsign="TEST123",
        aircraft_type="C172",
        position=Vector3(0, 1000, 0),
        heading=90,
        altitude_ft=5000,
        airspeed_kts=100,
    )

    traffic_plugin.add_aircraft(aircraft)
    assert traffic_plugin.get_aircraft_count() == 1

    traffic_plugin.remove_aircraft("TEST123")
    assert traffic_plugin.get_aircraft_count() == 0


def test_traffic_plugin_updates_aircraft(traffic_plugin):
    """Test traffic plugin updates aircraft positions."""
    aircraft = AIAircraft(
        callsign="TEST123",
        aircraft_type="C172",
        position=Vector3(0, 1000, 0),
        heading=0,  # North
        altitude_ft=5000,
        airspeed_kts=100,
    )

    traffic_plugin.add_aircraft(aircraft)

    initial_pos = aircraft.position
    traffic_plugin.update(1.0)  # Update 1 second

    # Aircraft should have moved
    assert aircraft.position.z > initial_pos.z


def test_traffic_plugin_removes_distant_aircraft(traffic_plugin):
    """Test traffic plugin removes aircraft beyond despawn distance."""
    # Set player position
    traffic_plugin._player_position = Vector3(0, 1000, 0)

    # Add aircraft far away (beyond despawn distance)
    aircraft = AIAircraft(
        callsign="DISTANT",
        aircraft_type="C172",
        position=Vector3(0, 1000, 200000),  # Very far
        heading=90,
        altitude_ft=5000,
        airspeed_kts=100,
    )

    traffic_plugin.add_aircraft(aircraft)
    assert traffic_plugin.get_aircraft_count() == 1

    # Update should remove distant aircraft
    traffic_plugin.update(1.0)

    assert traffic_plugin.get_aircraft_count() == 0


def test_traffic_plugin_broadcasts_updates(traffic_plugin):
    """Test traffic plugin broadcasts traffic updates."""
    # Add aircraft
    aircraft = AIAircraft(
        callsign="TEST123",
        aircraft_type="C172",
        position=Vector3(0, 1000, 0),
        heading=90,
        altitude_ft=5000,
        airspeed_kts=100,
    )

    traffic_plugin.add_aircraft(aircraft)

    # Set broadcast interval to 0 to force immediate broadcast
    traffic_plugin._update_interval = 0.0

    # Capture published messages
    messages = []

    def capture_message(msg):
        messages.append(msg)

    traffic_plugin._message_queue.subscribe(MessageTopic.TRAFFIC_UPDATE, capture_message)

    # Update (should trigger broadcast)
    traffic_plugin.update(0.1)
    traffic_plugin._message_queue.process()

    # Should have broadcast message
    assert len(messages) > 0
    assert messages[0].topic == MessageTopic.TRAFFIC_UPDATE
    assert "traffic" in messages[0].data
    assert len(messages[0].data["traffic"]) == 1


def test_traffic_plugin_updates_player_position(traffic_plugin):
    """Test traffic plugin tracks player position."""
    position = Vector3(1000, 2000, 3000)

    message = Message(
        sender="physics",
        recipients=["*"],
        topic=MessageTopic.POSITION_UPDATED,
        data={"position": position},
    )

    traffic_plugin.handle_message(message)

    assert traffic_plugin._player_position == position


def test_traffic_plugin_get_all_aircraft(traffic_plugin):
    """Test getting all aircraft."""
    aircraft1 = AIAircraft(
        callsign="TEST1",
        aircraft_type="C172",
        position=Vector3(0, 1000, 0),
        heading=90,
        altitude_ft=5000,
        airspeed_kts=100,
    )

    aircraft2 = AIAircraft(
        callsign="TEST2",
        aircraft_type="C182",
        position=Vector3(1000, 1000, 1000),
        heading=180,
        altitude_ft=6000,
        airspeed_kts=120,
    )

    traffic_plugin.add_aircraft(aircraft1)
    traffic_plugin.add_aircraft(aircraft2)

    all_aircraft = traffic_plugin.get_all_aircraft()

    assert len(all_aircraft) == 2
    assert "TEST1" in all_aircraft
    assert "TEST2" in all_aircraft


def test_traffic_plugin_clear_all(traffic_plugin):
    """Test clearing all aircraft."""
    aircraft = AIAircraft(
        callsign="TEST123",
        aircraft_type="C172",
        position=Vector3(0, 1000, 0),
        heading=90,
        altitude_ft=5000,
        airspeed_kts=100,
    )

    traffic_plugin.add_aircraft(aircraft)
    assert traffic_plugin.get_aircraft_count() == 1

    traffic_plugin.clear_all_aircraft()
    assert traffic_plugin.get_aircraft_count() == 0


def test_traffic_plugin_enable_disable(traffic_plugin):
    """Test enabling/disabling traffic."""
    assert traffic_plugin._traffic_enabled

    traffic_plugin.set_traffic_enabled(False)
    assert not traffic_plugin._traffic_enabled

    # Should clear aircraft when disabled
    aircraft = AIAircraft(
        callsign="TEST123",
        aircraft_type="C172",
        position=Vector3(0, 1000, 0),
        heading=90,
        altitude_ft=5000,
        airspeed_kts=100,
    )

    traffic_plugin.add_aircraft(aircraft)
    traffic_plugin.set_traffic_enabled(False)

    assert traffic_plugin.get_aircraft_count() == 0

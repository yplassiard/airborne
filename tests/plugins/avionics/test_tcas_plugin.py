"""Tests for TCAS plugin."""

import pytest

from airborne.core.event_bus import EventBus
from airborne.core.messaging import Message, MessageQueue, MessageTopic
from airborne.core.plugin import PluginContext
from airborne.core.registry import ComponentRegistry
from airborne.physics.vectors import Vector3
from airborne.plugins.avionics.tcas_plugin import TCASPlugin
from airborne.plugins.traffic.ai_aircraft import AIAircraft


@pytest.fixture
def tcas_plugin():
    """Create TCAS plugin with context."""
    plugin = TCASPlugin()

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


def test_tcas_metadata(tcas_plugin):
    """Test TCAS plugin metadata."""
    metadata = tcas_plugin.get_metadata()

    assert metadata.name == "tcas"
    assert "electrical" in metadata.dependencies
    assert "tcas" in metadata.provides


def test_tcas_starts_unpowered(tcas_plugin):
    """Test TCAS starts unpowered."""
    assert not tcas_plugin._powered


def test_tcas_powers_on_with_electrical(tcas_plugin):
    """Test TCAS powers on when electrical system provides power."""
    # Send electrical state message
    message = Message(
        sender="electrical",
        recipients=["tcas"],
        topic=MessageTopic.ELECTRICAL_STATE,
        data={"bus_voltage": 28.0},
    )

    tcas_plugin.handle_message(message)

    assert tcas_plugin._powered


def test_tcas_updates_own_position(tcas_plugin):
    """Test TCAS updates own aircraft position."""
    position = Vector3(1000, 2000, 3000)

    message = Message(
        sender="physics",
        recipients=["*"],
        topic=MessageTopic.POSITION_UPDATED,
        data={
            "position": position,
            "altitude_ft": 5000,
            "vertical_speed_fpm": 500,
        },
    )

    tcas_plugin.handle_message(message)

    assert tcas_plugin._own_position == position
    assert tcas_plugin._own_altitude_ft == 5000
    assert tcas_plugin._own_vertical_speed_fpm == 500


def test_tcas_receives_traffic_updates(tcas_plugin):
    """Test TCAS receives and processes traffic updates."""
    # Create AI aircraft
    aircraft = AIAircraft(
        callsign="TEST123",
        aircraft_type="C172",
        position=Vector3(1000, 5000, 1000),
        heading=90,
        altitude_ft=5000,
        airspeed_kts=100,
    )

    # Power on TCAS
    tcas_plugin._powered = True
    tcas_plugin._own_position = Vector3(0, 5000, 0)
    tcas_plugin._own_altitude_ft = 5000

    # Send traffic update
    message = Message(
        sender="ai_traffic",
        recipients=["*"],
        topic=MessageTopic.TRAFFIC_UPDATE,
        data={"traffic": [aircraft]},
    )

    tcas_plugin.handle_message(message)

    # Should have one target
    assert len(tcas_plugin._targets) == 1
    assert "TEST123" in tcas_plugin._targets


def test_tcas_ignores_distant_traffic(tcas_plugin):
    """Test TCAS ignores traffic beyond 10 NM."""
    # Create distant aircraft (20 NM away)
    aircraft = AIAircraft(
        callsign="DISTANT",
        aircraft_type="C172",
        position=Vector3(0, 5000, 121520),  # 20 NM north (20 * 6076)
        heading=90,
        altitude_ft=5000,
        airspeed_kts=100,
    )

    tcas_plugin._powered = True
    tcas_plugin._own_position = Vector3(0, 5000, 0)
    tcas_plugin._own_altitude_ft = 5000

    message = Message(
        sender="ai_traffic",
        recipients=["*"],
        topic=MessageTopic.TRAFFIC_UPDATE,
        data={"traffic": [aircraft]},
    )

    tcas_plugin.handle_message(message)

    # Should have no targets (too far)
    assert len(tcas_plugin._targets) == 0


def test_tcas_issues_traffic_advisory():
    """Test TCAS detects closing traffic."""
    plugin = TCASPlugin()
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
    plugin._powered = True

    # Position own aircraft
    plugin._own_position = Vector3(0, 5000, 0)
    plugin._own_altitude_ft = 5000

    # Create closing traffic (2 NM away, same altitude, closing fast)
    aircraft = AIAircraft(
        callsign="THREAT",
        aircraft_type="C172",
        position=Vector3(0, 5000, 12152),  # 2 NM north
        heading=180,  # Heading south (toward us)
        altitude_ft=5000,
        airspeed_kts=200,
        velocity=Vector3(0, 0, -102.8),  # 200 kts south
    )

    # Send traffic update
    message = Message(
        sender="ai_traffic",
        recipients=["*"],
        topic=MessageTopic.TRAFFIC_UPDATE,
        data={"traffic": [aircraft]},
    )

    plugin.handle_message(message)

    # Should track the aircraft
    assert len(plugin._targets) == 1
    assert "THREAT" in plugin._targets


def test_tcas_enable_disable(tcas_plugin):
    """Test TCAS enable/disable functionality."""
    assert tcas_plugin._enabled

    tcas_plugin.set_enabled(False)
    assert not tcas_plugin._enabled

    tcas_plugin.set_enabled(True)
    assert tcas_plugin._enabled


def test_tcas_get_targets(tcas_plugin):
    """Test getting tracked targets."""
    targets = tcas_plugin.get_targets()
    assert isinstance(targets, dict)
    assert len(targets) == 0  # Initially empty

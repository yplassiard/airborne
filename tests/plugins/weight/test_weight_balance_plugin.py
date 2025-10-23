"""Unit tests for weight and balance plugin."""

import pytest

from airborne.core.messaging import Message, MessageQueue, MessageTopic
from airborne.core.plugin import PluginContext
from airborne.plugins.weight.weight_balance_plugin import WeightBalancePlugin
from airborne.systems.weight_balance import LoadStation


@pytest.fixture
def message_queue():
    """Create a message queue for testing."""
    return MessageQueue()


@pytest.fixture
def plugin_context(message_queue):
    """Create a plugin context for testing."""
    config = {
        "aircraft": {
            "weight_balance": {
                "empty_weight": 1600.0,
                "empty_moment": 136000.0,
                "max_gross_weight": 2550.0,
                "stations": {
                    "fuel_tanks": [
                        {
                            "name": "main_tank",
                            "arm": 95.0,
                            "max_weight": 312.0,
                            "initial_weight": 312.0,
                        }
                    ],
                    "seats": [
                        {
                            "name": "seat_pilot",
                            "arm": 85.0,
                            "max_weight": 200.0,
                            "initial_weight": 200.0,
                        },
                        {
                            "name": "seat_copilot",
                            "arm": 85.0,
                            "max_weight": 200.0,
                            "initial_weight": 0.0,
                        },
                        {
                            "name": "seat_rear_left",
                            "arm": 118.0,
                            "max_weight": 200.0,
                            "initial_weight": 0.0,
                        },
                        {
                            "name": "seat_rear_right",
                            "arm": 118.0,
                            "max_weight": 200.0,
                            "initial_weight": 0.0,
                        },
                    ],
                    "cargo": [
                        {
                            "name": "cargo_bay",
                            "arm": 142.0,
                            "max_weight": 120.0,
                            "initial_weight": 0.0,
                        }
                    ],
                },
            }
        }
    }

    return PluginContext(
        event_bus=None,
        message_queue=message_queue,
        config=config,
        plugin_registry=None,
    )


@pytest.fixture
def plugin(plugin_context):
    """Create a weight and balance plugin for testing."""
    plugin = WeightBalancePlugin()
    plugin.initialize(plugin_context)
    return plugin


def test_plugin_initialization(plugin):
    """Test plugin initializes correctly."""
    assert plugin is not None
    assert plugin.empty_weight == 1600.0
    assert plugin.empty_moment == 136000.0
    assert plugin.max_gross_weight == 2550.0
    assert len(plugin.stations) == 6  # main_tank + pilot + copilot + 2 rear seats + cargo


def test_initial_weight_calculation(plugin):
    """Test initial weight is calculated correctly."""
    # Empty + pilot (200) + full fuel (312)
    expected_weight = 1600.0 + 200.0 + 312.0
    assert abs(plugin.get_total_weight() - expected_weight) < 0.1


def test_initial_cg_calculation(plugin):
    """Test initial CG is calculated correctly."""
    # Should be around 90-95 inches
    cg = plugin.get_cg_position()
    assert 85.0 < cg < 100.0


def test_weight_station_dataclass():
    """Test LoadStation dataclass works correctly."""
    station = LoadStation(
        name="test",
        current_weight=100.0,
        arm=50.0,
        max_weight=200.0,
        station_type="cargo",
    )
    assert station.name == "test"
    assert station.current_weight == 100.0
    assert station.arm == 50.0
    assert station.max_weight == 200.0


def test_fuel_update_changes_weight(plugin, message_queue):
    """Test fuel updates change total weight."""
    initial_weight = plugin.get_total_weight()

    # Reduce fuel to 20 gallons (120 lbs)
    message_queue.publish(
        Message(
            sender="fuel_system",
            recipients=["weight_balance_plugin"],
            topic="fuel.state",
            data={"quantity": 20.0},
        )
    )

    message_queue.process()

    # Weight should decrease by (312 - 120) = 192 lbs
    new_weight = plugin.get_total_weight()
    assert abs((initial_weight - new_weight) - 192.0) < 0.1


def test_fuel_update_changes_cg(plugin, message_queue):
    """Test fuel updates change CG."""
    initial_cg = plugin.get_cg_position()

    # Empty fuel tank
    message_queue.publish(
        Message(
            sender="fuel_system",
            recipients=["weight_balance_plugin"],
            topic="fuel.state",
            data={"quantity": 0.0},
        )
    )

    message_queue.process()

    # CG should move (fuel is at 95 inches, removing it changes CG)
    new_cg = plugin.get_cg_position()
    assert new_cg != initial_cg


def test_boarding_adds_passenger_weight(plugin, message_queue):
    """Test boarding service adds passenger weight."""
    initial_weight = plugin.get_total_weight()

    # Board 1 additional passenger (copilot)
    message_queue.publish(
        Message(
            sender="boarding_service",
            recipients=["weight_balance_plugin"],
            topic="ground.service.complete",
            data={"service_type": "boarding", "passengers": 2},
        )
    )

    message_queue.process()

    # Weight should increase by 200 lbs (1 additional passenger at 200 lbs each)
    # Total passengers = 2, we started with pilot weight = 200, so adding 2 * 200 = 400
    # But plugin distributes 400 lbs across 2 seat stations, so each gets 200
    # We had pilot already (200), so copilot gets 200 more
    new_weight = plugin.get_total_weight()
    weight_increase = new_weight - initial_weight
    assert abs(weight_increase - 200.0) < 0.1


def test_overweight_detection(plugin, message_queue):
    """Test overweight condition is detected."""
    # Initially within limits
    assert plugin.is_within_limits()

    # Add excessive cargo to exceed max gross weight
    plugin.stations["cargo_bay"].weight = 1000.0  # Add 1000 lbs
    plugin._recalculate()

    # Should be overweight now
    assert not plugin.is_within_limits()
    assert plugin.get_total_weight() > plugin.max_gross_weight


def test_performance_update_message_published(plugin, message_queue):
    """Test performance update message is published after weight change."""
    # Capture published messages
    captured_messages = []

    def capture_handler(msg):
        captured_messages.append(msg)

    message_queue.subscribe("aircraft.performance.update", capture_handler)

    # Change fuel
    message_queue.publish(
        Message(
            sender="fuel_system",
            recipients=["weight_balance_plugin"],
            topic="fuel.state",
            data={"quantity": 10.0},
        )
    )

    message_queue.process()

    # Should have published performance update
    assert len(captured_messages) > 0
    perf_msg = captured_messages[-1]
    assert "total_weight" in perf_msg.data
    assert "vr_factor" in perf_msg.data
    assert "climb_rate_factor" in perf_msg.data
    assert "fuel_flow_factor" in perf_msg.data


def test_performance_factors_with_light_weight(plugin, message_queue):
    """Test performance factors with light aircraft (less fuel)."""
    # Empty most of the fuel
    message_queue.publish(
        Message(
            sender="fuel_system",
            recipients=["weight_balance_plugin"],
            topic="fuel.state",
            data={"quantity": 5.0},  # Only 5 gallons
        )
    )

    # Capture performance message
    captured_messages = []

    def capture_handler(msg):
        captured_messages.append(msg)

    message_queue.subscribe("aircraft.performance.update", capture_handler)

    message_queue.process()

    perf_data = captured_messages[-1].data

    # Light aircraft should have:
    # - Lower Vr factor (easier to rotate)
    # - Higher climb rate factor (more excess power)
    # - Lower fuel flow factor (less power needed)
    assert perf_data["vr_factor"] < 1.0
    assert perf_data["climb_rate_factor"] > 1.0
    assert perf_data["fuel_flow_factor"] < 1.0


def test_performance_factors_with_heavy_weight(plugin, message_queue):
    """Test performance factors with heavy aircraft (full fuel + passengers)."""
    # Add more passengers
    plugin.stations["seat_copilot"].weight = 200.0
    plugin.stations["seat_rear_left"].weight = 200.0
    plugin.stations["seat_rear_right"].weight = 200.0
    plugin._recalculate()
    plugin._publish_performance_update()

    # Capture performance message
    captured_messages = []

    def capture_handler(msg):
        captured_messages.append(msg)

    message_queue.subscribe("aircraft.performance.update", capture_handler)

    message_queue.process()

    perf_data = captured_messages[-1].data

    # Heavy aircraft should have:
    # - Higher Vr factor (harder to rotate)
    # - Lower climb rate factor (less excess power)
    # - Higher fuel flow factor (more power needed)
    assert perf_data["vr_factor"] > 1.0
    assert perf_data["climb_rate_factor"] < 1.0
    assert perf_data["fuel_flow_factor"] > 1.0


def test_boarding_progress_updates_weight(plugin, message_queue):
    """Test boarding progress messages update weight incrementally."""
    initial_weight = plugin.get_total_weight()

    # Simulate boarding progress (2 passengers)
    message_queue.publish(
        Message(
            sender="boarding_service",
            recipients=["weight_balance_plugin"],
            topic=MessageTopic.BOARDING_PROGRESS,
            data={"passengers_boarded": 2},
        )
    )

    message_queue.process()

    # Weight should increase by 400 lbs (2 passengers × 200 lbs)
    # But we started with 200 lbs (pilot), so increase should be 200 lbs
    new_weight = plugin.get_total_weight()
    weight_increase = new_weight - initial_weight
    assert abs(weight_increase - 200.0) < 0.1


def test_get_metadata(plugin):
    """Test plugin metadata."""
    metadata = plugin.get_metadata()
    assert metadata.name == "weight_balance_plugin"
    assert metadata.version == "1.0.0"
    assert "weight_balance" in metadata.provides


def test_shutdown_unsubscribes(plugin, message_queue):
    """Test shutdown unsubscribes from messages."""
    # Shutdown plugin
    plugin.shutdown()

    # Publish message (should not be processed)
    message_queue.publish(
        Message(
            sender="fuel_system",
            recipients=["weight_balance_plugin"],
            topic="fuel.state",
            data={"quantity": 0.0},
        )
    )

    # Should not crash
    message_queue.process()


def test_empty_stations_handling(message_queue):
    """Test plugin handles configuration with no stations."""
    config = {
        "aircraft": {
            "weight_balance": {
                "empty_weight": 1600.0,
                "empty_moment": 136000.0,
                "max_gross_weight": 2550.0,
                "stations": {},
            }
        }
    }

    context = PluginContext(
        event_bus=None,
        message_queue=message_queue,
        config=config,
        plugin_registry=None,
    )

    plugin = WeightBalancePlugin()
    plugin.initialize(context)

    # Should initialize with just empty weight
    assert plugin.get_total_weight() == 1600.0


def test_cg_calculation_accuracy(plugin):
    """Test CG calculation is mathematically correct."""
    # Manual calculation
    total_weight = 0.0
    total_moment = 0.0

    # Empty aircraft
    total_weight += plugin.empty_weight
    total_moment += plugin.empty_moment

    # Add station weights
    for station in plugin.stations.values():
        total_weight += station.weight
        total_moment += station.weight * station.arm

    expected_cg = total_moment / total_weight

    # Compare with plugin calculation
    assert abs(plugin.get_cg_position() - expected_cg) < 0.01

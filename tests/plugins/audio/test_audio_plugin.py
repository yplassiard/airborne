"""Tests for audio plugin."""

import sys
from unittest.mock import Mock

import pytest

# Mock the pybass3 module before any imports
sys.modules["pybass3"] = Mock()

from airborne.core.event_bus import EventBus  # noqa: E402
from airborne.core.messaging import Message, MessageTopic  # noqa: E402
from airborne.core.plugin import PluginContext, PluginType  # noqa: E402
from airborne.plugins.audio.audio_plugin import AudioPlugin  # noqa: E402


class TestAudioPluginMetadata:
    """Test audio plugin metadata."""

    def test_get_metadata(self) -> None:
        """Test getting plugin metadata."""
        plugin = AudioPlugin()
        metadata = plugin.get_metadata()

        assert metadata.name == "audio_plugin"
        assert metadata.version == "1.0.0"
        assert metadata.plugin_type == PluginType.CORE
        assert "audio_engine" in metadata.provides
        assert "sound_manager" in metadata.provides
        assert "tts" in metadata.provides
        assert metadata.optional is False


class TestAudioPluginInitialization:
    """Test audio plugin initialization."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def message_queue(self) -> Mock:
        """Create mock message queue."""
        queue = Mock()
        queue.subscribe = Mock()
        queue.publish = Mock()
        queue.unsubscribe = Mock()
        return queue

    @pytest.fixture
    def registry(self) -> Mock:
        """Create mock registry."""
        reg = Mock()
        reg.register = Mock()
        reg.unregister = Mock()
        return reg

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: Mock, registry: Mock) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={"audio": {"sample_rate": 44100}, "tts": {"rate": 200}},
            plugin_registry=registry,
        )

    def test_initialize(self, context: PluginContext) -> None:
        """Test audio plugin initialization."""
        plugin = AudioPlugin()
        plugin.initialize(context)

        assert plugin.context == context
        assert plugin.sound_manager is not None
        assert plugin.audio_engine is not None
        assert plugin.tts_provider is not None

        # Should register components
        assert context.plugin_registry.register.call_count == 3

        # Should subscribe to eight message topics: POSITION_UPDATED, TTS_SPEAK, TTS_INTERRUPT, PROXIMITY_BEEP, CONTROL_INPUT, ENGINE_STATE, SYSTEM_STATE, electrical.master_switch
        assert context.message_queue.subscribe.call_count == 8


class TestAudioPluginPositionHandling:
    """Test audio plugin position update handling."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def message_queue(self) -> Mock:
        """Create mock message queue."""
        queue = Mock()
        queue.subscribe = Mock()
        queue.publish = Mock()
        return queue

    @pytest.fixture
    def registry(self) -> Mock:
        """Create mock registry."""
        return Mock()

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: Mock, registry: Mock) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={"audio": {}, "tts": {}},
            plugin_registry=registry,
        )

    @pytest.fixture
    def plugin(self, context: PluginContext) -> AudioPlugin:
        """Create initialized audio plugin."""
        plugin = AudioPlugin()
        plugin.initialize(context)
        return plugin

    def test_handle_position_update_dict(self, plugin: AudioPlugin) -> None:
        """Test handling position update with dict format."""
        message = Message(
            sender="physics",
            recipients=["*"],
            topic=MessageTopic.POSITION_UPDATED,
            data={
                "position": {"x": 100.0, "y": 50.0, "z": 200.0},
                "forward": {"x": 0.0, "y": 0.0, "z": 1.0},
                "up": {"x": 0.0, "y": 1.0, "z": 0.0},
                "velocity": {"x": 10.0, "y": 0.0, "z": 20.0},
            },
        )

        plugin.handle_message(message)

        assert plugin._listener_position.x == 100.0
        assert plugin._listener_position.y == 50.0
        assert plugin._listener_position.z == 200.0
        assert plugin._listener_forward.z == 1.0
        assert plugin._listener_up.y == 1.0
        assert plugin._listener_velocity.x == 10.0

    def test_handle_position_update_list(self, plugin: AudioPlugin) -> None:
        """Test handling position update with list format."""
        message = Message(
            sender="physics",
            recipients=["*"],
            topic=MessageTopic.POSITION_UPDATED,
            data={
                "position": [100.0, 50.0, 200.0],
                "forward": [0.0, 0.0, 1.0],
                "up": [0.0, 1.0, 0.0],
                "velocity": [10.0, 0.0, 20.0],
            },
        )

        plugin.handle_message(message)

        assert plugin._listener_position.x == 100.0
        assert plugin._listener_forward.z == 1.0


class TestAudioPluginShutdown:
    """Test audio plugin shutdown."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def message_queue(self) -> Mock:
        """Create mock message queue."""
        queue = Mock()
        queue.subscribe = Mock()
        queue.publish = Mock()
        queue.unsubscribe = Mock()
        return queue

    @pytest.fixture
    def registry(self) -> Mock:
        """Create mock registry."""
        reg = Mock()
        reg.register = Mock()
        reg.unregister = Mock()
        return reg

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: Mock, registry: Mock) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={"audio": {}, "tts": {}},
            plugin_registry=registry,
        )

    @pytest.fixture
    def plugin(self, context: PluginContext) -> AudioPlugin:
        """Create initialized audio plugin."""
        plugin = AudioPlugin()
        plugin.initialize(context)
        return plugin

    def test_shutdown(self, plugin: AudioPlugin) -> None:
        """Test audio plugin shutdown."""
        plugin.shutdown()

        # Should unsubscribe from messages (POSITION_UPDATED, TTS_SPEAK, CONTROL_INPUT, TTS_INTERRUPT, ENGINE_STATE, SYSTEM_STATE, PROXIMITY_BEEP, electrical.master_switch)
        assert plugin.context.message_queue.unsubscribe.call_count == 8

        # Should unregister components
        assert plugin.context.plugin_registry.unregister.call_count == 3


class TestAudioPluginConfigUpdate:
    """Test audio plugin configuration updates."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def message_queue(self) -> Mock:
        """Create mock message queue."""
        return Mock()

    @pytest.fixture
    def registry(self) -> Mock:
        """Create mock registry."""
        return Mock()

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: Mock, registry: Mock) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={"audio": {}, "tts": {}},
            plugin_registry=registry,
        )

    @pytest.fixture
    def plugin(self, context: PluginContext) -> AudioPlugin:
        """Create initialized audio plugin."""
        plugin = AudioPlugin()
        plugin.initialize(context)
        return plugin

    def test_config_change_master_volume(self, plugin: AudioPlugin) -> None:
        """Test updating master volume via config."""
        new_config = {"audio": {"master_volume": 0.5}}
        plugin.on_config_changed(new_config)

        # Volume should be updated (can't easily test without mocking internals)
        # Just verify no errors

    def test_config_change_tts_enabled(self, plugin: AudioPlugin) -> None:
        """Test enabling/disabling TTS via config."""
        new_config = {"audio": {"tts_enabled": False}}
        plugin.on_config_changed(new_config)

        # TTS should be disabled (can't easily test without mocking internals)
        # Just verify no errors


class TestAudioPluginInstrumentReadouts:
    """Test audio plugin instrument readout functionality."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def message_queue(self) -> Mock:
        """Create mock message queue."""
        return Mock()

    @pytest.fixture
    def registry(self) -> Mock:
        """Create mock registry."""
        return Mock()

    @pytest.fixture
    def context(self, event_bus: EventBus, message_queue: Mock, registry: Mock) -> PluginContext:
        """Create plugin context."""
        return PluginContext(
            event_bus=event_bus,
            message_queue=message_queue,
            config={"audio": {}, "tts": {}},
            plugin_registry=registry,
        )

    @pytest.fixture
    def plugin(self, context: PluginContext) -> AudioPlugin:
        """Create initialized audio plugin."""
        plugin = AudioPlugin()
        plugin.initialize(context)
        return plugin

    def test_handle_engine_state_message(self, plugin: AudioPlugin) -> None:
        """Test handling ENGINE_STATE messages."""
        message = Message(
            sender="engine_plugin",
            recipients=["*"],
            topic=MessageTopic.ENGINE_STATE,
            data={
                "running": True,
                "rpm": 2300.0,
                "manifold_pressure": 23.5,
                "oil_pressure": 55.0,
                "oil_temp": 85.0,
                "fuel_flow": 8.5,
            },
        )

        plugin.handle_message(message)

        assert plugin._engine_running is True
        assert plugin._engine_rpm == 2300.0
        assert plugin._manifold_pressure == 23.5
        assert plugin._oil_pressure == 55.0
        assert plugin._oil_temp == 85.0
        assert plugin._fuel_flow == 8.5

    def test_handle_electrical_system_state_message(self, plugin: AudioPlugin) -> None:
        """Test handling SYSTEM_STATE messages for electrical system."""
        message = Message(
            sender="electrical_plugin",
            recipients=["*"],
            topic=MessageTopic.SYSTEM_STATE,
            data={
                "system": "electrical",
                "battery_voltage": 12.6,
                "battery_soc_percent": 85.0,
                "battery_current_amps": 15.5,
                "alternator_output_amps": 18.0,
            },
        )

        plugin.handle_message(message)

        assert plugin._battery_voltage == 12.6
        assert plugin._battery_percent == 85.0
        assert plugin._battery_current == 15.5
        assert plugin._alternator_output == 18.0

    def test_handle_fuel_system_state_message(self, plugin: AudioPlugin) -> None:
        """Test handling SYSTEM_STATE messages for fuel system."""
        message = Message(
            sender="fuel_plugin",
            recipients=["*"],
            topic=MessageTopic.SYSTEM_STATE,
            data={
                "system": "fuel",
                "total_quantity_gallons": 35.5,
                "time_remaining_minutes": 240.0,
            },
        )

        plugin.handle_message(message)

        assert plugin._fuel_quantity == 35.5
        assert plugin._fuel_remaining_minutes == 240.0

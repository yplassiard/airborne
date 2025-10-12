"""Audio plugin for the AirBorne flight simulator.

This plugin wraps the audio system (engine and TTS) as a plugin component,
making it available to other plugins through the plugin context.

Typical usage:
    The audio plugin is loaded automatically by the plugin loader and provides
    audio services to other plugins via the component registry.
"""

from typing import Any

from airborne.audio.engine.base import IAudioEngine, Vector3
from airborne.audio.engine.pybass_engine import PyBASSEngine
from airborne.audio.sound_manager import SoundManager
from airborne.audio.tts.base import ITTSProvider
from airborne.audio.tts.pyttsx_provider import PyTTSXProvider
from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType

logger = get_logger(__name__)


class AudioPlugin(IPlugin):
    """Audio plugin that manages audio engine and TTS.

    This plugin wraps the sound manager, audio engine, and TTS provider,
    making them available to other plugins. It subscribes to position
    updates to maintain the 3D audio listener position.

    The plugin provides:
    - audio_engine: IAudioEngine instance
    - sound_manager: SoundManager instance
    - tts: ITTSProvider instance
    """

    def __init__(self) -> None:
        """Initialize audio plugin."""
        self.context: PluginContext | None = None
        self.sound_manager: SoundManager | None = None
        self.audio_engine: IAudioEngine | None = None
        self.tts_provider: ITTSProvider | None = None

        # Listener state
        self._listener_position = Vector3(0.0, 0.0, 0.0)
        self._listener_forward = Vector3(0.0, 0.0, 1.0)
        self._listener_up = Vector3(0.0, 1.0, 0.0)
        self._listener_velocity = Vector3(0.0, 0.0, 0.0)

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata.

        Returns:
            PluginMetadata describing this audio plugin.
        """
        return PluginMetadata(
            name="audio_plugin",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.CORE,
            dependencies=[],
            provides=["audio_engine", "sound_manager", "tts"],
            optional=False,
            update_priority=100,  # Update late (after physics)
            requires_physics=False,
            description="Audio system plugin with 3D audio and TTS",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the audio plugin.

        Args:
            context: Plugin context with access to core systems.
        """
        self.context = context

        # Get audio config from context
        audio_config = context.config.get("audio", {})
        tts_config = context.config.get("tts", {})

        # Create audio engine and TTS provider
        self.audio_engine = PyBASSEngine()
        self.tts_provider = PyTTSXProvider()

        # Create sound manager
        self.sound_manager = SoundManager()
        self.sound_manager.initialize(
            audio_engine=self.audio_engine,
            tts_provider=self.tts_provider,
            audio_config=audio_config,
            tts_config=tts_config,
        )

        # Register components in registry
        if context.plugin_registry:
            context.plugin_registry.register("audio_engine", self.audio_engine)
            context.plugin_registry.register("sound_manager", self.sound_manager)
            context.plugin_registry.register("tts", self.tts_provider)

        # Subscribe to position updates
        context.message_queue.subscribe(MessageTopic.POSITION_UPDATED, self.handle_message)

        logger.info("Audio plugin initialized")

    def update(self, dt: float) -> None:
        """Update audio systems.

        Args:
            dt: Delta time in seconds since last update.
        """
        if not self.sound_manager:
            return

        # Update listener position
        self.sound_manager.update_listener(
            position=self._listener_position,
            forward=self._listener_forward,
            up=self._listener_up,
            velocity=self._listener_velocity,
        )

    def shutdown(self) -> None:
        """Shutdown the audio plugin."""
        if self.context:
            # Unsubscribe from messages
            self.context.message_queue.unsubscribe(
                MessageTopic.POSITION_UPDATED, self.handle_message
            )

            # Unregister components
            if self.context.plugin_registry:
                self.context.plugin_registry.unregister("audio_engine")
                self.context.plugin_registry.unregister("sound_manager")
                self.context.plugin_registry.unregister("tts")

        # Shutdown sound manager (which shutdowns engine and TTS)
        if self.sound_manager:
            self.sound_manager.shutdown()

        logger.info("Audio plugin shutdown")

    def handle_message(self, message: Message) -> None:
        """Handle messages from other plugins.

        Args:
            message: Message from the queue.
        """
        if message.topic == MessageTopic.POSITION_UPDATED:
            # Update listener position from aircraft position
            data = message.data

            if "position" in data:
                pos = data["position"]
                if isinstance(pos, dict):
                    self._listener_position = Vector3(
                        pos.get("x", 0.0), pos.get("y", 0.0), pos.get("z", 0.0)
                    )
                elif isinstance(pos, (tuple, list)) and len(pos) >= 3:
                    self._listener_position = Vector3(float(pos[0]), float(pos[1]), float(pos[2]))

            if "forward" in data:
                fwd = data["forward"]
                if isinstance(fwd, dict):
                    self._listener_forward = Vector3(
                        fwd.get("x", 0.0), fwd.get("y", 0.0), fwd.get("z", 1.0)
                    )
                elif isinstance(fwd, (tuple, list)) and len(fwd) >= 3:
                    self._listener_forward = Vector3(float(fwd[0]), float(fwd[1]), float(fwd[2]))

            if "up" in data:
                up = data["up"]
                if isinstance(up, dict):
                    self._listener_up = Vector3(
                        up.get("x", 0.0), up.get("y", 1.0), up.get("z", 0.0)
                    )
                elif isinstance(up, (tuple, list)) and len(up) >= 3:
                    self._listener_up = Vector3(float(up[0]), float(up[1]), float(up[2]))

            if "velocity" in data:
                vel = data["velocity"]
                if isinstance(vel, dict):
                    self._listener_velocity = Vector3(
                        vel.get("x", 0.0), vel.get("y", 0.0), vel.get("z", 0.0)
                    )
                elif isinstance(vel, (tuple, list)) and len(vel) >= 3:
                    self._listener_velocity = Vector3(float(vel[0]), float(vel[1]), float(vel[2]))

    def on_config_changed(self, config: dict[str, Any]) -> None:
        """Handle configuration changes.

        Args:
            config: New configuration dictionary.
        """
        # Update audio settings if changed
        audio_config = config.get("audio", {})

        if self.sound_manager and "master_volume" in audio_config:
            self.sound_manager.set_master_volume(audio_config["master_volume"])

        if self.sound_manager and "tts_enabled" in audio_config:
            self.sound_manager.set_tts_enabled(audio_config["tts_enabled"])

        if self.tts_provider:
            if "rate" in audio_config:
                self.tts_provider.set_rate(audio_config["rate"])
            if "volume" in audio_config:
                self.tts_provider.set_volume(audio_config["volume"])

        logger.info("Audio plugin configuration updated")

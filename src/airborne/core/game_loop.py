"""Game loop with fixed timestep physics and variable framerate.

This module provides the main game loop that coordinates plugin updates,
message processing, and frame rate management.

Typical usage example:
    from airborne.core.game_loop import GameLoop

    loop = GameLoop(event_bus, message_queue, plugins, target_fps=60)
    loop.run()
"""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class GameLoop:
    """Main game loop with fixed timestep physics.

    Uses a fixed timestep for physics updates (60 Hz) while allowing
    variable framerate rendering. This ensures consistent physics behavior
    regardless of frame rate.

    Examples:
        >>> loop = GameLoop(event_bus, msg_queue, plugins)
        >>> loop.run()  # Starts the main loop
    """

    def __init__(
        self,
        event_bus: Any,
        message_queue: Any,
        plugin_registry: Any,
        target_fps: int = 60,
        physics_hz: int = 60,
    ) -> None:
        """Initialize the game loop.

        Args:
            event_bus: Global event bus.
            message_queue: Message queue for plugin communication.
            plugin_registry: Registry of loaded plugins.
            target_fps: Target frames per second (default: 60).
            physics_hz: Physics update rate in Hz (default: 60).
        """
        self.event_bus = event_bus
        self.message_queue = message_queue
        self.plugin_registry = plugin_registry
        self.target_fps = target_fps
        self.physics_hz = physics_hz

        self.physics_dt = 1.0 / physics_hz
        self.frame_time_target = 1.0 / target_fps

        self.running = False
        self.paused = False

        self.frame_count = 0
        self.physics_accumulator = 0.0

        self.last_time = 0.0
        self.last_fps_time = 0.0
        self.fps = 0.0

    def run(self) -> None:
        """Start the main game loop.

        Runs until stop() is called. Updates physics at fixed rate,
        processes messages, and updates plugins.

        Examples:
            >>> loop = GameLoop(event_bus, msg_queue, plugins)
            >>> loop.run()
        """
        self.running = True
        self.last_time = time.time()
        self.last_fps_time = self.last_time

        logger.info("Game loop started")

        try:
            while self.running:
                self._frame()

        except KeyboardInterrupt:
            logger.info("Game loop interrupted by user")

        except Exception as e:
            logger.error(f"Game loop error: {e}", exc_info=True)
            raise

        finally:
            logger.info("Game loop stopped")

    def _frame(self) -> None:
        """Execute one frame of the game loop."""
        current_time = time.time()
        frame_time = current_time - self.last_time
        self.last_time = current_time

        # Update FPS counter
        if current_time - self.last_fps_time >= 1.0:
            self.fps = self.frame_count / (current_time - self.last_fps_time)
            self.frame_count = 0
            self.last_fps_time = current_time

        if not self.paused:
            # Fixed timestep physics
            self.physics_accumulator += frame_time

            # Clamp accumulator to prevent spiral of death
            max_accumulator = self.physics_dt * 5
            if self.physics_accumulator > max_accumulator:
                logger.warning(f"Physics accumulator clamped: {self.physics_accumulator:.3f}s")
                self.physics_accumulator = max_accumulator

            # Update physics at fixed rate
            while self.physics_accumulator >= self.physics_dt:
                self._update_physics(self.physics_dt)
                self.physics_accumulator -= self.physics_dt

            # Process messages
            self.message_queue.process(max_messages=100)

        # Limit frame rate
        self._limit_framerate()

        self.frame_count += 1

    def _update_physics(self, dt: float) -> None:
        """Update all physics-enabled plugins.

        Args:
            dt: Fixed delta time for physics update.
        """
        # Get plugins sorted by update priority
        plugins = self.plugin_registry.get_plugins_by_priority()

        for plugin_info in plugins:
            if plugin_info.metadata.requires_physics:
                try:
                    plugin_info.plugin.update(dt)
                except Exception as e:
                    logger.error(f"Error updating plugin {plugin_info.metadata.name}: {e}")
                    plugin_info.plugin.on_error(e)

    def _limit_framerate(self) -> None:
        """Sleep to maintain target frame rate."""
        elapsed = time.time() - self.last_time
        sleep_time = self.frame_time_target - elapsed

        if sleep_time > 0:
            time.sleep(sleep_time)

    def stop(self) -> None:
        """Stop the game loop.

        The loop will exit at the end of the current frame.
        """
        self.running = False
        logger.info("Game loop stop requested")

    def pause(self) -> None:
        """Pause physics and plugin updates.

        The loop continues running but skips updates.
        """
        self.paused = True
        logger.info("Game loop paused")

    def resume(self) -> None:
        """Resume physics and plugin updates."""
        self.paused = False
        self.physics_accumulator = 0.0  # Reset to avoid catchup
        logger.info("Game loop resumed")

    def get_fps(self) -> float:
        """Get current frames per second.

        Returns:
            Current FPS.
        """
        return self.fps

    def is_running(self) -> bool:
        """Check if the loop is running.

        Returns:
            True if running, False otherwise.
        """
        return self.running

    def is_paused(self) -> bool:
        """Check if the loop is paused.

        Returns:
            True if paused, False otherwise.
        """
        return self.paused

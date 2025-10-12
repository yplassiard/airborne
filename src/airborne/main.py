"""AirBorne - Blind-Accessible Flight Simulator.

Main entry point for the application. Initializes Pygame, creates the game window,
sets up core systems, and runs the main game loop.

Typical usage:
    uv run python -m airborne.main
"""

import sys

import pygame

from airborne.core.event_bus import EventBus
from airborne.core.game_loop import GameLoop  # noqa: F401
from airborne.core.input import InputActionEvent, InputManager, InputStateEvent  # noqa: F401
from airborne.core.logging_system import get_logger, initialize_logging
from airborne.core.messaging import MessageQueue

logger = get_logger(__name__)


class AirBorne:
    """Main application class for AirBorne flight simulator.

    Manages initialization, game loop, and shutdown of all systems.
    """

    def __init__(self) -> None:
        """Initialize the application."""
        # Initialize logging first
        initialize_logging("config/logging.yaml")
        logger.info("AirBorne starting up...")

        # Initialize Pygame
        pygame.init()
        pygame.display.set_caption("AirBorne - Flight Simulator")

        # Create window
        self.screen = pygame.display.set_mode((800, 600), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.running = True

        # Initialize core systems
        self.event_bus = EventBus()
        self.message_queue = MessageQueue()
        # TODO: Load actual config file when needed
        # self.config = ConfigLoader.load("config/settings.yaml")

        # Initialize input system
        self.input_manager = InputManager(self.event_bus)

        # Subscribe to quit events
        self.event_bus.subscribe(InputActionEvent, self._handle_input_action)

        # Font for debug display
        self.font = pygame.font.SysFont("monospace", 14)
        self.large_font = pygame.font.SysFont("monospace", 32, bold=True)

        # Game state
        self.paused = False
        self.show_debug = True

        # FPS tracking
        self.frame_times: list[float] = []
        self.max_frame_samples = 60

        logger.info("AirBorne initialized successfully")

    def _handle_input_action(self, event: InputActionEvent) -> None:
        """Handle input action events.

        Args:
            event: Input action event.
        """
        if event.action == "quit":
            logger.info("Quit requested")
            self.running = False
        elif event.action == "pause":
            self.paused = not self.paused
            logger.info("Paused: %s", self.paused)

    def run(self) -> None:
        """Run the main game loop."""
        logger.info("Starting main game loop")

        while self.running:
            # Calculate delta time
            dt = self.clock.tick(60) / 1000.0  # Convert ms to seconds
            self._track_frametime(dt)

            # Process events
            self._process_events()

            if not self.paused:
                # Update input
                self.input_manager.update(dt)

                # Update game state
                self._update(dt)

            # Render
            self._render()

            # Update display
            pygame.display.flip()

        self._shutdown()

    def _process_events(self) -> None:
        """Process pygame events."""
        events = pygame.event.get()

        for event in events:
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.VIDEORESIZE:
                self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                logger.debug("Window resized to %dx%d", event.w, event.h)

        # Pass events to input manager
        self.input_manager.process_events(events)

    def _update(self, dt: float) -> None:
        """Update game state.

        Args:
            dt: Delta time in seconds.
        """
        # Process message queue
        self.message_queue.process()

        # TODO: Update plugins, physics, etc.

    def _render(self) -> None:
        """Render the current frame."""
        # Clear screen
        self.screen.fill((0, 0, 0))

        # Draw title
        title_text = self.large_font.render("AirBorne", True, (255, 255, 255))
        title_rect = title_text.get_rect(center=(self.screen.get_width() // 2, 100))
        self.screen.blit(title_text, title_rect)

        # Draw subtitle
        subtitle = self.font.render("Blind-Accessible Flight Simulator", True, (200, 200, 200))
        subtitle_rect = subtitle.get_rect(center=(self.screen.get_width() // 2, 140))
        self.screen.blit(subtitle, subtitle_rect)

        if self.paused:
            # Draw paused indicator
            paused_text = self.large_font.render("PAUSED", True, (255, 255, 0))
            paused_rect = paused_text.get_rect(
                center=(self.screen.get_width() // 2, self.screen.get_height() // 2)
            )
            self.screen.blit(paused_text, paused_rect)

        # Draw debug info
        if self.show_debug:
            self._render_debug_info()

        # Draw instructions
        self._render_instructions()

    def _render_debug_info(self) -> None:
        """Render debug information."""
        y_offset = 10
        line_height = 16

        # FPS
        fps = self.clock.get_fps()
        fps_text = self.font.render(f"FPS: {fps:.1f}", True, (0, 255, 0))
        self.screen.blit(fps_text, (10, y_offset))
        y_offset += line_height

        # Input state
        state = self.input_manager.get_state()
        inputs = [
            f"Pitch: {state.pitch:+.2f}",
            f"Roll: {state.roll:+.2f}",
            f"Yaw: {state.yaw:+.2f}",
            f"Throttle: {state.throttle:.2f}",
            f"Brakes: {state.brakes:.2f}",
            f"Flaps: {state.flaps:.2f}",
            f"Gear: {'DOWN' if state.gear > 0.5 else 'UP'}",
        ]

        for input_line in inputs:
            text = self.font.render(input_line, True, (0, 255, 0))
            self.screen.blit(text, (10, y_offset))
            y_offset += line_height

    def _render_instructions(self) -> None:
        """Render control instructions."""
        instructions = [
            "Controls:",
            "Arrow Keys: Pitch/Roll",
            "A/D: Yaw",
            "+/-: Throttle",
            "G: Gear Toggle",
            "[/]: Flaps",
            "B: Brakes",
            "Pause: Pause",
            "Esc: Quit",
        ]

        y_offset = self.screen.get_height() - len(instructions) * 16 - 10
        x_offset = self.screen.get_width() - 200

        for instruction in instructions:
            text = self.font.render(instruction, True, (150, 150, 150))
            self.screen.blit(text, (x_offset, y_offset))
            y_offset += 16

    def _track_frametime(self, dt: float) -> None:
        """Track frame time for performance monitoring.

        Args:
            dt: Delta time in seconds.
        """
        self.frame_times.append(dt)
        if len(self.frame_times) > self.max_frame_samples:
            self.frame_times.pop(0)

    def _shutdown(self) -> None:
        """Clean shutdown of all systems."""
        logger.info("AirBorne shutting down...")
        pygame.quit()
        logger.info("Shutdown complete")


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success).
    """
    try:
        app = AirBorne()
        app.run()
        return 0
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Fatal error: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())

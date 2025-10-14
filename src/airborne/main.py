"""AirBorne - Blind-Accessible Flight Simulator.

Main entry point for the application. Initializes Pygame, creates the game window,
sets up core systems, and runs the main game loop.

Typical usage:
    uv run python -m airborne.main
"""

import sys
from typing import TYPE_CHECKING

import pygame

from airborne.core.event_bus import EventBus
from airborne.core.game_loop import GameLoop  # noqa: F401
from airborne.core.input import InputActionEvent, InputManager, InputStateEvent  # noqa: F401
from airborne.core.logging_system import get_logger, initialize_logging
from airborne.core.messaging import Message, MessagePriority, MessageQueue, MessageTopic
from airborne.core.plugin import PluginContext
from airborne.core.plugin_loader import PluginLoader
from airborne.core.registry import ComponentRegistry

if TYPE_CHECKING:
    from airborne.aircraft.aircraft import Aircraft
    from airborne.plugins.audio.audio_plugin import AudioPlugin
    from airborne.plugins.core.physics_plugin import PhysicsPlugin

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
        self.registry = ComponentRegistry()

        # Initialize input system
        self.input_manager = InputManager(self.event_bus)

        # Plugin system
        self.plugin_loader = PluginLoader(["src/airborne/plugins"])
        self.plugin_context = PluginContext(
            event_bus=self.event_bus,
            message_queue=self.message_queue,
            config={},  # Will be populated by plugins
            plugin_registry=self.registry,
        )

        # Core plugins
        self.physics_plugin: PhysicsPlugin | None = None
        self.audio_plugin: AudioPlugin | None = None

        # Aircraft
        self.aircraft: Aircraft | None = None

        # Load plugins and aircraft
        self._initialize_plugins()

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

        # Send startup announcement via TTS
        from airborne.audio.tts.speech_messages import MSG_STARTUP

        self.message_queue.publish(
            Message(
                sender="main",
                recipients=["*"],
                topic=MessageTopic.TTS_SPEAK,
                data={
                    "text": MSG_STARTUP,
                    "priority": "high",
                },
                priority=MessagePriority.HIGH,
            )
        )

    def _initialize_plugins(self) -> None:
        """Initialize core plugins and load aircraft."""
        try:
            # Discover available plugins
            logger.info("Discovering plugins...")
            discovered = self.plugin_loader.discover_plugins()
            logger.info("Discovered %d plugins", len(discovered))

            # Load aircraft first to get flight model config
            logger.info("Loading aircraft...")

            # Load aircraft config to get flight model params
            from airborne.aircraft.builder import AircraftBuilder

            aircraft_config_path = "config/aircraft/cessna172.yaml"
            config = AircraftBuilder.load_config(aircraft_config_path)

            # Extract flight model config from aircraft config
            flight_model_config = config.get("aircraft", {}).get("flight_model_config", {})

            # Update plugin context with flight model config
            self.plugin_context.config["physics"] = {
                "flight_model": {"type": "simple_6dof", **flight_model_config}
            }

            # Load physics plugin
            logger.info("Loading physics plugin...")
            from airborne.plugins.core.physics_plugin import PhysicsPlugin

            self.physics_plugin = PhysicsPlugin()
            self.physics_plugin.initialize(self.plugin_context)

            # Load audio plugin
            logger.info("Loading audio plugin...")
            from airborne.plugins.audio.audio_plugin import AudioPlugin

            self.audio_plugin = AudioPlugin()
            self.audio_plugin.initialize(self.plugin_context)

            # Load autopilot plugin
            logger.info("Loading autopilot plugin...")
            from airborne.plugins.avionics.autopilot_plugin import AutopilotPlugin

            self.autopilot_plugin = AutopilotPlugin()
            self.autopilot_plugin.initialize(self.plugin_context)

            # Build aircraft with systems
            builder = AircraftBuilder(self.plugin_loader, self.plugin_context)
            self.aircraft = builder.build(aircraft_config_path)

            logger.info("All plugins and aircraft loaded successfully")

        except Exception as e:
            logger.error("Failed to initialize plugins: %s", e)
            raise

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
            self.message_queue.publish(
                Message(
                    sender="main",
                    recipients=["*"],
                    topic=MessageTopic.TTS_SPEAK,
                    data={"text": "Paused" if self.paused else "Resumed", "priority": "high"},
                    priority=MessagePriority.HIGH,
                )
            )
        elif event.action == "gear_toggle":
            state = self.input_manager.get_state()
            gear_status = "down" if state.gear > 0.5 else "up"
            self.message_queue.publish(
                Message(
                    sender="main",
                    recipients=["*"],
                    topic=MessageTopic.TTS_SPEAK,
                    data={"text": f"Gear {gear_status}", "priority": "normal"},
                    priority=MessagePriority.NORMAL,
                )
            )
        # ATC Menu controls
        elif event.action == "atc_menu":
            # Send to radio plugin
            self.message_queue.publish(
                Message(
                    sender="main",
                    recipients=["radio_plugin"],
                    topic="input.atc_menu",
                    data={"action": "toggle"},
                    priority=MessagePriority.HIGH,
                )
            )
            # TTS feedback (menu will speak its own content)
            logger.debug("ATC menu toggled")
        elif event.action == "atc_acknowledge":
            self.message_queue.publish(
                Message(
                    sender="main",
                    recipients=["radio_plugin"],
                    topic="input.atc_acknowledge",
                    data={},
                    priority=MessagePriority.HIGH,
                )
            )
        elif event.action == "atc_repeat":
            self.message_queue.publish(
                Message(
                    sender="main",
                    recipients=["radio_plugin"],
                    topic="input.atc_repeat",
                    data={},
                    priority=MessagePriority.HIGH,
                )
            )
        # ATC menu selection (number keys 1-9)
        elif event.action.startswith("atc_select_"):
            option = event.action.split("_")[-1]  # Extract number
            # Send to radio plugin (menu will provide its own TTS feedback)
            self.message_queue.publish(
                Message(
                    sender="main",
                    recipients=["radio_plugin"],
                    topic="input.atc_menu",
                    data={"action": "select", "option": option},
                    priority=MessagePriority.HIGH,
                )
            )
        # ESC closes ATC menu
        elif event.action == "menu_back":
            # Send to radio plugin (menu will provide its own TTS feedback)
            self.message_queue.publish(
                Message(
                    sender="main",
                    recipients=["radio_plugin"],
                    topic="input.atc_menu",
                    data={"action": "close"},
                    priority=MessagePriority.HIGH,
                )
            )

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
        # Send control inputs to physics
        self._send_control_inputs()

        # Update physics plugin
        if self.physics_plugin:
            self.physics_plugin.update(dt)

        # Update aircraft systems
        if self.aircraft:
            self.aircraft.update(dt)

        # Update autopilot
        if hasattr(self, "autopilot_plugin") and self.autopilot_plugin:
            self.autopilot_plugin.update(dt)

        # Update audio plugin
        if self.audio_plugin:
            self.audio_plugin.update(dt)

        # Process message queue
        self.message_queue.process()

    def _send_control_inputs(self) -> None:
        """Send control inputs to physics plugin."""
        if not self.physics_plugin:
            return

        # Get current input state
        state = self.input_manager.get_state()

        # Publish control input message
        self.message_queue.publish(
            Message(
                sender="main",
                recipients=["physics_plugin"],
                topic=MessageTopic.CONTROL_INPUT,
                data={
                    "pitch": state.pitch,
                    "roll": state.roll,
                    "yaw": state.yaw,
                    "throttle": state.throttle,
                    "flaps": state.flaps,
                    "brakes": state.brakes,
                    "gear": state.gear,
                },
                priority=MessagePriority.HIGH,
            )
        )

    def _render(self) -> None:
        """Render the current frame."""
        # Clear screen
        self.screen.fill((0, 0, 0))

        # Draw title
        title_text = self.large_font.render("AirBorne", True, (255, 255, 255))
        title_rect = title_text.get_rect(center=(self.screen.get_width() // 2, 50))
        self.screen.blit(title_text, title_rect)

        # Draw subtitle
        subtitle = self.font.render("Blind-Accessible Flight Simulator", True, (200, 200, 200))
        subtitle_rect = subtitle.get_rect(center=(self.screen.get_width() // 2, 80))
        self.screen.blit(subtitle, subtitle_rect)

        # Draw flight instruments (central display)
        self._render_flight_instruments()

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

    def _render_flight_instruments(self) -> None:
        """Render primary flight instruments in center of screen."""
        if not self.physics_plugin or not self.physics_plugin.flight_model:
            return

        flight_state = self.physics_plugin.flight_model.get_state()
        center_x = self.screen.get_width() // 2
        center_y = self.screen.get_height() // 2

        # Convert to aviation units
        airspeed_kts = flight_state.get_airspeed() * 1.94384  # m/s to knots
        altitude_ft = flight_state.position.y * 3.28084  # meters to feet
        vertical_speed_fpm = flight_state.velocity.y * 196.85  # m/s to feet per minute

        # Primary instruments (large, centered)
        instruments = [
            f"AIRSPEED: {airspeed_kts:>6.0f} KTS",
            f"ALTITUDE: {altitude_ft:>6.0f} FT",
            f"VS: {vertical_speed_fpm:>+7.0f} FPM",
        ]

        # Render instruments
        y_offset = center_y - 50
        for instrument in instruments:
            text = self.large_font.render(instrument, True, (0, 255, 0))
            text_rect = text.get_rect(center=(center_x, y_offset))
            self.screen.blit(text, text_rect)
            y_offset += 40

        # Control inputs (smaller, below instruments)
        state = self.input_manager.get_state()
        controls = [
            f"Throttle: {state.throttle * 100:>3.0f}%  Flaps: {state.flaps * 100:>3.0f}%",
            f"Gear: {'DOWN' if state.gear > 0.5 else 'UP  '}    "
            f"Brakes: {'ON' if state.brakes > 0.1 else 'OFF'}",
        ]

        y_offset += 20
        for control in controls:
            text = self.font.render(control, True, (200, 200, 0))
            text_rect = text.get_rect(center=(center_x, y_offset))
            self.screen.blit(text, text_rect)
            y_offset += 20

    def _render_debug_info(self) -> None:
        """Render debug information."""
        y_offset = 10
        line_height = 16

        # FPS
        fps = self.clock.get_fps()
        fps_text = self.font.render(f"FPS: {fps:.1f}", True, (0, 255, 0))
        self.screen.blit(fps_text, (10, y_offset))
        y_offset += line_height

        # Aircraft info
        if self.aircraft:
            aircraft_text = self.font.render(f"Aircraft: {self.aircraft.name}", True, (0, 255, 255))
            self.screen.blit(aircraft_text, (10, y_offset))
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

        # Physics state
        if self.physics_plugin and self.physics_plugin.flight_model:
            flight_state = self.physics_plugin.flight_model.get_state()
            physics_info = [
                "",  # Blank line
                "FLIGHT STATE:",
                f"Pos: ({flight_state.position.x:.1f}, {flight_state.position.y:.1f}, {flight_state.position.z:.1f})",
                f"Vel: {flight_state.get_airspeed():.1f} m/s",
                f"Alt: {flight_state.position.y:.1f} m",
                f"Mass: {flight_state.mass:.0f} kg",
            ]

            for info_line in physics_info:
                text = self.font.render(info_line, True, (255, 255, 0))
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

        # Shutdown aircraft
        if self.aircraft:
            logger.info("Shutting down aircraft...")
            self.aircraft.shutdown()

        # Shutdown plugins
        if hasattr(self, "autopilot_plugin") and self.autopilot_plugin:
            logger.info("Shutting down autopilot plugin...")
            self.autopilot_plugin.shutdown()

        if self.audio_plugin:
            logger.info("Shutting down audio plugin...")
            self.audio_plugin.shutdown()

        if self.physics_plugin:
            logger.info("Shutting down physics plugin...")
            self.physics_plugin.shutdown()

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

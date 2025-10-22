"""AirBorne - Blind-Accessible Flight Simulator.

Main entry point for the application. Initializes Pygame, creates the game window,
sets up core systems, and runs the main game loop.

Typical usage:
    uv run python -m airborne.main
    uv run python -m airborne.main --from-airport KPAO
    uv run python -m airborne.main --from-airport KPAO --to-airport KSFO
"""

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pygame

from airborne.adapters import (
    ChecklistMenuInputHandler,
    ControlPanelInputHandler,
    MenuInputHandler,
)
from airborne.core.event_bus import EventBus
from airborne.core.game_loop import GameLoop  # noqa: F401
from airborne.core.input import InputActionEvent, InputManager, InputStateEvent  # noqa: F401
from airborne.core.input_config import InputConfig
from airborne.core.input_event import InputEvent
from airborne.core.input_handler_manager import InputHandlerManager
from airborne.core.logging_system import get_logger, initialize_logging
from airborne.core.messaging import Message, MessagePriority, MessageQueue, MessageTopic
from airborne.core.plugin import PluginContext
from airborne.core.plugin_loader import PluginLoader
from airborne.core.registry import ComponentRegistry
from airborne.core.resource_path import (
    get_asset_path,
    get_config_path,
    get_data_path,
    get_plugin_dir,
    get_resource_path,
)

if TYPE_CHECKING:
    from airborne.aircraft.aircraft import Aircraft
    from airborne.plugins.audio.audio_plugin import AudioPlugin
    from airborne.plugins.core.physics_plugin import PhysicsPlugin

logger = get_logger(__name__)


class AirBorne:
    """Main application class for AirBorne flight simulator.

    Manages initialization, game loop, and shutdown of all systems.
    """

    def __init__(self, args: argparse.Namespace | None = None) -> None:
        """Initialize the application.

        Args:
            args: Command line arguments (optional)
        """
        # Store CLI arguments
        self.args = args or argparse.Namespace(from_airport=None, to_airport=None, callsign=None)

        # Initialize logging first (use platform-specific directories)
        logging_config = get_config_path("logging.yaml")
        if logging_config.exists():
            initialize_logging(str(logging_config), use_platform_dir=True)
        else:
            # Fall back to default config if file not found
            initialize_logging(use_platform_dir=True)
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

        # Initialize input system (with message queue for inter-plugin communication)
        self.input_manager = InputManager(self.event_bus, message_queue=self.message_queue)

        # Initialize new input handler system
        input_bindings_dir = get_config_path("input_bindings")
        self.input_config = InputConfig.load_from_directory(str(input_bindings_dir))
        self.input_handler_manager = InputHandlerManager()
        logger.info("Input handler system initialized")

        # Plugin system
        self.plugin_loader = PluginLoader([str(get_plugin_dir())])
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

        # Initialize navigation and scenario systems
        self._initialize_navigation_systems()

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

    def _initialize_navigation_systems(self) -> None:
        """Initialize navigation, aviation, and scenario systems."""
        from airborne.airports.database import AirportDatabase
        from airborne.aviation import CallsignGenerator
        from airborne.scenario import ScenarioBuilder, SpawnLocation, SpawnManager

        logger.info("Initializing navigation systems...")

        # Load airport database
        self.airport_db = AirportDatabase()
        self.airport_db.load_from_csv(str(get_data_path("airports")))
        logger.info(f"Loaded {len(self.airport_db.airports)} airports")

        # Initialize callsign generator
        self.callsign_gen = CallsignGenerator(
            callsigns_file=str(get_data_path("aviation/callsigns.yaml"))
        )

        # Create scenario from CLI args or default
        if self.args.from_airport:
            airport_icao = self.args.from_airport.upper()
            logger.info(f"Using departure airport from CLI: {airport_icao}")
        else:
            # Default to Palo Alto
            airport_icao = "KPAO"
            logger.info(f"Using default departure airport: {airport_icao}")

        # Generate or use provided callsign
        if self.args.callsign:
            callsign = self.args.callsign
        else:
            callsign_obj = self.callsign_gen.generate_ga_callsign("N")
            callsign = callsign_obj.full

        # Build scenario
        self.scenario = (
            ScenarioBuilder()
            .with_airport(airport_icao)
            .with_spawn_location(SpawnLocation.RAMP)
            .with_callsign(callsign)
            .build()
        )

        logger.info(
            f"Scenario created: {callsign} at {airport_icao} ({self.scenario.spawn_location.value})"
        )

        # Create spawn manager and get spawn state
        spawn_manager = SpawnManager(self.airport_db)
        try:
            self.spawn_state = spawn_manager.spawn_aircraft(self.scenario)
            logger.info(
                f"Spawn position: {self.spawn_state.position}, "
                f"heading: {self.spawn_state.heading:.0f}°"
            )
        except ValueError as e:
            logger.error(f"Failed to spawn aircraft: {e}")
            # Fall back to default position
            self.spawn_state = None
            logger.warning("Using default spawn position")

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

            aircraft_config_path = str(get_config_path("aircraft/cessna172.yaml"))
            config = AircraftBuilder.load_config(aircraft_config_path)

            # Extract flight model config from aircraft config
            flight_model_config = config.get("aircraft", {}).get("flight_model_config", {})

            # Update plugin context with flight model config
            self.plugin_context.config["physics"] = {
                "flight_model": {"type": "simple_6dof", **flight_model_config}
            }

            # Extract audio config from aircraft config
            audio_config = config.get("aircraft", {}).get("audio", {})
            if audio_config:
                # Merge with existing audio config (if any)
                if "audio" not in self.plugin_context.config:
                    self.plugin_context.config["audio"] = {}
                self.plugin_context.config["audio"]["aircraft"] = audio_config

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
            # Register audio plugin so other plugins can access it
            self.plugin_context.plugin_registry.register("audio_plugin", self.audio_plugin)

            # Load autopilot plugin
            logger.info("Loading autopilot plugin...")
            from airborne.plugins.avionics.autopilot_plugin import AutopilotPlugin

            self.autopilot_plugin = AutopilotPlugin()
            self.autopilot_plugin.initialize(self.plugin_context)

            # Load radio plugin
            logger.info("Loading radio plugin...")
            from airborne.plugins.radio.radio_plugin import RadioPlugin

            self.radio_plugin = RadioPlugin()
            self.radio_plugin.initialize(self.plugin_context)

            # Load control panel plugin
            logger.info("Loading control panel plugin...")
            from airborne.plugins.panel.control_panel_plugin import ControlPanelPlugin

            self.control_panel_plugin = ControlPanelPlugin()
            # Configure panel definition file
            self.plugin_context.config["panels"] = {
                "definition": str(get_config_path("panels/cessna172_panel.yaml"))
            }
            self.control_panel_plugin.initialize(self.plugin_context)

            # Load checklist plugin
            logger.info("Loading checklist plugin...")
            from airborne.plugins.checklist.checklist_plugin import ChecklistPlugin

            self.checklist_plugin = ChecklistPlugin()
            # Configure checklist directory
            self.plugin_context.config["checklists"] = {
                "directory": str(get_config_path("checklists"))
            }
            self.checklist_plugin.initialize(self.plugin_context)

            # Load ground services plugin
            logger.info("Loading ground services plugin...")
            from airborne.plugins.ground.ground_services_plugin import GroundServicesPlugin

            self.ground_services_plugin = GroundServicesPlugin()
            # Configure airport category
            self.plugin_context.config["airport"] = {"category": "MEDIUM"}
            self.ground_services_plugin.initialize(self.plugin_context)

            # Load weight and balance plugin
            logger.info("Loading weight and balance plugin...")
            from airborne.plugins.weight.weight_balance_plugin import WeightBalancePlugin

            self.weight_balance_plugin = WeightBalancePlugin()
            self.weight_balance_plugin.initialize(self.plugin_context)

            # Build aircraft with systems
            builder = AircraftBuilder(self.plugin_loader, self.plugin_context)
            self.aircraft = builder.build(aircraft_config_path)

            logger.info("All plugins and aircraft loaded successfully")

            # Initialize input handlers with loaded plugins
            self._initialize_input_handlers()

        except Exception as e:
            logger.error("Failed to initialize plugins: %s", e)
            raise

    def _initialize_input_handlers(self) -> None:
        """Initialize and register input handlers with priority-based dispatch."""
        logger.info("Registering input handlers...")

        # Register checklist menu handler (priority 10 - highest)
        if (
            hasattr(self, "checklist_plugin")
            and self.checklist_plugin
            and self.checklist_plugin.checklist_menu
        ):
            checklist_handler = ChecklistMenuInputHandler(
                menu=self.checklist_plugin.checklist_menu,
                name="checklist_menu",
                priority=self.input_config.get_handler_priority("checklist_menu"),
            )
            self.input_handler_manager.register(checklist_handler)
            logger.info("Registered checklist menu handler")

        # Register ATC menu handler (priority 20)
        if hasattr(self, "radio_plugin") and self.radio_plugin and self.radio_plugin.atc_menu:
            atc_handler = MenuInputHandler(
                menu=self.radio_plugin.atc_menu,
                name="atc_menu",
                priority=self.input_config.get_handler_priority("atc_menu"),
            )
            self.input_handler_manager.register(atc_handler)
            logger.info("Registered ATC menu handler")

        # Register ground services menu handler (priority 30)
        if (
            hasattr(self, "ground_services_plugin")
            and self.ground_services_plugin
            and self.ground_services_plugin.ground_services_menu
        ):
            ground_handler = MenuInputHandler(
                menu=self.ground_services_plugin.ground_services_menu,
                name="ground_services_menu",
                priority=self.input_config.get_handler_priority("ground_services_menu"),
            )
            self.input_handler_manager.register(ground_handler)
            logger.info("Registered ground services menu handler")

        # Register control panel handler (priority 100)
        if hasattr(self, "control_panel_plugin") and self.control_panel_plugin:
            panel_handler = ControlPanelInputHandler(
                control_panel=self.control_panel_plugin,
                name="control_panel",
                priority=self.input_config.get_handler_priority("control_panel"),
            )
            self.input_handler_manager.register(panel_handler)
            logger.info("Registered control panel handler")

        logger.info(
            f"Input handler registration complete: {self.input_handler_manager.get_handler_count()} handlers registered"
        )

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
        # Control key stops cockpit TTS
        elif event.action == "tts_interrupt":
            # Stop TTS via message queue
            self.message_queue.publish(
                Message(
                    sender="main",
                    recipients=["*"],
                    topic=MessageTopic.TTS_INTERRUPT,
                    data={},
                    priority=MessagePriority.HIGH,
                )
            )
        # Checklist menu controls
        elif event.action == "checklist_menu":
            # Send to checklist plugin
            self.message_queue.publish(
                Message(
                    sender="main",
                    recipients=["checklist_plugin"],
                    topic="input.checklist_menu",
                    data={"action": "toggle"},
                    priority=MessagePriority.HIGH,
                )
            )
        # Ground services menu controls
        elif event.action == "ground_services_menu":
            # Send to ground services plugin
            logger.info("F3 pressed - publishing ground_services_menu message")
            self.message_queue.publish(
                Message(
                    sender="main",
                    recipients=["ground_services_plugin"],
                    topic="input.ground_services_menu",
                    data={"action": "toggle"},
                    priority=MessagePriority.HIGH,
                )
            )

    def run(self) -> None:
        """Run the main game loop."""
        logger.info("Starting main game loop")

        while self.running:
            # Calculate delta time
            dt = self.clock.tick(240) / 1000.0  # 240 FPS - Convert ms to seconds
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
        """Process pygame events using new input handler system."""
        events = pygame.event.get()
        remaining_events = []

        for event in events:
            if event.type == pygame.QUIT:
                self.running = False
                remaining_events.append(event)
            elif event.type == pygame.VIDEORESIZE:
                self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                logger.debug("Window resized to %dx%d", event.w, event.h)
                remaining_events.append(event)
            elif event.type == pygame.KEYDOWN:
                # Convert pygame event to InputEvent
                input_event = InputEvent.from_keyboard(key=event.key, mods=pygame.key.get_mods())

                # Dispatch through handler manager (priority-based)
                handled = self.input_handler_manager.process_input(input_event)

                # If not handled, add to remaining events
                if not handled:
                    remaining_events.append(event)
            else:
                remaining_events.append(event)

        # Pass remaining events to input manager
        self.input_manager.process_events(remaining_events)

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

        # Update radio plugin
        if hasattr(self, "radio_plugin") and self.radio_plugin:
            self.radio_plugin.update(dt)

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

        if hasattr(self, "radio_plugin") and self.radio_plugin:
            logger.info("Shutting down radio plugin...")
            self.radio_plugin.shutdown()

        if self.audio_plugin:
            logger.info("Shutting down audio plugin...")
            self.audio_plugin.shutdown()

        if self.physics_plugin:
            logger.info("Shutting down physics plugin...")
            self.physics_plugin.shutdown()

        pygame.quit()
        logger.info("Shutdown complete")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(description="AirBorne - Blind-Accessible Flight Simulator")

    parser.add_argument(
        "--from-airport",
        type=str,
        help="Departure airport ICAO code (e.g., KPAO, KSFO)",
    )

    parser.add_argument(
        "--to-airport",
        type=str,
        help="Destination airport ICAO code (e.g., KSFO, KLAX)",
    )

    parser.add_argument(
        "--callsign",
        type=str,
        help="Aircraft callsign (e.g., N12345, Cessna 123)",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success).
    """
    try:
        args = parse_args()
        app = AirBorne(args)
        app.run()
        return 0
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Fatal error: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())

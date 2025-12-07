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
    get_config_path,
    get_data_path,
    get_plugin_dir,
)

if TYPE_CHECKING:
    from airborne.aircraft.aircraft import Aircraft
    from airborne.audio.tts_service import TTSService
    from airborne.plugins.audio.audio_plugin import AudioPlugin
    from airborne.plugins.core.physics_plugin import PhysicsPlugin

logger = get_logger(__name__)


class AirBorne:
    """Main application class for AirBorne flight simulator.

    Manages initialization, game loop, and shutdown of all systems.
    """

    def __init__(
        self,
        args: argparse.Namespace | None = None,
        tts_service: "TTSService | None" = None,
    ) -> None:
        """Initialize the application.

        Args:
            args: Command line arguments (optional)
            tts_service: Shared TTSService instance (optional)
        """
        # Store CLI arguments
        self.args = args or argparse.Namespace(
            from_airport=None, to_airport=None, callsign=None, tts=None
        )

        # Store shared TTS service
        self.tts_service = tts_service

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

        # Register TTS service in registry if provided
        if self.tts_service:
            self.registry.register("tts_service", self.tts_service)

        # Initialize input system (will be updated with aircraft config after loading)
        self.input_manager = InputManager(self.event_bus, message_queue=self.message_queue)

        # Subscribe to context push/pop messages for input context management
        self.message_queue.subscribe("input.context.push", self._handle_context_push)
        self.message_queue.subscribe("input.context.pop", self._handle_context_pop)

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

        # Publish initial parking status to ground services plugin
        self._publish_initial_parking_status()

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
        from airborne.core.i18n import t

        self.message_queue.publish(
            Message(
                sender="main",
                recipients=["*"],
                topic=MessageTopic.TTS_SPEAK,
                data={
                    "text": t("system.startup"),
                    "priority": "high",
                },
                priority=MessagePriority.HIGH,
            )
        )

    def _initialize_navigation_systems(self) -> None:
        """Initialize navigation, aviation, and scenario systems."""
        from airborne.airports.database import AirportDatabase
        from airborne.aviation import CallsignGenerator
        from airborne.scenario import EngineState, ScenarioBuilder, SpawnLocation, SpawnManager
        from airborne.services.weather import WeatherService

        logger.info("Initializing navigation systems...")

        # Initialize weather service and start background METAR fetch
        self.weather_service = WeatherService()

        # Airport database (loads airports on-demand from X-Plane Gateway)
        self.airport_db = AirportDatabase()

        # Initialize callsign generator
        self.callsign_gen = CallsignGenerator(
            callsigns_file=str(get_data_path("aviation/callsigns.yaml"))
        )

        # Get flight config from menu or use defaults
        flight_config = getattr(self.args, "flight_config", {})

        # Create scenario from CLI args or menu config
        if self.args.from_airport:
            airport_icao = self.args.from_airport.upper()
            logger.info(f"Using departure airport: {airport_icao}")
        else:
            # Default to Palo Alto
            airport_icao = "KPAO"
            logger.info(f"Using default departure airport: {airport_icao}")

        # Store departure airport for later use (e.g., radio plugin)
        self.departure_airport_icao = airport_icao

        # Start background METAR fetch for departure airport (non-blocking)
        self.weather_service.prefetch_weather(airport_icao)

        # Generate or use provided callsign
        if self.args.callsign:
            callsign = self.args.callsign
        else:
            # Generate callsign based on departure airport country
            country_prefix = self._get_country_prefix_from_icao(airport_icao)
            callsign_obj = self.callsign_gen.generate_ga_callsign(country_prefix)
            callsign = callsign_obj.full

        # Get settings from flight config
        spawn_location = flight_config.get("initial_position", SpawnLocation.RAMP)
        engine_state = flight_config.get("initial_state", EngineState.COLD_AND_DARK)
        arrival_icao = flight_config.get("arrival")
        circuit_training = flight_config.get("circuit_training", False)
        fuel_gallons = flight_config.get("fuel_gallons")
        passenger_count = flight_config.get("passengers", 0)

        # Build scenario with all settings
        builder = (
            ScenarioBuilder()
            .with_airport(airport_icao)
            .with_spawn_location(spawn_location)
            .with_engine_state(engine_state)
            .with_callsign(callsign)
            .with_circuit_training(circuit_training)
            .with_passengers(passenger_count)
        )

        if arrival_icao:
            builder = builder.with_arrival(arrival_icao)
        if fuel_gallons is not None:
            builder = builder.with_fuel(fuel_gallons)

        self.scenario = builder.build()

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

        # Update plugin context with scenario and spawn state
        # This makes scenario values available to all plugins during initialization
        self.plugin_context.scenario = self.scenario
        self.plugin_context.spawn_state = self.spawn_state

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

            # Extract propeller config from aircraft section (not physics!)
            propeller_config = config.get("aircraft", {}).get("propeller", {})

            # Update plugin context with flight model config
            self.plugin_context.config["physics"] = {
                "flight_model": {"type": "simple_6dof", **flight_model_config}
            }

            # Add propeller config if present
            if propeller_config:
                self.plugin_context.config["propeller"] = propeller_config
                logger.info(f"Propeller config loaded: {propeller_config.get('type', 'unknown')}")

            # Extract audio config from aircraft config
            audio_config = config.get("aircraft", {}).get("audio", {})
            if audio_config:
                # Merge with existing audio config (if any)
                if "audio" not in self.plugin_context.config:
                    self.plugin_context.config["audio"] = {}
                self.plugin_context.config["audio"]["aircraft"] = audio_config

            # Load TTS settings from saved settings
            if "tts" not in self.plugin_context.config:
                self.plugin_context.config["tts"] = {}

            from airborne.settings import get_tts_settings

            tts_settings = get_tts_settings()
            saved_language = tts_settings.language

            # Apply saved language to i18n system (critical for --skip-menu)
            from airborne.core.i18n import set_language

            set_language(saved_language)

            self.plugin_context.config["tts"]["language"] = saved_language
            logger.info(f"TTS settings loaded: language={saved_language}")

            # Extract aircraft characteristics (fixed_gear, etc.) and performance config
            aircraft_info = config.get("aircraft", {})
            fixed_gear = aircraft_info.get("fixed_gear", False)
            performance_config = aircraft_info.get("performance", {})
            weight_balance_config = aircraft_info.get("weight_balance", {})

            self.plugin_context.config["aircraft"] = {
                "fixed_gear": fixed_gear,
                "performance": performance_config,
                "weight_balance": weight_balance_config,
            }
            logger.info(f"Aircraft configuration: fixed_gear={fixed_gear}")

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

            # Add radio config with departure airport and weather service
            # Extract aircraft type from config filename (e.g., "cessna172" from "cessna172.yaml")
            aircraft_type_id = Path(aircraft_config_path).stem
            self.plugin_context.config["radio"] = {
                "callsign": self.scenario.callsign,
                "aircraft_type": aircraft_type_id,
                "departure_airport": self.departure_airport_icao,
                "weather_service": self.weather_service,
            }

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

            # Load performance display plugin (FMC/PFD) - after weight & balance
            logger.info("Loading performance display plugin...")
            from airborne.plugins.performance.performance_display_plugin import (
                PerformanceDisplayPlugin,
            )

            self.performance_display_plugin = PerformanceDisplayPlugin()
            self.performance_display_plugin.initialize(self.plugin_context)

            # Load flight instructor plugin
            logger.info("Loading flight instructor plugin...")
            from airborne.plugins.training.flight_instructor_plugin import FlightInstructorPlugin

            self.flight_instructor_plugin = FlightInstructorPlugin()
            self.flight_instructor_plugin.initialize(self.plugin_context)

            # Build aircraft with systems
            builder = AircraftBuilder(self.plugin_loader, self.plugin_context)
            self.aircraft = builder.build(aircraft_config_path)

            logger.info("All plugins and aircraft loaded successfully")

            # Update InputManager with aircraft configuration
            self.input_manager.aircraft_config = self.plugin_context.config.get("aircraft", {})
            self.input_manager.fixed_gear = self.input_manager.aircraft_config.get(
                "fixed_gear", False
            )
            logger.info(
                f"InputManager updated with aircraft config: fixed_gear={self.input_manager.fixed_gear}"
            )

            # Reinitialize context manager with aircraft-specific keybindings
            # This applies user-defined key binding overrides for this aircraft
            aircraft_type_for_keybindings = Path(aircraft_config_path).stem
            self.input_manager.reinitialize_context_manager(aircraft_type_for_keybindings)

            # Initialize input handlers with loaded plugins
            self._initialize_input_handlers()

        except Exception as e:
            logger.error("Failed to initialize plugins: %s", e)
            raise

    def _get_country_prefix_from_icao(self, airport_icao: str) -> str:
        """Get aircraft registration country prefix from airport ICAO code.

        Maps ICAO airport prefixes to aircraft registration prefixes:
        - K (USA) -> N
        - EG (UK) -> G
        - LF (France) -> F
        - ED (Germany) -> D
        - etc.

        Args:
            airport_icao: Airport ICAO code (e.g., "KPAO", "EGLL", "LFLY")

        Returns:
            Country registration prefix (e.g., "N" for US, "G" for UK)
        """
        icao_upper = airport_icao.upper()

        # Map ICAO airport prefixes to registration country prefixes
        icao_to_registration = {
            "K": "N",  # USA
            "P": "N",  # Pacific (USA)
            "EG": "G",  # UK
            "LF": "F",  # France
            "ED": "D",  # Germany
            "LE": "EC",  # Spain
            "LI": "I",  # Italy
            "EH": "PH",  # Netherlands
            "EB": "OO",  # Belgium
            "LS": "HB",  # Switzerland
            "LO": "OE",  # Austria
            "EK": "OY",  # Denmark
            "EN": "LN",  # Norway
            "ES": "SE",  # Sweden
            "EF": "OH",  # Finland
            "CY": "C",  # Canada
            "VH": "VH",  # Australia
            "ZK": "ZK",  # New Zealand
        }

        # Try 2-letter prefix first (more specific), then 1-letter
        for prefix_len in [2, 1]:
            if len(icao_upper) >= prefix_len:
                prefix = icao_upper[:prefix_len]
                if prefix in icao_to_registration:
                    return icao_to_registration[prefix]

        # Default to US registration if unknown
        return "N"

    def _publish_initial_parking_status(self) -> None:
        """Publish initial parking status based on spawn state.

        This notifies the ground services plugin whether we're at a parking spot
        so the F3 ground services menu works immediately after spawn.
        """
        if not self.spawn_state:
            logger.debug("No spawn state, not publishing parking status")
            return

        at_parking = self.spawn_state.at_parking
        parking_id = self.spawn_state.parking_id

        logger.info(
            "Publishing initial parking status: at_parking=%s, parking_id=%s",
            at_parking,
            parking_id,
        )

        self.message_queue.publish(
            Message(
                sender="main",
                recipients=["ground_services_plugin"],
                topic="parking.status",
                data={
                    "at_parking": at_parking,
                    "parking_id": parking_id,
                },
                priority=MessagePriority.NORMAL,
            )
        )

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

        # Register performance display handler (F4 key, priority 50)
        if hasattr(self, "performance_display_plugin") and self.performance_display_plugin:
            from airborne.plugins.performance.performance_display_plugin import (
                PerformanceDisplayInputHandler,
            )

            perf_handler = PerformanceDisplayInputHandler(
                display=self.performance_display_plugin.display
            )
            self.input_handler_manager.register(perf_handler)
            logger.info("Registered performance display handler (F4 key)")

        logger.info(
            f"Input handler registration complete: {self.input_handler_manager.get_handler_count()} handlers registered"
        )

    def _handle_context_push(self, message: Message) -> None:
        """Handle input context push request.

        Args:
            message: Message with context name in data["context"].
        """
        context_name = message.data.get("context")
        if context_name and self.input_manager.context_manager:
            self.input_manager.context_manager.push_context(context_name)
            logger.debug(f"Pushed input context: {context_name}")

    def _handle_context_pop(self, message: Message) -> None:
        """Handle input context pop request.

        Args:
            message: Message requesting context pop.
        """
        if self.input_manager.context_manager:
            self.input_manager.context_manager.pop_context()
            logger.debug("Popped input context")

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
        # ATC Menu controls (toggle_atc_menu from context system)
        elif event.action in ("atc_menu", "toggle_atc_menu"):
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
        # Push-to-talk for ATC voice control
        elif event.action == "push_to_talk":
            self.message_queue.publish(
                Message(
                    sender="main",
                    recipients=["radio_plugin"],
                    topic="input.push_to_talk",
                    data={"pressed": True},
                    priority=MessagePriority.HIGH,
                )
            )
        # ATC V2 text input (Shift+Space)
        elif event.action == "atc_v2_text_input":
            self.message_queue.publish(
                Message(
                    sender="main",
                    recipients=["radio_plugin"],
                    topic="input.atc_v2_text_input",
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
        # Checklist menu controls (toggle_checklist_menu from context system)
        elif event.action in ("checklist_menu", "toggle_checklist_menu"):
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
        # Ground services menu controls (toggle_ground_services_menu from context system)
        elif event.action in ("ground_services_menu", "toggle_ground_services_menu"):
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
                # Check if radio plugin text input dialog is active
                if (
                    hasattr(self, "radio_plugin")
                    and self.radio_plugin
                    and self.radio_plugin.is_text_input_active()
                ):
                    # Route to text input dialog
                    mods = pygame.key.get_mods()
                    if self.radio_plugin.handle_text_input_key(event.key, event.unicode, mods):
                        continue  # Key consumed by dialog

                # Convert pygame event to InputEvent
                input_event = InputEvent.from_keyboard(key=event.key, mods=pygame.key.get_mods())

                # Dispatch through handler manager (priority-based)
                handled = self.input_handler_manager.process_input(input_event)

                # If not handled, add to remaining events
                if not handled:
                    remaining_events.append(event)
            elif event.type == pygame.KEYUP:
                # Handle PTT release (Space key without modifiers)
                if event.key == pygame.K_SPACE and not (pygame.key.get_mods() & pygame.KMOD_SHIFT):
                    self.message_queue.publish(
                        Message(
                            sender="main",
                            recipients=["radio_plugin"],
                            topic="input.push_to_talk",
                            data={"pressed": False},
                            priority=MessagePriority.HIGH,
                        )
                    )
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

        # Update flight instructor plugin
        if hasattr(self, "flight_instructor_plugin") and self.flight_instructor_plugin:
            self.flight_instructor_plugin.update(dt)

        # Update TTS service (process pending audio callbacks)
        if self.tts_service:
            self.tts_service.update()

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

        if hasattr(self, "flight_instructor_plugin") and self.flight_instructor_plugin:
            logger.info("Shutting down flight instructor plugin...")
            self.flight_instructor_plugin.shutdown()

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

    parser.add_argument(
        "--skip-menu",
        action="store_true",
        help="Skip main menu and start flight directly (for development)",
    )

    return parser.parse_args()


def run_main_menu(tts_service: "TTSService | None" = None) -> tuple[str | None, dict]:
    """Run the main menu before game startup.

    Args:
        tts_service: Optional TTSService instance to pass to MenuRunner.

    Returns:
        Tuple of (result, flight_config) where result is "fly", "exit", or None.
    """
    from airborne.ui.menus import MenuRunner

    runner = MenuRunner(tts_service=tts_service)
    result = runner.run()
    return result, runner.get_flight_config()


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success).
    """
    from airborne.audio.tts_service import TTSService

    tts_service: TTSService | None = None

    try:
        args = parse_args()

        # Initialize TTSService before menu or game
        tts_service = TTSService()
        if not tts_service.start(timeout=10.0):
            logger.warning("TTSService failed to start, continuing without TTS")
            tts_service = None

        # Run main menu unless skipped
        if not getattr(args, "skip_menu", False):
            result, flight_config = run_main_menu(tts_service=tts_service)

            if result == "exit" or result is None:
                logger.info("User exited from main menu")
                if tts_service:
                    tts_service.shutdown()
                return 0

            # Apply menu selections to args
            if flight_config.get("departure"):
                args.from_airport = flight_config["departure"]
            if flight_config.get("arrival"):
                args.to_airport = flight_config["arrival"]
            if flight_config.get("aircraft"):
                args.aircraft = flight_config["aircraft"]
            # Store additional flight config for scenario building
            args.flight_config = flight_config
            logger.info("Starting flight with config: %s", flight_config)

        app = AirBorne(args, tts_service=tts_service)
        app.run()
        return 0
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Fatal error: %s", e)
        return 1
    finally:
        # Always shutdown TTS service
        if tts_service:
            tts_service.shutdown()


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Automatic flight demo using autopilot.

This script demonstrates a fully automated flight sequence:
1. Engine startup
2. Automatic takeoff
3. Climb to cruise altitude
4. Level flight with heading hold
5. Gentle descent
6. Landing approach

No user input required - the autopilot handles everything.
"""

import sys
import time
from pathlib import Path

import pygame

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from airborne.core.config import ConfigLoader
from airborne.core.event_bus import EventBus
from airborne.core.input import InputManager
from airborne.core.logging_system import get_logger
from airborne.core.messaging import MessageQueue, MessageTopic
from airborne.core.plugin_loader import PluginLoader
from airborne.core.registry import ComponentRegistry
from airborne.physics.vectors import Vector3
from airborne.plugins.avionics.autopilot_plugin import AutopilotMode

logger = get_logger(__name__)


class AutomaticDemoFlight:
    """Orchestrates an automatic demo flight using the autopilot."""

    def __init__(self):
        """Initialize the demo."""
        logger.info("=== AirBorne Automatic Flight Demo ===")
        logger.info("Initializing systems...")

        # Initialize pygame
        pygame.init()
        self.screen = pygame.display.set_mode((800, 600))
        pygame.display.set_caption("AirBorne - Automatic Demo Flight")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 36)
        self.small_font = pygame.font.Font(None, 24)

        # Core systems
        self.event_bus = EventBus()
        self.message_queue = MessageQueue()
        self.plugin_registry = ComponentRegistry()

        # Load plugins
        self.plugin_loader = PluginLoader([Path("src/airborne/plugins")])

        # Load aircraft config first to get flight model params
        from airborne.aircraft.builder import AircraftBuilder

        aircraft_config_path = "config/aircraft/cessna172.yaml"
        config_data = AircraftBuilder.load_config(aircraft_config_path)
        flight_model_config = config_data.get("aircraft", {}).get("flight_model_config", {})

        # Create config with flight model params
        self.config = {
            "physics": {"flight_model": {"type": "simple_6dof", **flight_model_config}},
            "audio": {},
            "tts": {},
        }

        # Initialize plugins
        from airborne.core.plugin import PluginContext

        context = PluginContext(
            event_bus=self.event_bus,
            message_queue=self.message_queue,
            config=self.config,
            plugin_registry=self.plugin_registry,
        )

        # Load physics plugin
        logger.info("Loading physics plugin...")
        self.physics_plugin = self.plugin_loader.load_plugin("physics_plugin", context)

        # Load audio plugin
        logger.info("Loading audio plugin...")
        self.audio_plugin = self.plugin_loader.load_plugin("audio_plugin", context)

        # Load autopilot plugin
        logger.info("Loading autopilot plugin...")
        self.autopilot_plugin = self.plugin_loader.load_plugin("autopilot_plugin", context)

        # Load aircraft
        logger.info("Loading Cessna 172...")
        builder = AircraftBuilder(self.plugin_loader, context)
        self.aircraft = builder.build(Path(aircraft_config_path))

        # Demo state
        self.phase = 0
        self.phase_time = 0.0
        self.running = True
        self.paused = False

        logger.info("Demo initialized successfully!")

    def run(self) -> None:
        """Run the automatic demo flight."""
        logger.info("Starting automatic flight sequence...")
        logger.info("Press SPACE to pause/resume, ESC to exit")

        # Demo sequence phases with durations (seconds)
        phases = [
            ("Startup & Taxi", 5.0, self._phase_startup),
            ("Takeoff Roll", 15.0, self._phase_takeoff),
            ("Climb to 3000ft", 30.0, self._phase_climb),
            ("Level Flight", 20.0, self._phase_cruise),
            ("Descent", 25.0, self._phase_descent),
            ("Approach", 15.0, self._phase_approach),
        ]

        dt = 1.0 / 60.0  # Fixed 60 FPS
        total_time = 0.0

        while self.running:
            # Handle events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    elif event.key == pygame.K_SPACE:
                        self.paused = not self.paused
                        logger.info(f"Demo {'PAUSED' if self.paused else 'RESUMED'}")

            if not self.paused:
                # Update current phase
                if self.phase < len(phases):
                    phase_name, phase_duration, phase_func = phases[self.phase]

                    # Execute phase logic
                    phase_func(dt)

                    # Check if phase complete
                    self.phase_time += dt
                    if self.phase_time >= phase_duration:
                        logger.info(f"Phase {self.phase + 1}/{len(phases)} complete: {phase_name}")
                        self.phase += 1
                        self.phase_time = 0.0
                else:
                    # Demo complete
                    logger.info("=== Demo flight complete! ===")
                    self.running = False

                # Update all systems
                self.aircraft.update(dt)
                self.physics_plugin.update(dt)
                self.audio_plugin.update(dt)
                self.autopilot_plugin.update(dt)
                self.message_queue.process(max_messages=100)

                total_time += dt

            # Render
            self._render(phases)

            # Maintain 60 FPS
            self.clock.tick(60)

        # Shutdown
        logger.info("Shutting down demo...")
        self.aircraft.shutdown()
        self.physics_plugin.shutdown()
        self.audio_plugin.shutdown()
        self.autopilot_plugin.shutdown()
        pygame.quit()
        logger.info("Demo shutdown complete")

    def _phase_startup(self, dt: float) -> None:
        """Phase 0: Engine startup and taxi prep."""
        if self.phase_time == 0:
            logger.info("PHASE: Engine Startup")
            # Turn on battery and start engine
            self.message_queue.publish(
                Message(
                    sender="demo",
                    recipients=["electrical"],
                    topic=MessageTopic.SYSTEM_COMMAND,
                    data={"command": "master_switch", "value": True},
                )
            )
            self.message_queue.publish(
                Message(
                    sender="demo",
                    recipients=["engine"],
                    topic=MessageTopic.SYSTEM_COMMAND,
                    data={"command": "start_engine"},
                )
            )
            # Set 25% throttle for taxi
            self.message_queue.publish(
                Message(
                    sender="demo",
                    recipients=["engine"],
                    topic=MessageTopic.CONTROL_INPUT,
                    data={"throttle": 0.25},
                )
            )

    def _phase_takeoff(self, dt: float) -> None:
        """Phase 1: Takeoff roll using autopilot."""
        if self.phase_time == 0:
            logger.info("PHASE: Takeoff Roll - Full throttle, autopilot engaged")
            # Full throttle
            self.message_queue.publish(
                Message(
                    sender="demo",
                    recipients=["engine"],
                    topic=MessageTopic.CONTROL_INPUT,
                    data={"throttle": 1.0},
                )
            )
            # Engage autopilot takeoff mode
            self.message_queue.publish(
                Message(
                    sender="demo",
                    recipients=["autopilot"],
                    topic=MessageTopic.AUTOPILOT_COMMAND,
                    data={"command": "set_mode", "mode": AutopilotMode.GROUND_TAKEOFF},
                )
            )

    def _phase_climb(self, dt: float) -> None:
        """Phase 2: Climb to cruise altitude."""
        if self.phase_time == 0:
            logger.info("PHASE: Climbing to 3000ft MSL with autopilot")
            # Engage altitude hold at 3000ft
            self.message_queue.publish(
                Message(
                    sender="demo",
                    recipients=["autopilot"],
                    topic=MessageTopic.AUTOPILOT_COMMAND,
                    data={
                        "command": "set_altitude_target",
                        "altitude_ft": 3000.0,
                    },
                )
            )
            self.message_queue.publish(
                Message(
                    sender="demo",
                    recipients=["autopilot"],
                    topic=MessageTopic.AUTOPILOT_COMMAND,
                    data={"command": "set_mode", "mode": AutopilotMode.ALTITUDE_HOLD},
                )
            )

    def _phase_cruise(self, dt: float) -> None:
        """Phase 3: Level flight at cruise altitude."""
        if self.phase_time == 0:
            logger.info("PHASE: Cruise flight - maintaining 3000ft, heading 270°")
            # Set heading hold to 270° (west)
            self.message_queue.publish(
                Message(
                    sender="demo",
                    recipients=["autopilot"],
                    topic=MessageTopic.AUTOPILOT_COMMAND,
                    data={
                        "command": "set_heading_target",
                        "heading_deg": 270.0,
                    },
                )
            )
            self.message_queue.publish(
                Message(
                    sender="demo",
                    recipients=["autopilot"],
                    topic=MessageTopic.AUTOPILOT_COMMAND,
                    data={"command": "set_mode", "mode": AutopilotMode.HEADING_HOLD},
                )
            )

    def _phase_descent(self, dt: float) -> None:
        """Phase 4: Descend to pattern altitude."""
        if self.phase_time == 0:
            logger.info("PHASE: Descending to 1500ft for approach")
            # Reduce throttle
            self.message_queue.publish(
                Message(
                    sender="demo",
                    recipients=["engine"],
                    topic=MessageTopic.CONTROL_INPUT,
                    data={"throttle": 0.5},
                )
            )
            # Set vertical speed to -500 fpm
            self.message_queue.publish(
                Message(
                    sender="demo",
                    recipients=["autopilot"],
                    topic=MessageTopic.AUTOPILOT_COMMAND,
                    data={
                        "command": "set_vertical_speed_target",
                        "vs_fpm": -500.0,
                    },
                )
            )
            self.message_queue.publish(
                Message(
                    sender="demo",
                    recipients=["autopilot"],
                    topic=MessageTopic.AUTOPILOT_COMMAND,
                    data={"command": "set_mode", "mode": AutopilotMode.VERTICAL_SPEED},
                )
            )

    def _phase_approach(self, dt: float) -> None:
        """Phase 5: Final approach."""
        if self.phase_time == 0:
            logger.info("PHASE: Final approach - autopilot landing mode")
            # Engage auto-land
            self.message_queue.publish(
                Message(
                    sender="demo",
                    recipients=["autopilot"],
                    topic=MessageTopic.AUTOPILOT_COMMAND,
                    data={"command": "set_mode", "mode": AutopilotMode.AUTO_LAND},
                )
            )

    def _render(self, phases) -> None:
        """Render the demo display."""
        # Black background
        self.screen.fill((0, 0, 0))

        # Get current state from physics
        try:
            flight_model = self.plugin_registry.get("flight_model")
            state = flight_model.get_state()

            # Display title
            title = self.font.render("AirBorne - Automatic Demo Flight", True, (0, 255, 0))
            self.screen.blit(title, (50, 30))

            # Display current phase
            if self.phase < len(phases):
                phase_name, duration, _ = phases[self.phase]
                phase_text = self.small_font.render(
                    f"Phase {self.phase + 1}/{len(phases)}: {phase_name}",
                    True,
                    (255, 255, 0),
                )
                self.screen.blit(phase_text, (50, 80))

                # Progress bar
                progress = min(1.0, self.phase_time / duration)
                pygame.draw.rect(self.screen, (50, 50, 50), (50, 110, 700, 20))  # Background
                pygame.draw.rect(
                    self.screen, (0, 200, 0), (50, 110, int(700 * progress), 20)
                )  # Progress

            # Display flight data
            y = 160
            data = [
                f"Altitude: {state.altitude_msl_ft:.0f} ft MSL",
                f"Airspeed: {state.airspeed_kts:.1f} kts",
                f"Heading: {state.heading_deg:.0f}°",
                f"Vertical Speed: {state.vertical_speed_fpm:.0f} fpm",
                f"Throttle: {state.throttle * 100:.0f}%",
                "",
                f"Position: ({state.position.x:.1f}, {state.position.y:.1f}, {state.position.z:.1f})",
                f"Velocity: {state.velocity.magnitude():.1f} m/s",
            ]

            for line in data:
                text = self.small_font.render(line, True, (200, 200, 200))
                self.screen.blit(text, (50, y))
                y += 30

            # Pause indicator
            if self.paused:
                pause_text = self.font.render("PAUSED", True, (255, 0, 0))
                self.screen.blit(pause_text, (320, 500))

            # Instructions
            help_text = self.small_font.render(
                "SPACE: Pause/Resume | ESC: Exit", True, (150, 150, 150)
            )
            self.screen.blit(help_text, (50, 550))

        except Exception as e:
            error_text = self.small_font.render(f"Error: {e}", True, (255, 0, 0))
            self.screen.blit(error_text, (50, 160))

        pygame.display.flip()


def main():
    """Run the automatic demo flight."""
    try:
        demo = AutomaticDemoFlight()
        demo.run()
        return 0
    except KeyboardInterrupt:
        logger.info("Demo interrupted by user")
        return 0
    except Exception as e:
        logger.error(f"Demo failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Automatic flight demo using autopilot.

This script demonstrates a fully automated flight sequence by extending
the main AirBorne application and injecting autopilot commands.

Phases:
1. Engine startup and taxi prep (5s)
2. Takeoff roll with autopilot (15s)
3. Climb to 3000ft (30s)
4. Cruise flight at 270° heading (20s)
5. Descent to pattern altitude (25s)
6. Final approach and landing (15s)

Total demo duration: ~110 seconds

Controls:
- SPACE: Pause/Resume
- ESC: Exit demo
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessageTopic
from airborne.main import AirBorne
from airborne.plugins.avionics.autopilot_plugin import AutopilotMode

logger = get_logger(__name__)


class AutopilotDemo(AirBorne):
    """Automatic demo extending main AirBorne app."""

    def __init__(self):
        """Initialize demo with phase tracking."""
        logger.info("=== AirBorne Automatic Flight Demo ===")
        logger.info("Initializing automatic demo...")

        # Initialize base app
        super().__init__()

        # Demo state
        self.demo_phase = 0
        self.demo_time = 0.0
        self.demo_active = True

        # Phase definitions: (name, duration, init_function)
        self.phases = [
            ("Engine Startup & Taxi Prep", 5.0, self._init_phase_startup),
            ("Takeoff Roll", 15.0, self._init_phase_takeoff),
            ("Climb to 3000ft", 30.0, self._init_phase_climb),
            ("Cruise Flight", 20.0, self._init_phase_cruise),
            ("Descent", 25.0, self._init_phase_descent),
            ("Final Approach", 15.0, self._init_phase_approach),
        ]

        logger.info(f"Demo initialized with {len(self.phases)} phases")
        logger.info("Press SPACE to pause, ESC to exit")

    def run(self) -> None:
        """Run the demo with automatic phase progression."""
        logger.info("Starting automatic flight sequence...")

        # Execute first phase
        if self.phases:
            phase_name, _, init_func = self.phases[0]
            logger.info(f"=== PHASE 1: {phase_name} ===")
            init_func()

        # Run main loop
        super().run()

    def _update(self, dt: float) -> None:
        """Override update to inject demo logic."""
        # Run base update
        super()._update(dt)

        # Demo phase management
        if self.demo_active and not self.paused:
            self.demo_time += dt

            # Check for phase transition
            if self.demo_phase < len(self.phases):
                _, duration, _ = self.phases[self.demo_phase]

                if self.demo_time >= duration:
                    # Move to next phase
                    self.demo_phase += 1
                    self.demo_time = 0.0

                    if self.demo_phase < len(self.phases):
                        phase_name, _, init_func = self.phases[self.demo_phase]
                        logger.info(f"=== PHASE {self.demo_phase + 1}: {phase_name} ===")
                        init_func()
                    else:
                        logger.info("=== DEMO COMPLETE ===")
                        logger.info("All phases executed successfully!")
                        self.demo_active = False
                        # Let it run for a bit more to see results
                        # Don't auto-quit, let user exit with ESC

    def _render(self) -> None:
        """Override render to show demo info."""
        # Call base render
        super()._render()

        # Add demo overlay
        if self.demo_active and self.demo_phase < len(self.phases):
            phase_name, duration, _ = self.phases[self.demo_phase]
            progress = min(1.0, self.demo_time / duration)

            # Phase indicator
            phase_text = f"Phase {self.demo_phase + 1}/{len(self.phases)}: {phase_name}"
            text_surface = self.font.render(phase_text, True, (255, 255, 0))
            self.screen.blit(text_surface, (10, 10))

            # Progress bar
            bar_width = 300
            bar_height = 10
            bar_x = 10
            bar_y = 30

            # Background
            import pygame

            pygame.draw.rect(self.screen, (50, 50, 50), (bar_x, bar_y, bar_width, bar_height))
            # Progress
            pygame.draw.rect(
                self.screen,
                (0, 200, 0),
                (bar_x, bar_y, int(bar_width * progress), bar_height),
            )

            # Time remaining
            time_left = duration - self.demo_time
            time_text = f"{time_left:.1f}s remaining"
            time_surface = self.font.render(time_text, True, (200, 200, 200))
            self.screen.blit(time_surface, (bar_x + bar_width + 10, bar_y))

    # Phase initialization functions

    def _init_phase_startup(self) -> None:
        """Phase 0: Engine startup and taxi preparation."""
        logger.info("Starting engine and preparing for taxi...")

        # Start "Before Engine Start" checklist
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["checklist_plugin"],
                topic="checklist.start",
                data={"checklist_name": "Before Engine Start"},
            )
        )

        # Master switch ON
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["electrical"],
                topic="electrical.master_switch",
                data={"state": "ON"},
            )
        )

        # Fuel selector to BOTH
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["fuel"],
                topic="fuel.selector",
                data={"state": "BOTH"},
            )
        )

        # Mixture to RICH
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["engine"],
                topic="engine.mixture",
                data={"state": "RICH"},
            )
        )

        # Magnetos to BOTH
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["engine"],
                topic="engine.magnetos",
                data={"state": "BOTH"},
            )
        )

        # Set idle throttle for engine start
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["*"],
                topic=MessageTopic.CONTROL_INPUT,
                data={"throttle": 0.15},
            )
        )

        # Engage starter (engine start checklist)
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["engine"],
                topic="engine.magnetos",
                data={"state": "START"},
            )
        )

    def _init_phase_takeoff(self) -> None:
        """Phase 1: Takeoff roll with autopilot."""
        logger.info("Commencing takeoff roll - FULL POWER!")

        # Start takeoff checklist
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["checklist_plugin"],
                topic="checklist.start",
                data={"checklist_name": "Normal Takeoff"},
            )
        )

        # Request takeoff clearance from ATC
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["radio_plugin"],
                topic="atc.request",
                data={"request_type": "takeoff_clearance"},
            )
        )

        # Full throttle
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["*"],
                topic=MessageTopic.CONTROL_INPUT,
                data={"throttle": 1.0},
            )
        )

        # Engage autopilot takeoff mode
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["autopilot"],
                topic="autopilot.command",
                data={"command": "set_mode", "mode": AutopilotMode.GROUND_TAKEOFF.value},
            )
        )

    def _init_phase_climb(self) -> None:
        """Phase 2: Climb to cruise altitude."""
        logger.info("Climbing to cruise altitude (3000ft MSL)")

        # Retract landing gear after positive climb
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["*"],
                topic=MessageTopic.CONTROL_INPUT,
                data={"gear": 0.0},  # Gear up
            )
        )

        # Set altitude target
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["autopilot"],
                topic="autopilot.command",
                data={"command": "set_altitude_target", "altitude_ft": 3000.0},
            )
        )

        # Engage altitude hold mode
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["autopilot"],
                topic="autopilot.command",
                data={"command": "set_mode", "mode": AutopilotMode.ALTITUDE_HOLD.value},
            )
        )

        # Check in with departure
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["radio_plugin"],
                topic="atc.request",
                data={"request_type": "departure_checkin"},
            )
        )

    def _init_phase_cruise(self) -> None:
        """Phase 3: Cruise flight at constant heading."""
        logger.info("Cruise flight - maintaining 3000ft, heading 270° (West)")

        # Set heading to 270° (west)
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["autopilot"],
                topic="autopilot.command",
                data={"command": "set_heading_target", "heading_deg": 270.0},
            )
        )

        # Engage heading hold mode
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["autopilot"],
                topic="autopilot.command",
                data={"command": "set_mode", "mode": AutopilotMode.HEADING_HOLD.value},
            )
        )

    def _init_phase_descent(self) -> None:
        """Phase 4: Descend to pattern altitude."""
        logger.info("Descending to pattern altitude (1500ft)")

        # Start before landing checklist
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["checklist_plugin"],
                topic="checklist.start",
                data={"checklist_name": "Before Landing"},
            )
        )

        # Reduce power
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["*"],
                topic=MessageTopic.CONTROL_INPUT,
                data={"throttle": 0.5},
            )
        )

        # Set vertical speed to -500 fpm
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["autopilot"],
                topic="autopilot.command",
                data={"command": "set_vertical_speed_target", "vs_fpm": -500.0},
            )
        )

        # Engage vertical speed mode
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["autopilot"],
                topic="autopilot.command",
                data={"command": "set_mode", "mode": AutopilotMode.VERTICAL_SPEED.value},
            )
        )

    def _init_phase_approach(self) -> None:
        """Phase 5: Final approach and landing."""
        logger.info("Final approach - autopilot landing mode engaged")

        # Lower landing gear
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["*"],
                topic=MessageTopic.CONTROL_INPUT,
                data={"gear": 1.0},  # Gear down
            )
        )

        # Extend flaps for landing
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["*"],
                topic=MessageTopic.CONTROL_INPUT,
                data={"flaps": 0.5},  # Half flaps
            )
        )

        # Request landing clearance
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["radio_plugin"],
                topic="atc.request",
                data={"request_type": "landing_clearance"},
            )
        )

        # Engage auto-land mode
        self.message_queue.publish(
            Message(
                sender="demo",
                recipients=["autopilot"],
                topic="autopilot.command",
                data={"command": "set_mode", "mode": AutopilotMode.AUTO_LAND.value},
            )
        )


def main() -> int:
    """Run the automatic demo."""
    try:
        demo = AutopilotDemo()
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

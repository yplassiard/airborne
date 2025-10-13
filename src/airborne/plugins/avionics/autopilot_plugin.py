"""Autopilot plugin for automated flight control.

Provides comprehensive autopilot functionality including:
- Ground operations (taxi, takeoff roll)
- Heading hold
- Altitude hold
- Vertical speed mode
- Speed hold
- Navigation mode (follow waypoints)
- Automatic landing

Uses PID controllers for smooth, realistic control.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType
from airborne.physics.vectors import Vector3

logger = get_logger(__name__)


class AutopilotMode(Enum):
    """Autopilot operating modes."""

    OFF = "off"
    GROUND_TAXI = "ground_taxi"  # Follow taxiway centerline
    GROUND_TAKEOFF = "ground_takeoff"  # Takeoff roll
    HEADING_HOLD = "heading_hold"  # Maintain heading
    ALTITUDE_HOLD = "altitude_hold"  # Maintain altitude
    VERTICAL_SPEED = "vertical_speed"  # Maintain vertical speed
    SPEED_HOLD = "speed_hold"  # Maintain airspeed
    NAV_MODE = "nav_mode"  # Follow waypoints
    APPROACH = "approach"  # ILS approach
    AUTO_LAND = "auto_land"  # Automatic landing


@dataclass
class PIDController:
    """Simple PID controller for smooth control.

    Attributes:
        kp: Proportional gain
        ki: Integral gain
        kd: Derivative gain
        integral: Accumulated integral error
        last_error: Previous error for derivative
        output_min: Minimum output value
        output_max: Maximum output value
    """

    kp: float
    ki: float
    kd: float
    integral: float = 0.0
    last_error: float = 0.0
    output_min: float = -1.0
    output_max: float = 1.0

    def update(self, error: float, dt: float) -> float:
        """Update PID controller and return control output.

        Args:
            error: Current error (setpoint - actual)
            dt: Time delta since last update

        Returns:
            Control output value
        """
        # Proportional term
        p_term = self.kp * error

        # Integral term (with anti-windup)
        self.integral += error * dt
        self.integral = max(
            min(self.integral, self.output_max / self.ki if self.ki > 0 else 1.0),
            self.output_min / self.ki if self.ki > 0 else -1.0,
        )
        i_term = self.ki * self.integral

        # Derivative term
        d_term = self.kd * (error - self.last_error) / dt if dt > 0 else 0.0

        self.last_error = error

        # Calculate output and clamp
        output = p_term + i_term + d_term
        return max(min(output, self.output_max), self.output_min)

    def reset(self) -> None:
        """Reset controller state."""
        self.integral = 0.0
        self.last_error = 0.0


class AutopilotPlugin(IPlugin):
    """Autopilot plugin for automated flight control.

    Provides multiple autopilot modes with PID-based control for smooth,
    realistic automated flight from ground operations through landing.
    """

    def __init__(self) -> None:
        """Initialize autopilot plugin."""
        self.context: PluginContext | None = None

        # Autopilot state
        self.mode = AutopilotMode.OFF
        self.enabled = False

        # Target values
        self.target_heading: float = 0.0
        self.target_altitude: float = 0.0
        self.target_vertical_speed: float = 0.0
        self.target_speed: float = 80.0  # knots
        self.target_runway_heading: float = 0.0

        # Current state (from physics)
        self.current_position = Vector3(0, 0, 0)
        self.current_altitude: float = 0.0
        self.current_heading: float = 0.0
        self.current_vertical_speed: float = 0.0
        self.current_speed: float = 0.0
        self.current_pitch: float = 0.0
        self.current_roll: float = 0.0
        self.on_ground: bool = True

        # PID controllers
        self.heading_pid = PIDController(kp=0.02, ki=0.001, kd=0.01)
        self.altitude_pid = PIDController(
            kp=0.01, ki=0.0005, kd=0.005, output_min=-0.5, output_max=0.5
        )
        self.speed_pid = PIDController(kp=0.05, ki=0.01, kd=0.0, output_min=0.0, output_max=1.0)
        self.vs_pid = PIDController(kp=0.005, ki=0.0001, kd=0.002, output_min=-0.3, output_max=0.3)

        # Takeoff parameters
        self.takeoff_rotation_speed = 55.0  # knots
        self.takeoff_climb_speed = 70.0  # knots
        self.takeoff_climb_angle = 10.0  # degrees

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return PluginMetadata(
            name="autopilot_plugin",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.AVIONICS,
            dependencies=[],
            provides=["autopilot"],
            optional=False,
            update_priority=25,
            requires_physics=True,
            description="Automated flight control system",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the autopilot plugin."""
        self.context = context
        logger.info("Autopilot plugin initializing...")

        # Subscribe to messages
        context.message_queue.subscribe(MessageTopic.POSITION_UPDATED, self.handle_message)
        context.message_queue.subscribe("input.autopilot", self.handle_message)
        context.message_queue.subscribe(
            "autopilot.command", self.handle_message
        )  # For demo commands

        # Register in registry
        if context.plugin_registry:
            context.plugin_registry.register("autopilot", self)

        logger.info("Autopilot plugin initialized")

    def update(self, dt: float) -> None:
        """Update autopilot and generate control outputs."""
        if not self.enabled or self.mode == AutopilotMode.OFF:
            return

        # Generate control outputs based on mode
        if self.mode == AutopilotMode.GROUND_TAKEOFF:
            self._update_ground_takeoff(dt)
        elif self.mode == AutopilotMode.HEADING_HOLD:
            self._update_heading_hold(dt)
        elif self.mode == AutopilotMode.ALTITUDE_HOLD:
            self._update_altitude_hold(dt)
        elif self.mode == AutopilotMode.VERTICAL_SPEED:
            self._update_vertical_speed(dt)
        elif self.mode == AutopilotMode.SPEED_HOLD:
            self._update_speed_hold(dt)

    def shutdown(self) -> None:
        """Shutdown the autopilot plugin."""
        if self.context:
            self.context.message_queue.unsubscribe(
                MessageTopic.POSITION_UPDATED, self.handle_message
            )
            self.context.message_queue.unsubscribe("input.autopilot", self.handle_message)
            self.context.message_queue.unsubscribe("autopilot.command", self.handle_message)

        logger.info("Autopilot plugin shutdown")

    def handle_message(self, message: Message) -> None:
        """Handle incoming messages."""
        if not self.context:
            return

        if message.topic == MessageTopic.POSITION_UPDATED:
            self._handle_position_update(message)
        elif message.topic in ("input.autopilot", "autopilot.command"):
            self._handle_autopilot_command(message)

    def _handle_position_update(self, message: Message) -> None:
        """Handle position updates from physics."""
        data = message.data
        self.current_position = Vector3(data.get("x", 0), data.get("y", 0), data.get("z", 0))
        self.current_altitude = data.get("altitude_ft", 0)
        self.current_heading = data.get("heading", 0)
        self.current_vertical_speed = data.get("vertical_speed_fpm", 0)
        self.current_speed = data.get("airspeed_kts", 0)
        self.current_pitch = data.get("pitch", 0)
        self.current_roll = data.get("roll", 0)
        self.on_ground = data.get("on_ground", True)

    def _handle_autopilot_command(self, message: Message) -> None:
        """Handle autopilot commands."""
        data = message.data
        command = data.get("command", "")

        if command == "engage":
            self.engage(data.get("mode", "heading_hold"))
        elif command == "disengage":
            self.disengage()
        elif command == "set_mode":
            # Handle direct mode setting (from demo)
            mode = data.get("mode", "")
            if mode:
                self.engage(mode)
        elif command == "set_target_heading" or command == "set_heading_target":
            self.set_target_heading(data.get("heading", data.get("heading_deg", 0)))
        elif command == "set_target_altitude" or command == "set_altitude_target":
            self.set_target_altitude(data.get("altitude", data.get("altitude_ft", 0)))
        elif command == "set_target_speed":
            self.set_target_speed(data.get("speed", 80))
        elif command == "set_vertical_speed_target":
            self.target_vertical_speed = data.get("vs_fpm", 0)
            if self.mode != AutopilotMode.VERTICAL_SPEED:
                self.engage(AutopilotMode.VERTICAL_SPEED.value)
            logger.info("Target vertical speed set to %.0f fpm", self.target_vertical_speed)

    def engage(self, mode_str: str) -> None:
        """Engage autopilot in specified mode."""
        try:
            self.mode = AutopilotMode(mode_str)
            self.enabled = True

            # Set initial targets based on current state
            if self.mode == AutopilotMode.HEADING_HOLD:
                self.target_heading = self.current_heading
            elif self.mode == AutopilotMode.ALTITUDE_HOLD:
                self.target_altitude = self.current_altitude
            elif self.mode == AutopilotMode.SPEED_HOLD:
                self.target_speed = self.current_speed

            # Reset PID controllers
            self.heading_pid.reset()
            self.altitude_pid.reset()
            self.speed_pid.reset()
            self.vs_pid.reset()

            logger.info("Autopilot engaged: %s", self.mode.value)

            # Announce via TTS
            if self.context and self.context.plugin_registry:
                self._announce(f"Autopilot {self.mode.value.replace('_', ' ')}")

        except ValueError:
            logger.error("Unknown autopilot mode: %s", mode_str)

    def disengage(self) -> None:
        """Disengage autopilot."""
        self.enabled = False
        self.mode = AutopilotMode.OFF
        logger.info("Autopilot disengaged")

        if self.context and self.context.plugin_registry:
            self._announce("Autopilot off")

    def set_target_heading(self, heading: float) -> None:
        """Set target heading for heading hold mode."""
        self.target_heading = heading % 360
        logger.info("Target heading set to %.1f", self.target_heading)

    def set_target_altitude(self, altitude: float) -> None:
        """Set target altitude for altitude hold mode."""
        self.target_altitude = altitude
        logger.info("Target altitude set to %.0f ft", self.target_altitude)

    def set_target_speed(self, speed: float) -> None:
        """Set target speed for speed hold mode."""
        self.target_speed = speed
        logger.info("Target speed set to %.0f kts", self.target_speed)

    def _update_ground_takeoff(self, dt: float) -> None:
        """Update ground takeoff mode."""
        if not self.context:
            return

        # Full throttle during takeoff roll
        throttle = 1.0

        # Keep wings level and centered on runway
        roll_input = 0.0
        yaw_input = 0.0

        # Rotate at rotation speed
        if self.current_speed >= self.takeoff_rotation_speed and self.on_ground:
            pitch_input = 0.15  # Gentle rotation
        elif not self.on_ground:
            # Airborne - maintain climb angle
            target_pitch = self.takeoff_climb_angle
            pitch_error = target_pitch - self.current_pitch
            pitch_input = pitch_error * 0.02
            pitch_input = max(min(pitch_input, 0.3), -0.3)

            # Switch to altitude hold when reaching 500 ft AGL
            if self.current_altitude > 500:
                self.mode = AutopilotMode.ALTITUDE_HOLD
                self.target_altitude = 1500  # Climb to pattern altitude
                logger.info("Takeoff complete, switching to altitude hold")
        else:
            pitch_input = 0.0

        # Send control inputs
        self._send_control_inputs(pitch_input, roll_input, yaw_input, throttle)

    def _update_heading_hold(self, dt: float) -> None:
        """Update heading hold mode."""
        # Calculate heading error (-180 to +180)
        heading_error = self.target_heading - self.current_heading
        if heading_error > 180:
            heading_error -= 360
        elif heading_error < -180:
            heading_error += 360

        # Use PID controller for roll input
        roll_input = self.heading_pid.update(heading_error, dt)

        # Keep pitch and throttle neutral (or use from other modes)
        pitch_input = 0.0
        yaw_input = 0.0
        throttle = 0.5

        self._send_control_inputs(pitch_input, roll_input, yaw_input, throttle)

    def _update_altitude_hold(self, dt: float) -> None:
        """Update altitude hold mode."""
        # Calculate altitude error
        altitude_error = self.target_altitude - self.current_altitude

        # Use PID controller for pitch input
        pitch_input = self.altitude_pid.update(altitude_error, dt)

        # Also maintain heading
        heading_error = self.target_heading - self.current_heading
        if heading_error > 180:
            heading_error -= 360
        elif heading_error < -180:
            heading_error += 360
        roll_input = self.heading_pid.update(heading_error, dt)

        # Maintain speed with throttle
        speed_error = self.target_speed - self.current_speed
        throttle = self.speed_pid.update(speed_error, dt)

        yaw_input = 0.0

        self._send_control_inputs(pitch_input, roll_input, yaw_input, throttle)

    def _update_vertical_speed(self, dt: float) -> None:
        """Update vertical speed mode."""
        # Calculate VS error
        vs_error = self.target_vertical_speed - self.current_vertical_speed

        # Use PID controller for pitch input
        pitch_input = self.vs_pid.update(vs_error, dt)

        # Maintain heading
        heading_error = self.target_heading - self.current_heading
        if heading_error > 180:
            heading_error -= 360
        elif heading_error < -180:
            heading_error += 360
        roll_input = self.heading_pid.update(heading_error, dt)

        # Maintain speed with throttle
        speed_error = self.target_speed - self.current_speed
        throttle = self.speed_pid.update(speed_error, dt)

        yaw_input = 0.0

        self._send_control_inputs(pitch_input, roll_input, yaw_input, throttle)

    def _update_speed_hold(self, dt: float) -> None:
        """Update speed hold mode."""
        # Calculate speed error
        speed_error = self.target_speed - self.current_speed

        # Use PID controller for throttle
        throttle = self.speed_pid.update(speed_error, dt)

        # Keep other controls neutral
        pitch_input = 0.0
        roll_input = 0.0
        yaw_input = 0.0

        self._send_control_inputs(pitch_input, roll_input, yaw_input, throttle)

    def _send_control_inputs(self, pitch: float, roll: float, yaw: float, throttle: float) -> None:
        """Send control inputs to physics."""
        if not self.context:
            return

        control_message = Message(
            sender="autopilot",
            recipients=["physics_plugin"],
            topic="control.autopilot",
            data={
                "pitch": max(min(pitch, 1.0), -1.0),
                "roll": max(min(roll, 1.0), -1.0),
                "yaw": max(min(yaw, 1.0), -1.0),
                "throttle": max(min(throttle, 1.0), 0.0),
            },
            priority=MessagePriority.HIGH,
        )
        self.context.message_queue.publish(control_message)

    def _announce(self, text: str) -> None:
        """Announce via TTS."""
        if not self.context or not self.context.plugin_registry:
            return

        try:
            audio_plugin = self.context.plugin_registry.get("audio_plugin")
            if audio_plugin and hasattr(audio_plugin, "tts_provider"):
                audio_plugin.tts_provider.speak(text, interrupt=False)
        except Exception as e:
            logger.debug("Failed to announce: %s", e)

    def on_config_changed(self, config: dict[str, Any]) -> None:
        """Handle configuration changes."""
        autopilot_config = config.get("autopilot", {})

        # Update PID gains if provided
        if "heading_pid" in autopilot_config:
            pid = autopilot_config["heading_pid"]
            self.heading_pid.kp = pid.get("kp", self.heading_pid.kp)
            self.heading_pid.ki = pid.get("ki", self.heading_pid.ki)
            self.heading_pid.kd = pid.get("kd", self.heading_pid.kd)

        if "altitude_pid" in autopilot_config:
            pid = autopilot_config["altitude_pid"]
            self.altitude_pid.kp = pid.get("kp", self.altitude_pid.kp)
            self.altitude_pid.ki = pid.get("ki", self.altitude_pid.ki)
            self.altitude_pid.kd = pid.get("kd", self.altitude_pid.kd)

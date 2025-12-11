"""Physics plugin for the AirBorne flight simulator.

This plugin wraps the physics system (flight model and collision detection),
making it available to other plugins through the plugin context.

Typical usage:
    The physics plugin is loaded automatically by the plugin loader and provides
    physics services to other plugins via the component registry.
"""

import math
from typing import Any

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType
from airborne.physics.collision import TerrainCollisionDetector
from airborne.physics.flight_model.base import AircraftState, ControlInputs, IFlightModel
from airborne.physics.flight_model.simple_6dof import Simple6DOFFlightModel
from airborne.physics.ground_physics import GroundContact, GroundPhysics
from airborne.physics.vectors import Vector3
from airborne.systems.propeller import FixedPitchPropeller, IPropeller
from airborne.telemetry import TelemetryLogger

logger = get_logger(__name__)


class PhysicsPlugin(IPlugin):
    """Physics plugin that manages flight model and collision detection.

    This plugin wraps the flight model and collision detector, making them
    available to other plugins. It receives control inputs via messages and
    publishes position updates every frame.

    The plugin provides:
    - flight_model: IFlightModel instance
    - collision_detector: TerrainCollisionDetector instance
    """

    def __init__(self) -> None:
        """Initialize physics plugin."""
        self.context: PluginContext | None = None
        self.flight_model: IFlightModel | None = None
        self.collision_detector: TerrainCollisionDetector | None = None
        self.ground_physics: GroundPhysics | None = None
        self.propeller: IPropeller | None = None

        # Control inputs (updated via messages)
        self.control_inputs = ControlInputs()

        # Parking brake state (persists independent of regular brakes)
        self.parking_brake_engaged = False

        # Terrain elevation (updated via messages)
        self._terrain_elevation: float = 0.0

        # Telemetry logger
        self.telemetry: TelemetryLogger | None = None

        # Engine state (cached from messages)
        self._engine_rpm: float = 0.0
        self._engine_power_hp: float = 0.0
        self._engine_running: bool = False
        self._fuel_flow_gph: float = 0.0
        self._fuel_remaining_gallons: float = 0.0

        # Trim state (cached from messages)
        self._pitch_trim: float = 0.0
        self._rudder_trim: float = 0.0

        # Auto-trim state
        self._auto_trim_enabled: bool = False
        self._auto_trim_target_vspeed: float = 0.0  # Target vertical speed (ft/min)
        self._auto_trim_rate: float = 0.02  # Trim adjustment rate per second

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata.

        Returns:
            PluginMetadata describing this physics plugin.
        """
        return PluginMetadata(
            name="physics_plugin",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.CORE,
            dependencies=[],
            provides=["flight_model", "collision_detector"],
            optional=False,
            update_priority=10,  # Update early (before systems)
            requires_physics=False,
            description="Physics simulation plugin with flight model and collision detection",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the physics plugin.

        Args:
            context: Plugin context with access to core systems.
        """
        self.context = context

        # Get physics config from context
        physics_config = context.config.get("physics", {})
        flight_model_config = physics_config.get("flight_model", {})

        # Create flight model (default to Simple6DOF)
        flight_model_type = flight_model_config.get("type", "simple_6dof")

        if flight_model_type == "simple_6dof":
            self.flight_model = Simple6DOFFlightModel()
        else:
            logger.warning("Unknown flight model type: %s, using Simple6DOF", flight_model_type)
            self.flight_model = Simple6DOFFlightModel()

        # Initialize flight model with config
        self.flight_model.initialize(flight_model_config)

        # Create propeller model if configured
        # Propeller config is in the aircraft section (context.config is the aircraft config)
        propeller_config = context.config.get("propeller", {})
        logger.info(f"Propeller config: {propeller_config}")
        if propeller_config:
            propeller_type = propeller_config.get("type", "fixed_pitch")
            if propeller_type == "fixed_pitch":
                self.propeller = FixedPitchPropeller(
                    diameter_m=propeller_config.get("diameter_m", 1.905),
                    pitch_ratio=propeller_config.get("pitch_ratio", 0.6),
                    efficiency_static=propeller_config.get("efficiency_static", 0.50),
                    efficiency_cruise=propeller_config.get("efficiency_cruise", 0.80),
                    cruise_advance_ratio=propeller_config.get("cruise_advance_ratio", 0.6),
                    static_thrust_multiplier=propeller_config.get("static_thrust_multiplier", 1.45),
                )
                # Attach propeller to flight model
                if hasattr(self.flight_model, "propeller"):
                    self.flight_model.propeller = self.propeller
                    logger.info(
                        f"Propeller model attached to flight model: diameter={propeller_config.get('diameter_m', 1.905)}m, "
                        f"efficiency_static={propeller_config.get('efficiency_static', 0.50)}, "
                        f"efficiency_cruise={propeller_config.get('efficiency_cruise', 0.80)}"
                    )
                else:
                    logger.warning("Flight model does not support propeller attachment!")
            else:
                logger.warning(f"Unknown propeller type: {propeller_type}")

        # Create collision detector (without elevation service for now)
        # Elevation service will be provided by terrain plugin if available
        self.collision_detector = TerrainCollisionDetector(elevation_service=None)

        # Create ground physics with aircraft mass from flight model config
        aircraft_mass_kg = (
            flight_model_config.get("weight_lbs", 2450.0) * 0.453592
        )  # Convert lbs to kg
        # Max brake force sized for ~0.35g deceleration (realistic for light aircraft)
        # a = F/m, so F = m*a = mass_kg * 0.35 * 9.81 ≈ 3.4 * mass_kg
        max_brake_force = aircraft_mass_kg * 3.4
        self.ground_physics = GroundPhysics(
            mass_kg=aircraft_mass_kg,
            max_brake_force_n=max_brake_force,  # ~0.35g deceleration
            max_steering_angle_deg=60.0,  # Nosewheel steering angle
        )
        logger.info(f"Ground physics initialized with mass={aircraft_mass_kg:.1f} kg")

        # Apply spawn state if available (source of truth for initial position/heading)
        if hasattr(context, "spawn_state") and context.spawn_state is not None:
            spawn = context.spawn_state
            # Apply position
            if hasattr(spawn, "position") and spawn.position is not None:
                self.flight_model.state.position = spawn.position
                logger.info(f"Initial position from spawn: {spawn.position}")
            # Apply heading (spawn.heading is in degrees, rotation.z is yaw in radians)
            if hasattr(spawn, "heading"):
                yaw_rad = math.radians(spawn.heading)
                self.flight_model.state.rotation = Vector3(0.0, 0.0, yaw_rad)
                logger.info(f"Initial heading from spawn: {spawn.heading}°")
            # Apply parking brake
            if hasattr(spawn, "parking_brake"):
                self.parking_brake_engaged = spawn.parking_brake
                logger.info(f"Parking brake from spawn: {spawn.parking_brake}")
            # Set on_ground based on spawn location
            self.flight_model.state.on_ground = True
        else:
            # Fallback to initial state from config
            initial_state = context.config.get("aircraft", {}).get("initial_state", {})
            controls_state = initial_state.get("controls", {})
            self.parking_brake_engaged = controls_state.get("parking_brake", False)
            logger.info(f"Parking brake from config: {self.parking_brake_engaged}")

        # Register components in registry
        if context.plugin_registry:
            context.plugin_registry.register("flight_model", self.flight_model)
            context.plugin_registry.register("collision_detector", self.collision_detector)
            context.plugin_registry.register("ground_physics", self.ground_physics)

        # Subscribe to control input messages and parking brake toggle
        context.message_queue.subscribe(MessageTopic.CONTROL_INPUT, self.handle_message)
        context.message_queue.subscribe("parking_brake", self.handle_message)
        # Also subscribe to new input context manager action topics
        context.message_queue.subscribe("input.parking_brake_set", self.handle_message)
        context.message_queue.subscribe("input.parking_brake_release", self.handle_message)

        # Subscribe to terrain updates
        context.message_queue.subscribe(MessageTopic.TERRAIN_UPDATED, self.handle_message)

        # Subscribe to engine state (to get power and RPM for propeller calculations)
        context.message_queue.subscribe(MessageTopic.ENGINE_STATE, self.handle_message)

        # Subscribe to weight & balance updates (to update aircraft mass)
        context.message_queue.subscribe("weight_balance.updated", self.handle_message)

        # Subscribe to auto-trim control
        context.message_queue.subscribe("flight_controls.auto_trim", self.handle_message)

        # Initialize telemetry logger
        self.telemetry = TelemetryLogger(buffer_size=60)  # Buffer ~1 second of data at 60fps
        logger.info(f"Telemetry logging to: {self.telemetry.db_path}")

        logger.info("Physics plugin initialized")

    def update(self, dt: float) -> None:
        """Update physics simulation.

        Args:
            dt: Delta time in seconds since last update.
        """
        if not self.flight_model or not self.context:
            return

        # Get current state BEFORE update (for ground force calculation)
        state = self.flight_model.get_state()

        # DIAGNOSTIC: Log ground detection state
        if not hasattr(self, "_ground_detection_log_counter"):
            self._ground_detection_log_counter = 0
        self._ground_detection_log_counter += 1

        # Check for terrain collision BEFORE update to apply ground forces
        if self.collision_detector:
            collision_result = self.collision_detector.check_terrain_collision(
                state.position, state.position.y, state.velocity
            )

            # Log every 60 frames to see what's happening
            if self._ground_detection_log_counter % 60 == 0:
                logger.debug(
                    f"[GROUND_DETECT] position_y={state.position.y:.2f}m "
                    f"flight_model_on_ground={state.on_ground} "
                    f"collision_is_colliding={collision_result.is_colliding} "
                    f"terrain_elevation={collision_result.terrain_elevation_m:.2f}m "
                    f"agl={collision_result.agl_altitude:.2f}m"
                )

            if collision_result.is_colliding:
                # Prepare ground collision (apply ground forces BEFORE update)
                self._prepare_ground_forces(state, collision_result)

        # Apply auto-trim if enabled (adjusts pitch trim to maintain vertical speed)
        if self._auto_trim_enabled and not state.on_ground:
            self._apply_auto_trim(dt, state)

        # Update flight model's trim state (critical for trim moment calculation)
        # The flight model uses state.pitch_trim and state.rudder_trim for
        # aerodynamic moment calculations, so we must sync these before update
        self.flight_model.state.pitch_trim = self._pitch_trim
        self.flight_model.state.rudder_trim = self._rudder_trim

        # NOW update flight model with control inputs AND ground forces
        self.flight_model.update(dt, self.control_inputs)

        # Get updated state
        state = self.flight_model.get_state()

        # Post-update collision handling (position correction only)
        if self.collision_detector:
            collision_result = self.collision_detector.check_terrain_collision(
                state.position, state.position.y, state.velocity
            )

            if collision_result.is_colliding:
                # Correct position and velocity after integration
                self._correct_ground_position(state, collision_result)

                # Publish collision event
                self.context.message_queue.publish(
                    Message(
                        sender="physics_plugin",
                        recipients=["*"],
                        topic=MessageTopic.COLLISION_DETECTED,
                        data={
                            "type": collision_result.collision_type.value,
                            "severity": collision_result.severity.value,
                            "position": {
                                "x": state.position.x,
                                "y": state.position.y,
                                "z": state.position.z,
                            },
                            "terrain_elevation": collision_result.terrain_elevation_m,
                            "agl_altitude": collision_result.agl_altitude,
                            "distance_to_terrain": collision_result.distance_to_terrain,
                        },
                        priority=MessagePriority.HIGH,
                    )
                )

        # Publish position update
        self._publish_position_update(state)

        # Log telemetry data
        self._log_telemetry(dt, state)

    def shutdown(self) -> None:
        """Shutdown the physics plugin."""
        # Close telemetry logger
        if self.telemetry:
            self.telemetry.close()
            logger.info(f"Telemetry saved: {self.telemetry.db_path}")

        if self.context:
            # Unsubscribe from messages
            self.context.message_queue.unsubscribe(MessageTopic.CONTROL_INPUT, self.handle_message)
            self.context.message_queue.unsubscribe(
                MessageTopic.TERRAIN_UPDATED, self.handle_message
            )
            self.context.message_queue.unsubscribe("parking_brake", self.handle_message)
            self.context.message_queue.unsubscribe("input.parking_brake_set", self.handle_message)
            self.context.message_queue.unsubscribe(
                "input.parking_brake_release", self.handle_message
            )
            self.context.message_queue.unsubscribe(MessageTopic.ENGINE_STATE, self.handle_message)
            self.context.message_queue.unsubscribe("weight_balance.updated", self.handle_message)
            self.context.message_queue.unsubscribe("flight_controls.auto_trim", self.handle_message)

            # Unregister components
            if self.context.plugin_registry:
                self.context.plugin_registry.unregister("flight_model")
                self.context.plugin_registry.unregister("collision_detector")
                self.context.plugin_registry.unregister("ground_physics")

        logger.info("Physics plugin shutdown")

    def handle_message(self, message: Message) -> None:
        """Handle messages from other plugins.

        Args:
            message: Message from the queue.
        """
        if message.topic == MessageTopic.CONTROL_INPUT:
            # Update control inputs
            data = message.data

            # Get base control inputs
            pitch_input = float(data.get("pitch", 0.0))
            roll_input = float(data.get("roll", 0.0))
            yaw_input = float(data.get("yaw", 0.0))

            # Get trim values and store for telemetry
            # Note: Trim is stored separately and applied to flight model state,
            # NOT added to control inputs. Trim creates a separate aerodynamic
            # moment (via trim tab) - it doesn't change elevator deflection.
            # This allows the pilot to release the controls and let trim hold attitude.
            new_pitch_trim = float(data.get("pitch_trim", 0.0))
            new_rudder_trim = float(data.get("rudder_trim", 0.0))

            # Log when trim changes
            if abs(new_pitch_trim - self._pitch_trim) > 0.001:
                pitch_trim_deg = float(data.get("pitch_trim_deg", 0.0))
                logger.info(
                    f"[PHYSICS] Pitch trim changed: {self._pitch_trim:.3f} -> {new_pitch_trim:.3f} "
                    f"({pitch_trim_deg:.1f}°)"
                )

            self._pitch_trim = new_pitch_trim
            self._rudder_trim = new_rudder_trim

            # Set control inputs (no trim added - trim moment is calculated separately)
            self.control_inputs.pitch = pitch_input
            self.control_inputs.roll = roll_input
            self.control_inputs.yaw = yaw_input

            # Other controls (no trim)
            if "throttle" in data:
                self.control_inputs.throttle = float(data["throttle"])
            if "flaps" in data:
                self.control_inputs.flaps = float(data["flaps"])
            if "brakes" in data:
                self.control_inputs.brakes = float(data["brakes"])
            if "gear" in data:
                self.control_inputs.gear = float(data["gear"])

        elif message.topic == MessageTopic.TERRAIN_UPDATED:
            # Update terrain elevation
            data = message.data
            if "elevation" in data:
                self._terrain_elevation = float(data["elevation"])

        elif message.topic == "parking_brake":
            # Set or release parking brake (old InputManager format)
            data = message.data
            action = data.get("action", "toggle")  # Default to toggle for backward compatibility

            if action == "set":
                self.parking_brake_engaged = True
                logger.info("Parking brake SET")
            elif action == "release":
                self.parking_brake_engaged = False
                logger.info("Parking brake RELEASED")
            else:  # toggle (backward compatibility)
                self.parking_brake_engaged = not self.parking_brake_engaged
                logger.info(
                    f"Parking brake {'engaged' if self.parking_brake_engaged else 'released'}"
                )

        elif message.topic == "input.parking_brake_set":
            # Set parking brake (new InputContextManager format)
            self.parking_brake_engaged = True
            logger.info("Parking brake SET (from input context)")

        elif message.topic == "input.parking_brake_release":
            # Release parking brake (new InputContextManager format)
            self.parking_brake_engaged = False
            logger.info("Parking brake RELEASED (from input context)")

        elif message.topic == MessageTopic.ENGINE_STATE:
            # Update engine state for propeller thrust calculations
            data = message.data
            # Accept both "horsepower" (from engine) and "power_hp" (alternative)
            power_hp = data.get("horsepower") or data.get("power_hp", 0.0)
            rpm = data.get("rpm", 0.0)

            # Cache engine state for telemetry
            self._engine_rpm = float(rpm)
            self._engine_power_hp = float(power_hp)
            self._engine_running = data.get("running", False)
            self._fuel_flow_gph = data.get("fuel_flow_gph", 0.0)

            if (
                self.flight_model
                and hasattr(self.flight_model, "engine_power_hp")
                and hasattr(self.flight_model, "engine_rpm")
            ):
                # Update flight model's engine power and RPM (Simple6DOF specific)
                self.flight_model.engine_power_hp = float(power_hp)  # type: ignore[attr-defined]
                self.flight_model.engine_rpm = float(rpm)  # type: ignore[attr-defined]

                # DIAGNOSTIC: Log engine state received
                if not hasattr(self, "_engine_state_log_counter"):
                    self._engine_state_log_counter = 0
                self._engine_state_log_counter += 1

                # Log every 60 messages when receiving power
                if power_hp > 10.0 and self._engine_state_log_counter % 60 == 0:
                    logger.info(
                        f"[PHYSICS] ENGINE_STATE received: power={power_hp:.1f}HP rpm={rpm:.0f}"
                    )

        elif message.topic == "weight_balance.updated":
            # Update aircraft mass from weight & balance system
            data = message.data
            if "total_weight_lbs" in data and self.flight_model:
                # Convert pounds to kilograms
                total_weight_lbs = float(data["total_weight_lbs"])
                mass_kg = total_weight_lbs * 0.453592

                # Update flight model mass
                state = self.flight_model.get_state()
                state.mass = mass_kg

                # Update ground physics mass
                if self.ground_physics:
                    self.ground_physics.mass_kg = mass_kg

                logger.debug(f"Mass updated: {total_weight_lbs:.0f} lbs ({mass_kg:.1f} kg)")

        elif message.topic == "flight_controls.auto_trim":
            # Handle auto-trim enable/disable
            data = message.data
            enabled = data.get("enabled", False)
            # Also handle panel control state format
            if "state" in data:
                enabled = data["state"] == "ON"

            self._auto_trim_enabled = enabled
            # Capture current vertical speed as target when enabling
            if enabled and self.flight_model:
                state = self.flight_model.get_state()
                self._auto_trim_target_vspeed = state.velocity.y * 196.85  # m/s to ft/min
            logger.info(f"Auto-trim {'enabled' if enabled else 'disabled'}")

    def on_config_changed(self, config: dict[str, Any]) -> None:
        """Handle configuration changes.

        Args:
            config: New configuration dictionary.
        """
        # Update physics settings if changed
        physics_config = config.get("physics", {})

        if self.flight_model and "flight_model" in physics_config:
            # Reinitialize flight model with new config
            flight_model_config = physics_config["flight_model"]
            self.flight_model.initialize(flight_model_config)

        logger.info("Physics plugin configuration updated")

    def _prepare_ground_forces(
        self, state: AircraftState, collision: Any
    ) -> None:  # collision: CollisionResult
        """Prepare ground forces before flight model update.

        This calculates and applies ground forces as external forces so they
        are properly integrated in the flight model's physics update.

        Args:
            state: Aircraft state.
            collision: Collision result from terrain collision detector.
        """
        # Mark as on ground
        state.on_ground = True

        # Apply realistic ground physics when on ground
        if self.ground_physics:
            # Calculate ground speed (horizontal velocity magnitude)
            ground_velocity = Vector3(state.velocity.x, 0.0, state.velocity.z)
            ground_speed_mps = ground_velocity.magnitude()

            # Calculate heading from velocity vector
            import math

            heading_deg = math.degrees(math.atan2(state.velocity.x, state.velocity.z))

            # Create ground contact state
            contact = GroundContact(
                on_ground=True,
                gear_compression=1.0,  # Full compression when on ground
                surface_type="asphalt",  # Default to asphalt
                ground_speed_mps=ground_speed_mps,
                heading_deg=heading_deg,
                ground_friction=0.8,
            )

            # Use parking brake or regular brakes
            brake_input = 1.0 if self.parking_brake_engaged else self.control_inputs.brakes

            # Calculate ground forces
            ground_forces = self.ground_physics.calculate_ground_forces(
                contact=contact,
                rudder_input=self.control_inputs.yaw,
                brake_input=brake_input,
                velocity=ground_velocity,
            )

            # Apply ground forces to flight model as external forces
            # These will be integrated in the next update() call
            self.flight_model.apply_force(ground_forces.total_force, Vector3.zero())

    def _correct_ground_position(
        self, state: AircraftState, collision: Any
    ) -> None:  # collision: CollisionResult
        """Correct aircraft position after physics update to prevent ground penetration.

        Args:
            state: Aircraft state (after update).
            collision: Collision result from terrain collision detector.
        """
        # Prevent aircraft from going below ground
        if state.position.y <= collision.terrain_elevation_m:
            state.position.y = collision.terrain_elevation_m
            state.on_ground = True

            # Stop vertical velocity if moving downward
            if state.velocity.y < 0.0:
                state.velocity.y = 0.0

    def _publish_position_update(self, state: AircraftState) -> None:
        """Publish position update message.

        Args:
            state: Aircraft state.
        """
        if not self.context:
            return

        self.context.message_queue.publish(
            Message(
                sender="physics_plugin",
                recipients=["*"],
                topic=MessageTopic.POSITION_UPDATED,
                data={
                    "position": {
                        "x": state.position.x,
                        "y": state.position.y,
                        "z": state.position.z,
                    },
                    "velocity": {
                        "x": state.velocity.x,
                        "y": state.velocity.y,
                        "z": state.velocity.z,
                    },
                    "acceleration": {
                        "x": state.acceleration.x,
                        "y": state.acceleration.y,
                        "z": state.acceleration.z,
                    },
                    "rotation": {
                        "pitch": state.rotation.x,
                        "roll": state.rotation.y,
                        "yaw": state.rotation.z,
                    },
                    "angular_velocity": {
                        "x": state.angular_velocity.x,
                        "y": state.angular_velocity.y,
                        "z": state.angular_velocity.z,
                    },
                    "airspeed": state.get_airspeed() * 1.94384,  # Convert m/s to knots
                    "altitude": state.position.y * 3.28084,  # Convert meters to feet
                    "heading": state.rotation.z * 57.2958,  # Convert radians to degrees (yaw)
                    "vspeed": state.velocity.y * 196.85,  # Convert m/s to ft/min
                    "bank": state.rotation.y * 57.2958,  # Convert radians to degrees (roll)
                    "pitch": state.rotation.x * 57.2958,  # Convert radians to degrees
                    "groundspeed": self._calculate_groundspeed(state),  # For rolling sound
                    "mass": state.mass,
                    "fuel": state.fuel,
                    "on_ground": state.on_ground,
                    # Angle of attack for stall warning system
                    "angle_of_attack_deg": (
                        self.flight_model.angle_of_attack_deg
                        if hasattr(self.flight_model, "angle_of_attack_deg")
                        else None
                    ),
                    # For audio system
                    "forward": {"x": 0.0, "y": 0.0, "z": 1.0},  # TODO: Calculate from rotation
                    "up": {"x": 0.0, "y": 1.0, "z": 0.0},  # TODO: Calculate from rotation
                },
                priority=MessagePriority.HIGH,
            )
        )

    def _calculate_groundspeed(self, state: AircraftState) -> float:
        """Calculate ground speed in knots from horizontal velocity.

        Args:
            state: Aircraft state.

        Returns:
            Ground speed in knots.
        """
        # Ground speed = horizontal velocity magnitude (ignore vertical component)
        ground_velocity = Vector3(state.velocity.x, 0.0, state.velocity.z)
        ground_speed_mps = ground_velocity.magnitude()

        # Convert m/s to knots (1 m/s = 1.94384 knots)
        ground_speed_knots = ground_speed_mps * 1.94384

        return ground_speed_knots

    def _log_telemetry(self, dt: float, state: AircraftState) -> None:
        """Log telemetry data to SQLite database.

        Args:
            dt: Delta time since last update
            state: Current aircraft state
        """
        if not self.telemetry or not self.flight_model:
            return

        # Calculate airspeeds
        airspeed_mps = state.velocity.magnitude()
        airspeed_kts = airspeed_mps * 1.94384
        groundspeed_mps = Vector3(state.velocity.x, 0.0, state.velocity.z).magnitude()
        vertical_speed_mps = state.velocity.y
        vertical_speed_fpm = vertical_speed_mps * 196.85  # m/s to ft/min

        # Get propeller data if available
        propeller_rpm = None
        advance_ratio = None
        propeller_efficiency = None
        thrust_correction = None
        thrust_n = None

        if self.propeller and hasattr(self.flight_model, "engine_rpm"):
            propeller_rpm = getattr(self.flight_model, "engine_rpm", 0.0)
            if propeller_rpm > 0 and hasattr(self.propeller, "get_advance_ratio"):
                advance_ratio = self.propeller.get_advance_ratio(airspeed_mps, propeller_rpm)
                propeller_efficiency = self.propeller.get_efficiency(airspeed_mps, propeller_rpm)

                # Get thrust correction if available
                if hasattr(self.propeller, "_get_static_thrust_correction"):
                    thrust_correction = self.propeller._get_static_thrust_correction(advance_ratio)

                # Calculate thrust
                if hasattr(self.flight_model, "engine_power_hp"):
                    engine_power_hp = getattr(self.flight_model, "engine_power_hp", 0.0)
                    thrust_n = self.propeller.calculate_thrust(
                        power_hp=engine_power_hp,
                        rpm=propeller_rpm,
                        airspeed_mps=airspeed_mps,
                        air_density_kgm3=1.225,  # TODO: Get from environment
                    )

        # Get flight model forces (Simple6DOF specific)
        lift_n = None
        drag_parasite_n = None
        drag_induced_n = None
        drag_total_n = None
        lift_coefficient = None
        angle_of_attack_deg = None

        if hasattr(self.flight_model, "forces"):
            lift_n = (
                self.flight_model.forces.lift.magnitude() if self.flight_model.forces.lift else None
            )
            drag_total_n = (
                self.flight_model.forces.drag.magnitude() if self.flight_model.forces.drag else None
            )

        if hasattr(self.flight_model, "drag_parasite_n"):
            drag_parasite_n = self.flight_model.drag_parasite_n
        if hasattr(self.flight_model, "drag_induced_n"):
            drag_induced_n = self.flight_model.drag_induced_n
        if hasattr(self.flight_model, "lift_coefficient"):
            lift_coefficient = self.flight_model.lift_coefficient
        if hasattr(self.flight_model, "angle_of_attack_deg"):
            angle_of_attack_deg = self.flight_model.angle_of_attack_deg

        # Get ground forces
        rolling_resistance_n = None
        ground_friction_coeff = None

        if self.ground_physics and state.on_ground:
            # Create ground contact for force calculation
            from airborne.physics.ground_physics import GroundContact

            contact = GroundContact(
                on_ground=state.on_ground,
                ground_speed_mps=groundspeed_mps,
                heading_deg=math.degrees(state.rotation.z),
                gear_compression=1.0 if state.on_ground else 0.0,
            )

            # Calculate ground forces to get rolling resistance
            ground_forces = self.ground_physics.calculate_ground_forces(
                contact,
                rudder_input=self.control_inputs.yaw,
                brake_input=self.control_inputs.brakes,
                velocity=state.velocity,
            )
            rolling_resistance_n = ground_forces.rolling_resistance.magnitude()
            ground_friction_coeff = contact.ground_friction

        # Build telemetry data dictionary
        data = {
            "dt": dt,
            # Position and orientation
            "position_x": state.position.x,
            "position_y": state.position.y,
            "position_z": state.position.z,
            "heading_deg": math.degrees(state.rotation.z),  # yaw -> heading
            "pitch_deg": math.degrees(state.rotation.x),  # pitch
            "roll_deg": math.degrees(state.rotation.y),  # roll
            # Velocity
            "velocity_x": state.velocity.x,
            "velocity_y": state.velocity.y,
            "velocity_z": state.velocity.z,
            "airspeed_mps": airspeed_mps,
            "airspeed_kts": airspeed_kts,
            "groundspeed_mps": groundspeed_mps,
            "vertical_speed_mps": vertical_speed_mps,
            "vertical_speed_fpm": vertical_speed_fpm,
            # State flags
            "on_ground": 1 if state.on_ground else 0,
            "parking_brake": 1 if self.parking_brake_engaged else 0,
            "gear_down": 1,  # Fixed gear always down
            # Control inputs
            "throttle": self.control_inputs.throttle,
            "aileron": self.control_inputs.roll,
            "elevator": self.control_inputs.pitch,
            "rudder": self.control_inputs.yaw,
            "flaps": self.control_inputs.flaps,
            "brake": self.control_inputs.brakes,
            # Trim settings
            "pitch_trim": self._pitch_trim,
            "rudder_trim": self._rudder_trim,
            # Engine
            "engine_running": 1 if self._engine_running else 0,
            "engine_rpm": self._engine_rpm,
            "engine_power_hp": self._engine_power_hp,
            "engine_power_watts": self._engine_power_hp * 745.7 if self._engine_power_hp else None,
            "fuel_flow_gph": self._fuel_flow_gph,
            "fuel_remaining_gallons": self._fuel_remaining_gallons,
            # Propeller
            "propeller_rpm": propeller_rpm,
            "advance_ratio": advance_ratio,
            "propeller_efficiency": propeller_efficiency,
            "thrust_correction": thrust_correction,
            "thrust_n": thrust_n,
            # Aerodynamic forces
            "lift_n": lift_n,
            "drag_parasite_n": drag_parasite_n,
            "drag_induced_n": drag_induced_n,
            "drag_total_n": drag_total_n,
            "lift_coefficient": lift_coefficient,
            "angle_of_attack_deg": angle_of_attack_deg,
            # Ground forces
            "rolling_resistance_n": rolling_resistance_n,
            "ground_friction_coeff": ground_friction_coeff,
            # Environmental
            "air_density_kgm3": 1.225,  # TODO: Get from environment system
        }

        # Log to telemetry system
        self.telemetry.log(data)

        # Log detailed force vectors for physics debugging (only at high speeds to reduce overhead)
        if state.get_airspeed() > 25.0:  # 25 m/s ~= 49 knots
            forces = self.flight_model.get_forces()

            force_data = {
                # Thrust vector
                "thrust_x": forces.thrust.x,
                "thrust_y": forces.thrust.y,
                "thrust_z": forces.thrust.z,
                "thrust_mag": forces.thrust.magnitude(),
                # Drag vector
                "drag_x": forces.drag.x,
                "drag_y": forces.drag.y,
                "drag_z": forces.drag.z,
                "drag_mag": forces.drag.magnitude(),
                # Lift vector
                "lift_x": forces.lift.x,
                "lift_y": forces.lift.y,
                "lift_z": forces.lift.z,
                "lift_mag": forces.lift.magnitude(),
                # Weight vector
                "weight_x": forces.weight.x,
                "weight_y": forces.weight.y,
                "weight_z": forces.weight.z,
                "weight_mag": forces.weight.magnitude(),
                # External forces
                "external_x": self.flight_model.external_force.x,
                "external_y": self.flight_model.external_force.y,
                "external_z": self.flight_model.external_force.z,
                "external_mag": self.flight_model.external_force.magnitude(),
                # Total force
                "total_x": forces.total.x,
                "total_y": forces.total.y,
                "total_z": forces.total.z,
                "total_mag": forces.total.magnitude(),
                # Acceleration from F=ma
                "accel_from_forces_x": forces.total.x / state.mass,
                "accel_from_forces_y": forces.total.y / state.mass,
                "accel_from_forces_z": forces.total.z / state.mass,
                "accel_from_forces_mag": forces.total.magnitude() / state.mass,
                # Actual state acceleration
                "actual_accel_x": state.acceleration.x,
                "actual_accel_y": state.acceleration.y,
                "actual_accel_z": state.acceleration.z,
                "actual_accel_mag": state.acceleration.magnitude(),
            }

            self.telemetry.log_forces(force_data)

    def _apply_auto_trim(self, dt: float, state: AircraftState) -> None:
        """Apply automatic pitch trim to maintain vertical speed.

        Args:
            dt: Delta time in seconds.
            state: Current aircraft state.
        """
        # Get current vertical speed in ft/min
        current_vspeed_fpm = state.velocity.y * 196.85

        # Calculate error from target vertical speed
        vspeed_error = self._auto_trim_target_vspeed - current_vspeed_fpm

        # Proportional trim adjustment based on error
        # Positive error (below target) = need to pitch up = positive trim
        # Negative error (above target) = need to pitch down = negative trim
        trim_adjustment = vspeed_error * 0.0001 * dt  # Small proportional gain

        # Clamp adjustment rate
        max_adjustment = self._auto_trim_rate * dt
        trim_adjustment = max(-max_adjustment, min(max_adjustment, trim_adjustment))

        # Apply to pitch trim (will be used in next control input message)
        self._pitch_trim = max(-1.0, min(1.0, self._pitch_trim + trim_adjustment))

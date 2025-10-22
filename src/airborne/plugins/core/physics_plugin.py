"""Physics plugin for the AirBorne flight simulator.

This plugin wraps the physics system (flight model and collision detection),
making it available to other plugins through the plugin context.

Typical usage:
    The physics plugin is loaded automatically by the plugin loader and provides
    physics services to other plugins via the component registry.
"""

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
        propeller_config = context.config.get("propeller", {})
        if propeller_config:
            propeller_type = propeller_config.get("type", "fixed_pitch")
            if propeller_type == "fixed_pitch":
                self.propeller = FixedPitchPropeller(
                    diameter_m=propeller_config.get("diameter_m", 1.905),
                    pitch_ratio=propeller_config.get("pitch_ratio", 0.6),
                    efficiency_static=propeller_config.get("efficiency_static", 0.50),
                    efficiency_cruise=propeller_config.get("efficiency_cruise", 0.80),
                    cruise_advance_ratio=propeller_config.get("cruise_advance_ratio", 0.6),
                )
                # Attach propeller to flight model
                if hasattr(self.flight_model, "propeller"):
                    self.flight_model.propeller = self.propeller
                    logger.info("Propeller model attached to flight model")
            else:
                logger.warning(f"Unknown propeller type: {propeller_type}")

        # Create collision detector (without elevation service for now)
        # Elevation service will be provided by terrain plugin if available
        self.collision_detector = TerrainCollisionDetector(elevation_service=None)

        # Create ground physics with aircraft mass from flight model config
        aircraft_mass_kg = (
            flight_model_config.get("weight_lbs", 2450.0) * 0.453592
        )  # Convert lbs to kg
        self.ground_physics = GroundPhysics(
            mass_kg=aircraft_mass_kg,
            max_brake_force_n=15000.0,  # Cessna 172 brake force
            max_steering_angle_deg=60.0,  # Nosewheel steering angle
        )
        logger.info(f"Ground physics initialized with mass={aircraft_mass_kg:.1f} kg")

        # Initialize parking brake from initial state if available
        initial_state = context.config.get("aircraft", {}).get("initial_state", {})
        controls_state = initial_state.get("controls", {})
        self.parking_brake_engaged = controls_state.get("parking_brake", False)
        logger.info(f"Parking brake initial state: {self.parking_brake_engaged}")

        # Register components in registry
        if context.plugin_registry:
            context.plugin_registry.register("flight_model", self.flight_model)
            context.plugin_registry.register("collision_detector", self.collision_detector)
            context.plugin_registry.register("ground_physics", self.ground_physics)

        # Subscribe to control input messages and parking brake toggle
        context.message_queue.subscribe(MessageTopic.CONTROL_INPUT, self.handle_message)
        context.message_queue.subscribe("parking_brake", self.handle_message)

        # Subscribe to terrain updates
        context.message_queue.subscribe(MessageTopic.TERRAIN_UPDATED, self.handle_message)

        # Subscribe to engine state (to get power and RPM for propeller calculations)
        context.message_queue.subscribe(MessageTopic.ENGINE_STATE, self.handle_message)

        logger.info("Physics plugin initialized")

    def update(self, dt: float) -> None:
        """Update physics simulation.

        Args:
            dt: Delta time in seconds since last update.
        """
        if not self.flight_model or not self.context:
            return

        # Update flight model with control inputs
        self.flight_model.update(dt, self.control_inputs)

        # Get current state
        state = self.flight_model.get_state()

        # Check for terrain collision
        if self.collision_detector:
            collision_result = self.collision_detector.check_terrain_collision(
                state.position, state.position.y, state.velocity
            )

            if collision_result.is_colliding:
                # Handle ground collision
                self._handle_ground_collision(state, collision_result)

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

    def shutdown(self) -> None:
        """Shutdown the physics plugin."""
        if self.context:
            # Unsubscribe from messages
            self.context.message_queue.unsubscribe(MessageTopic.CONTROL_INPUT, self.handle_message)
            self.context.message_queue.unsubscribe(
                MessageTopic.TERRAIN_UPDATED, self.handle_message
            )
            self.context.message_queue.unsubscribe("parking_brake", self.handle_message)
            self.context.message_queue.unsubscribe(MessageTopic.ENGINE_STATE, self.handle_message)

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

            if "pitch" in data:
                self.control_inputs.pitch = float(data["pitch"])
            if "roll" in data:
                self.control_inputs.roll = float(data["roll"])
            if "yaw" in data:
                self.control_inputs.yaw = float(data["yaw"])
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
            # Toggle parking brake
            self.parking_brake_engaged = not self.parking_brake_engaged
            logger.info(f"Parking brake {'engaged' if self.parking_brake_engaged else 'released'}")

        elif message.topic == MessageTopic.ENGINE_STATE:
            # Update engine state for propeller thrust calculations
            data = message.data
            if "power_hp" in data and "rpm" in data and hasattr(self.flight_model, "engine_power_hp"):
                # Update flight model's engine power and RPM
                self.flight_model.engine_power_hp = float(data["power_hp"])
                self.flight_model.engine_rpm = float(data["rpm"])

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

    def _handle_ground_collision(
        self, state: AircraftState, collision: Any
    ) -> None:  # collision: CollisionResult
        """Handle ground collision.

        Args:
            state: Aircraft state.
            collision: Collision result from terrain collision detector.
        """
        # Prevent aircraft from going below ground
        if state.position.y < collision.terrain_elevation_m:
            state.position.y = collision.terrain_elevation_m
            state.on_ground = True

            # Stop vertical velocity
            state.velocity.y = max(0.0, state.velocity.y)

            # Apply realistic ground physics when on ground
            if state.on_ground and self.ground_physics:
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

                # Apply ground forces to aircraft state (convert N to acceleration)
                # F = ma, so a = F/m
                if self.ground_physics.mass_kg > 0:
                    ground_accel = ground_forces.total_force * (1.0 / self.ground_physics.mass_kg)
                    state.acceleration.x += ground_accel.x
                    state.acceleration.z += ground_accel.z

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
                    "airspeed": state.get_airspeed(),
                    "groundspeed": self._calculate_groundspeed(state),  # For rolling sound
                    "mass": state.mass,
                    "fuel": state.fuel,
                    "on_ground": state.on_ground,
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

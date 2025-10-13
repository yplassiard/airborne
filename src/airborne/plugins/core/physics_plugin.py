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
from airborne.physics.collision import CollisionDetector
from airborne.physics.flight_model.base import AircraftState, ControlInputs, IFlightModel
from airborne.physics.flight_model.simple_6dof import Simple6DOFFlightModel

logger = get_logger(__name__)


class PhysicsPlugin(IPlugin):
    """Physics plugin that manages flight model and collision detection.

    This plugin wraps the flight model and collision detector, making them
    available to other plugins. It receives control inputs via messages and
    publishes position updates every frame.

    The plugin provides:
    - flight_model: IFlightModel instance
    - collision_detector: CollisionDetector instance
    """

    def __init__(self) -> None:
        """Initialize physics plugin."""
        self.context: PluginContext | None = None
        self.flight_model: IFlightModel | None = None
        self.collision_detector: CollisionDetector | None = None

        # Control inputs (updated via messages)
        self.control_inputs = ControlInputs()

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

        # Create collision detector
        self.collision_detector = CollisionDetector()

        # Register components in registry
        if context.plugin_registry:
            context.plugin_registry.register("flight_model", self.flight_model)
            context.plugin_registry.register("collision_detector", self.collision_detector)

        # Subscribe to control input messages
        context.message_queue.subscribe(MessageTopic.CONTROL_INPUT, self.handle_message)

        # Subscribe to terrain updates
        context.message_queue.subscribe(MessageTopic.TERRAIN_UPDATED, self.handle_message)

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

        # Check for ground collision
        if self.collision_detector:
            ground_collision = self.collision_detector.check_ground_collision(
                state.position, self._terrain_elevation
            )

            if ground_collision.collided:
                # Handle ground collision
                self._handle_ground_collision(state, ground_collision)

                # Publish collision event
                self.context.message_queue.publish(
                    Message(
                        sender="physics_plugin",
                        recipients=["*"],
                        topic=MessageTopic.COLLISION_DETECTED,
                        data={
                            "type": "ground",
                            "position": {
                                "x": state.position.x,
                                "y": state.position.y,
                                "z": state.position.z,
                            },
                            "contact_point": {
                                "x": ground_collision.contact_point.x,
                                "y": ground_collision.contact_point.y,
                                "z": ground_collision.contact_point.z,
                            },
                            "penetration_depth": ground_collision.penetration_depth,
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

            # Unregister components
            if self.context.plugin_registry:
                self.context.plugin_registry.unregister("flight_model")
                self.context.plugin_registry.unregister("collision_detector")

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
            collision: Collision result (unused for now).
        """
        _ = collision  # Mark as intentionally unused
        # Prevent aircraft from going below ground
        if state.position.y < self._terrain_elevation:
            state.position.y = self._terrain_elevation
            state.on_ground = True

            # Stop vertical velocity
            state.velocity.y = max(0.0, state.velocity.y)

            # Apply friction to horizontal velocity when on ground
            if state.on_ground:
                friction_factor = 0.95  # 5% velocity loss per frame
                state.velocity.x *= friction_factor
                state.velocity.z *= friction_factor

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

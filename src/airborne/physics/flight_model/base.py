"""Abstract flight model interface.

This module defines the interface for flight models that simulate aircraft
dynamics. Flight models calculate forces, moments, and state updates based
on control inputs and current conditions.

Typical usage example:
    from airborne.physics.flight_model.base import IFlightModel

    class MyFlightModel(IFlightModel):
        def update(self, dt: float, inputs: ControlInputs) -> AircraftState:
            # Calculate forces and update state
            pass
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from airborne.physics.vectors import Vector3


@dataclass
class ControlInputs:
    """Control surface positions and engine controls.

    All values normalized to -1.0 to 1.0 range (or 0.0 to 1.0 for throttle).

    Attributes:
        pitch: Elevator input (-1.0 = full down, 1.0 = full up).
        roll: Aileron input (-1.0 = full left, 1.0 = full right).
        yaw: Rudder input (-1.0 = full left, 1.0 = full right).
        throttle: Throttle position (0.0 = idle, 1.0 = full power).
        flaps: Flap position (0.0 = retracted, 1.0 = fully extended).
        brakes: Brake application (0.0 = off, 1.0 = full brakes).
        gear: Landing gear (0.0 = up, 1.0 = down).
    """

    pitch: float = 0.0
    roll: float = 0.0
    yaw: float = 0.0
    throttle: float = 0.0
    flaps: float = 0.0
    brakes: float = 0.0
    gear: float = 1.0  # Default: gear down

    def __post_init__(self) -> None:
        """Clamp all inputs to valid ranges."""
        self.pitch = max(-1.0, min(1.0, self.pitch))
        self.roll = max(-1.0, min(1.0, self.roll))
        self.yaw = max(-1.0, min(1.0, self.yaw))
        self.throttle = max(0.0, min(1.0, self.throttle))
        self.flaps = max(0.0, min(1.0, self.flaps))
        self.brakes = max(0.0, min(1.0, self.brakes))
        self.gear = max(0.0, min(1.0, self.gear))


@dataclass
class AircraftState:
    """Complete aircraft state for physics simulation.

    Uses efficient storage and provides cached computed properties.

    Attributes:
        position: Position in world space (meters).
        velocity: Velocity vector (m/s).
        acceleration: Acceleration vector (m/s²).
        rotation: Euler angles (pitch, roll, yaw) in radians.
        angular_velocity: Angular velocity (rad/s).
        mass: Current mass including fuel (kg).
        fuel: Fuel remaining (kg).
        on_ground: Whether aircraft is on the ground.
    """

    position: Vector3 = field(default_factory=Vector3.zero)
    velocity: Vector3 = field(default_factory=Vector3.zero)
    acceleration: Vector3 = field(default_factory=Vector3.zero)
    rotation: Vector3 = field(default_factory=Vector3.zero)  # pitch, roll, yaw
    angular_velocity: Vector3 = field(default_factory=Vector3.zero)
    mass: float = 1000.0
    fuel: float = 100.0
    on_ground: bool = False

    # Cached properties for efficiency
    _airspeed: float = field(default=0.0, init=False, repr=False)
    _airspeed_dirty: bool = field(default=True, init=False, repr=False)

    def get_airspeed(self) -> float:
        """Get airspeed (magnitude of velocity).

        Returns:
            Airspeed in m/s.

        Note:
            Cached for performance - only recalculated when velocity changes.
        """
        if self._airspeed_dirty:
            self._airspeed = self.velocity.magnitude()
            self._airspeed_dirty = False
        return self._airspeed

    def mark_velocity_dirty(self) -> None:
        """Mark velocity as changed to recalculate cached values.

        Call this whenever velocity is modified directly.
        """
        self._airspeed_dirty = True

    def get_altitude(self) -> float:
        """Get altitude (Y component of position).

        Returns:
            Altitude in meters.
        """
        return self.position.y

    def get_heading(self) -> float:
        """Get heading (yaw angle).

        Returns:
            Heading in radians.
        """
        return self.rotation.z

    def get_pitch(self) -> float:
        """Get pitch angle.

        Returns:
            Pitch in radians.
        """
        return self.rotation.x

    def get_roll(self) -> float:
        """Get roll angle.

        Returns:
            Roll in radians.
        """
        return self.rotation.y


@dataclass
class FlightForces:
    """Forces and moments acting on the aircraft.

    Optimized for frequent updates during physics simulation.

    Attributes:
        lift: Lift force vector (N).
        drag: Drag force vector (N).
        thrust: Thrust force vector (N).
        weight: Weight force vector (N).
        total: Total force vector (N).
    """

    lift: Vector3 = field(default_factory=Vector3.zero)
    drag: Vector3 = field(default_factory=Vector3.zero)
    thrust: Vector3 = field(default_factory=Vector3.zero)
    weight: Vector3 = field(default_factory=Vector3.zero)
    total: Vector3 = field(default_factory=Vector3.zero)

    def calculate_total(self) -> None:
        """Calculate total force from components.

        Updates the total field in-place for efficiency.
        """
        # In-place addition for performance
        self.total = self.lift + self.drag + self.thrust + self.weight


class IFlightModel(ABC):
    """Abstract interface for flight models.

    Flight models implement aircraft dynamics, calculating forces and updating
    state based on control inputs. Implementations should be optimized for
    performance as update() is called every physics frame (60Hz).

    Performance considerations:
    - Minimize allocations in update()
    - Cache computed values when possible
    - Use in-place operations for vectors
    - Avoid expensive math operations (sin, cos, sqrt) when possible

    Examples:
        >>> model = Simple6DOFFlightModel(config)
        >>> inputs = ControlInputs(throttle=0.8, pitch=0.1)
        >>> state = model.update(dt=0.016, inputs=inputs)
        >>> print(f"Altitude: {state.get_altitude():.1f}m")
    """

    @abstractmethod
    def initialize(self, config: dict) -> None:
        """Initialize the flight model.

        Args:
            config: Configuration dictionary with model parameters.

        Raises:
            ValueError: If configuration is invalid.

        Examples:
            >>> config = {
            ...     "wing_area_sqft": 174.0,
            ...     "weight_lbs": 2400.0,
            ...     "drag_coefficient": 0.027,
            ... }
            >>> model.initialize(config)
        """

    @abstractmethod
    def update(self, dt: float, inputs: ControlInputs) -> AircraftState:
        """Update flight model for one physics step.

        This is called every physics frame (typically 60Hz) and must be
        efficient. Avoid allocations and expensive operations.

        Args:
            dt: Time step in seconds (typically 1/60 = 0.016).
            inputs: Control inputs for this frame.

        Returns:
            Updated aircraft state.

        Examples:
            >>> state = model.update(0.016, ControlInputs(throttle=0.7))
        """

    @abstractmethod
    def get_state(self) -> AircraftState:
        """Get current aircraft state.

        Returns:
            Current state (should be a reference, not a copy).

        Note:
            Returns reference for efficiency - do not modify directly.
        """

    @abstractmethod
    def reset(self, initial_state: AircraftState) -> None:
        """Reset flight model to a new state.

        Args:
            initial_state: New initial state.

        Examples:
            >>> state = AircraftState(
            ...     position=Vector3(0, 1000, 0),
            ...     velocity=Vector3(50, 0, 0)
            ... )
            >>> model.reset(state)
        """

    @abstractmethod
    def apply_force(self, force: Vector3, position: Vector3) -> None:
        """Apply an external force at a specific position.

        Args:
            force: Force vector in Newtons.
            position: Position relative to center of mass.

        Note:
            Used for external forces like wind gusts, collisions.

        Examples:
            >>> # Apply wind gust
            >>> model.apply_force(Vector3(100, 0, 50), Vector3(0, 0, 0))
        """

    def get_forces(self) -> FlightForces:
        """Get current forces acting on aircraft.

        Returns:
            Current flight forces.

        Note:
            Optional - default implementation returns empty forces.
            Override for debugging/visualization.
        """
        return FlightForces()

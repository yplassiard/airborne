"""Leading-edge slat systems.

This module implements leading-edge slats for STOL aircraft.
Automatic slats deploy based on angle of attack to delay stall
and increase maximum lift coefficient.

The CH701 uses automatic leading-edge slats that deploy at high AOA,
extending the wing's usable lift range and providing excellent
STOL performance.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


class SlatType(Enum):
    """Types of leading-edge slat systems."""

    AUTOMATIC = "automatic"  # Deploy based on AOA (aerodynamic pressure)
    MANUAL = "manual"  # Pilot-controlled
    FIXED = "fixed"  # Always deployed (leading edge droop)


@dataclass
class SlatsState:
    """Current state of the slat system.

    Attributes:
        position: Slat position (0.0 = retracted, 1.0 = fully deployed).
        left_position: Left slat position (may differ in asymmetric conditions).
        right_position: Right slat position.
        cl_bonus: Current lift coefficient bonus from slats.
        stall_aoa_extension_deg: Current stall AOA extension in degrees.
        drag_penalty: Current drag coefficient increase from slats.
        is_deploying: True if slats are currently extending.
        is_retracting: True if slats are currently retracting.
    """

    position: float = 0.0
    left_position: float = 0.0
    right_position: float = 0.0
    cl_bonus: float = 0.0
    stall_aoa_extension_deg: float = 0.0
    drag_penalty: float = 0.0
    is_deploying: bool = False
    is_retracting: bool = False


class ISlats(ABC):
    """Abstract interface for slat systems.

    Slats are leading-edge high-lift devices that increase maximum
    lift coefficient and delay stall by allowing higher angles of attack.
    """

    @abstractmethod
    def get_slat_position(self) -> float:
        """Get current slat position.

        Returns:
            Position from 0.0 (retracted) to 1.0 (fully deployed).
        """

    @abstractmethod
    def get_state(self) -> SlatsState:
        """Get complete slat system state.

        Returns:
            Current slat system state.
        """

    @abstractmethod
    def update(self, angle_of_attack_deg: float, airspeed_mps: float, dt: float) -> None:
        """Update slat system state.

        Args:
            angle_of_attack_deg: Current angle of attack in degrees.
            airspeed_mps: Current airspeed in meters per second.
            dt: Time step in seconds.
        """

    @abstractmethod
    def get_cl_bonus(self) -> float:
        """Get current lift coefficient bonus from slats.

        Returns:
            Additional CL provided by slat deployment.
        """

    @abstractmethod
    def get_stall_aoa_extension(self) -> float:
        """Get stall AOA extension in degrees.

        Returns:
            Additional stall AOA margin from slats.
        """


class AutomaticSlats(ISlats):
    """Automatic leading-edge slats that deploy based on AOA.

    These slats are aerodynamically actuated - high angle of attack
    creates a pressure differential that deploys the slats automatically.
    This is the type used on the Zenair CH701 and similar STOL aircraft.

    Characteristics:
    - Deploy progressively as AOA increases
    - Fully deploy before stall AOA is reached
    - Retract automatically at low AOA (cruise)
    - Provide significant CL increase (~0.4-0.5)
    - Extend stall AOA by 6-10 degrees

    Examples:
        >>> slats = AutomaticSlats(
        ...     deploy_aoa_start_deg=8.0,
        ...     deploy_aoa_full_deg=14.0,
        ...     max_cl_bonus=0.45,
        ...     max_stall_extension_deg=8.0,
        ... )
        >>> slats.update(angle_of_attack_deg=12.0, airspeed_mps=30.0, dt=0.016)
        >>> print(f"Slat position: {slats.get_slat_position():.2f}")
    """

    def __init__(
        self,
        deploy_aoa_start_deg: float = 8.0,
        deploy_aoa_full_deg: float = 14.0,
        max_cl_bonus: float = 0.45,
        max_stall_extension_deg: float = 8.0,
        deploy_rate: float = 2.0,
        retract_rate: float = 1.5,
        min_deploy_airspeed_mps: float = 10.0,
        max_drag_penalty: float = 0.02,
    ):
        """Initialize automatic slats.

        Args:
            deploy_aoa_start_deg: AOA at which slats begin to deploy.
            deploy_aoa_full_deg: AOA at which slats are fully deployed.
            max_cl_bonus: Maximum CL increase when fully deployed.
            max_stall_extension_deg: Maximum stall AOA extension when deployed.
            deploy_rate: Deployment rate (full deploy per second).
            retract_rate: Retraction rate (full retract per second).
            min_deploy_airspeed_mps: Minimum airspeed for slat deployment.
            max_drag_penalty: Maximum drag coefficient increase when deployed.
        """
        self.deploy_aoa_start = deploy_aoa_start_deg
        self.deploy_aoa_full = deploy_aoa_full_deg
        self.max_cl_bonus = max_cl_bonus
        self.max_stall_extension = max_stall_extension_deg
        self.deploy_rate = deploy_rate
        self.retract_rate = retract_rate
        self.min_deploy_airspeed = min_deploy_airspeed_mps
        self.max_drag_penalty = max_drag_penalty

        # Current state
        self._position = 0.0
        self._left_position = 0.0
        self._right_position = 0.0
        self._target_position = 0.0
        self._is_deploying = False
        self._is_retracting = False

        logger.info(
            "AutomaticSlats initialized: deploy AOA %.1f-%.1f°, CL bonus %.2f",
            deploy_aoa_start_deg,
            deploy_aoa_full_deg,
            max_cl_bonus,
        )

    def get_slat_position(self) -> float:
        """Get current slat position."""
        return self._position

    def get_state(self) -> SlatsState:
        """Get complete slat system state."""
        return SlatsState(
            position=self._position,
            left_position=self._left_position,
            right_position=self._right_position,
            cl_bonus=self.get_cl_bonus(),
            stall_aoa_extension_deg=self.get_stall_aoa_extension(),
            drag_penalty=self._position * self.max_drag_penalty,
            is_deploying=self._is_deploying,
            is_retracting=self._is_retracting,
        )

    def update(self, angle_of_attack_deg: float, airspeed_mps: float, dt: float) -> None:
        """Update slat position based on flight conditions.

        The slats deploy progressively as AOA increases, driven by
        aerodynamic pressure differential on the leading edge.

        Args:
            angle_of_attack_deg: Current angle of attack in degrees.
            airspeed_mps: Current airspeed in meters per second.
            dt: Time step in seconds.
        """
        # Calculate target position based on AOA
        if airspeed_mps < self.min_deploy_airspeed:
            # Not enough airspeed for aerodynamic deployment
            self._target_position = 0.0
        elif angle_of_attack_deg <= self.deploy_aoa_start:
            self._target_position = 0.0
        elif angle_of_attack_deg >= self.deploy_aoa_full:
            self._target_position = 1.0
        else:
            # Progressive deployment
            aoa_range = self.deploy_aoa_full - self.deploy_aoa_start
            self._target_position = (angle_of_attack_deg - self.deploy_aoa_start) / aoa_range

        # Move position toward target
        position_error = self._target_position - self._position

        if abs(position_error) < 0.001:
            # Close enough, snap to target
            self._position = self._target_position
            self._is_deploying = False
            self._is_retracting = False
        elif position_error > 0:
            # Deploying
            self._is_deploying = True
            self._is_retracting = False
            self._position = min(self._target_position, self._position + self.deploy_rate * dt)
        else:
            # Retracting
            self._is_deploying = False
            self._is_retracting = True
            self._position = max(self._target_position, self._position - self.retract_rate * dt)

        # Symmetric deployment (both sides move together)
        self._left_position = self._position
        self._right_position = self._position

    def get_cl_bonus(self) -> float:
        """Get current lift coefficient bonus.

        Returns:
            CL bonus proportional to slat deployment.
        """
        return self._position * self.max_cl_bonus

    def get_stall_aoa_extension(self) -> float:
        """Get stall AOA extension in degrees.

        Returns:
            Stall AOA extension proportional to deployment.
        """
        return self._position * self.max_stall_extension

    def get_drag_penalty(self) -> float:
        """Get drag coefficient increase from deployed slats.

        Returns:
            Drag penalty proportional to deployment.
        """
        return self._position * self.max_drag_penalty

    def reset(self) -> None:
        """Reset slats to retracted position."""
        self._position = 0.0
        self._left_position = 0.0
        self._right_position = 0.0
        self._target_position = 0.0
        self._is_deploying = False
        self._is_retracting = False

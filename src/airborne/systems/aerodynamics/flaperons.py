"""Flaperon (combined flap/aileron) systems.

This module implements flaperon systems used on many STOL aircraft.
Flaperons are control surfaces that serve dual purposes:
- Act as flaps for increased lift during takeoff/landing
- Act as ailerons for roll control

The CH701 uses full-span flaperons, providing excellent STOL performance
while maintaining good roll control throughout the flight envelope.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


class FlaperonMode(Enum):
    """Operating modes for flaperon systems."""

    CRUISE = "cruise"  # Minimal flap, full aileron authority
    TAKEOFF = "takeoff"  # Partial flap, good aileron authority
    LANDING = "landing"  # Full flap, reduced aileron authority


@dataclass
class FlaperonState:
    """Current state of the flaperon system.

    Attributes:
        flap_position: Symmetric flap component (0.0 to 1.0).
        left_surface_deg: Left flaperon deflection in degrees.
        right_surface_deg: Right flaperon deflection in degrees.
        roll_authority: Current roll authority multiplier (0.0 to 1.0).
        cl_contribution: Lift coefficient contribution from flap component.
        mode: Current operating mode.
    """

    flap_position: float = 0.0
    left_surface_deg: float = 0.0
    right_surface_deg: float = 0.0
    roll_authority: float = 1.0
    cl_contribution: float = 0.0
    mode: FlaperonMode = FlaperonMode.CRUISE


class IFlaperons(ABC):
    """Abstract interface for flaperon systems.

    Flaperons combine flap and aileron functions in a single surface.
    When used as flaps, both surfaces deflect together (symmetrically).
    When used as ailerons, surfaces deflect differentially.
    """

    @abstractmethod
    def get_flap_component(self) -> float:
        """Get current flap deflection component.

        Returns:
            Flap position from 0.0 (up) to 1.0 (full down).
        """

    @abstractmethod
    def get_roll_authority(self) -> float:
        """Get current roll authority multiplier.

        Roll authority decreases as flaps are extended because
        the surface is already deflected.

        Returns:
            Roll authority multiplier from 0.0 to 1.0.
        """

    @abstractmethod
    def get_state(self) -> FlaperonState:
        """Get complete flaperon system state.

        Returns:
            Current flaperon system state.
        """

    @abstractmethod
    def update(self, flap_command: float, roll_command: float, dt: float) -> None:
        """Update flaperon positions based on commands.

        Args:
            flap_command: Flap command (0.0 = up, 1.0 = full).
            roll_command: Roll command (-1.0 = left, 1.0 = right).
            dt: Time step in seconds.
        """


class FlaperonSystem(IFlaperons):
    """Full-span flaperon system for STOL aircraft.

    This system models flaperons that provide both flap and aileron
    functions. The surfaces move symmetrically for flap effect and
    differentially for roll control.

    Key characteristics:
    - Full-span coverage for maximum lift effect
    - Differential aileron mixing (more up than down to prevent adverse yaw)
    - Reduced roll authority at high flap settings
    - Smooth transition between modes

    The mixing formula for each surface is:
        deflection = flap_offset + roll_differential

    Where:
        flap_offset = flap_position * max_flap_deflection
        roll_differential = roll_command * available_roll_travel

    Examples:
        >>> flaperons = FlaperonSystem(
        ...     max_flap_deflection_deg=40.0,
        ...     max_aileron_deflection_deg=20.0,
        ...     differential_ratio=1.3,
        ... )
        >>> # Set half flaps with slight right roll
        >>> flaperons.update(flap_command=0.5, roll_command=0.3, dt=0.016)
        >>> state = flaperons.get_state()
        >>> print(f"Left: {state.left_surface_deg:.1f}°, Right: {state.right_surface_deg:.1f}°")
    """

    def __init__(
        self,
        max_flap_deflection_deg: float = 40.0,
        max_aileron_deflection_deg: float = 20.0,
        differential_ratio: float = 1.3,
        flap_rate_per_second: float = 0.3,
        roll_response_rate: float = 10.0,
        min_roll_authority_at_full_flap: float = 0.5,
        cl_per_flap_unit: float = 0.6,
    ):
        """Initialize flaperon system.

        Args:
            max_flap_deflection_deg: Maximum symmetric flap deflection.
            max_aileron_deflection_deg: Maximum differential (roll) deflection.
            differential_ratio: Ratio of up-going to down-going deflection
                for roll. Values > 1.0 reduce adverse yaw.
            flap_rate_per_second: How fast flaps move (0-1 per second).
            roll_response_rate: How fast roll response moves (per second).
            min_roll_authority_at_full_flap: Minimum roll authority with
                flaps fully extended (0.0 to 1.0).
            cl_per_flap_unit: CL increase per unit of flap deflection.
        """
        self.max_flap_deg = max_flap_deflection_deg
        self.max_aileron_deg = max_aileron_deflection_deg
        self.differential_ratio = differential_ratio
        self.flap_rate = flap_rate_per_second
        self.roll_rate = roll_response_rate
        self.min_roll_authority = min_roll_authority_at_full_flap
        self.cl_per_flap = cl_per_flap_unit

        # Current state
        self._flap_position = 0.0
        self._roll_position = 0.0
        self._flap_target = 0.0
        self._left_deg = 0.0
        self._right_deg = 0.0

        logger.info(
            "FlaperonSystem initialized: max_flap=%.1f°, max_aileron=%.1f°, differential=%.2f",
            max_flap_deflection_deg,
            max_aileron_deflection_deg,
            differential_ratio,
        )

    def get_flap_component(self) -> float:
        """Get current flap deflection component."""
        return self._flap_position

    def get_roll_authority(self) -> float:
        """Get current roll authority multiplier.

        Roll authority decreases linearly with flap extension.
        """
        return 1.0 - (1.0 - self.min_roll_authority) * self._flap_position

    def get_state(self) -> FlaperonState:
        """Get complete flaperon system state."""
        # Determine mode based on flap position
        if self._flap_position < 0.1:
            mode = FlaperonMode.CRUISE
        elif self._flap_position < 0.6:
            mode = FlaperonMode.TAKEOFF
        else:
            mode = FlaperonMode.LANDING

        return FlaperonState(
            flap_position=self._flap_position,
            left_surface_deg=self._left_deg,
            right_surface_deg=self._right_deg,
            roll_authority=self.get_roll_authority(),
            cl_contribution=self._flap_position * self.cl_per_flap,
            mode=mode,
        )

    def update(self, flap_command: float, roll_command: float, dt: float) -> None:
        """Update flaperon positions.

        Args:
            flap_command: Flap command (0.0 = up, 1.0 = full).
            roll_command: Roll command (-1.0 = left, 1.0 = right).
            dt: Time step in seconds.
        """
        # Clamp inputs
        flap_command = max(0.0, min(1.0, flap_command))
        roll_command = max(-1.0, min(1.0, roll_command))

        # Update flap position (slow movement)
        self._flap_target = flap_command
        flap_error = self._flap_target - self._flap_position

        if abs(flap_error) < 0.001:
            self._flap_position = self._flap_target
        elif flap_error > 0:
            self._flap_position = min(self._flap_target, self._flap_position + self.flap_rate * dt)
        else:
            self._flap_position = max(self._flap_target, self._flap_position - self.flap_rate * dt)

        # Update roll position (fast response)
        roll_error = roll_command - self._roll_position
        if abs(roll_error) < 0.01:
            self._roll_position = roll_command
        else:
            self._roll_position += roll_error * min(1.0, self.roll_rate * dt)

        # Calculate surface positions
        self._calculate_surface_positions()

    def _calculate_surface_positions(self) -> None:
        """Calculate left and right flaperon deflections.

        Combines symmetric flap deflection with differential roll.
        Uses differential ratio to reduce adverse yaw.
        """
        # Symmetric flap component (both surfaces down)
        flap_deflection = self._flap_position * self.max_flap_deg

        # Available roll travel (decreases with flap extension)
        roll_authority = self.get_roll_authority()
        available_roll = self.max_aileron_deg * roll_authority

        # Differential roll component
        # Positive roll_position = right roll = left up, right down
        if self._roll_position >= 0:
            # Right roll: left surface goes up (less), right goes down (more)
            left_roll = -self._roll_position * available_roll / self.differential_ratio
            right_roll = self._roll_position * available_roll
        else:
            # Left roll: right surface goes up (less), left goes down (more)
            left_roll = -self._roll_position * available_roll
            right_roll = self._roll_position * available_roll / self.differential_ratio

        # Combine flap and roll components
        # Positive = trailing edge down
        self._left_deg = flap_deflection + left_roll
        self._right_deg = flap_deflection + right_roll

        # Clamp to physical limits
        total_max = self.max_flap_deg + self.max_aileron_deg
        self._left_deg = max(-self.max_aileron_deg, min(total_max, self._left_deg))
        self._right_deg = max(-self.max_aileron_deg, min(total_max, self._right_deg))

    def get_surface_positions_deg(self) -> tuple[float, float]:
        """Get current surface deflections in degrees.

        Returns:
            Tuple of (left_deflection_deg, right_deflection_deg).
            Positive values = trailing edge down.
        """
        return (self._left_deg, self._right_deg)

    def reset(self) -> None:
        """Reset flaperons to neutral position."""
        self._flap_position = 0.0
        self._roll_position = 0.0
        self._flap_target = 0.0
        self._left_deg = 0.0
        self._right_deg = 0.0

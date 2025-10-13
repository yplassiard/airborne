"""Proximity audio cues for spatial awareness.

Provides beeping and audio feedback based on distance to waypoints, taxiways,
runways, and other objects. Helps pilots navigate without visual feedback.

Typical usage:
    from airborne.audio.proximity import ProximityCueManager, BeepPattern

    manager = ProximityCueManager(audio_engine)
    manager.add_target("runway_threshold", position, BeepPattern.LINEAR)
    manager.update(aircraft_position)  # Updates beep frequency based on distance
"""

import logging
import math
from dataclasses import dataclass
from enum import Enum

from airborne.physics.vectors import Vector3

logger = logging.getLogger(__name__)


class BeepPattern(Enum):
    """Beep pattern types for proximity cues."""

    LINEAR = "linear"  # Linear frequency increase as distance decreases
    EXPONENTIAL = "exponential"  # Exponential frequency increase (faster near target)
    STEPPED = "stepped"  # Step-based frequency (discrete zones)
    CONSTANT = "constant"  # Constant beep frequency (distance alarm)


@dataclass
class ProximityTarget:
    """A target for proximity-based audio cues.

    Attributes:
        target_id: Unique identifier for the target
        position: 3D position of the target (m)
        pattern: Beep pattern to use
        min_distance_m: Minimum distance for beeping (m)
        max_distance_m: Maximum distance for beeping (m)
        min_frequency_hz: Minimum beep frequency (Hz)
        max_frequency_hz: Maximum beep frequency (Hz)
        enabled: Whether this target is currently active
    """

    target_id: str
    position: Vector3
    pattern: BeepPattern = BeepPattern.LINEAR
    min_distance_m: float = 10.0
    max_distance_m: float = 500.0
    min_frequency_hz: float = 0.5
    max_frequency_hz: float = 10.0
    enabled: bool = True


class ProximityCueManager:
    """Manages proximity-based audio cues.

    Tracks multiple targets and generates beeping cues based on distance.
    Automatically adjusts beep frequency based on proximity to targets.

    Examples:
        >>> from airborne.audio.proximity import ProximityCueManager, BeepPattern
        >>> manager = ProximityCueManager()
        >>> manager.add_target("runway_27", Vector3(0, 0, 1000), BeepPattern.LINEAR)
        >>> distance, frequency = manager.get_nearest_target(Vector3(0, 0, 500))
        >>> print(f"Distance: {distance:.1f}m, Frequency: {frequency:.2f}Hz")
    """

    def __init__(self) -> None:
        """Initialize proximity cue manager."""
        self.targets: dict[str, ProximityTarget] = {}
        self.active_target_id: str | None = None
        self.current_beep_frequency: float = 0.0
        self.last_beep_time: float = 0.0

    def add_target(
        self,
        target_id: str,
        position: Vector3,
        pattern: BeepPattern = BeepPattern.LINEAR,
        min_distance_m: float = 10.0,
        max_distance_m: float = 500.0,
        min_frequency_hz: float = 0.5,
        max_frequency_hz: float = 10.0,
    ) -> None:
        """Add a proximity target.

        Args:
            target_id: Unique identifier for the target
            position: 3D position of the target
            pattern: Beep pattern to use
            min_distance_m: Minimum distance for beeping (m)
            max_distance_m: Maximum distance for beeping (m)
            min_frequency_hz: Minimum beep frequency (Hz)
            max_frequency_hz: Maximum beep frequency (Hz)

        Examples:
            >>> manager.add_target("gate_5", Vector3(100, 0, 200))
            >>> manager.add_target("taxiway_b", Vector3(50, 0, 100), BeepPattern.EXPONENTIAL)
        """
        self.targets[target_id] = ProximityTarget(
            target_id=target_id,
            position=position,
            pattern=pattern,
            min_distance_m=min_distance_m,
            max_distance_m=max_distance_m,
            min_frequency_hz=min_frequency_hz,
            max_frequency_hz=max_frequency_hz,
            enabled=True,
        )
        logger.debug("Added proximity target: %s at %s", target_id, position)

    def remove_target(self, target_id: str) -> None:
        """Remove a proximity target.

        Args:
            target_id: Target to remove

        Examples:
            >>> manager.remove_target("gate_5")
        """
        if target_id in self.targets:
            del self.targets[target_id]
            logger.debug("Removed proximity target: %s", target_id)

            # Clear active target if it was removed
            if self.active_target_id == target_id:
                self.active_target_id = None
                self.current_beep_frequency = 0.0

    def enable_target(self, target_id: str, enabled: bool = True) -> None:
        """Enable or disable a proximity target.

        Args:
            target_id: Target to enable/disable
            enabled: True to enable, False to disable

        Examples:
            >>> manager.enable_target("gate_5", False)  # Disable
            >>> manager.enable_target("gate_5", True)   # Re-enable
        """
        if target_id in self.targets:
            self.targets[target_id].enabled = enabled
            logger.debug("Target %s %s", target_id, "enabled" if enabled else "disabled")

    def clear_targets(self) -> None:
        """Clear all proximity targets.

        Examples:
            >>> manager.clear_targets()
        """
        self.targets.clear()
        self.active_target_id = None
        self.current_beep_frequency = 0.0
        logger.debug("Cleared all proximity targets")

    def get_nearest_target(self, position: Vector3) -> tuple[str | None, float, float]:
        """Get nearest enabled target and its beep frequency.

        Args:
            position: Current position to check from

        Returns:
            Tuple of (target_id, distance_m, beep_frequency_hz)
            Returns (None, inf, 0.0) if no targets in range

        Examples:
            >>> target_id, distance, frequency = manager.get_nearest_target(Vector3(0, 0, 0))
            >>> if target_id:
            ...     print(f"Nearest: {target_id} at {distance:.1f}m")
        """
        nearest_target = None
        nearest_distance = float("inf")
        nearest_frequency = 0.0

        # Find nearest enabled target
        for target in self.targets.values():
            if not target.enabled:
                continue

            distance = self._calculate_distance(position, target.position)

            # Check if within range
            if target.min_distance_m <= distance <= target.max_distance_m:
                if distance < nearest_distance:
                    nearest_target = target.target_id
                    nearest_distance = distance
                    nearest_frequency = self._calculate_frequency(distance, target)

        return nearest_target, nearest_distance, nearest_frequency

    def update(self, position: Vector3, delta_time: float = 0.0) -> bool:
        """Update proximity cues based on current position.

        Args:
            position: Current position
            delta_time: Time since last update (seconds)

        Returns:
            True if a beep should be played, False otherwise

        Examples:
            >>> should_beep = manager.update(Vector3(0, 0, 500), delta_time=0.016)
            >>> if should_beep:
            ...     play_beep_sound()
        """
        target_id, distance, frequency = self.get_nearest_target(position)

        # Update active target
        if target_id != self.active_target_id:
            self.active_target_id = target_id
            self.last_beep_time = 0.0

        self.current_beep_frequency = frequency

        # Check if we should beep
        if frequency > 0 and delta_time > 0:
            beep_interval = 1.0 / frequency
            self.last_beep_time += delta_time

            if self.last_beep_time >= beep_interval:
                self.last_beep_time = 0.0
                return True

        return False

    def get_target(self, target_id: str) -> ProximityTarget | None:
        """Get a specific target by ID.

        Args:
            target_id: Target identifier

        Returns:
            ProximityTarget or None if not found

        Examples:
            >>> target = manager.get_target("runway_27")
            >>> if target:
            ...     print(f"Target position: {target.position}")
        """
        return self.targets.get(target_id)

    def get_all_targets(self) -> list[ProximityTarget]:
        """Get all targets.

        Returns:
            List of all proximity targets

        Examples:
            >>> targets = manager.get_all_targets()
            >>> print(f"Total targets: {len(targets)}")
        """
        return list(self.targets.values())

    def get_active_target_id(self) -> str | None:
        """Get the currently active target ID.

        Returns:
            Active target ID or None

        Examples:
            >>> active = manager.get_active_target_id()
            >>> if active:
            ...     print(f"Approaching: {active}")
        """
        return self.active_target_id

    def get_current_frequency(self) -> float:
        """Get current beep frequency.

        Returns:
            Current beep frequency in Hz

        Examples:
            >>> frequency = manager.get_current_frequency()
            >>> print(f"Beep rate: {frequency:.2f} Hz")
        """
        return self.current_beep_frequency

    def _calculate_distance(self, pos1: Vector3, pos2: Vector3) -> float:
        """Calculate distance between two positions.

        Args:
            pos1: First position
            pos2: Second position

        Returns:
            Distance in meters
        """
        return (pos2 - pos1).magnitude()

    def _calculate_frequency(self, distance: float, target: ProximityTarget) -> float:
        """Calculate beep frequency based on distance and pattern.

        Args:
            distance: Distance to target (m)
            target: Proximity target

        Returns:
            Beep frequency in Hz
        """
        # Clamp distance to valid range
        distance = max(target.min_distance_m, min(distance, target.max_distance_m))

        # Normalize distance to 0-1 range (1 = closest, 0 = farthest)
        distance_range = target.max_distance_m - target.min_distance_m
        if distance_range <= 0:
            normalized = 1.0
        else:
            normalized = 1.0 - (distance - target.min_distance_m) / distance_range

        # Apply pattern
        if target.pattern == BeepPattern.LINEAR:
            factor = normalized
        elif target.pattern == BeepPattern.EXPONENTIAL:
            # Exponential curve: slower at distance, faster when close
            factor = normalized**2
        elif target.pattern == BeepPattern.STEPPED:
            # 4 discrete zones: 0-25%, 25-50%, 50-75%, 75-100%
            if normalized < 0.25:
                factor = 0.125  # Very slow
            elif normalized < 0.5:
                factor = 0.375  # Slow
            elif normalized < 0.75:
                factor = 0.625  # Medium
            else:
                factor = 0.875  # Fast
        elif target.pattern == BeepPattern.CONSTANT:
            factor = 1.0  # Always at max frequency
        else:
            factor = normalized  # Default to linear

        # Map to frequency range
        frequency_range = target.max_frequency_hz - target.min_frequency_hz
        frequency = target.min_frequency_hz + (factor * frequency_range)

        return frequency

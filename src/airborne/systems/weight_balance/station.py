"""Load station for weight and balance calculations.

A load station represents a point where weight can be added/removed from
the aircraft, such as fuel tanks, seats, or cargo areas.
"""

from dataclasses import dataclass


@dataclass
class LoadStation:
    """Represents a weight station in the aircraft.

    Load stations have a fixed arm (distance from datum) and variable weight.
    Common stations: fuel tanks, pilot seat, passenger seats, cargo bay.

    Attributes:
        name: Station identifier (e.g., "fuel_main", "seat_pilot")
        arm: Distance from reference datum in inches
        max_weight: Maximum allowable weight in pounds
        current_weight: Current weight in pounds
        station_type: Type of station ("fuel", "seat", "cargo")

    Examples:
        >>> pilot_seat = LoadStation(
        ...     name="seat_pilot",
        ...     arm=85.0,
        ...     max_weight=200.0,
        ...     current_weight=180.0,
        ...     station_type="seat"
        ... )
        >>> moment = pilot_seat.calculate_moment()  # 180 lbs × 85 in = 15300 lb-in
    """

    name: str
    arm: float  # Distance from datum (inches)
    max_weight: float  # Maximum weight (lbs)
    current_weight: float  # Current weight (lbs)
    station_type: str  # "fuel", "seat", "cargo"

    def calculate_moment(self) -> float:
        """Calculate moment (weight × arm).

        Returns:
            Moment in pound-inches (lb-in).

        Note:
            Moment is used for CG calculation: CG = total_moment / total_weight
        """
        return self.current_weight * self.arm

    def is_overweight(self) -> bool:
        """Check if station exceeds maximum weight.

        Returns:
            True if current_weight > max_weight, False otherwise.
        """
        return self.current_weight > self.max_weight

    def set_weight(self, weight: float) -> bool:
        """Set station weight with validation.

        Args:
            weight: New weight in pounds (must be >= 0 and <= max_weight).

        Returns:
            True if weight was set successfully, False if invalid.

        Note:
            Weight is clamped to valid range [0, max_weight].
        """
        if weight < 0:
            return False

        self.current_weight = min(weight, self.max_weight)
        return True

    def add_weight(self, delta: float) -> bool:
        """Add or remove weight from station.

        Args:
            delta: Weight change in pounds (positive to add, negative to remove).

        Returns:
            True if successful, False if would exceed limits.

        Note:
            Weight is clamped to valid range [0, max_weight].
        """
        new_weight = self.current_weight + delta
        return self.set_weight(new_weight)

    def get_remaining_capacity(self) -> float:
        """Get remaining weight capacity.

        Returns:
            Available weight capacity in pounds.
        """
        return self.max_weight - self.current_weight

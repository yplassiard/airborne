"""Weight and balance calculation system.

This module calculates total aircraft weight and center of gravity position
based on all load stations (fuel, passengers, cargo).
"""

from airborne.core.logging_system import get_logger
from airborne.systems.weight_balance.station import LoadStation

logger = get_logger(__name__)


class WeightBalanceSystem:
    """Dynamic weight and balance calculation for aircraft.

    Tracks all weight stations and calculates:
    - Total aircraft weight (empty + fuel + occupants + cargo)
    - Center of gravity position (inches from datum)
    - CG within/outside limits check

    Weight changes dynamically with:
    - Fuel consumption
    - Passenger loading/unloading
    - Cargo loading/unloading

    Examples:
        >>> config = {
        ...     "empty_weight": 1600.0,
        ...     "empty_moment": 136000.0,
        ...     "max_gross_weight": 2550.0,
        ...     "cg_limits": {"forward": 82.9, "aft": 95.5},
        ...     "stations": {...}
        ... }
        >>> wb = WeightBalanceSystem(config)
        >>> total_weight = wb.calculate_total_weight()
        >>> cg_position = wb.calculate_cg()
        >>> within_limits, msg = wb.is_within_limits()
    """

    def __init__(self, config: dict):
        """Initialize weight and balance system.

        Args:
            config: Configuration dictionary with keys:
                - empty_weight: Aircraft empty weight (lbs)
                - empty_moment: Empty aircraft moment (lb-in)
                - max_gross_weight: Maximum gross weight (lbs)
                - cg_limits: {"forward": inches, "aft": inches}
                - stations: Dict of station configurations

        Raises:
            ValueError: If required configuration keys are missing.
        """
        # Aircraft basic data
        self.empty_weight = float(config.get("empty_weight", 0))
        self.empty_moment = float(config.get("empty_moment", 0))
        self.max_gross_weight = float(config.get("max_gross_weight", 0))

        # CG limits
        cg_limits = config.get("cg_limits", {})
        self.cg_forward_limit = float(cg_limits.get("forward", 0))
        self.cg_aft_limit = float(cg_limits.get("aft", 0))

        # Load stations
        self.stations: dict[str, LoadStation] = {}
        self._load_stations(config.get("stations", {}))

        logger.info(
            f"WeightBalanceSystem initialized: empty={self.empty_weight:.0f} lbs, "
            f"max_gross={self.max_gross_weight:.0f} lbs, "
            f"CG limits={self.cg_forward_limit:.1f}-{self.cg_aft_limit:.1f} in"
        )

    def _load_stations(self, stations_config: dict) -> None:
        """Load station configurations.

        Args:
            stations_config: Dict with station types (fuel, seats, cargo) as keys.
        """
        # Load fuel stations
        fuel_stations = stations_config.get("fuel", [])
        for station_config in fuel_stations:
            station = LoadStation(
                name=station_config["name"],
                arm=float(station_config["arm"]),
                max_weight=float(station_config["max_weight"]),
                current_weight=float(station_config.get("initial_weight", 0)),
                station_type="fuel",
            )
            self.stations[station.name] = station
            logger.debug(f"Loaded fuel station: {station.name} @ {station.arm} in")

        # Load seat stations
        seat_stations = stations_config.get("seats", [])
        for station_config in seat_stations:
            station = LoadStation(
                name=station_config["name"],
                arm=float(station_config["arm"]),
                max_weight=float(station_config["max_weight"]),
                current_weight=float(station_config.get("initial_weight", 0)),
                station_type="seat",
            )
            self.stations[station.name] = station
            logger.debug(f"Loaded seat station: {station.name} @ {station.arm} in")

        # Load cargo stations
        cargo_stations = stations_config.get("cargo", [])
        for station_config in cargo_stations:
            station = LoadStation(
                name=station_config["name"],
                arm=float(station_config["arm"]),
                max_weight=float(station_config["max_weight"]),
                current_weight=float(station_config.get("initial_weight", 0)),
                station_type="cargo",
            )
            self.stations[station.name] = station
            logger.debug(f"Loaded cargo station: {station.name} @ {station.arm} in")

    def calculate_total_weight(self) -> float:
        """Calculate current total aircraft weight.

        Returns:
            Total weight in pounds (empty + all stations).

        Note:
            This is the actual weight used by physics calculations.
        """
        total = self.empty_weight
        for station in self.stations.values():
            total += station.current_weight
        return total

    def calculate_total_moment(self) -> float:
        """Calculate total moment.

        Returns:
            Total moment in pound-inches.
        """
        total_moment = self.empty_moment
        for station in self.stations.values():
            total_moment += station.calculate_moment()
        return total_moment

    def calculate_cg(self) -> float:
        """Calculate center of gravity position.

        Returns:
            CG position in inches from datum.

        Note:
            CG = total_moment / total_weight
            Returns empty CG if total weight is zero.
        """
        total_weight = self.calculate_total_weight()
        if total_weight <= 0:
            return self.empty_moment / self.empty_weight if self.empty_weight > 0 else 0.0

        total_moment = self.calculate_total_moment()
        return total_moment / total_weight

    def is_within_limits(self) -> tuple[bool, str]:
        """Check if current weight and balance are within limits.

        Returns:
            Tuple of (within_limits, message):
                - within_limits: True if OK, False if out of limits
                - message: Description of status or problem

        Note:
            Checks both weight limits and CG limits.
        """
        total_weight = self.calculate_total_weight()
        cg = self.calculate_cg()

        # Check overweight
        if total_weight > self.max_gross_weight:
            return False, f"Overweight: {total_weight:.0f} lbs > {self.max_gross_weight:.0f} lbs"

        # Check CG too far forward
        if cg < self.cg_forward_limit:
            return False, f'CG too far forward: {cg:.1f}" < {self.cg_forward_limit:.1f}"'

        # Check CG too far aft
        if cg > self.cg_aft_limit:
            return False, f'CG too far aft: {cg:.1f}" > {self.cg_aft_limit:.1f}"'

        return True, "Within limits"

    def get_station(self, name: str) -> LoadStation | None:
        """Get load station by name.

        Args:
            name: Station identifier.

        Returns:
            LoadStation if found, None otherwise.
        """
        return self.stations.get(name)

    def update_station_weight(self, name: str, weight: float) -> bool:
        """Update weight at a specific station.

        Args:
            name: Station identifier.
            weight: New weight in pounds.

        Returns:
            True if successful, False if station not found or weight invalid.
        """
        station = self.get_station(name)
        if not station:
            logger.warning(f"Station not found: {name}")
            return False

        return station.set_weight(weight)

    def add_station_weight(self, name: str, delta: float) -> bool:
        """Add or remove weight from a station.

        Args:
            name: Station identifier.
            delta: Weight change in pounds (positive to add, negative to remove).

        Returns:
            True if successful, False if station not found or invalid.
        """
        station = self.get_station(name)
        if not station:
            logger.warning(f"Station not found: {name}")
            return False

        return station.add_weight(delta)

    def get_fuel_weight(self) -> float:
        """Get total fuel weight.

        Returns:
            Total weight of fuel in all fuel stations (lbs).
        """
        total_fuel = 0.0
        for station in self.stations.values():
            if station.station_type == "fuel":
                total_fuel += station.current_weight
        return total_fuel

    def get_occupant_weight(self) -> float:
        """Get total occupant weight.

        Returns:
            Total weight of all passengers/crew (lbs).
        """
        total_occupants = 0.0
        for station in self.stations.values():
            if station.station_type == "seat":
                total_occupants += station.current_weight
        return total_occupants

    def get_cargo_weight(self) -> float:
        """Get total cargo weight.

        Returns:
            Total cargo weight (lbs).
        """
        total_cargo = 0.0
        for station in self.stations.values():
            if station.station_type == "cargo":
                total_cargo += station.current_weight
        return total_cargo

    def get_weight_breakdown(self) -> dict[str, float]:
        """Get detailed weight breakdown.

        Returns:
            Dictionary with weight components:
                - empty: Empty aircraft weight
                - fuel: Total fuel weight
                - occupants: Total occupant weight
                - cargo: Total cargo weight
                - total: Total aircraft weight
                - cg: CG position (inches)
        """
        return {
            "empty": self.empty_weight,
            "fuel": self.get_fuel_weight(),
            "occupants": self.get_occupant_weight(),
            "cargo": self.get_cargo_weight(),
            "total": self.calculate_total_weight(),
            "cg": self.calculate_cg(),
        }

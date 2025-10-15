"""Simple gravity-feed fuel system for Cessna 172.

Implements realistic dual-tank gravity-feed system with no forgiveness.
Engine dies immediately when fuel exhausted.

Typical usage:
    system = SimpleGravityFuelSystem()
    system.initialize(config)
    system.update(dt=0.016, fuel_flow_gph=8.5)
    state = system.get_state()
"""

from airborne.systems.fuel.base import (
    FuelSelectorPosition,
    FuelState,
    FuelTank,
    FuelType,
    IFuelSystem,
)


class SimpleGravityFuelSystem(IFuelSystem):
    """Simple gravity-feed fuel system for Cessna 172.

    Features:
    - Two wing tanks (26 gal usable each, 28 gal total)
    - Gravity feed (no pumps required at low altitude)
    - Optional electric boost pump for high altitude/takeoff
    - Fuel selector: OFF/LEFT/RIGHT/BOTH
    - AVGAS 100LL (6.0 lbs/gallon)

    Realistic behavior (no forgiveness):
    - Engine dies immediately when fuel exhausted (no grace period)
    - Selector must be on correct tank or BOTH
    - Each tank has 2 gallons unusable fuel
    - Fuel weight affects aircraft CG and performance
    - Fuel imbalance warnings
    """

    def __init__(self):
        """Initialize fuel system."""
        self.tanks: dict[str, FuelTank] = {}
        self.selector_position = FuelSelectorPosition.BOTH
        self.fuel_pump_enabled = False
        self.lbs_per_gallon = 6.0  # AVGAS 100LL
        self.fuel_pump_power_draw = 5.0  # Amps (if electric pump used)

    def initialize(self, config: dict) -> None:
        """Initialize fuel system from configuration.

        Args:
            config: Configuration dictionary with tank specs.

        Example config:
            {
                "tanks": {
                    "left": {
                        "capacity_total": 28.0,
                        "capacity_usable": 26.0,
                        "fuel_type": "avgas_100ll",
                        "position": [-5.0, 0.0, -8.0]  # Relative to CG
                    },
                    "right": {
                        "capacity_total": 28.0,
                        "capacity_usable": 26.0,
                        "fuel_type": "avgas_100ll",
                        "position": [-5.0, 0.0, 8.0]
                    }
                },
                "selector_positions": ["OFF", "LEFT", "RIGHT", "BOTH"],
                "fuel_type": "avgas_100ll",
                "lbs_per_gallon": 6.0
            }
        """
        # Configure fuel type and weight
        if "fuel_type" in config:
            fuel_type_str = config["fuel_type"]
            self.fuel_type = FuelType[fuel_type_str.upper()]
        else:
            self.fuel_type = FuelType.AVGAS_100LL

        if "lbs_per_gallon" in config:
            self.lbs_per_gallon = config["lbs_per_gallon"]

        # Configure tanks
        if "tanks" in config:
            for tank_name, tank_config in config["tanks"].items():
                fuel_type = FuelType[tank_config.get("fuel_type", "avgas_100ll").upper()]
                self.tanks[tank_name] = FuelTank(
                    name=tank_name,
                    capacity_total=tank_config["capacity_total"],
                    capacity_usable=tank_config["capacity_usable"],
                    current_quantity=tank_config.get(
                        "initial_quantity", tank_config["capacity_usable"]
                    ),
                    fuel_type=fuel_type,
                    position=tuple(tank_config["position"]),
                )

    def update(self, dt: float, fuel_flow_gph: float) -> None:
        """Update fuel system state (consume fuel).

        Args:
            dt: Delta time in seconds
            fuel_flow_gph: Current fuel consumption rate in gallons per hour
        """
        # Don't consume if selector is OFF
        if self.selector_position == FuelSelectorPosition.OFF:
            return

        # Convert GPH to gallons per second
        fuel_consumed_gps = fuel_flow_gph / 3600.0
        fuel_consumed = fuel_consumed_gps * dt

        # Draw from tanks based on selector position
        if self.selector_position == FuelSelectorPosition.BOTH:
            # Draw equally from both tanks
            self._consume_from_both_tanks(fuel_consumed)

        elif self.selector_position == FuelSelectorPosition.LEFT:
            self._consume_from_tank("left", fuel_consumed)

        elif self.selector_position == FuelSelectorPosition.RIGHT:
            self._consume_from_tank("right", fuel_consumed)

    def get_state(self) -> FuelState:
        """Get current fuel system state.

        Returns:
            FuelState with current fuel quantities, warnings, failures
        """
        # Calculate total quantities
        total_quantity = sum(tank.current_quantity for tank in self.tanks.values())
        total_usable = sum(
            max(0.0, tank.current_quantity - (tank.capacity_total - tank.capacity_usable))
            for tank in self.tanks.values()
        )
        total_weight = total_quantity * self.lbs_per_gallon

        # Calculate CG shift due to fuel distribution
        cg_shift = self._calculate_cg_shift()

        # Calculate fuel pressure (simplified)
        fuel_pressure = self._calculate_fuel_pressure()

        # Generate warnings
        warnings = []
        if total_usable < 5.0:
            warnings.append("LOW_FUEL")
        if total_usable < 2.0:
            warnings.append("CRITICAL_FUEL")

        # Check for fuel imbalance
        if len(self.tanks) >= 2:
            quantities = [tank.current_quantity for tank in self.tanks.values()]
            if max(quantities) - min(quantities) > 5.0:
                warnings.append("FUEL_IMBALANCE")

        # Generate failures
        failures = []
        if total_usable <= 0.0:
            failures.append("FUEL_EXHAUSTED")
        if self.selector_position == FuelSelectorPosition.OFF:
            failures.append("FUEL_SELECTOR_OFF")

        # Calculate time remaining
        fuel_flow = self._get_current_fuel_flow()
        time_remaining = None
        if fuel_flow > 0.0 and total_usable > 0.0:
            time_remaining = (total_usable / fuel_flow) * 60.0  # Minutes

        return FuelState(
            tanks=self.tanks.copy(),
            total_quantity_gallons=total_quantity,
            total_usable_gallons=total_usable,
            total_weight_lbs=total_weight,
            fuel_selector_position=self.selector_position,
            fuel_flow_rate_gph=fuel_flow,
            fuel_pressure_psi=fuel_pressure,
            fuel_temperature_c=20.0,  # Simplified (ambient temp)
            center_of_gravity_shift=cg_shift,
            warnings=warnings,
            failures=failures,
            time_remaining_minutes=time_remaining,
        )

    def set_selector_position(self, position: FuelSelectorPosition) -> bool:
        """Set fuel selector valve position.

        Args:
            position: Desired selector position

        Returns:
            True if position valid for this aircraft
        """
        # Cessna 172 supports: OFF, LEFT, RIGHT, BOTH
        valid_positions = [
            FuelSelectorPosition.OFF,
            FuelSelectorPosition.LEFT,
            FuelSelectorPosition.RIGHT,
            FuelSelectorPosition.BOTH,
        ]

        if position in valid_positions:
            self.selector_position = position
            return True
        return False

    def get_available_fuel_flow(self) -> float:
        """Get available fuel flow rate to engine.

        Returns:
            Maximum available fuel flow in GPH.
            Returns 0.0 if selector OFF, tanks empty, or insufficient fuel.
        """
        if self.selector_position == FuelSelectorPosition.OFF:
            return 0.0

        # Check usable fuel in selected tanks
        usable_fuel = 0.0

        if self.selector_position == FuelSelectorPosition.BOTH:
            # Both tanks must have fuel above unusable
            for tank in self.tanks.values():
                unusable = tank.capacity_total - tank.capacity_usable
                usable = max(0.0, tank.current_quantity - unusable)
                usable_fuel += usable

        elif self.selector_position == FuelSelectorPosition.LEFT:
            if "left" in self.tanks:
                tank = self.tanks["left"]
                unusable = tank.capacity_total - tank.capacity_usable
                usable_fuel = max(0.0, tank.current_quantity - unusable)

        elif self.selector_position == FuelSelectorPosition.RIGHT and "right" in self.tanks:
            tank = self.tanks["right"]
            unusable = tank.capacity_total - tank.capacity_usable
            usable_fuel = max(0.0, tank.current_quantity - unusable)

        # If no usable fuel, return 0 (engine will die immediately)
        if usable_fuel <= 0.0:
            return 0.0

        # Gravity feed can supply ~15 GPH max (more than engine needs)
        # Electric pump can boost to ~20 GPH (for high altitude)
        if self.fuel_pump_enabled:
            return 20.0
        else:
            return 15.0

    def set_pump_enabled(self, pump_name: str, enabled: bool) -> bool:
        """Enable/disable fuel pump.

        Args:
            pump_name: Pump identifier (only "boost" for Cessna 172)
            enabled: True to enable

        Returns:
            True if successful
        """
        if pump_name == "boost":
            self.fuel_pump_enabled = enabled
            return True
        return False

    def refuel(self, tank_name: str, gallons: float) -> bool:
        """Add fuel to tank (ground refueling).

        Args:
            tank_name: Tank to refuel
            gallons: Amount to add

        Returns:
            True if successful, False if would overflow
        """
        if tank_name not in self.tanks:
            return False

        tank = self.tanks[tank_name]
        new_quantity = tank.current_quantity + gallons

        # Check for overflow
        if new_quantity > tank.capacity_total:
            return False

        tank.current_quantity = new_quantity
        return True

    def get_fuel_weight_distribution(self) -> dict[str, float]:
        """Get fuel weight per tank for CG calculation.

        Returns:
            Dict of tank_name -> weight_lbs
        """
        return {
            tank_name: tank.current_quantity * self.lbs_per_gallon
            for tank_name, tank in self.tanks.items()
        }

    def drain_tank(self, tank_name: str, gallons: float) -> float:
        """Drain fuel from tank.

        Args:
            tank_name: Tank to drain
            gallons: Amount to drain (negative = drain all)

        Returns:
            Actual amount drained
        """
        if tank_name not in self.tanks:
            return 0.0

        tank = self.tanks[tank_name]

        if gallons < 0:
            # Drain all
            drained = tank.current_quantity
            tank.current_quantity = 0.0
            return drained
        else:
            # Drain specified amount
            drained = min(gallons, tank.current_quantity)
            tank.current_quantity -= drained
            return drained

    def _consume_from_tank(self, tank_name: str, gallons: float) -> None:
        """Consume fuel from specific tank.

        Args:
            tank_name: Tank to consume from
            gallons: Amount to consume
        """
        if tank_name not in self.tanks:
            return

        tank = self.tanks[tank_name]
        tank.current_quantity -= gallons

        # Clamp to zero (no negative fuel)
        if tank.current_quantity < 0.0:
            tank.current_quantity = 0.0

    def _consume_from_both_tanks(self, gallons: float) -> None:
        """Consume fuel equally from both tanks.

        Args:
            gallons: Total amount to consume
        """
        # Split consumption between tanks
        per_tank = gallons / 2.0

        if "left" in self.tanks:
            left_tank = self.tanks["left"]
            left_tank.current_quantity -= per_tank

            # If left tank exhausted, take remainder from right
            if left_tank.current_quantity < 0:
                remainder = abs(left_tank.current_quantity)
                left_tank.current_quantity = 0.0
                if "right" in self.tanks:
                    self.tanks["right"].current_quantity -= remainder

        if "right" in self.tanks:
            right_tank = self.tanks["right"]
            right_tank.current_quantity -= per_tank

            # Clamp to zero
            if right_tank.current_quantity < 0:
                right_tank.current_quantity = 0.0

    def _calculate_cg_shift(self) -> tuple[float, float, float]:
        """Calculate CG shift due to fuel distribution.

        Returns:
            CG shift (x, y, z) in feet
        """
        total_weight = 0.0
        weighted_position = [0.0, 0.0, 0.0]

        for tank in self.tanks.values():
            tank_weight = tank.current_quantity * self.lbs_per_gallon
            total_weight += tank_weight

            weighted_position[0] += tank.position[0] * tank_weight
            weighted_position[1] += tank.position[1] * tank_weight
            weighted_position[2] += tank.position[2] * tank_weight

        if total_weight > 0:
            cg_x = weighted_position[0] / total_weight
            cg_y = weighted_position[1] / total_weight
            cg_z = weighted_position[2] / total_weight
            return (cg_x, cg_y, cg_z)
        else:
            return (0.0, 0.0, 0.0)

    def _calculate_fuel_pressure(self) -> float:
        """Calculate fuel pressure at engine.

        Returns:
            Fuel pressure in PSI
        """
        # Gravity feed provides ~3-5 PSI
        # Electric pump boosts to ~8-10 PSI
        if self.fuel_pump_enabled:
            return 8.0
        else:
            # Check if fuel available
            if self.get_available_fuel_flow() > 0:
                return 4.0
            else:
                return 0.0

    def _get_current_fuel_flow(self) -> float:
        """Get current fuel flow rate.

        Returns:
            Current fuel flow in GPH (estimated from last update)
        """
        # This would be set by engine, but we estimate here
        # In real implementation, would track from last update() call
        return 0.0  # Placeholder

"""Standard aircraft lighting system.

Implements basic aircraft exterior lights that consume electrical power.

Typical usage:
    system = StandardLightingSystem()
    system.initialize(config)
    system.update(dt=0.016, bus_voltage=14.0)
"""

from dataclasses import dataclass


@dataclass
class LightState:
    """State of a single light.

    Attributes:
        name: Light name
        enabled: Whether light is turned on
        power_draw_amps: Current consumption
        brightness: Current brightness (0.0-1.0, affected by voltage)
    """

    name: str
    enabled: bool
    power_draw_amps: float
    brightness: float


class StandardLightingSystem:
    """Standard aircraft lighting system.

    Manages exterior aircraft lights with realistic power consumption
    and voltage-dependent brightness.

    Lights:
    - Nav lights: Red (left), green (right), white (tail)
    - Beacon: Rotating red anti-collision light
    - Strobe: High-intensity white flashing lights
    - Taxi light: Fixed white light for ground operations
    - Landing light: High-intensity white light for landing

    Realistic behavior:
    - Lights dim when bus voltage drops below 12V
    - Lights off when bus voltage < 10V
    - Each light draws realistic current
    """

    def __init__(self):
        """Initialize lighting system."""
        self.lights: dict[str, LightState] = {}
        self.bus_voltage = 0.0

    def initialize(self, config: dict) -> None:
        """Initialize lighting system from configuration.

        Args:
            config: Configuration with light specs.

        Example config:
            {
                "lights": {
                    "nav_lights": {"power_draw": 1.5},
                    "beacon": {"power_draw": 2.0},
                    "strobe": {"power_draw": 3.0},
                    "taxi_light": {"power_draw": 4.0},
                    "landing_light": {"power_draw": 8.0}
                }
            }
        """
        if "lights" in config:
            for light_name, light_config in config["lights"].items():
                self.lights[light_name] = LightState(
                    name=light_name,
                    enabled=False,
                    power_draw_amps=light_config["power_draw"],
                    brightness=0.0,
                )

    def update(self, dt: float, bus_voltage: float) -> None:
        """Update lighting system.

        Args:
            dt: Delta time in seconds
            bus_voltage: Current electrical bus voltage
        """
        self.bus_voltage = bus_voltage

        # Update brightness based on voltage
        for light in self.lights.values():
            if light.enabled:
                if bus_voltage < 10.0:
                    # Too low, lights off
                    light.brightness = 0.0
                elif bus_voltage < 12.0:
                    # Dimmed
                    light.brightness = (bus_voltage - 10.0) / 2.0  # 0.0-1.0
                else:
                    # Full brightness
                    light.brightness = 1.0
            else:
                light.brightness = 0.0

    def set_light_enabled(self, light_name: str, enabled: bool) -> bool:
        """Enable/disable a light.

        Args:
            light_name: Light to control
            enabled: True to turn on

        Returns:
            True if successful
        """
        if light_name in self.lights:
            self.lights[light_name].enabled = enabled
            return True
        return False

    def get_total_power_draw(self) -> float:
        """Get total power draw from all enabled lights.

        Returns:
            Total current in amps
        """
        return sum(light.power_draw_amps for light in self.lights.values() if light.enabled)

    def get_light_state(self, light_name: str) -> LightState | None:
        """Get state of specific light.

        Args:
            light_name: Light name

        Returns:
            LightState or None if not found
        """
        return self.lights.get(light_name)

    def get_all_states(self) -> dict[str, LightState]:
        """Get states of all lights.

        Returns:
            Dict of light_name -> LightState
        """
        return self.lights.copy()

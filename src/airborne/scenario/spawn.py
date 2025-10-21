"""Aircraft spawning system.

This module provides functionality for spawning aircraft at airports
based on scenario configuration.

Typical usage:
    from airborne.scenario import SpawnManager, Scenario

    spawn_manager = SpawnManager(airport_db)
    spawn_state = spawn_manager.spawn_aircraft(scenario)
"""

import logging
from dataclasses import dataclass

from airborne.airports.database import AirportDatabase
from airborne.physics.vectors import Vector3
from airborne.scenario.scenario import EngineState, Scenario, SpawnLocation

logger = logging.getLogger(__name__)


@dataclass
class SpawnState:
    """Aircraft spawn state.

    Attributes:
        position: Spawn position (longitude, elevation, latitude)
        heading: Initial heading in degrees
        airspeed: Initial airspeed in m/s
        engine_running: Whether engine should be running
        on_ground: Whether aircraft is on ground
        parking_brake: Whether parking brake is set
    """

    position: Vector3
    heading: float
    airspeed: float = 0.0
    engine_running: bool = False
    on_ground: bool = True
    parking_brake: bool = True


class SpawnManager:
    """Manages aircraft spawning at airports.

    Handles determining spawn position based on scenario configuration
    and airport layout.

    Attributes:
        airport_db: Airport database for airport lookups

    Examples:
        >>> spawn_manager = SpawnManager(airport_db)
        >>> scenario = Scenario(airport_icao="KPAO")
        >>> spawn_state = spawn_manager.spawn_aircraft(scenario)
    """

    def __init__(self, airport_db: AirportDatabase) -> None:
        """Initialize spawn manager.

        Args:
            airport_db: Airport database instance
        """
        self.airport_db = airport_db

    def spawn_aircraft(self, scenario: Scenario) -> SpawnState:
        """Spawn aircraft according to scenario.

        Args:
            scenario: Scenario configuration

        Returns:
            Spawn state with position and configuration

        Raises:
            ValueError: If airport not found in database
        """
        # Get airport
        airport = self.airport_db.get_airport(scenario.airport_icao)
        if not airport:
            raise ValueError(f"Airport not found: {scenario.airport_icao}")

        logger.info(f"Spawning at {airport.name} ({scenario.airport_icao})")

        # Determine spawn position
        if scenario.spawn_position:
            position = scenario.spawn_position
            heading = scenario.spawn_heading
        else:
            position, heading = self._get_spawn_position(scenario, airport.icao)

        # Determine engine and brake state based on engine state
        engine_running = scenario.engine_state in (
            EngineState.RUNNING,
            EngineState.READY_FOR_TAKEOFF,
        )

        parking_brake = scenario.engine_state in (
            EngineState.COLD_AND_DARK,
            EngineState.READY_TO_START,
        )

        # Initial airspeed (takeoff scenarios may have initial speed)
        airspeed = 0.0
        if scenario.engine_state == EngineState.READY_FOR_TAKEOFF:
            airspeed = 0.0  # Still stationary, just configured

        return SpawnState(
            position=position,
            heading=heading,
            airspeed=airspeed,
            engine_running=engine_running,
            on_ground=True,
            parking_brake=parking_brake,
        )

    def _get_spawn_position(self, scenario: Scenario, airport_icao: str) -> tuple[Vector3, float]:
        """Get spawn position for scenario.

        Args:
            scenario: Scenario configuration
            airport_icao: Airport ICAO code

        Returns:
            Tuple of (position, heading)
        """
        if scenario.spawn_location == SpawnLocation.RUNWAY:
            return self._get_runway_spawn(airport_icao, scenario.spawn_heading)
        elif scenario.spawn_location == SpawnLocation.RAMP:
            return self._get_ramp_spawn(airport_icao, scenario.spawn_heading)
        elif scenario.spawn_location == SpawnLocation.TAXIWAY:
            return self._get_taxiway_spawn(airport_icao, scenario.spawn_heading)
        elif scenario.spawn_location == SpawnLocation.GATE:
            return self._get_gate_spawn(airport_icao, scenario.spawn_heading)
        else:
            # Default to airport center
            airport = self.airport_db.get_airport(airport_icao)
            if airport:
                return airport.position, scenario.spawn_heading
            else:
                return Vector3(0, 0, 0), 0.0

    def _get_runway_spawn(
        self, airport_icao: str, preferred_heading: float
    ) -> tuple[Vector3, float]:
        """Get spawn position at runway threshold.

        Args:
            airport_icao: Airport ICAO code
            preferred_heading: Preferred runway heading

        Returns:
            Tuple of (position, heading)
        """
        runways = self.airport_db.get_runways(airport_icao)

        if not runways:
            # No runways, use airport center
            airport = self.airport_db.get_airport(airport_icao)
            if airport:
                logger.warning(f"No runways at {airport_icao}, using airport center")
                return airport.position, preferred_heading
            return Vector3(0, 0, 0), 0.0

        # Find runway closest to preferred heading
        best_runway = runways[0]
        if preferred_heading > 0:
            min_diff = abs(best_runway.le_heading_deg - preferred_heading)
            for runway in runways[1:]:
                diff = abs(runway.le_heading_deg - preferred_heading)
                if diff < min_diff:
                    min_diff = diff
                    best_runway = runway

        # Use runway low-end threshold position
        position = Vector3(
            best_runway.le_longitude,
            best_runway.le_elevation_ft * 0.3048,  # Convert feet to meters
            best_runway.le_latitude,
        )
        heading = best_runway.le_heading_deg

        logger.info(f"Spawning on runway {best_runway.le_ident} heading {heading:.0f}")

        return position, heading

    def _get_ramp_spawn(self, airport_icao: str, preferred_heading: float) -> tuple[Vector3, float]:
        """Get spawn position at ramp/parking.

        Args:
            airport_icao: Airport ICAO code
            preferred_heading: Preferred heading

        Returns:
            Tuple of (position, heading)
        """
        # For now, spawn near airport reference point
        # TODO: Integrate with parking system when available
        airport = self.airport_db.get_airport(airport_icao)

        if not airport:
            logger.warning(f"Airport {airport_icao} not found")
            return Vector3(0, 0, 0), 0.0

        # Offset slightly from airport center (50m south)
        position = Vector3(
            airport.position.x,
            airport.position.y,
            airport.position.z - 0.0005,  # ~50m south
        )

        # Face north by default, or use preferred heading
        heading = preferred_heading if preferred_heading > 0 else 0.0

        logger.info(f"Spawning on ramp at {airport.name}")

        return position, heading

    def _get_taxiway_spawn(
        self, airport_icao: str, preferred_heading: float
    ) -> tuple[Vector3, float]:
        """Get spawn position on taxiway.

        Args:
            airport_icao: Airport ICAO code
            preferred_heading: Preferred heading

        Returns:
            Tuple of (position, heading)
        """
        # For now, use ramp spawn
        # TODO: Integrate with taxiway system when available
        return self._get_ramp_spawn(airport_icao, preferred_heading)

    def _get_gate_spawn(self, airport_icao: str, preferred_heading: float) -> tuple[Vector3, float]:
        """Get spawn position at gate.

        Args:
            airport_icao: Airport ICAO code
            preferred_heading: Preferred heading

        Returns:
            Tuple of (position, heading)
        """
        # For now, use ramp spawn
        # TODO: Integrate with gate system when available
        return self._get_ramp_spawn(airport_icao, preferred_heading)

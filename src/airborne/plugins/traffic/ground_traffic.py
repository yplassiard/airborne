"""Ground traffic management for AI aircraft taxi operations.

This module manages AI aircraft taxiing on the ground, including conflict
detection, hold-short instructions, and realistic taxi behavior.

Typical usage:
    manager = GroundTrafficManager(message_queue)
    manager.spawn_traffic(count=3)
    manager.update(dt)
"""

import logging
import random
import time
from dataclasses import dataclass
from enum import Enum

from airborne.core.messaging import Message, MessagePriority, MessageQueue, MessageTopic

logger = logging.getLogger(__name__)


class GroundTrafficState(Enum):
    """States for AI ground traffic aircraft.

    Attributes:
        PARKED: Aircraft at parking, not yet moving.
        REQUESTING_TAXI: Aircraft requesting taxi clearance.
        TAXIING: Aircraft actively taxiing.
        HOLDING: Aircraft holding short for traffic or clearance.
        AT_RUNWAY: Aircraft at runway hold-short line.
    """

    PARKED = "parked"
    REQUESTING_TAXI = "requesting_taxi"
    TAXIING = "taxiing"
    HOLDING = "holding"
    AT_RUNWAY = "at_runway"


@dataclass
class GroundTrafficAircraft:
    """Represents an AI aircraft on the ground.

    Attributes:
        aircraft_id: Unique identifier (e.g., "AI_N456CD").
        callsign: Radio callsign.
        aircraft_type: Aircraft type (e.g., "C172", "B737").
        position: Current position (x, y, z).
        heading: Current heading in degrees.
        speed: Current speed in knots.
        state: Current ground traffic state.
        parking_id: Current/starting parking position.
        destination_runway: Destination runway for departure.
        taxi_route: List of taxiway nodes to follow.
        current_route_index: Current position in taxi route.
        hold_short_node: Node where aircraft should hold short.
        spawn_time: Time when aircraft spawned.
    """

    aircraft_id: str
    callsign: str
    aircraft_type: str
    position: tuple[float, float, float]
    heading: float
    speed: float
    state: GroundTrafficState
    parking_id: str
    destination_runway: str
    taxi_route: list[str]
    current_route_index: int = 0
    hold_short_node: str | None = None
    spawn_time: float = 0.0


class GroundTrafficManager:
    """Manages AI aircraft taxiing on the ground.

    Spawns AI aircraft, manages their taxi routes, detects conflicts,
    and issues hold-short clearances to prevent collisions.
    """

    def __init__(self, message_queue: MessageQueue) -> None:
        """Initialize ground traffic manager.

        Args:
            message_queue: Message queue for publishing traffic updates.
        """
        self.message_queue = message_queue
        self.traffic: dict[str, GroundTrafficAircraft] = {}
        self.next_aircraft_id = 1
        self.taxi_speed_kts = 12.0  # Normal taxi speed
        self.spawn_interval = 120.0  # Spawn every 2 minutes
        self.last_spawn_time = 0.0
        self.max_traffic = 5  # Maximum concurrent ground traffic

        logger.info("Ground traffic manager initialized")

    def spawn_traffic(self, count: int = 1, parking_positions: list[str] | None = None) -> None:
        """Spawn AI ground traffic aircraft.

        Args:
            count: Number of aircraft to spawn.
            parking_positions: Optional list of parking positions. If None, generates random.
        """
        if parking_positions is None:
            parking_positions = [f"parking_{i}" for i in range(1, 20)]

        for i in range(count):
            if len(self.traffic) >= self.max_traffic:
                logger.warning(
                    "Maximum ground traffic reached (%d), not spawning more", self.max_traffic
                )
                break

            # Generate unique aircraft ID
            aircraft_id = f"AI_N{self.next_aircraft_id:03d}CD"
            self.next_aircraft_id += 1

            # Random parking and runway
            parking = random.choice(parking_positions)
            runway = random.choice(["31", "13", "27", "09"])

            # Create simple taxi route (in real implementation, would query airport database)
            taxi_route = ["Alpha", "Bravo"]  # Simplified route

            # Random aircraft type
            aircraft_type = random.choice(["C172", "C182", "PA28", "SR22"])

            # Create traffic aircraft
            traffic_aircraft = GroundTrafficAircraft(
                aircraft_id=aircraft_id,
                callsign=aircraft_id,
                aircraft_type=aircraft_type,
                position=(0.0, 0.0, 0.0),  # Will be updated from parking position
                heading=0.0,
                speed=0.0,
                state=GroundTrafficState.PARKED,
                parking_id=parking,
                destination_runway=runway,
                taxi_route=taxi_route,
                spawn_time=time.time(),
            )

            self.traffic[aircraft_id] = traffic_aircraft

            logger.info(
                "Spawned ground traffic: %s (%s) at %s, destination runway %s",
                aircraft_id,
                aircraft_type,
                parking,
                runway,
            )

            # Publish traffic spawn event
            self._publish_traffic_update(traffic_aircraft)

    def update(self, dt: float) -> None:
        """Update all ground traffic aircraft.

        Args:
            dt: Time delta since last update (seconds).
        """
        current_time = time.time()

        # Auto-spawn traffic if interval elapsed
        if current_time - self.last_spawn_time > self.spawn_interval:
            if len(self.traffic) < self.max_traffic:
                self.spawn_traffic(count=1)
            self.last_spawn_time = current_time

        # Update each aircraft
        for aircraft_id in list(self.traffic.keys()):
            aircraft = self.traffic[aircraft_id]
            self._update_aircraft(aircraft, dt)

        # Detect conflicts
        self._detect_conflicts()

    def _update_aircraft(self, aircraft: GroundTrafficAircraft, dt: float) -> None:
        """Update individual aircraft state.

        Args:
            aircraft: Aircraft to update.
            dt: Time delta (seconds).
        """
        if aircraft.state == GroundTrafficState.PARKED:
            # Wait a bit, then request taxi
            if time.time() - aircraft.spawn_time > 10.0:
                self._request_taxi(aircraft)

        elif aircraft.state == GroundTrafficState.REQUESTING_TAXI:
            # Simulated: ATC grants clearance after short delay
            if time.time() - aircraft.spawn_time > 15.0:
                self._start_taxiing(aircraft)

        elif aircraft.state == GroundTrafficState.TAXIING:
            # Move aircraft along route
            self._move_aircraft(aircraft, dt)

        elif aircraft.state == GroundTrafficState.HOLDING:
            # Aircraft is holding, check if can resume
            # For now, simple timeout
            pass

        elif aircraft.state == GroundTrafficState.AT_RUNWAY:
            # At runway, ready for departure
            # In a full sim, would request takeoff clearance
            # For now, just remove after a while
            if time.time() - aircraft.spawn_time > 300.0:  # 5 min timeout
                self._remove_aircraft(aircraft.aircraft_id)

    def _request_taxi(self, aircraft: GroundTrafficAircraft) -> None:
        """Aircraft requests taxi clearance.

        Args:
            aircraft: Aircraft requesting taxi.
        """
        aircraft.state = GroundTrafficState.REQUESTING_TAXI

        # Publish ATC request (simplified)
        self.message_queue.publish(
            Message(
                sender="ground_traffic_manager",
                recipients=["atc_manager"],
                topic="ground.traffic.request_taxi",
                data={
                    "aircraft_id": aircraft.aircraft_id,
                    "parking_id": aircraft.parking_id,
                    "destination_runway": aircraft.destination_runway,
                },
                priority=MessagePriority.LOW,
            )
        )

        logger.info(
            "%s requesting taxi from %s to runway %s",
            aircraft.aircraft_id,
            aircraft.parking_id,
            aircraft.destination_runway,
        )

    def _start_taxiing(self, aircraft: GroundTrafficAircraft) -> None:
        """Start aircraft taxiing.

        Args:
            aircraft: Aircraft to start taxiing.
        """
        aircraft.state = GroundTrafficState.TAXIING
        aircraft.speed = self.taxi_speed_kts

        logger.info("%s cleared to taxi, beginning taxi", aircraft.aircraft_id)

    def _move_aircraft(self, aircraft: GroundTrafficAircraft, dt: float) -> None:
        """Move aircraft along taxi route.

        Args:
            aircraft: Aircraft to move.
            dt: Time delta (seconds).
        """
        # Simple movement simulation
        # In real implementation, would follow actual taxiway paths

        # Check if holding
        if aircraft.hold_short_node:
            aircraft.speed = 0.0
            aircraft.state = GroundTrafficState.HOLDING
            return

        # Move forward at taxi speed
        distance = aircraft.speed * 0.514444 * dt  # Convert kts to m/s

        # Simplified: just increment position
        x, y, z = aircraft.position
        x += distance * 0.001  # Simplified movement

        aircraft.position = (x, y, z)

        # Check if reached next waypoint
        if aircraft.current_route_index >= len(aircraft.taxi_route):
            # Reached runway
            aircraft.state = GroundTrafficState.AT_RUNWAY
            logger.info(
                "%s holding short runway %s", aircraft.aircraft_id, aircraft.destination_runway
            )
        elif time.time() - aircraft.spawn_time > 30.0 * (aircraft.current_route_index + 1):
            # Simplified: advance every 30 seconds
            aircraft.current_route_index += 1

    def _detect_conflicts(self) -> None:
        """Detect potential conflicts between aircraft."""
        # Simple conflict detection: check if two aircraft are on same taxiway
        # and approaching each other within conflict threshold

        aircraft_list = list(self.traffic.values())

        for i, aircraft1 in enumerate(aircraft_list):
            if aircraft1.state != GroundTrafficState.TAXIING:
                continue

            for aircraft2 in aircraft_list[i + 1 :]:
                if aircraft2.state != GroundTrafficState.TAXIING:
                    continue

                # Check if on same taxiway
                if aircraft1.current_route_index < len(
                    aircraft1.taxi_route
                ) and aircraft2.current_route_index < len(aircraft2.taxi_route):
                    taxiway1 = aircraft1.taxi_route[aircraft1.current_route_index]
                    taxiway2 = aircraft2.taxi_route[aircraft2.current_route_index]

                    if taxiway1 == taxiway2:
                        # Conflict detected! Issue hold-short to one aircraft
                        self._resolve_conflict(aircraft1, aircraft2)

    def _resolve_conflict(
        self, aircraft1: GroundTrafficAircraft, aircraft2: GroundTrafficAircraft
    ) -> None:
        """Resolve conflict between two aircraft.

        Args:
            aircraft1: First aircraft.
            aircraft2: Second aircraft.
        """
        # Simple priority: aircraft with lower ID holds
        if aircraft1.aircraft_id < aircraft2.aircraft_id:
            holding_aircraft = aircraft1
        else:
            holding_aircraft = aircraft2

        # Issue hold short instruction
        if not holding_aircraft.hold_short_node:
            holding_aircraft.hold_short_node = "conflict_hold"
            holding_aircraft.state = GroundTrafficState.HOLDING
            holding_aircraft.speed = 0.0

            # Publish ATC hold-short instruction
            self.message_queue.publish(
                Message(
                    sender="ground_traffic_manager",
                    recipients=["atc_manager"],
                    topic=MessageTopic.ATC_MESSAGE,
                    data={
                        "aircraft_id": holding_aircraft.aircraft_id,
                        "controller": "ground",
                        "message": f"{holding_aircraft.callsign}, hold short, traffic crossing",
                        "message_key": "MSG_GROUND_HOLD_SHORT_TRAFFIC",
                    },
                    priority=MessagePriority.HIGH,
                )
            )

            logger.info(
                "Conflict detected: %s instructed to hold for %s",
                holding_aircraft.aircraft_id,
                aircraft1.aircraft_id if holding_aircraft == aircraft2 else aircraft2.aircraft_id,
            )

    def _remove_aircraft(self, aircraft_id: str) -> None:
        """Remove aircraft from ground traffic.

        Args:
            aircraft_id: Aircraft to remove.
        """
        if aircraft_id in self.traffic:
            del self.traffic[aircraft_id]
            logger.info("Removed ground traffic: %s", aircraft_id)

    def _publish_traffic_update(self, aircraft: GroundTrafficAircraft) -> None:
        """Publish traffic update message.

        Args:
            aircraft: Aircraft to publish update for.
        """
        self.message_queue.publish(
            Message(
                sender="ground_traffic_manager",
                recipients=["*"],
                topic=MessageTopic.TRAFFIC_UPDATE,
                data={
                    "aircraft_id": aircraft.aircraft_id,
                    "callsign": aircraft.callsign,
                    "aircraft_type": aircraft.aircraft_type,
                    "position": aircraft.position,
                    "heading": aircraft.heading,
                    "speed": aircraft.speed,
                    "state": aircraft.state.value,
                    "on_ground": True,
                },
                priority=MessagePriority.LOW,
            )
        )

    def get_traffic_count(self) -> int:
        """Get current number of ground traffic aircraft.

        Returns:
            Number of active ground traffic aircraft.
        """
        return len(self.traffic)

    def get_aircraft(self, aircraft_id: str) -> GroundTrafficAircraft | None:
        """Get specific aircraft.

        Args:
            aircraft_id: Aircraft identifier.

        Returns:
            Aircraft object, or None if not found.
        """
        return self.traffic.get(aircraft_id)

    def clear_all_traffic(self) -> None:
        """Remove all ground traffic aircraft."""
        self.traffic.clear()
        logger.info("Cleared all ground traffic")

"""AI Traffic system for AirBorne flight simulator.

Provides realistic AI aircraft traffic including:
- AI aircraft entities with realistic flight dynamics
- Traffic pattern generation (arrivals, departures, pattern work)
- TCAS collision avoidance system
"""

from airborne.plugins.traffic.ai_aircraft import AIAircraft, FlightPlan, Waypoint

__all__ = ["AIAircraft", "FlightPlan", "Waypoint"]

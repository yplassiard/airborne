"""Flight scenario management.

This module provides functionality for defining and loading flight scenarios
including spawn location, aircraft configuration, and initial conditions.

Typical usage:
    from airborne.scenario import Scenario, ScenarioBuilder, SpawnLocation

    scenario = ScenarioBuilder() \\
        .with_airport("KPAO") \\
        .with_spawn_location(SpawnLocation.RUNWAY) \\
        .build()
"""

from airborne.scenario.scenario import (
    EngineState,
    Scenario,
    ScenarioBuilder,
    SpawnLocation,
)
from airborne.scenario.spawn import SpawnManager, SpawnState

__all__ = [
    "EngineState",
    "Scenario",
    "ScenarioBuilder",
    "SpawnLocation",
    "SpawnManager",
    "SpawnState",
]

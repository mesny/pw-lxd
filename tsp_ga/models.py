from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


City = tuple[float, float]
Route = list[int]
DistanceMatrix = list[list[float]]
History = list[tuple[int, float]]
PopulationMode = str
MigrationStrategy = str


@dataclass(slots=True)
class Individual:
    """Single TSP candidate route with its cached distance."""

    route: Route
    distance: float


@dataclass(slots=True)
class Problem:
    """Prepared TSP instance shared by all ranks."""

    cities: list[City]
    distances: DistanceMatrix


@dataclass(slots=True)
class IslandResult:
    """Final local result produced by one island/rank."""

    rank: int
    best_distance: float
    best_generation: int
    best_route: Route
    history: History
    migration_count: int
    migration_time_seconds: float
    evolution_time_seconds: float


@dataclass(slots=True)
class MpiContext:
    """Small wrapper around the active MPI communicator."""

    comm: Any | None
    rank: int
    size: int


@dataclass(slots=True)
class GAConfig:
    """Genetic algorithm parameters after CLI parsing and validation."""

    population: int
    generations: int
    mutation: float
    elite: int
    tournament: int
    migration_interval: int
    immigrants: int
    two_opt_attempts: int
    report_interval: int
    debug_routes: bool
    migration_strategy: MigrationStrategy
    population_mode: PopulationMode


@dataclass(slots=True)
class ExperimentConfig:
    """Input, output and metadata describing a single experiment run."""

    input: str | None
    cities: int
    seed: int
    output: str
    metadata_run_id: str
    metadata_run_group_id: str | None
    metadata_scenario_name: str
    metadata_containers_per_node: int | None
    metadata_hostfile: str | None
    metadata_cpu_limit: str | None
    metadata_memory_limit: str | None
    metadata_code_version: str | None


@dataclass(slots=True)
class AppConfig:
    """Top-level configuration passed into the runner."""

    ga: GAConfig
    experiment: ExperimentConfig


@dataclass(slots=True)
class RuntimeMetrics:
    """Measured wall-clock timings for the major run stages."""

    prepare_problem_seconds: float = 0.0
    run_island_seconds: float = 0.0
    gather_seconds: float = 0.0
    report_seconds: float = 0.0
    total_seconds: float = 0.0
    total_seconds_max_rank: float = 0.0


@dataclass(slots=True)
class PopulationPlan:
    """Resolved population split across MPI ranks."""

    requested_population: int
    population_mode: PopulationMode
    per_rank_populations: list[int] = field(default_factory=list)

    @property
    def effective_total_population(self) -> int:
        """Return the actual total population used by all ranks."""

        return sum(self.per_rank_populations)

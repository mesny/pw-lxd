from __future__ import annotations

import csv
import math
import random

from tsp_ga.models import City, DistanceMatrix, ExperimentConfig, MpiContext, Problem


def load_cities_from_csv(path: str) -> list[City]:
    """Load city coordinates from a CSV file with x and y columns."""

    cities: list[City] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])
        missing_columns = sorted({"x", "y"} - fieldnames)
        if missing_columns:
            raise ValueError(
                f"CSV input {path!r} is missing required column(s): {', '.join(missing_columns)}"
            )

        for line_number, row in enumerate(reader, start=2):
            try:
                # Only coordinates define the TSP instance; optional id/name columns are ignored.
                x = float(row["x"])
                y = float(row["y"])
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"CSV input {path!r} has invalid numeric value at line {line_number}: "
                    f"x={row['x']!r}, y={row['y']!r}"
                ) from exc

            cities.append((x, y))

    if len(cities) < 3:
        raise ValueError(f"CSV input {path!r} must contain at least 3 cities, got {len(cities)}.")

    return cities


def generate_random_cities(n: int, seed: int) -> list[City]:
    """Generate a deterministic random TSP instance."""

    rng = random.Random(seed)
    return [(rng.uniform(0, 1000), rng.uniform(0, 1000)) for _ in range(n)]


def prepare_cities(config: ExperimentConfig) -> list[City]:
    """Load configured city data or generate it when no input file is set."""

    if config.input:
        return load_cities_from_csv(config.input)
    return generate_random_cities(config.cities, config.seed)


def build_distance_matrix(cities: list[City]) -> DistanceMatrix:
    """Build a symmetric Euclidean distance matrix for all city pairs."""

    n = len(cities)
    matrix = [[0.0] * n for _ in range(n)]

    for i in range(n):
        xi, yi = cities[i]
        for j in range(i + 1, n):
            xj, yj = cities[j]
            d = math.hypot(xi - xj, yi - yj)
            # Euclidean TSP is symmetric, so computing one triangle and mirroring it halves the work.
            matrix[i][j] = d
            matrix[j][i] = d

    return matrix


def prepare_problem(config: ExperimentConfig, mpi: MpiContext) -> Problem:
    """Prepare and broadcast the TSP problem for the current MPI rank."""

    if mpi.rank == 0:
        cities = prepare_cities(config)
    else:
        cities = None

    # Rank 0 is the single source of input data; all ranks build the same distance matrix locally.
    if mpi.comm is not None:
        cities = mpi.comm.bcast(cities, root=0)

    if cities is None:
        raise RuntimeError("Problem data was not initialized on this process.")

    distances = build_distance_matrix(cities)
    return Problem(cities=cities, distances=distances)

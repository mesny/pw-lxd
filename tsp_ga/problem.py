from __future__ import annotations

import csv
import math
import random

from tsp_ga.models import City, DistanceMatrix, ExperimentConfig, MpiContext, Problem


def load_cities_from_csv(path: str) -> list[City]:
    cities: list[City] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cities.append((float(row["x"]), float(row["y"])))

    if len(cities) < 3:
        raise ValueError("TSP wymaga co najmniej 3 miast.")

    return cities


def generate_random_cities(n: int, seed: int) -> list[City]:
    rng = random.Random(seed)
    return [(rng.uniform(0, 1000), rng.uniform(0, 1000)) for _ in range(n)]


def prepare_cities(config: ExperimentConfig) -> list[City]:
    if config.input:
        return load_cities_from_csv(config.input)
    return generate_random_cities(config.cities, config.seed)


def build_distance_matrix(cities: list[City]) -> DistanceMatrix:
    n = len(cities)
    matrix = [[0.0] * n for _ in range(n)]

    for i in range(n):
        xi, yi = cities[i]
        for j in range(i + 1, n):
            xj, yj = cities[j]
            d = math.hypot(xi - xj, yi - yj)
            matrix[i][j] = d
            matrix[j][i] = d

    return matrix


def prepare_problem(config: ExperimentConfig, mpi: MpiContext) -> Problem:
    if mpi.rank == 0:
        cities = prepare_cities(config)
    else:
        cities = None

    if mpi.comm is not None:
        cities = mpi.comm.bcast(cities, root=0)

    if cities is None:
        raise RuntimeError("Problem data was not initialized on this process.")

    distances = build_distance_matrix(cities)
    return Problem(cities=cities, distances=distances)

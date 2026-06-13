from __future__ import annotations

import random
from collections import Counter

from tsp_ga.models import DistanceMatrix, Individual, Route


def validate_route(route: Route, n: int) -> None:
    """Ensure a route is a valid permutation of all city indexes."""

    if len(route) != n:
        raise ValueError(f"Invalid TSP route length: expected {n}, got {len(route)}")

    counts = Counter(route)
    expected = set(range(n))
    actual = set(counts.keys())

    if actual != expected or any(count != 1 for count in counts.values()):
        missing = sorted(expected - actual)
        duplicates = sorted(city for city, count in counts.items() if count > 1)
        unexpected = sorted(actual - expected)

        raise ValueError(
            "Invalid TSP route permutation: "
            f"missing={missing}, duplicates={duplicates}, unexpected={unexpected}"
        )


def validate_route_if_enabled(route: Route, n: int, enabled: bool) -> None:
    """Run route validation only when debug checks are enabled."""

    if enabled:
        validate_route(route, n)


def route_distance(route: Route, dist: DistanceMatrix) -> float:
    """Compute the closed-tour distance for a TSP route."""

    total = 0.0
    for i in range(len(route) - 1):
        total += dist[route[i]][route[i + 1]]
    total += dist[route[-1]][route[0]]
    return total


def random_route(n: int, rng: random.Random) -> Route:
    """Create a shuffled route containing every city exactly once."""

    route = list(range(n))
    rng.shuffle(route)
    return route


def make_individual(route: Route, dist: DistanceMatrix) -> Individual:
    """Create an individual and cache its route distance."""

    return Individual(route=route, distance=route_distance(route, dist))


def initial_population(pop_size: int, n: int, dist: DistanceMatrix, rng: random.Random) -> list[Individual]:
    """Generate the initial random population for one island."""

    return [make_individual(random_route(n, rng), dist) for _ in range(pop_size)]


def tournament_select(pop: list[Individual], k: int, rng: random.Random) -> Individual:
    """Select the best individual from a random tournament sample."""

    candidates = rng.sample(pop, k)
    return min(candidates, key=lambda ind: ind.distance)


def ordered_crossover(parent_a: Route, parent_b: Route, rng: random.Random) -> Route:
    """Combine two parent routes using ordered crossover."""

    n = len(parent_a)
    left, right = sorted(rng.sample(range(n), 2))

    # Ordered crossover preserves a slice from parent A and fills remaining cities in parent B order.
    child: list[int | None] = [None] * n
    child[left:right + 1] = parent_a[left:right + 1]

    used = set(x for x in child if x is not None)
    insert_pos = (right + 1) % n

    # Wrapping after right keeps the child aligned with the classical OX operator for permutations.
    for gene in parent_b[right + 1:] + parent_b[:right + 1]:
        if gene not in used:
            child[insert_pos] = gene
            used.add(gene)
            insert_pos = (insert_pos + 1) % n

    result = [int(x) for x in child]
    validate_route(result, n)
    return result


def swap_mutation(route: Route, mutation_rate: float, rng: random.Random) -> None:
    """Randomly swap two cities in place according to mutation probability."""

    if rng.random() < mutation_rate:
        i, j = rng.sample(range(len(route)), 2)
        route[i], route[j] = route[j], route[i]


def two_opt_delta(route: Route, dist: DistanceMatrix, i: int, j: int) -> float:
    """Return the distance change caused by reversing route[i:j]."""

    a = route[i - 1]
    b = route[i]
    c = route[j - 1]
    d = route[j % len(route)]

    # Negative delta means reversing route[i:j] shortens the closed TSP tour.
    return dist[a][c] + dist[b][d] - dist[a][b] - dist[c][d]


def apply_two_opt_in_place(route: Route, i: int, j: int) -> None:
    """Reverse a route segment in place for a 2-opt move."""

    route[i:j] = reversed(route[i:j])


def random_two_opt_improvement(route: Route, dist: DistanceMatrix, max_attempts: int, rng: random.Random) -> Route:
    """Try a bounded number of random improving 2-opt moves."""

    best = route[:]
    n = len(best)

    if n < 4 or max_attempts <= 0:
        return best

    for _ in range(max_attempts):
        # Keep endpoints separated so the 2-opt move reverses a real segment, not adjacent edges.
        i = rng.randrange(1, n - 2)
        j = rng.randrange(i + 2, n)

        delta = two_opt_delta(best, dist, i, j)
        if delta < 0.0:
            apply_two_opt_in_place(best, i, j)

    return best

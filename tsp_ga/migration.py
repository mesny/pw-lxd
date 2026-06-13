from __future__ import annotations

import heapq
from typing import Any

from tsp_ga.models import Individual, MigrationStrategy


def migrate_none(pop: list[Individual]) -> list[Individual]:
    """Return the population unchanged when migration is disabled."""

    return pop


def migrate_ring(
    pop: list[Individual],
    comm: Any | None,
    rank: int,
    size: int,
    immigrants: int,
) -> list[Individual]:
    """Exchange elite individuals with neighboring ranks in a ring topology."""

    if size <= 1 or immigrants <= 0:
        return pop
    if comm is None:
        raise RuntimeError("MPI communicator is required for migration when size > 1.")

    # Only elite routes are sent; the rest of each island remains local to preserve diversity.
    best_local = heapq.nsmallest(immigrants, pop, key=lambda ind: ind.distance)
    payload = [(ind.route, ind.distance) for ind in best_local]

    dest = (rank + 1) % size
    source = (rank - 1 + size) % size

    # sendrecv avoids deadlock by exchanging elites with both neighbors in one MPI call.
    received = comm.sendrecv(
        sendobj=payload,
        dest=dest,
        sendtag=100,
        source=source,
        recvtag=100,
    )

    immigrants_ind = [Individual(route=list(route), distance=float(distance)) for route, distance in received]
    return heapq.nsmallest(len(pop), pop + immigrants_ind, key=lambda ind: ind.distance)


def migrate_global_best(
    pop: list[Individual],
    comm: Any | None,
    size: int,
    immigrants: int,
) -> list[Individual]:
    """Share elite individuals globally and keep the best combined population."""

    if size <= 1 or immigrants <= 0:
        return pop
    if comm is None:
        raise RuntimeError("MPI communicator is required for global-best migration when size > 1.")

    best_local = heapq.nsmallest(immigrants, pop, key=lambda ind: ind.distance)
    local_payload = [(ind.route, ind.distance) for ind in best_local]

    all_payloads = comm.allgather(local_payload)
    # Every rank receives the same candidate pool, then trims it locally to the population size.
    # This speeds convergence, but can also make islands collapse to similar routes.
    global_candidates = [
        Individual(route=list(route), distance=float(distance))
        for payload in all_payloads
        for route, distance in payload
    ]

    return heapq.nsmallest(len(pop), pop + global_candidates, key=lambda ind: ind.distance)


def migrate_population(
    strategy: MigrationStrategy,
    pop: list[Individual],
    comm: Any | None,
    rank: int,
    size: int,
    immigrants: int,
) -> list[Individual]:
    """Dispatch population migration to the selected strategy."""

    if strategy == "none":
        return migrate_none(pop)
    if strategy == "ring":
        return migrate_ring(pop, comm, rank, size, immigrants)
    if strategy == "global-best":
        return migrate_global_best(pop, comm, size, immigrants)
    raise ValueError(f"Unsupported migration strategy: {strategy}")

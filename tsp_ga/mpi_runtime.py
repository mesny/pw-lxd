from __future__ import annotations

from mpi4py import MPI

from tsp_ga.models import IslandResult, MpiContext


def now_seconds() -> float:
    """Return the MPI wall-clock timer value."""

    return MPI.Wtime()


def get_mpi_context() -> MpiContext:
    """Build a lightweight context from MPI_COMM_WORLD."""

    comm = MPI.COMM_WORLD
    return MpiContext(
        comm=comm,
        rank=comm.Get_rank(),
        size=comm.Get_size(),
    )


def collect_results(local_result: IslandResult, mpi: MpiContext) -> list[IslandResult] | None:
    """Gather local island results on rank 0."""

    if mpi.comm is None:
        return [local_result]

    return mpi.comm.gather(local_result, root=0)

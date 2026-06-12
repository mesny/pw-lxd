from __future__ import annotations

from collections.abc import Callable


class StageTimer:
    """Measure elapsed time using the clock selected by the caller."""

    def __init__(self, now: Callable[[], float]) -> None:
        """Store the clock function used by this timer."""

        self._now = now

    def measure(self, action: Callable[[], object]) -> tuple[object, float]:
        """Run an action and return both its result and elapsed seconds."""

        start = self._now()
        result = action()
        return result, self._now() - start

    def measure_void(self, action: Callable[[], None]) -> float:
        """Run a side-effect-only action and return elapsed seconds."""

        start = self._now()
        action()
        return self._now() - start

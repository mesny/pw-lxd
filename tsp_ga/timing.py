from __future__ import annotations

from collections.abc import Callable


class StageTimer:
    def __init__(self, now: Callable[[], float]) -> None:
        self._now = now

    def measure(self, action: Callable[[], object]) -> tuple[object, float]:
        start = self._now()
        result = action()
        return result, self._now() - start

    def measure_void(self, action: Callable[[], None]) -> float:
        start = self._now()
        action()
        return self._now() - start
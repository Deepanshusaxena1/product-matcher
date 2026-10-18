"""`Cache` kept in this process's memory: entries expire, and the least recently used make room when full.

Enough for one server instance; several instances would share a networked cache behind the same port.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


class TtlCache[V]:
    def __init__(self, *, max_entries: int = 1000, clock: Callable[[], float] = time.monotonic) -> None:
        self._entries: OrderedDict[str, tuple[float, V]] = OrderedDict()
        self._max_entries = max_entries
        self._clock = clock

    def get(self, key: str) -> V | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if self._clock() >= expires_at:
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return value

    def set(self, key: str, value: V, ttl_seconds: float) -> None:
        self._entries[key] = (self._clock() + ttl_seconds, value)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

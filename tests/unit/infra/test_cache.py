from app.infra.cache import TtlCache


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_a_value_is_kept_until_its_time_to_live_runs_out() -> None:
    clock = Clock()
    cache: TtlCache[str] = TtlCache(clock=clock)
    cache.set("k", "v", ttl_seconds=60)

    clock.now += 59
    assert cache.get("k") == "v"
    clock.now += 2
    assert cache.get("k") is None


def test_the_least_recently_used_entry_makes_room_when_full() -> None:
    cache: TtlCache[int] = TtlCache(max_entries=2, clock=Clock())
    cache.set("a", 1, ttl_seconds=60)
    cache.set("b", 2, ttl_seconds=60)
    cache.get("a")  # "b" is now the least recently used

    cache.set("c", 3, ttl_seconds=60)

    assert (cache.get("a"), cache.get("b"), cache.get("c")) == (1, None, 3)

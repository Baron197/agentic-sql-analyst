"""Shared helpers for the deterministic seed: tables, RNGs, time zones, sampling."""

import hashlib
import math
import random
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta, timezone
from itertools import accumulate

WIB = timezone(timedelta(hours=7), "WIB")


@dataclass
class Table:
    """One core table: its column names and rows, in insertion order."""

    name: str
    columns: tuple[str, ...] | str  # a space-separated string is split into a tuple
    rows: list[tuple] = field(default_factory=list)

    def __post_init__(self) -> None:
        if isinstance(self.columns, str):
            self.columns = tuple(self.columns.split())

    def digest(self) -> str:
        """SHA-256 over the rows' repr: used to prove the seed is deterministic."""
        h = hashlib.sha256(self.name.encode())
        for row in self.rows:
            h.update(repr(row).encode())
        return h.hexdigest()


def rng_for(seed: int, domain: str) -> random.Random:
    """An independent RNG per domain, so changing one domain never shifts another.

    String seeds are hashed with SHA-512 by `random`, so this does not depend on
    PYTHONHASHSEED.
    """
    return random.Random(f"{seed}:{domain}")


def poisson(rng: random.Random, lam: float) -> int:
    """Poisson sample: Knuth's method for small means, a normal approximation above 30."""
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


class WeightedPicker:
    """Fast repeated weighted choice (bisect on cumulative weights)."""

    def __init__(self, items: list, weights: list[float]):
        self.items = items
        self.cum = list(accumulate(weights))

    def pick(self, rng: random.Random, limit: int | None = None):
        """Pick one item; with `limit`, only among the first `limit` items."""
        n = len(self.items) if limit is None else limit
        x = rng.random() * self.cum[n - 1]
        return self.items[min(bisect_right(self.cum, x), n - 1)]


def wib_to_utc(d: date, seconds_of_day: int) -> datetime:
    """A WIB wall-clock moment on business day `d`, returned as an aware UTC datetime."""
    local = datetime.combine(d, time(), tzinfo=WIB) + timedelta(seconds=seconds_of_day)
    return local.astimezone(UTC)


def wib_date(ts: datetime) -> date:
    """The WIB business day of a UTC timestamp."""
    return ts.astimezone(WIB).date()


def round_to(value: float, step: int) -> int:
    return round(value / step) * step


def retail_price(value: float) -> int:
    """Indonesian shelf price: rounded to Rp 1,000 then minus Rp 100 (e.g. 149_900)."""
    if value < 20_000:
        return max(1_000, round_to(value, 500))
    return round_to(value, 1_000) - 100

"""Who a rate limit counts, and a limit for everyone together (ADR-123).

An IPv6 customer usually holds a whole /64 network (2^64 addresses); counting each address on
its own would let one visitor ask without limit. So an IPv6 address counts as its
`limits.ipv6_prefix` network; an IPv4 address as itself. And whatever the addresses, the shop
writes at most `limits.quotes_per_minute` new proposals a minute in all (each one writes files).
"""

from __future__ import annotations

import ipaddress
import threading
import time
from collections import deque
from functools import lru_cache
from typing import Any

WINDOW_S = 60.0  # a minute


@lru_cache(maxsize=1)
def _settings() -> tuple[int, int]:
    from coverengine.params import Registry

    p = Registry.load(None).resolve()
    return int(p["limits.ipv6_prefix"]), int(p["limits.quotes_per_minute"])  # type: ignore[arg-type]


def visitor_key(address: str) -> str:
    """The address a limit counts: an IPv6 address as its network (/64), else itself."""
    try:
        ip = ipaddress.ip_address(address.strip())
    except ValueError:
        return address
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        prefix = _settings()[0]
        return str(ipaddress.IPv6Network(f"{ip}/{prefix}", strict=False))
    return str(ip)


class GlobalCap:
    """At most `per_minute` events a minute in all; `hit()` is False when over."""

    def __init__(self, per_minute: int | None = None) -> None:
        self.per_minute = per_minute
        self.times: deque[float] = deque()
        self.lock = threading.Lock()

    def hit(self, now: float | None = None) -> bool:
        cap = self.per_minute if self.per_minute is not None else _settings()[1]
        now = time.time() if now is None else now
        with self.lock:
            while self.times and now - self.times[0] >= WINDOW_S:
                self.times.popleft()
            if len(self.times) >= cap:
                return False
            self.times.append(now)
            return True


def quote_cap(app: Any) -> GlobalCap:
    """The app's one cap for every place that writes a proposal (the shop, the B2B shop, the
    old webshop API)."""
    cap: GlobalCap | None = getattr(app.state, "quote_cap", None)
    if cap is None:
        cap = app.state.quote_cap = GlobalCap()
    return cap

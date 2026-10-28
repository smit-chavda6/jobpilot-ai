"""Statistics helpers for analytics: Wilson score intervals and rate reporting with sample-size guards."""

from __future__ import annotations

import math
from typing import Any


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 0.0
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def rate(successes: int, n: int, min_n: int) -> dict[str, Any]:
    if n < min_n:
        return {
            "n": n,
            "successes": successes,
            "rate": None,
            "ci_low": None,
            "ci_high": None,
            "insufficient_data": True,
            "min_n": min_n,
        }
    lo, hi = wilson_interval(successes, n)
    return {
        "n": n,
        "successes": successes,
        "rate": round(successes / n, 4),
        "ci_low": round(lo, 4),
        "ci_high": round(hi, 4),
        "insufficient_data": False,
        "min_n": min_n,
    }

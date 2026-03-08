from __future__ import annotations

from math import gcd


def common_divisors(width: int, height: int) -> list[int]:
    g = gcd(width, height)
    divisors: list[int] = []
    for i in range(1, int(g**0.5) + 1):
        if g % i == 0:
            divisors.append(i)
            if i * i != g:
                divisors.append(g // i)
    return sorted(divisors)


def choose_fastpath_scale(width: int, height: int, min_scale: int = 1) -> int | None:
    valid = [d for d in common_divisors(width, height) if d >= min_scale]
    return max(valid) if valid else None

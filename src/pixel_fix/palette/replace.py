from __future__ import annotations

from pixel_fix.types import LabelGrid


def _channels(label: int) -> tuple[int, int, int]:
    return (label >> 16) & 0xFF, (label >> 8) & 0xFF, label & 0xFF


def _distance(a: int, b: int) -> int:
    ar, ag, ab = _channels(a)
    br, bg, bb = _channels(b)
    return (ar - br) ** 2 + (ag - bg) ** 2 + (ab - bb) ** 2


def replace_exact(labels: LabelGrid, src: int, dst: int) -> LabelGrid:
    return [[dst if value == src else value for value in row] for row in labels]


def replace_tolerance(labels: LabelGrid, src: int, dst: int, tolerance: int) -> LabelGrid:
    threshold = max(0, tolerance) ** 2
    return [[dst if _distance(value, src) <= threshold else value for value in row] for row in labels]


def replace_batch(labels: LabelGrid, mapping: dict[int, int]) -> LabelGrid:
    return [[mapping.get(value, value) for value in row] for row in labels]

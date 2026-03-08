from __future__ import annotations

from collections import Counter

from pixel_fix.types import LabelGrid


def top_k_palette(labels: LabelGrid, colors: int) -> list[int]:
    if colors <= 0:
        raise ValueError("colors must be > 0")
    flat = [value for row in labels for value in row]
    counts = Counter(flat)
    return [label for label, _ in counts.most_common(colors)]


def remap_to_palette(labels: LabelGrid, palette: list[int]) -> LabelGrid:
    if not palette:
        raise ValueError("palette cannot be empty")

    def nearest(label: int) -> int:
        return min(palette, key=lambda p: abs(p - label))

    return [[nearest(value) for value in row] for row in labels]

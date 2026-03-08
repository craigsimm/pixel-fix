from __future__ import annotations

from collections import Counter

from pixel_fix.types import LabelGrid


COLOR_MODES = ("rgba", "indexed", "grayscale")


def _channels(label: int) -> tuple[int, int, int]:
    return (label >> 16) & 0xFF, (label >> 8) & 0xFF, label & 0xFF


def to_grayscale(labels: LabelGrid) -> LabelGrid:
    out: LabelGrid = []
    for row in labels:
        converted: list[int] = []
        for value in row:
            r, g, b = _channels(value)
            gray = round(0.299 * r + 0.587 * g + 0.114 * b)
            converted.append((gray << 16) | (gray << 8) | gray)
        out.append(converted)
    return out


def extract_unique_colors(labels: LabelGrid) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for row in labels:
        for value in row:
            if value not in seen:
                seen.add(value)
                ordered.append(value)
    return ordered


def to_indexed(labels: LabelGrid, max_colors: int = 256) -> tuple[list[list[int]], list[int]]:
    counts = Counter(value for row in labels for value in row)
    palette = [label for label, _ in counts.most_common(max_colors)]
    mapping = {color: idx for idx, color in enumerate(palette)}
    index_grid = [[mapping.get(value, 0) for value in row] for row in labels]
    return index_grid, palette


def indexed_to_labels(indexed: list[list[int]], palette: list[int]) -> LabelGrid:
    if not palette:
        raise ValueError("palette cannot be empty")
    last = len(palette) - 1
    return [[palette[min(max(idx, 0), last)] for idx in row] for row in indexed]


def convert_mode(labels: LabelGrid, mode: str) -> LabelGrid:
    if mode == "rgba":
        return [row[:] for row in labels]
    if mode == "grayscale":
        return to_grayscale(labels)
    if mode == "indexed":
        indexed, palette = to_indexed(labels)
        return indexed_to_labels(indexed, palette)
    raise ValueError(f"Unsupported color mode: {mode}")

from __future__ import annotations

from collections import Counter
from math import inf

import numpy as np

from pixel_fix.palette.workspace import ColorWorkspace, hyab_distance


def connected_component_continuity(labels: list[list[int]], target_label: int) -> float:
    """Largest-component ratio for a given label using 8-connected neighborhoods."""
    height = len(labels)
    width = len(labels[0]) if height else 0
    if width == 0 or height == 0:
        return 0.0

    visited: set[tuple[int, int]] = set()
    total = sum(1 for row in labels for value in row if value == target_label)
    if total == 0:
        return 0.0

    largest = 0
    for y in range(height):
        for x in range(width):
            if labels[y][x] != target_label or (y, x) in visited:
                continue
            stack = [(y, x)]
            visited.add((y, x))
            size = 0
            while stack:
                cy, cx = stack.pop()
                size += 1
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dy == 0 and dx == 0:
                            continue
                        ny = cy + dy
                        nx = cx + dx
                        if 0 <= ny < height and 0 <= nx < width and (ny, nx) not in visited and labels[ny][nx] == target_label:
                            visited.add((ny, nx))
                            stack.append((ny, nx))
            largest = max(largest, size)
    return float(largest) / float(total)


def _nearest_palette_index(label: int, palette: np.ndarray, workspace: ColorWorkspace) -> int:
    query = workspace.labels_to_oklab(np.asarray([label], dtype=np.int64))
    palette_oklab = workspace.labels_to_oklab(palette)
    distances = hyab_distance(query, palette_oklab)
    return int(np.argmin(distances))


def per_cell_purity(
    labels: list[list[int]],
    base_labels: list[list[int]],
    scale: int,
    phase_x: int,
    phase_y: int,
) -> float:
    """Average fraction of pixels per source cell that map to the expected class."""
    workspace = ColorWorkspace()
    palette = np.asarray(sorted({value for row in base_labels for value in row}), dtype=np.int64)
    height = len(base_labels)
    width = len(base_labels[0]) if height else 0
    if width == 0 or height == 0:
        return 0.0

    total_score = 0.0
    count = 0
    for cell_y in range(height):
        for cell_x in range(width):
            y0 = phase_y + cell_y * scale
            x0 = phase_x + cell_x * scale
            y1 = min(y0 + scale, len(labels))
            x1 = min(x0 + scale, len(labels[0]))
            if y0 >= len(labels) or x0 >= len(labels[0]) or y0 >= y1 or x0 >= x1:
                continue

            expected_index = _nearest_palette_index(base_labels[cell_y][cell_x], palette, workspace)
            mapped: list[int] = []
            for y in range(y0, y1):
                for x in range(x0, x1):
                    mapped.append(_nearest_palette_index(labels[y][x], palette, workspace))
            matches = sum(1 for index in mapped if index == expected_index)
            total_score += matches / max(1, len(mapped))
            count += 1
    return total_score / max(1, count)


def estimate_grid_alignment(
    labels: list[list[int]],
    base_labels: list[list[int]],
    candidate_scales: range,
    max_phase_offset: int,
) -> tuple[int, int, int, float]:
    best = (0, 0, 0, -inf)
    for scale in candidate_scales:
        for phase_y in range(max_phase_offset + 1):
            for phase_x in range(max_phase_offset + 1):
                score = per_cell_purity(labels, base_labels, scale, phase_x, phase_y)
                if score > best[3]:
                    best = (scale, phase_x, phase_y, score)
    return best


def oklab_delta_distribution(
    before: list[list[int]],
    after: list[list[int]],
) -> np.ndarray:
    if len(before) != len(after) or (before and len(before[0]) != len(after[0])):
        raise ValueError("Grids must have matching sizes")
    workspace = ColorWorkspace()
    before_flat = np.asarray([value for row in before for value in row], dtype=np.int64)
    after_flat = np.asarray([value for row in after for value in row], dtype=np.int64)
    before_oklab = workspace.labels_to_oklab(before_flat)
    after_oklab = workspace.labels_to_oklab(after_flat)
    return hyab_distance(before_oklab, after_oklab)


def masked_oklab_variance(labels: list[list[int]], mask: list[list[int]]) -> float:
    selected = [value for y, row in enumerate(labels) for x, value in enumerate(row) if mask[y][x]]
    if len(selected) < 2:
        return 0.0
    workspace = ColorWorkspace()
    samples = workspace.labels_to_oklab(np.asarray(selected, dtype=np.int64))
    return float(np.var(samples, axis=0).sum())


def palette_cardinality(labels: list[list[int]]) -> int:
    return len(Counter(value for row in labels for value in row))

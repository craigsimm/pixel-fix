from __future__ import annotations

from pixel_fix.types import LabelGrid


def bridge_single_pixel_gaps(labels: LabelGrid, target_label: int) -> LabelGrid:
    h = len(labels)
    w = len(labels[0]) if h else 0
    out = [row[:] for row in labels]

    for y in range(h):
        for x in range(w):
            if out[y][x] == target_label:
                continue

            horizontal = 0 < x < w - 1 and out[y][x - 1] == target_label and out[y][x + 1] == target_label
            vertical = 0 < y < h - 1 and out[y - 1][x] == target_label and out[y + 1][x] == target_label
            if horizontal or vertical:
                out[y][x] = target_label

    return out

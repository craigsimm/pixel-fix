from __future__ import annotations

from collections import Counter

from pixel_fix.types import LabelGrid


def downsample_labels_by_block(labels: LabelGrid, block: int, sampler: str = "mode") -> LabelGrid:
    if block <= 0:
        raise ValueError("block must be > 0")
    if sampler not in {"mode", "median"}:
        raise ValueError("sampler must be mode or median")

    height = len(labels)
    width = len(labels[0]) if height else 0
    out: LabelGrid = []

    for y in range(0, height, block):
        row: list[int] = []
        for x in range(0, width, block):
            cell = [labels[yy][xx] for yy in range(y, min(y + block, height)) for xx in range(x, min(x + block, width))]
            if not cell:
                continue
            if sampler == "mode":
                value = Counter(cell).most_common(1)[0][0]
            else:
                ordered = sorted(cell)
                value = ordered[len(ordered) // 2]
            row.append(value)
        if row:
            out.append(row)
    return out

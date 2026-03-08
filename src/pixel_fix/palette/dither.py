from __future__ import annotations

from pixel_fix.palette.quantize import nearest_palette_color
from pixel_fix.types import LabelGrid


def _channels(label: int) -> tuple[float, float, float]:
    return float((label >> 16) & 0xFF), float((label >> 8) & 0xFF), float(label & 0xFF)


def _to_label(r: float, g: float, b: float) -> int:
    rr = min(255, max(0, int(round(r))))
    gg = min(255, max(0, int(round(g))))
    bb = min(255, max(0, int(round(b))))
    return (rr << 16) | (gg << 8) | bb


def floyd_steinberg(labels: LabelGrid, palette: list[int]) -> LabelGrid:
    if not labels:
        return []
    height = len(labels)
    width = len(labels[0])
    work = [[list(_channels(value)) for value in row] for row in labels]
    out: LabelGrid = [[0 for _ in row] for row in labels]

    for y in range(height):
        for x in range(width):
            old = work[y][x]
            old_label = _to_label(*old)
            new_label = nearest_palette_color(old_label, palette)
            out[y][x] = new_label
            nr, ng, nb = _channels(new_label)
            err = (old[0] - nr, old[1] - ng, old[2] - nb)

            for dx, dy, weight in ((1, 0, 7 / 16), (-1, 1, 3 / 16), (0, 1, 5 / 16), (1, 1, 1 / 16)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height:
                    work[ny][nx][0] += err[0] * weight
                    work[ny][nx][1] += err[1] * weight
                    work[ny][nx][2] += err[2] * weight
    return out


def ordered_bayer(labels: LabelGrid, palette: list[int]) -> LabelGrid:
    matrix = (
        (0, 8, 2, 10),
        (12, 4, 14, 6),
        (3, 11, 1, 9),
        (15, 7, 13, 5),
    )
    out: LabelGrid = []
    for y, row in enumerate(labels):
        converted: list[int] = []
        for x, value in enumerate(row):
            r, g, b = _channels(value)
            threshold = (matrix[y % 4][x % 4] - 7.5) * 8
            adjusted = _to_label(r + threshold, g + threshold, b + threshold)
            converted.append(nearest_palette_color(adjusted, palette))
        out.append(converted)
    return out


def apply_dither(labels: LabelGrid, palette: list[int], mode: str) -> LabelGrid:
    if mode == "none":
        return [[nearest_palette_color(value, palette) for value in row] for row in labels]
    if mode == "floyd-steinberg":
        return floyd_steinberg(labels, palette)
    if mode == "ordered":
        return ordered_bayer(labels, palette)
    raise ValueError(f"Unsupported dither mode: {mode}")

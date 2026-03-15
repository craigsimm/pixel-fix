from __future__ import annotations

from collections import Counter

from PIL import Image

from .advanced import generate_rampforge_8_palette
from .model import StructuredPalette
from .workspace import ColorWorkspace
from pixel_fix.types import LabelGrid

RAMPFORGE_8_METHOD = "rampforge-8"
STRUCTURED_QUANTIZER_METHODS = frozenset({RAMPFORGE_8_METHOD})


def _channels(label: int) -> tuple[int, int, int]:
    return (label >> 16) & 0xFF, (label >> 8) & 0xFF, label & 0xFF


def _distance(a: int, b: int) -> int:
    ar, ag, ab = _channels(a)
    br, bg, bb = _channels(b)
    return (ar - br) ** 2 + (ag - bg) ** 2 + (ab - bb) ** 2


def top_k_palette(labels: LabelGrid, colors: int) -> list[int]:
    if colors <= 0:
        raise ValueError("colors must be > 0")
    flat = [value for row in labels for value in row]
    counts = Counter(flat)
    return [label for label, _ in counts.most_common(colors)]


def median_cut_palette(labels: LabelGrid, colors: int) -> list[int]:
    if colors <= 0:
        raise ValueError("colors must be > 0")
    height = len(labels)
    width = len(labels[0]) if height else 0
    if width == 0 or height == 0:
        return []

    image = Image.new("RGB", (width, height))
    image.putdata([_channels(value) for row in labels for value in row])
    quantized = image.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    palette_bytes = quantized.getpalette() or []
    used_entries = quantized.getcolors() or []
    ordered_indices = [index for _count, index in sorted(used_entries, reverse=True)]
    palette: list[int] = []
    for index in ordered_indices:
        offset = index * 3
        if offset + 2 >= len(palette_bytes):
            continue
        red, green, blue = palette_bytes[offset : offset + 3]
        palette.append((int(red) << 16) | (int(green) << 8) | int(blue))
    return palette[:colors]


def kmeans_palette(labels: LabelGrid, colors: int, iterations: int = 6) -> list[int]:
    if colors <= 0:
        raise ValueError("colors must be > 0")
    flat = [value for row in labels for value in row]
    if not flat:
        return []
    counts = Counter(flat)
    seeds = [label for label, _ in counts.most_common(colors)]
    centers = [_channels(seed) for seed in seeds]
    while len(centers) < colors:
        centers.append(centers[-1])

    for _ in range(iterations):
        buckets: list[list[tuple[int, int, int]]] = [[] for _ in range(colors)]
        for value in flat:
            point = _channels(value)
            best = min(range(colors), key=lambda idx: (point[0] - centers[idx][0]) ** 2 + (point[1] - centers[idx][1]) ** 2 + (point[2] - centers[idx][2]) ** 2)
            buckets[best].append(point)

        for i, bucket in enumerate(buckets):
            if not bucket:
                continue
            n = len(bucket)
            centers[i] = (
                sum(c[0] for c in bucket) // n,
                sum(c[1] for c in bucket) // n,
                sum(c[2] for c in bucket) // n,
            )

    return [(r << 16) | (g << 8) | b for (r, g, b) in centers]


def nearest_palette_color(label: int, palette: list[int]) -> int:
    if not palette:
        raise ValueError("palette cannot be empty")
    return min(palette, key=lambda p: _distance(p, label))


def remap_to_palette(labels: LabelGrid, palette: list[int]) -> LabelGrid:
    return [[nearest_palette_color(value, palette) for value in row] for row in labels]


def generate_palette(labels: LabelGrid, colors: int, method: str = "topk") -> list[int]:
    if method == "topk":
        return top_k_palette(labels, colors)
    if method == "median-cut":
        return median_cut_palette(labels, colors)
    if method == "kmeans":
        return kmeans_palette(labels, colors)
    raise ValueError(f"Unsupported quantizer: {method}")


def is_structured_quantizer(method: str) -> bool:
    return str(method or "").strip().lower() in STRUCTURED_QUANTIZER_METHODS


def generate_palette_source(
    labels: LabelGrid,
    colors: int,
    *,
    method: str = "topk",
    workspace: ColorWorkspace | None = None,
    source_label: str = "Generated",
) -> list[int] | StructuredPalette:
    if is_structured_quantizer(method):
        return generate_rampforge_8_palette(
            labels,
            workspace=workspace,
            source_label=source_label,
        ).palette
    return generate_palette(labels, colors, method=method)

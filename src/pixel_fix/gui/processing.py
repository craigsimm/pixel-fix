from __future__ import annotations

from pixel_fix.pipeline import PipelineConfig, PixelFixPipeline
from pixel_fix.types import LabelGrid

RGB = tuple[int, int, int]
RGBGrid = list[list[RGB]]


def rgb_to_labels(grid: RGBGrid) -> LabelGrid:
    return [[(r << 16) | (g << 8) | b for (r, g, b) in row] for row in grid]


def labels_to_rgb(grid: LabelGrid) -> RGBGrid:
    return [[((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF) for value in row] for row in grid]


def render_preview(grid: RGBGrid, config: PipelineConfig, palette_override: list[int] | None = None) -> RGBGrid:
    pipeline = PixelFixPipeline(config)
    labels = rgb_to_labels(grid)
    processed = pipeline.run_on_labels(labels, palette_override=palette_override)
    return labels_to_rgb(processed)

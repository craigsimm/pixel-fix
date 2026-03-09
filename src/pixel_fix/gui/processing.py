from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from PIL import Image

from pixel_fix.palette.model import StructuredPalette
from pixel_fix.palette.color_modes import extract_unique_colors
from pixel_fix.pipeline import (
    PipelineConfig,
    PipelinePreparedResult,
    PipelineProgressCallback,
    PixelFixPipeline,
)
from pixel_fix.types import LabelGrid

RGB = tuple[int, int, int]
RGBGrid = list[list[RGB]]


def rgb_to_labels(grid: RGBGrid) -> LabelGrid:
    return [[(r << 16) | (g << 8) | b for (r, g, b) in row] for row in grid]


def labels_to_rgb(grid: LabelGrid) -> RGBGrid:
    return [[((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF) for value in row] for row in grid]


@dataclass(frozen=True)
class ProcessStats:
    stage: str
    pixel_width: int
    resize_method: str
    input_size: tuple[int, int]
    output_size: tuple[int, int]
    initial_color_count: int
    color_count: int
    elapsed_seconds: float
    seed_count: int = 0
    ramp_count: int = 0
    palette_strategy: str = "advanced"
    effective_palette_size: int = 0
    histogram_size: int = 0
    palette_generation_seconds: float = 0.0
    mapping_seconds: float = 0.0
    anti_alias_pixels_fixed: int = 0
    orphan_pixels_replaced: int = 0
    gap_pixels_filled: int = 0


@dataclass(frozen=True)
class ProcessResult:
    grid: RGBGrid
    width: int
    height: int
    stats: ProcessStats
    prepared_input: PipelinePreparedResult
    display_palette_labels: tuple[int, ...] = ()
    structured_palette: StructuredPalette | None = None


def grid_to_pil_image(grid: RGBGrid) -> Image.Image:
    height = len(grid)
    width = len(grid[0]) if height else 0
    image = Image.new("RGB", (width, height))
    if width == 0 or height == 0:
        return image
    image.putdata([pixel for row in grid for pixel in row])
    return image


def load_png_grid(path: str) -> RGBGrid:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        pixels = list(rgb.getdata())
    return [pixels[index : index + width] for index in range(0, width * height, width)] if height else []


def load_png_rgba_image(path: str) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGBA").copy()


def downsample_image(
    grid: RGBGrid,
    config: PipelineConfig,
    source_rgba: Image.Image | None = None,
    progress_callback: PipelineProgressCallback | None = None,
) -> ProcessResult:
    started = perf_counter()
    pipeline = PixelFixPipeline(config)
    prepared_input = pipeline.prepare_labels(
        rgb_to_labels(grid),
        progress_callback=progress_callback,
        grid_message=f"Downsampling with {display_resize_method(config.downsample_mode)}...",
        source_rgba=source_rgba,
    )
    display_palette_labels = tuple(extract_unique_colors(prepared_input.reduced_labels))
    rgb_grid = labels_to_rgb(prepared_input.reduced_labels)
    height = len(rgb_grid)
    width = len(rgb_grid[0]) if height else 0
    return ProcessResult(
        grid=rgb_grid,
        width=width,
        height=height,
        stats=ProcessStats(
            stage="downsample",
            pixel_width=prepared_input.pixel_width,
            resize_method=config.downsample_mode,
            input_size=prepared_input.input_size,
            output_size=(width, height),
            initial_color_count=prepared_input.initial_color_count,
            color_count=len(display_palette_labels),
            elapsed_seconds=perf_counter() - started,
            anti_alias_pixels_fixed=prepared_input.anti_alias_pixels_fixed,
            orphan_pixels_replaced=prepared_input.orphan_pixels_replaced,
            gap_pixels_filled=prepared_input.gap_pixels_filled,
        ),
        prepared_input=prepared_input,
        display_palette_labels=display_palette_labels,
    )


def reduce_palette_image(
    prepared_input: PipelinePreparedResult,
    config: PipelineConfig,
    palette_override: list[int] | None = None,
    structured_palette: StructuredPalette | None = None,
    progress_callback: PipelineProgressCallback | None = None,
) -> ProcessResult:
    started = perf_counter()
    pipeline = PixelFixPipeline(config)
    result = pipeline.run_prepared_labels(
        prepared_input,
        palette_override=palette_override,
        structured_palette=structured_palette,
        progress_callback=progress_callback,
    )
    output_palette_labels = tuple(extract_unique_colors(result.labels))
    display_palette_labels = tuple(result.structured_palette.labels()) if result.structured_palette is not None else output_palette_labels
    rgb_grid = labels_to_rgb(result.labels)
    height = len(rgb_grid)
    width = len(rgb_grid[0]) if height else 0
    return ProcessResult(
        grid=rgb_grid,
        width=width,
        height=height,
        stats=ProcessStats(
            stage="palette",
            pixel_width=result.pixel_width,
            resize_method=config.downsample_mode,
            input_size=prepared_input.input_size,
            output_size=(width, height),
            initial_color_count=prepared_input.initial_color_count,
            color_count=len(output_palette_labels),
            elapsed_seconds=perf_counter() - started,
            seed_count=result.seed_count,
            ramp_count=result.ramp_count,
            palette_strategy=result.structured_palette.source_mode if result.structured_palette is not None else config.palette_strategy,
            effective_palette_size=result.effective_palette_size,
            histogram_size=result.histogram_size,
            palette_generation_seconds=result.palette_generation_seconds,
            mapping_seconds=result.mapping_seconds,
            anti_alias_pixels_fixed=result.anti_alias_pixels_fixed,
            orphan_pixels_replaced=result.orphan_pixels_replaced,
            gap_pixels_filled=result.gap_pixels_filled,
        ),
        prepared_input=prepared_input,
        display_palette_labels=display_palette_labels,
        structured_palette=result.structured_palette,
    )


def process_image(
    grid: RGBGrid,
    config: PipelineConfig,
    palette_override: list[int] | None = None,
    structured_palette: StructuredPalette | None = None,
    progress_callback: PipelineProgressCallback | None = None,
    prepared_input: PipelinePreparedResult | None = None,
    source_rgba: Image.Image | None = None,
) -> ProcessResult:
    prepared = prepared_input
    if prepared is None:
        downsampled = downsample_image(grid, config, source_rgba=source_rgba, progress_callback=progress_callback)
        prepared = downsampled.prepared_input
    elif progress_callback is not None:
        progress_callback(10, "Preparing input")
        progress_callback(35, "Reusing downsampled image...")
    return reduce_palette_image(
        prepared,
        config,
        palette_override=palette_override,
        structured_palette=structured_palette,
        progress_callback=progress_callback,
    )


def display_resize_method(value: str) -> str:
    mapping = {
        "nearest": "Nearest Neighbor",
        "bilinear": "Bilinear Interpolation",
        "rotsprite": "RotSprite",
    }
    return mapping.get(value, value.title())

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pixel_fix.io import copy_as_placeholder, validate_input_path, validate_output_path
from pixel_fix.palette.color_modes import COLOR_MODES, convert_mode, extract_unique_colors
from pixel_fix.palette.dither import apply_dither
from pixel_fix.palette.io import load_palette, save_palette
from pixel_fix.palette.quantize import generate_palette
from pixel_fix.resample import resize_labels


@dataclass(frozen=True)
class PipelineConfig:
    pixel_width: int | None = None
    downsample_mode: str = "nearest"
    colors: int = 16
    overwrite: bool = False
    input_mode: str = "rgba"
    output_mode: str = "rgba"
    quantizer: str = "topk"
    dither_mode: str = "none"
    palette_path: Path | None = None
    save_palette_path: Path | None = None
    # Legacy fields kept for compatibility with older settings/tests; they are no
    # longer used in the staged GUI workflow.
    grid: str = "manual"
    guide_pixel_width: int | None = None
    cell_sampler: str = "nearest"
    min_island_size: int = 1
    line_color: int | None = None
    replace_src: int | None = None
    replace_dst: int | None = None
    replace_tolerance: int = 0
    replace_map: dict[int, int] | None = None


PipelineProgressCallback = Callable[[int, str], None]


@dataclass(frozen=True)
class PipelineRunResult:
    labels: list[list[int]]
    pixel_width: int
    grid_method: str
    removed_isolated_pixels: int


@dataclass(frozen=True)
class PipelinePreparedResult:
    reduced_labels: list[list[int]]
    pixel_width: int
    grid_method: str
    input_size: tuple[int, int]
    initial_color_count: int


class PixelFixPipeline:
    def __init__(self, config: PipelineConfig):
        self.config = config

    @staticmethod
    def _emit_progress(callback: PipelineProgressCallback | None, percent: int, message: str) -> None:
        if callback is not None:
            callback(percent, message)

    def _resolve_pixel_width(self) -> int:
        return max(1, self.config.pixel_width or self.config.guide_pixel_width or 1)

    def _resolve_palette(self, reduced: list[list[int]], override: list[int] | None = None) -> list[int]:
        if override:
            return override
        if self.config.palette_path is not None:
            return load_palette(self.config.palette_path)
        return generate_palette(reduced, colors=self.config.colors, method=self.config.quantizer)

    def prepare_labels(
        self,
        labels: list[list[int]],
        progress_callback: PipelineProgressCallback | None = None,
        *,
        grid_message: str = "Downsampling image...",
    ) -> PipelinePreparedResult:
        if self.config.input_mode not in COLOR_MODES or self.config.output_mode not in COLOR_MODES:
            raise ValueError("Unsupported color mode")

        self._emit_progress(progress_callback, 10, "Preparing input")
        normalized = convert_mode(labels, self.config.input_mode)
        height = len(normalized)
        width = len(normalized[0]) if height else 0
        initial_color_count = len(extract_unique_colors(normalized))
        pixel_width = self._resolve_pixel_width()
        self._emit_progress(progress_callback, 35, grid_message)
        reduced = resize_labels(normalized, pixel_width, method=self.config.downsample_mode)
        return PipelinePreparedResult(
            reduced_labels=reduced,
            pixel_width=pixel_width,
            grid_method="manual",
            input_size=(width, height),
            initial_color_count=initial_color_count,
        )

    def run_prepared_labels(
        self,
        prepared: PipelinePreparedResult,
        palette_override: list[int] | None = None,
        progress_callback: PipelineProgressCallback | None = None,
    ) -> PipelineRunResult:
        if self.config.input_mode not in COLOR_MODES or self.config.output_mode not in COLOR_MODES:
            raise ValueError("Unsupported color mode")

        palette = self._resolve_palette(prepared.reduced_labels, override=palette_override)
        self._emit_progress(
            progress_callback,
            65,
            f"Quantizing to {len(palette)} colours with {self.config.quantizer}...",
        )
        if self.config.save_palette_path is not None:
            save_palette(self.config.save_palette_path, palette)
        mapped = apply_dither(prepared.reduced_labels, palette, self.config.dither_mode)
        self._emit_progress(progress_callback, 90, "Finalizing output...")
        output = convert_mode(mapped, self.config.output_mode)
        self._emit_progress(progress_callback, 100, "Complete")
        return PipelineRunResult(
            labels=output,
            pixel_width=prepared.pixel_width,
            grid_method=prepared.grid_method,
            removed_isolated_pixels=0,
        )

    def run_on_labels_detailed(
        self,
        labels: list[list[int]],
        palette_override: list[int] | None = None,
        progress_callback: PipelineProgressCallback | None = None,
    ) -> PipelineRunResult:
        prepared = self.prepare_labels(labels, progress_callback=progress_callback)
        return self.run_prepared_labels(
            prepared,
            palette_override=palette_override,
            progress_callback=progress_callback,
        )

    def run_on_labels(
        self,
        labels: list[list[int]],
        palette_override: list[int] | None = None,
        progress_callback: PipelineProgressCallback | None = None,
    ) -> list[list[int]]:
        return self.run_on_labels_detailed(
            labels,
            palette_override=palette_override,
            progress_callback=progress_callback,
        ).labels

    def run_file(self, input_path: Path, output_path: Path) -> None:
        validate_input_path(input_path)
        validate_output_path(output_path, overwrite=self.config.overwrite)
        copy_as_placeholder(input_path, output_path)

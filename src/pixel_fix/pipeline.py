from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from pixel_fix.io import copy_as_placeholder, validate_input_path, validate_output_path
from pixel_fix.palette.advanced import (
    generate_structured_palette,
    map_palette_to_labels,
    structured_palette_from_override,
)
from pixel_fix.palette.color_modes import COLOR_MODES, convert_mode, extract_unique_colors
from pixel_fix.palette.io import load_palette, save_palette
from pixel_fix.palette.workspace import ColorWorkspace
from pixel_fix.resample import resize_labels

if TYPE_CHECKING:
    from pixel_fix.palette.model import StructuredPalette


@dataclass(frozen=True)
class PipelineConfig:
    pixel_width: int | None = None
    downsample_mode: str = "nearest"
    colors: int = 16
    palette_strategy: str = "advanced"
    key_colors: tuple[int, ...] = ()
    generated_shades: int = 4
    contrast_bias: float = 1.0
    palette_dither_mode: str = "none"
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
    structured_palette: "StructuredPalette | None" = None
    palette_indices: list[list[int]] | None = None
    ramp_index_grid: list[list[int]] | None = None
    histogram_size: int = 0
    effective_palette_size: int = 0
    seed_count: int = 0
    ramp_count: int = 0
    palette_generation_seconds: float = 0.0
    mapping_seconds: float = 0.0


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

    def _resolve_override_palette(self, override: list[int] | None = None) -> list[int]:
        if override:
            return override
        if self.config.palette_path is not None:
            return load_palette(self.config.palette_path)
        return []

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
        normalized = convert_mode([row[:] for row in labels], self.config.input_mode)
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
        structured_palette: "StructuredPalette | None" = None,
        progress_callback: PipelineProgressCallback | None = None,
    ) -> PipelineRunResult:
        if self.config.input_mode not in COLOR_MODES or self.config.output_mode not in COLOR_MODES:
            raise ValueError("Unsupported color mode")

        workspace = ColorWorkspace()
        override_palette = self._resolve_override_palette(palette_override)
        dither_mode = self.config.palette_dither_mode or self.config.dither_mode

        if override_palette or self.config.palette_strategy == "override":
            self._emit_progress(progress_callback, 65, f"Applying override palette ({len(override_palette)} colours)...")
            palette_data = structured_palette_from_override(
                override_palette,
                workspace=workspace,
                source_label="Override",
            )
            histogram_size = len(extract_unique_colors(prepared.reduced_labels))
            palette_seconds = 0.0
        elif structured_palette is not None:
            self._emit_progress(progress_callback, 65, "Using generated palette...")
            palette_data = structured_palette
            histogram_size = len(extract_unique_colors(prepared.reduced_labels))
            palette_seconds = 0.0
        else:
            self._emit_progress(progress_callback, 65, "Generating perceptual palette...")
            computation = generate_structured_palette(
                prepared.reduced_labels,
                key_colors=list(self.config.key_colors),
                generated_shades=self.config.generated_shades,
                contrast_bias=self.config.contrast_bias,
                workspace=workspace,
                progress_callback=progress_callback,
                source_label="Generated",
            )
            palette_data = computation.palette
            histogram_size = computation.histogram_size
            palette_seconds = computation.palette_seconds

        if self.config.save_palette_path is not None and palette_data.labels():
            save_palette(self.config.save_palette_path, palette_data.labels())

        mapping = map_palette_to_labels(
            prepared.reduced_labels,
            palette_data,
            workspace=workspace,
            dither_mode=dither_mode,
            progress_callback=progress_callback,
        )
        output = convert_mode(mapping.labels, self.config.output_mode)
        self._emit_progress(progress_callback, 100, "Complete")
        return PipelineRunResult(
            labels=output,
            pixel_width=prepared.pixel_width,
            grid_method=prepared.grid_method,
            structured_palette=palette_data,
            palette_indices=mapping.palette_indices,
            ramp_index_grid=mapping.ramp_index_grid,
            histogram_size=histogram_size,
            effective_palette_size=palette_data.palette_size(),
            seed_count=len(palette_data.key_colors),
            ramp_count=len(palette_data.ramps),
            palette_generation_seconds=palette_seconds,
            mapping_seconds=0.0,
        )

    def run_on_labels_detailed(
        self,
        labels: list[list[int]],
        palette_override: list[int] | None = None,
        structured_palette: "StructuredPalette | None" = None,
        progress_callback: PipelineProgressCallback | None = None,
    ) -> PipelineRunResult:
        prepared = self.prepare_labels(labels, progress_callback=progress_callback)
        return self.run_prepared_labels(
            prepared,
            palette_override=palette_override,
            structured_palette=structured_palette,
            progress_callback=progress_callback,
        )

    def run_on_labels(
        self,
        labels: list[list[int]],
        palette_override: list[int] | None = None,
        structured_palette: "StructuredPalette | None" = None,
        progress_callback: PipelineProgressCallback | None = None,
    ) -> list[list[int]]:
        return self.run_on_labels_detailed(
            labels,
            palette_override=palette_override,
            structured_palette=structured_palette,
            progress_callback=progress_callback,
        ).labels

    def run_file(self, input_path: Path, output_path: Path) -> None:
        validate_input_path(input_path)
        validate_output_path(output_path, overwrite=self.config.overwrite)
        copy_as_placeholder(input_path, output_path)

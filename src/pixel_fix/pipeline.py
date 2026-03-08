from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pixel_fix.cleanup.components import remove_small_islands
from pixel_fix.cleanup.line_rules import bridge_single_pixel_gaps
from pixel_fix.grid.divisor_fastpath import choose_fastpath_scale
from pixel_fix.grid.hough_mesh import estimate_hough_candidate
from pixel_fix.grid.projection_fft import estimate_projection_candidate
from pixel_fix.grid.scoring import GridScoreWeights, select_best_candidate
from pixel_fix.io import copy_as_placeholder, validate_input_path, validate_output_path
from pixel_fix.palette.color_modes import COLOR_MODES, convert_mode, extract_unique_colors
from pixel_fix.palette.dither import apply_dither
from pixel_fix.palette.io import load_palette, save_palette
from pixel_fix.palette.quantize import generate_palette
from pixel_fix.palette.replace import replace_batch, replace_exact, replace_tolerance
from pixel_fix.resample import downsample_labels_by_block


@dataclass(frozen=True)
class PipelineConfig:
    grid: str = "auto"
    pixel_width: int | None = None
    colors: int = 16
    cell_sampler: str = "mode"
    min_island_size: int = 2
    line_color: int | None = None
    overwrite: bool = False
    input_mode: str = "rgba"
    output_mode: str = "rgba"
    quantizer: str = "topk"
    dither_mode: str = "none"
    palette_path: Path | None = None
    save_palette_path: Path | None = None
    replace_src: int | None = None
    replace_dst: int | None = None
    replace_tolerance: int = 0
    replace_map: dict[int, int] | None = None


class PixelFixPipeline:
    def __init__(self, config: PipelineConfig):
        self.config = config

    def _choose_pixel_width(self, width: int, height: int) -> int:
        if self.config.pixel_width:
            return self.config.pixel_width

        if self.config.grid == "divisor":
            return choose_fastpath_scale(width, height, min_scale=1) or 1
        if self.config.grid == "hough":
            return estimate_hough_candidate(width, height).pixel_width
        if self.config.grid == "fft":
            return estimate_projection_candidate(width, height).pixel_width

        candidates = [
            estimate_hough_candidate(width, height),
            estimate_projection_candidate(width, height),
        ]
        fast = choose_fastpath_scale(width, height, min_scale=1)
        if fast:
            from pixel_fix.types import GridCandidate

            candidates.append(
                GridCandidate(
                    method="divisor",
                    pixel_width=fast,
                    edge_alignment=0.5,
                    spacing_consistency=0.9,
                    cell_homogeneity=0.5,
                )
            )
        return select_best_candidate(candidates, GridScoreWeights()).candidate.pixel_width

    def _resolve_palette(self, reduced: list[list[int]], override: list[int] | None = None) -> list[int]:
        if override:
            return override
        if self.config.palette_path is not None:
            return load_palette(self.config.palette_path)
        return generate_palette(reduced, colors=self.config.colors, method=self.config.quantizer)

    def _apply_replacement(self, labels: list[list[int]]) -> list[list[int]]:
        replaced = labels
        if self.config.replace_src is not None and self.config.replace_dst is not None:
            if self.config.replace_tolerance > 0:
                replaced = replace_tolerance(replaced, self.config.replace_src, self.config.replace_dst, self.config.replace_tolerance)
            else:
                replaced = replace_exact(replaced, self.config.replace_src, self.config.replace_dst)
        if self.config.replace_map:
            replaced = replace_batch(replaced, self.config.replace_map)
        return replaced

    def run_on_labels(self, labels: list[list[int]], palette_override: list[int] | None = None) -> list[list[int]]:
        if self.config.input_mode not in COLOR_MODES or self.config.output_mode not in COLOR_MODES:
            raise ValueError("Unsupported color mode")

        normalized = convert_mode(labels, self.config.input_mode)
        height = len(normalized)
        width = len(normalized[0]) if height else 0
        pixel_width = max(1, self._choose_pixel_width(width, height))

        reduced = downsample_labels_by_block(normalized, pixel_width, sampler=self.config.cell_sampler)
        palette = self._resolve_palette(reduced, override=palette_override)

        if self.config.save_palette_path is not None:
            save_palette(self.config.save_palette_path, palette)

        mapped = apply_dither(reduced, palette, self.config.dither_mode)
        mapped = self._apply_replacement(mapped)
        cleaned = remove_small_islands(mapped, min_size=self.config.min_island_size, connectivity=8)

        if self.config.line_color is not None:
            cleaned = bridge_single_pixel_gaps(cleaned, self.config.line_color)

        if self.config.output_mode == "indexed":
            # keep mapped labels but limit to palette for external indexed workflows
            limited_palette = extract_unique_colors(cleaned)[:256]
            cleaned = apply_dither(cleaned, limited_palette or palette, "none")

        return convert_mode(cleaned, self.config.output_mode)

    def run_file(self, input_path: Path, output_path: Path) -> None:
        validate_input_path(input_path)
        validate_output_path(output_path, overwrite=self.config.overwrite)
        copy_as_placeholder(input_path, output_path)

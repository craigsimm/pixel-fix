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
from pixel_fix.palette.quantize import remap_to_palette, top_k_palette
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

    def run_on_labels(self, labels: list[list[int]]) -> list[list[int]]:
        height = len(labels)
        width = len(labels[0]) if height else 0
        pixel_width = max(1, self._choose_pixel_width(width, height))

        reduced = downsample_labels_by_block(labels, pixel_width, sampler=self.config.cell_sampler)
        palette = top_k_palette(reduced, colors=self.config.colors)
        mapped = remap_to_palette(reduced, palette)
        cleaned = remove_small_islands(mapped, min_size=self.config.min_island_size, connectivity=8)

        if self.config.line_color is not None:
            cleaned = bridge_single_pixel_gaps(cleaned, self.config.line_color)

        return cleaned

    def run_file(self, input_path: Path, output_path: Path) -> None:
        validate_input_path(input_path)
        validate_output_path(output_path, overwrite=self.config.overwrite)
        # Temporary no-dependency fallback; image backend integration is next.
        copy_as_placeholder(input_path, output_path)

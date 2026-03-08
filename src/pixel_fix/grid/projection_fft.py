from __future__ import annotations

from pixel_fix.types import GridCandidate


def estimate_projection_candidate(width: int, height: int) -> GridCandidate:
    smaller = min(width, height)
    pixel_width = max(1, smaller // 24)
    return GridCandidate(
        method="fft",
        pixel_width=pixel_width,
        edge_alignment=0.65,
        spacing_consistency=0.75,
        cell_homogeneity=0.65,
    )

from __future__ import annotations

from pixel_fix.types import GridCandidate


def estimate_hough_candidate(width: int, height: int, initial_upscale: int = 1) -> GridCandidate:
    """Heuristic placeholder for Hough-based estimate.

    This function exposes stable interfaces before adding heavy OpenCV-based detection.
    """

    smaller = min(width, height)
    pixel_width = max(1, smaller // max(16, 16 // max(initial_upscale, 1)))
    return GridCandidate(
        method="hough",
        pixel_width=pixel_width,
        edge_alignment=0.7,
        spacing_consistency=0.7,
        cell_homogeneity=0.6,
    )

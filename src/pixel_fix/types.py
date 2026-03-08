from __future__ import annotations

from dataclasses import dataclass

LabelGrid = list[list[int]]


@dataclass(frozen=True)
class GridCandidate:
    """Candidate grid definition and quality attributes."""

    method: str
    pixel_width: int
    edge_alignment: float
    spacing_consistency: float
    cell_homogeneity: float


@dataclass(frozen=True)
class GridSelection:
    """Result of selecting the strongest candidate grid."""

    candidate: GridCandidate
    score: float

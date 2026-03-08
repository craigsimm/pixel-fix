from __future__ import annotations

from dataclasses import dataclass

from pixel_fix.types import GridCandidate, GridSelection


@dataclass(frozen=True)
class GridScoreWeights:
    edge_alignment: float = 0.45
    spacing_consistency: float = 0.35
    cell_homogeneity: float = 0.20


def score_candidate(candidate: GridCandidate, weights: GridScoreWeights) -> float:
    return (
        candidate.edge_alignment * weights.edge_alignment
        + candidate.spacing_consistency * weights.spacing_consistency
        + candidate.cell_homogeneity * weights.cell_homogeneity
    )


def select_best_candidate(
    candidates: list[GridCandidate],
    weights: GridScoreWeights | None = None,
) -> GridSelection:
    if not candidates:
        raise ValueError("No grid candidates were provided")

    resolved_weights = weights or GridScoreWeights()
    scored = [(candidate, score_candidate(candidate, resolved_weights)) for candidate in candidates]
    best_candidate, best_score = max(scored, key=lambda item: item[1])
    return GridSelection(candidate=best_candidate, score=best_score)

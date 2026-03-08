from pixel_fix.grid.scoring import GridScoreWeights, select_best_candidate
from pixel_fix.types import GridCandidate


def test_select_best_candidate_prefers_weighted_score():
    candidates = [
        GridCandidate("hough", 3, edge_alignment=0.8, spacing_consistency=0.6, cell_homogeneity=0.5),
        GridCandidate("fft", 2, edge_alignment=0.7, spacing_consistency=0.9, cell_homogeneity=0.7),
    ]
    selected = select_best_candidate(candidates, GridScoreWeights())
    assert selected.candidate.method == "fft"

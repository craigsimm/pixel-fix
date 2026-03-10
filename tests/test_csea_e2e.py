from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np

from pixel_fix.pipeline import PipelineConfig, PixelFixPipeline
from pixel_fix.palette.quantize import generate_palette
from tests.metrics import (
    connected_component_continuity,
    estimate_grid_alignment,
    masked_oklab_variance,
    oklab_delta_distribution,
    palette_cardinality,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


def test_grid_detection_error_bounds_scale_phase_and_purity() -> None:
    fixture = _load_fixture("grid_sprite_fixture.json")
    noisy_labels = fixture["noisy_labels"]
    base_labels = fixture["base_labels"]
    expected_scale = int(fixture["scale"])
    expected_phase_x, expected_phase_y = fixture["phase"]

    scale, phase_x, phase_y, purity = estimate_grid_alignment(
        noisy_labels,
        base_labels,
        candidate_scales=range(2, 5),
        max_phase_offset=3,
    )

    assert abs(scale - expected_scale) <= 0
    assert abs(phase_x - expected_phase_x) <= 1
    assert abs(phase_y - expected_phase_y) <= 1
    assert purity >= 0.82


def test_outline_continuity_palette_exactness_and_variance_reduction() -> None:
    fixture = _load_fixture("outline_sprite_fixture.json")
    noisy = fixture["noisy_labels"]
    outline_color = int(fixture["outline_color"])
    expected_palette = [int(value) for value in fixture["expected_palette"]]
    flat_mask = fixture["flat_region_mask"]

    before_continuity = connected_component_continuity(noisy, outline_color)
    before_variance = masked_oklab_variance(noisy, flat_mask)

    np.random.seed(17)
    random.seed(17)
    result = PixelFixPipeline(
        PipelineConfig(
            pixel_width=1,
            palette_strategy="override",
            orphan_cleanup_enabled=True,
            orphan_min_similar_neighbors=2,
            orphan_fill_gaps=True,
        )
    ).run_on_labels_detailed(noisy, palette_override=expected_palette)

    after = result.labels
    after_continuity = connected_component_continuity(after, outline_color)
    after_variance = masked_oklab_variance(after, flat_mask)

    assert after_continuity >= before_continuity + 0.12
    assert palette_cardinality(after) == len(expected_palette)
    assert after_variance <= before_variance * 0.35

    deltas = oklab_delta_distribution(noisy, after)
    assert float(np.percentile(deltas, 95)) <= 0.50


def test_clustering_paths_are_seeded_and_repeatable() -> None:
    fixture = _load_fixture("grid_sprite_fixture.json")
    noisy_labels = fixture["noisy_labels"]

    np.random.seed(7)
    random.seed(7)
    palette_a = generate_palette(noisy_labels, colors=4, method="kmeans")

    np.random.seed(7)
    random.seed(7)
    palette_b = generate_palette(noisy_labels, colors=4, method="kmeans")

    assert palette_a == palette_b

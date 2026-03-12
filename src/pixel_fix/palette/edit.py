from __future__ import annotations

import numpy as np

from .advanced import MAX_KEY_COLORS, generate_structured_palette
from .workspace import ColorWorkspace


def merge_palette_labels(labels: list[int], workspace: ColorWorkspace | None = None) -> int:
    if not labels:
        raise ValueError("labels cannot be empty")
    workspace = workspace or ColorWorkspace()
    merged = np.median(workspace.labels_to_oklab(labels), axis=0)
    return workspace.oklab_to_label(merged)


def generate_ramp_palette_labels(
    seed_labels: list[int],
    *,
    generated_shades: int,
    contrast_bias: float,
    workspace: ColorWorkspace | None = None,
) -> list[int]:
    if not seed_labels:
        return []
    workspace = workspace or ColorWorkspace()
    ramps: list[int] = []
    for start in range(0, len(seed_labels), MAX_KEY_COLORS):
        batch = seed_labels[start : start + MAX_KEY_COLORS]
        computation = generate_structured_palette(
            [],
            key_colors=batch,
            generated_shades=generated_shades,
            contrast_bias=contrast_bias,
            workspace=workspace,
            source_label="Generated",
        )
        ramps.extend(computation.palette.labels())
    return ramps

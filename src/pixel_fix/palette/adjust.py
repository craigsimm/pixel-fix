from __future__ import annotations

from dataclasses import dataclass
from math import pi

import numpy as np

from .model import StructuredPalette, clone_structured_palette
from .workspace import ColorWorkspace, oklab_to_oklch, oklch_to_oklab


@dataclass(frozen=True)
class PaletteAdjustments:
    brightness: int = 0
    contrast: int = 100
    hue: int = 0
    saturation: int = 100

    def is_neutral(self) -> bool:
        return (
            self.brightness == 0
            and self.contrast == 100
            and self.hue == 0
            and self.saturation == 100
        )


def adjust_palette_labels(
    labels: list[int],
    adjustments: PaletteAdjustments,
    *,
    workspace: ColorWorkspace | None = None,
) -> list[int]:
    if not labels:
        return []
    workspace = workspace or ColorWorkspace()
    oklab = workspace.labels_to_oklab(np.asarray(labels, dtype=np.int64))
    adjusted_labels, _adjusted_oklab = _adjust_oklab_labels(oklab, adjustments, workspace)
    return adjusted_labels


def adjust_structured_palette(
    palette: StructuredPalette,
    adjustments: PaletteAdjustments,
    *,
    workspace: ColorWorkspace | None = None,
) -> StructuredPalette:
    workspace = workspace or ColorWorkspace()
    adjusted = clone_structured_palette(palette) or StructuredPalette()
    colors = adjusted.flattened_colors()
    if not colors:
        return adjusted

    labels = [color.label for color in colors]
    oklab = np.asarray([color.oklab for color in colors], dtype=np.float64)
    adjusted_labels, adjusted_oklab = _adjust_oklab_labels(oklab, adjustments, workspace, source_labels=labels)

    for index, color in enumerate(colors):
        color.label = int(adjusted_labels[index])
        color.oklab = tuple(float(value) for value in adjusted_oklab[index])

    for ramp in adjusted.ramps:
        seed_color = next((color for color in ramp.colors if color.is_seed), ramp.colors[0] if ramp.colors else None)
        if seed_color is None:
            ramp.seed_label = 0
            ramp.seed_oklab = (0.0, 0.0, 0.0)
        else:
            ramp.seed_label = seed_color.label
            ramp.seed_oklab = tuple(seed_color.oklab)
    return adjusted


def _adjust_oklab_labels(
    oklab: np.ndarray,
    adjustments: PaletteAdjustments,
    workspace: ColorWorkspace,
    *,
    source_labels: list[int] | None = None,
) -> tuple[list[int], np.ndarray]:
    if oklab.size == 0:
        return ([], np.empty((0, 3), dtype=np.float64))
    if adjustments.is_neutral():
        if source_labels is None:
            source_labels = [workspace.oklab_to_label(color) for color in oklab]
        return ([int(label) for label in source_labels], np.asarray(oklab, dtype=np.float64))

    oklch = oklab_to_oklch(np.asarray(oklab, dtype=np.float64))
    lightness = oklch[:, 0]
    pivot = float(np.median(lightness)) if lightness.size else 0.5
    brightness_delta = adjustments.brightness / 250.0
    contrast_factor = max(0.0, adjustments.contrast / 100.0)
    saturation_factor = max(0.0, adjustments.saturation / 100.0)
    hue_shift = (adjustments.hue / 180.0) * pi

    adjusted_l = np.clip(((lightness - pivot) * contrast_factor) + pivot + brightness_delta, 0.0, 1.0)
    adjusted_c = np.clip(oklch[:, 1] * saturation_factor, 0.0, None)
    adjusted_h = np.mod(oklch[:, 2] + hue_shift, 2 * pi)
    adjusted_oklch = np.stack((adjusted_l, adjusted_c, adjusted_h), axis=1)
    adjusted_oklab = oklch_to_oklab(adjusted_oklch)
    labels = [workspace.oklab_to_label(color) for color in adjusted_oklab]
    realized = workspace.labels_to_oklab(np.asarray(labels, dtype=np.int64))
    return (labels, realized)

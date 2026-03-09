from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from pixel_fix.types import LabelGrid


@dataclass
class PaletteColor:
    label: int
    oklab: tuple[float, float, float]
    locked: bool = False
    is_seed: bool = False
    ramp_index: int = 0
    shade_index: int = 0


@dataclass
class PaletteRamp:
    ramp_id: int
    seed_label: int
    seed_oklab: tuple[float, float, float]
    colors: list[PaletteColor] = field(default_factory=list)


@dataclass
class StructuredPalette:
    ramps: list[PaletteRamp] = field(default_factory=list)
    source_mode: str = "advanced"
    key_colors: list[int] = field(default_factory=list)
    contrast_bias: float = 1.0
    generated_shades: int = 4
    source_label: str = ""

    def flattened_colors(self) -> list[PaletteColor]:
        return [color for ramp in self.ramps for color in ramp.colors]

    def labels(self) -> list[int]:
        return [color.label for color in self.flattened_colors()]

    def locked_labels(self) -> list[int]:
        return [color.label for color in self.flattened_colors() if color.locked]

    def palette_size(self) -> int:
        return len(self.flattened_colors())


@dataclass
class WeightedColorDataset:
    labels: np.ndarray
    counts: np.ndarray
    oklab: np.ndarray

    @property
    def size(self) -> int:
        return int(self.labels.size)


@dataclass
class PaletteMappingResult:
    labels: LabelGrid
    palette_indices: list[list[int]]
    ramp_index_grid: list[list[int]] | None


def clone_structured_palette(palette: StructuredPalette | None) -> StructuredPalette | None:
    if palette is None:
        return None
    return StructuredPalette(
        ramps=[
            PaletteRamp(
                ramp_id=ramp.ramp_id,
                seed_label=ramp.seed_label,
                seed_oklab=tuple(ramp.seed_oklab),
                colors=[
                    PaletteColor(
                        label=color.label,
                        oklab=tuple(color.oklab),
                        locked=color.locked,
                        is_seed=color.is_seed,
                        ramp_index=color.ramp_index,
                        shade_index=color.shade_index,
                    )
                    for color in ramp.colors
                ],
            )
            for ramp in palette.ramps
        ],
        source_mode=palette.source_mode,
        key_colors=list(palette.key_colors),
        contrast_bias=palette.contrast_bias,
        generated_shades=palette.generated_shades,
        source_label=palette.source_label,
    )

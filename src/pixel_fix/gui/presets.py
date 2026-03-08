from __future__ import annotations

from dataclasses import dataclass, replace

from .state import PreviewSettings


@dataclass(frozen=True)
class PresetDefinition:
    name: str
    description: str
    patch: dict[str, object]


PRESET_DEFINITIONS: tuple[PresetDefinition, ...] = (
    PresetDefinition(
        name="AI sprite cleanup",
        description="Balanced cleanup for single sprites with preserved edges.",
        patch={
            "colors": 32,
            "quantizer": "topk",
            "dither_mode": "none",
            "min_island_size": 2,
            "cell_sampler": "mode",
        },
    ),
    PresetDefinition(
        name="AI tileset cleanup",
        description="Lower palette and lighter cleanup for repeated tiles.",
        patch={
            "colors": 16,
            "quantizer": "topk",
            "dither_mode": "none",
            "min_island_size": 1,
            "cell_sampler": "mode",
        },
    ),
    PresetDefinition(
        name="UI icon cleanup",
        description="Tight palette and crisp edges for small UI graphics.",
        patch={
            "colors": 8,
            "quantizer": "topk",
            "dither_mode": "none",
            "min_island_size": 1,
        },
    ),
    PresetDefinition(
        name="Preserve outlines",
        description="Favor solid edges and minimal cleanup changes.",
        patch={
            "cell_sampler": "mode",
            "dither_mode": "none",
            "min_island_size": 1,
        },
    ),
    PresetDefinition(
        name="Aggressive palette reduction",
        description="Pushes toward a very small palette with stronger cleanup.",
        patch={
            "colors": 8,
            "quantizer": "kmeans",
            "dither_mode": "ordered",
            "min_island_size": 2,
        },
    ),
)


PRESET_BY_NAME = {preset.name: preset for preset in PRESET_DEFINITIONS}


def preset_names() -> list[str]:
    return ["Custom", *[preset.name for preset in PRESET_DEFINITIONS]]


def apply_preset(settings: PreviewSettings, preset_name: str) -> PreviewSettings:
    if preset_name == "Custom":
        return settings
    preset = PRESET_BY_NAME[preset_name]
    return replace(settings, **preset.patch)

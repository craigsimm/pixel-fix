from __future__ import annotations

from colorsys import rgb_to_hsv
from dataclasses import dataclass
from math import ceil, cos, pi, sqrt

from pixel_fix.palette.workspace import ColorWorkspace

PALETTE_SORT_LIGHTNESS = "lightness"
PALETTE_SORT_HUE = "hue"
PALETTE_SORT_SATURATION = "saturation"
PALETTE_SORT_CHROMA = "chroma"
PALETTE_SORT_TEMPERATURE = "temperature"

PALETTE_SORT_MODES = (
    PALETTE_SORT_LIGHTNESS,
    PALETTE_SORT_HUE,
    PALETTE_SORT_SATURATION,
    PALETTE_SORT_CHROMA,
    PALETTE_SORT_TEMPERATURE,
)

PALETTE_SORT_LABELS = {
    PALETTE_SORT_LIGHTNESS: "Lightness (Dark -> Light)",
    PALETTE_SORT_HUE: "Hue (Red Wheel)",
    PALETTE_SORT_SATURATION: "Saturation (Low -> High)",
    PALETTE_SORT_CHROMA: "Chroma (Low -> High)",
    PALETTE_SORT_TEMPERATURE: "Temperature (Cool -> Warm)",
}

PALETTE_SELECT_LIGHTNESS_DARK = "lightness-dark"
PALETTE_SELECT_LIGHTNESS_LIGHT = "lightness-light"
PALETTE_SELECT_SATURATION_LOW = "saturation-low"
PALETTE_SELECT_SATURATION_HIGH = "saturation-high"
PALETTE_SELECT_CHROMA_LOW = "chroma-low"
PALETTE_SELECT_CHROMA_HIGH = "chroma-high"
PALETTE_SELECT_TEMPERATURE_COOL = "temperature-cool"
PALETTE_SELECT_TEMPERATURE_WARM = "temperature-warm"
PALETTE_SELECT_HUE_RED = "hue-red"
PALETTE_SELECT_HUE_YELLOW = "hue-yellow"
PALETTE_SELECT_HUE_GREEN = "hue-green"
PALETTE_SELECT_HUE_CYAN = "hue-cyan"
PALETTE_SELECT_HUE_BLUE = "hue-blue"
PALETTE_SELECT_HUE_MAGENTA = "hue-magenta"

PALETTE_SELECT_DIRECT_MODES = (
    PALETTE_SELECT_LIGHTNESS_DARK,
    PALETTE_SELECT_LIGHTNESS_LIGHT,
    PALETTE_SELECT_SATURATION_LOW,
    PALETTE_SELECT_SATURATION_HIGH,
    PALETTE_SELECT_CHROMA_LOW,
    PALETTE_SELECT_CHROMA_HIGH,
    PALETTE_SELECT_TEMPERATURE_COOL,
    PALETTE_SELECT_TEMPERATURE_WARM,
)

PALETTE_SELECT_HUE_MODES = (
    PALETTE_SELECT_HUE_RED,
    PALETTE_SELECT_HUE_YELLOW,
    PALETTE_SELECT_HUE_GREEN,
    PALETTE_SELECT_HUE_CYAN,
    PALETTE_SELECT_HUE_BLUE,
    PALETTE_SELECT_HUE_MAGENTA,
)

PALETTE_SELECT_MODES = PALETTE_SELECT_DIRECT_MODES + PALETTE_SELECT_HUE_MODES

PALETTE_SELECT_LABELS = {
    PALETTE_SELECT_LIGHTNESS_DARK: "Lightness (Dark)",
    PALETTE_SELECT_LIGHTNESS_LIGHT: "Lightness (Light)",
    PALETTE_SELECT_SATURATION_LOW: "Saturation (Low)",
    PALETTE_SELECT_SATURATION_HIGH: "Saturation (High)",
    PALETTE_SELECT_CHROMA_LOW: "Chroma (Low)",
    PALETTE_SELECT_CHROMA_HIGH: "Chroma (High)",
    PALETTE_SELECT_TEMPERATURE_COOL: "Temperature (Cool)",
    PALETTE_SELECT_TEMPERATURE_WARM: "Temperature (Warm)",
    PALETTE_SELECT_HUE_RED: "Hue (Red)",
    PALETTE_SELECT_HUE_YELLOW: "Hue (Yellow)",
    PALETTE_SELECT_HUE_GREEN: "Hue (Green)",
    PALETTE_SELECT_HUE_CYAN: "Hue (Cyan)",
    PALETTE_SELECT_HUE_BLUE: "Hue (Blue)",
    PALETTE_SELECT_HUE_MAGENTA: "Hue (Magenta)",
}

_NEUTRAL_SATURATION_EPSILON = 0.02
_NEUTRAL_CHROMA_EPSILON = 0.015
_WARM_HUE_CENTER = pi / 6.0
_HUE_BUCKET_CENTERS = {
    PALETTE_SELECT_HUE_RED: 0.0,
    PALETTE_SELECT_HUE_YELLOW: pi / 3.0,
    PALETTE_SELECT_HUE_GREEN: (2.0 * pi) / 3.0,
    PALETTE_SELECT_HUE_CYAN: pi,
    PALETTE_SELECT_HUE_BLUE: (4.0 * pi) / 3.0,
    PALETTE_SELECT_HUE_MAGENTA: (5.0 * pi) / 3.0,
}


@dataclass(frozen=True)
class _PaletteSortMetrics:
    label: int
    index: int
    lightness: float
    chroma: float
    hue: float
    saturation: float
    is_neutral: bool
    temperature: float


def sort_palette_labels(labels: list[int], mode: str, workspace: ColorWorkspace) -> list[int]:
    if mode not in PALETTE_SORT_MODES:
        raise ValueError(f"Unsupported palette sort mode: {mode}")
    if not labels:
        return []

    metrics = _palette_metrics(labels, workspace)
    key_function = _sort_key_function(mode)
    return [metric.label for metric in sorted(metrics, key=key_function)]


def select_palette_indices(labels: list[int], mode: str, threshold_percent: int, workspace: ColorWorkspace) -> list[int]:
    if mode not in PALETTE_SELECT_MODES:
        raise ValueError(f"Unsupported palette selection mode: {mode}")
    if not labels:
        return []
    metrics = _palette_metrics(labels, workspace)
    target_count = max(1, ceil(len(labels) * (max(0.0, min(100.0, float(threshold_percent))) / 100.0)))
    ranked = _selection_ranking(metrics, mode)
    if not ranked:
        return []
    limited = ranked[: min(target_count, len(ranked))]
    return sorted(metric.index for metric in limited)


def _palette_metrics(labels: list[int], workspace: ColorWorkspace) -> list[_PaletteSortMetrics]:
    oklab = workspace.labels_to_oklab(labels)
    srgb = workspace.labels_to_srgb(labels)
    return [_build_metrics(label, index, oklab[index], srgb[index]) for index, label in enumerate(labels)]


def _build_metrics(label: int, index: int, oklab: object, srgb: object) -> _PaletteSortMetrics:
    lightness, axis_a, axis_b = (float(value) for value in oklab)
    red, green, blue = (float(value) for value in srgb)
    hue, saturation, _value = rgb_to_hsv(red, green, blue)
    hue_angle = float(hue * (2.0 * pi))
    chroma = float(sqrt((axis_a * axis_a) + (axis_b * axis_b)))
    is_neutral = saturation < _NEUTRAL_SATURATION_EPSILON or chroma < _NEUTRAL_CHROMA_EPSILON
    temperature = float(cos(hue_angle - _WARM_HUE_CENTER))
    return _PaletteSortMetrics(
        label=label,
        index=index,
        lightness=lightness,
        chroma=chroma,
        hue=hue_angle,
        saturation=float(saturation),
        is_neutral=is_neutral,
        temperature=temperature,
    )


def _sort_key_function(mode: str):
    if mode == PALETTE_SORT_LIGHTNESS:
        return lambda metric: (metric.lightness, metric.chroma, metric.hue, metric.index)
    if mode == PALETTE_SORT_HUE:
        return lambda metric: (
            0 if metric.is_neutral else 1,
            metric.lightness if metric.is_neutral else metric.hue,
            0.0 if metric.is_neutral else metric.lightness,
            metric.index,
        )
    if mode == PALETTE_SORT_SATURATION:
        return lambda metric: (metric.saturation, metric.lightness, metric.hue, metric.index)
    if mode == PALETTE_SORT_CHROMA:
        return lambda metric: (metric.chroma, metric.lightness, metric.hue, metric.index)
    return lambda metric: (
        0 if metric.is_neutral else 1,
        metric.lightness if metric.is_neutral else metric.temperature,
        0.0 if metric.is_neutral else metric.lightness,
        metric.index,
    )


def _selection_ranking(metrics: list[_PaletteSortMetrics], mode: str) -> list[_PaletteSortMetrics]:
    if mode == PALETTE_SELECT_LIGHTNESS_DARK:
        return sorted(metrics, key=lambda metric: (metric.lightness, metric.chroma, metric.hue, metric.index))
    if mode == PALETTE_SELECT_LIGHTNESS_LIGHT:
        return sorted(metrics, key=lambda metric: (-metric.lightness, metric.chroma, metric.hue, metric.index))
    if mode == PALETTE_SELECT_SATURATION_LOW:
        return sorted(metrics, key=lambda metric: (metric.saturation, metric.lightness, metric.hue, metric.index))
    if mode == PALETTE_SELECT_SATURATION_HIGH:
        return sorted(metrics, key=lambda metric: (-metric.saturation, metric.lightness, metric.hue, metric.index))
    if mode == PALETTE_SELECT_CHROMA_LOW:
        return sorted(metrics, key=lambda metric: (metric.chroma, metric.lightness, metric.hue, metric.index))
    if mode == PALETTE_SELECT_CHROMA_HIGH:
        return sorted(metrics, key=lambda metric: (-metric.chroma, metric.lightness, metric.hue, metric.index))
    if mode == PALETTE_SELECT_TEMPERATURE_COOL:
        eligible = [metric for metric in metrics if not metric.is_neutral] or list(metrics)
        return sorted(eligible, key=lambda metric: (metric.temperature, -metric.saturation, metric.lightness, metric.index))
    if mode == PALETTE_SELECT_TEMPERATURE_WARM:
        eligible = [metric for metric in metrics if not metric.is_neutral] or list(metrics)
        return sorted(eligible, key=lambda metric: (-metric.temperature, -metric.saturation, metric.lightness, metric.index))
    eligible = [metric for metric in metrics if not metric.is_neutral]
    if not eligible:
        return []
    center = _HUE_BUCKET_CENTERS[mode]
    return sorted(
        eligible,
        key=lambda metric: (_circular_hue_distance(metric.hue, center), -metric.saturation, -metric.chroma, metric.index),
    )


def _circular_hue_distance(left: float, right: float) -> float:
    delta = abs(left - right)
    return min(delta, (2.0 * pi) - delta)

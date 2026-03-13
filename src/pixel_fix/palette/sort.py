from __future__ import annotations

from colorsys import rgb_to_hsv
from dataclasses import dataclass
from math import ceil, cos, pi, sqrt

import numpy as np

from pixel_fix.palette.workspace import ColorWorkspace, hyab_distance

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
PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES = "similarity-near-duplicates"

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

PALETTE_SELECT_SPECIAL_MODES = (PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES,)

PALETTE_SELECT_MODES = PALETTE_SELECT_DIRECT_MODES + PALETTE_SELECT_HUE_MODES + PALETTE_SELECT_SPECIAL_MODES

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
    PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES: "Similarity (Near-Duplicates)",
}

_NEUTRAL_SATURATION_EPSILON = 0.02
_NEUTRAL_CHROMA_EPSILON = 0.015
_WARM_HUE_CENTER = pi / 6.0
_SELECTION_THRESHOLD_OPTIONS = tuple(range(10, 101, 10))
_SIMILARITY_MIN_CUTOFF = 0.004
_SIMILARITY_MAX_CUTOFF = 0.060
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
    if mode == PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES:
        return _select_similarity_palette_indices(labels, threshold_percent, workspace)
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


def _select_similarity_palette_indices(labels: list[int], threshold_percent: int, workspace: ColorWorkspace) -> list[int]:
    if len(labels) < 2:
        return []

    cutoff = _similarity_cutoff(threshold_percent)
    oklab = workspace.labels_to_oklab(np.asarray(labels, dtype=np.int64))
    distances = hyab_distance(oklab[:, None, :], oklab[None, :, :]).astype(np.float64, copy=False)

    candidate_clusters: list[tuple[int, ...]] = []
    for left_index in range(len(labels) - 1):
        for right_index in range(left_index + 1, len(labels)):
            if float(distances[left_index, right_index]) > cutoff:
                continue
            candidate_clusters.append(_expand_similarity_cluster(left_index, right_index, distances, cutoff))

    if not candidate_clusters:
        return []

    best_cluster = min(candidate_clusters, key=lambda cluster: _similarity_cluster_sort_key(cluster, distances))
    return list(best_cluster)


def _coerce_selection_threshold_percent(value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 30
    parsed = max(0, min(100, parsed))
    return min(_SELECTION_THRESHOLD_OPTIONS, key=lambda candidate: abs(candidate - parsed))


def _similarity_cutoff(threshold_percent: int) -> float:
    threshold = _coerce_selection_threshold_percent(threshold_percent)
    weight = (threshold - 10) / 90.0
    return _SIMILARITY_MIN_CUTOFF + (weight * (_SIMILARITY_MAX_CUTOFF - _SIMILARITY_MIN_CUTOFF))


def _expand_similarity_cluster(seed_left: int, seed_right: int, distances: np.ndarray, cutoff: float) -> tuple[int, ...]:
    cluster_members = {seed_left, seed_right}
    for candidate_index in range(distances.shape[0]):
        if candidate_index in cluster_members:
            continue
        if all(float(distances[candidate_index, member_index]) <= cutoff for member_index in cluster_members):
            cluster_members.add(candidate_index)
    return tuple(sorted(cluster_members))


def _similarity_cluster_sort_key(cluster: tuple[int, ...], distances: np.ndarray) -> tuple[object, ...]:
    return (-len(cluster), _mean_internal_distance(cluster, distances), min(cluster), cluster)


def _mean_internal_distance(cluster: tuple[int, ...], distances: np.ndarray) -> float:
    if len(cluster) < 2:
        return 0.0
    subset = distances[np.ix_(cluster, cluster)]
    upper = subset[np.triu_indices(len(cluster), k=1)]
    return float(np.mean(upper)) if upper.size else 0.0


def _circular_hue_distance(left: float, right: float) -> float:
    delta = abs(left - right)
    return min(delta, (2.0 * pi) - delta)

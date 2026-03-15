from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from math import pi
from time import perf_counter
from typing import Callable

import numpy as np
from PIL import Image

from pixel_fix.types import LabelGrid

from .model import (
    PaletteColor,
    PaletteMappingResult,
    PaletteRamp,
    StructuredPalette,
    WeightedColorDataset,
)
from .sort import (
    PALETTE_SELECT_HUE_BLUE,
    PALETTE_SELECT_HUE_CYAN,
    PALETTE_SELECT_HUE_GREEN,
    PALETTE_SELECT_HUE_MAGENTA,
    PALETTE_SELECT_HUE_RED,
    PALETTE_SELECT_HUE_YELLOW,
    _HUE_BUCKET_CENTERS,
    _circular_hue_distance,
    _palette_metrics,
    _selection_ranking,
    _similarity_cutoff,
    select_palette_indices,
)
from .workspace import (
    ColorWorkspace,
    circular_lerp,
    hyab_distance,
    oklab_to_oklch,
    oklch_to_oklab,
)

PaletteProgressCallback = Callable[[int, str], None] | None

_WARM_HUE = np.deg2rad(75.0)
_COOL_HUE = np.deg2rad(285.0)
_BAYER_4 = np.asarray(
    (
        (0, 8, 2, 10),
        (12, 4, 14, 6),
        (3, 11, 1, 9),
        (15, 7, 13, 5),
    ),
    dtype=np.float64,
)
_BLUE_NOISE_8 = np.asarray(
    (
        (0, 48, 12, 60, 3, 51, 15, 63),
        (32, 16, 44, 28, 35, 19, 47, 31),
        (8, 56, 4, 52, 11, 59, 7, 55),
        (40, 24, 36, 20, 43, 27, 39, 23),
        (2, 50, 14, 62, 1, 49, 13, 61),
        (34, 18, 46, 30, 33, 17, 45, 29),
        (10, 58, 6, 54, 9, 57, 5, 53),
        (42, 26, 38, 22, 41, 25, 37, 21),
    ),
    dtype=np.float64,
)
MAX_KEY_COLORS = 24
_VISIBLE_ALPHA_THRESHOLD = 16
_MAX_DETECTION_VISIBLE_PIXELS = 200_000
_NEUTRAL_CHROMA_THRESHOLD = 0.03
_NEUTRAL_SLOT_THRESHOLD = 0.07
_HUE_BIN_COUNT = 36
_MIN_PEAK_SEPARATION = np.deg2rad(20.0)
_MIN_PEAK_MASS_RATIO = 0.04
_MIN_FAMILY_WEIGHT_RATIO = 0.03
RAMPFORGE_8_TARGET_ANCHORS = 12
RAMPFORGE_8_GENERATED_SHADES = 4
RAMPFORGE_8_CONTRAST_BIAS = 0.6
_RAMPFORGE_8_MIDTONE_MIN = 0.35
_RAMPFORGE_8_MIDTONE_MAX = 0.75
_RAMPFORGE_8_TARGET_LIGHTNESS = 0.55
_RAMPFORGE_8_SIMILARITY_THRESHOLD = 30
_RAMPFORGE_8_HUE_AUDIT_THRESHOLD = 20
_RAMPFORGE_8_BLACK_RAMP_SEED = 0x101010
_RAMPFORGE_8_WHITE_RAMP_SEED = 0xE0E0E0
_RAMPFORGE_8_BLACK_ENDPOINT = 0x000000
_RAMPFORGE_8_WHITE_ENDPOINT = 0xFFFFFF
_RAMPFORGE_8_ORANGE_MODE = "hue-orange"
_RAMPFORGE_8_HUE_CENTERS = {
    PALETTE_SELECT_HUE_RED: _HUE_BUCKET_CENTERS[PALETTE_SELECT_HUE_RED],
    _RAMPFORGE_8_ORANGE_MODE: pi / 6.0,
    PALETTE_SELECT_HUE_YELLOW: _HUE_BUCKET_CENTERS[PALETTE_SELECT_HUE_YELLOW],
    PALETTE_SELECT_HUE_GREEN: _HUE_BUCKET_CENTERS[PALETTE_SELECT_HUE_GREEN],
    PALETTE_SELECT_HUE_CYAN: _HUE_BUCKET_CENTERS[PALETTE_SELECT_HUE_CYAN],
    PALETTE_SELECT_HUE_BLUE: _HUE_BUCKET_CENTERS[PALETTE_SELECT_HUE_BLUE],
    PALETTE_SELECT_HUE_MAGENTA: _HUE_BUCKET_CENTERS[PALETTE_SELECT_HUE_MAGENTA],
}
_RAMPFORGE_8_HUE_MODES = (
    PALETTE_SELECT_HUE_RED,
    _RAMPFORGE_8_ORANGE_MODE,
    PALETTE_SELECT_HUE_YELLOW,
    PALETTE_SELECT_HUE_GREEN,
    PALETTE_SELECT_HUE_CYAN,
    PALETTE_SELECT_HUE_BLUE,
    PALETTE_SELECT_HUE_MAGENTA,
)
_RAMPFORGE_8_RED_TONAL_VARIANT_LIGHTNESS_DELTA = 0.055
_RAMPFORGE_8_RED_TONAL_VARIANT_CHROMA_DELTA = 0.02
_RAMPFORGE_8_WARM_MODES = frozenset(
    (
        PALETTE_SELECT_HUE_RED,
        _RAMPFORGE_8_ORANGE_MODE,
        PALETTE_SELECT_HUE_YELLOW,
    )
)
_RAMPFORGE_8_MODE_NEIGHBORS = {
    PALETTE_SELECT_HUE_RED: frozenset((PALETTE_SELECT_HUE_RED, _RAMPFORGE_8_ORANGE_MODE, PALETTE_SELECT_HUE_MAGENTA)),
    _RAMPFORGE_8_ORANGE_MODE: frozenset((PALETTE_SELECT_HUE_RED, _RAMPFORGE_8_ORANGE_MODE, PALETTE_SELECT_HUE_YELLOW)),
    PALETTE_SELECT_HUE_YELLOW: frozenset((_RAMPFORGE_8_ORANGE_MODE, PALETTE_SELECT_HUE_YELLOW, PALETTE_SELECT_HUE_GREEN)),
    PALETTE_SELECT_HUE_GREEN: frozenset((PALETTE_SELECT_HUE_YELLOW, PALETTE_SELECT_HUE_GREEN, PALETTE_SELECT_HUE_CYAN)),
    PALETTE_SELECT_HUE_CYAN: frozenset((PALETTE_SELECT_HUE_GREEN, PALETTE_SELECT_HUE_CYAN, PALETTE_SELECT_HUE_BLUE)),
    PALETTE_SELECT_HUE_BLUE: frozenset((PALETTE_SELECT_HUE_CYAN, PALETTE_SELECT_HUE_BLUE, PALETTE_SELECT_HUE_MAGENTA)),
    PALETTE_SELECT_HUE_MAGENTA: frozenset((PALETTE_SELECT_HUE_RED, PALETTE_SELECT_HUE_BLUE, PALETTE_SELECT_HUE_MAGENTA)),
}


@dataclass
class AdvancedPaletteComputation:
    palette: StructuredPalette
    histogram_size: int
    palette_seconds: float


@dataclass
class _KDNode:
    index: int
    axis: int
    point: np.ndarray
    left: "_KDNode | None" = None
    right: "_KDNode | None" = None


@dataclass(frozen=True)
class _Rampforge8HueSelection:
    mode: str
    representative_label: int
    vivid_labels: tuple[int, ...]


@dataclass(frozen=True)
class _Rampforge8RecoveryCandidate:
    label: int
    mode: str
    lightness: float
    weight: float
    weighted_error: float
    score: float


@dataclass(frozen=True)
class _Rampforge8ReplaceableSlot:
    palette_index: int
    ramp_index: int
    ramp_mode: str | None
    shade_index: int
    lightness: float
    seed_lightness: float
    mapped_weight: float
    redundancy_distance: float
    outer_distance: int


@dataclass(frozen=True)
class _Rampforge8RampProfile:
    lightness_scale: float
    center_chroma_boost: float
    edge_chroma_loss: float
    min_chroma_scale: float
    shadow_hue: float | None
    shadow_strength: float
    light_hue: float | None
    light_strength: float


def _rampforge_8_ramp_profile(mode: str | None) -> _Rampforge8RampProfile:
    if mode == PALETTE_SELECT_HUE_RED:
        return _Rampforge8RampProfile(
            lightness_scale=0.92,
            center_chroma_boost=0.26,
            edge_chroma_loss=0.10,
            min_chroma_scale=0.28,
            shadow_hue=_RAMPFORGE_8_HUE_CENTERS[PALETTE_SELECT_HUE_RED],
            shadow_strength=0.24,
            light_hue=_RAMPFORGE_8_HUE_CENTERS[_RAMPFORGE_8_ORANGE_MODE],
            light_strength=0.18,
        )
    if mode == _RAMPFORGE_8_ORANGE_MODE:
        return _Rampforge8RampProfile(
            lightness_scale=0.94,
            center_chroma_boost=0.22,
            edge_chroma_loss=0.17,
            min_chroma_scale=0.18,
            shadow_hue=_RAMPFORGE_8_HUE_CENTERS[PALETTE_SELECT_HUE_RED],
            shadow_strength=0.16,
            light_hue=_RAMPFORGE_8_HUE_CENTERS[PALETTE_SELECT_HUE_YELLOW],
            light_strength=0.18,
        )
    if mode == PALETTE_SELECT_HUE_YELLOW:
        return _Rampforge8RampProfile(
            lightness_scale=0.82,
            center_chroma_boost=0.22,
            edge_chroma_loss=0.10,
            min_chroma_scale=0.30,
            shadow_hue=_RAMPFORGE_8_HUE_CENTERS[_RAMPFORGE_8_ORANGE_MODE],
            shadow_strength=0.28,
            light_hue=_RAMPFORGE_8_HUE_CENTERS[PALETTE_SELECT_HUE_YELLOW],
            light_strength=0.06,
        )
    if mode == PALETTE_SELECT_HUE_GREEN:
        return _Rampforge8RampProfile(
            lightness_scale=0.98,
            center_chroma_boost=0.20,
            edge_chroma_loss=0.18,
            min_chroma_scale=0.14,
            shadow_hue=_RAMPFORGE_8_HUE_CENTERS[PALETTE_SELECT_HUE_GREEN],
            shadow_strength=0.10,
            light_hue=_RAMPFORGE_8_HUE_CENTERS[PALETTE_SELECT_HUE_YELLOW],
            light_strength=0.12,
        )
    if mode == PALETTE_SELECT_HUE_CYAN:
        return _Rampforge8RampProfile(
            lightness_scale=1.0,
            center_chroma_boost=0.18,
            edge_chroma_loss=0.22,
            min_chroma_scale=0.12,
            shadow_hue=_RAMPFORGE_8_HUE_CENTERS[PALETTE_SELECT_HUE_BLUE],
            shadow_strength=0.14,
            light_hue=_RAMPFORGE_8_HUE_CENTERS[PALETTE_SELECT_HUE_CYAN],
            light_strength=0.08,
        )
    if mode == PALETTE_SELECT_HUE_BLUE:
        return _Rampforge8RampProfile(
            lightness_scale=1.0,
            center_chroma_boost=0.19,
            edge_chroma_loss=0.21,
            min_chroma_scale=0.12,
            shadow_hue=_RAMPFORGE_8_HUE_CENTERS[PALETTE_SELECT_HUE_BLUE],
            shadow_strength=0.12,
            light_hue=_RAMPFORGE_8_HUE_CENTERS[PALETTE_SELECT_HUE_CYAN],
            light_strength=0.14,
        )
    if mode == PALETTE_SELECT_HUE_MAGENTA:
        return _Rampforge8RampProfile(
            lightness_scale=0.96,
            center_chroma_boost=0.20,
            edge_chroma_loss=0.18,
            min_chroma_scale=0.14,
            shadow_hue=_RAMPFORGE_8_HUE_CENTERS[PALETTE_SELECT_HUE_MAGENTA],
            shadow_strength=0.16,
            light_hue=_RAMPFORGE_8_HUE_CENTERS[PALETTE_SELECT_HUE_RED],
            light_strength=0.14,
        )
    return _Rampforge8RampProfile(
        lightness_scale=1.0,
        center_chroma_boost=0.18,
        edge_chroma_loss=0.30,
        min_chroma_scale=0.06,
        shadow_hue=_COOL_HUE,
        shadow_strength=0.30,
        light_hue=_WARM_HUE,
        light_strength=0.25,
    )


def _rampforge_8_family_penalty(slot_mode: str | None, candidate_mode: str) -> float:
    if slot_mode is None:
        return 1.5
    if slot_mode == candidate_mode:
        return 0.0
    if slot_mode in _RAMPFORGE_8_MODE_NEIGHBORS.get(candidate_mode, frozenset()):
        if candidate_mode in _RAMPFORGE_8_WARM_MODES and slot_mode in _RAMPFORGE_8_WARM_MODES:
            return 0.3
        return 0.45
    if candidate_mode in _RAMPFORGE_8_WARM_MODES and slot_mode in _RAMPFORGE_8_WARM_MODES:
        return 0.7
    return 1.2


def _rampforge_8_allows_red_tonal_variant(
    label: int,
    compare_labels: list[int],
    workspace: ColorWorkspace,
    *,
    family_total: int,
) -> bool:
    if family_total >= 2:
        return False
    candidate_metric = _rampforge_8_label_metric(label, workspace)
    if candidate_metric.is_neutral:
        return False
    same_mode_labels = [
        int(existing)
        for existing in compare_labels
        if _rampforge_8_label_mode(int(existing), workspace) == PALETTE_SELECT_HUE_RED
    ]
    if not same_mode_labels:
        return False
    candidate_oklab = workspace.label_to_oklab(int(label)).reshape(1, 3)
    same_mode_oklab = workspace.labels_to_oklab(np.asarray(same_mode_labels, dtype=np.int64))
    distances = hyab_distance(same_mode_oklab, candidate_oklab).astype(np.float64, copy=False)
    closest_index = int(np.argmin(distances))
    closest_metric = _rampforge_8_label_metric(same_mode_labels[closest_index], workspace)
    return bool(
        candidate_metric.lightness <= closest_metric.lightness - _RAMPFORGE_8_RED_TONAL_VARIANT_LIGHTNESS_DELTA
        or abs(candidate_metric.lightness - closest_metric.lightness) >= _RAMPFORGE_8_RED_TONAL_VARIANT_LIGHTNESS_DELTA
        or abs(candidate_metric.chroma - closest_metric.chroma) >= _RAMPFORGE_8_RED_TONAL_VARIANT_CHROMA_DELTA
    )


class PaletteKDTree:
    def __init__(self, points: np.ndarray):
        self.points = np.asarray(points, dtype=np.float64)
        indices = list(range(len(self.points)))
        self.root = self._build(indices, axis=0)

    def _build(self, indices: list[int], axis: int) -> _KDNode | None:
        if not indices:
            return None
        indices.sort(key=lambda idx: self.points[idx, axis])
        mid = len(indices) // 2
        index = indices[mid]
        next_axis = (axis + 1) % 3
        return _KDNode(
            index=index,
            axis=axis,
            point=self.points[index],
            left=self._build(indices[:mid], next_axis),
            right=self._build(indices[mid + 1 :], next_axis),
        )

    def query(self, target: np.ndarray, k: int = 4) -> list[int]:
        heap: list[tuple[float, int]] = []

        def search(node: _KDNode | None) -> None:
            if node is None:
                return
            squared = float(np.sum((target - node.point) ** 2))
            if len(heap) < k:
                heappush(heap, (-squared, node.index))
            elif squared < -heap[0][0]:
                heappop(heap)
                heappush(heap, (-squared, node.index))

            delta = float(target[node.axis] - node.point[node.axis])
            near = node.left if delta < 0 else node.right
            far = node.right if delta < 0 else node.left
            search(near)
            if len(heap) < k or delta * delta < -heap[0][0]:
                search(far)

        search(self.root)
        return [index for _dist, index in sorted(heap, reverse=True)]


def _emit_progress(callback: PaletteProgressCallback, percent: int, message: str) -> None:
    if callback is not None:
        callback(percent, message)


def build_weighted_dataset(labels: LabelGrid, workspace: ColorWorkspace | None = None) -> WeightedColorDataset:
    workspace = workspace or ColorWorkspace()
    flat = np.asarray([value for row in labels for value in row], dtype=np.int64)
    if flat.size == 0:
        return WeightedColorDataset(
            labels=np.asarray([], dtype=np.int64),
            counts=np.asarray([], dtype=np.float64),
            oklab=np.empty((0, 3), dtype=np.float64),
        )

    unique, counts = np.unique(flat, return_counts=True)
    order = np.argsort(counts)[::-1]
    labels_sorted = unique[order].astype(np.int64)
    counts_sorted = counts[order].astype(np.float64)
    return WeightedColorDataset(
        labels=labels_sorted,
        counts=counts_sorted,
        oklab=workspace.labels_to_oklab(labels_sorted),
    )


def _weighted_percentile(values: np.ndarray, weights: np.ndarray, percentile: float) -> float:
    if values.size == 0:
        return 0.0
    order = np.argsort(values)
    sorted_values = values[order]
    sorted_weights = weights[order]
    cumulative = np.cumsum(sorted_weights)
    if cumulative[-1] <= 0:
        return float(sorted_values[len(sorted_values) // 2])
    target = float(np.clip(percentile, 0.0, 1.0) * cumulative[-1])
    index = int(np.searchsorted(cumulative, target, side="left"))
    return float(sorted_values[min(index, len(sorted_values) - 1)])


def _angular_distance(left: float | np.ndarray, right: float | np.ndarray) -> np.ndarray:
    return np.abs(((np.asarray(left) - np.asarray(right) + np.pi) % (2 * np.pi)) - np.pi)


def _select_representative_label(
    labels: np.ndarray,
    weights: np.ndarray,
    lightness: np.ndarray,
    chroma: np.ndarray,
) -> int:
    if labels.size == 0:
        return 0
    p25 = _weighted_percentile(lightness, weights, 0.25)
    p75 = _weighted_percentile(lightness, weights, 0.75)
    median_l = _weighted_percentile(lightness, weights, 0.5)
    candidates = np.flatnonzero((lightness >= p25) & (lightness <= p75))
    if candidates.size == 0:
        candidates = np.arange(labels.size, dtype=np.int64)
    order = np.lexsort(
        (
            -chroma[candidates],
            np.abs(lightness[candidates] - median_l),
            -weights[candidates],
        )
    )
    return int(labels[int(candidates[int(order[0])])])


def _dedupe_detected_labels(labels: list[int], workspace: ColorWorkspace, max_colors: int) -> list[int]:
    if not labels:
        return []
    label_array = np.asarray(labels, dtype=np.int64)
    oklch = oklab_to_oklch(workspace.labels_to_oklab(label_array))
    selected: list[int] = []
    selected_hues: list[float] = []
    has_neutral = False
    for index, label in enumerate(label_array.tolist()):
        chroma = float(oklch[index, 1])
        if chroma < _NEUTRAL_CHROMA_THRESHOLD:
            if not has_neutral:
                selected.append(int(label))
                has_neutral = True
        else:
            hue = float(oklch[index, 2])
            if all(float(_angular_distance(hue, existing)) >= _MIN_PEAK_SEPARATION for existing in selected_hues):
                selected.append(int(label))
                selected_hues.append(hue)
        if len(selected) >= max_colors:
            break
    return selected[:max_colors]


def _build_weighted_image_histogram(
    image: Image.Image,
    *,
    max_visible_pixels: int,
) -> tuple[np.ndarray, np.ndarray]:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    alpha = rgba[..., 3]
    visible_mask = alpha >= _VISIBLE_ALPHA_THRESHOLD
    visible_pixels = int(np.count_nonzero(visible_mask))
    if visible_pixels == 0:
        return np.asarray([], dtype=np.int64), np.asarray([], dtype=np.float64)

    stride = 1
    if visible_pixels > max_visible_pixels:
        stride = int(np.ceil(np.sqrt(visible_pixels / max_visible_pixels)))
        rgba = rgba[::stride, ::stride]
        alpha = rgba[..., 3]
        visible_mask = alpha >= _VISIBLE_ALPHA_THRESHOLD

    visible = rgba[visible_mask]
    rgb = visible[:, :3].astype(np.int64)
    weights = visible[:, 3].astype(np.float64) / 255.0
    packed = (rgb[:, 0] << 16) | (rgb[:, 1] << 8) | rgb[:, 2]
    unique, inverse = np.unique(packed, return_inverse=True)
    aggregated = np.bincount(inverse, weights=weights)
    order = np.argsort(aggregated)[::-1]
    return unique[order].astype(np.int64), aggregated[order].astype(np.float64)


def _backfill_detected_labels(
    selected: list[int],
    labels: np.ndarray,
    weights: np.ndarray,
    oklab: np.ndarray,
    workspace: ColorWorkspace,
    limit: int,
) -> list[int]:
    if len(selected) >= limit or labels.size == 0:
        return selected[:limit]
    fallback_labels = labels
    fallback_weights = weights
    fallback_oklab = oklab
    if selected:
        oklch = oklab_to_oklch(oklab)
        selected_oklch = oklab_to_oklch(workspace.labels_to_oklab(np.asarray(selected, dtype=np.int64)))
        neutral_mask = oklch[:, 1] < _NEUTRAL_CHROMA_THRESHOLD
        selected_neutral = selected_oklch[:, 1] < _NEUTRAL_CHROMA_THRESHOLD
        candidate_mask = np.zeros(labels.shape[0], dtype=bool)
        if bool(np.any(selected_neutral)):
            candidate_mask |= neutral_mask
        selected_hues = selected_oklch[~selected_neutral, 2]
        if selected_hues.size:
            candidate_mask |= (
                ~neutral_mask
                & (np.min(_angular_distance(oklch[:, 2][:, None], selected_hues[None, :]), axis=1) <= (_MIN_PEAK_SEPARATION * 1.5))
            )
        if bool(np.any(candidate_mask)):
            fallback_labels = labels[candidate_mask]
            fallback_weights = weights[candidate_mask]
            fallback_oklab = oklab[candidate_mask]
    fallback_dataset = WeightedColorDataset(labels=fallback_labels, counts=fallback_weights, oklab=fallback_oklab)
    fallback = suggest_seed_colors(fallback_dataset, count=limit)
    chosen = set(selected)
    for label in fallback:
        if label in chosen:
            continue
        selected.append(label)
        chosen.add(label)
        if len(selected) >= limit:
            break
    return selected[:limit]


def detect_key_colors_from_image(
    image: Image.Image,
    *,
    max_colors: int = MAX_KEY_COLORS,
    workspace: ColorWorkspace | None = None,
    progress_callback: PaletteProgressCallback = None,
) -> list[int]:
    workspace = workspace or ColorWorkspace()
    limit = max(1, min(int(max_colors), MAX_KEY_COLORS))
    _emit_progress(progress_callback, 20, "Scanning original colours...")
    labels, weights = _build_weighted_image_histogram(image, max_visible_pixels=_MAX_DETECTION_VISIBLE_PIXELS)
    if labels.size == 0:
        return []

    oklab = workspace.labels_to_oklab(labels)
    oklch = oklab_to_oklch(oklab)
    lightness = oklab[:, 0]
    chroma = oklch[:, 1]
    hue = oklch[:, 2]
    total_weight = float(np.sum(weights))
    neutral_mask = chroma < _NEUTRAL_CHROMA_THRESHOLD
    chromatic_mask = ~neutral_mask

    selections: list[tuple[float, int]] = []
    neutral_weight = float(np.sum(weights[neutral_mask]))
    reserve_neutral = bool(neutral_mask.any() and total_weight > 0 and (neutral_weight / total_weight) >= _NEUTRAL_SLOT_THRESHOLD)
    chromatic_slots = max(0, limit - (1 if reserve_neutral else 0))

    if reserve_neutral:
        neutral_label = _select_representative_label(
            labels[neutral_mask],
            weights[neutral_mask],
            lightness[neutral_mask],
            chroma[neutral_mask],
        )
        selections.append((neutral_weight, neutral_label))

    _emit_progress(progress_callback, 50, "Finding hue families...")
    if chromatic_slots > 0 and chromatic_mask.any():
        chromatic_labels = labels[chromatic_mask]
        chromatic_weights = weights[chromatic_mask]
        chromatic_lightness = lightness[chromatic_mask]
        chromatic_chroma = chroma[chromatic_mask]
        chromatic_hue = hue[chromatic_mask]
        hue_weights = chromatic_weights * np.clip(chromatic_chroma, 0.05, 0.25)
        bins = np.floor((chromatic_hue / (2 * np.pi)) * _HUE_BIN_COUNT).astype(np.int64) % _HUE_BIN_COUNT
        histogram = np.bincount(bins, weights=hue_weights, minlength=_HUE_BIN_COUNT)
        smoothed = (np.roll(histogram, 1) * 0.25) + (histogram * 0.5) + (np.roll(histogram, -1) * 0.25)
        total_hist_weight = float(np.sum(histogram))
        candidate_bins = [
            index
            for index in range(_HUE_BIN_COUNT)
            if smoothed[index] >= smoothed[(index - 1) % _HUE_BIN_COUNT]
            and smoothed[index] > smoothed[(index + 1) % _HUE_BIN_COUNT]
        ]
        candidate_bins.sort(key=lambda index: smoothed[index], reverse=True)
        min_peak_mass = _MIN_PEAK_MASS_RATIO * total_hist_weight
        centers = ((np.arange(_HUE_BIN_COUNT, dtype=np.float64) + 0.5) / _HUE_BIN_COUNT) * (2 * np.pi)

        kept_bins: list[int] = []
        for peak_index in candidate_bins:
            if smoothed[peak_index] < min_peak_mass:
                continue
            peak_hue = centers[peak_index]
            if any(float(_angular_distance(peak_hue, centers[existing])) < _MIN_PEAK_SEPARATION for existing in kept_bins):
                continue
            kept_bins.append(peak_index)
            if len(kept_bins) >= chromatic_slots:
                break

        if kept_bins:
            kept_hues = centers[np.asarray(kept_bins, dtype=np.int64)]
            assignments = np.argmin(_angular_distance(chromatic_hue[:, None], kept_hues[None, :]), axis=1)
            family_members: dict[int, list[int]] = {index: [] for index in range(len(kept_bins))}
            for chromatic_index, family_index in enumerate(assignments.tolist()):
                family_members[family_index].append(chromatic_index)

            minimum_family_weight = _MIN_FAMILY_WEIGHT_RATIO * total_weight
            family_weights = {family_index: float(np.sum(chromatic_weights[members])) for family_index, members in family_members.items()}
            for family_index in sorted(family_members.keys(), key=lambda index: family_weights[index]):
                if len(family_members) <= 1 or family_weights[family_index] >= minimum_family_weight:
                    continue
                source_hue = kept_hues[family_index]
                candidates = [index for index in family_members.keys() if index != family_index and family_members[index]]
                if not candidates:
                    continue
                target_family = min(candidates, key=lambda index: float(_angular_distance(source_hue, kept_hues[index])))
                family_members[target_family].extend(family_members[family_index])
                family_members[family_index] = []
                family_weights[target_family] = float(np.sum(chromatic_weights[family_members[target_family]]))
                family_weights[family_index] = 0.0

            _emit_progress(progress_callback, 80, "Selecting representative midtones...")
            chromatic_selections: list[tuple[float, int]] = []
            for family_index, members in family_members.items():
                if not members:
                    continue
                member_indices = np.asarray(members, dtype=np.int64)
                family_label = _select_representative_label(
                    chromatic_labels[member_indices],
                    chromatic_weights[member_indices],
                    chromatic_lightness[member_indices],
                    chromatic_chroma[member_indices],
                )
                chromatic_selections.append((float(np.sum(chromatic_weights[member_indices])), family_label))
            selections.extend(sorted(chromatic_selections, key=lambda item: item[0], reverse=True)[:chromatic_slots])

    if not selections:
        _emit_progress(progress_callback, 80, "Selecting representative midtones...")
        fallback_dataset = WeightedColorDataset(labels=labels, counts=weights, oklab=oklab)
        fallback = suggest_seed_colors(fallback_dataset, count=limit)
        selected = _dedupe_detected_labels(fallback, workspace, limit)
        return _backfill_detected_labels(selected, labels, weights, oklab, workspace, limit)

    ordered_labels = [label for _weight, label in sorted(selections, key=lambda item: item[0], reverse=True)]
    selected = _dedupe_detected_labels(ordered_labels, workspace, limit)
    return _backfill_detected_labels(selected, labels, weights, oklab, workspace, limit)


def suggest_seed_colors(dataset: WeightedColorDataset, count: int = 4) -> list[int]:
    if dataset.size == 0:
        return []
    target = max(1, min(count, MAX_KEY_COLORS, dataset.size))
    chosen = [0]
    if target == 1:
        return [int(dataset.labels[0])]

    weights = np.sqrt(np.maximum(dataset.counts, 1.0))
    while len(chosen) < target:
        selected = dataset.oklab[chosen]
        distances = hyab_distance(dataset.oklab[:, None, :], selected[None, :, :]).min(axis=1)
        scores = distances * weights
        scores[np.asarray(chosen, dtype=np.int64)] = -1.0
        next_index = int(np.argmax(scores))
        if next_index in chosen:
            break
        chosen.append(next_index)
    return [int(dataset.labels[index]) for index in chosen]


def _subset_weighted_dataset(dataset: WeightedColorDataset, mask: np.ndarray) -> WeightedColorDataset:
    selected = np.flatnonzero(mask)
    return WeightedColorDataset(
        labels=dataset.labels[selected],
        counts=dataset.counts[selected],
        oklab=dataset.oklab[selected],
    )


def _rampforge_8_candidate_pool(dataset: WeightedColorDataset) -> WeightedColorDataset:
    if dataset.size == 0:
        return dataset
    lightness = dataset.oklab[:, 0]
    mask = (lightness >= _RAMPFORGE_8_MIDTONE_MIN) & (lightness <= _RAMPFORGE_8_MIDTONE_MAX)
    if bool(np.any(mask)):
        return _subset_weighted_dataset(dataset, mask)
    return dataset


def _rampforge_8_target_chroma(dataset: WeightedColorDataset) -> float:
    if dataset.size == 0:
        return 0.0
    oklch = oklab_to_oklch(dataset.oklab)
    chroma = oklch[:, 1]
    chromatic = chroma >= _NEUTRAL_CHROMA_THRESHOLD
    if bool(np.any(chromatic)):
        return _weighted_percentile(chroma[chromatic], dataset.counts[chromatic], 0.5)
    return _weighted_percentile(chroma, dataset.counts, 0.5)


def _select_rampforge_8_anchor_label(
    labels: np.ndarray,
    weights: np.ndarray,
    oklab: np.ndarray,
    *,
    target_chroma: float,
) -> int:
    if labels.size == 0:
        return 0
    oklch = oklab_to_oklch(oklab)
    lightness = oklab[:, 0]
    chroma = oklch[:, 1]
    max_weight = float(np.max(weights)) if weights.size else 1.0
    normalized_weight = weights / max(max_weight, 1.0)
    score = (
        (np.abs(lightness - _RAMPFORGE_8_TARGET_LIGHTNESS) * 2.0)
        + (np.abs(chroma - target_chroma) * 1.5)
        - (normalized_weight * 0.5)
    )
    order = np.lexsort((labels.astype(np.int64), -weights, score))
    return int(labels[int(order[0])])


def _rampforge_8_anchor_score(
    lightness: float,
    chroma: float,
    *,
    target_chroma: float,
    normalized_weight: float,
) -> float:
    return (
        (abs(lightness - _RAMPFORGE_8_TARGET_LIGHTNESS) * 2.0)
        + (abs(chroma - target_chroma) * 1.5)
        - (normalized_weight * 0.5)
    )


def _rampforge_8_hue_peak_labels(dataset: WeightedColorDataset, *, target_chroma: float) -> list[int]:
    if dataset.size == 0:
        return []
    oklch = oklab_to_oklch(dataset.oklab)
    chroma = oklch[:, 1]
    chromatic_mask = chroma >= _NEUTRAL_CHROMA_THRESHOLD
    if not bool(np.any(chromatic_mask)):
        return []

    labels = dataset.labels[chromatic_mask]
    weights = dataset.counts[chromatic_mask]
    oklab = dataset.oklab[chromatic_mask]
    hue = oklch[chromatic_mask, 2]
    chroma = chroma[chromatic_mask]
    hue_weights = weights * np.clip(chroma, 0.05, 0.25)
    bins = np.floor((hue / (2 * np.pi)) * _HUE_BIN_COUNT).astype(np.int64) % _HUE_BIN_COUNT
    histogram = np.bincount(bins, weights=hue_weights, minlength=_HUE_BIN_COUNT)
    smoothed = (np.roll(histogram, 1) * 0.25) + (histogram * 0.5) + (np.roll(histogram, -1) * 0.25)
    total_hist_weight = float(np.sum(histogram))
    candidate_bins = [
        index
        for index in range(_HUE_BIN_COUNT)
        if smoothed[index] >= smoothed[(index - 1) % _HUE_BIN_COUNT]
        and smoothed[index] > smoothed[(index + 1) % _HUE_BIN_COUNT]
    ]
    candidate_bins.sort(key=lambda index: smoothed[index], reverse=True)
    min_peak_mass = _MIN_PEAK_MASS_RATIO * total_hist_weight
    centers = ((np.arange(_HUE_BIN_COUNT, dtype=np.float64) + 0.5) / _HUE_BIN_COUNT) * (2 * np.pi)

    kept_bins: list[int] = []
    for peak_index in candidate_bins:
        if smoothed[peak_index] < min_peak_mass:
            continue
        peak_hue = centers[peak_index]
        if any(float(_angular_distance(peak_hue, centers[existing])) < _MIN_PEAK_SEPARATION for existing in kept_bins):
            continue
        kept_bins.append(peak_index)
        if len(kept_bins) >= RAMPFORGE_8_TARGET_ANCHORS:
            break

    if not kept_bins:
        return []

    kept_hues = centers[np.asarray(kept_bins, dtype=np.int64)]
    assignments = np.argmin(_angular_distance(hue[:, None], kept_hues[None, :]), axis=1)
    selections: list[tuple[float, int]] = []
    for family_index in range(len(kept_bins)):
        member_indices = np.flatnonzero(assignments == family_index)
        if member_indices.size == 0:
            continue
        selections.append(
            (
                float(np.sum(weights[member_indices])),
                _select_rampforge_8_anchor_label(
                    labels[member_indices],
                    weights[member_indices],
                    oklab[member_indices],
                    target_chroma=target_chroma,
                ),
            )
        )
    return [label for _weight, label in sorted(selections, key=lambda item: item[0], reverse=True)]


def _rampforge_8_label_metric(label: int, workspace: ColorWorkspace):
    return _palette_metrics([int(label)], workspace)[0]


def _rampforge_8_label_mode(label: int, workspace: ColorWorkspace) -> str | None:
    metric = _rampforge_8_label_metric(label, workspace)
    if metric.is_neutral:
        return None
    return min(
        _RAMPFORGE_8_HUE_MODES,
        key=lambda candidate: _circular_hue_distance(metric.hue, _RAMPFORGE_8_HUE_CENTERS[candidate]),
    )


def _rampforge_8_rank_metrics_for_mode(metrics: list, mode: str) -> list:
    if mode != _RAMPFORGE_8_ORANGE_MODE:
        return _selection_ranking(metrics, mode)
    eligible = [metric for metric in metrics if not metric.is_neutral]
    if not eligible:
        return []
    center = _RAMPFORGE_8_HUE_CENTERS[mode]
    return sorted(
        eligible,
        key=lambda metric: (_circular_hue_distance(metric.hue, center), -metric.saturation, -metric.chroma, metric.index),
    )


def _rampforge_8_select_bucket_indices(labels: list[int], mode: str, workspace: ColorWorkspace) -> list[int]:
    if mode != _RAMPFORGE_8_ORANGE_MODE:
        return select_palette_indices(labels, mode, _RAMPFORGE_8_HUE_AUDIT_THRESHOLD, workspace)
    if not labels:
        return []
    ranked = _rampforge_8_rank_metrics_for_mode(_palette_metrics(labels, workspace), mode)
    if not ranked:
        return []
    target_count = max(1, int(np.ceil(len(labels) * (_RAMPFORGE_8_HUE_AUDIT_THRESHOLD / 100.0))))
    limited = ranked[: min(target_count, len(ranked))]
    return sorted(metric.index for metric in limited)


def _rampforge_8_hue_bucket_member_indices(dataset: WeightedColorDataset, workspace: ColorWorkspace) -> dict[str, list[int]]:
    members = {mode: [] for mode in _RAMPFORGE_8_HUE_MODES}
    if dataset.size == 0:
        return members
    for metric in _palette_metrics(dataset.labels.tolist(), workspace):
        if metric.is_neutral:
            continue
        mode = min(
            _RAMPFORGE_8_HUE_MODES,
            key=lambda candidate: _circular_hue_distance(metric.hue, _RAMPFORGE_8_HUE_CENTERS[candidate]),
        )
        members[mode].append(metric.index)
    return members


def _rampforge_8_hue_bucket_selections(
    dataset: WeightedColorDataset,
    workspace: ColorWorkspace,
) -> dict[str, _Rampforge8HueSelection]:
    selections: dict[str, _Rampforge8HueSelection] = {}
    if dataset.size == 0:
        return selections
    labels_list = dataset.labels.tolist()
    metrics_by_index = {metric.index: metric for metric in _palette_metrics(labels_list, workspace)}
    weight_lookup = {
        int(label): float(weight)
        for label, weight in zip(dataset.labels.tolist(), dataset.counts.tolist(), strict=True)
    }
    members = _rampforge_8_hue_bucket_member_indices(dataset, workspace)
    for mode in _RAMPFORGE_8_HUE_MODES:
        bucket_members = members[mode]
        if not bucket_members:
            continue
        bucket_labels = [int(labels_list[index]) for index in bucket_members]
        selected_indices = _rampforge_8_select_bucket_indices(bucket_labels, mode, workspace)
        if not selected_indices:
            continue
        dataset_indices = [bucket_members[index] for index in selected_indices]
        ranked = _rampforge_8_rank_metrics_for_mode([metrics_by_index[index] for index in dataset_indices], mode)
        if not ranked:
            continue
        candidate_ranked = [
            metric
            for metric in ranked
            if metric.lightness >= _RAMPFORGE_8_MIDTONE_MIN
        ] or ranked
        vivid_count = max(1, (len(candidate_ranked) + 1) // 2)
        working_metrics = candidate_ranked[:vivid_count] or candidate_ranked
        working_indices = np.asarray([metric.index for metric in working_metrics], dtype=np.int64)
        working_oklab = dataset.oklab[working_indices]
        working_weights = dataset.counts[working_indices]
        working_oklch = oklab_to_oklch(working_oklab)
        target_lightness = _weighted_percentile(working_oklab[:, 0], working_weights, 0.5)
        target_chroma = _weighted_percentile(working_oklch[:, 1], working_weights, 0.5)
        center = _RAMPFORGE_8_HUE_CENTERS[mode]
        representative = min(
            working_metrics,
            key=lambda metric: (
                _circular_hue_distance(metric.hue, center),
                -metric.saturation,
                -metric.chroma,
                abs(metric.lightness - target_lightness),
                abs(metric.chroma - target_chroma),
                -weight_lookup.get(int(metric.label), 0.0),
                metric.index,
            ),
        )
        selections[mode] = _Rampforge8HueSelection(
            mode=mode,
            representative_label=int(representative.label),
            vivid_labels=tuple(int(metric.label) for metric in working_metrics),
        )
    return selections


def _rampforge_8_best_label_for_hue_mode(labels: list[int], mode: str, workspace: ColorWorkspace) -> int | None:
    if not labels:
        return None
    ranked = _rampforge_8_rank_metrics_for_mode(_palette_metrics(labels, workspace), mode)
    if not ranked:
        return None
    return int(ranked[0].label)


def _rampforge_8_needs_forced_bucket_label(
    labels: list[int],
    representative_label: int,
    *,
    mode: str,
    workspace: ColorWorkspace,
) -> bool:
    if representative_label in labels:
        return False
    best = _rampforge_8_best_label_for_hue_mode(labels + [representative_label], mode, workspace)
    return best == representative_label


def _rampforge_8_anchor_sort_key(
    label: int,
    *,
    target_chroma: float,
    workspace: ColorWorkspace,
    weight_lookup: dict[int, float],
    max_weight: float,
    protected_modes: set[str] | None = None,
) -> tuple[int, int, float, float, int]:
    metric = _rampforge_8_label_metric(label, workspace)
    label_mode = _rampforge_8_label_mode(label, workspace)
    weight = float(weight_lookup.get(int(label), 0.0))
    normalized_weight = weight / max(max_weight, 1.0)
    return (
        1 if label_mode in (protected_modes or set()) else 0,
        1 if label_mode is None else 0,
        _rampforge_8_anchor_score(
            float(metric.lightness),
            float(metric.chroma),
            target_chroma=target_chroma,
            normalized_weight=normalized_weight,
        ),
        -weight,
        int(label),
    )


def _cap_rampforge_8_anchor_labels(
    labels: list[int],
    *,
    protected_labels: set[int],
    protected_modes: set[str],
    dataset: WeightedColorDataset,
    target_chroma: float,
    workspace: ColorWorkspace,
) -> list[int]:
    unique = list(dict.fromkeys(int(label) for label in labels))
    if len(unique) <= RAMPFORGE_8_TARGET_ANCHORS:
        return unique
    protected = {int(label) for label in protected_labels}
    protected_count = sum(1 for label in unique if label in protected)
    if protected_count >= RAMPFORGE_8_TARGET_ANCHORS:
        return [label for label in unique if label in protected][:RAMPFORGE_8_TARGET_ANCHORS]
    weight_lookup = {int(label): float(weight) for label, weight in zip(dataset.labels.tolist(), dataset.counts.tolist(), strict=True)}
    max_weight = float(np.max(dataset.counts)) if dataset.size else 1.0
    keep_count = max(0, RAMPFORGE_8_TARGET_ANCHORS - protected_count)
    non_protected = [label for label in unique if label not in protected]
    strongest = sorted(
        non_protected,
        key=lambda label: _rampforge_8_anchor_sort_key(
            label,
            target_chroma=target_chroma,
            workspace=workspace,
            weight_lookup=weight_lookup,
            max_weight=max_weight,
            protected_modes=protected_modes,
        ),
    )[:keep_count]
    keep = protected | set(strongest)
    return [label for label in unique if label in keep][:RAMPFORGE_8_TARGET_ANCHORS]


def _merge_rampforge_8_anchor_labels(
    labels: list[int],
    workspace: ColorWorkspace,
    *,
    protected_labels: set[int] | None = None,
) -> list[int]:
    if len(labels) < 2:
        return labels
    from .edit import merge_palette_labels
    from .sort import PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES

    protected = {int(label) for label in protected_labels or set()}
    merged = list(dict.fromkeys(int(label) for label in labels))
    while len(merged) >= 2:
        cluster = select_palette_indices(
            merged,
            PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES,
            _RAMPFORGE_8_SIMILARITY_THRESHOLD,
            workspace,
        )
        if len(cluster) < 2:
            break
        cluster_set = set(cluster)
        protected_cluster = [index for index in cluster if merged[index] in protected]
        next_labels: list[int] = []
        if protected_cluster:
            keep_index = min(protected_cluster)
            for index, label in enumerate(merged):
                if index == keep_index:
                    next_labels.append(int(label))
                if index in cluster_set:
                    continue
                next_labels.append(int(label))
        else:
            replacement_index = min(cluster)
            merged_label = merge_palette_labels([merged[index] for index in cluster], workspace=workspace)
            for index, label in enumerate(merged):
                if index == replacement_index:
                    next_labels.append(int(merged_label))
                if index in cluster_set:
                    continue
                next_labels.append(int(label))
        merged = list(dict.fromkeys(next_labels))
    return merged


def _select_rampforge_8_anchors(dataset: WeightedColorDataset, workspace: ColorWorkspace) -> list[int]:
    if dataset.size == 0:
        return []
    candidate_pool = _rampforge_8_candidate_pool(dataset)
    target_chroma = _rampforge_8_target_chroma(candidate_pool)
    bucket_selections = _rampforge_8_hue_bucket_selections(dataset, workspace)
    selected = _rampforge_8_hue_peak_labels(candidate_pool, target_chroma=target_chroma)
    fallback = [selection.representative_label for selection in bucket_selections.values()]
    fallback.extend(suggest_seed_colors(candidate_pool, count=RAMPFORGE_8_TARGET_ANCHORS))
    for label in fallback:
        if label not in selected:
            selected.append(int(label))
        if len(selected) >= RAMPFORGE_8_TARGET_ANCHORS:
            break
    baseline = _merge_rampforge_8_anchor_labels(selected, workspace)
    protected_by_mode: dict[str, int] = {}
    for mode, selection in bucket_selections.items():
        if _rampforge_8_needs_forced_bucket_label(
            baseline,
            selection.representative_label,
            mode=mode,
            workspace=workspace,
        ):
            baseline.append(int(selection.representative_label))
            protected_by_mode[mode] = int(selection.representative_label)
    merged = _merge_rampforge_8_anchor_labels(
        baseline,
        workspace,
        protected_labels=set(protected_by_mode.values()),
    )
    capped = _cap_rampforge_8_anchor_labels(
        merged,
        protected_labels=set(protected_by_mode.values()),
        protected_modes=set(protected_by_mode),
        dataset=dataset,
        target_chroma=target_chroma,
        workspace=workspace,
    )
    return _replace_neutralish_rampforge_8_anchors(
        capped,
        bucket_selections=bucket_selections,
        dataset=dataset,
        target_chroma=target_chroma,
        workspace=workspace,
    )


def _replace_neutralish_rampforge_8_anchors(
    labels: list[int],
    *,
    bucket_selections: dict[str, _Rampforge8HueSelection],
    dataset: WeightedColorDataset,
    target_chroma: float,
    workspace: ColorWorkspace,
) -> list[int]:
    finalized = list(dict.fromkeys(int(label) for label in labels))
    if not finalized or not bucket_selections:
        return finalized
    finalized = [label for label in finalized if _rampforge_8_label_mode(label, workspace) is not None]
    if not finalized:
        return finalized
    weight_lookup = {
        int(label): float(weight)
        for label, weight in zip(dataset.labels.tolist(), dataset.counts.tolist(), strict=True)
    }
    max_weight = float(np.max(dataset.counts)) if dataset.size else 1.0
    while True:
        uncovered = [
            selection
            for mode, selection in bucket_selections.items()
            if _rampforge_8_needs_forced_bucket_label(
                finalized,
                selection.representative_label,
                mode=mode,
                workspace=workspace,
            )
        ]
        if not uncovered:
            return finalized
        if len(finalized) < RAMPFORGE_8_TARGET_ANCHORS:
            replacement = min(
                (selection.representative_label for selection in uncovered),
                key=lambda label: _rampforge_8_anchor_sort_key(
                    label,
                    target_chroma=target_chroma,
                    workspace=workspace,
                    weight_lookup=weight_lookup,
                    max_weight=max_weight,
                    protected_modes=None,
                ),
            )
            if replacement in finalized:
                return finalized
            finalized.append(int(replacement))
            finalized = list(dict.fromkeys(finalized))
            continue
        neutralish = [label for label in finalized if _rampforge_8_label_mode(label, workspace) is None]
        if not neutralish:
            return finalized
        replacement = min(
            (selection.representative_label for selection in uncovered),
            key=lambda label: _rampforge_8_anchor_sort_key(
                label,
                target_chroma=target_chroma,
                workspace=workspace,
                weight_lookup=weight_lookup,
                max_weight=max_weight,
                protected_modes=None,
            ),
        )
        weakest = max(
            neutralish,
            key=lambda label: _rampforge_8_anchor_sort_key(
                label,
                target_chroma=target_chroma,
                workspace=workspace,
                weight_lookup=weight_lookup,
                max_weight=max_weight,
                protected_modes=None,
            ),
        )
        if replacement in finalized:
            return finalized
        finalized[finalized.index(weakest)] = int(replacement)
        finalized = list(dict.fromkeys(finalized))


def generate_rampforge_8_palette(
    labels: LabelGrid,
    *,
    workspace: ColorWorkspace | None = None,
    progress_callback: PaletteProgressCallback = None,
    source_label: str = "Generated: RampForge-8",
) -> AdvancedPaletteComputation:
    workspace = workspace or ColorWorkspace()
    _emit_progress(progress_callback, 50, "Selecting RampForge-8 anchors...")
    dataset = build_weighted_dataset(labels, workspace)
    selected = _select_rampforge_8_anchors(dataset, workspace)
    _emit_progress(progress_callback, 65, f"Generating {len(selected)} RampForge-8 ramps...")
    computation = generate_structured_palette(
        labels,
        key_colors=selected,
        generated_shades=RAMPFORGE_8_GENERATED_SHADES,
        contrast_bias=RAMPFORGE_8_CONTRAST_BIAS,
        workspace=workspace,
        progress_callback=progress_callback,
        source_label=source_label,
        source_mode="rampforge-8",
    )
    if dataset.size > 0:
        _append_rampforge_8_neutral_ramps(computation.palette, workspace)
        _recover_rampforge_8_missed_source_colors(computation.palette, dataset, workspace)
    return computation


def _set_palette_color_label(color: PaletteColor, label: int, workspace: ColorWorkspace) -> None:
    color.label = int(label)
    color.oklab = tuple(float(value) for value in workspace.label_to_oklab(int(label)))


def _append_rampforge_8_neutral_ramps(palette: StructuredPalette, workspace: ColorWorkspace) -> None:
    neutral_specs = (
        (_RAMPFORGE_8_BLACK_RAMP_SEED, _RAMPFORGE_8_BLACK_ENDPOINT),
        (_RAMPFORGE_8_WHITE_RAMP_SEED, _RAMPFORGE_8_WHITE_ENDPOINT),
    )
    next_ramp_index = len(palette.ramps)
    for seed_label, endpoint_label in neutral_specs:
        ramp = _generate_seed_ramp(
            seed_label,
            next_ramp_index,
            RAMPFORGE_8_GENERATED_SHADES,
            RAMPFORGE_8_CONTRAST_BIAS,
            workspace,
        )
        if endpoint_label == _RAMPFORGE_8_BLACK_ENDPOINT:
            _set_palette_color_label(ramp.colors[0], endpoint_label, workspace)
        else:
            _set_palette_color_label(ramp.colors[-1], endpoint_label, workspace)
        palette.ramps.append(ramp)
        if seed_label not in palette.key_colors:
            palette.key_colors.append(seed_label)
        next_ramp_index += 1


def _rampforge_8_is_near_duplicate_to_labels(
    label: int,
    labels: list[int],
    workspace: ColorWorkspace,
    *,
    cutoff: float,
) -> bool:
    if not labels:
        return False
    existing_oklab = workspace.labels_to_oklab(np.asarray(labels, dtype=np.int64))
    candidate_oklab = workspace.label_to_oklab(int(label)).reshape(1, 3)
    distances = hyab_distance(existing_oklab, candidate_oklab).astype(np.float64, copy=False)
    return bool(np.any(distances <= cutoff))


def _rampforge_8_recovery_candidates(
    dataset: WeightedColorDataset,
    palette: StructuredPalette,
    primary_indices: np.ndarray,
    primary_distances: np.ndarray,
    workspace: ColorWorkspace,
    *,
    limit: int,
) -> list[_Rampforge8RecoveryCandidate]:
    if limit <= 0 or dataset.size == 0:
        return []
    palette_colors = palette.flattened_colors()
    palette_labels = {int(color.label) for color in palette_colors}
    source_labels = {int(label) for label in dataset.labels.tolist()}
    family_counts: dict[str, int] = {}
    for ramp in palette.ramps:
        if ramp.seed_label in {_RAMPFORGE_8_BLACK_RAMP_SEED, _RAMPFORGE_8_WHITE_RAMP_SEED}:
            continue
        mode = _rampforge_8_label_mode(int(ramp.seed_label), workspace)
        if mode is None:
            continue
        family_counts[mode] = family_counts.get(mode, 0) + 1
    protected_labels = [
        int(color.label)
        for color in palette_colors
        if color.is_seed
        or color.label in source_labels
        or palette.ramps[color.ramp_index].seed_label in {_RAMPFORGE_8_BLACK_RAMP_SEED, _RAMPFORGE_8_WHITE_RAMP_SEED}
    ]

    weighted_errors = dataset.counts * primary_distances
    max_weighted_error = float(np.max(weighted_errors)) if weighted_errors.size else 0.0
    family_residuals: dict[str, float] = {}
    for index, label in enumerate(dataset.labels.tolist()):
        mode = _rampforge_8_label_mode(int(label), workspace)
        if mode is None:
            continue
        family_residuals[mode] = family_residuals.get(mode, 0.0) + float(weighted_errors[index])
    max_family_residual = max(family_residuals.values(), default=0.0)
    candidate_by_label: dict[int, _Rampforge8RecoveryCandidate] = {}
    for index, label in enumerate(dataset.labels.tolist()):
        label = int(label)
        if label in palette_labels:
            continue
        mode = _rampforge_8_label_mode(label, workspace)
        if mode is None:
            continue
        weighted_error = float(weighted_errors[index])
        if weighted_error <= 0.0:
            continue
        metric = _rampforge_8_label_metric(label, workspace)
        family_count = float(family_counts.get(mode, 0))
        scarcity_bonus = (0.05 * max_weighted_error) / (1.0 + family_count)
        residual_bonus = 0.0
        if max_family_residual > 0.0:
            residual_ratio = family_residuals.get(mode, 0.0) / max_family_residual
            residual_bonus = 0.25 * max_weighted_error * residual_ratio / (1.0 + (0.5 * family_count))
        depth_bonus = 0.0
        if mode == PALETTE_SELECT_HUE_RED and max_weighted_error > 0.0:
            depth_ratio = float(np.clip((_RAMPFORGE_8_TARGET_LIGHTNESS - metric.lightness) / 0.22, 0.0, 1.0))
            chroma_ratio = float(np.clip(metric.chroma / 0.12, 0.0, 1.0))
            depth_bonus = 0.12 * max_weighted_error * depth_ratio * (0.6 + (0.4 * chroma_ratio)) / (1.0 + (0.4 * family_count))
        candidate_by_label[label] = _Rampforge8RecoveryCandidate(
            label=label,
            mode=mode,
            lightness=float(metric.lightness),
            weight=float(dataset.counts[index]),
            weighted_error=weighted_error,
            score=weighted_error + scarcity_bonus + residual_bonus + depth_bonus,
        )

    if not candidate_by_label:
        return []

    ordered_labels = [
        candidate.label
        for candidate in sorted(
            candidate_by_label.values(),
            key=lambda candidate: (-candidate.score, -candidate.weighted_error, -candidate.weight, candidate.label),
        )
    ]
    ordered_labels = _dedupe_detected_labels(ordered_labels, workspace, len(ordered_labels))
    similarity_cutoff = _similarity_cutoff(_RAMPFORGE_8_SIMILARITY_THRESHOLD)
    compare_labels = list(dict.fromkeys(protected_labels))
    selected: list[_Rampforge8RecoveryCandidate] = []
    selected_family_counts: dict[str, int] = {}
    for label in ordered_labels:
        candidate = candidate_by_label[int(label)]
        family_total = int(family_counts.get(candidate.mode, 0)) + selected_family_counts.get(candidate.mode, 0)
        if _rampforge_8_is_near_duplicate_to_labels(label, compare_labels, workspace, cutoff=similarity_cutoff):
            if candidate.mode != PALETTE_SELECT_HUE_RED or not _rampforge_8_allows_red_tonal_variant(
                label,
                compare_labels,
                workspace,
                family_total=family_total,
            ):
                continue
        selected.append(candidate)
        selected_family_counts[candidate.mode] = selected_family_counts.get(candidate.mode, 0) + 1
        compare_labels.append(int(label))
        if len(selected) >= limit:
            break
    return selected


def _rampforge_8_replaceable_slots(
    palette: StructuredPalette,
    dataset: WeightedColorDataset,
    primary_indices: np.ndarray,
    workspace: ColorWorkspace,
) -> list[_Rampforge8ReplaceableSlot]:
    palette_colors = palette.flattened_colors()
    if not palette_colors:
        return []
    source_labels = {int(label) for label in dataset.labels.tolist()}
    mapped_weights = np.bincount(primary_indices, weights=dataset.counts, minlength=len(palette_colors))
    seed_idx = _seed_shade_index(palette.generated_shades)
    replaceable: list[_Rampforge8ReplaceableSlot] = []
    for palette_index, color in enumerate(palette_colors):
        ramp = palette.ramps[color.ramp_index]
        ramp_mode = _rampforge_8_label_mode(int(ramp.seed_label), workspace)
        if ramp.seed_label in {_RAMPFORGE_8_BLACK_RAMP_SEED, _RAMPFORGE_8_WHITE_RAMP_SEED}:
            continue
        if color.is_seed or color.label in source_labels:
            continue
        ramp_oklab = np.asarray([candidate.oklab for candidate in ramp.colors], dtype=np.float64)
        redundancy_distance = 0.0
        if ramp_oklab.shape[0] > 1:
            other_indices = [index for index in range(ramp_oklab.shape[0]) if index != color.shade_index]
            if other_indices:
                distances = hyab_distance(
                    ramp_oklab[np.asarray(other_indices, dtype=np.int64)],
                    ramp_oklab[color.shade_index].reshape(1, 3),
                ).astype(np.float64, copy=False)
                redundancy_distance = float(np.min(distances)) if distances.size else 0.0
        replaceable.append(
            _Rampforge8ReplaceableSlot(
                palette_index=palette_index,
                ramp_index=int(color.ramp_index),
                ramp_mode=ramp_mode,
                shade_index=int(color.shade_index),
                lightness=float(color.oklab[0]),
                seed_lightness=float(ramp.seed_oklab[0]),
                mapped_weight=float(mapped_weights[palette_index]),
                redundancy_distance=redundancy_distance,
                outer_distance=abs(int(color.shade_index) - seed_idx),
            )
        )
    return replaceable


def _rampforge_8_replaceable_slot_key(slot: _Rampforge8ReplaceableSlot) -> tuple[float, float, int, int]:
    return (
        slot.mapped_weight,
        slot.redundancy_distance,
        -slot.outer_distance,
        slot.palette_index,
    )


def _rampforge_8_assignment_key(
    slot: _Rampforge8ReplaceableSlot,
    candidate: _Rampforge8RecoveryCandidate,
) -> tuple[float, float, float, float, int, int]:
    slot_direction = -1 if slot.shade_index < _seed_shade_index(RAMPFORGE_8_GENERATED_SHADES) else 1
    candidate_direction = -1 if candidate.lightness < slot.seed_lightness else 1
    family_penalty = _rampforge_8_family_penalty(slot.ramp_mode, candidate.mode)
    side_penalty = 0.0 if slot_direction == candidate_direction else 1.0
    return (
        family_penalty,
        side_penalty,
        abs(candidate.lightness - slot.lightness),
        slot.mapped_weight,
        -slot.outer_distance,
        slot.palette_index,
    )


def _recover_rampforge_8_missed_source_colors(
    palette: StructuredPalette,
    dataset: WeightedColorDataset,
    workspace: ColorWorkspace,
) -> None:
    if dataset.size == 0 or not palette.ramps:
        return
    palette_colors = palette.flattened_colors()
    if not palette_colors:
        return
    palette_oklab = np.asarray([color.oklab for color in palette_colors], dtype=np.float64)
    primary_indices, _secondary_indices, _ramp_indices = _unique_mapping_candidates(dataset.labels, palette, workspace)
    primary_distances = hyab_distance(dataset.oklab, palette_oklab[primary_indices]).astype(np.float64, copy=False)
    replaceable = _rampforge_8_replaceable_slots(palette, dataset, primary_indices, workspace)
    if not replaceable:
        return
    candidates = _rampforge_8_recovery_candidates(
        dataset,
        palette,
        primary_indices,
        primary_distances,
        workspace,
        limit=len(replaceable),
    )
    if not candidates:
        return
    available_slots = sorted(replaceable, key=_rampforge_8_replaceable_slot_key)[: len(candidates)]
    for candidate in candidates:
        if not available_slots:
            break
        best_index = min(
            range(len(available_slots)),
            key=lambda index: _rampforge_8_assignment_key(available_slots[index], candidate),
        )
        slot = available_slots.pop(best_index)
        _set_palette_color_label(palette_colors[slot.palette_index], candidate.label, workspace)


def _normalize_generated_shades(value: int) -> int:
    allowed = (2, 4, 6, 8, 10)
    if value in allowed:
        return value
    return min(allowed, key=lambda candidate: abs(candidate - value))


def _seed_shade_index(generated_shades: int) -> int:
    return generated_shades // 2


def _generate_seed_ramp(
    seed_label: int,
    ramp_index: int,
    generated_shades: int,
    contrast_bias: float,
    workspace: ColorWorkspace,
) -> PaletteRamp:
    seed_lab = workspace.label_to_oklab(seed_label)
    seed_lch = oklab_to_oklch(seed_lab.reshape(1, 3))[0]
    seed_mode = _rampforge_8_label_mode(seed_label, workspace)
    profile = _rampforge_8_ramp_profile(seed_mode)
    seed_idx = _seed_shade_index(generated_shades)
    total_colors = generated_shades + 1
    denominator = max(seed_idx, 1)
    lightness_span = 0.14 * max(0.35, contrast_bias) * profile.lightness_scale
    colors: list[PaletteColor] = []

    for shade_index in range(total_colors):
        position = (shade_index - seed_idx) / denominator
        distance = abs(position)
        lightness = float(np.clip(seed_lch[0] + position * lightness_span, 0.02, 0.98))
        chroma_scale = max(
            profile.min_chroma_scale,
            1.0 + (profile.center_chroma_boost * (1.0 - distance)) - (profile.edge_chroma_loss * distance),
        )
        hue = seed_lch[2]
        if position > 0 and profile.light_hue is not None and profile.light_strength > 0.0:
            hue = circular_lerp(hue, profile.light_hue, min(0.4, profile.light_strength * distance))
        elif position < 0 and profile.shadow_hue is not None and profile.shadow_strength > 0.0:
            hue = circular_lerp(hue, profile.shadow_hue, min(0.45, profile.shadow_strength * distance))
        candidate = np.asarray(
            [[lightness, seed_lch[1] * chroma_scale, hue]],
            dtype=np.float64,
        )
        label = workspace.oklab_to_label(oklch_to_oklab(candidate)[0])
        colors.append(
            PaletteColor(
                label=label,
                oklab=tuple(float(value) for value in workspace.label_to_oklab(label)),
                locked=False,
                is_seed=shade_index == seed_idx,
                ramp_index=ramp_index,
                shade_index=shade_index,
            )
        )

    return PaletteRamp(
        ramp_id=ramp_index,
        seed_label=seed_label,
        seed_oklab=tuple(float(value) for value in seed_lab),
        colors=colors,
    )

def generate_structured_palette(
    labels: LabelGrid,
    colors: int | None = None,
    *,
    key_colors: list[int] | None = None,
    seed_colors: list[int] | None = None,
    locked_palette_colors: list[int] | None = None,
    generated_shades: int | None = None,
    ramp_length: int | None = None,
    contrast_bias: float = 1.0,
    workspace: ColorWorkspace | None = None,
    template: StructuredPalette | None = None,
    progress_callback: PaletteProgressCallback = None,
    source_label: str = "Generated",
    source_mode: str = "advanced",
) -> AdvancedPaletteComputation:
    started = perf_counter()
    workspace = workspace or ColorWorkspace()
    dataset = build_weighted_dataset(labels, workspace)
    del colors, locked_palette_colors, template
    selected = list(key_colors or seed_colors or [])
    if not selected:
        return AdvancedPaletteComputation(
            palette=StructuredPalette(source_mode=source_mode, source_label=source_label),
            histogram_size=0,
            palette_seconds=perf_counter() - started,
        )

    selected = selected[:MAX_KEY_COLORS]
    shade_count = _normalize_generated_shades(generated_shades if generated_shades is not None else (ramp_length if ramp_length is not None else 4))
    _emit_progress(progress_callback, 65, f"Generating {len(selected)} ramps in Oklab...")
    ramps = [
        _generate_seed_ramp(seed_label, ramp_index, shade_count, contrast_bias, workspace)
        for ramp_index, seed_label in enumerate(selected)
    ]

    palette = StructuredPalette(
        ramps=ramps,
        source_mode=source_mode,
        key_colors=list(selected),
        contrast_bias=contrast_bias,
        generated_shades=shade_count,
        source_label=source_label,
    )
    return AdvancedPaletteComputation(
        palette=palette,
        histogram_size=dataset.size,
        palette_seconds=perf_counter() - started,
    )


def structured_palette_from_override(
    palette_labels: list[int],
    workspace: ColorWorkspace | None = None,
    *,
    source_label: str = "Override",
) -> StructuredPalette:
    workspace = workspace or ColorWorkspace()
    colors = [
        PaletteColor(
            label=label,
            oklab=tuple(float(value) for value in workspace.label_to_oklab(label)),
            locked=False,
            is_seed=index == 0,
            ramp_index=0,
            shade_index=index,
        )
        for index, label in enumerate(palette_labels)
    ]
    ramp = PaletteRamp(
        ramp_id=0,
        seed_label=palette_labels[0] if palette_labels else 0,
        seed_oklab=tuple(float(value) for value in workspace.label_to_oklab(palette_labels[0])) if palette_labels else (0.0, 0.0, 0.0),
        colors=colors,
    )
    return StructuredPalette(
        ramps=[ramp] if palette_labels else [],
        source_mode="override",
        key_colors=[palette_labels[0]] if palette_labels else [],
        contrast_bias=1.0,
        generated_shades=max(0, len(palette_labels) - 1),
        source_label=source_label,
    )


def _nearest_indices(points: np.ndarray, palette_oklab: np.ndarray) -> np.ndarray:
    distances = hyab_distance(points[:, None, :], palette_oklab[None, :, :])
    return np.argmin(distances, axis=1)


def _nearest_with_tree(points: np.ndarray, palette_oklab: np.ndarray) -> np.ndarray:
    tree = PaletteKDTree(palette_oklab)
    nearest = np.zeros(points.shape[0], dtype=np.int64)
    for index, point in enumerate(points):
        candidates = tree.query(point, k=min(4, len(palette_oklab)))
        candidate_points = palette_oklab[np.asarray(candidates, dtype=np.int64)]
        best = int(np.argmin(hyab_distance(candidate_points, point.reshape(1, 3))))
        nearest[index] = candidates[best]
    return nearest


def _palette_index_arrays(palette: StructuredPalette) -> tuple[np.ndarray, np.ndarray]:
    flattened = palette.flattened_colors()
    labels = np.asarray([color.label for color in flattened], dtype=np.int64)
    ramp_indices = np.asarray([color.ramp_index for color in flattened], dtype=np.int64)
    return labels, ramp_indices


def _unique_mapping_candidates(
    unique_labels: np.ndarray,
    palette: StructuredPalette,
    workspace: ColorWorkspace,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    palette_colors = palette.flattened_colors()
    palette_oklab = np.asarray([color.oklab for color in palette_colors], dtype=np.float64)
    unique_oklab = workspace.labels_to_oklab(unique_labels)
    if palette_oklab.shape[0] > 24:
        primary_indices = _nearest_with_tree(unique_oklab, palette_oklab)
    else:
        primary_indices = _nearest_indices(unique_oklab, palette_oklab)

    ramp_indices = np.asarray([palette_colors[index].ramp_index for index in primary_indices], dtype=np.int64)
    secondary_indices = primary_indices.copy()
    second_weights = np.zeros(primary_indices.shape[0], dtype=np.float64)

    by_ramp: dict[int, np.ndarray] = {}
    for ramp_index in sorted({color.ramp_index for color in palette_colors}):
        by_ramp[ramp_index] = np.asarray(
            [index for index, color in enumerate(palette_colors) if color.ramp_index == ramp_index],
            dtype=np.int64,
        )

    for index, point in enumerate(unique_oklab):
        ramp_palette_indices = by_ramp[int(ramp_indices[index])]
        ramp_points = palette_oklab[ramp_palette_indices]
        distances = hyab_distance(ramp_points, point.reshape(1, 3))
        order = np.argsort(distances)
        primary = ramp_palette_indices[int(order[0])]
        primary_indices[index] = primary
        if order.size > 1:
            secondary = ramp_palette_indices[int(order[1])]
            secondary_indices[index] = secondary
            first_distance = float(distances[int(order[0])])
            second_distance = float(distances[int(order[1])])
            second_weights[index] = first_distance / max(first_distance + second_distance, 1e-9)
        else:
            secondary_indices[index] = primary
            second_weights[index] = 0.0
    return primary_indices, secondary_indices, ramp_indices


def _matrix_threshold(mode: str, y: int, x: int) -> float:
    if mode == "ordered":
        return float((_BAYER_4[y % 4, x % 4] + 0.5) / 16.0)
    return float((_BLUE_NOISE_8[y % 8, x % 8] + 0.5) / 64.0)


def map_palette_to_labels(
    labels: LabelGrid,
    palette: StructuredPalette,
    *,
    workspace: ColorWorkspace | None = None,
    dither_mode: str = "none",
    progress_callback: PaletteProgressCallback = None,
) -> PaletteMappingResult:
    workspace = workspace or ColorWorkspace()
    height = len(labels)
    width = len(labels[0]) if height else 0
    if height == 0 or width == 0 or not palette.ramps:
        return PaletteMappingResult(labels=[row[:] for row in labels], palette_indices=[], ramp_index_grid=None)

    flattened_labels, ramp_lookup = _palette_index_arrays(palette)
    flat = np.asarray([value for row in labels for value in row], dtype=np.int64)
    unique, inverse = np.unique(flat, return_inverse=True)
    primary_indices, secondary_indices, ramp_indices = _unique_mapping_candidates(unique, palette, workspace)

    _emit_progress(progress_callback, 90, "Finalizing output...")
    if dither_mode == "none":
        mapped_indices = primary_indices[inverse].reshape(height, width)
    elif dither_mode in {"ordered", "blue-noise"}:
        second_weight_lookup = np.zeros(unique.shape[0], dtype=np.float64)
        unique_oklab = workspace.labels_to_oklab(unique)
        palette_oklab = workspace.labels_to_oklab(flattened_labels)
        for index, point in enumerate(unique_oklab):
            primary = int(primary_indices[index])
            secondary = int(secondary_indices[index])
            if primary == secondary:
                second_weight_lookup[index] = 0.0
                continue
            distances = hyab_distance(
                palette_oklab[np.asarray([primary, secondary], dtype=np.int64)],
                point.reshape(1, 3),
            )
            second_weight_lookup[index] = float(distances[0] / max(distances[0] + distances[1], 1e-9))

        unique_index_lookup = {int(label): idx for idx, label in enumerate(unique)}
        mapped_indices = np.zeros((height, width), dtype=np.int64)
        for y, row in enumerate(labels):
            for x, label in enumerate(row):
                lookup_index = unique_index_lookup[int(label)]
                threshold = _matrix_threshold(dither_mode, y, x)
                if threshold < second_weight_lookup[lookup_index]:
                    mapped_indices[y, x] = secondary_indices[lookup_index]
                else:
                    mapped_indices[y, x] = primary_indices[lookup_index]
    else:
        raise ValueError(f"Unsupported dither mode: {dither_mode}")

    mapped_labels = flattened_labels[mapped_indices]
    ramp_index_grid = ramp_lookup[mapped_indices]
    return PaletteMappingResult(
        labels=[[int(value) for value in row] for row in mapped_labels.tolist()],
        palette_indices=[[int(value) for value in row] for row in mapped_indices.tolist()],
        ramp_index_grid=[[int(value) for value in row] for row in ramp_index_grid.tolist()],
    )

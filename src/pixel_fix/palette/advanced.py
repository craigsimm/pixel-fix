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
    seed_idx = _seed_shade_index(generated_shades)
    total_colors = generated_shades + 1
    denominator = max(seed_idx, 1)
    lightness_span = 0.14 * max(0.35, contrast_bias)
    colors: list[PaletteColor] = []

    for shade_index in range(total_colors):
        position = (shade_index - seed_idx) / denominator
        distance = abs(position)
        lightness = float(np.clip(seed_lch[0] + position * lightness_span, 0.02, 0.98))
        chroma_scale = max(0.06, 1.0 + 0.18 * (1.0 - distance) - 0.30 * distance)
        hue = seed_lch[2]
        if position > 0:
            hue = circular_lerp(hue, _WARM_HUE, min(0.4, 0.25 * distance))
        elif position < 0:
            hue = circular_lerp(hue, _COOL_HUE, min(0.45, 0.30 * distance))
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
) -> AdvancedPaletteComputation:
    started = perf_counter()
    workspace = workspace or ColorWorkspace()
    dataset = build_weighted_dataset(labels, workspace)
    del colors, locked_palette_colors, template
    selected = list(key_colors or seed_colors or [])
    if not selected:
        return AdvancedPaletteComputation(
            palette=StructuredPalette(source_mode="advanced", source_label=source_label),
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
        source_mode="advanced",
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

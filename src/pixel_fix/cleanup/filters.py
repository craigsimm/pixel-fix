from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

from pixel_fix.palette.color_modes import extract_unique_colors
from pixel_fix.palette.workspace import ColorWorkspace, hyab_distance
from pixel_fix.types import LabelGrid

_ORPHAN_SIMILARITY_THRESHOLD = 0.08
_ANTI_ALIAS_EDGE_CONTRAST_THRESHOLD = 0.18
_MIN_GAP_CLAIM_NEIGHBORS = 3


@dataclass(frozen=True)
class AntiAliasCleanupResult:
    image: Image.Image
    replaced_pixels: int


@dataclass(frozen=True)
class OrphanCleanupResult:
    labels: LabelGrid
    orphan_pixels_replaced: int
    gap_pixels_filled: int


def remove_anti_aliased_edges(image: Image.Image, alpha_cutoff: int, workspace: ColorWorkspace | None = None) -> AntiAliasCleanupResult:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    if rgba.size == 0:
        return AntiAliasCleanupResult(image=image.convert("RGBA").copy(), replaced_pixels=0)

    workspace = workspace or ColorWorkspace()
    height, width = rgba.shape[:2]
    output = rgba.copy()
    replaced_pixels = 0

    solid_mask = rgba[..., 3] >= alpha_cutoff
    transparent_mask = rgba[..., 3] == 0
    packed = _pack_rgb(rgba[..., :3])
    unique = np.unique(packed.reshape(-1))
    oklab_lookup = _oklab_lookup(unique, workspace)

    for y in range(height):
        for x in range(width):
            alpha = int(rgba[y, x, 3])
            if alpha <= 0 or alpha >= alpha_cutoff:
                continue

            solid_neighbors: list[int] = []
            transparent_neighbors = 0
            for ny, nx in _neighbors8(y, x, height, width):
                if solid_mask[ny, nx]:
                    solid_neighbors.append(int(packed[ny, nx]))
                elif transparent_mask[ny, nx]:
                    transparent_neighbors += 1

            if len(solid_neighbors) < 2:
                continue

            distinct_neighbors = list(dict.fromkeys(solid_neighbors))
            high_contrast_edge = (
                len(distinct_neighbors) >= 2
                and _max_pairwise_distance(distinct_neighbors, oklab_lookup) >= _ANTI_ALIAS_EDGE_CONTRAST_THRESHOLD
            )
            solid_transparent_edge = len(solid_neighbors) >= 2 and transparent_neighbors >= 2
            if not high_contrast_edge and not solid_transparent_edge:
                continue

            current_label = int(packed[y, x])
            replacement = min(
                distinct_neighbors,
                key=lambda label: (_distance_between(current_label, label, oklab_lookup), label),
            )
            if replacement == current_label and alpha == 255:
                continue
            output[y, x, 0] = (replacement >> 16) & 0xFF
            output[y, x, 1] = (replacement >> 8) & 0xFF
            output[y, x, 2] = replacement & 0xFF
            output[y, x, 3] = 255
            replaced_pixels += 1

    return AntiAliasCleanupResult(
        image=Image.fromarray(output, mode="RGBA"),
        replaced_pixels=replaced_pixels,
    )


def clean_orphan_pixels(
    labels: LabelGrid,
    min_similar_neighbors: int,
    *,
    fill_gaps: bool,
    workspace: ColorWorkspace | None = None,
) -> OrphanCleanupResult:
    copied = [row[:] for row in labels]
    height = len(copied)
    width = len(copied[0]) if height else 0
    if width == 0 or height == 0:
        return OrphanCleanupResult(labels=copied, orphan_pixels_replaced=0, gap_pixels_filled=0)

    workspace = workspace or ColorWorkspace()
    orphan_pixels_replaced = 0

    if min_similar_neighbors > 0:
        source = [row[:] for row in copied]
        label_lookup = _oklab_lookup(extract_unique_colors(source), workspace)
        for y in range(height):
            for x in range(width):
                current = source[y][x]
                neighbors = _neighbors8(y, x, height, width)
                if not neighbors:
                    continue
                similar_neighbors = sum(
                    1
                    for ny, nx in neighbors
                    if _distance_between(current, source[ny][nx], label_lookup) <= _ORPHAN_SIMILARITY_THRESHOLD
                )
                if similar_neighbors >= min_similar_neighbors:
                    continue

                first_seen: dict[int, int] = {}
                counts: dict[int, int] = {}
                for index, (ny, nx) in enumerate(neighbors):
                    label = source[ny][nx]
                    counts[label] = counts.get(label, 0) + 1
                    first_seen.setdefault(label, index)

                replacement = min(
                    counts,
                    key=lambda label: (
                        -counts[label],
                        _distance_between(current, label, label_lookup),
                        first_seen[label],
                    ),
                )
                if replacement != current:
                    copied[y][x] = replacement
                    orphan_pixels_replaced += 1

    gap_pixels_filled = 0
    if fill_gaps:
        source = [row[:] for row in copied]
        label_order = extract_unique_colors(source)
        label_lookup = _oklab_lookup(label_order, workspace)
        claimants: list[list[list[int]]] = [[[] for _ in range(width)] for _ in range(height)]

        for label in label_order:
            mask = np.asarray([[value == label for value in row] for row in source], dtype=bool)
            closed = _binary_close_3x3(mask)
            for y in range(height):
                for x in range(width):
                    if not closed[y, x] or source[y][x] == label:
                        continue
                    support = _local_neighbor_count(source, y, x, label)
                    if support >= _MIN_GAP_CLAIM_NEIGHBORS:
                        claimants[y][x].append(label)

        for y in range(height):
            for x in range(width):
                labels_here = claimants[y][x]
                if not labels_here:
                    continue
                original = source[y][x]
                if _local_neighbor_count(source, y, x, original) > 0:
                    continue
                replacement = min(
                    labels_here,
                    key=lambda label: (
                        -_local_neighbor_count(source, y, x, label),
                        _distance_between(original, label, label_lookup),
                        labels_here.index(label),
                    ),
                )
                if replacement != original:
                    copied[y][x] = replacement
                    gap_pixels_filled += 1

    return OrphanCleanupResult(
        labels=copied,
        orphan_pixels_replaced=orphan_pixels_replaced,
        gap_pixels_filled=gap_pixels_filled,
    )


def _neighbors8(y: int, x: int, height: int, width: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            ny = y + dy
            nx = x + dx
            if 0 <= ny < height and 0 <= nx < width:
                out.append((ny, nx))
    return out


def _pack_rgb(rgb: np.ndarray) -> np.ndarray:
    data = rgb.astype(np.int64, copy=False)
    return (data[..., 0] << 16) | (data[..., 1] << 8) | data[..., 2]


def _oklab_lookup(labels: list[int] | np.ndarray, workspace: ColorWorkspace) -> dict[int, np.ndarray]:
    label_array = np.asarray(labels, dtype=np.int64)
    if label_array.size == 0:
        return {}
    oklab = workspace.labels_to_oklab(label_array)
    return {int(label): np.asarray(oklab[index], dtype=np.float64) for index, label in enumerate(label_array)}


def _distance_between(left: int, right: int, oklab_lookup: dict[int, np.ndarray]) -> float:
    return float(
        hyab_distance(
            oklab_lookup[left].reshape(1, 3),
            oklab_lookup[right].reshape(1, 3),
        )[0]
    )


def _max_pairwise_distance(labels: list[int], oklab_lookup: dict[int, np.ndarray]) -> float:
    if len(labels) < 2:
        return 0.0
    points = np.asarray([oklab_lookup[label] for label in labels], dtype=np.float64)
    distances = hyab_distance(points[:, None, :], points[None, :, :])
    return float(np.max(distances))


def _binary_close_3x3(mask: np.ndarray) -> np.ndarray:
    return _erode3x3(_dilate3x3(mask))


def _dilate3x3(mask: np.ndarray) -> np.ndarray:
    height, width = mask.shape
    padded = np.pad(mask, 1, mode="edge")
    output = np.zeros_like(mask, dtype=bool)
    for dy in range(3):
        for dx in range(3):
            output |= padded[dy : dy + height, dx : dx + width]
    return output


def _erode3x3(mask: np.ndarray) -> np.ndarray:
    height, width = mask.shape
    padded = np.pad(mask, 1, mode="edge")
    output = np.ones_like(mask, dtype=bool)
    for dy in range(3):
        for dx in range(3):
            output &= padded[dy : dy + height, dx : dx + width]
    return output


def _local_neighbor_count(labels: LabelGrid, y: int, x: int, target_label: int) -> int:
    height = len(labels)
    width = len(labels[0]) if height else 0
    return sum(1 for ny, nx in _neighbors8(y, x, height, width) if labels[ny][nx] == target_label)

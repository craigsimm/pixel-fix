from __future__ import annotations

from dataclasses import replace
from dataclasses import dataclass
from functools import lru_cache
from time import perf_counter

import numpy as np
from PIL import Image, ImageDraw

from pixel_fix.palette.model import StructuredPalette
from pixel_fix.palette.color_modes import extract_unique_colors
from pixel_fix.palette.workspace import ColorWorkspace, oklab_to_oklch, oklch_to_oklab
from pixel_fix.pipeline import (
    PipelineConfig,
    PipelinePreparedResult,
    PipelineProgressCallback,
    PixelFixPipeline,
)
from pixel_fix.types import LabelGrid

RGB = tuple[int, int, int]
RGBGrid = list[list[RGB]]
BRUSH_SHAPE_SQUARE = "square"
BRUSH_SHAPE_ROUND = "round"
BRUSH_WIDTH_DEFAULT = 1
BRUSH_WIDTH_MIN = 1
BRUSH_WIDTH_MAX = 64
OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK = "dark"
OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_BRIGHT = "bright"
OUTLINE_REMOVE_BRIGHTNESS_THRESHOLD_DEFAULT = 40


def rgb_to_labels(grid: RGBGrid) -> LabelGrid:
    return [[(r << 16) | (g << 8) | b for (r, g, b) in row] for row in grid]


def labels_to_rgb(grid: LabelGrid) -> RGBGrid:
    return [[((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF) for value in row] for row in grid]


@dataclass(frozen=True)
class ProcessStats:
    stage: str
    pixel_width: int
    resize_method: str
    input_size: tuple[int, int]
    output_size: tuple[int, int]
    initial_color_count: int
    color_count: int
    elapsed_seconds: float
    seed_count: int = 0
    ramp_count: int = 0
    palette_strategy: str = "advanced"
    effective_palette_size: int = 0
    histogram_size: int = 0
    palette_generation_seconds: float = 0.0
    mapping_seconds: float = 0.0


@dataclass(frozen=True)
class ProcessResult:
    grid: RGBGrid
    width: int
    height: int
    stats: ProcessStats
    prepared_input: PipelinePreparedResult
    display_palette_labels: tuple[int, ...] = ()
    structured_palette: StructuredPalette | None = None
    alpha_mask: tuple[tuple[bool, ...], ...] | None = None


def apply_transparency_fill(result: ProcessResult, x: int, y: int) -> tuple[ProcessResult, int]:
    if result.width <= 0 or result.height <= 0:
        return result, 0
    if x < 0 or y < 0 or x >= result.width or y >= result.height:
        return result, 0
    current_mask = result.alpha_mask
    if current_mask is not None and not current_mask[y][x]:
        return result, 0
    target = result.grid[y][x]
    next_mask = [list(row) for row in current_mask] if current_mask is not None else [[True] * result.width for _ in range(result.height)]
    pending = [(x, y)]
    changed = 0
    while pending:
        px, py = pending.pop()
        if px < 0 or py < 0 or px >= result.width or py >= result.height:
            continue
        if not next_mask[py][px]:
            continue
        if result.grid[py][px] != target:
            continue
        next_mask[py][px] = False
        changed += 1
        pending.append((px - 1, py))
        pending.append((px + 1, py))
        pending.append((px, py - 1))
        pending.append((px, py + 1))
    if changed == 0:
        return result, 0
    return replace(result, alpha_mask=tuple(tuple(row) for row in next_mask)), changed


def apply_bucket_fill(result: ProcessResult, x: int, y: int, label: int) -> tuple[ProcessResult, int]:
    if result.width <= 0 or result.height <= 0:
        return result, 0
    if x < 0 or y < 0 or x >= result.width or y >= result.height:
        return result, 0
    current_mask = result.alpha_mask
    seed_visible = True if current_mask is None else bool(current_mask[y][x])
    target_rgb = _label_to_rgb(label)
    seed_rgb = result.grid[y][x]
    pending = [(x, y)]
    visited: set[tuple[int, int]] = set()
    changed_points: set[tuple[int, int]] = set()
    next_grid = [list(row) for row in result.grid]
    next_mask = [list(row) for row in current_mask] if current_mask is not None else None
    while pending:
        point_x, point_y = pending.pop()
        if point_x < 0 or point_y < 0 or point_x >= result.width or point_y >= result.height:
            continue
        point = (point_x, point_y)
        if point in visited:
            continue
        visited.add(point)
        point_visible = True if current_mask is None else bool(current_mask[point_y][point_x])
        if point_visible != seed_visible:
            continue
        if seed_visible and result.grid[point_y][point_x] != seed_rgb:
            continue
        current_rgb = result.grid[point_y][point_x]
        if (not point_visible) or current_rgb != target_rgb:
            next_grid[point_y][point_x] = target_rgb
            changed_points.add(point)
        if next_mask is not None and not point_visible:
            next_mask[point_y][point_x] = True
            changed_points.add(point)
        pending.append((point_x - 1, point_y))
        pending.append((point_x + 1, point_y))
        pending.append((point_x, point_y - 1))
        pending.append((point_x, point_y + 1))
    if not changed_points:
        return result, 0
    if next_mask is not None:
        return replace(result, grid=next_grid, alpha_mask=_normalize_alpha_mask(next_mask)), len(changed_points)
    return replace(result, grid=next_grid), len(changed_points)


def apply_rectangle_operation(
    result: ProcessResult,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    outline_label: int,
    *,
    fill_label: int | None,
    width: int = BRUSH_WIDTH_DEFAULT,
) -> tuple[ProcessResult, int]:
    return _apply_shape_operation(
        result,
        "rectangle",
        x0,
        y0,
        x1,
        y1,
        outline_label=outline_label,
        fill_label=fill_label,
        width=width,
    )


def apply_ellipse_operation(
    result: ProcessResult,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    outline_label: int,
    *,
    fill_label: int | None,
    width: int = BRUSH_WIDTH_DEFAULT,
) -> tuple[ProcessResult, int]:
    return _apply_shape_operation(
        result,
        "ellipse",
        x0,
        y0,
        x1,
        y1,
        outline_label=outline_label,
        fill_label=fill_label,
        width=width,
    )


def brush_footprint(width: int = BRUSH_WIDTH_DEFAULT, shape: str = BRUSH_SHAPE_SQUARE) -> set[tuple[int, int]]:
    return set(_brush_footprint_offsets(width, shape))


@lru_cache(maxsize=None)
def _brush_footprint_offsets(width: int, shape: str) -> tuple[tuple[int, int], ...]:
    normalized_width = _coerce_brush_width(width)
    normalized_shape = _coerce_brush_shape(shape)
    if normalized_width == 1:
        return ((0, 0),)
    start = -(normalized_width // 2)
    offsets = range(start, start + normalized_width)
    if normalized_shape == BRUSH_SHAPE_SQUARE:
        return tuple((offset_x, offset_y) for offset_y in offsets for offset_x in offsets)
    radius = max(1.0, (normalized_width - 1) / 2.0)
    radius_squared = (radius * radius) + 0.25
    return tuple(
        (offset_x, offset_y)
        for offset_y in offsets
        for offset_x in offsets
        if (offset_x * offset_x) + (offset_y * offset_y) <= radius_squared
    )


def apply_pencil_operation(
    result: ProcessResult,
    x: int,
    y: int,
    label: int,
    *,
    width: int = BRUSH_WIDTH_DEFAULT,
    shape: str = BRUSH_SHAPE_SQUARE,
) -> tuple[ProcessResult, int]:
    return apply_pencil_operations(result, ((x, y),), label=label, width=width, shape=shape)


def apply_pencil_operations(
    result: ProcessResult,
    points: tuple[tuple[int, int], ...] | list[tuple[int, int]],
    *,
    label: int,
    width: int = BRUSH_WIDTH_DEFAULT,
    shape: str = BRUSH_SHAPE_SQUARE,
) -> tuple[ProcessResult, int]:
    return _apply_brush_operations(result, points, label=label, erase=False, width=width, shape=shape)


def apply_eraser_operation(
    result: ProcessResult,
    x: int,
    y: int,
    *,
    width: int = BRUSH_WIDTH_DEFAULT,
    shape: str = BRUSH_SHAPE_SQUARE,
) -> tuple[ProcessResult, int]:
    return apply_eraser_operations(result, ((x, y),), width=width, shape=shape)


def apply_eraser_operations(
    result: ProcessResult,
    points: tuple[tuple[int, int], ...] | list[tuple[int, int]],
    *,
    width: int = BRUSH_WIDTH_DEFAULT,
    shape: str = BRUSH_SHAPE_SQUARE,
) -> tuple[ProcessResult, int]:
    return _apply_brush_operations(result, points, label=None, erase=True, width=width, shape=shape)


def add_exterior_outline(
    result: ProcessResult,
    outline_label: int,
    *,
    transparent_labels: set[int] | None = None,
    pixel_perfect: bool = True,
    adaptive: bool = False,
    adaptive_darken_percent: int = 60,
    workspace: ColorWorkspace | None = None,
) -> tuple[ProcessResult, int, tuple[int, ...]]:
    if result.width <= 0 or result.height <= 0:
        return result, 0, ()
    visible = _effective_visible_mask(result, transparent_labels)
    exterior = _exterior_transparent_mask(visible)
    outline_mask = _raw_exterior_outline_mask(visible, exterior)
    if pixel_perfect:
        outline_mask = _pixel_perfect_mask(outline_mask)
    next_grid = [list(row) for row in result.grid]
    next_mask = [row[:] for row in visible]
    changed = 0
    generated_labels: set[int] = set()
    outline_rgb = _label_to_rgb(outline_label)
    darken_percent = _coerce_outline_darken_percent(adaptive_darken_percent)
    color_workspace = workspace or ColorWorkspace()
    for y in range(result.height):
        for x in range(result.width):
            if not outline_mask[y][x]:
                continue
            if adaptive:
                label = _adaptive_outline_label(result, visible, x, y, darken_percent=darken_percent, workspace=color_workspace)
                next_grid[y][x] = _label_to_rgb(label)
                generated_labels.add(label)
            else:
                next_grid[y][x] = outline_rgb
                generated_labels.add(outline_label)
            next_mask[y][x] = True
            changed += 1
    if changed == 0:
        return result, 0, ()
    return replace(result, grid=next_grid, alpha_mask=_normalize_alpha_mask(next_mask)), changed, tuple(sorted(generated_labels))


def _adaptive_outline_label(
    result: ProcessResult,
    visible: list[list[bool]],
    x: int,
    y: int,
    *,
    darken_percent: int,
    workspace: ColorWorkspace,
) -> int:
    labels = _sample_interior_neighbor_labels(result, visible, x, y)
    dominant = _select_dominant_color_label(labels)
    return _darken_label(dominant, darken_percent=darken_percent, workspace=workspace)


def remove_exterior_outline(
    result: ProcessResult,
    *,
    transparent_labels: set[int] | None = None,
    pixel_perfect: bool = True,
    brightness_threshold_enabled: bool = False,
    brightness_threshold_percent: int = OUTLINE_REMOVE_BRIGHTNESS_THRESHOLD_DEFAULT,
    brightness_threshold_direction: str = OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK,
    workspace: ColorWorkspace | None = None,
) -> tuple[ProcessResult, int]:
    if result.width <= 0 or result.height <= 0:
        return result, 0
    visible = _effective_visible_mask(result, transparent_labels)
    exterior = _exterior_transparent_mask(visible)
    remove_mask = _raw_exterior_edge_mask(visible, exterior)
    if brightness_threshold_enabled:
        remove_mask = _filter_remove_mask_by_brightness(
            result,
            remove_mask,
            threshold_percent=brightness_threshold_percent,
            direction=brightness_threshold_direction,
            workspace=workspace or ColorWorkspace(),
        )
    if pixel_perfect:
        remove_mask = _pixel_perfect_mask(remove_mask)
    next_mask = [row[:] for row in visible]
    changed = 0
    for y in range(result.height):
        for x in range(result.width):
            if not remove_mask[y][x]:
                continue
            next_mask[y][x] = False
            changed += 1
    if changed == 0:
        return result, 0
    return replace(result, alpha_mask=_normalize_alpha_mask(next_mask)), changed


def _effective_visible_mask(result: ProcessResult, transparent_labels: set[int] | None = None) -> list[list[bool]]:
    blocked = transparent_labels or set()
    alpha_mask = result.alpha_mask
    visible: list[list[bool]] = []
    for y, row in enumerate(result.grid):
        visible_row: list[bool] = []
        for x, (red, green, blue) in enumerate(row):
            label = (red << 16) | (green << 8) | blue
            alpha_visible = True if alpha_mask is None else bool(alpha_mask[y][x])
            visible_row.append(alpha_visible and label not in blocked)
        visible.append(visible_row)
    return visible


def _sample_interior_neighbor_labels(result: ProcessResult, visible: list[list[bool]], x: int, y: int) -> list[int]:
    neighbors_8 = _collect_neighbor_labels(result, visible, x, y, include_diagonals=True)
    if neighbors_8:
        return neighbors_8
    neighbors_4 = _collect_neighbor_labels(result, visible, x, y, include_diagonals=False)
    if neighbors_4:
        return neighbors_4
    return _collect_nearest_visible_labels(result, visible, x, y)


def _collect_neighbor_labels(
    result: ProcessResult,
    visible: list[list[bool]],
    x: int,
    y: int,
    *,
    include_diagonals: bool,
) -> list[int]:
    labels: list[int] = []
    for neighbor_y in range(max(0, y - 1), min(result.height, y + 2)):
        for neighbor_x in range(max(0, x - 1), min(result.width, x + 2)):
            if neighbor_x == x and neighbor_y == y:
                continue
            if not include_diagonals and neighbor_x != x and neighbor_y != y:
                continue
            if not visible[neighbor_y][neighbor_x]:
                continue
            red, green, blue = result.grid[neighbor_y][neighbor_x]
            labels.append((red << 16) | (green << 8) | blue)
    return labels


def _collect_nearest_visible_labels(result: ProcessResult, visible: list[list[bool]], x: int, y: int) -> list[int]:
    max_radius = max(result.width, result.height)
    for radius in range(1, max_radius + 1):
        labels: list[int] = []
        min_x = max(0, x - radius)
        max_x = min(result.width - 1, x + radius)
        min_y = max(0, y - radius)
        max_y = min(result.height - 1, y + radius)
        for neighbor_y in range(min_y, max_y + 1):
            for neighbor_x in range(min_x, max_x + 1):
                if max(abs(neighbor_x - x), abs(neighbor_y - y)) != radius:
                    continue
                if not visible[neighbor_y][neighbor_x]:
                    continue
                red, green, blue = result.grid[neighbor_y][neighbor_x]
                labels.append((red << 16) | (green << 8) | blue)
        if labels:
            return labels
    return [0]


def _select_dominant_color_label(labels: list[int]) -> int:
    if not labels:
        return 0
    frequencies: dict[int, int] = {}
    for label in labels:
        frequencies[label] = frequencies.get(label, 0) + 1
    max_count = max(frequencies.values())
    candidates = [label for label, count in frequencies.items() if count == max_count]
    return min(candidates)


def _darken_label(label: int, *, darken_percent: int, workspace: ColorWorkspace) -> int:
    percent = _coerce_outline_darken_percent(darken_percent)
    if percent <= 0:
        return int(label)
    if percent >= 100:
        return 0
    oklab = workspace.label_to_oklab(int(label))
    oklch = oklab_to_oklch(np.asarray([oklab], dtype=np.float64))
    oklch[0, 0] = np.clip(oklch[0, 0] * (1.0 - (percent / 100.0)), 0.0, 1.0)
    darkened = oklch_to_oklab(oklch)[0]
    return workspace.oklab_to_label(darkened)


def _coerce_outline_darken_percent(value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 60
    return max(0, min(100, parsed))


def _coerce_brush_width(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = BRUSH_WIDTH_DEFAULT
    return max(BRUSH_WIDTH_MIN, min(BRUSH_WIDTH_MAX, parsed))


def _coerce_brush_shape(value: object) -> str:
    normalized = str(value or BRUSH_SHAPE_SQUARE).strip().lower()
    if normalized == BRUSH_SHAPE_ROUND:
        return BRUSH_SHAPE_ROUND
    return BRUSH_SHAPE_SQUARE


def _coerce_outline_remove_brightness_threshold_percent(value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = OUTLINE_REMOVE_BRIGHTNESS_THRESHOLD_DEFAULT
    return max(0, min(100, parsed))


def _coerce_outline_remove_brightness_direction(value: object) -> str:
    normalized = str(value or OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK).strip().lower()
    if normalized == OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_BRIGHT:
        return OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_BRIGHT
    return OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK


def _filter_remove_mask_by_brightness(
    result: ProcessResult,
    remove_mask: list[list[bool]],
    *,
    threshold_percent: int,
    direction: str,
    workspace: ColorWorkspace,
) -> list[list[bool]]:
    filtered = [row[:] for row in remove_mask]
    threshold_lightness = _coerce_outline_remove_brightness_threshold_percent(threshold_percent) / 100.0
    normalized_direction = _coerce_outline_remove_brightness_direction(direction)
    for y in range(result.height):
        for x in range(result.width):
            if not remove_mask[y][x]:
                continue
            red, green, blue = result.grid[y][x]
            label = (red << 16) | (green << 8) | blue
            filtered[y][x] = _matches_outline_remove_brightness_threshold(
                label,
                threshold_lightness=threshold_lightness,
                direction=normalized_direction,
                workspace=workspace,
            )
    return filtered


def _matches_outline_remove_brightness_threshold(
    label: int,
    *,
    threshold_lightness: float,
    direction: str,
    workspace: ColorWorkspace,
) -> bool:
    lightness = float(workspace.label_to_oklab(int(label))[0])
    if direction == OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_BRIGHT:
        return lightness >= threshold_lightness
    return lightness <= threshold_lightness


def _label_to_rgb(label: int) -> RGB:
    return ((label >> 16) & 0xFF, (label >> 8) & 0xFF, label & 0xFF)


def _apply_shape_operation(
    result: ProcessResult,
    shape: str,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    *,
    outline_label: int,
    fill_label: int | None,
    width: int,
) -> tuple[ProcessResult, int]:
    if result.width <= 0 or result.height <= 0:
        return result, 0
    outline_points, fill_points = _rasterize_shape_points(
        shape,
        result.width,
        result.height,
        x0,
        y0,
        x1,
        y1,
        width=width,
    )
    if not outline_points and not fill_points:
        return result, 0
    current_mask = result.alpha_mask
    next_grid = [list(row) for row in result.grid]
    needs_mask_copy = current_mask is not None or fill_label is None
    next_mask = (
        [list(row) for row in current_mask]
        if current_mask is not None
        else ([[True] * result.width for _ in range(result.height)] if needs_mask_copy else None)
    )
    changed_points: set[tuple[int, int]] = set()
    if fill_points:
        _apply_shape_points(
            result,
            next_grid,
            next_mask,
            changed_points,
            fill_points,
            label=fill_label,
        )
    if outline_points:
        _apply_shape_points(
            result,
            next_grid,
            next_mask,
            changed_points,
            outline_points,
            label=outline_label,
        )
    if not changed_points:
        return result, 0
    if next_mask is not None:
        return replace(result, grid=next_grid, alpha_mask=_normalize_alpha_mask(next_mask)), len(changed_points)
    return replace(result, grid=next_grid), len(changed_points)


def _apply_shape_points(
    result: ProcessResult,
    next_grid: RGBGrid,
    next_mask: list[list[bool]] | None,
    changed_points: set[tuple[int, int]],
    points: set[tuple[int, int]],
    *,
    label: int | None,
) -> None:
    current_mask = result.alpha_mask
    target_rgb = _label_to_rgb(label) if label is not None else None
    for point_x, point_y in points:
        current_visible = True if current_mask is None else bool(current_mask[point_y][point_x])
        if label is None:
            if not current_visible:
                continue
            assert next_mask is not None
            next_mask[point_y][point_x] = False
            changed_points.add((point_x, point_y))
            continue
        assert target_rgb is not None
        if current_visible and result.grid[point_y][point_x] == target_rgb:
            continue
        next_grid[point_y][point_x] = target_rgb
        if next_mask is not None:
            next_mask[point_y][point_x] = True
        changed_points.add((point_x, point_y))


def _rasterize_shape_points(
    shape: str,
    image_width: int,
    image_height: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    *,
    width: int,
) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    if image_width <= 0 or image_height <= 0:
        return set(), set()
    left, right = sorted((int(x0), int(x1)))
    top, bottom = sorted((int(y0), int(y1)))
    stroke_width = _coerce_brush_width(width)
    fill_mask = Image.new("1", (image_width, image_height), 0)
    outline_mask = Image.new("1", (image_width, image_height), 0)
    fill_draw = ImageDraw.Draw(fill_mask)
    outline_draw = ImageDraw.Draw(outline_mask)
    bounds = (left, top, right, bottom)
    if shape == "ellipse":
        fill_draw.ellipse(bounds, fill=1)
        outline_draw.ellipse(bounds, outline=1, width=stroke_width)
    else:
        fill_draw.rectangle(bounds, fill=1)
        outline_draw.rectangle(bounds, outline=1, width=stroke_width)
    outline_points = _mask_points(outline_mask)
    fill_points = _mask_points(fill_mask) - outline_points
    return outline_points, fill_points


def _mask_points(mask: Image.Image) -> set[tuple[int, int]]:
    width, height = mask.size
    points: set[tuple[int, int]] = set()
    pixels = mask.load()
    for y in range(height):
        for x in range(width):
            if pixels[x, y]:
                points.add((x, y))
    return points


def _brush_points_in_bounds(
    result: ProcessResult,
    x: int,
    y: int,
    *,
    width: int,
    shape: str,
) -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    for offset_x, offset_y in _brush_footprint_offsets(_coerce_brush_width(width), _coerce_brush_shape(shape)):
        point_x = x + offset_x
        point_y = y + offset_y
        if point_x < 0 or point_y < 0 or point_x >= result.width or point_y >= result.height:
            continue
        points.append((point_x, point_y))
    return points


def _apply_brush_operations(
    result: ProcessResult,
    points: tuple[tuple[int, int], ...] | list[tuple[int, int]],
    *,
    label: int | None,
    erase: bool,
    width: int,
    shape: str,
) -> tuple[ProcessResult, int]:
    if result.width <= 0 or result.height <= 0:
        return result, 0
    if not points:
        return result, 0
    current_mask = result.alpha_mask
    target_rgb = _label_to_rgb(label) if label is not None else None
    changed_points: set[tuple[int, int]] = set()
    needs_mask_copy = erase or current_mask is not None
    for center_x, center_y in points:
        if center_x < 0 or center_y < 0 or center_x >= result.width or center_y >= result.height:
            continue
        for point_x, point_y in _brush_points_in_bounds(result, center_x, center_y, width=width, shape=shape):
            if (point_x, point_y) in changed_points:
                continue
            if erase:
                if current_mask is not None and not current_mask[point_y][point_x]:
                    continue
            else:
                assert target_rgb is not None
                is_visible = True if current_mask is None else bool(current_mask[point_y][point_x])
                if result.grid[point_y][point_x] == target_rgb and is_visible:
                    continue
            changed_points.add((point_x, point_y))
    if not changed_points:
        return result, 0
    next_grid = [list(row) for row in result.grid] if not erase else None
    next_mask = [list(row) for row in current_mask] if current_mask is not None else ([[True] * result.width for _ in range(result.height)] if needs_mask_copy else None)
    if erase:
        assert next_mask is not None
        for point_x, point_y in changed_points:
            next_mask[point_y][point_x] = False
        return replace(result, alpha_mask=_normalize_alpha_mask(next_mask)), len(changed_points)
    assert next_grid is not None and target_rgb is not None
    if next_mask is not None:
        for point_x, point_y in changed_points:
            next_grid[point_y][point_x] = target_rgb
            next_mask[point_y][point_x] = True
        return replace(result, grid=next_grid, alpha_mask=_normalize_alpha_mask(next_mask)), len(changed_points)
    for point_x, point_y in changed_points:
        next_grid[point_y][point_x] = target_rgb
    return replace(result, grid=next_grid), len(changed_points)


def _raw_exterior_outline_mask(visible: list[list[bool]], exterior: list[list[bool]]) -> list[list[bool]]:
    height = len(visible)
    width = len(visible[0]) if height else 0
    outline = [[False] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            if visible[y][x] or not exterior[y][x]:
                continue
            outline[y][x] = _touches_visible_pixel(visible, x, y)
    return outline


def _raw_exterior_edge_mask(visible: list[list[bool]], exterior: list[list[bool]]) -> list[list[bool]]:
    height = len(visible)
    width = len(visible[0]) if height else 0
    edge = [[False] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            if not visible[y][x]:
                continue
            edge[y][x] = _touches_exterior_space(exterior, x, y)
    return edge


def _exterior_transparent_mask(visible: list[list[bool]]) -> list[list[bool]]:
    height = len(visible)
    width = len(visible[0]) if height else 0
    exterior = [[False] * width for _ in range(height)]
    pending: list[tuple[int, int]] = []
    for x in range(width):
        pending.append((x, 0))
        pending.append((x, height - 1))
    for y in range(1, max(0, height - 1)):
        pending.append((0, y))
        pending.append((width - 1, y))
    while pending:
        x, y = pending.pop()
        if x < 0 or y < 0 or x >= width or y >= height:
            continue
        if exterior[y][x] or visible[y][x]:
            continue
        exterior[y][x] = True
        pending.append((x - 1, y))
        pending.append((x + 1, y))
        pending.append((x, y - 1))
        pending.append((x, y + 1))
    return exterior


def _touches_visible_pixel(visible: list[list[bool]], x: int, y: int) -> bool:
    height = len(visible)
    width = len(visible[0]) if height else 0
    for neighbor_y in range(max(0, y - 1), min(height, y + 2)):
        for neighbor_x in range(max(0, x - 1), min(width, x + 2)):
            if neighbor_x == x and neighbor_y == y:
                continue
            if visible[neighbor_y][neighbor_x]:
                return True
    return False


def _touches_exterior_space(exterior: list[list[bool]], x: int, y: int) -> bool:
    height = len(exterior)
    width = len(exterior[0]) if height else 0
    for neighbor_y in range(max(0, y - 1), min(height, y + 2)):
        for neighbor_x in range(max(0, x - 1), min(width, x + 2)):
            if neighbor_x == x and neighbor_y == y:
                continue
            if exterior[neighbor_y][neighbor_x]:
                return True
    return x == 0 or y == 0 or x == width - 1 or y == height - 1


def _pixel_perfect_mask(mask: list[list[bool]]) -> list[list[bool]]:
    cleaned = [row[:] for row in mask]
    height = len(cleaned)
    width = len(cleaned[0]) if height else 0
    if width == 0 or height == 0:
        return cleaned
    changed = True
    while changed:
        changed = False
        for phase in range(2):
            coordinates = [(x, y) for y in range(height) for x in range(width)]
            if phase == 1:
                coordinates.reverse()
            phase_changed = False
            for x, y in coordinates:
                if not _pixel_perfect_candidate(cleaned, x, y, phase):
                    continue
                cleaned[y][x] = False
                phase_changed = True
            changed = changed or phase_changed
    return cleaned


def _pixel_perfect_candidate(mask: list[list[bool]], x: int, y: int, phase: int) -> bool:
    if not mask[y][x]:
        return False
    north = y > 0 and mask[y - 1][x]
    east = x + 1 < len(mask[0]) and mask[y][x + 1]
    south = y + 1 < len(mask) and mask[y + 1][x]
    west = x > 0 and mask[y][x - 1]
    orthogonal = [north, east, south, west]
    active_neighbors = 0
    for neighbor_y in range(max(0, y - 1), min(len(mask), y + 2)):
        for neighbor_x in range(max(0, x - 1), min(len(mask[0]), x + 2)):
            if neighbor_x == x and neighbor_y == y:
                continue
            if mask[neighbor_y][neighbor_x]:
                active_neighbors += 1
    if active_neighbors < 2 or active_neighbors > 6:
        return False
    if sum(orthogonal) != 2:
        return False
    if (north and south) or (east and west):
        return False
    ring = orthogonal + [orthogonal[0]]
    transitions = sum((not current) and following for current, following in zip(ring, ring[1:]))
    if transitions != 1:
        return False
    if phase == 0:
        if north and east and south:
            return False
        if east and south and west:
            return False
    else:
        if north and east and west:
            return False
        if north and south and west:
            return False
    return _preserves_local_connectivity(mask, x, y)


def _preserves_local_connectivity(mask: list[list[bool]], x: int, y: int) -> bool:
    height = len(mask)
    width = len(mask[0]) if height else 0
    neighbors: list[tuple[int, int]] = []
    for neighbor_y in range(max(0, y - 1), min(height, y + 2)):
        for neighbor_x in range(max(0, x - 1), min(width, x + 2)):
            if neighbor_x == x and neighbor_y == y:
                continue
            if mask[neighbor_y][neighbor_x]:
                neighbors.append((neighbor_x, neighbor_y))
    if len(neighbors) <= 1:
        return True
    allowed = set(neighbors)
    pending = [neighbors[0]]
    visited: set[tuple[int, int]] = set()
    while pending:
        point = pending.pop()
        if point in visited:
            continue
        visited.add(point)
        px, py = point
        for neighbor_y in range(max(0, py - 1), min(height, py + 2)):
            for neighbor_x in range(max(0, px - 1), min(width, px + 2)):
                neighbor = (neighbor_x, neighbor_y)
                if neighbor in allowed and neighbor not in visited:
                    pending.append(neighbor)
    return len(visited) == len(allowed)


def _normalize_alpha_mask(mask: list[list[bool]]) -> tuple[tuple[bool, ...], ...] | None:
    if all(all(value for value in row) for row in mask):
        return None
    return tuple(tuple(row) for row in mask)


def grid_to_pil_image(grid: RGBGrid) -> Image.Image:
    height = len(grid)
    width = len(grid[0]) if height else 0
    image = Image.new("RGB", (width, height))
    if width == 0 or height == 0:
        return image
    image.putdata([pixel for row in grid for pixel in row])
    return image


def load_png_grid(path: str) -> RGBGrid:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        pixels = list(rgb.getdata())
    return [pixels[index : index + width] for index in range(0, width * height, width)] if height else []


def load_png_rgba_image(path: str) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGBA").copy()


def image_to_rgb_grid(image: Image.Image) -> RGBGrid:
    rgb = image.convert("RGB")
    width, height = rgb.size
    pixels = list(rgb.getdata())
    return [pixels[index : index + width] for index in range(0, width * height, width)] if height else []


def downsample_image(
    grid: RGBGrid,
    config: PipelineConfig,
    progress_callback: PipelineProgressCallback | None = None,
) -> ProcessResult:
    started = perf_counter()
    pipeline = PixelFixPipeline(config)
    prepared_input = pipeline.prepare_labels(
        rgb_to_labels(grid),
        progress_callback=progress_callback,
        grid_message=f"Downsampling with {display_resize_method(config.downsample_mode)}...",
    )
    display_palette_labels = tuple(extract_unique_colors(prepared_input.reduced_labels))
    rgb_grid = labels_to_rgb(prepared_input.reduced_labels)
    height = len(rgb_grid)
    width = len(rgb_grid[0]) if height else 0
    return ProcessResult(
        grid=rgb_grid,
        width=width,
        height=height,
        stats=ProcessStats(
            stage="downsample",
            pixel_width=prepared_input.pixel_width,
            resize_method=config.downsample_mode,
            input_size=prepared_input.input_size,
            output_size=(width, height),
            initial_color_count=prepared_input.initial_color_count,
            color_count=len(display_palette_labels),
            elapsed_seconds=perf_counter() - started,
        ),
        prepared_input=prepared_input,
        display_palette_labels=display_palette_labels,
    )


def reduce_palette_image(
    prepared_input: PipelinePreparedResult,
    config: PipelineConfig,
    palette_override: list[int] | None = None,
    structured_palette: StructuredPalette | None = None,
    progress_callback: PipelineProgressCallback | None = None,
) -> ProcessResult:
    started = perf_counter()
    pipeline = PixelFixPipeline(config)
    result = pipeline.run_prepared_labels(
        prepared_input,
        palette_override=palette_override,
        structured_palette=structured_palette,
        progress_callback=progress_callback,
    )
    output_palette_labels = tuple(extract_unique_colors(result.labels))
    display_palette_labels = tuple(result.structured_palette.labels()) if result.structured_palette is not None else output_palette_labels
    rgb_grid = labels_to_rgb(result.labels)
    height = len(rgb_grid)
    width = len(rgb_grid[0]) if height else 0
    return ProcessResult(
        grid=rgb_grid,
        width=width,
        height=height,
        stats=ProcessStats(
            stage="palette",
            pixel_width=result.pixel_width,
            resize_method=config.downsample_mode,
            input_size=prepared_input.input_size,
            output_size=(width, height),
            initial_color_count=prepared_input.initial_color_count,
            color_count=len(output_palette_labels),
            elapsed_seconds=perf_counter() - started,
            seed_count=result.seed_count,
            ramp_count=result.ramp_count,
            palette_strategy=result.structured_palette.source_mode if result.structured_palette is not None else config.palette_strategy,
            effective_palette_size=result.effective_palette_size,
            histogram_size=result.histogram_size,
            palette_generation_seconds=result.palette_generation_seconds,
            mapping_seconds=result.mapping_seconds,
        ),
        prepared_input=prepared_input,
        display_palette_labels=display_palette_labels,
        structured_palette=result.structured_palette,
    )


def process_image(
    grid: RGBGrid,
    config: PipelineConfig,
    palette_override: list[int] | None = None,
    structured_palette: StructuredPalette | None = None,
    progress_callback: PipelineProgressCallback | None = None,
    prepared_input: PipelinePreparedResult | None = None,
) -> ProcessResult:
    prepared = prepared_input
    if prepared is None:
        downsampled = downsample_image(grid, config, progress_callback=progress_callback)
        prepared = downsampled.prepared_input
    elif progress_callback is not None:
        progress_callback(10, "Preparing input")
        progress_callback(35, "Reusing downsampled image...")
    return reduce_palette_image(
        prepared,
        config,
        palette_override=palette_override,
        structured_palette=structured_palette,
        progress_callback=progress_callback,
    )


def display_resize_method(value: str) -> str:
    mapping = {
        "nearest": "Nearest Neighbor",
        "bilinear": "Bilinear Interpolation",
        "rotsprite": "RotSprite",
    }
    return mapping.get(value, value.title())

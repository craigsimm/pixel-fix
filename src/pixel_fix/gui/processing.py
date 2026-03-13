from __future__ import annotations

from dataclasses import replace
from dataclasses import dataclass
from time import perf_counter

from PIL import Image

from pixel_fix.palette.model import StructuredPalette
from pixel_fix.palette.color_modes import extract_unique_colors
from pixel_fix.pipeline import (
    PipelineConfig,
    PipelinePreparedResult,
    PipelineProgressCallback,
    PixelFixPipeline,
)
from pixel_fix.types import LabelGrid

RGB = tuple[int, int, int]
RGBGrid = list[list[RGB]]


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


<<<<<<< ours
<<<<<<< ours
def add_exterior_outline(result: ProcessResult, outline_label: int, *, transparent_labels: set[int] | None = None) -> tuple[ProcessResult, int]:
=======
def apply_pencil_stroke(result: ProcessResult, points: list[tuple[int, int]], label: int) -> tuple[ProcessResult, int]:
    if result.width <= 0 or result.height <= 0 or not points:
        return result, 0
    paint_rgb = ((label >> 16) & 0xFF, (label >> 8) & 0xFF, label & 0xFF)
    next_grid = [list(row) for row in result.grid]
    next_mask = [list(row) for row in result.alpha_mask] if result.alpha_mask is not None else [[True] * result.width for _ in range(result.height)]
    changed = 0
    for x, y in points:
        if x < 0 or y < 0 or x >= result.width or y >= result.height:
            continue
        became_visible = not next_mask[y][x]
        recolored = next_grid[y][x] != paint_rgb
        if not became_visible and not recolored:
            continue
        next_grid[y][x] = paint_rgb
        next_mask[y][x] = True
        changed += 1
    if changed == 0:
        return result, 0
    return replace(result, grid=next_grid, alpha_mask=_normalize_alpha_mask(next_mask)), changed


def apply_eraser_stroke(result: ProcessResult, points: list[tuple[int, int]]) -> tuple[ProcessResult, int]:
    if result.width <= 0 or result.height <= 0 or not points:
        return result, 0
    next_mask = [list(row) for row in result.alpha_mask] if result.alpha_mask is not None else [[True] * result.width for _ in range(result.height)]
    changed = 0
    for x, y in points:
        if x < 0 or y < 0 or x >= result.width or y >= result.height:
            continue
        if not next_mask[y][x]:
            continue
        next_mask[y][x] = False
        changed += 1
    if changed == 0:
        return result, 0
    return replace(result, alpha_mask=_normalize_alpha_mask(next_mask)), changed
=======
def brush_pixels(center: tuple[int, int], width: int, shape: str, bounds: tuple[int, int]) -> list[tuple[int, int]]:
    image_width, image_height = bounds
    if image_width <= 0 or image_height <= 0 or width <= 0:
        return []

    x, y = center
    diameter = max(1, width)
    radius = diameter // 2
    start_x = x - radius
    start_y = y - radius
    end_x = start_x + diameter
    end_y = start_y + diameter

    pixels: list[tuple[int, int]] = []
    for py in range(start_y, end_y):
        if py < 0 or py >= image_height:
            continue
        for px in range(start_x, end_x):
            if px < 0 or px >= image_width:
                continue
            if shape == "round":
                dx = px - x
                dy = py - y
                if (dx * dx) + (dy * dy) > (radius * radius):
                    continue
            pixels.append((px, py))
    return pixels
>>>>>>> theirs


def add_exterior_outline(
    result: ProcessResult,
    outline_label: int,
    *,
    transparent_labels: set[int] | None = None,
    pixel_perfect: bool = True,
    adaptive: bool = False,
<<<<<<< ours
=======
    darken_factor: float = 0.8,
>>>>>>> theirs
) -> tuple[ProcessResult, int]:
>>>>>>> theirs
    if result.width <= 0 or result.height <= 0:
        return result, 0
    visible = _effective_visible_mask(result, transparent_labels)
    exterior = _exterior_transparent_mask(visible)
<<<<<<< ours
    outline_rgb = ((outline_label >> 16) & 0xFF, (outline_label >> 8) & 0xFF, outline_label & 0xFF)
=======
    outline_mask = _raw_exterior_outline_mask(visible, exterior)
    if pixel_perfect:
        outline_mask = _pixel_perfect_mask(outline_mask)
<<<<<<< ours
>>>>>>> theirs
=======
>>>>>>> theirs
    next_grid = [list(row) for row in result.grid]
    next_mask = [row[:] for row in visible]
    changed = 0
    for y in range(result.height):
        for x in range(result.width):
            if visible[y][x] or not exterior[y][x]:
                continue
<<<<<<< ours
            if not _touches_visible_pixel(visible, x, y):
                continue
            if adaptive:
<<<<<<< ours
                interior_labels = _sample_interior_neighbor_labels(result, visible, x, y)
                dominant = _select_dominant_color_label(interior_labels)
                label = _darken_label(dominant)
                next_grid[y][x] = ((label >> 16) & 0xFF, (label >> 8) & 0xFF, label & 0xFF)
            else:
                next_grid[y][x] = ((outline_label >> 16) & 0xFF, (outline_label >> 8) & 0xFF, outline_label & 0xFF)
=======
            if adaptive:
                next_grid[y][x] = _adaptive_outline_rgb(result, visible, x, y)
            else:
                next_grid[y][x] = outline_rgb
>>>>>>> theirs
=======
                next_grid[y][x] = _adaptive_outline_color(result.grid, visible, x, y, darken_factor=darken_factor)
            else:
                next_grid[y][x] = ((outline_label >> 16) & 0xFF, (outline_label >> 8) & 0xFF, outline_label & 0xFF)
>>>>>>> theirs
            next_mask[y][x] = True
            changed += 1
    if changed == 0:
        return result, 0
<<<<<<< ours
    output_palette_labels = tuple(extract_unique_colors(rgb_to_labels(next_grid)))
    display_palette_labels = output_palette_labels
    if result.display_palette_labels:
        ordered_palette = list(result.display_palette_labels)
        existing = set(ordered_palette)
        ordered_palette.extend(label for label in output_palette_labels if label not in existing)
        display_palette_labels = tuple(ordered_palette)
    return (
        replace(
            result,
            grid=next_grid,
            alpha_mask=_normalize_alpha_mask(next_mask),
            display_palette_labels=display_palette_labels,
        ),
        changed,
    )

=======
    return replace(
        result,
        grid=next_grid,
        alpha_mask=_normalize_alpha_mask(next_mask),
        display_palette_labels=tuple(extract_unique_colors(rgb_to_labels(next_grid))),
    ), changed


def _adaptive_outline_color(
    grid: RGBGrid,
    visible: list[list[bool]],
    x: int,
    y: int,
    *,
    darken_factor: float,
) -> RGB:
    counts: dict[int, int] = {}
    height = len(grid)
    width = len(grid[0]) if height else 0
    for ny in range(max(0, y - 1), min(height, y + 2)):
        for nx in range(max(0, x - 1), min(width, x + 2)):
            if nx == x and ny == y:
                continue
            if not visible[ny][nx]:
                continue
            red, green, blue = grid[ny][nx]
            label = (red << 16) | (green << 8) | blue
            counts[label] = counts.get(label, 0) + 1
    if not counts:
        return (0, 0, 0)
    dominant = min(((-count, label) for label, count in counts.items()))[1]
    red = (dominant >> 16) & 0xFF
    green = (dominant >> 8) & 0xFF
    blue = dominant & 0xFF
    factor = max(0.0, min(1.0, darken_factor))
    return (int(red * factor), int(green * factor), int(blue * factor))
>>>>>>> theirs

<<<<<<< ours
<<<<<<< ours
def remove_exterior_outline(result: ProcessResult, *, transparent_labels: set[int] | None = None) -> tuple[ProcessResult, int]:
=======
=======
def _adaptive_outline_rgb(result: ProcessResult, visible: list[list[bool]], x: int, y: int) -> RGBPixel:
    counts: dict[RGBPixel, int] = {}
    for ny in range(max(0, y - 1), min(result.height, y + 2)):
        for nx in range(max(0, x - 1), min(result.width, x + 2)):
            if nx == x and ny == y:
                continue
            if not visible[ny][nx]:
                continue
            rgb = result.grid[ny][nx]
            counts[rgb] = counts.get(rgb, 0) + 1
    if not counts:
        return result.grid[y][x]
    return max(counts.items(), key=lambda item: item[1])[0]


>>>>>>> theirs
def remove_exterior_outline(
    result: ProcessResult,
    *,
    transparent_labels: set[int] | None = None,
    pixel_perfect: bool = True,
<<<<<<< ours
    brightness_threshold: int = 255,
=======
    brightness_threshold: int | None = None,
>>>>>>> theirs
) -> tuple[ProcessResult, int]:
>>>>>>> theirs
    if result.width <= 0 or result.height <= 0:
        return result, 0
    visible = _effective_visible_mask(result, transparent_labels)
    exterior = _exterior_transparent_mask(visible)
<<<<<<< ours
=======
    remove_mask = _raw_exterior_edge_mask(visible, exterior)
    if pixel_perfect:
        remove_mask = _pixel_perfect_mask(remove_mask)
    threshold = _normalized_brightness_threshold(brightness_threshold)
>>>>>>> theirs
    next_mask = [row[:] for row in visible]
    changed = 0
    for y in range(result.height):
        for x in range(result.width):
            if not visible[y][x]:
                continue
            if not _touches_exterior_space(exterior, x, y):
                continue
            red, green, blue = result.grid[y][x]
            brightness = int(round((red * 0.299) + (green * 0.587) + (blue * 0.114)))
            if brightness > max(0, min(255, brightness_threshold)):
                continue
            if threshold is not None and _pixel_brightness(result.grid[y][x]) > threshold:
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


<<<<<<< ours
<<<<<<< ours
=======
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


def _darken_label(label: int, factor: float = 0.7) -> int:
    red = max(0, min(255, int(((label >> 16) & 0xFF) * factor)))
    green = max(0, min(255, int(((label >> 8) & 0xFF) * factor)))
    blue = max(0, min(255, int((label & 0xFF) * factor)))
    return (red << 16) | (green << 8) | blue
=======
def _normalized_brightness_threshold(value: int | None) -> int | None:
    if value is None:
        return None
    return max(0, min(255, int(value)))


def _pixel_brightness(rgb: RGB) -> int:
    red, green, blue = rgb
    return round((0.299 * red) + (0.587 * green) + (0.114 * blue))
>>>>>>> theirs


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


>>>>>>> theirs
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

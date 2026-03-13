from types import SimpleNamespace
from pathlib import Path

from PIL import Image
import pytest

import pixel_fix.gui.app as app_module
from pixel_fix.gui.app import PaletteUndoState, PixelFixGui
from pixel_fix.gui.processing import (
    ProcessResult,
    ProcessStats,
    add_exterior_outline,
    apply_eraser_stroke,
    apply_pencil_stroke,
    apply_transparency_fill,
    brush_pixels,
    downsample_image,
    process_image,
    reduce_palette_image,
    remove_exterior_outline,
)
from pixel_fix.gui.state import PreviewSettings
from pixel_fix.palette.advanced import generate_structured_palette
from pixel_fix.palette.sort import (
    PALETTE_SELECT_LABELS,
    PALETTE_SELECT_LIGHTNESS_DARK,
    PALETTE_SELECT_MODES,
    PALETTE_SORT_HUE,
    PALETTE_SORT_LIGHTNESS,
)
from pixel_fix.palette.workspace import ColorWorkspace
from pixel_fix.pipeline import PipelineConfig, PipelinePreparedResult




def _similarity_selection_mode() -> str:
    for mode in PALETTE_SELECT_MODES:
        if "similar" in mode or "duplicate" in mode:
            return mode
    pytest.skip("Similarity palette selection mode is not available in this build.")

def _sample_grid():
    return [
        [(255, 0, 0), (255, 0, 0), (0, 0, 255), (0, 0, 255)],
        [(255, 0, 0), (255, 0, 0), (0, 0, 255), (0, 0, 255)],
        [(0, 255, 0), (0, 255, 0), (255, 255, 0), (255, 255, 0)],
        [(0, 255, 0), (0, 255, 0), (255, 255, 0), (255, 255, 0)],
    ]


class PickerPreviewFrameStub:
    def __init__(self) -> None:
        self.manager = ""
        self.pack_calls: list[dict[str, object]] = []

    def pack(self, **kwargs) -> None:
        self.manager = "pack"
        self.pack_calls.append(kwargs)

    def pack_forget(self) -> None:
        self.manager = ""

    def winfo_manager(self) -> str:
        return self.manager


class PickerPreviewSwatchStub:
    def __init__(self) -> None:
        self.config: dict[str, object] = {}

    def configure(self, **kwargs) -> None:
        self.config.update(kwargs)


def _result_from_labels(labels: list[list[int]], *, stage: str = "palette") -> ProcessResult:
    height = len(labels)
    width = len(labels[0]) if height else 0
    return ProcessResult(
        grid=[[((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF) for value in row] for row in labels],
        width=width,
        height=height,
        stats=ProcessStats(
            stage=stage,
            pixel_width=1,
            resize_method="nearest",
            input_size=(width, height),
            output_size=(width, height),
            initial_color_count=len({value for row in labels for value in row}),
            color_count=len({value for row in labels for value in row}),
            elapsed_seconds=0.0,
        ),
        prepared_input=PipelinePreparedResult(
            reduced_labels=labels,
            pixel_width=1,
            grid_method="manual",
            input_size=(width, height),
            initial_color_count=len({value for row in labels for value in row}),
        ),
        alpha_mask=tuple(tuple(value != 0x000000 for value in row) for row in labels),
    )


class WidgetStub:
    def __init__(self) -> None:
        self.state = None
        self.text = None

    def configure(self, **kwargs) -> None:
        if "state" in kwargs:
            self.state = kwargs["state"]
        if "text" in kwargs:
            self.text = kwargs["text"]


class MenuStub:
    def __init__(self) -> None:
        self.states: dict[str, object] = {}

    def entryconfigure(self, label: str, **kwargs) -> None:
        self.states[label] = kwargs.get("state")


<<<<<<< ours
=======
def _assert_no_full_2x2(mask: list[list[bool]]) -> None:
    height = len(mask)
    width = len(mask[0]) if height else 0
    for y in range(max(0, height - 1)):
        for x in range(max(0, width - 1)):
            assert not (mask[y][x] and mask[y][x + 1] and mask[y + 1][x] and mask[y + 1][x + 1])



def test_brush_pixels_width_one_affects_exactly_center_pixel() -> None:
    assert brush_pixels((2, 3), 1, "square", (8, 8)) == [(2, 3)]
    assert brush_pixels((2, 3), 1, "round", (8, 8)) == [(2, 3)]


def test_brush_pixels_square_returns_full_axis_aligned_block() -> None:
    pixels = brush_pixels((4, 4), 3, "square", (10, 10))

    assert set(pixels) == {
        (3, 3), (4, 3), (5, 3),
        (3, 4), (4, 4), (5, 4),
        (3, 5), (4, 5), (5, 5),
    }


def test_brush_pixels_round_uses_radius_test() -> None:
    pixels = brush_pixels((4, 4), 5, "round", (12, 12))

    assert set(pixels) == {
        (4, 2),
        (3, 3), (4, 3), (5, 3),
        (2, 4), (3, 4), (4, 4), (5, 4), (6, 4),
        (3, 5), (4, 5), (5, 5),
        (4, 6),
    }


def test_brush_pixels_clips_to_bounds() -> None:
    pixels = brush_pixels((0, 0), 3, "square", (2, 2))

    assert set(pixels) == {(0, 0), (1, 0), (0, 1), (1, 1)}

>>>>>>> theirs
def test_downsample_image_returns_metadata_and_progress() -> None:
    progress: list[tuple[int, str]] = []
    result = downsample_image(
        _sample_grid(),
        PipelineConfig(pixel_width=2, downsample_mode="nearest"),
        progress_callback=lambda percent, message: progress.append((percent, message)),
    )
    assert result.width == 2
    assert result.height == 2
    assert result.stats.stage == "downsample"
    assert result.stats.pixel_width == 2
    assert result.stats.output_size == (2, 2)
    assert result.stats.color_count == 4
    assert result.display_palette_labels == (0xFF0000, 0x0000FF, 0x00FF00, 0xFFFF00)
    assert progress == [
        (10, "Preparing input"),
        (35, "Downsampling with Nearest Neighbor..."),
    ]


def test_reduce_palette_image_uses_prepared_input() -> None:
    downsampled = downsample_image(_sample_grid(), PipelineConfig(pixel_width=2))
    structured_palette = generate_structured_palette(
        downsampled.prepared_input.reduced_labels,
        key_colors=[0xFF0000, 0x0000FF],
        generated_shades=2,
    ).palette
    progress: list[tuple[int, str]] = []
    reduced = reduce_palette_image(
        downsampled.prepared_input,
        PipelineConfig(pixel_width=2, key_colors=(0xFF0000, 0x0000FF), generated_shades=2),
        structured_palette=structured_palette,
        progress_callback=lambda percent, message: progress.append((percent, message)),
    )
    assert reduced.stats.stage == "palette"
    assert reduced.stats.pixel_width == 2
    assert reduced.stats.output_size == (2, 2)
    assert reduced.structured_palette is not None
    assert reduced.stats.palette_strategy == "advanced"
    assert reduced.stats.effective_palette_size == reduced.structured_palette.palette_size()
    assert reduced.structured_palette.generated_shades == 2
    assert progress == [
        (65, "Using generated palette..."),
        (90, "Finalizing output..."),
        (100, "Complete"),
    ]


def test_process_image_reuses_prepared_downsample() -> None:
    first = downsample_image(_sample_grid(), PipelineConfig(pixel_width=2))
    structured_palette = generate_structured_palette(
        first.prepared_input.reduced_labels,
        key_colors=[0xFF0000, 0x0000FF],
        generated_shades=2,
    ).palette
    progress: list[tuple[int, str]] = []
    second = process_image(
        _sample_grid(),
        PipelineConfig(pixel_width=2, key_colors=(0xFF0000, 0x0000FF), generated_shades=2),
        structured_palette=structured_palette,
        prepared_input=first.prepared_input,
        progress_callback=lambda percent, message: progress.append((percent, message)),
    )
    assert second.stats.pixel_width == 2
    assert second.structured_palette is not None
    assert second.stats.ramp_count == len(second.structured_palette.ramps)
    assert progress == [
        (10, "Preparing input"),
        (35, "Reusing downsampled image..."),
        (65, "Using generated palette..."),
        (90, "Finalizing output..."),
        (100, "Complete"),
    ]
def test_build_output_display_image_respects_alpha_mask() -> None:
    prepared = PipelinePreparedResult(
        reduced_labels=[[0x111111, 0xEEEEEE]],
        pixel_width=1,
        grid_method="manual",
        input_size=(2, 1),
        initial_color_count=2,
    )
    result = ProcessResult(
        grid=[[(17, 17, 17), (238, 238, 238)]],
        width=2,
        height=1,
        stats=ProcessStats(
            stage="palette",
            pixel_width=1,
            resize_method="nearest",
            input_size=(2, 1),
            output_size=(2, 1),
            initial_color_count=2,
            color_count=2,
            elapsed_seconds=0.0,
        ),
        prepared_input=prepared,
        alpha_mask=((True, False),),
    )
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.transparent_colors = set()

    image = PixelFixGui._build_output_display_image(gui, result)

    assert image.getpixel((0, 0))[3] == 255
    assert image.getpixel((1, 0))[3] == 0


def test_apply_transparency_fill_only_removes_connected_region() -> None:
    prepared = PipelinePreparedResult(
        reduced_labels=[
            [0xFF0000, 0xFF0000, 0x0000FF],
            [0x0000FF, 0x0000FF, 0xFF0000],
        ],
        pixel_width=1,
        grid_method="manual",
        input_size=(3, 2),
        initial_color_count=2,
    )
    result = ProcessResult(
        grid=[
            [(255, 0, 0), (255, 0, 0), (0, 0, 255)],
            [(0, 0, 255), (0, 0, 255), (255, 0, 0)],
        ],
        width=3,
        height=2,
        stats=ProcessStats(
            stage="downsample",
            pixel_width=1,
            resize_method="nearest",
            input_size=(3, 2),
            output_size=(3, 2),
            initial_color_count=2,
            color_count=2,
            elapsed_seconds=0.0,
        ),
        prepared_input=prepared,
    )

    updated, changed = apply_transparency_fill(result, 0, 0)

    assert changed == 2
    assert updated.alpha_mask == (
        (False, False, True),
        (True, True, True),
    )


def test_add_exterior_outline_adds_ring_without_touching_interior() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000],
            [0x000000, 0x445566, 0x000000],
            [0x000000, 0x000000, 0x000000],
        ]
    )

    updated, changed = add_exterior_outline(result, 0x112233)

    assert changed == 8
    assert updated.grid[1][1] == (0x44, 0x55, 0x66)
    assert updated.grid[0][0] == (0x11, 0x22, 0x33)
    assert updated.alpha_mask is None


<<<<<<< ours
def test_add_exterior_outline_ignores_internal_holes() -> None:
=======
def test_add_exterior_outline_updates_display_palette_labels_with_new_colour() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000],
            [0x000000, 0x445566, 0x000000],
            [0x000000, 0x000000, 0x000000],
        ]
    )

    updated, changed = add_exterior_outline(result, 0x112233)

    assert changed == 4
    assert updated.display_palette_labels == (0x000000, 0x112233, 0x445566)


def test_add_exterior_outline_preserves_display_palette_order_and_appends_new_colour() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000],
            [0x000000, 0x445566, 0x000000],
            [0x000000, 0x000000, 0x000000],
        ]
    )
    result = ProcessResult(
        grid=result.grid,
        width=result.width,
        height=result.height,
        stats=result.stats,
        prepared_input=result.prepared_input,
        display_palette_labels=(0x445566, 0xABCDEF),
        structured_palette=result.structured_palette,
        alpha_mask=result.alpha_mask,
    )

    updated, changed = add_exterior_outline(result, 0x112233)

    assert changed == 4
    assert updated.display_palette_labels == (0x445566, 0xABCDEF, 0x000000, 0x112233)


def test_add_exterior_outline_pixel_perfect_ignores_internal_holes() -> None:
>>>>>>> theirs
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x445566, 0x445566, 0x445566, 0x000000],
            [0x000000, 0x445566, 0x000000, 0x445566, 0x000000],
            [0x000000, 0x445566, 0x445566, 0x445566, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
        ]
    )

    updated, changed = add_exterior_outline(result, 0x112233)

    assert changed == 16
    assert updated.alpha_mask is not None
    assert updated.alpha_mask[2][2] is False
    assert updated.grid[2][2] == (0, 0, 0)
    assert updated.grid[0][2] == (0x11, 0x22, 0x33)


<<<<<<< ours
def test_remove_exterior_outline_erodes_only_outside_edge() -> None:
=======
def test_add_exterior_outline_pixel_perfect_stair_step_has_no_full_2x2_blocks() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x445566, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x000000, 0x445566, 0x000000, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x445566, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
        ]
    )

    updated, changed = add_exterior_outline(result, 0x112233)

    assert changed > 0
    assert updated.alpha_mask is not None
    added_mask = [
        [bool(updated.alpha_mask[y][x]) and not bool(result.alpha_mask[y][x]) for x in range(result.width)]
        for y in range(result.height)
    ]
    _assert_no_full_2x2(added_mask)




<<<<<<< ours
<<<<<<< ours
def test_add_exterior_outline_adaptive_uses_dominant_neighbor_color() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000],
            [0x000000, 0x445566, 0x000000],
=======
def test_add_exterior_outline_adaptive_uses_dominant_neighbour_colour() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x445566, 0x112233, 0x000000],
            [0x000000, 0x445566, 0x000000, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000],
        ]
    )

    updated, _changed = add_exterior_outline(result, 0xFFFFFF, adaptive=True, pixel_perfect=False)

    assert updated.grid[2][2] == (0x36, 0x44, 0x51)


def test_add_exterior_outline_adaptive_tie_breaker_is_deterministic() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x112233, 0x224466, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000],
        ]
    )

    updated, _changed = add_exterior_outline(result, 0xFFFFFF, adaptive=True, pixel_perfect=False)

    assert updated.grid[0][1] == (0x0D, 0x1B, 0x28)


def test_add_exterior_outline_adaptive_darkens_output_with_configured_factor() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000],
            [0x000000, 0x204060, 0x000000],
>>>>>>> theirs
            [0x000000, 0x000000, 0x000000],
        ]
    )

<<<<<<< ours
    updated, changed = add_exterior_outline(result, 0x112233, adaptive=True)

    assert changed == 4
    assert updated.alpha_mask is not None
    assert updated.grid[0][1] == (0x2F, 0x3B, 0x47)
    assert updated.grid[1][0] == (0x2F, 0x3B, 0x47)
    assert updated.grid[1][2] == (0x2F, 0x3B, 0x47)
    assert updated.grid[2][1] == (0x2F, 0x3B, 0x47)


def test_add_exterior_outline_adaptive_tie_breaks_to_smallest_label() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0xFF0000],
            [0x0000FF, 0x000000],
=======
def test_add_exterior_outline_adaptive_uses_neighbouring_colours() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x112233, 0x445566, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000],
>>>>>>> theirs
        ]
    )

    updated, changed = add_exterior_outline(result, 0xABCDEF, adaptive=True, pixel_perfect=False)

<<<<<<< ours
    assert changed == 2
    assert updated.grid[0][0] == (0x00, 0x00, 0xB2)
    assert updated.grid[1][1] == (0x00, 0x00, 0xB2)

=======
    assert changed > 0
    assert updated.grid[0][1] in {(0x11, 0x22, 0x33), (0x44, 0x55, 0x66)}
    assert updated.grid[0][2] in {(0x11, 0x22, 0x33), (0x44, 0x55, 0x66)}
    assert updated.grid[0][1] != (0xAB, 0xCD, 0xEF)
>>>>>>> theirs
=======
    updated, _changed = add_exterior_outline(result, 0xFFFFFF, adaptive=True, darken_factor=0.5)

    assert updated.grid[0][1] == (0x10, 0x20, 0x30)


def test_add_exterior_outline_adaptive_respects_pixel_perfect_and_square_modes() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000],
            [0x000000, 0x445566, 0x000000],
            [0x000000, 0x000000, 0x000000],
        ]
    )

    pixel_perfect, pixel_perfect_changed = add_exterior_outline(result, 0xFFFFFF, adaptive=True)
    square, square_changed = add_exterior_outline(result, 0xFFFFFF, adaptive=True, pixel_perfect=False)

    assert pixel_perfect_changed == 4
    assert square_changed == 8
    assert pixel_perfect.alpha_mask is not None
    assert square.alpha_mask is None


def test_add_exterior_outline_adaptive_updates_display_palette_labels() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000],
            [0x000000, 0x204060, 0x000000],
            [0x000000, 0x000000, 0x000000],
        ]
    )

    updated, _changed = add_exterior_outline(result, 0xFFFFFF, adaptive=True)

    assert 0x19334C in updated.display_palette_labels
>>>>>>> theirs

def test_remove_exterior_outline_defaults_to_pixel_perfect_edge_removal() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x445566, 0x445566, 0x445566, 0x000000],
            [0x000000, 0x445566, 0x445566, 0x445566, 0x000000],
            [0x000000, 0x445566, 0x445566, 0x445566, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
        ]
    )

    updated, changed = remove_exterior_outline(result)

    assert changed == 4
    assert updated.alpha_mask is not None
    assert updated.alpha_mask[1][1] is True
    assert updated.alpha_mask[1][2] is False
    assert updated.alpha_mask[2][1] is False
    assert updated.alpha_mask[2][2] is True
    assert updated.alpha_mask[2][3] is False
    assert updated.alpha_mask[3][2] is False
    assert updated.alpha_mask[3][3] is True


def test_remove_exterior_outline_square_mode_erodes_only_outside_edge() -> None:
>>>>>>> theirs
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x445566, 0x445566, 0x445566, 0x445566, 0x445566, 0x000000],
            [0x000000, 0x445566, 0x445566, 0x445566, 0x445566, 0x445566, 0x000000],
            [0x000000, 0x445566, 0x445566, 0x000000, 0x445566, 0x445566, 0x000000],
            [0x000000, 0x445566, 0x445566, 0x445566, 0x445566, 0x445566, 0x000000],
            [0x000000, 0x445566, 0x445566, 0x445566, 0x445566, 0x445566, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
        ]
    )

    updated, changed = remove_exterior_outline(result)

    assert changed == 16
    assert updated.alpha_mask is not None
    assert updated.alpha_mask[2][2] is True
    assert updated.alpha_mask[3][2] is True
    assert updated.alpha_mask[1][1] is False
    assert updated.alpha_mask[5][5] is False


def test_remove_exterior_outline_can_erase_one_pixel_wide_shape() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x445566, 0x000000],
            [0x000000, 0x445566, 0x000000],
            [0x000000, 0x445566, 0x000000],
        ]
    )

    updated, changed = remove_exterior_outline(result)

    assert changed == 3
    assert updated.alpha_mask == (
        (False, False, False),
        (False, False, False),
        (False, False, False),
    )


<<<<<<< ours
<<<<<<< ours
<<<<<<< ours
def _require_brush_processing_api() -> None:
    required = [
        "brush_footprint",
        "apply_pencil_operation",
        "apply_eraser_operation",
    ]
    missing = [name for name in required if not hasattr(app_module, name)]
    if missing:
        pytest.skip(f"Brush-processing API is not available in this build: {', '.join(missing)}")


def test_brush_api_square_and_round_footprints_vary_by_width() -> None:
    _require_brush_processing_api()

    square_w1 = set(app_module.brush_footprint(width=1, shape="square"))
    square_w3 = set(app_module.brush_footprint(width=3, shape="square"))
    round_w1 = set(app_module.brush_footprint(width=1, shape="round"))
    round_w3 = set(app_module.brush_footprint(width=3, shape="round"))

    assert square_w1 == {(0, 0)}
    assert round_w1 == {(0, 0)}
    assert len(square_w3) > len(square_w1)
    assert len(round_w3) > len(round_w1)
    assert round_w3 != square_w3


def test_brush_api_pencil_and_eraser_apply_expected_alpha_changes() -> None:
    _require_brush_processing_api()

    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000],
            [0x000000, 0x000000, 0x000000],
            [0x000000, 0x000000, 0x000000],
        ]
    )
=======
def test_apply_pencil_stroke_recolors_and_restores_visibility() -> None:
    result = _result_from_labels(
        [
            [0x111111, 0x222222],
            [0x333333, 0x444444],
        ]
    )
    result = ProcessResult(
        grid=result.grid,
        width=result.width,
        height=result.height,
        stats=result.stats,
        prepared_input=result.prepared_input,
        alpha_mask=((False, True), (True, True)),
    )

    updated, changed = apply_pencil_stroke(result, [(0, 0), (1, 0), (4, 4)], 0xAA5500)

    assert changed == 2
    assert updated.grid[0][0] == (0xAA, 0x55, 0x00)
    assert updated.grid[0][1] == (0xAA, 0x55, 0x00)
    assert updated.alpha_mask is None


def test_apply_pencil_stroke_noop_when_pixels_already_match() -> None:
    result = _result_from_labels([[0x112233]])

    updated, changed = apply_pencil_stroke(result, [(0, 0), (0, 0)], 0x112233)

    assert changed == 0
    assert updated is result


def test_apply_eraser_stroke_hides_pixels_without_recoloring() -> None:
    result = _result_from_labels(
        [
            [0x112233, 0x445566],
            [0x778899, 0xAABBCC],
        ]
    )

    updated, changed = apply_eraser_stroke(result, [(0, 0), (1, 0), (3, 3)])

    assert changed == 2
    assert updated.grid == result.grid
    assert updated.alpha_mask == ((False, False), (True, True))


def test_apply_eraser_stroke_noop_when_pixels_already_hidden() -> None:
    result = _result_from_labels([[0x112233]])
>>>>>>> theirs
    result = ProcessResult(
        grid=result.grid,
        width=result.width,
        height=result.height,
        stats=result.stats,
        prepared_input=result.prepared_input,
<<<<<<< ours
        alpha_mask=((False, False, False), (False, False, False), (False, False, False)),
    )

    painted, painted_changed = app_module.apply_pencil_operation(
        result,
        x=1,
        y=1,
        label=0xAABBCC,
        width=1,
        shape="square",
    )
    assert painted_changed == 1
    assert painted.grid[1][1] == (0xAA, 0xBB, 0xCC)
    assert painted.alpha_mask is not None
    assert painted.alpha_mask[1][1] is True

    erased, erased_changed = app_module.apply_eraser_operation(painted, x=1, y=1, width=1, shape="square")
    assert erased_changed == 1
    assert erased.alpha_mask is not None
    assert erased.alpha_mask[1][1] is False


def test_brush_api_no_op_cases_report_zero_changed() -> None:
    _require_brush_processing_api()

    result = _result_from_labels([[0x112233]])
    no_paint, changed = app_module.apply_pencil_operation(result, x=-1, y=-1, label=0xFFFFFF, width=1, shape="square")
    assert changed == 0
    assert no_paint is result

    no_erase, changed = app_module.apply_eraser_operation(result, x=-1, y=-1, width=1, shape="round")
    assert changed == 0
    assert no_erase is result


def _require_brush_gui_api() -> None:
    required = ["_on_canvas_press", "_on_canvas_drag", "_on_canvas_release"]
    if any(not hasattr(PixelFixGui, name) for name in required) or not hasattr(PixelFixGui, "_apply_brush_stroke"):
        pytest.skip("GUI brush interaction API is not available in this build")


def test_gui_brush_drag_interpolates_without_holes() -> None:
    _require_brush_gui_api()

    applied: list[tuple[int, int]] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui.dragging = False
    gui._display_context = object()
    gui.canvas = SimpleNamespace(configure=lambda **_kwargs: None, winfo_width=lambda: 64, winfo_height=lambda: 64)
    gui.redraw_canvas = lambda: None
    gui._point_is_over_image = lambda *_args, **_kwargs: True
    gui._preview_image_coordinates = lambda x, y, **_kwargs: (x, y)
    gui._cursor_for_pointer = lambda: ""
    gui._apply_brush_stroke = lambda x, y, *_args, **_kwargs: applied.append((x, y))

    PixelFixGui._on_canvas_press(gui, SimpleNamespace(x=1, y=1))
    PixelFixGui._on_canvas_drag(gui, SimpleNamespace(x=4, y=1))
    PixelFixGui._on_canvas_release(gui, SimpleNamespace())

    xs = sorted({x for x, y in applied if y == 1})
    assert xs == list(range(min(xs), max(xs) + 1))


def test_gui_brush_stroke_captures_single_undo_for_press_drag_release() -> None:
    _require_brush_gui_api()

    calls: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui.dragging = False
    gui._display_context = object()
    gui.canvas = SimpleNamespace(configure=lambda **_kwargs: None, winfo_width=lambda: 64, winfo_height=lambda: 64)
    gui.redraw_canvas = lambda: None
    gui._point_is_over_image = lambda *_args, **_kwargs: True
    gui._preview_image_coordinates = lambda x, y, **_kwargs: (x, y)
    gui._cursor_for_pointer = lambda: ""
    gui._apply_brush_stroke = lambda *_args, **_kwargs: None
    gui._capture_palette_undo_state = lambda: calls.append("capture")

    PixelFixGui._on_canvas_press(gui, SimpleNamespace(x=1, y=1))
    PixelFixGui._on_canvas_drag(gui, SimpleNamespace(x=3, y=1))
    PixelFixGui._on_canvas_drag(gui, SimpleNamespace(x=5, y=1))
    PixelFixGui._on_canvas_release(gui, SimpleNamespace())

    assert calls == ["capture"]
=======
        alpha_mask=((False,),),
    )

    updated, changed = apply_eraser_stroke(result, [(0, 0), (0, 0)])

    assert changed == 0
    assert updated is result
>>>>>>> theirs
=======
def test_remove_exterior_outline_respects_brightness_threshold() -> None:
=======
def test_remove_exterior_outline_brightness_threshold_only_removes_dark_edges() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x112233, 0xD0D0D0, 0x112233, 0x000000],
            [0x000000, 0x112233, 0x112233, 0x112233, 0x000000],
            [0x000000, 0x112233, 0x112233, 0x112233, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
        ]
    )

    updated, changed = remove_exterior_outline(result, pixel_perfect=False, brightness_threshold=80)

    assert changed == 7
    assert updated.alpha_mask is not None
    assert updated.alpha_mask[1][2] is True
    assert updated.alpha_mask[2][2] is True


def test_remove_exterior_outline_brightness_threshold_clamps_high_values() -> None:
>>>>>>> theirs
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000],
            [0x000000, 0xFFFFFF, 0x000000],
            [0x000000, 0x000000, 0x000000],
        ]
    )

<<<<<<< ours
    updated, changed = remove_exterior_outline(result, pixel_perfect=False, brightness_threshold=128)

    assert changed == 0
    assert updated.alpha_mask == result.alpha_mask
>>>>>>> theirs
=======
    updated, changed = remove_exterior_outline(result, pixel_perfect=False, brightness_threshold=999)

    assert changed == 1
    assert updated.alpha_mask == (
        (False, False, False),
        (False, False, False),
        (False, False, False),
    )
>>>>>>> theirs


def test_undo_palette_application_restores_previous_preview_state() -> None:
    downsampled = downsample_image(_sample_grid(), PipelineConfig(pixel_width=2))
    structured_palette = generate_structured_palette(
        downsampled.prepared_input.reduced_labels,
        key_colors=[0xFF0000, 0x0000FF],
        generated_shades=2,
    ).palette
    reduced = reduce_palette_image(
        downsampled.prepared_input,
        PipelineConfig(pixel_width=2, key_colors=(0xFF0000, 0x0000FF), generated_shades=2),
        structured_palette=structured_palette,
    )
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.palette_result = reduced
    gui.downsample_display_image = Image.new("RGBA", (reduced.width, reduced.height), (9, 8, 7, 255))
    gui.palette_display_image = Image.new("RGBA", (reduced.width, reduced.height), (1, 2, 3, 255))
    gui.image_state = "processed_current"
    gui.last_successful_process_snapshot = {"stage": "palette"}
    gui.active_palette = None
    gui.active_palette_source = ""
    gui.active_palette_path = None
    gui.advanced_palette_preview = None
    gui.transparent_colors = {0x112233}
    gui.session = SimpleNamespace(current=PreviewSettings())
    gui.quick_compare_active = True
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))
    gui._update_palette_strip = lambda: None
    gui._update_image_info = lambda: None
    gui.redraw_canvas = lambda: None
    gui._schedule_state_persist = lambda: None
    gui._refresh_action_states = lambda: None
    gui._sync_controls_from_settings = lambda _settings: None
    gui._clear_palette_undo_state = lambda: setattr(gui, "_palette_undo_state", None)
    gui._palette_undo_state = PaletteUndoState(
        palette_result=None,
        downsample_display_image=None,
        palette_display_image=None,
        image_state="processed_stale",
        last_successful_process_snapshot={"stage": "downsample"},
        active_palette=None,
        active_palette_source="",
        active_palette_path=None,
        advanced_palette_preview=None,
        transparent_colors=(),
        settings=PreviewSettings(),
    )

    assert PixelFixGui._undo_palette_application(gui) is True
    assert gui.palette_result is None
    assert gui.downsample_display_image is None
    assert gui.palette_display_image is None
    assert gui.image_state == "processed_stale"
    assert gui.last_successful_process_snapshot == {"stage": "downsample"}
    assert gui.transparent_colors == set()
    assert gui.quick_compare_active is False
    assert gui.process_status_var.value == "Reverted the last image change."
    assert gui._palette_undo_state is None


def test_add_key_color_ignores_duplicates() -> None:
    messages: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.key_colors = []
    gui.advanced_palette_preview = object()
    gui.process_status_var = SimpleNamespace(set=lambda value: messages.append(value))
    gui._update_key_color_list = lambda: None
    gui._mark_output_stale = lambda message=None: messages.append(message or "")
    gui._update_palette_strip = lambda: None
    gui._refresh_action_states = lambda: None

    PixelFixGui._add_key_color(gui, 0x112233)
    PixelFixGui._add_key_color(gui, 0x112233)

    assert gui.key_colors == [0x112233]
    assert "already in the key-colour list" in messages[-1]


def test_add_key_color_allows_twenty_four_and_blocks_twenty_five() -> None:
    messages: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.key_colors = [index for index in range(24)]
    gui.advanced_palette_preview = object()
    gui.process_status_var = SimpleNamespace(set=lambda value: messages.append(value))
    gui._update_key_color_list = lambda: None
    gui._mark_output_stale = lambda message=None: messages.append(message or "")
    gui._update_palette_strip = lambda: None
    gui._refresh_action_states = lambda: None

    PixelFixGui._add_key_color(gui, 0x123456)

    assert len(gui.key_colors) == 24
    assert messages[-1] == "You can only pick up to 24 key colours."


def test_update_key_color_list_refreshes_count_label() -> None:
    entries: list[str] = []

    class ListboxStub:
        def curselection(self):
            return ()

        def delete(self, *_args):
            entries.clear()

        def insert(self, _index, value):
            entries.append(value)

        def itemconfig(self, *_args, **_kwargs):
            return None

        def selection_set(self, *_args):
            return None

    gui = PixelFixGui.__new__(PixelFixGui)
    gui.key_colors = [0x111111, 0x222222, 0x333333]
    gui.key_colors_label_var = SimpleNamespace(value="", set=lambda value: setattr(gui.key_colors_label_var, "value", value))
    gui.key_color_listbox = ListboxStub()

    PixelFixGui._update_key_color_list(gui)

    assert gui.key_colors_label_var.value == "Key colours (3)"
    assert entries == ["#111111", "#222222", "#333333"]


def test_get_display_palette_reuses_cached_process_labels_for_neutral_adjustments() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.active_palette = None
    gui.active_palette_source = ""
    gui.active_palette_path = None
    gui.advanced_palette_preview = None
    gui.palette_result = None
    gui.downsample_result = ProcessResult(
        grid=[],
        width=0,
        height=0,
        stats=ProcessStats(
            stage="downsample",
            pixel_width=1,
            resize_method="nearest",
            input_size=(0, 0),
            output_size=(0, 0),
            initial_color_count=0,
            color_count=2,
            elapsed_seconds=0.0,
        ),
        prepared_input=PipelinePreparedResult(
            reduced_labels=[],
            pixel_width=1,
            grid_method="manual",
            input_size=(0, 0),
            initial_color_count=0,
        ),
        display_palette_labels=(0x112233, 0x445566),
    )
    gui.session = SimpleNamespace(current=PreviewSettings())
    gui._current_adjusted_structured_palette = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected palette rebuild"))

    palette, source = PixelFixGui._get_display_palette(gui)

    assert palette == [0x112233, 0x445566]
    assert source == "Downsample"


def test_current_adjusted_structured_palette_reuses_cached_result(monkeypatch) -> None:
    calls = 0
    original = app_module.adjust_structured_palette

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(app_module, "adjust_structured_palette", counted)

    gui = PixelFixGui.__new__(PixelFixGui)
    gui.active_palette = [0x112233, 0x445566]
    gui.active_palette_source = "Loaded"
    gui.active_palette_path = None
    gui.advanced_palette_preview = None
    gui.palette_result = None
    gui.downsample_result = None
    gui.session = SimpleNamespace(current=PreviewSettings(palette_brightness=10))
    gui.workspace = ColorWorkspace()
    gui._adjusted_palette_cache_key = None
    gui._adjusted_palette_cache = None

    first = PixelFixGui._current_adjusted_structured_palette(gui)
    second = PixelFixGui._current_adjusted_structured_palette(gui)

    assert first is not second
    assert first is not None
    assert second is not None
    assert first.labels() == second.labels()
    assert calls == 1


def test_current_adjusted_structured_palette_only_adjusts_selected_swatches() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.active_palette = [0x336699, 0x88AACC, 0xCC8844]
    gui.active_palette_source = "Loaded"
    gui.active_palette_path = None
    gui.advanced_palette_preview = None
    gui.palette_result = None
    gui.downsample_result = None
    gui.session = SimpleNamespace(current=PreviewSettings(palette_brightness=20, palette_hue=20, palette_saturation=140))
    gui.workspace = ColorWorkspace()
    gui._palette_selection_indices = {1}
    gui._adjusted_palette_cache_key = None
    gui._adjusted_palette_cache = None

    adjusted = PixelFixGui._current_adjusted_structured_palette(gui)

    assert adjusted is not None
    labels = adjusted.labels()
    assert labels[0] == gui.active_palette[0]
    assert labels[1] != gui.active_palette[1]
    assert labels[2] == gui.active_palette[2]


def test_remove_selected_seed_removes_multiple_key_colours() -> None:
    messages: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.key_colors = [0x111111, 0x222222, 0x333333]
    gui.advanced_palette_preview = object()
    gui.key_color_listbox = SimpleNamespace(curselection=lambda: (0, 2))
    gui.process_status_var = SimpleNamespace(set=lambda value: messages.append(value))
    gui._update_key_color_list = lambda: None
    gui._mark_output_stale = lambda message=None: messages.append(message or "")
    gui._update_palette_strip = lambda: None
    gui._refresh_action_states = lambda: None

    PixelFixGui._remove_selected_seed(gui)

    assert gui.key_colors == [0x222222]
    assert messages[-1] == "Key colours changed. Click Generate Ramps to rebuild the palette."


def test_auto_detect_key_colors_replaces_current_list(monkeypatch) -> None:
    messages: list[str] = []
    requested: dict[str, int] = {}
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.original_display_image = Image.new("RGBA", (2, 2), (1, 2, 3, 255))
    gui.active_palette = None
    gui.image_state = "loaded_original"
    gui.key_color_pick_mode = True
    gui.key_colors = [0xABCDEF]
    gui.advanced_palette_preview = object()
    gui.session = SimpleNamespace(current=PreviewSettings(auto_detect_count=5))
    gui.workspace = object()
    gui.root = SimpleNamespace(update_idletasks=lambda: None)
    gui.key_color_listbox = SimpleNamespace(selection_clear=lambda *_args: None)
    gui.process_status_var = SimpleNamespace(set=lambda value: messages.append(value))
    gui._update_key_color_list = lambda: None
    gui._mark_output_stale = lambda message=None: messages.append(message or "")
    gui._update_palette_strip = lambda: None
    gui._refresh_action_states = lambda: None

    def fake_detect(*args, **kwargs):
        requested["max_colors"] = kwargs["max_colors"]
        return [0x112233, 0x445566]

    monkeypatch.setattr(app_module, "detect_key_colors_from_image", fake_detect)

    PixelFixGui._auto_detect_key_colors(gui)

    assert requested["max_colors"] == 5
    assert gui.key_color_pick_mode is False
    assert gui.key_colors == [0x112233, 0x445566]
    assert gui.advanced_palette_preview is None
    assert messages[-1] == "Detected 2 key colours. Click Generate Ramps to rebuild the palette."


def test_auto_detect_key_colors_keeps_existing_list_when_none_found(monkeypatch) -> None:
    messages: list[str] = []
    existing_preview = object()
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.original_display_image = Image.new("RGBA", (2, 2), (1, 2, 3, 255))
    gui.active_palette = None
    gui.image_state = "loaded_original"
    gui.key_color_pick_mode = False
    gui.key_colors = [0xABCDEF]
    gui.advanced_palette_preview = existing_preview
    gui.session = SimpleNamespace(current=PreviewSettings(auto_detect_count=3))
    gui.workspace = object()
    gui.root = SimpleNamespace(update_idletasks=lambda: None)
    gui.key_color_listbox = SimpleNamespace(selection_clear=lambda *_args: None)
    gui.process_status_var = SimpleNamespace(set=lambda value: messages.append(value))
    gui._update_key_color_list = lambda: None
    gui._mark_output_stale = lambda message=None: messages.append(message or "")
    gui._update_palette_strip = lambda: None
    gui._refresh_action_states = lambda: None
    monkeypatch.setattr(app_module, "detect_key_colors_from_image", lambda *args, **kwargs: [])

    PixelFixGui._auto_detect_key_colors(gui)

    assert gui.key_colors == [0xABCDEF]
    assert gui.advanced_palette_preview is existing_preview
    assert messages[-1] == "No visible colours were found for auto-detection."


def test_auto_detect_count_change_does_not_mark_output_stale() -> None:
    messages: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.process_status_var = SimpleNamespace(set=lambda value: messages.append(value))
    gui._clear_palette_undo_state = lambda: messages.append("clear")
    gui._mark_output_stale = lambda message=None: messages.append(f"stale:{message}")
    gui._update_key_color_list = lambda: messages.append("list")
    gui._update_scale_info = lambda: messages.append("scale")
    gui._update_palette_strip = lambda: messages.append("palette")
    gui.redraw_canvas = lambda: messages.append("redraw")
    gui._schedule_state_persist = lambda: messages.append("persist")
    gui._refresh_action_states = lambda: messages.append("refresh")

    PixelFixGui._handle_settings_transition(
        gui,
        PreviewSettings(auto_detect_count=12),
        PreviewSettings(auto_detect_count=6),
    )

    assert messages == ["Auto-detect count set to 6.", "persist", "refresh"]


def test_palette_reduction_settings_change_does_not_mark_output_stale() -> None:
    messages: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.process_status_var = SimpleNamespace(set=lambda value: messages.append(value))
    gui._clear_palette_undo_state = lambda: messages.append("clear")
    gui._mark_output_stale = lambda message=None: messages.append(f"stale:{message}")
    gui._update_key_color_list = lambda: messages.append("list")
    gui._update_scale_info = lambda: messages.append("scale")
    gui._update_palette_strip = lambda: messages.append("palette")
    gui.redraw_canvas = lambda: messages.append("redraw")
    gui._schedule_state_persist = lambda: messages.append("persist")
    gui._refresh_action_states = lambda: messages.append("refresh")

    PixelFixGui._handle_settings_transition(
        gui,
        PreviewSettings(palette_reduction_colors=16, quantizer="median-cut"),
        PreviewSettings(palette_reduction_colors=24, quantizer="kmeans"),
    )

    assert messages == ["Palette reduction settings changed. Click Generate Reduced Palette to rebuild the palette.", "persist", "refresh"]


def test_downsample_setting_change_marks_downsample_stale_and_clears_cache() -> None:
    messages: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.prepared_input_cache = object()
    gui.prepared_input_cache_key = ("cached",)
    gui.process_status_var = SimpleNamespace(set=lambda value: messages.append(value))
    gui._clear_palette_undo_state = lambda: messages.append("clear")
    gui._mark_output_stale = lambda message=None: messages.append(f"stale:{message}")
    gui._update_key_color_list = lambda: messages.append("list")
    gui._update_palette_adjustment_labels = lambda: messages.append("adjust")
    gui._update_scale_info = lambda: messages.append("scale")
    gui._update_palette_strip = lambda: messages.append("palette")
    gui.redraw_canvas = lambda: messages.append("redraw")
    gui._schedule_state_persist = lambda: messages.append("persist")
    gui._refresh_action_states = lambda: messages.append("refresh")

    PixelFixGui._handle_settings_transition(
        gui,
        PreviewSettings(),
        PreviewSettings(pixel_width=4),
    )

    assert gui.prepared_input_cache is None
    assert gui.prepared_input_cache_key is None
    assert messages == [
        "clear",
        "stale:Downsample settings changed. Click Downsample to update the preview.",
        "list",
        "adjust",
        "scale",
        "palette",
        "redraw",
        "persist",
        "refresh",
    ]


def test_prepare_cache_key_includes_downsample_settings() -> None:
    assert PixelFixGui._build_prepare_cache_key(PreviewSettings()) != PixelFixGui._build_prepare_cache_key(
        PreviewSettings(pixel_width=4)
    )
    assert PixelFixGui._build_prepare_cache_key(PreviewSettings()) != PixelFixGui._build_prepare_cache_key(
        PreviewSettings(downsample_mode="rotsprite")
    )


def test_generate_override_palette_uses_downsampled_labels_and_marks_stale(monkeypatch) -> None:
    captured: dict[str, object] = {}
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.image_state = "processed_current"
    gui.prepared_input_cache = SimpleNamespace(
        reduced_labels=[
            [0x111111, 0x222222],
            [0x333333, 0x444444],
        ]
    )
    gui.active_palette = None
    gui.advanced_palette_preview = SimpleNamespace(palette_size=lambda: 6)
    gui.key_colors = []
    gui.session = SimpleNamespace(current=PreviewSettings(palette_reduction_colors=24, quantizer="kmeans", generated_shades=4))
    gui._apply_active_palette = lambda palette, source, path_value, *, message, mark_stale=True: captured.update(
        {
            "palette": palette,
            "source": source,
            "path_value": path_value,
            "message": message,
            "mark_stale": mark_stale,
        }
    )

    def fake_generate(labels, colors, method):
        captured["labels"] = labels
        captured["colors"] = colors
        captured["method"] = method
        return [0xAAAAAA, 0xBBBBBB, 0xCCCCCC]

    monkeypatch.setattr(app_module, "generate_override_palette", fake_generate)

    PixelFixGui._generate_override_palette_from_settings(gui, gui.session.current)

    assert captured["labels"] == gui.prepared_input_cache.reduced_labels
    assert captured["colors"] == 4
    assert captured["method"] == "kmeans"
    assert captured["palette"] == [0xAAAAAA, 0xBBBBBB, 0xCCCCCC]
    assert captured["source"] == "Generated Override: K-Means Clustering"
    assert captured["path_value"] is None
    assert captured["mark_stale"] is True
    assert captured["message"] == "Generated a 3-colour override palette with K-Means Clustering. Click Apply Palette to use it."


def test_generate_override_palette_requires_downsample(monkeypatch) -> None:
    messages: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.image_state = "loaded_original"
    gui.prepared_input_cache = None
    gui.session = SimpleNamespace(current=PreviewSettings())
    gui.process_status_var = SimpleNamespace(set=lambda value: messages.append(value))

    monkeypatch.setattr(app_module, "generate_override_palette", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not run")))

    PixelFixGui._generate_override_palette_from_settings(gui, gui.session.current)

    assert messages == ["Downsample the image before generating an override palette."]


def test_load_palette_file_browses_for_gpl_files(monkeypatch) -> None:
    captured: dict[str, object] = {}
    gui = PixelFixGui.__new__(PixelFixGui)
    gui._resolve_palette_path = lambda value: str(value)
    gui._apply_active_palette = lambda palette, source, path_value, *, message, mark_stale=True: captured.update(
        {
            "palette": palette,
            "source": source,
            "path_value": path_value,
            "message": message,
            "mark_stale": mark_stale,
        }
    )

    def fake_askopenfilename(**kwargs):
        captured["filetypes"] = kwargs["filetypes"]
        return "example.gpl"

    monkeypatch.setattr(app_module.filedialog, "askopenfilename", fake_askopenfilename)
    monkeypatch.setattr(app_module, "load_palette", lambda path: [0x112233, 0x445566])

    PixelFixGui.load_palette_file(gui)

    assert captured["filetypes"][0] == ("GIMP Palette", "*.gpl")
    assert captured["palette"] == [0x112233, 0x445566]
    assert captured["source"] == "Loaded: example.gpl"
    assert captured["path_value"] == "example.gpl"
    assert captured["message"] == "Loaded palette from example.gpl. Click Apply Palette to update the preview."
    assert captured["mark_stale"] is True


def test_save_palette_file_uses_gpl_dialog(monkeypatch) -> None:
    captured: dict[str, object] = {}
    gui = PixelFixGui.__new__(PixelFixGui)
    gui._get_display_palette = lambda: ([0x112233, 0x445566], "Generated")
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))

    def fake_asksaveasfilename(**kwargs):
        captured["defaultextension"] = kwargs["defaultextension"]
        captured["filetypes"] = kwargs["filetypes"]
        return "saved-palette.gpl"

    monkeypatch.setattr(app_module.filedialog, "asksaveasfilename", fake_asksaveasfilename)
    monkeypatch.setattr(app_module, "save_palette", lambda path, palette: captured.update({"path": path, "palette": palette}))

    PixelFixGui.save_palette_file(gui)

    assert captured["defaultextension"] == ".gpl"
    assert captured["filetypes"] == [("GIMP Palette", "*.gpl")]
    assert str(captured["path"]).endswith("saved-palette.gpl")
    assert captured["palette"] == [0x112233, 0x445566]
    assert gui.process_status_var.value == "Saved palette to saved-palette.gpl"


def test_open_image_path_clears_palette_and_transparency_state(monkeypatch, tmp_path) -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.active_palette = [0x112233]
    gui.active_palette_source = "Loaded"
    gui.active_palette_path = "example.gpl"
    gui.transparent_colors = {0x112233}
    gui._palette_selection_indices = {0}
    gui._displayed_palette = [0x112233]
    gui.key_colors = [0x445566]
    gui.advanced_palette_preview = object()
    gui.key_color_pick_mode = True
    gui.palette_add_pick_mode = True
    gui.transparency_pick_mode = True
    gui.downsample_result = object()
    gui.palette_result = object()
    gui.downsample_display_image = object()
    gui.palette_display_image = object()
    gui.comparison_original_image = object()
    gui._comparison_original_key = ("old",)
    gui.prepared_input_cache = object()
    gui.prepared_input_cache_key = ("old",)
    gui.quick_compare_active = True
    gui.pan_x = 5
    gui.pan_y = 7
    gui.image_state = "processed_current"
    gui.root = SimpleNamespace(update_idletasks=lambda: None)
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))
    gui._record_recent_file = lambda _path: None
    gui._set_view = lambda _value: None
    gui.zoom_fit = lambda: None
    gui._update_scale_info = lambda: None
    gui._update_key_color_list = lambda: None
    gui._update_palette_strip = lambda: None
    gui.redraw_canvas = lambda: None
    gui._refresh_action_states = lambda: None
    gui._clear_palette_undo_state = lambda: None

    monkeypatch.setattr(app_module, "load_png_rgba_image", lambda _path: Image.new("RGBA", (4, 4), (1, 2, 3, 255)))

    image_path = tmp_path / "sprite.png"
    image_path.write_text("", encoding="utf-8")

    PixelFixGui._open_image_path(gui, image_path)

    assert gui.active_palette is None
    assert gui.active_palette_source == ""
    assert gui.active_palette_path is None
    assert gui.transparent_colors == set()
    assert gui.downsample_result is None
    assert gui.palette_result is None
    assert gui.key_colors == []
    assert gui.key_color_pick_mode is False
    assert gui.palette_add_pick_mode is False
    assert gui.transparency_pick_mode is False
    assert gui.image_state == "loaded_original"
    assert gui.original_display_image is not None


def test_canvas_motion_updates_live_pick_preview() -> None:
    cursor_updates: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.dragging = False
    gui.key_color_pick_mode = True
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui.pick_preview_var = SimpleNamespace(value="", set=lambda value: setattr(gui.pick_preview_var, "value", value))
    gui.pick_preview_frame = PickerPreviewFrameStub()
    gui.pick_preview_swatch = PickerPreviewSwatchStub()
    gui.canvas = SimpleNamespace(configure=lambda **kwargs: cursor_updates.append(kwargs["cursor"]))
    gui._sample_label_from_preview = lambda x, y, *, view: 0x336699 if (x, y, view) == (12, 18, "original") else None

    PixelFixGui._on_canvas_motion(gui, SimpleNamespace(x=12, y=18))

    assert cursor_updates == ["crosshair"]
    assert gui.pick_preview_var.value == "#336699"
    assert gui.pick_preview_frame.manager == "pack"
    assert gui.pick_preview_swatch.config["bg"] == "#336699"


def test_canvas_leave_clears_live_pick_preview() -> None:
    cursor_updates: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.dragging = False
    gui.key_color_pick_mode = True
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui.pick_preview_var = SimpleNamespace(value="", set=lambda value: setattr(gui.pick_preview_var, "value", value))
    gui.pick_preview_frame = PickerPreviewFrameStub()
    gui.pick_preview_swatch = PickerPreviewSwatchStub()
    gui.canvas = SimpleNamespace(configure=lambda **kwargs: cursor_updates.append(kwargs["cursor"]))
    gui._sample_label_from_preview = lambda _x, _y, *, view: 0x224466 if view == "original" else None

    PixelFixGui._on_canvas_motion(gui, SimpleNamespace(x=4, y=6))
    PixelFixGui._on_canvas_leave(gui, SimpleNamespace())

    assert gui.pick_preview_var.value == ""
    assert gui.pick_preview_frame.manager == ""
    assert cursor_updates == ["crosshair", ""]


def test_persist_state_omits_palette_adjustment_values(monkeypatch) -> None:
    captured: dict[str, object] = {}
    gui = PixelFixGui.__new__(PixelFixGui)
    gui._persist_after_id = None
    gui.session = SimpleNamespace(
        current=PreviewSettings(
            palette_brightness=15,
            palette_contrast=140,
            palette_hue=-20,
            palette_saturation=160,
        )
    )
    gui.last_output_path = "out.png"
    gui.last_successful_process_snapshot = {"stage": "palette"}
    gui.zoom = 125
    gui.selection_threshold_var = SimpleNamespace(get=lambda: 30)
    gui.checkerboard_var = SimpleNamespace(get=lambda: True)
<<<<<<< ours
=======
    gui.outline_pixel_perfect_var = SimpleNamespace(get=lambda: False)
    gui.outline_brightness_threshold_enabled_var = SimpleNamespace(get=lambda: True)
    gui.outline_brightness_threshold_var = SimpleNamespace(get=lambda: 64, set=lambda _value: None)
>>>>>>> theirs
    gui.view_var = SimpleNamespace(get=lambda: "processed")
    gui.recent_files = ["example.png"]

    monkeypatch.setattr(app_module, "save_app_state", lambda data: captured.update(data))

    PixelFixGui._persist_state(gui)

    settings = captured["settings"]
    assert "palette_brightness" not in settings
    assert "palette_contrast" not in settings
    assert "palette_hue" not in settings
    assert "palette_saturation" not in settings
    assert captured["selection_threshold"] == 30
<<<<<<< ours
=======
    assert captured["outline_pixel_perfect"] is False
    assert captured["outline_brightness_threshold_enabled"] is True
    assert captured["outline_brightness_threshold"] == 64
>>>>>>> theirs


def test_add_colour_to_current_palette_materializes_display_palette() -> None:
    captured: dict[str, object] = {}
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.process_status_var = SimpleNamespace(set=lambda value: captured.setdefault("status", value))
    gui._get_display_palette = lambda: ([0x112233], "Generated")
    gui._apply_palette_edit = lambda palette, message: captured.update({"palette": palette, "message": message})

    added = PixelFixGui._add_colour_to_current_palette(gui, 0x445566)

    assert added is True
    assert captured["palette"] == [0x112233, 0x445566]
    assert captured["message"] == "Added #445566 to the current palette. Click Apply Palette to update the preview."


def test_remove_selected_palette_colours_uses_selected_swatches() -> None:
    captured: dict[str, object] = {}
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.process_status_var = SimpleNamespace(set=lambda value: captured.setdefault("status", value))
    gui._get_display_palette = lambda: ([0x111111, 0x222222, 0x333333], "Generated")
    gui._apply_palette_edit = lambda palette, message: captured.update({"palette": palette, "message": message})
    gui._palette_selection_indices = {0, 2}

    PixelFixGui._remove_selected_palette_colors(gui)

    assert captured["palette"] == [0x222222]
    assert captured["message"] == "Removed 2 palette colours. Click Apply Palette to update the preview."


def test_select_all_palette_colors_selects_displayed_palette() -> None:
    messages: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui._displayed_palette = [0x111111, 0x222222, 0x333333]
    gui._palette_selection_indices = set()
    gui._palette_selection_anchor_index = None
    gui.process_status_var = SimpleNamespace(set=lambda value: messages.append(value))
    gui._update_palette_strip = lambda: messages.append("palette")
    gui._refresh_action_states = lambda: messages.append("refresh")

    PixelFixGui._select_all_palette_colors(gui)

    assert gui._palette_selection_indices == {0, 1, 2}
    assert gui._palette_selection_anchor_index == 0
    assert messages == ["palette", "refresh", "Selected 3 palette colours."]


def test_palette_canvas_shift_click_selects_range() -> None:
    updates: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui._displayed_palette = [0x111111, 0x222222, 0x333333, 0x444444]
    gui._palette_hit_regions = [
        (0, 0, 9, 9),
        (10, 0, 19, 9),
        (20, 0, 29, 9),
        (30, 0, 39, 9),
    ]
    gui._palette_selection_indices = {1}
    gui._palette_selection_anchor_index = 1
    gui._update_palette_strip = lambda: updates.append("palette")
    gui._refresh_action_states = lambda: updates.append("refresh")

    PixelFixGui._on_palette_canvas_click(gui, SimpleNamespace(x=35, y=5, state=0x0001))

    assert gui._palette_selection_indices == {1, 2, 3}
    assert gui._palette_selection_anchor_index == 1
    assert updates == ["palette", "refresh"]


def test_palette_canvas_ctrl_click_toggles_single_swatch_on_release() -> None:
    updates: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui._displayed_palette = [0x111111, 0x222222, 0x333333]
    gui._palette_hit_regions = [
        (0, 0, 9, 9),
        (10, 0, 19, 9),
        (20, 0, 29, 9),
    ]
    gui._palette_selection_indices = {1}
    gui._palette_selection_anchor_index = 1
    gui._update_palette_strip = lambda: updates.append("palette")
    gui._refresh_action_states = lambda: updates.append("refresh")

    PixelFixGui._on_palette_canvas_click(gui, SimpleNamespace(x=25, y=5, state=0x0004))
    PixelFixGui._on_palette_canvas_release(gui, SimpleNamespace())

    assert gui._palette_selection_indices == {1, 2}
    assert gui._palette_selection_anchor_index == 2
    assert updates == ["palette", "refresh"]


def test_palette_canvas_ctrl_drag_selects_hovered_swatches_until_release() -> None:
    updates: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui._displayed_palette = [0x111111, 0x222222, 0x333333, 0x444444]
    gui._palette_hit_regions = [
        (0, 0, 9, 9),
        (10, 0, 19, 9),
        (20, 0, 29, 9),
        (30, 0, 39, 9),
    ]
    gui._palette_selection_indices = {0}
    gui._palette_selection_anchor_index = 0
    gui._update_palette_strip = lambda: updates.append("palette")
    gui._refresh_action_states = lambda: updates.append("refresh")

    PixelFixGui._on_palette_canvas_click(gui, SimpleNamespace(x=15, y=5, state=0x0004))
    PixelFixGui._on_palette_canvas_drag(gui, SimpleNamespace(x=25, y=5, state=0x0004))
    PixelFixGui._on_palette_canvas_drag(gui, SimpleNamespace(x=35, y=5, state=0x0004))
    PixelFixGui._on_palette_canvas_release(gui, SimpleNamespace())

    assert gui._palette_selection_indices == {0, 1, 2, 3}
    assert gui._palette_selection_anchor_index == 1
    assert updates == ["palette", "refresh", "palette", "refresh"]


def test_palette_canvas_ctrl_drag_stops_when_ctrl_is_released() -> None:
    updates: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui._displayed_palette = [0x111111, 0x222222, 0x333333, 0x444444]
    gui._palette_hit_regions = [
        (0, 0, 9, 9),
        (10, 0, 19, 9),
        (20, 0, 29, 9),
        (30, 0, 39, 9),
    ]
    gui._palette_selection_indices = set()
    gui._palette_selection_anchor_index = None
    gui._update_palette_strip = lambda: updates.append("palette")
    gui._refresh_action_states = lambda: updates.append("refresh")

    PixelFixGui._on_palette_canvas_click(gui, SimpleNamespace(x=15, y=5, state=0x0004))
    PixelFixGui._on_palette_canvas_drag(gui, SimpleNamespace(x=25, y=5, state=0x0004))
    PixelFixGui._on_palette_canvas_drag(gui, SimpleNamespace(x=35, y=5, state=0x0000))
    PixelFixGui._on_palette_canvas_release(gui, SimpleNamespace())

    assert gui._palette_selection_indices == {1, 2}
    assert gui._palette_selection_anchor_index == 1
    assert updates == ["palette", "refresh"]


def test_sort_current_palette_applies_sorted_override_and_tracks_reset_source() -> None:
    captured: dict[str, object] = {}
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.workspace = ColorWorkspace()
    gui.active_palette = None
    gui.active_palette_source = ""
    gui.active_palette_path = None
    gui.advanced_palette_preview = generate_structured_palette(
        [],
        key_colors=[0x00FF00, 0x777777, 0xFF0000],
        generated_shades=1,
    ).palette
    gui.palette_result = None
    gui.downsample_result = None
    gui._palette_sort_reset_labels = None
    gui._palette_sort_reset_source = None
    gui._palette_sort_reset_path = None
    gui._get_display_palette = lambda: ([0x00FF00, 0x777777, 0xFF0000], "Generated")
    gui._palette_sort_source = lambda: ([0x00FF00, 0x777777, 0xFF0000], "Generated", None)
    gui._apply_active_palette = lambda palette, source, path_value, *, message, mark_stale=True, capture_undo=False: captured.update(
        {
            "palette": palette,
            "source": source,
            "path_value": path_value,
            "message": message,
            "mark_stale": mark_stale,
            "capture_undo": capture_undo,
        }
    )

    PixelFixGui.sort_current_palette(gui, PALETTE_SORT_HUE)

    assert captured["palette"] == [0x777777, 0xFF0000, 0x00FF00]
    assert captured["source"] == "Sorted: Hue (Red Wheel)"
    assert captured["path_value"] is None
    assert captured["capture_undo"] is True
    assert captured["message"] == "Sorted current palette by Hue (Red Wheel). Click Apply Palette to update the preview."
    assert gui._palette_sort_reset_labels == [0x00FF00, 0x777777, 0xFF0000]
    assert gui._palette_sort_reset_source == "Generated"


def test_reset_palette_sort_order_restores_saved_source_order() -> None:
    captured: dict[str, object] = {}
    gui = PixelFixGui.__new__(PixelFixGui)
    gui._palette_sort_reset_labels = [0x112233, 0x445566]
    gui._palette_sort_reset_source = "Built-in: Example / DB16"
    gui._palette_sort_reset_path = "palette.gpl"
    gui._apply_active_palette = lambda palette, source, path_value, *, message, mark_stale=True, capture_undo=False: captured.update(
        {
            "palette": palette,
            "source": source,
            "path_value": path_value,
            "message": message,
            "capture_undo": capture_undo,
        }
    )

    PixelFixGui.reset_palette_sort_order(gui)

    assert captured["palette"] == [0x112233, 0x445566]
    assert captured["source"] == "Built-in: Example / DB16"
    assert captured["path_value"] == "palette.gpl"
    assert captured["capture_undo"] is True


def test_sort_current_palette_undo_restores_previous_palette_state() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.workspace = ColorWorkspace()
    gui.active_palette = [0x00FF00, 0x777777, 0xFF0000]
    gui.active_palette_source = "Built-in: Example / DB16"
    gui.active_palette_path = "palette.gpl"
    gui.advanced_palette_preview = None
    gui.palette_result = None
    gui.downsample_result = None
    gui.downsample_display_image = None
    gui.palette_display_image = None
    gui.image_state = "processed_stale"
    gui.last_successful_process_snapshot = {"stage": "palette"}
    gui.transparent_colors = set()
    gui.session = SimpleNamespace(current=PreviewSettings())
    gui.quick_compare_active = False
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))
    gui._update_palette_strip = lambda: None
    gui._update_image_info = lambda: None
    gui.redraw_canvas = lambda: None
    gui._schedule_state_persist = lambda: None
    gui._refresh_action_states = lambda: None
    gui._sync_controls_from_settings = lambda _settings: None
    gui._persist_after_id = None
    gui._menu_items = {}
    gui._palette_sort_reset_labels = None
    gui._palette_sort_reset_source = None
    gui._palette_sort_reset_path = None

    PixelFixGui.sort_current_palette(gui, PALETTE_SORT_LIGHTNESS)

    assert gui.active_palette == [0x777777, 0xFF0000, 0x00FF00]
    assert gui.active_palette_source == "Sorted: Lightness (Dark -> Light)"
    assert PixelFixGui._undo_palette_application(gui) is True
    assert gui.active_palette == [0x00FF00, 0x777777, 0xFF0000]
    assert gui.active_palette_source == "Built-in: Example / DB16"


def test_select_current_palette_replaces_selection_using_displayed_palette() -> None:
    updates: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.workspace = ColorWorkspace()
    gui.selection_threshold_var = SimpleNamespace(get=lambda: 30)
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))
    gui._get_display_palette = lambda: ([0xEEEEEE, 0x222222, 0x888888, 0x444444], "Generated (Adjusted)")
    gui._palette_selection_indices = {0}
    gui._palette_selection_anchor_index = 0
    gui._reset_palette_ctrl_drag_state = lambda: updates.append("reset")
    gui._update_palette_strip = lambda: updates.append("palette")
    gui._refresh_action_states = lambda: updates.append("refresh")

    PixelFixGui.select_current_palette(gui, PALETTE_SELECT_LIGHTNESS_DARK)

    assert gui._palette_selection_indices == {1, 3}
    assert gui._palette_selection_anchor_index == 1
    assert gui.process_status_var.value == "Selected 2 palette colours by Lightness (Dark) at 30%."
    assert updates == ["reset", "palette", "refresh"]




def test_select_current_palette_similarity_mode_updates_selection_and_status_text() -> None:
    updates: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.workspace = ColorWorkspace()
    gui.selection_threshold_var = SimpleNamespace(get=lambda: 50)
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))
    gui._get_display_palette = lambda: ([0x101010, 0x111111, 0x80FF00, 0x80FE00, 0xB040A0], "Generated")
    gui._palette_selection_indices = {4}
    gui._palette_selection_anchor_index = 4
    gui._reset_palette_ctrl_drag_state = lambda: updates.append("reset")
    gui._update_palette_strip = lambda: updates.append("palette")
    gui._refresh_action_states = lambda: updates.append("refresh")

    mode = _similarity_selection_mode()

    PixelFixGui.select_current_palette(gui, mode)

    assert gui._palette_selection_indices == {0, 1, 2}
    assert gui._palette_selection_anchor_index == 0
    assert gui.process_status_var.value == f"Selected 3 palette colours by {PALETTE_SELECT_LABELS[mode]} at 50%."
    assert updates == ["reset", "palette", "refresh"]

def test_selection_threshold_change_persists_without_marking_output_stale() -> None:
    messages: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.selection_threshold_var = SimpleNamespace(value=26, get=lambda: gui.selection_threshold_var.value, set=lambda value: setattr(gui.selection_threshold_var, "value", value))
    gui.process_status_var = SimpleNamespace(set=lambda value: messages.append(value))
    gui._schedule_state_persist = lambda: messages.append("persist")
    gui._refresh_action_states = lambda: messages.append("refresh")

    PixelFixGui._on_selection_threshold_changed(gui)

    assert gui.selection_threshold_var.value == 30
    assert messages == ["Selection threshold set to 30%.", "persist", "refresh"]


def test_refresh_action_states_enables_outline_buttons_with_processed_output_and_single_selection() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.image_state = "processed_current"
    gui.original_grid = _sample_grid()
    gui.prepared_input_cache = object()
    gui._palette_undo_state = None
    gui._palette_selection_indices = {0}
    gui._displayed_palette = [0x112233, 0x445566]
    gui.key_color_pick_mode = False
    gui.transparency_pick_mode = False
    gui.key_colors = []
    gui.session = SimpleNamespace(history=SimpleNamespace(can_undo=lambda: False))
    gui.key_color_listbox = SimpleNamespace(curselection=lambda: (), configure=lambda **_kwargs: None)
    gui.downsample_button = WidgetStub()
    gui.generate_ramps_button = WidgetStub()
    gui.generate_override_palette_button = WidgetStub()
    gui.reduce_palette_button = WidgetStub()
    gui.transparency_button = WidgetStub()
    gui.add_outline_button = WidgetStub()
    gui.remove_outline_button = WidgetStub()
    gui.zoom_in_button = WidgetStub()
    gui.zoom_out_button = WidgetStub()
    gui.pick_seed_button = WidgetStub()
    gui.auto_detect_button = WidgetStub()
    gui.remove_seed_button = WidgetStub()
    gui.clear_seeds_button = WidgetStub()
    gui.add_palette_color_button = WidgetStub()
    gui.select_all_palette_button = WidgetStub()
    gui.clear_palette_selection_button = WidgetStub()
    gui.remove_palette_color_button = WidgetStub()
    gui.pixel_width_spinbox = WidgetStub()
    gui.palette_reduction_spinbox = WidgetStub()
    gui.palette_adjustment_controls = []
    gui._menu_items = {
        "view": MenuStub(),
        "file": MenuStub(),
        "edit": MenuStub(),
        "palette": MenuStub(),
        "palette_add": MenuStub(),
        "preferences": MenuStub(),
    }
    gui._menu_bar = MenuStub()
    gui._refresh_primary_button_style = lambda _button: None
    gui._palette_is_override_mode = lambda: False
    gui._has_palette_source = lambda: True
    gui._current_output_result = lambda: object()

    PixelFixGui._refresh_action_states(gui)

    assert gui.add_outline_button.state == app_module.tk.NORMAL
    assert gui.remove_outline_button.state == app_module.tk.NORMAL


def test_add_transparent_region_updates_output_and_undo_restores() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.downsample_result = downsample_image(_sample_grid(), PipelineConfig(pixel_width=2))
    gui.palette_result = None
    gui.transparent_colors = set()
    gui.downsample_display_image = None
    gui.palette_display_image = None
    gui.image_state = "processed_current"
    gui.last_successful_process_snapshot = {"stage": "downsample"}
    gui.active_palette = None
    gui.active_palette_source = ""
    gui.active_palette_path = None
    gui.advanced_palette_preview = None
    gui.session = SimpleNamespace(current=PreviewSettings())
    gui.quick_compare_active = False
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))
    gui._update_palette_strip = lambda: None
    gui._update_image_info = lambda: None
    gui.redraw_canvas = lambda: None
    gui._schedule_state_persist = lambda: None
    gui._refresh_action_states = lambda: None
    gui._sync_controls_from_settings = lambda _settings: None
    PixelFixGui._refresh_output_display_images(gui)

    changed = PixelFixGui._add_transparent_region(gui, 0, 0, 0xFF0000)

    assert changed is True
    assert gui.downsample_display_image.getpixel((0, 0))[3] == 0
    assert gui.process_status_var.value == "Made 1 pixel of #FF0000 transparent. Press Undo to restore it."

    assert PixelFixGui._undo_palette_application(gui) is True
    assert gui.downsample_display_image.getpixel((0, 0))[3] == 255
    assert gui.transparent_colors == set()


def test_add_outline_from_selection_requires_exactly_one_palette_colour() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.downsample_result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000],
            [0x000000, 0x445566, 0x000000],
            [0x000000, 0x000000, 0x000000],
        ],
        stage="downsample",
    )
    gui.palette_result = None
    gui.image_state = "processed_current"
    gui._displayed_palette = [0x112233, 0x445566]
    gui._palette_selection_indices = {0, 1}
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))

    PixelFixGui._add_outline_from_selection(gui)

    assert gui.process_status_var.value == "Select exactly one palette colour to add an outline."


def test_add_outline_from_selection_updates_output_and_undo_restores() -> None:
    updates: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.downsample_result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000],
            [0x000000, 0x778899, 0x000000],
            [0x000000, 0x000000, 0x000000],
        ],
        stage="downsample",
    )
    gui.palette_result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000],
            [0x000000, 0x445566, 0x000000],
            [0x000000, 0x000000, 0x000000],
        ],
        stage="palette",
    )
    gui.transparent_colors = set()
    gui.downsample_display_image = None
    gui.palette_display_image = None
    gui.image_state = "processed_current"
    gui.last_successful_process_snapshot = {"stage": "downsample"}
    gui.active_palette = None
    gui.active_palette_source = ""
    gui.active_palette_path = None
    gui.advanced_palette_preview = None
    gui.session = SimpleNamespace(current=PreviewSettings())
    gui.quick_compare_active = False
    gui.view_var = SimpleNamespace(set=lambda _value: None)
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))
    gui._displayed_palette = [0x112233]
    gui._palette_selection_indices = {0}
    gui._palette_selection_anchor_index = 0
    gui._update_palette_strip = lambda: updates.append("palette")
    gui._update_image_info = lambda: updates.append("image")
    gui.redraw_canvas = lambda: updates.append("redraw")
    gui._schedule_state_persist = lambda: updates.append("persist")
    gui._refresh_action_states = lambda: updates.append("refresh")
    gui._sync_controls_from_settings = lambda _settings: None
    gui._clear_palette_undo_state = lambda: setattr(gui, "_palette_undo_state", None)
    PixelFixGui._refresh_output_display_images(gui)

    PixelFixGui._add_outline_from_selection(gui)

    assert gui.palette_display_image.getpixel((0, 0)) == (0x11, 0x22, 0x33, 255)
    assert gui.downsample_display_image.getpixel((0, 0))[3] == 0
    assert gui.process_status_var.value == "Added outline to 8 pixels with #112233. Press Undo to restore it."
    assert PixelFixGui._undo_palette_application(gui) is True
    assert gui.palette_display_image.getpixel((0, 0))[3] == 0


def test_remove_outline_updates_output_and_undo_restores() -> None:
    updates: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.downsample_result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x778899, 0x778899, 0x778899, 0x000000],
            [0x000000, 0x778899, 0x778899, 0x778899, 0x000000],
            [0x000000, 0x778899, 0x778899, 0x778899, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
        ],
        stage="downsample",
    )
    gui.palette_result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x445566, 0x445566, 0x445566, 0x000000],
            [0x000000, 0x445566, 0x445566, 0x445566, 0x000000],
            [0x000000, 0x445566, 0x445566, 0x445566, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
        ],
        stage="palette",
    )
    gui.transparent_colors = set()
    gui.downsample_display_image = None
    gui.palette_display_image = None
    gui.image_state = "processed_current"
    gui.last_successful_process_snapshot = {"stage": "downsample"}
    gui.active_palette = None
    gui.active_palette_source = ""
    gui.active_palette_path = None
    gui.advanced_palette_preview = None
    gui.session = SimpleNamespace(current=PreviewSettings())
    gui.quick_compare_active = False
    gui.view_var = SimpleNamespace(set=lambda _value: None)
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))
    gui._update_palette_strip = lambda: updates.append("palette")
    gui._update_image_info = lambda: updates.append("image")
    gui.redraw_canvas = lambda: updates.append("redraw")
    gui._schedule_state_persist = lambda: updates.append("persist")
    gui._refresh_action_states = lambda: updates.append("refresh")
    gui._sync_controls_from_settings = lambda _settings: None
    gui._clear_palette_undo_state = lambda: setattr(gui, "_palette_undo_state", None)
    PixelFixGui._refresh_output_display_images(gui)

    PixelFixGui._remove_outline(gui)

    assert gui.palette_display_image.getpixel((1, 1))[3] == 0
    assert gui.palette_display_image.getpixel((2, 2))[3] == 255
    assert gui.downsample_display_image.getpixel((1, 1))[3] == 255
    assert gui.process_status_var.value == "Removed 8 outline pixels. Press Undo to restore it."
    assert PixelFixGui._undo_palette_application(gui) is True
    assert gui.palette_display_image.getpixel((1, 1))[3] == 255


<<<<<<< ours
<<<<<<< ours
=======


def test_add_outline_from_selection_allows_adaptive_without_palette_selection() -> None:
=======


def test_add_outline_from_selection_adaptive_mode_works_with_zero_selection() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.downsample_result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000],
            [0x000000, 0x445566, 0x000000],
            [0x000000, 0x000000, 0x000000],
        ],
        stage="downsample",
    )
    gui.palette_result = None
    gui.transparent_colors = set()
    gui.downsample_display_image = None
    gui.palette_display_image = None
    gui.image_state = "processed_current"
    gui.last_successful_process_snapshot = {"stage": "downsample"}
    gui.active_palette = None
    gui.active_palette_source = ""
    gui.active_palette_path = None
    gui.advanced_palette_preview = None
    gui.session = SimpleNamespace(current=PreviewSettings())
    gui.quick_compare_active = False
    gui.view_var = SimpleNamespace(set=lambda _value: None)
    gui.outline_pixel_perfect_var = SimpleNamespace(get=lambda: True)
    gui.outline_adaptive_var = SimpleNamespace(get=lambda: True)
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))
    gui._displayed_palette = [0x112233]
    gui._palette_selection_indices = set()
    gui._palette_selection_anchor_index = None
    gui._update_palette_strip = lambda: None
    gui._update_image_info = lambda: None
    gui.redraw_canvas = lambda: None
    gui._schedule_state_persist = lambda: None
    gui._refresh_action_states = lambda: None
    gui._sync_controls_from_settings = lambda _settings: None
    gui._clear_palette_undo_state = lambda: setattr(gui, "_palette_undo_state", None)
    PixelFixGui._refresh_output_display_images(gui)

    PixelFixGui._add_outline_from_selection(gui)

    assert gui.process_status_var.value == "Added adaptive pixel-perfect outline to 4 pixels. Press Undo to restore it."


def test_add_outline_from_selection_adaptive_mode_ignores_invalid_selection_index() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.downsample_result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000],
            [0x000000, 0x445566, 0x000000],
            [0x000000, 0x000000, 0x000000],
        ],
        stage="downsample",
    )
    gui.palette_result = None
    gui.transparent_colors = set()
    gui.downsample_display_image = None
    gui.palette_display_image = None
    gui.image_state = "processed_current"
    gui.last_successful_process_snapshot = {"stage": "downsample"}
    gui.active_palette = None
    gui.active_palette_source = ""
    gui.active_palette_path = None
    gui.advanced_palette_preview = None
    gui.session = SimpleNamespace(current=PreviewSettings())
    gui.quick_compare_active = False
    gui.view_var = SimpleNamespace(set=lambda _value: None)
    gui.outline_pixel_perfect_var = SimpleNamespace(get=lambda: True)
    gui.outline_adaptive_var = SimpleNamespace(get=lambda: True)
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))
    gui._displayed_palette = [0x112233]
    gui._palette_selection_indices = {9}
    gui._palette_selection_anchor_index = None
    gui._update_palette_strip = lambda: None
    gui._update_image_info = lambda: None
    gui.redraw_canvas = lambda: None
    gui._schedule_state_persist = lambda: None
    gui._refresh_action_states = lambda: None
    gui._sync_controls_from_settings = lambda _settings: None
    gui._clear_palette_undo_state = lambda: setattr(gui, "_palette_undo_state", None)
    PixelFixGui._refresh_output_display_images(gui)

    PixelFixGui._add_outline_from_selection(gui)

    assert gui.process_status_var.value == "Added adaptive pixel-perfect outline to 4 pixels. Press Undo to restore it."


def test_add_outline_from_selection_adaptive_updates_output_and_undo_restores() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.downsample_result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000],
            [0x000000, 0x204060, 0x000000],
            [0x000000, 0x000000, 0x000000],
        ],
        stage="downsample",
    )
    gui.palette_result = None
    gui.transparent_colors = set()
    gui.downsample_display_image = None
    gui.palette_display_image = None
    gui.image_state = "processed_current"
    gui.last_successful_process_snapshot = {"stage": "downsample"}
    gui.active_palette = None
    gui.active_palette_source = ""
    gui.active_palette_path = None
    gui.advanced_palette_preview = None
    gui.session = SimpleNamespace(current=PreviewSettings())
    gui.quick_compare_active = False
    gui.view_var = SimpleNamespace(set=lambda _value: None)
    gui.outline_pixel_perfect_var = SimpleNamespace(get=lambda: True)
    gui.outline_adaptive_var = SimpleNamespace(get=lambda: True)
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))
    gui._displayed_palette = [0xFFFFFF]
    gui._palette_selection_indices = set()
    gui._palette_selection_anchor_index = None
    gui._update_palette_strip = lambda: None
    gui._update_image_info = lambda: None
    gui.redraw_canvas = lambda: None
    gui._schedule_state_persist = lambda: None
    gui._refresh_action_states = lambda: None
    gui._sync_controls_from_settings = lambda _settings: None
    gui._clear_palette_undo_state = lambda: setattr(gui, "_palette_undo_state", None)
    PixelFixGui._refresh_output_display_images(gui)

    PixelFixGui._add_outline_from_selection(gui)

    assert gui.downsample_display_image.getpixel((1, 0)) == (0x19, 0x33, 0x4C, 255)
    assert gui.process_status_var.value == "Added adaptive pixel-perfect outline to 4 pixels. Press Undo to restore it."
    assert 0x19334C in gui.downsample_result.display_palette_labels
    assert PixelFixGui._undo_palette_application(gui) is True
    assert gui.downsample_display_image.getpixel((1, 0))[3] == 0

def test_remove_outline_updates_output_and_undo_restores() -> None:
    updates: list[str] = []
>>>>>>> theirs
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.downsample_result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x112233, 0x445566, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000],
        ],
        stage="palette",
    )
    gui.palette_result = None
    gui.transparent_colors = set()
    gui.downsample_display_image = None
    gui.palette_display_image = None
    gui.image_state = "processed_current"
    gui.last_successful_process_snapshot = {"stage": "downsample"}
    gui.active_palette = None
    gui.active_palette_source = ""
    gui.active_palette_path = None
    gui.advanced_palette_preview = None
    gui.session = SimpleNamespace(current=PreviewSettings())
    gui.quick_compare_active = False
    gui.view_var = SimpleNamespace(set=lambda _value: None)
    gui.outline_pixel_perfect_var = SimpleNamespace(get=lambda: False)
    gui.outline_adaptive_var = SimpleNamespace(get=lambda: True)
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))
    gui._displayed_palette = [0x112233, 0x445566]
    gui._palette_selection_indices = set()
    gui._palette_selection_anchor_index = None
    gui._update_palette_strip = lambda: None
    gui._update_image_info = lambda: None
    gui.redraw_canvas = lambda: None
    gui._schedule_state_persist = lambda: None
    gui._refresh_action_states = lambda: None
    gui._sync_controls_from_settings = lambda _settings: None
    gui._clear_palette_undo_state = lambda: setattr(gui, "_palette_undo_state", None)
    PixelFixGui._refresh_output_display_images(gui)

    PixelFixGui._add_outline_from_selection(gui)

    assert gui.process_status_var.value == "Added adaptive outline to 10 pixels. Press Undo to restore it."


def test_outline_adaptive_enabled_defaults_false_without_gui_state() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)

    assert PixelFixGui._outline_adaptive_enabled(gui) is False

def test_remove_outline_with_brightness_threshold_updates_status() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.downsample_result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x112233, 0xD0D0D0, 0x112233, 0x000000],
            [0x000000, 0x112233, 0x112233, 0x112233, 0x000000],
            [0x000000, 0x112233, 0x112233, 0x112233, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
        ],
        stage="downsample",
    )
    gui.palette_result = None
    gui.transparent_colors = set()
    gui.downsample_display_image = None
    gui.palette_display_image = None
    gui.image_state = "processed_current"
    gui.last_successful_process_snapshot = {"stage": "downsample"}
    gui.active_palette = None
    gui.active_palette_source = ""
    gui.active_palette_path = None
    gui.advanced_palette_preview = None
    gui.session = SimpleNamespace(current=PreviewSettings())
    gui.quick_compare_active = False
    gui.view_var = SimpleNamespace(set=lambda _value: None)
    gui.outline_pixel_perfect_var = SimpleNamespace(get=lambda: False)
    gui.outline_brightness_threshold_enabled_var = SimpleNamespace(get=lambda: True)
    gui.outline_brightness_threshold_var = SimpleNamespace(get=lambda: 80, set=lambda _value: None)
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))
    gui._update_palette_strip = lambda: None
    gui._update_image_info = lambda: None
    gui.redraw_canvas = lambda: None
    gui._schedule_state_persist = lambda: None
    gui._refresh_action_states = lambda: None
    gui._sync_controls_from_settings = lambda _settings: None
    gui._clear_palette_undo_state = lambda: setattr(gui, "_palette_undo_state", None)
    PixelFixGui._refresh_output_display_images(gui)

    PixelFixGui._remove_outline(gui)

    assert gui.process_status_var.value == "Removed 7 outline pixels at brightness ≤ 80. Press Undo to restore it."
    assert gui.downsample_display_image.getpixel((2, 1))[3] == 255


def test_outline_pixel_perfect_enabled_defaults_true_without_gui_state() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)

    assert PixelFixGui._outline_pixel_perfect_enabled(gui) is True


<<<<<<< ours
>>>>>>> theirs
=======
def test_outline_brightness_threshold_helpers_have_safe_defaults() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)

    assert PixelFixGui._outline_brightness_threshold_enabled(gui) is False
    assert PixelFixGui._outline_brightness_threshold_value(gui) == 80


>>>>>>> theirs
def test_update_palette_strip_flattens_generated_ramps_into_normal_palette() -> None:
    rectangles: list[tuple[object, ...]] = []
    palette_info = SimpleNamespace(value="", set=lambda value: setattr(palette_info, "value", value))

    class PaletteCanvasStub:
        def delete(self, *_args):
            rectangles.clear()

        def configure(self, **_kwargs):
            return None

        def winfo_width(self):
            return 240

        def create_rectangle(self, *args, **_kwargs):
            rectangles.append(args)

        def create_text(self, *_args, **_kwargs):
            raise AssertionError("Palette preview should not render grouped ramp labels.")

    gui = PixelFixGui.__new__(PixelFixGui)
    gui.palette_canvas = PaletteCanvasStub()
    gui.palette_info_var = palette_info
    gui.active_palette = None
    gui.active_palette_source = ""
    gui._palette_selection_indices = set()
    gui.advanced_palette_preview = generate_structured_palette(
        [],
        key_colors=[0x336699, 0xCC8844],
        generated_shades=2,
    ).palette
    gui._current_output_result = lambda: None

    PixelFixGui._update_palette_strip(gui)

    assert len(rectangles) == gui.advanced_palette_preview.palette_size()
    assert palette_info.value == f"Palette: Generated ({gui.advanced_palette_preview.palette_size()} colours)"


def test_get_display_palette_uses_adjusted_palette_preview() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.workspace = ColorWorkspace()
    gui.active_palette = None
    gui.active_palette_source = ""
    gui.advanced_palette_preview = generate_structured_palette(
        [],
        key_colors=[0x336699],
        generated_shades=2,
    ).palette
    gui.palette_result = None
    gui.downsample_result = None
    gui.session = SimpleNamespace(current=PreviewSettings(palette_brightness=20))

    palette, source = PixelFixGui._get_display_palette(gui)

    assert len(palette) == gui.advanced_palette_preview.palette_size()
    assert palette != gui.advanced_palette_preview.labels()
    assert source == "Generated (Adjusted)"


def test_palette_adjustment_change_marks_output_stale_and_refreshes_palette() -> None:
    messages: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.process_status_var = SimpleNamespace(set=lambda value: messages.append(value))
    gui._clear_palette_undo_state = lambda: messages.append("clear")
    gui._mark_output_stale = lambda message=None: messages.append(f"stale:{message}")
    gui._update_key_color_list = lambda: messages.append("list")
    gui._update_palette_adjustment_labels = lambda: messages.append("adjust")
    gui._update_scale_info = lambda: messages.append("scale")
    gui._update_palette_strip = lambda: messages.append("palette")
    gui.redraw_canvas = lambda: messages.append("redraw")
    gui._schedule_state_persist = lambda: messages.append("persist")
    gui._refresh_action_states = lambda: messages.append("refresh")
    gui._has_palette_source = lambda: True

    PixelFixGui._handle_settings_transition(
        gui,
        PreviewSettings(),
        PreviewSettings(palette_brightness=15),
    )

    assert messages == [
        "clear",
        "stale:Palette adjustments changed. Click Apply Palette to update the preview.",
        "list",
        "adjust",
        "scale",
        "palette",
        "redraw",
        "persist",
        "refresh",
    ]


def test_selected_palette_adjustment_change_uses_selection_message() -> None:
    messages: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.process_status_var = SimpleNamespace(set=lambda value: messages.append(value))
    gui._clear_palette_undo_state = lambda: messages.append("clear")
    gui._mark_output_stale = lambda message=None: messages.append(f"stale:{message}")
    gui._update_key_color_list = lambda: messages.append("list")
    gui._update_palette_adjustment_labels = lambda: messages.append("adjust")
    gui._update_scale_info = lambda: messages.append("scale")
    gui._update_palette_strip = lambda: messages.append("palette")
    gui.redraw_canvas = lambda: messages.append("redraw")
    gui._schedule_state_persist = lambda: messages.append("persist")
    gui._refresh_action_states = lambda: messages.append("refresh")
    gui._has_palette_source = lambda: True
    gui._palette_adjustment_selection_indices = lambda: {1, 2}

    PixelFixGui._handle_settings_transition(
        gui,
        PreviewSettings(),
        PreviewSettings(palette_brightness=15),
    )

    assert messages[1] == "stale:Selected palette colours changed. Click Apply Palette to update the preview."

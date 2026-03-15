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
    apply_bucket_fill,
    apply_ellipse_operation,
    apply_line_operation,
    apply_rectangle_operation,
    apply_transparency_fill,
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
    PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES,
    PALETTE_SORT_HUE,
    PALETTE_SORT_LIGHTNESS,
)
from pixel_fix.palette.workspace import ColorWorkspace
from pixel_fix.pipeline import PipelineConfig, PipelinePreparedResult


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


class TextVarStub:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


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
        self.style = None
        self.image = None

    def configure(self, **kwargs) -> None:
        if "state" in kwargs:
            self.state = kwargs["state"]
        if "text" in kwargs:
            self.text = kwargs["text"]
        if "style" in kwargs:
            self.style = kwargs["style"]
        if "image" in kwargs:
            self.image = kwargs["image"]


class PackWidgetStub(WidgetStub):
    def __init__(self) -> None:
        super().__init__()
        self.manager = ""
        self.pack_calls: list[dict[str, object]] = []

    def pack(self, **kwargs) -> None:
        self.manager = "pack"
        self.pack_calls.append(kwargs)

    def pack_forget(self) -> None:
        self.manager = ""

    def winfo_manager(self) -> str:
        return self.manager


class MenuStub:
    def __init__(self) -> None:
        self.states: dict[str, object] = {}

    def entryconfigure(self, label: str, **kwargs) -> None:
        self.states[label] = kwargs.get("state")


def _assert_no_full_2x2(mask: list[list[bool]]) -> None:
    height = len(mask)
    width = len(mask[0]) if height else 0
    for y in range(max(0, height - 1)):
        for x in range(max(0, width - 1)):
            assert not (mask[y][x] and mask[y][x + 1] and mask[y + 1][x] and mask[y + 1][x + 1])


def _make_tool_options_gui(
    mode: str | None,
    *,
    outline_mode: str = app_module.OUTLINE_COLOUR_MODE_PALETTE,
    remove_threshold: bool = False,
    selected_outline_label: int | None = 0x112233,
    has_output: bool = True,
) -> PixelFixGui:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.canvas_tool_mode = mode
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui.image_state = "processed_current"
    gui._pick_preview_sample = None
    gui.pick_preview_var = TextVarStub("")
    gui.pick_preview_rgb_var = TextVarStub("")
    gui.pick_preview_position_var = TextVarStub("")
    gui.options_helper_var = TextVarStub("")
    gui.options_helper_label = PackWidgetStub()
    gui.brush_width_row = PackWidgetStub()
    gui.brush_shape_row = PackWidgetStub()
    gui.pick_preview_empty_label = PackWidgetStub()
    gui.pick_preview_frame = PackWidgetStub()
    gui.outline_pixel_perfect_row = PackWidgetStub()
    gui.outline_colour_mode_row = PackWidgetStub()
    gui.outline_adaptive_row = PackWidgetStub()
    gui.outline_add_generated_colours_row = PackWidgetStub()
    gui.outline_remove_threshold_row = PackWidgetStub()
    gui.outline_remove_direction_row = PackWidgetStub()
    gui.options_apply_row = PackWidgetStub()
    gui.pick_preview_swatch = PickerPreviewSwatchStub()
    gui.brush_width_spinbox = WidgetStub()
    gui.brush_shape_dropdown_button = WidgetStub()
    gui.outline_pixel_perfect_toggle = WidgetStub()
    gui.outline_colour_mode_dropdown_button = WidgetStub()
    gui.outline_add_generated_colours_toggle = WidgetStub()
    gui.outline_adaptive_darken_label = WidgetStub()
    gui.outline_adaptive_darken_spinbox = WidgetStub()
    gui.outline_remove_brightness_threshold_toggle = WidgetStub()
    gui.outline_remove_brightness_threshold_spinbox = WidgetStub()
    gui.outline_remove_brightness_direction_dropdown_button = WidgetStub()
    gui.options_apply_button = WidgetStub()
    gui.outline_colour_mode_var = TextVarStub(outline_mode)
    gui.outline_colour_mode_display_var = TextVarStub(app_module.OUTLINE_COLOUR_MODE_LABELS[outline_mode])
    gui.outline_remove_brightness_threshold_enabled_var = SimpleNamespace(get=lambda: remove_threshold)
    gui.outline_remove_brightness_threshold_direction_var = TextVarStub(
        app_module.OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK
    )
    gui.outline_remove_brightness_direction_display_var = TextVarStub("Dark")
    gui._selected_palette_outline_label = lambda: selected_outline_label
    gui._current_output_result = lambda: object() if has_output else None
    return gui


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


def test_build_output_display_image_applies_adjustments_to_processed_image_only() -> None:
    prepared = PipelinePreparedResult(
        reduced_labels=[[0x336699, 0x88AACC]],
        pixel_width=1,
        grid_method="manual",
        input_size=(2, 1),
        initial_color_count=2,
    )
    result = ProcessResult(
        grid=[[(0x33, 0x66, 0x99), (0x88, 0xAA, 0xCC)]],
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
    )
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.transparent_colors = set()
    gui.workspace = ColorWorkspace()
    gui.session = SimpleNamespace(current=PreviewSettings(palette_brightness=20, palette_hue=20, palette_saturation=140))
    gui.active_palette = [0x336699, 0x88AACC]
    gui.active_palette_source = "Loaded"
    gui.advanced_palette_preview = None
    gui.palette_result = result
    gui.downsample_result = None
    gui._palette_selection_indices = set()

    image = PixelFixGui._build_output_display_image(gui, result)

    assert image.getpixel((0, 0))[:3] != (0x33, 0x66, 0x99)
    assert image.getpixel((1, 0))[:3] != (0x88, 0xAA, 0xCC)
    palette, source = PixelFixGui._get_display_palette(gui)
    assert palette == [0x336699, 0x88AACC]
    assert source == "Loaded"


def test_build_output_display_image_only_adjusts_selected_palette_colours() -> None:
    prepared = PipelinePreparedResult(
        reduced_labels=[[0x336699, 0x88AACC]],
        pixel_width=1,
        grid_method="manual",
        input_size=(2, 1),
        initial_color_count=2,
    )
    result = ProcessResult(
        grid=[[(0x33, 0x66, 0x99), (0x88, 0xAA, 0xCC)]],
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
    )
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.transparent_colors = set()
    gui.workspace = ColorWorkspace()
    gui.session = SimpleNamespace(current=PreviewSettings(palette_brightness=20, palette_hue=20, palette_saturation=140))
    gui.active_palette = [0x336699, 0x88AACC]
    gui.active_palette_source = "Loaded"
    gui.advanced_palette_preview = None
    gui.palette_result = result
    gui.downsample_result = None
    gui._palette_selection_indices = {1}

    image = PixelFixGui._build_output_display_image(gui, result)

    assert image.getpixel((0, 0))[:3] == (0x33, 0x66, 0x99)
    assert image.getpixel((1, 0))[:3] != (0x88, 0xAA, 0xCC)


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


def test_apply_bucket_fill_only_updates_connected_visible_region() -> None:
    result = _result_from_labels(
        [
            [0xFF0000, 0xFF0000, 0x0000FF],
            [0x0000FF, 0x0000FF, 0xFF0000],
        ]
    )

    updated, changed = apply_bucket_fill(result, 0, 0, 0x00FF00)

    assert changed == 2
    assert updated.grid[0][0] == (0x00, 0xFF, 0x00)
    assert updated.grid[0][1] == (0x00, 0xFF, 0x00)
    assert updated.grid[1][2] == (0xFF, 0x00, 0x00)


def test_apply_bucket_fill_can_fill_connected_transparent_region() -> None:
    result = _result_from_labels(
        [
            [0x112233, 0x445566, 0x778899],
            [0xAABBCC, 0xDDEEFF, 0x123456],
        ]
    )
    result = ProcessResult(
        grid=result.grid,
        width=result.width,
        height=result.height,
        stats=result.stats,
        prepared_input=result.prepared_input,
        alpha_mask=((False, False, True), (False, True, True)),
    )

    updated, changed = apply_bucket_fill(result, 0, 0, 0x00FF00)

    assert changed == 3
    assert updated.alpha_mask is None
    assert updated.grid[0][0] == (0x00, 0xFF, 0x00)
    assert updated.grid[0][1] == (0x00, 0xFF, 0x00)
    assert updated.grid[1][0] == (0x00, 0xFF, 0x00)


def test_apply_bucket_fill_reports_no_change_when_visible_region_already_matches() -> None:
    result = _result_from_labels([[0x00FF00, 0x00FF00]])

    updated, changed = apply_bucket_fill(result, 0, 0, 0x00FF00)

    assert changed == 0
    assert updated is result


def test_apply_rectangle_operation_draws_outline_and_fill() -> None:
    result = _result_from_labels(
        [
            [0x111111, 0x111111, 0x111111],
            [0x111111, 0x111111, 0x111111],
            [0x111111, 0x111111, 0x111111],
        ]
    )
    result = ProcessResult(
        grid=result.grid,
        width=result.width,
        height=result.height,
        stats=result.stats,
        prepared_input=result.prepared_input,
        alpha_mask=((False, False, False), (False, False, False), (False, False, False)),
    )

    updated, changed = apply_rectangle_operation(result, 0, 0, 2, 2, 0xAA0000, fill_label=0x00BB00, width=1)

    assert changed == 9
    assert updated.alpha_mask is None
    assert updated.grid[0][0] == (0xAA, 0x00, 0x00)
    assert updated.grid[1][1] == (0x00, 0xBB, 0x00)


def test_apply_rectangle_operation_can_use_transparent_fill() -> None:
    result = _result_from_labels(
        [
            [0x445566, 0x445566, 0x445566],
            [0x445566, 0x445566, 0x445566],
            [0x445566, 0x445566, 0x445566],
        ]
    )

    updated, changed = apply_rectangle_operation(result, 0, 0, 2, 2, 0xAA0000, fill_label=None, width=1)

    assert changed == 9
    assert updated.alpha_mask is not None
    assert updated.alpha_mask[1][1] is False
    assert updated.grid[0][1] == (0xAA, 0x00, 0x00)


def test_apply_rectangle_operation_respects_outline_width() -> None:
    result = _result_from_labels(
        [
            [0x111111] * 7,
            [0x111111] * 7,
            [0x111111] * 7,
            [0x111111] * 7,
            [0x111111] * 7,
            [0x111111] * 7,
            [0x111111] * 7,
        ]
    )
    result = ProcessResult(
        grid=result.grid,
        width=result.width,
        height=result.height,
        stats=result.stats,
        prepared_input=result.prepared_input,
        alpha_mask=tuple(tuple(False for _ in range(7)) for _ in range(7)),
    )

    updated, changed = apply_rectangle_operation(result, 0, 0, 6, 6, 0xAA0000, fill_label=None, width=2)

    assert changed > 0
    assert updated.alpha_mask is not None
    assert updated.alpha_mask[1][1] is True
    assert updated.alpha_mask[3][3] is False
    assert updated.grid[1][1] == (0xAA, 0x00, 0x00)


def test_apply_ellipse_operation_draws_expected_pixels() -> None:
    result = _result_from_labels(
        [
            [0x111111] * 5,
            [0x111111] * 5,
            [0x111111] * 5,
            [0x111111] * 5,
            [0x111111] * 5,
        ]
    )
    result = ProcessResult(
        grid=result.grid,
        width=result.width,
        height=result.height,
        stats=result.stats,
        prepared_input=result.prepared_input,
        alpha_mask=tuple(tuple(False for _ in range(5)) for _ in range(5)),
    )

    updated, changed = apply_ellipse_operation(result, 0, 0, 4, 4, 0xAA0000, fill_label=0x00BB00, width=1)

    assert changed > 0
    assert updated.alpha_mask is not None
    assert updated.alpha_mask[0][0] is False
    assert updated.alpha_mask[0][2] is True
    assert updated.grid[0][2] == (0xAA, 0x00, 0x00)
    assert updated.grid[2][2] == (0x00, 0xBB, 0x00)


def test_apply_line_operation_respects_width() -> None:
    result = _result_from_labels([[0x000000] * 7 for _ in range(7)])

    updated, changed = apply_line_operation(result, 1, 3, 5, 3, 0xAA0000, width=3)

    assert changed > 5
    assert updated.alpha_mask is not None
    assert updated.alpha_mask[3][3] is True
    assert updated.grid[3][3] == (0xAA, 0x00, 0x00)
    assert updated.grid[2][3] == (0xAA, 0x00, 0x00)
    assert updated.grid[4][3] == (0xAA, 0x00, 0x00)
    assert updated.alpha_mask[0][0] is False


def test_add_exterior_outline_defaults_to_pixel_perfect_diamond() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000],
            [0x000000, 0x445566, 0x000000],
            [0x000000, 0x000000, 0x000000],
        ]
    )

    updated, changed, generated = add_exterior_outline(result, 0x112233)

    assert changed == 4
    assert generated == (0x112233,)
    assert updated.grid[1][1] == (0x44, 0x55, 0x66)
    assert updated.alpha_mask is not None
    assert updated.alpha_mask[0][0] is False
    assert updated.alpha_mask[0][1] is True
    assert updated.grid[0][1] == (0x11, 0x22, 0x33)
    assert updated.grid[1][0] == (0x11, 0x22, 0x33)
    assert updated.grid[1][2] == (0x11, 0x22, 0x33)
    assert updated.grid[2][1] == (0x11, 0x22, 0x33)
    assert updated.alpha_mask[2][2] is False


def test_add_exterior_outline_square_mode_keeps_full_ring() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000],
            [0x000000, 0x445566, 0x000000],
            [0x000000, 0x000000, 0x000000],
        ]
    )

    updated, changed, generated = add_exterior_outline(result, 0x112233, pixel_perfect=False)

    assert changed == 8
    assert generated == (0x112233,)
    assert updated.grid[0][0] == (0x11, 0x22, 0x33)
    assert updated.alpha_mask is None


def test_add_exterior_outline_pixel_perfect_ignores_internal_holes() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x445566, 0x445566, 0x445566, 0x000000],
            [0x000000, 0x445566, 0x000000, 0x445566, 0x000000],
            [0x000000, 0x445566, 0x445566, 0x445566, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
        ]
    )

    updated, changed, generated = add_exterior_outline(result, 0x112233)

    assert changed == 12
    assert generated == (0x112233,)
    assert updated.alpha_mask is not None
    assert updated.alpha_mask[2][2] is False
    assert updated.grid[2][2] == (0, 0, 0)
    assert updated.alpha_mask[0][0] is False
    assert updated.grid[0][2] == (0x11, 0x22, 0x33)


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

    updated, changed, generated = add_exterior_outline(result, 0x112233)

    assert changed > 0
    assert generated == (0x112233,)
    assert updated.alpha_mask is not None
    added_mask = [
        [bool(updated.alpha_mask[y][x]) and not bool(result.alpha_mask[y][x]) for x in range(result.width)]
        for y in range(result.height)
    ]
    _assert_no_full_2x2(added_mask)




def test_add_exterior_outline_adaptive_uses_darkened_neighbouring_colours() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x112233, 0x445566, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000],
        ]
    )

    workspace = ColorWorkspace()
    updated, changed, generated = add_exterior_outline(
        result,
        0xABCDEF,
        adaptive=True,
        pixel_perfect=False,
        adaptive_darken_percent=60,
        workspace=workspace,
    )

    assert changed > 0
    assert generated
    assert updated.grid[0][1] not in {(0x11, 0x22, 0x33), (0x44, 0x55, 0x66)}
    assert updated.grid[0][2] not in {(0x11, 0x22, 0x33), (0x44, 0x55, 0x66)}
    assert updated.grid[0][1] != (0xAB, 0xCD, 0xEF)
    original_lightness = workspace.label_to_oklab(0x112233)[0]
    darkened_label = (updated.grid[0][1][0] << 16) | (updated.grid[0][1][1] << 8) | updated.grid[0][1][2]
    assert workspace.label_to_oklab(darkened_label)[0] < original_lightness


def test_add_exterior_outline_adaptive_clamps_darken_percent_and_reports_generated_labels() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000],
            [0x000000, 0x6699CC, 0x000000],
            [0x000000, 0x000000, 0x000000],
        ]
    )

    updated, changed, generated = add_exterior_outline(
        result,
        0xFFFFFF,
        adaptive=True,
        pixel_perfect=False,
        adaptive_darken_percent=150,
        workspace=ColorWorkspace(),
    )

    assert changed == 8
    assert generated == (0,)
    assert updated.grid[0][0] == (0, 0, 0)


def test_add_exterior_outline_adaptive_prefers_lowest_label_on_dominant_tie() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x111111, 0x222222],
            [0x000000, 0x000000, 0x000000],
        ]
    )

    updated, _changed, generated = add_exterior_outline(
        result,
        0xFFFFFF,
        adaptive=True,
        pixel_perfect=False,
        adaptive_darken_percent=0,
        workspace=ColorWorkspace(),
    )

    assert generated == (0x111111,)
    assert updated.grid[1][1] == (0x11, 0x11, 0x11)


def test_add_exterior_outline_repeats_width_passes() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x000000, 0x445566, 0x000000, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
        ]
    )

    updated, changed, generated = add_exterior_outline(result, 0x112233, pixel_perfect=False, width=2)

    assert changed == 24
    assert generated == (0x112233,)
    assert updated.alpha_mask is None
    assert updated.grid[2][2] == (0x44, 0x55, 0x66)
    assert updated.grid[0][0] == (0x11, 0x22, 0x33)
    assert updated.grid[4][4] == (0x11, 0x22, 0x33)


def test_add_exterior_outline_adaptive_repeats_width_passes() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x000000, 0x6699CC, 0x000000, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
        ]
    )

    updated, changed, generated = add_exterior_outline(
        result,
        0xFFFFFF,
        adaptive=True,
        pixel_perfect=False,
        adaptive_darken_percent=60,
        width=2,
        workspace=ColorWorkspace(),
    )

    assert changed == 24
    assert generated
    assert updated.alpha_mask is None
    assert updated.grid[0][0] != (0x66, 0x99, 0xCC)
    assert updated.grid[4][4] != (0xFF, 0xFF, 0xFF)


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

    updated, changed = remove_exterior_outline(result, pixel_perfect=False)

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

    updated, changed = remove_exterior_outline(result, pixel_perfect=False)

    assert changed == 3
    assert updated.alpha_mask == (
        (False, False, False),
        (False, False, False),
        (False, False, False),
    )


def test_remove_exterior_outline_dark_brightness_threshold_removes_only_dark_candidates() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x202020, 0x202020, 0x202020, 0x000000],
            [0x000000, 0xE0E0E0, 0x808080, 0xE0E0E0, 0x000000],
            [0x000000, 0xE0E0E0, 0xE0E0E0, 0xE0E0E0, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
        ]
    )

    updated, changed = remove_exterior_outline(
        result,
        pixel_perfect=False,
        brightness_threshold_enabled=True,
        brightness_threshold_percent=40,
        brightness_threshold_direction=app_module.OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK,
        workspace=ColorWorkspace(),
    )

    assert changed == 3
    assert updated.alpha_mask is not None
    assert updated.alpha_mask[1][1] is False
    assert updated.alpha_mask[1][2] is False
    assert updated.alpha_mask[1][3] is False
    assert updated.alpha_mask[2][1] is True
    assert updated.alpha_mask[3][2] is True


def test_remove_exterior_outline_bright_brightness_threshold_removes_only_bright_candidates() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x202020, 0x202020, 0x202020, 0x000000],
            [0x000000, 0xE0E0E0, 0x808080, 0xE0E0E0, 0x000000],
            [0x000000, 0xE0E0E0, 0xE0E0E0, 0xE0E0E0, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
        ]
    )

    updated, changed = remove_exterior_outline(
        result,
        pixel_perfect=False,
        brightness_threshold_enabled=True,
        brightness_threshold_percent=40,
        brightness_threshold_direction=app_module.OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_BRIGHT,
        workspace=ColorWorkspace(),
    )

    assert changed == 5
    assert updated.alpha_mask is not None
    assert updated.alpha_mask[1][1] is True
    assert updated.alpha_mask[2][1] is False
    assert updated.alpha_mask[2][3] is False
    assert updated.alpha_mask[3][1] is False
    assert updated.alpha_mask[3][2] is False
    assert updated.alpha_mask[3][3] is False


def test_remove_exterior_outline_brightness_threshold_clamps_percent() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x202020, 0x202020, 0x202020, 0x000000],
            [0x000000, 0xE0E0E0, 0x808080, 0xE0E0E0, 0x000000],
            [0x000000, 0xE0E0E0, 0xE0E0E0, 0xE0E0E0, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
        ]
    )

    updated, changed = remove_exterior_outline(
        result,
        pixel_perfect=False,
        brightness_threshold_enabled=True,
        brightness_threshold_percent=400,
        brightness_threshold_direction=app_module.OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK,
        workspace=ColorWorkspace(),
    )

    assert changed == 8
    assert updated.alpha_mask is not None
    assert updated.alpha_mask[2][2] is True
    assert updated.alpha_mask[1][1] is False
    assert updated.alpha_mask[3][3] is False


def test_remove_exterior_outline_applies_pixel_perfect_after_brightness_filter() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x202020, 0x202020, 0x202020, 0x000000],
            [0x000000, 0xE0E0E0, 0x808080, 0xE0E0E0, 0x000000],
            [0x000000, 0xE0E0E0, 0xE0E0E0, 0xE0E0E0, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
        ]
    )

    updated, changed = remove_exterior_outline(
        result,
        brightness_threshold_enabled=True,
        brightness_threshold_percent=40,
        brightness_threshold_direction=app_module.OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK,
        workspace=ColorWorkspace(),
    )

    assert changed == 3
    assert updated.alpha_mask is not None
    assert updated.alpha_mask[1][1] is False
    assert updated.alpha_mask[1][2] is False
    assert updated.alpha_mask[1][3] is False
    assert updated.alpha_mask[2][1] is True


def test_remove_exterior_outline_reports_no_change_when_no_pixels_meet_brightness_threshold() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0xE0E0E0, 0xE0E0E0, 0xE0E0E0, 0x000000],
            [0x000000, 0xE0E0E0, 0x808080, 0xE0E0E0, 0x000000],
            [0x000000, 0xE0E0E0, 0xE0E0E0, 0xE0E0E0, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
        ]
    )

    updated, changed = remove_exterior_outline(
        result,
        pixel_perfect=False,
        brightness_threshold_enabled=True,
        brightness_threshold_percent=0,
        brightness_threshold_direction=app_module.OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK,
        workspace=ColorWorkspace(),
    )

    assert changed == 0
    assert updated is result


def test_remove_exterior_outline_repeats_width_passes_with_brightness_threshold() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x202020, 0x202020, 0x202020, 0x202020, 0x202020, 0x000000],
            [0x000000, 0x202020, 0x202020, 0x202020, 0x202020, 0x202020, 0x000000],
            [0x000000, 0x202020, 0x202020, 0xE0E0E0, 0x202020, 0x202020, 0x000000],
            [0x000000, 0x202020, 0x202020, 0x202020, 0x202020, 0x202020, 0x000000],
            [0x000000, 0x202020, 0x202020, 0x202020, 0x202020, 0x202020, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
        ]
    )

    updated, changed = remove_exterior_outline(
        result,
        brightness_threshold_enabled=True,
        brightness_threshold_percent=40,
        brightness_threshold_direction=app_module.OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK,
        width=2,
        workspace=ColorWorkspace(),
    )

    assert changed == 24
    assert updated.alpha_mask is not None
    assert updated.alpha_mask[3][3] is True
    assert updated.alpha_mask[2][3] is False
    assert updated.alpha_mask[3][2] is False


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
    result = ProcessResult(
        grid=result.grid,
        width=result.width,
        height=result.height,
        stats=result.stats,
        prepared_input=result.prepared_input,
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
    if any(not hasattr(PixelFixGui, name) for name in required) or not hasattr(PixelFixGui, "_apply_brush_segment"):
        pytest.skip("GUI brush interaction API is not available in this build")


def test_gui_brush_drag_interpolates_without_holes() -> None:
    _require_brush_gui_api()

    applied: list[tuple[int, int]] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_PENCIL
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui.dragging = False
    gui._display_context = object()
    gui.canvas = SimpleNamespace(configure=lambda **_kwargs: None, winfo_width=lambda: 64, winfo_height=lambda: 64)
    gui.redraw_canvas = lambda: None
    gui._point_is_over_image = lambda *_args, **_kwargs: True
    gui._preview_image_coordinates = lambda x, y, **_kwargs: (x, y)
    gui._cursor_for_pointer = lambda: ""
    gui._apply_brush_segment = lambda points, *_args, **_kwargs: (applied.extend(points) or len(points))
    gui._capture_palette_undo_state = lambda: None
    gui._refresh_action_states = lambda: None
    gui.process_status_var = SimpleNamespace(set=lambda _value: None)

    PixelFixGui._on_canvas_press(gui, SimpleNamespace(x=1, y=1))
    PixelFixGui._on_canvas_drag(gui, SimpleNamespace(x=4, y=1))
    PixelFixGui._on_canvas_release(gui, SimpleNamespace())

    xs = sorted({x for x, y in applied if y == 1})
    assert xs == list(range(min(xs), max(xs) + 1))


def test_gui_brush_stroke_captures_single_undo_for_press_drag_release() -> None:
    _require_brush_gui_api()

    calls: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_PENCIL
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui.dragging = False
    gui._display_context = object()
    gui.canvas = SimpleNamespace(configure=lambda **_kwargs: None, winfo_width=lambda: 64, winfo_height=lambda: 64)
    gui.redraw_canvas = lambda: None
    gui._point_is_over_image = lambda *_args, **_kwargs: True
    gui._preview_image_coordinates = lambda x, y, **_kwargs: (x, y)
    gui._cursor_for_pointer = lambda: ""
    gui._apply_brush_segment = lambda *_args, **_kwargs: 0
    gui._capture_palette_undo_state = lambda: calls.append("capture")
    gui._clear_palette_undo_state = lambda: None

    PixelFixGui._on_canvas_press(gui, SimpleNamespace(x=1, y=1))
    PixelFixGui._on_canvas_drag(gui, SimpleNamespace(x=3, y=1))
    PixelFixGui._on_canvas_drag(gui, SimpleNamespace(x=5, y=1))
    PixelFixGui._on_canvas_release(gui, SimpleNamespace())

    assert calls == ["capture"]


def test_shape_preview_image_uses_temporary_rasterized_result() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.downsample_result = ProcessResult(
        grid=[[(17, 17, 17), (17, 17, 17), (17, 17, 17)], [(17, 17, 17), (17, 17, 17), (17, 17, 17)], [(17, 17, 17), (17, 17, 17), (17, 17, 17)]],
        width=3,
        height=3,
        stats=ProcessStats(
            stage="downsample",
            pixel_width=1,
            resize_method="nearest",
            input_size=(3, 3),
            output_size=(3, 3),
            initial_color_count=1,
            color_count=1,
            elapsed_seconds=0.0,
        ),
        prepared_input=PipelinePreparedResult(
            reduced_labels=[[0x111111] * 3 for _ in range(3)],
            pixel_width=1,
            grid_method="manual",
            input_size=(3, 3),
            initial_color_count=1,
        ),
        alpha_mask=((False, False, False), (False, False, False), (False, False, False)),
    )
    gui.palette_result = None
    gui.transparent_colors = set()
    gui.primary_color_label = 0xAA0000
    gui.secondary_color_label = 0x00BB00
    gui.transparent_color_slot = None
    gui.brush_width_var = SimpleNamespace(get=lambda: 1)
    gui._shape_drag_active = True
    gui._shape_preview_anchor = (0, 0)
    gui._shape_preview_current = (2, 2)
    gui._shape_preview_tool_mode = app_module.CANVAS_TOOL_MODE_RECTANGLE
    gui._shape_preview_constrained = False

    preview = PixelFixGui._shape_preview_image(gui)

    assert preview is not None
    assert preview.getpixel((0, 0)) == (0xAA, 0x00, 0x00, 255)
    assert preview.getpixel((1, 1)) == (0x00, 0xBB, 0x00, 255)
    assert gui.downsample_result.alpha_mask is not None
    assert gui.downsample_result.alpha_mask[1][1] is False


def test_shape_preview_image_supports_line_tool() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.downsample_result = _result_from_labels([[0x000000] * 5 for _ in range(5)])
    gui.palette_result = None
    gui.transparent_colors = set()
    gui.primary_color_label = 0xAA0000
    gui.secondary_color_label = 0x00BB00
    gui.transparent_color_slot = app_module.ACTIVE_COLOR_SLOT_SECONDARY
    gui.brush_width_var = SimpleNamespace(get=lambda: 1)
    gui._shape_drag_active = True
    gui._shape_preview_anchor = (0, 0)
    gui._shape_preview_current = (4, 4)
    gui._shape_preview_tool_mode = app_module.CANVAS_TOOL_MODE_LINE
    gui._shape_preview_constrained = False

    preview = PixelFixGui._shape_preview_image(gui)

    assert preview is not None
    assert preview.getpixel((0, 0)) == (0xAA, 0x00, 0x00, 255)
    assert preview.getpixel((2, 2)) == (0xAA, 0x00, 0x00, 255)
    assert preview.getpixel((4, 4)) == (0xAA, 0x00, 0x00, 255)


def test_gui_bucket_click_updates_output_and_keeps_bucket_mode() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.downsample_result = _result_from_labels(
        [
            [0xFF0000, 0xFF0000, 0x0000FF],
            [0x0000FF, 0x0000FF, 0xFF0000],
        ]
    )
    gui.palette_result = None
    gui.original_display_image = object()
    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_BUCKET
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui.transparent_colors = set()
    gui.primary_color_label = 0x00FF00
    gui.secondary_color_label = 0x445566
    gui.transparent_color_slot = app_module.ACTIVE_COLOR_SLOT_SECONDARY
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))
    gui._preview_image_coordinates = lambda _x, _y, **_kwargs: (0, 0)
    gui._capture_palette_undo_state = lambda: setattr(gui, "captured_undo", True)
    gui.redraw_canvas = lambda: None
    gui._refresh_action_states = lambda: None

    PixelFixGui._on_canvas_press(gui, SimpleNamespace(x=5, y=5))

    assert gui.canvas_tool_mode == app_module.CANVAS_TOOL_MODE_BUCKET
    assert gui.downsample_result.grid[0][0] == (0x00, 0xFF, 0x00)
    assert gui.downsample_result.grid[0][1] == (0x00, 0xFF, 0x00)
    assert gui.process_status_var.value == "Filled 2 pixels with #00FF00. Press Undo to restore it."
    assert gui.captured_undo is True


def test_gui_shape_drag_captures_single_undo_and_commits_once() -> None:
    calls: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.original_display_image = object()
    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_RECTANGLE
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui.dragging = False
    gui.canvas = SimpleNamespace(configure=lambda **_kwargs: None)
    gui.redraw_canvas = lambda: calls.append("redraw")
    gui._preview_image_coordinates = lambda x, y, **_kwargs: (x, y)
    gui._cursor_for_pointer = lambda: ""
    gui._capture_palette_undo_state = lambda: calls.append("capture")
    gui._shape_preview_operation = lambda: (_result_from_labels([[0x123456]]), 1)
    gui._set_current_output_result = lambda _result: calls.append("set")
    gui._refresh_output_display_images = lambda: calls.append("refresh-images")
    gui._refresh_action_states = lambda: calls.append("actions")
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))
    gui.transparent_colors = set()

    PixelFixGui._on_canvas_press(gui, SimpleNamespace(x=1, y=1, state=0))
    PixelFixGui._on_canvas_drag(gui, SimpleNamespace(x=3, y=2, state=0))
    PixelFixGui._on_canvas_release(gui, SimpleNamespace(x=3, y=2, state=0))

    assert calls.count("capture") == 1
    assert "set" in calls
    assert "refresh-images" in calls
    assert gui.process_status_var.value == "Rectangle changed 1 pixel. Press Undo to restore it."
    assert gui._shape_drag_active is False


def test_gui_shape_drag_noop_release_clears_undo_and_preview_state() -> None:
    calls: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.original_display_image = object()
    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_ELLIPSE
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui.dragging = False
    gui.canvas = SimpleNamespace(configure=lambda **_kwargs: None)
    gui.redraw_canvas = lambda: calls.append("redraw")
    gui._preview_image_coordinates = lambda x, y, **_kwargs: (x, y)
    gui._cursor_for_pointer = lambda: ""
    gui._capture_palette_undo_state = lambda: calls.append("capture")
    gui._clear_palette_undo_state = lambda: calls.append("clear")
    gui._shape_preview_operation = lambda: (None, 0)

    PixelFixGui._on_canvas_press(gui, SimpleNamespace(x=1, y=1, state=0))
    PixelFixGui._on_canvas_drag(gui, SimpleNamespace(x=2, y=2, state=app_module.EVENT_STATE_SHIFT_MASK))
    PixelFixGui._on_canvas_release(gui, SimpleNamespace(x=2, y=2, state=app_module.EVENT_STATE_SHIFT_MASK))

    assert calls.count("capture") == 1
    assert "clear" in calls
    assert gui._shape_drag_active is False
    assert gui._shape_preview_anchor is None
    assert gui._shape_preview_current is None


def test_resolved_shape_preview_endpoint_constrains_square_with_shift() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui._shape_preview_anchor = (1, 1)
    gui._shape_preview_current = (4, 2)
    gui._shape_preview_constrained = True
    gui._shape_preview_tool_mode = app_module.CANVAS_TOOL_MODE_RECTANGLE

    endpoint = PixelFixGui._resolved_shape_preview_endpoint(gui, _result_from_labels([[0x112233] * 6 for _ in range(6)]))

    assert endpoint == (4, 4)


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


def test_redo_palette_application_reapplies_undone_preview_state() -> None:
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
    gui._clear_palette_redo_state = lambda: setattr(gui, "_palette_redo_state", None)
    gui._palette_undo_state = None
    gui._palette_redo_state = PaletteUndoState(
        palette_result=None,
        downsample_result=None,
        downsample_display_image=None,
        palette_display_image=None,
        image_state="loaded_original",
        last_successful_process_snapshot=None,
        active_palette=None,
        active_palette_source="",
        active_palette_path=None,
        advanced_palette_preview=None,
        transparent_colors=(),
        settings=PreviewSettings(pixel_width=4),
        palette_sort_reset_labels=(),
        palette_sort_reset_source=None,
        palette_sort_reset_path=None,
    )

    assert PixelFixGui._redo_palette_application(gui) is True
    assert gui.downsample_result is None
    assert gui.process_status_var.value == "Reapplied the last undone image change."
    assert gui._palette_redo_state is None
    assert gui._palette_undo_state is not None


def test_redo_settings_restores_next_state() -> None:
    messages: list[tuple[PreviewSettings, PreviewSettings, str | None]] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    previous = PreviewSettings(pixel_width=2)
    restored = PreviewSettings(pixel_width=6)
    gui._redo_palette_application = lambda: False
    gui.process_status_var = SimpleNamespace(set=lambda _value: None)
    gui.session = SimpleNamespace(
        current=previous,
        redo=lambda: restored,
        history=SimpleNamespace(can_redo=lambda: True),
    )
    gui._sync_controls_from_settings = lambda settings: messages.append((settings, settings, None))
    gui._handle_settings_transition = lambda before, after, message=None: messages.append((before, after, message))

    PixelFixGui.redo(gui)

    assert messages == [
        (restored, restored, None),
        (previous, restored, "Settings restored from redo."),
    ]


def test_active_color_picker_uses_processed_preview_and_sets_active_slot() -> None:
    calls: list[tuple[str, int]] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.original_display_image = object()
    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_ACTIVE_COLOR_PICK
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui._sample_label_from_preview = lambda _x, _y, *, view: 0x224466 if view == "processed" else None
    gui._assign_palette_color_to_slot = lambda slot, label: calls.append((slot, label))
    gui._active_color_slot_value = lambda: app_module.ACTIVE_COLOR_SLOT_SECONDARY
    gui._set_canvas_tool_mode = lambda mode: calls.append(("mode", -1 if mode is None else 1))
    gui._refresh_action_states = lambda: calls.append(("refresh", 0))

    PixelFixGui._on_canvas_press(gui, SimpleNamespace(x=10, y=12))

    assert calls == [
        (app_module.ACTIVE_COLOR_SLOT_SECONDARY, 0x224466),
        ("mode", -1),
        ("refresh", 0),
    ]


def test_merge_selected_palette_colours_replaces_selection_with_merged_label() -> None:
    captured: dict[str, object] = {}
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.workspace = ColorWorkspace()
    gui.process_status_var = SimpleNamespace(set=lambda value: captured.setdefault("status", value))
    gui._get_display_palette = lambda: ([0xFF0000, 0x00FF00, 0x0000FF], "Generated")
    gui._apply_palette_edit = lambda palette, message: captured.update({"palette": palette, "message": message})
    gui._palette_selection_indices = {0, 2}

    PixelFixGui._merge_selected_palette_colors(gui)

    assert captured["palette"][1] == 0x00FF00
    assert len(captured["palette"]) == 2
    assert captured["message"].startswith("Merged 2 palette colours into #")


def test_merge_selected_palette_colours_requires_two_swatches() -> None:
    messages: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.process_status_var = SimpleNamespace(set=lambda value: messages.append(value))
    gui._get_display_palette = lambda: ([0x111111, 0x222222], "Generated")
    gui._palette_selection_indices = {1}

    PixelFixGui._merge_selected_palette_colors(gui)

    assert messages == ["Select 2 or more palette colours to merge."]


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


def test_ramp_selected_palette_colours_appends_generated_ramps() -> None:
    captured: dict[str, object] = {}
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.workspace = ColorWorkspace()
    gui.process_status_var = SimpleNamespace(set=lambda value: captured.setdefault("status", value))
    gui._get_display_palette = lambda: ([0x336699, 0xCC8844, 0x112233], "Generated")
    gui._read_settings_from_controls = lambda *, strict=False: PreviewSettings(generated_shades=2, contrast_bias=0.7)
    gui._apply_palette_edit = lambda palette, message: captured.update({"palette": palette, "message": message})
    gui._palette_selection_indices = {0, 1}

    PixelFixGui._ramp_selected_palette_colors(gui)

    assert captured["palette"][:3] == [0x336699, 0xCC8844, 0x112233]
    assert len(captured["palette"]) == 3 + (2 * 3)
    assert captured["message"] == "Appended 6 ramp colours from 2 selected palette colours. Click Apply Palette to update the preview."


def test_ramp_selected_palette_colours_requires_selection() -> None:
    messages: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.process_status_var = SimpleNamespace(set=lambda value: messages.append(value))
    gui._get_display_palette = lambda: ([0x111111, 0x222222], "Generated")
    gui._palette_selection_indices = set()

    PixelFixGui._ramp_selected_palette_colors(gui)

    assert messages == ["Select one or more palette colours to ramp."]


def test_ramp_settings_change_does_not_mark_output_stale() -> None:
    messages: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.process_status_var = SimpleNamespace(set=lambda value: messages.append(value))
    gui._clear_palette_undo_state = lambda: messages.append("clear")
    gui._mark_output_stale = lambda message=None: messages.append(f"stale:{message}")
    gui._update_scale_info = lambda: messages.append("scale")
    gui._update_palette_strip = lambda: messages.append("palette")
    gui.redraw_canvas = lambda: messages.append("redraw")
    gui._schedule_state_persist = lambda: messages.append("persist")
    gui._refresh_action_states = lambda: messages.append("refresh")

    PixelFixGui._handle_settings_transition(
        gui,
        PreviewSettings(generated_shades=4),
        PreviewSettings(generated_shades=6),
    )

    assert messages == ["Ramp settings changed. Select palette colours and click Ramp to append new ramps.", "persist", "refresh"]


def test_palette_reduction_settings_change_does_not_mark_output_stale() -> None:
    messages: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.process_status_var = SimpleNamespace(set=lambda value: messages.append(value))
    gui._clear_palette_undo_state = lambda: messages.append("clear")
    gui._mark_output_stale = lambda message=None: messages.append(f"stale:{message}")
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

    assert messages == ["Palette reduction settings changed. Click Reduce Palette to rebuild the palette.", "persist", "refresh"]


def test_downsample_setting_change_marks_downsample_stale_and_clears_cache() -> None:
    messages: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.prepared_input_cache = object()
    gui.prepared_input_cache_key = ("cached",)
    gui.process_status_var = SimpleNamespace(set=lambda value: messages.append(value))
    gui._clear_palette_undo_state = lambda: messages.append("clear")
    gui._mark_output_stale = lambda message=None: messages.append(f"stale:{message}")
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


def test_generate_override_palette_uses_structured_preview_for_rampforge_8(monkeypatch) -> None:
    captured: dict[str, object] = {}
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.image_state = "processed_current"
    gui.prepared_input_cache = SimpleNamespace(
        reduced_labels=[
            [0xAA5533, 0x4477AA],
            [0x55AA55, 0xAA3355],
        ]
    )
    gui.session = SimpleNamespace(current=PreviewSettings(palette_reduction_colors=24, quantizer="rampforge-8"))
    gui._apply_structured_palette_preview = lambda palette, *, message, mark_stale=True, capture_undo=False: captured.update(
        {
            "palette": palette,
            "message": message,
            "mark_stale": mark_stale,
            "capture_undo": capture_undo,
        }
    )
    palette = generate_structured_palette(
        gui.prepared_input_cache.reduced_labels,
        key_colors=[0xAA5533, 0x4477AA],
        generated_shades=6,
        contrast_bias=0.7,
        source_label="Generated: RampForge-8",
        source_mode="rampforge-8",
    ).palette

    monkeypatch.setattr(
        app_module,
        "generate_override_palette",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("flat override path should not run")),
    )

    def fake_generate(labels, colors, *, method, workspace=None, source_label):
        captured["labels"] = labels
        captured["colors"] = colors
        captured["method"] = method
        captured["source_label"] = source_label
        return palette

    monkeypatch.setattr(app_module, "generate_palette_source", fake_generate)

    PixelFixGui._generate_override_palette_from_settings(gui, gui.session.current)

    assert captured["labels"] == gui.prepared_input_cache.reduced_labels
    assert captured["colors"] == 0
    assert captured["method"] == "rampforge-8"
    assert captured["source_label"] == "Generated: RampForge-8"
    assert captured["palette"].source_mode == "rampforge-8"
    assert captured["mark_stale"] is True
    assert captured["message"] == (
        f"Generated a {palette.palette_size()}-colour RampForge-8 palette across {len(palette.ramps)} ramps. "
        "Click Apply Palette to use it."
    )


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


def test_load_default_palette_uses_default_resource_entry() -> None:
    captured: dict[str, object] = {}
    default_path = str(Path("palettes/default.gpl").resolve())
    entry = app_module.PaletteCatalogEntry(
        label="Default",
        path=Path(default_path),
        colors=(0x112233, 0x445566),
        menu_path=(),
        source_label="Default",
    )
    gui = PixelFixGui.__new__(PixelFixGui)
    gui._builtin_palette_by_path = {default_path: entry}
    gui._resource_path = lambda name: Path(default_path) if name == app_module.DEFAULT_PALETTE_RESOURCE else Path(name)
    gui._resolve_palette_path = lambda value: default_path
    gui._set_active_palette = lambda palette, source, path_value: captured.update(
        {
            "palette": list(palette) if palette is not None else None,
            "source": source,
            "path_value": path_value,
        }
    )

    loaded = PixelFixGui._load_default_palette(gui)

    assert loaded is True
    assert captured["palette"] == [0x112233, 0x445566]
    assert captured["source"] == "Built-in: Default"
    assert captured["path_value"] == default_path


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


def test_open_image_path_preserves_palette_and_clears_transparency_state(monkeypatch, tmp_path) -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_PENCIL
    gui.active_palette = [0x112233]
    gui.active_palette_source = "Loaded"
    gui.active_palette_path = "example.gpl"
    gui.transparent_colors = {0x112233}
    gui._palette_selection_indices = {0}
    gui._displayed_palette = [0x112233]
    gui.advanced_palette_preview = object()
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
    gui._update_palette_strip = lambda: None
    gui.redraw_canvas = lambda: None
    gui._refresh_action_states = lambda: None
    gui._clear_palette_undo_state = lambda: None

    monkeypatch.setattr(app_module, "load_png_rgba_image", lambda _path: Image.new("RGBA", (4, 4), (1, 2, 3, 255)))

    image_path = tmp_path / "sprite.png"
    image_path.write_text("", encoding="utf-8")

    PixelFixGui._open_image_path(gui, image_path)

    assert gui.active_palette == [0x112233]
    assert gui.active_palette_source == "Loaded"
    assert gui.active_palette_path == "example.gpl"
    assert gui.advanced_palette_preview is not None
    assert gui.transparent_colors == set()
    assert gui.downsample_result is None
    assert gui.palette_result is None
    assert gui.canvas_tool_mode is None
    assert gui.palette_add_pick_mode is False
    assert gui.transparency_pick_mode is False
    assert gui.image_state == "loaded_original"
    assert gui.original_display_image is not None


def test_canvas_motion_updates_live_pick_preview() -> None:
    cursor_updates: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.dragging = False
    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_ACTIVE_COLOR_PICK
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui.pick_preview_var = TextVarStub("")
    gui.pick_preview_rgb_var = TextVarStub("")
    gui.pick_preview_position_var = TextVarStub("")
    gui.pick_preview_frame = PickerPreviewFrameStub()
    gui.pick_preview_empty_label = PickerPreviewFrameStub()
    gui.pick_preview_swatch = PickerPreviewSwatchStub()
    gui.canvas = SimpleNamespace(configure=lambda **kwargs: cursor_updates.append(kwargs["cursor"]))
    gui._sample_point_from_preview = (
        lambda x, y, *, view: (12, 18, 0x336699) if (x, y, view) == (12, 18, "processed") else None
    )

    PixelFixGui._on_canvas_motion(gui, SimpleNamespace(x=12, y=18))

    assert cursor_updates == ["crosshair"]
    assert gui.pick_preview_var.value == "#336699"
    assert gui.pick_preview_rgb_var.value == "RGB 51,102,153"
    assert gui.pick_preview_position_var.value == "X12 Y18"
    assert gui.pick_preview_frame.manager == "pack"
    assert gui.pick_preview_empty_label.manager == ""
    assert gui.pick_preview_swatch.config["bg"] == "#336699"


def test_canvas_leave_clears_live_pick_preview() -> None:
    cursor_updates: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.dragging = False
    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_ACTIVE_COLOR_PICK
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui.pick_preview_var = TextVarStub("")
    gui.pick_preview_rgb_var = TextVarStub("")
    gui.pick_preview_position_var = TextVarStub("")
    gui.pick_preview_frame = PickerPreviewFrameStub()
    gui.pick_preview_empty_label = PickerPreviewFrameStub()
    gui.pick_preview_swatch = PickerPreviewSwatchStub()
    gui.canvas = SimpleNamespace(configure=lambda **kwargs: cursor_updates.append(kwargs["cursor"]))
    gui._sample_point_from_preview = lambda _x, _y, *, view: (4, 6, 0x224466) if view == "processed" else None

    PixelFixGui._on_canvas_motion(gui, SimpleNamespace(x=4, y=6))
    PixelFixGui._on_canvas_leave(gui, SimpleNamespace())

    assert gui.pick_preview_var.value == ""
    assert gui.pick_preview_rgb_var.value == ""
    assert gui.pick_preview_position_var.value == ""
    assert gui.pick_preview_frame.manager == ""
    assert gui.pick_preview_empty_label.manager == "pack"
    assert cursor_updates == ["crosshair", ""]


def test_refresh_tool_options_panel_shows_only_relevant_controls() -> None:
    gui = _make_tool_options_gui(None)

    PixelFixGui._refresh_tool_options_panel(gui)

    assert gui.options_helper_label.manager == "pack"
    assert gui.options_helper_var.value == "Select a tool to see its options."

    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_PENCIL
    PixelFixGui._refresh_tool_options_panel(gui)
    assert gui.brush_width_row.manager == "pack"
    assert gui.brush_shape_row.manager == "pack"
    assert gui.options_helper_label.manager == ""

    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_ACTIVE_COLOR_PICK
    PixelFixGui._refresh_tool_options_panel(gui)
    assert gui.pick_preview_empty_label.manager == "pack"
    assert gui.brush_width_row.manager == ""

    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_BUCKET
    PixelFixGui._refresh_tool_options_panel(gui)
    assert gui.options_helper_label.manager == "pack"
    assert gui.options_helper_var.value == "Bucket has no options."

    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_RECTANGLE
    PixelFixGui._refresh_tool_options_panel(gui)
    assert gui.brush_width_row.manager == "pack"
    assert gui.brush_shape_row.manager == ""

    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_LINE
    PixelFixGui._refresh_tool_options_panel(gui)
    assert gui.brush_width_row.manager == "pack"
    assert gui.brush_shape_row.manager == ""

    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_GRADIENT
    PixelFixGui._refresh_tool_options_panel(gui)
    assert gui.options_helper_label.manager == "pack"
    assert gui.options_helper_var.value == "Gradient tool is not implemented yet."


def test_add_outline_options_require_valid_palette_selection_before_apply() -> None:
    gui = _make_tool_options_gui(
        app_module.CANVAS_TOOL_MODE_ADD_OUTLINE,
        outline_mode=app_module.OUTLINE_COLOUR_MODE_PALETTE,
        selected_outline_label=None,
    )

    PixelFixGui._refresh_outline_control_states(gui)
    PixelFixGui._refresh_tool_options_panel(gui)

    assert gui.options_apply_button.state == app_module.tk.DISABLED
    assert gui.options_apply_row.manager == "pack"
    assert gui.options_helper_label.manager == "pack"
    assert gui.options_helper_var.value == "Select exactly one palette colour to use Selected outline colour."

    gui.outline_colour_mode_var.set(app_module.OUTLINE_COLOUR_MODE_ADAPTIVE)
    gui.outline_colour_mode_display_var.set(app_module.OUTLINE_COLOUR_MODE_LABELS[app_module.OUTLINE_COLOUR_MODE_ADAPTIVE])
    PixelFixGui._refresh_outline_control_states(gui)
    PixelFixGui._refresh_tool_options_panel(gui)

    assert gui.options_apply_button.state == app_module.tk.NORMAL
    assert gui.outline_adaptive_row.manager == "pack"
    assert gui.options_helper_label.manager == ""


def test_canvas_click_without_image_does_not_open_file_dialog() -> None:
    calls: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.original_display_image = None
    gui.open_image = lambda: calls.append("open")

    PixelFixGui._on_canvas_press(gui, SimpleNamespace(x=10, y=12))

    assert calls == []


def test_coerce_mouse_button_action_falls_back_to_default_for_invalid_values() -> None:
    assert (
        PixelFixGui._coerce_mouse_button_action(
            "invalid",
            default=app_module.MOUSE_BUTTON_DEFAULT_RIGHT_ACTION,
        )
        == app_module.MOUSE_BUTTON_DEFAULT_RIGHT_ACTION
    )
    assert (
        PixelFixGui._coerce_mouse_button_action(
            None,
            default=app_module.MOUSE_BUTTON_DEFAULT_MIDDLE_ACTION,
        )
        == app_module.MOUSE_BUTTON_DEFAULT_MIDDLE_ACTION
    )


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
    gui.outline_pixel_perfect_var = SimpleNamespace(get=lambda: False)
    gui.outline_colour_mode_var = SimpleNamespace(get=lambda: app_module.OUTLINE_COLOUR_MODE_ADAPTIVE)
    gui.outline_adaptive_darken_percent_var = SimpleNamespace(get=lambda: 85)
    gui.outline_add_generated_colours_var = SimpleNamespace(get=lambda: True)
    gui.outline_remove_brightness_threshold_enabled_var = SimpleNamespace(get=lambda: True)
    gui.outline_remove_brightness_threshold_percent_var = SimpleNamespace(get=lambda: 45)
    gui.outline_remove_brightness_threshold_direction_var = SimpleNamespace(
        get=lambda: app_module.OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_BRIGHT
    )
    gui.brush_width_var = SimpleNamespace(get=lambda: 7)
    gui.brush_shape_var = SimpleNamespace(get=lambda: app_module.BRUSH_SHAPE_ROUND)
    gui.view_var = SimpleNamespace(get=lambda: "processed")
    gui.right_mouse_action_var = SimpleNamespace(get=lambda: app_module.MOUSE_BUTTON_ACTION_SWAP_COLORS)
    gui.middle_mouse_action_var = SimpleNamespace(get=lambda: app_module.MOUSE_BUTTON_ACTION_ERASER)
    gui.primary_color_label = 0x112233
    gui.secondary_color_label = 0x445566
    gui.transparent_color_slot = app_module.ACTIVE_COLOR_SLOT_SECONDARY
    gui.active_color_slot = app_module.ACTIVE_COLOR_SLOT_PRIMARY
    gui.active_palette_source = "Built-in: Default"
    gui.active_palette_path = "palettes/default.gpl"
    gui.recent_files = ["example.png"]

    monkeypatch.setattr(app_module, "save_app_state", lambda data: captured.update(data))

    PixelFixGui._persist_state(gui)

    settings = captured["settings"]
    assert "palette_brightness" not in settings
    assert "palette_contrast" not in settings
    assert "palette_hue" not in settings
    assert "palette_saturation" not in settings
    assert captured["selection_threshold"] == 30
    assert captured["outline_pixel_perfect"] is False
    assert captured["outline_colour_mode"] == app_module.OUTLINE_COLOUR_MODE_ADAPTIVE
    assert captured["outline_adaptive_darken_percent"] == 85
    assert captured["outline_add_generated_colours"] is True
    assert captured["outline_remove_brightness_threshold_enabled"] is True
    assert captured["outline_remove_brightness_threshold_percent"] == 45
    assert captured["outline_remove_brightness_threshold_direction"] == app_module.OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_BRIGHT
    assert captured["brush_width"] == 7
    assert captured["primary_color_label"] == 0x112233
    assert captured["secondary_color_label"] == 0x445566
    assert captured["transparent_color_slot"] == app_module.ACTIVE_COLOR_SLOT_SECONDARY
    assert captured["active_color_slot"] == app_module.ACTIVE_COLOR_SLOT_PRIMARY
    assert captured["brush_shape"] == app_module.BRUSH_SHAPE_ROUND
    assert captured["right_mouse_action"] == app_module.MOUSE_BUTTON_ACTION_SWAP_COLORS
    assert captured["middle_mouse_action"] == app_module.MOUSE_BUTTON_ACTION_ERASER
    assert captured["active_palette_source"] == "Built-in: Default"
    assert captured["active_palette_path"] == "palettes/default.gpl"


def test_assigned_right_click_starts_and_releases_quick_compare() -> None:
    redraws: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.right_mouse_action_var = SimpleNamespace(get=lambda: app_module.MOUSE_BUTTON_ACTION_VIEW_ORIGINAL)
    gui.quick_compare_active = False
    gui._mouse_button_action_state = None
    gui._brush_stroke_active = False
    gui._shape_drag_active = False
    gui.dragging = False
    gui.view_var = SimpleNamespace(get=lambda: "processed")
    gui._current_output_image = lambda: object()
    gui.redraw_canvas = lambda: redraws.append("redraw")

    PixelFixGui._on_canvas_assigned_button_press(gui, SimpleNamespace(), app_module.CANVAS_MOUSE_BUTTON_RIGHT)

    assert gui.quick_compare_active is True
    assert gui._mouse_button_action_state == app_module.CanvasMouseActionState(
        app_module.CANVAS_MOUSE_BUTTON_RIGHT,
        app_module.MOUSE_BUTTON_ACTION_VIEW_ORIGINAL,
    )
    assert redraws == ["redraw"]

    PixelFixGui._on_canvas_assigned_button_release(gui, SimpleNamespace(), app_module.CANVAS_MOUSE_BUTTON_RIGHT)

    assert gui.quick_compare_active is False
    assert gui._mouse_button_action_state is None
    assert redraws == ["redraw", "redraw"]


def test_assigned_middle_click_samples_visible_preview_into_active_slot() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.middle_mouse_action_var = SimpleNamespace(get=lambda: app_module.MOUSE_BUTTON_ACTION_SAMPLE_COLOR)
    gui.original_display_image = object()
    gui.active_color_slot = app_module.ACTIVE_COLOR_SLOT_PRIMARY
    gui.primary_color_label = 0x112233
    gui.secondary_color_label = 0x445566
    gui.transparent_color_slot = None
    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_LINE
    gui._mouse_button_action_state = None
    gui._brush_stroke_active = False
    gui._shape_drag_active = False
    gui.dragging = False
    gui.quick_compare_active = False
    gui._get_effective_view = lambda: "original"
    gui._sample_label_from_preview = lambda x, y, *, view: 0x336699 if (x, y, view) == (5, 7, "original") else None
    gui._refresh_active_color_preview = lambda: None
    gui._schedule_state_persist_if_ready = lambda: None
    gui._refresh_action_states = lambda: None

    PixelFixGui._on_canvas_assigned_button_press(gui, SimpleNamespace(x=5, y=7), app_module.CANVAS_MOUSE_BUTTON_MIDDLE)

    assert gui.primary_color_label == 0x336699
    assert gui.secondary_color_label == 0x445566
    assert gui.canvas_tool_mode == app_module.CANVAS_TOOL_MODE_LINE


def test_assigned_sample_color_ignores_missing_pixel() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.middle_mouse_action_var = SimpleNamespace(get=lambda: app_module.MOUSE_BUTTON_ACTION_SAMPLE_COLOR)
    gui.original_display_image = object()
    gui.active_color_slot = app_module.ACTIVE_COLOR_SLOT_PRIMARY
    gui.primary_color_label = 0x112233
    gui.secondary_color_label = 0x445566
    gui.transparent_color_slot = None
    gui._mouse_button_action_state = None
    gui._brush_stroke_active = False
    gui._shape_drag_active = False
    gui.dragging = False
    gui.quick_compare_active = False
    gui._get_effective_view = lambda: "processed"
    gui._sample_label_from_preview = lambda *_args, **_kwargs: None
    gui._refresh_active_color_preview = lambda: None
    gui._schedule_state_persist_if_ready = lambda: None
    gui._refresh_action_states = lambda: None

    PixelFixGui._on_canvas_assigned_button_press(gui, SimpleNamespace(x=5, y=7), app_module.CANVAS_MOUSE_BUTTON_MIDDLE)

    assert gui.primary_color_label == 0x112233
    assert gui.secondary_color_label == 0x445566


def test_assigned_swap_colors_swaps_without_changing_selected_tool() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.right_mouse_action_var = SimpleNamespace(get=lambda: app_module.MOUSE_BUTTON_ACTION_SWAP_COLORS)
    gui.primary_color_label = 0x112233
    gui.secondary_color_label = 0x445566
    gui.transparent_color_slot = app_module.ACTIVE_COLOR_SLOT_SECONDARY
    gui.active_color_slot = app_module.ACTIVE_COLOR_SLOT_PRIMARY
    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_RECTANGLE
    gui._mouse_button_action_state = None
    gui._brush_stroke_active = False
    gui._shape_drag_active = False
    gui.dragging = False
    gui.quick_compare_active = False
    gui._refresh_active_color_preview = lambda: None
    gui._schedule_state_persist_if_ready = lambda: None
    gui._refresh_action_states = lambda: None

    PixelFixGui._on_canvas_assigned_button_press(gui, SimpleNamespace(), app_module.CANVAS_MOUSE_BUTTON_RIGHT)

    assert gui.primary_color_label == 0x445566
    assert gui.secondary_color_label == 0x112233
    assert gui.transparent_color_slot == app_module.ACTIVE_COLOR_SLOT_PRIMARY
    assert gui.canvas_tool_mode == app_module.CANVAS_TOOL_MODE_RECTANGLE


def test_assigned_eraser_uses_brush_settings_without_changing_selected_tool(monkeypatch) -> None:
    calls: list[tuple[str, int, str]] = []
    cursor_updates: list[str] = []
    refreshes: list[str] = []
    current_result = object()
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.right_mouse_action_var = SimpleNamespace(get=lambda: app_module.MOUSE_BUTTON_ACTION_ERASER)
    gui.original_display_image = object()
    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_PENCIL
    gui._mouse_button_action_state = None
    gui._brush_stroke_active = False
    gui._shape_drag_active = False
    gui.dragging = False
    gui.quick_compare_active = False
    gui.transparent_colors = set()
    gui.brush_width_var = SimpleNamespace(get=lambda: 7)
    gui.brush_shape_var = SimpleNamespace(get=lambda: app_module.BRUSH_SHAPE_ROUND)
    gui.view_var = SimpleNamespace(get=lambda: "processed")
    gui.canvas = SimpleNamespace(configure=lambda **kwargs: cursor_updates.append(kwargs["cursor"]))
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))
    gui._preview_image_coordinates = lambda x, y, *, view, clamp=False: (x, y) if view == "processed" else None
    gui._current_output_result = lambda: current_result
    gui._set_current_output_result = lambda updated: refreshes.append("set")
    gui._refresh_output_display_images = lambda: refreshes.append("output")
    gui._refresh_current_output_display_image = lambda: refreshes.append("current")
    gui.redraw_canvas = lambda: refreshes.append("redraw")
    gui._capture_palette_undo_state = lambda: refreshes.append("capture")
    gui._clear_palette_undo_state = lambda: refreshes.append("clear")
    gui._refresh_action_states = lambda: refreshes.append("actions")
    gui._cursor_for_pointer = lambda: "open"

    monkeypatch.setattr(
        app_module,
        "apply_eraser_operation",
        lambda current, x, y, *, width, shape: (calls.append(("press", width, shape)) or (current, 1)),
    )
    monkeypatch.setattr(
        app_module,
        "apply_eraser_operations",
        lambda current, points, *, width, shape: (
            calls.append(("press" if len(points) == 1 else "drag", width, shape)) or (current, 1 if len(points) == 1 else 2)
        ),
    )

    PixelFixGui._on_canvas_assigned_button_press(gui, SimpleNamespace(x=1, y=1), app_module.CANVAS_MOUSE_BUTTON_RIGHT)
    PixelFixGui._on_canvas_assigned_button_drag(gui, SimpleNamespace(x=3, y=1), app_module.CANVAS_MOUSE_BUTTON_RIGHT)
    PixelFixGui._on_canvas_assigned_button_release(gui, SimpleNamespace(), app_module.CANVAS_MOUSE_BUTTON_RIGHT)

    assert calls == [("press", 7, app_module.BRUSH_SHAPE_ROUND), ("drag", 7, app_module.BRUSH_SHAPE_ROUND)]
    assert gui.canvas_tool_mode == app_module.CANVAS_TOOL_MODE_PENCIL
    assert gui.process_status_var.value == "Eraser changed 3 pixels. Press Undo to restore it."
    assert gui._mouse_button_action_state is None
    assert cursor_updates == ["crosshair", "open"]


def test_assigned_eraser_is_ignored_while_shape_drag_is_active() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.right_mouse_action_var = SimpleNamespace(get=lambda: app_module.MOUSE_BUTTON_ACTION_ERASER)
    gui.original_display_image = object()
    gui._mouse_button_action_state = None
    gui._brush_stroke_active = False
    gui._shape_drag_active = True
    gui.dragging = False
    gui.quick_compare_active = False
    gui._get_effective_view = lambda: "processed"
    gui._current_output_result = lambda: object()
    gui._preview_image_coordinates = lambda *_args, **_kwargs: (1, 1)
    gui._start_brush_stroke = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Should not start erasing"))

    PixelFixGui._on_canvas_assigned_button_press(gui, SimpleNamespace(x=1, y=1), app_module.CANVAS_MOUSE_BUTTON_RIGHT)

    assert gui._mouse_button_action_state is None


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


def test_palette_canvas_plain_click_assigns_primary_colour() -> None:
    updates: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui._displayed_palette = [0x111111, 0x222222]
    gui._palette_hit_regions = [(0, 0, 9, 9), (10, 0, 19, 9)]
    gui._palette_selection_indices = set()
    gui._palette_selection_anchor_index = None
    gui.primary_color_label = 0xFFFFFF
    gui.secondary_color_label = 0xFFFFFF
    gui.transparent_color_slot = app_module.ACTIVE_COLOR_SLOT_SECONDARY
    gui.active_color_slot = app_module.ACTIVE_COLOR_SLOT_PRIMARY
    gui._update_palette_strip = lambda: updates.append("palette")
    gui._refresh_action_states = lambda: updates.append("refresh")

    PixelFixGui._on_palette_canvas_click(gui, SimpleNamespace(x=15, y=5, state=0))

    assert gui._palette_selection_indices == {1}
    assert gui._palette_selection_anchor_index == 1
    assert gui.primary_color_label == 0x222222
    assert updates == ["refresh", "palette"]


def test_palette_canvas_right_click_assigns_secondary_without_clearing_selection() -> None:
    updates: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui._displayed_palette = [0x111111, 0x222222]
    gui._palette_hit_regions = [(0, 0, 9, 9), (10, 0, 19, 9)]
    gui._palette_selection_indices = {0}
    gui._palette_selection_anchor_index = 0
    gui.primary_color_label = 0xFFFFFF
    gui.secondary_color_label = 0xFFFFFF
    gui.transparent_color_slot = app_module.ACTIVE_COLOR_SLOT_SECONDARY
    gui.active_color_slot = app_module.ACTIVE_COLOR_SLOT_PRIMARY
    gui._refresh_action_states = lambda: updates.append("refresh")

    PixelFixGui._on_palette_canvas_right_click(gui, SimpleNamespace(x=15, y=5))

    assert gui._palette_selection_indices == {0}
    assert gui._palette_selection_anchor_index == 0
    assert gui.secondary_color_label == 0x222222
    assert updates == ["refresh"]


def test_invert_palette_selection_reverses_selected_and_unselected_swatches() -> None:
    messages: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui._displayed_palette = [0x111111, 0x222222, 0x333333, 0x444444]
    gui._palette_selection_indices = {1, 3}
    gui._palette_selection_anchor_index = 1
    gui.process_status_var = SimpleNamespace(set=lambda value: messages.append(value))
    gui._update_palette_strip = lambda: messages.append("palette")
    gui._refresh_action_states = lambda: messages.append("refresh")

    PixelFixGui._invert_palette_selection(gui)

    assert gui._palette_selection_indices == {0, 2}
    assert gui._palette_selection_anchor_index == 0
    assert messages == ["palette", "refresh", "Inverted palette selection. 2 palette colours selected."]


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

    PixelFixGui.select_current_palette(gui, PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES)

    assert gui._palette_selection_indices == {2, 3}
    assert gui._palette_selection_anchor_index == 2
    assert (
        gui.process_status_var.value
        == f"Selected 2 palette colours by {PALETTE_SELECT_LABELS[PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES]} at 50%."
    )
    assert updates == ["reset", "palette", "refresh"]


def test_select_current_palette_similarity_mode_clears_selection_when_no_cluster_matches() -> None:
    updates: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.workspace = ColorWorkspace()
    gui.selection_threshold_var = SimpleNamespace(get=lambda: 100)
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))
    gui._get_display_palette = lambda: ([0x101010, 0x80FF00, 0xB040A0, 0x00B0FF], "Generated")
    gui._palette_selection_indices = {1, 2}
    gui._palette_selection_anchor_index = 1
    gui._reset_palette_ctrl_drag_state = lambda: updates.append("reset")
    gui._update_palette_strip = lambda: updates.append("palette")
    gui._refresh_action_states = lambda: updates.append("refresh")

    PixelFixGui.select_current_palette(gui, PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES)

    assert gui._palette_selection_indices == set()
    assert gui._palette_selection_anchor_index is None
    assert gui.process_status_var.value == "No near-duplicate palette colours found at 100%."
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


def test_refresh_brush_control_states_enables_bucket_and_shape_buttons() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.image_state = "processed_current"
    gui.primary_color_label = 0x112233
    gui.secondary_color_label = 0x445566
    gui.transparent_color_slot = app_module.ACTIVE_COLOR_SLOT_SECONDARY
    gui.bucket_button = WidgetStub()
    gui.pencil_button = WidgetStub()
    gui.eraser_button = WidgetStub()
    gui.circle_button = WidgetStub()
    gui.square_button = WidgetStub()
    gui.line_button = WidgetStub()
    gui.gradient_button = WidgetStub()
    gui.brush_width_spinbox = WidgetStub()
    gui.brush_shape_dropdown_button = WidgetStub()
    gui._current_output_result = lambda: object()

    PixelFixGui._refresh_brush_control_states(gui)

    assert gui.bucket_button.state == app_module.tk.NORMAL
    assert gui.pencil_button.state == app_module.tk.NORMAL
    assert gui.eraser_button.state == app_module.tk.NORMAL
    assert gui.circle_button.state == app_module.tk.NORMAL
    assert gui.square_button.state == app_module.tk.NORMAL
    assert gui.line_button.state == app_module.tk.NORMAL
    assert gui.gradient_button.state == app_module.tk.NORMAL
    assert gui.brush_width_spinbox.state == "normal"
    assert gui.brush_shape_dropdown_button.state == app_module.tk.NORMAL


def test_refresh_brush_control_states_disables_primary_colour_tools_when_primary_is_transparent() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.image_state = "processed_current"
    gui.primary_color_label = 0x112233
    gui.secondary_color_label = 0x445566
    gui.transparent_color_slot = app_module.ACTIVE_COLOR_SLOT_PRIMARY
    gui.bucket_button = WidgetStub()
    gui.pencil_button = WidgetStub()
    gui.eraser_button = WidgetStub()
    gui.circle_button = WidgetStub()
    gui.square_button = WidgetStub()
    gui.line_button = WidgetStub()
    gui.gradient_button = WidgetStub()
    gui.brush_width_spinbox = WidgetStub()
    gui.brush_shape_dropdown_button = WidgetStub()
    gui._current_output_result = lambda: object()

    PixelFixGui._refresh_brush_control_states(gui)

    assert gui.bucket_button.state == app_module.tk.DISABLED
    assert gui.pencil_button.state == app_module.tk.DISABLED
    assert gui.eraser_button.state == app_module.tk.NORMAL
    assert gui.circle_button.state == app_module.tk.DISABLED
    assert gui.square_button.state == app_module.tk.DISABLED
    assert gui.line_button.state == app_module.tk.DISABLED
    assert gui.gradient_button.state == app_module.tk.NORMAL


def test_refresh_action_states_enables_outline_buttons_with_processed_output_and_single_selection() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.image_state = "processed_current"
    gui.original_grid = _sample_grid()
    gui.prepared_input_cache = object()
    gui._palette_undo_state = None
    gui._palette_selection_indices = {0}
    gui._displayed_palette = [0x112233, 0x445566]
    gui.canvas_tool_mode = None
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui.session = SimpleNamespace(history=SimpleNamespace(can_undo=lambda: False))
    gui.downsample_button = WidgetStub()
    gui.generate_override_palette_button = WidgetStub()
    gui.reduce_palette_button = WidgetStub()
    gui.transparency_button = WidgetStub()
    gui.bucket_button = WidgetStub()
    gui.pencil_button = WidgetStub()
    gui.eraser_button = WidgetStub()
    gui.circle_button = WidgetStub()
    gui.square_button = WidgetStub()
    gui.add_outline_button = WidgetStub()
    gui.remove_outline_button = WidgetStub()
    gui.brush_width_spinbox = WidgetStub()
    gui.brush_shape_dropdown_button = WidgetStub()
    gui.outline_palette_mode_button = WidgetStub()
    gui.outline_adaptive_mode_button = WidgetStub()
    gui.outline_adaptive_darken_spinbox = WidgetStub()
    gui.outline_adaptive_darken_label = WidgetStub()
    gui.outline_add_generated_colours_toggle = WidgetStub()
    gui.outline_remove_brightness_threshold_toggle = WidgetStub()
    gui.outline_remove_brightness_threshold_spinbox = WidgetStub()
    gui.outline_remove_brightness_direction_dark_button = WidgetStub()
    gui.outline_remove_brightness_direction_bright_button = WidgetStub()
    gui.zoom_in_button = WidgetStub()
    gui.zoom_out_button = WidgetStub()
    gui.add_palette_color_button = WidgetStub()
    gui.merge_palette_button = WidgetStub()
    gui.ramp_palette_button = WidgetStub()
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
        "preferences_mouse_buttons": MenuStub(),
    }
    gui._menu_bar = MenuStub()
    gui._refresh_primary_button_style = lambda _button: None
    gui._palette_is_override_mode = lambda: False
    gui._has_palette_source = lambda: True
    gui._current_output_result = lambda: object()
    gui.outline_colour_mode_var = SimpleNamespace(get=lambda: app_module.OUTLINE_COLOUR_MODE_PALETTE)
    gui.outline_remove_brightness_threshold_enabled_var = SimpleNamespace(get=lambda: False)

    PixelFixGui._refresh_action_states(gui)

    assert gui.add_outline_button.state == app_module.tk.NORMAL
    assert gui.remove_outline_button.state == app_module.tk.NORMAL
    assert gui.bucket_button.state == app_module.tk.NORMAL
    assert gui.pencil_button.state == app_module.tk.NORMAL
    assert gui.eraser_button.state == app_module.tk.NORMAL
    assert gui.circle_button.state == app_module.tk.NORMAL
    assert gui.square_button.state == app_module.tk.NORMAL
    assert gui.merge_palette_button.state == app_module.tk.DISABLED
    assert gui.ramp_palette_button.state == app_module.tk.NORMAL
    assert gui.brush_width_spinbox.state == "normal"
    assert gui.brush_shape_dropdown_button.state == app_module.tk.NORMAL
    assert gui.outline_adaptive_darken_spinbox.state == "disabled"
    assert gui.outline_remove_brightness_threshold_toggle.state == app_module.tk.NORMAL
    assert gui.outline_remove_brightness_threshold_spinbox.state == "disabled"
    assert gui.outline_remove_brightness_direction_dark_button.state == "disabled"
    assert gui._menu_items["preferences"].states["Mouse Buttons"] == app_module.tk.NORMAL
    assert gui._menu_items["preferences_mouse_buttons"].states["Right Mouse Button"] == app_module.tk.NORMAL
    assert gui._menu_items["preferences_mouse_buttons"].states["Middle Mouse Button"] == app_module.tk.NORMAL


def test_refresh_action_states_disables_palette_size_for_rampforge_8() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.image_state = "processed_current"
    gui.original_grid = _sample_grid()
    gui.prepared_input_cache = object()
    gui._palette_undo_state = None
    gui._palette_selection_indices = set()
    gui._displayed_palette = [0x112233]
    gui.session = SimpleNamespace(
        current=PreviewSettings(quantizer="rampforge-8"),
        history=SimpleNamespace(can_undo=lambda: False, can_redo=lambda: False),
    )
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
        "preferences_mouse_buttons": MenuStub(),
    }
    gui._menu_bar = MenuStub()
    gui._has_palette_source = lambda: True
    gui._current_output_result = lambda: object()
    gui._outline_adaptive_enabled = lambda: False
    gui._set_tool_button_enabled = lambda *_args, **_kwargs: None
    gui._refresh_brush_control_states = lambda: None
    gui._refresh_outline_control_states = lambda: None
    gui._refresh_tool_button_styles = lambda: None

    PixelFixGui._refresh_action_states(gui)

    assert gui.palette_reduction_spinbox.state == "disabled"

    gui.session.current = PreviewSettings(quantizer="kmeans")
    PixelFixGui._refresh_action_states(gui)

    assert gui.palette_reduction_spinbox.state == "normal"


def test_refresh_action_states_enables_merge_with_multiple_selected_swatches() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.image_state = "processed_current"
    gui.original_grid = _sample_grid()
    gui.prepared_input_cache = object()
    gui._palette_undo_state = None
    gui._palette_selection_indices = {0, 1}
    gui._displayed_palette = [0x112233, 0x445566]
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui.session = SimpleNamespace(history=SimpleNamespace(can_undo=lambda: False))
    gui.downsample_button = WidgetStub()
    gui.generate_override_palette_button = WidgetStub()
    gui.reduce_palette_button = WidgetStub()
    gui.transparency_button = WidgetStub()
    gui.bucket_button = WidgetStub()
    gui.pencil_button = WidgetStub()
    gui.eraser_button = WidgetStub()
    gui.circle_button = WidgetStub()
    gui.square_button = WidgetStub()
    gui.add_outline_button = WidgetStub()
    gui.remove_outline_button = WidgetStub()
    gui.brush_width_spinbox = WidgetStub()
    gui.brush_shape_dropdown_button = WidgetStub()
    gui.outline_palette_mode_button = WidgetStub()
    gui.outline_adaptive_mode_button = WidgetStub()
    gui.outline_adaptive_darken_spinbox = WidgetStub()
    gui.outline_adaptive_darken_label = WidgetStub()
    gui.outline_add_generated_colours_toggle = WidgetStub()
    gui.outline_remove_brightness_threshold_toggle = WidgetStub()
    gui.outline_remove_brightness_threshold_spinbox = WidgetStub()
    gui.outline_remove_brightness_direction_dark_button = WidgetStub()
    gui.outline_remove_brightness_direction_bright_button = WidgetStub()
    gui.zoom_in_button = WidgetStub()
    gui.zoom_out_button = WidgetStub()
    gui.add_palette_color_button = WidgetStub()
    gui.merge_palette_button = WidgetStub()
    gui.ramp_palette_button = WidgetStub()
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
    gui.outline_colour_mode_var = SimpleNamespace(get=lambda: app_module.OUTLINE_COLOUR_MODE_PALETTE)
    gui.outline_remove_brightness_threshold_enabled_var = SimpleNamespace(get=lambda: False)

    PixelFixGui._refresh_action_states(gui)

    assert gui.merge_palette_button.state == app_module.tk.NORMAL
    assert gui.ramp_palette_button.state == app_module.tk.NORMAL
    assert gui.add_outline_button.state == app_module.tk.NORMAL


def test_refresh_action_states_updates_palette_action_button_icons() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.image_state = "processed_current"
    gui.original_grid = _sample_grid()
    gui.prepared_input_cache = object()
    gui._palette_undo_state = None
    gui._palette_selection_indices = {0}
    gui._displayed_palette = [0x112233, 0x445566]
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui.session = SimpleNamespace(
        history=SimpleNamespace(can_undo=lambda: False, can_redo=lambda: False),
        current=PreviewSettings(),
    )
    gui.downsample_button = WidgetStub()
    gui.generate_override_palette_button = WidgetStub()
    gui.reduce_palette_button = WidgetStub()
    gui.transparency_button = WidgetStub()
    gui.bucket_button = WidgetStub()
    gui.pencil_button = WidgetStub()
    gui.eraser_button = WidgetStub()
    gui.circle_button = WidgetStub()
    gui.square_button = WidgetStub()
    gui.line_button = WidgetStub()
    gui.gradient_button = WidgetStub()
    gui.add_outline_button = WidgetStub()
    gui.remove_outline_button = WidgetStub()
    gui.brush_width_spinbox = WidgetStub()
    gui.brush_shape_dropdown_button = WidgetStub()
    gui.outline_palette_mode_button = WidgetStub()
    gui.outline_adaptive_mode_button = WidgetStub()
    gui.outline_adaptive_darken_spinbox = WidgetStub()
    gui.outline_adaptive_darken_label = WidgetStub()
    gui.outline_add_generated_colours_toggle = WidgetStub()
    gui.outline_remove_brightness_threshold_toggle = WidgetStub()
    gui.outline_remove_brightness_threshold_spinbox = WidgetStub()
    gui.outline_remove_brightness_direction_dark_button = WidgetStub()
    gui.outline_remove_brightness_direction_bright_button = WidgetStub()
    gui.zoom_in_button = WidgetStub()
    gui.zoom_out_button = WidgetStub()
    gui.add_palette_color_button = WidgetStub()
    gui.merge_palette_button = WidgetStub()
    gui.ramp_palette_button = WidgetStub()
    gui.select_all_palette_button = WidgetStub()
    gui.clear_palette_selection_button = WidgetStub()
    gui.invert_palette_selection_button = WidgetStub()
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
        "preferences_mouse_buttons": MenuStub(),
    }
    gui._menu_bar = MenuStub()
    gui._refresh_primary_button_style = lambda _button: None
    gui._palette_is_override_mode = lambda: False
    gui._has_palette_source = lambda: True
    gui._current_output_result = lambda: object()
    gui.outline_colour_mode_var = SimpleNamespace(get=lambda: app_module.OUTLINE_COLOUR_MODE_PALETTE)
    gui.outline_remove_brightness_threshold_enabled_var = SimpleNamespace(get=lambda: False)
    gui._palette_action_button_assets = {
        "merge_palette_button": "icon_merge.png",
        "ramp_palette_button": "icon_ramp.png",
    }
    gui._palette_action_button_enabled = {
        "merge_palette_button": True,
        "ramp_palette_button": True,
    }
    gui._palette_action_button_icon = lambda asset_name, disabled=False: f"{asset_name}:{disabled}"

    PixelFixGui._refresh_action_states(gui)

    assert gui.merge_palette_button.state is None
    assert gui.merge_palette_button.image == "icon_merge.png:True"
    assert gui.merge_palette_button.style == "PaletteActionIconDisabled.TButton"
    assert gui.ramp_palette_button.state is None
    assert gui.ramp_palette_button.image == "icon_ramp.png:False"
    assert gui.ramp_palette_button.style == "PaletteActionIcon.TButton"


def test_refresh_action_states_enables_outline_without_selection_in_adaptive_mode() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.image_state = "processed_current"
    gui.original_grid = _sample_grid()
    gui.prepared_input_cache = object()
    gui._palette_undo_state = None
    gui._palette_selection_indices = set()
    gui._displayed_palette = [0x112233, 0x445566]
    gui.canvas_tool_mode = None
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui.session = SimpleNamespace(history=SimpleNamespace(can_undo=lambda: False))
    gui.downsample_button = WidgetStub()
    gui.generate_override_palette_button = WidgetStub()
    gui.reduce_palette_button = WidgetStub()
    gui.transparency_button = WidgetStub()
    gui.bucket_button = WidgetStub()
    gui.pencil_button = WidgetStub()
    gui.eraser_button = WidgetStub()
    gui.circle_button = WidgetStub()
    gui.square_button = WidgetStub()
    gui.add_outline_button = WidgetStub()
    gui.remove_outline_button = WidgetStub()
    gui.brush_width_spinbox = WidgetStub()
    gui.brush_shape_dropdown_button = WidgetStub()
    gui.outline_palette_mode_button = WidgetStub()
    gui.outline_adaptive_mode_button = WidgetStub()
    gui.outline_adaptive_darken_spinbox = WidgetStub()
    gui.outline_adaptive_darken_label = WidgetStub()
    gui.outline_add_generated_colours_toggle = WidgetStub()
    gui.outline_remove_brightness_threshold_toggle = WidgetStub()
    gui.outline_remove_brightness_threshold_spinbox = WidgetStub()
    gui.outline_remove_brightness_direction_dark_button = WidgetStub()
    gui.outline_remove_brightness_direction_bright_button = WidgetStub()
    gui.zoom_in_button = WidgetStub()
    gui.zoom_out_button = WidgetStub()
    gui.add_palette_color_button = WidgetStub()
    gui.merge_palette_button = WidgetStub()
    gui.ramp_palette_button = WidgetStub()
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
    gui.outline_colour_mode_var = SimpleNamespace(get=lambda: app_module.OUTLINE_COLOUR_MODE_ADAPTIVE)
    gui.outline_remove_brightness_threshold_enabled_var = SimpleNamespace(get=lambda: False)

    PixelFixGui._refresh_action_states(gui)

    assert gui.add_outline_button.state == app_module.tk.NORMAL
    assert gui.pencil_button.state == app_module.tk.NORMAL
    assert gui.eraser_button.state == app_module.tk.NORMAL
    assert gui.brush_shape_dropdown_button.state == app_module.tk.NORMAL
    assert gui.outline_adaptive_darken_spinbox.state == "normal"
    assert gui.outline_remove_brightness_threshold_spinbox.state == "disabled"


def test_refresh_action_states_enables_remove_threshold_controls_when_enabled() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.image_state = "processed_current"
    gui.original_grid = _sample_grid()
    gui.prepared_input_cache = object()
    gui._palette_undo_state = None
    gui._palette_selection_indices = {0}
    gui._displayed_palette = [0x112233, 0x445566]
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui.session = SimpleNamespace(history=SimpleNamespace(can_undo=lambda: False))
    gui.downsample_button = WidgetStub()
    gui.generate_override_palette_button = WidgetStub()
    gui.reduce_palette_button = WidgetStub()
    gui.transparency_button = WidgetStub()
    gui.bucket_button = WidgetStub()
    gui.pencil_button = WidgetStub()
    gui.eraser_button = WidgetStub()
    gui.circle_button = WidgetStub()
    gui.square_button = WidgetStub()
    gui.add_outline_button = WidgetStub()
    gui.remove_outline_button = WidgetStub()
    gui.brush_width_spinbox = WidgetStub()
    gui.brush_shape_dropdown_button = WidgetStub()
    gui.outline_palette_mode_button = WidgetStub()
    gui.outline_adaptive_mode_button = WidgetStub()
    gui.outline_adaptive_darken_spinbox = WidgetStub()
    gui.outline_adaptive_darken_label = WidgetStub()
    gui.outline_add_generated_colours_toggle = WidgetStub()
    gui.outline_remove_brightness_threshold_toggle = WidgetStub()
    gui.outline_remove_brightness_threshold_spinbox = WidgetStub()
    gui.outline_remove_brightness_direction_dark_button = WidgetStub()
    gui.outline_remove_brightness_direction_bright_button = WidgetStub()
    gui.zoom_in_button = WidgetStub()
    gui.zoom_out_button = WidgetStub()
    gui.add_palette_color_button = WidgetStub()
    gui.merge_palette_button = WidgetStub()
    gui.ramp_palette_button = WidgetStub()
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
    gui.outline_colour_mode_var = SimpleNamespace(get=lambda: app_module.OUTLINE_COLOUR_MODE_PALETTE)
    gui.outline_remove_brightness_threshold_enabled_var = SimpleNamespace(get=lambda: True)

    PixelFixGui._refresh_action_states(gui)

    assert gui.outline_remove_brightness_threshold_toggle.state == app_module.tk.NORMAL
    assert gui.outline_remove_brightness_threshold_spinbox.state == "normal"
    assert gui.outline_remove_brightness_direction_dark_button.state == "normal"
    assert gui.outline_remove_brightness_direction_bright_button.state == "normal"


def test_refresh_tool_button_styles_marks_active_tool_and_view() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_RECTANGLE
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui.view_var = SimpleNamespace(get=lambda: "processed")
    gui.bucket_button = WidgetStub()
    gui.pencil_button = WidgetStub()
    gui.eraser_button = WidgetStub()
    gui.circle_button = WidgetStub()
    gui.square_button = WidgetStub()
    gui.line_button = WidgetStub()
    gui.gradient_button = WidgetStub()
    gui.palette_picker_button = WidgetStub()
    gui.view_original_button = WidgetStub()
    gui.view_processed_button = WidgetStub()

    PixelFixGui._refresh_tool_button_styles(gui)

    assert gui.bucket_button.style == "ToolButton.TButton"
    assert gui.pencil_button.style == "ToolButton.TButton"
    assert gui.eraser_button.style == "ToolButton.TButton"
    assert gui.circle_button.style == "ToolButton.TButton"
    assert gui.square_button.style == "ToolButtonActive.TButton"
    assert gui.line_button.style == "ToolButton.TButton"
    assert gui.gradient_button.style == "ToolButton.TButton"
    assert gui.palette_picker_button.style == "ToolButton.TButton"
    assert gui.view_original_button.style == "ToolButton.TButton"
    assert gui.view_processed_button.style == "ToolButtonActive.TButton"


def test_refresh_tool_button_styles_marks_active_outline_tool() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_ADD_OUTLINE
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui.view_var = SimpleNamespace(get=lambda: "processed")
    gui.add_outline_button = WidgetStub()
    gui.remove_outline_button = WidgetStub()

    PixelFixGui._refresh_tool_button_styles(gui)

    assert gui.add_outline_button.style == "ToolButtonActive.TButton"
    assert gui.remove_outline_button.style == "ToolButton.TButton"


def test_refresh_tool_button_styles_marks_active_line_and_gradient_tools() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui.view_var = SimpleNamespace(get=lambda: "processed")
    gui.line_button = WidgetStub()
    gui.gradient_button = WidgetStub()

    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_LINE
    PixelFixGui._refresh_tool_button_styles(gui)
    assert gui.line_button.style == "ToolButtonActive.TButton"
    assert gui.gradient_button.style == "ToolButton.TButton"

    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_GRADIENT
    PixelFixGui._refresh_tool_button_styles(gui)
    assert gui.line_button.style == "ToolButton.TButton"
    assert gui.gradient_button.style == "ToolButtonActive.TButton"


def test_toggle_line_mode_selects_tool() -> None:
    calls: list[tuple[str, object]] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui._canvas_tool_mode_value = lambda: None
    gui._start_shape_tool_mode = lambda mode, *, action_name: calls.append((mode, action_name))

    PixelFixGui._toggle_line_mode(gui)

    assert calls == [(app_module.CANVAS_TOOL_MODE_LINE, "Line")]


def test_toggle_gradient_mode_selects_placeholder_tool() -> None:
    calls: list[tuple[str, object]] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.image_state = "processed_current"
    gui._current_output_result = lambda: object()
    gui._canvas_tool_mode_value = lambda: None
    gui._set_canvas_tool_mode = lambda mode: calls.append(("mode", mode))
    gui._refresh_action_states = lambda: calls.append(("refresh", None))
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))

    PixelFixGui._toggle_gradient_mode(gui)

    assert calls == [
        ("mode", app_module.CANVAS_TOOL_MODE_GRADIENT),
        ("refresh", None),
    ]


def test_toggle_add_outline_mode_selects_tool_without_applying() -> None:
    calls: list[tuple[str, object]] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.image_state = "processed_current"
    gui._current_output_result = lambda: object()
    gui._set_canvas_tool_mode = lambda mode: calls.append(("mode", mode))
    gui._refresh_action_states = lambda: calls.append(("refresh", None))

    PixelFixGui._toggle_add_outline_mode(gui)

    assert calls == [
        ("mode", app_module.CANVAS_TOOL_MODE_ADD_OUTLINE),
        ("refresh", None),
    ]


def test_apply_selected_tool_options_routes_outline_actions() -> None:
    calls: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_ADD_OUTLINE
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui._add_outline_from_selection = lambda: calls.append("add")
    gui._remove_outline = lambda: calls.append("remove")

    PixelFixGui._apply_selected_tool_options(gui)
    gui.canvas_tool_mode = app_module.CANVAS_TOOL_MODE_REMOVE_OUTLINE
    PixelFixGui._apply_selected_tool_options(gui)

    assert calls == ["add", "remove"]


def test_initial_active_color_state_defaults_to_white_primary_and_transparent_secondary() -> None:
    assert PixelFixGui._initial_active_color_state({}) == (
        0xFFFFFF,
        0xFFFFFF,
        app_module.ACTIVE_COLOR_SLOT_SECONDARY,
        app_module.ACTIVE_COLOR_SLOT_PRIMARY,
    )


def test_build_active_color_preview_image_renders_front_active_and_back_secondary() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui._active_color_preview_templates = {}
    gui.primary_color_label = 0x123456
    gui.secondary_color_label = 0xABCDEF
    gui.transparent_color_slot = None
    gui.active_color_slot = app_module.ACTIVE_COLOR_SLOT_PRIMARY

    image = PixelFixGui._build_active_color_preview_image(gui)

    assert image.getpixel((27, 27)) == (0x12, 0x34, 0x56, 255)
    assert image.getpixel((2, 2)) == (0xAB, 0xCD, 0xEF, 255)


def test_update_palette_adjustment_labels_use_percent_suffixes() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.palette_brightness_var = SimpleNamespace(get=lambda: 15)
    gui.palette_contrast_var = SimpleNamespace(get=lambda: -20)
    gui.palette_hue_var = SimpleNamespace(get=lambda: 30)
    gui.palette_saturation_var = SimpleNamespace(get=lambda: 40)
    gui.palette_brightness_value_var = SimpleNamespace(value="", set=lambda value: setattr(gui.palette_brightness_value_var, "value", value))
    gui.palette_contrast_value_var = SimpleNamespace(value="", set=lambda value: setattr(gui.palette_contrast_value_var, "value", value))
    gui.palette_hue_value_var = SimpleNamespace(value="", set=lambda value: setattr(gui.palette_hue_value_var, "value", value))
    gui.palette_saturation_value_var = SimpleNamespace(value="", set=lambda value: setattr(gui.palette_saturation_value_var, "value", value))

    PixelFixGui._update_palette_adjustment_labels(gui)

    assert gui.palette_brightness_value_var.value == "15%"
    assert gui.palette_contrast_value_var.value == "-20%"
    assert gui.palette_hue_value_var.value == "30%"
    assert gui.palette_saturation_value_var.value == "40%"


def test_update_image_info_includes_current_colour_count() -> None:
    info = SimpleNamespace(value="", set=lambda value: setattr(info, "value", value))
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.source_path = Path("sprite.png")
    gui.zoom = 300
    gui.image_info_var = info
    gui.original_display_image = None
    gui.palette_result = _result_from_labels([[0x112233, 0x445566], [0x112233, 0x112233]])
    gui.downsample_result = None

    PixelFixGui._update_image_info(gui)

    assert info.value == "sprite.png  2x2  2 colours  300%"


def test_update_palette_strip_updates_palette_frame_title_with_count() -> None:
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

    palette_frame = WidgetStub()
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.palette_canvas = PaletteCanvasStub()
    gui.palette_frame = palette_frame
    gui.palette_info_var = palette_info
    gui.active_palette = [0x112233, 0x445566, 0x778899]
    gui.active_palette_source = "Edited Palette"
    gui._palette_selection_indices = set()
    gui.advanced_palette_preview = None
    gui._current_output_result = lambda: None

    PixelFixGui._update_palette_strip(gui)

    assert palette_frame.text == "PALETTE (3)"
    assert palette_info.value == "Palette: Edited Palette (3 colours)"
    assert rectangles[0] == (0, 0, app_module.PALETTE_SWATCH_SIZE - 1, app_module.PALETTE_SWATCH_SIZE - 1)
    assert rectangles[1] == (
        1,
        1,
        app_module.PALETTE_SWATCH_COLOUR_SIZE,
        app_module.PALETTE_SWATCH_COLOUR_SIZE,
    )
    assert rectangles[2][0] == app_module.PALETTE_SWATCH_SIZE


def test_update_palette_column_width_uses_reduced_ratio_and_minimum() -> None:
    widths: list[int] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.palette_column = SimpleNamespace(configure=lambda **kwargs: widths.append(kwargs["width"]))

    PixelFixGui._update_palette_column_width(gui, 1600)
    PixelFixGui._update_palette_column_width(gui, 900)

    expected_wide = max(app_module.PALETTE_COLUMN_MIN_WIDTH, round(1600 * app_module.PALETTE_COLUMN_WIDTH_RATIO))

    assert widths == [expected_wide, app_module.PALETTE_COLUMN_MIN_WIDTH]


def test_lock_palette_column_width_disables_pack_and_grid_propagation() -> None:
    calls: list[tuple[str, bool]] = []

    class PaletteColumnStub:
        def pack_propagate(self, enabled: bool) -> None:
            calls.append(("pack", enabled))

        def grid_propagate(self, enabled: bool) -> None:
            calls.append(("grid", enabled))

    gui = PixelFixGui.__new__(PixelFixGui)
    gui.palette_column = PaletteColumnStub()

    PixelFixGui._lock_palette_column_width(gui)

    assert calls == [("pack", False), ("grid", False)]


def test_update_palette_strip_limits_display_to_1024_swatches() -> None:
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

    gui = PixelFixGui.__new__(PixelFixGui)
    gui.palette_canvas = PaletteCanvasStub()
    gui.palette_info_var = palette_info
    gui.active_palette = [index + 1 for index in range(1100)]
    gui.active_palette_source = "Edited Palette"
    gui._palette_selection_indices = set()
    gui.advanced_palette_preview = None
    gui._current_output_result = lambda: None

    PixelFixGui._update_palette_strip(gui)

    assert len(gui._displayed_palette) == app_module.MAX_PALETTE_SWATCHES
    assert len(rectangles) == app_module.MAX_PALETTE_SWATCHES * 2
    assert palette_info.value.endswith("(showing first 1024)")


def test_build_active_color_preview_image_moves_active_slot_to_front() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui._active_color_preview_templates = {}
    gui.primary_color_label = 0x123456
    gui.secondary_color_label = 0xABCDEF
    gui.transparent_color_slot = None
    gui.active_color_slot = app_module.ACTIVE_COLOR_SLOT_SECONDARY

    image = PixelFixGui._build_active_color_preview_image(gui)

    assert image.getpixel((27, 27)) == (0xAB, 0xCD, 0xEF, 255)
    assert image.getpixel((2, 2)) == (0x12, 0x34, 0x56, 255)


def test_active_color_preview_click_selects_back_slot() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.primary_color_label = 0xFFFFFF
    gui.secondary_color_label = 0x000000
    gui.transparent_color_slot = app_module.ACTIVE_COLOR_SLOT_SECONDARY
    gui.active_color_slot = app_module.ACTIVE_COLOR_SLOT_PRIMARY
    gui._refresh_active_color_preview = lambda: None
    gui._schedule_state_persist_if_ready = lambda: None

    PixelFixGui._on_active_color_preview_click(gui, SimpleNamespace(x=4, y=4))

    assert gui.active_color_slot == app_module.ACTIVE_COLOR_SLOT_SECONDARY


def test_swap_active_colors_exchanges_labels_and_transparency_slot() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.primary_color_label = 0x112233
    gui.secondary_color_label = 0x445566
    gui.transparent_color_slot = app_module.ACTIVE_COLOR_SLOT_SECONDARY
    gui.active_color_slot = app_module.ACTIVE_COLOR_SLOT_PRIMARY
    gui._refresh_active_color_preview = lambda: None
    gui._schedule_state_persist_if_ready = lambda: None
    gui._refresh_action_states = lambda: None

    PixelFixGui._swap_active_colors(gui)

    assert gui.primary_color_label == 0x445566
    assert gui.secondary_color_label == 0x112233
    assert gui.transparent_color_slot == app_module.ACTIVE_COLOR_SLOT_PRIMARY


def test_make_active_color_transparent_targets_active_slot() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.primary_color_label = 0x112233
    gui.secondary_color_label = 0x445566
    gui.transparent_color_slot = app_module.ACTIVE_COLOR_SLOT_SECONDARY
    gui.active_color_slot = app_module.ACTIVE_COLOR_SLOT_PRIMARY
    gui._refresh_active_color_preview = lambda: None
    gui._schedule_state_persist_if_ready = lambda: None
    gui._refresh_action_states = lambda: None

    PixelFixGui._make_active_color_transparent(gui)

    assert gui.transparent_color_slot == app_module.ACTIVE_COLOR_SLOT_PRIMARY


def test_selected_palette_brush_label_uses_primary_active_colour() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.primary_color_label = 0x224466
    gui.secondary_color_label = 0x88AACC
    gui.transparent_color_slot = app_module.ACTIVE_COLOR_SLOT_SECONDARY

    assert PixelFixGui._selected_palette_brush_label(gui) == 0x224466


def test_selected_palette_brush_label_returns_none_when_primary_is_transparent() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.primary_color_label = 0x224466
    gui.secondary_color_label = 0x88AACC
    gui.transparent_color_slot = app_module.ACTIVE_COLOR_SLOT_PRIMARY

    assert PixelFixGui._selected_palette_brush_label(gui) is None


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
    gui.outline_pixel_perfect_var = SimpleNamespace(get=lambda: True)
    gui.outline_colour_mode_var = SimpleNamespace(get=lambda: app_module.OUTLINE_COLOUR_MODE_PALETTE)
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

    assert gui.palette_display_image.getpixel((0, 0))[3] == 0
    assert gui.palette_display_image.getpixel((1, 0)) == (0x11, 0x22, 0x33, 255)
    assert gui.downsample_display_image.getpixel((0, 0))[3] == 0
    assert gui.process_status_var.value == "Added pixel-perfect outline to 4 pixels with #112233. Press Undo to restore it."
    assert PixelFixGui._undo_palette_application(gui) is True
    assert gui.palette_display_image.getpixel((0, 0))[3] == 0


def test_add_outline_from_selection_can_use_square_mode() -> None:
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
    gui.outline_pixel_perfect_var = SimpleNamespace(get=lambda: False)
    gui.outline_colour_mode_var = SimpleNamespace(get=lambda: app_module.OUTLINE_COLOUR_MODE_PALETTE)
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))
    gui._displayed_palette = [0x112233]
    gui._palette_selection_indices = {0}
    gui._palette_selection_anchor_index = 0
    gui._update_palette_strip = lambda: None
    gui._update_image_info = lambda: None
    gui.redraw_canvas = lambda: None
    gui._schedule_state_persist = lambda: None
    gui._refresh_action_states = lambda: None
    gui._sync_controls_from_settings = lambda _settings: None
    gui._clear_palette_undo_state = lambda: setattr(gui, "_palette_undo_state", None)
    PixelFixGui._refresh_output_display_images(gui)

    PixelFixGui._add_outline_from_selection(gui)

    assert gui.palette_display_image.getpixel((0, 0)) == (0x11, 0x22, 0x33, 255)
    assert gui.process_status_var.value == "Added outline to 8 pixels with #112233. Press Undo to restore it."


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
    gui.outline_pixel_perfect_var = SimpleNamespace(get=lambda: True)
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

    assert gui.palette_display_image.getpixel((1, 1))[3] == 255
    assert gui.palette_display_image.getpixel((2, 1))[3] == 0
    assert gui.palette_display_image.getpixel((2, 2))[3] == 255
    assert gui.downsample_display_image.getpixel((1, 1))[3] == 255
    assert gui.process_status_var.value == "Removed 4 pixel-perfect edge pixels. Press Undo to restore it."
    assert PixelFixGui._undo_palette_application(gui) is True
    assert gui.palette_display_image.getpixel((1, 1))[3] == 255


def test_remove_outline_uses_brightness_threshold_and_updates_status() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.downsample_result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x202020, 0x202020, 0x202020, 0x000000],
            [0x000000, 0xE0E0E0, 0x808080, 0xE0E0E0, 0x000000],
            [0x000000, 0xE0E0E0, 0xE0E0E0, 0xE0E0E0, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
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
    gui.outline_remove_brightness_threshold_enabled_var = SimpleNamespace(get=lambda: True)
    gui.outline_remove_brightness_threshold_percent_var = SimpleNamespace(get=lambda: 40)
    gui.outline_remove_brightness_threshold_direction_var = SimpleNamespace(
        get=lambda: app_module.OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK
    )
    gui.workspace = ColorWorkspace()
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

    assert gui.downsample_display_image.getpixel((1, 1))[3] == 0
    assert gui.downsample_display_image.getpixel((2, 1))[3] == 0
    assert gui.downsample_display_image.getpixel((3, 1))[3] == 0
    assert gui.downsample_display_image.getpixel((1, 2))[3] == 255
    assert gui.process_status_var.value == "Removed 3 outline pixels using the dark brightness threshold at 40%. Press Undo to restore it."


def test_remove_outline_reports_threshold_no_match_without_changing_image() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.downsample_result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0xE0E0E0, 0xE0E0E0, 0xE0E0E0, 0x000000],
            [0x000000, 0xE0E0E0, 0x808080, 0xE0E0E0, 0x000000],
            [0x000000, 0xE0E0E0, 0xE0E0E0, 0xE0E0E0, 0x000000],
            [0x000000, 0x000000, 0x000000, 0x000000, 0x000000],
        ],
        stage="palette",
    )
    gui.palette_result = None
    gui.transparent_colors = set()
    gui.downsample_display_image = None
    gui.palette_display_image = None
    gui.image_state = "processed_current"
    gui.workspace = ColorWorkspace()
    gui.outline_pixel_perfect_var = SimpleNamespace(get=lambda: False)
    gui.outline_remove_brightness_threshold_enabled_var = SimpleNamespace(get=lambda: True)
    gui.outline_remove_brightness_threshold_percent_var = SimpleNamespace(get=lambda: 0)
    gui.outline_remove_brightness_threshold_direction_var = SimpleNamespace(
        get=lambda: app_module.OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK
    )
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))
    gui._refresh_output_display_images = lambda: (_ for _ in ()).throw(AssertionError("Display image should not refresh on no-op"))

    before = gui.downsample_result
    PixelFixGui._remove_outline(gui)

    assert gui.downsample_result is before
    assert gui.process_status_var.value == "No exterior outline pixels met the dark brightness threshold at 0%."




def test_add_outline_from_selection_allows_adaptive_without_palette_selection() -> None:
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
    gui.outline_colour_mode_var = SimpleNamespace(get=lambda: app_module.OUTLINE_COLOUR_MODE_ADAPTIVE)
    gui.outline_adaptive_darken_percent_var = SimpleNamespace(get=lambda: 60)
    gui.outline_add_generated_colours_var = SimpleNamespace(get=lambda: False)
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

    assert gui.process_status_var.value == "Added adaptive outline to 10 pixels at 60% darkening. Press Undo to restore it."


def test_add_outline_from_selection_can_append_generated_colours_to_current_palette() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.downsample_result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000, 0x000000],
            [0x000000, 0x6699CC, 0x6699CC, 0x000000],
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
    gui.active_palette = [0x6699CC]
    gui.active_palette_source = "Edited Palette"
    gui.active_palette_path = None
    gui.advanced_palette_preview = None
    gui.session = SimpleNamespace(current=PreviewSettings())
    gui.quick_compare_active = False
    gui.view_var = SimpleNamespace(set=lambda _value: None)
    gui.outline_pixel_perfect_var = SimpleNamespace(get=lambda: False)
    gui.outline_colour_mode_var = SimpleNamespace(get=lambda: app_module.OUTLINE_COLOUR_MODE_ADAPTIVE)
    gui.outline_adaptive_darken_percent_var = SimpleNamespace(get=lambda: 60)
    gui.outline_add_generated_colours_var = SimpleNamespace(get=lambda: True)
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))
    gui._displayed_palette = [0x6699CC]
    gui._palette_selection_indices = {0}
    gui._palette_selection_anchor_index = 0
    gui._update_palette_strip = lambda: None
    gui._update_image_info = lambda: None
    gui.redraw_canvas = lambda: None
    gui._schedule_state_persist = lambda: None
    gui._refresh_action_states = lambda: None
    gui._sync_controls_from_settings = lambda _settings: None
    gui._clear_palette_undo_state = lambda: setattr(gui, "_palette_undo_state", None)
    PixelFixGui._refresh_output_display_images(gui)

    PixelFixGui._add_outline_from_selection(gui)

    assert len(gui.active_palette) == 2
    assert gui.active_palette[0] == 0x6699CC
    assert gui.active_palette[1] != 0x6699CC
    assert gui.process_status_var.value.endswith("Added 1 generated palette colour to the current palette. Press Undo to restore it.")
    assert gui._palette_selection_indices == {0}
    assert gui._palette_selection_anchor_index == 0
    assert PixelFixGui._undo_palette_application(gui) is True
    assert gui.active_palette == [0x6699CC]


def test_outline_adaptive_enabled_defaults_false_without_gui_state() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)

    assert PixelFixGui._outline_adaptive_enabled(gui) is False


def test_outline_colour_mode_migrates_from_legacy_persisted_adaptive_flag() -> None:
    assert PixelFixGui._initial_outline_colour_mode({"outline_adaptive": True}) == app_module.OUTLINE_COLOUR_MODE_ADAPTIVE
    assert PixelFixGui._initial_outline_colour_mode({}) == app_module.OUTLINE_COLOUR_MODE_PALETTE


def test_outline_adaptive_darken_percent_defaults_and_clamps() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.outline_adaptive_darken_percent_var = SimpleNamespace(get=lambda: 140)

    assert PixelFixGui._outline_adaptive_darken_percent(gui) == 100


def test_outline_remove_brightness_threshold_defaults_and_clamps() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.outline_remove_brightness_threshold_percent_var = SimpleNamespace(get=lambda: 140)
    gui.outline_remove_brightness_threshold_direction_var = SimpleNamespace(get=lambda: "invalid")

    assert PixelFixGui._outline_remove_brightness_threshold_enabled(gui) is False
    assert PixelFixGui._outline_remove_brightness_threshold_percent(gui) == 100
    assert PixelFixGui._outline_remove_brightness_threshold_direction(gui) == app_module.OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK


def test_brush_settings_default_and_clamp() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.brush_width_var = SimpleNamespace(get=lambda: 400)
    gui.brush_shape_var = SimpleNamespace(get=lambda: "invalid")

    assert PixelFixGui._brush_width(gui) == app_module.BRUSH_WIDTH_MAX
    assert PixelFixGui._brush_shape(gui) == app_module.BRUSH_SHAPE_SQUARE


def test_outline_pixel_perfect_enabled_defaults_true_without_gui_state() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)

    assert PixelFixGui._outline_pixel_perfect_enabled(gui) is True


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

    assert len(rectangles) == gui.advanced_palette_preview.palette_size() * 2
    assert palette_info.value == f"Palette: Generated ({gui.advanced_palette_preview.palette_size()} colours)"


def test_update_palette_strip_uses_builtin_preview_without_mutating_selection() -> None:
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

    gui = PixelFixGui.__new__(PixelFixGui)
    gui.palette_canvas = PaletteCanvasStub()
    gui.palette_info_var = palette_info
    gui.active_palette = [0x112233, 0x445566, 0x778899]
    gui.active_palette_source = "Edited Palette"
    gui._palette_selection_indices = {2}
    gui._palette_selection_anchor_index = 2
    gui._builtin_palette_preview_entry = app_module.PaletteCatalogEntry(
        label="Preview",
        path=Path("preview.gpl"),
        colors=(0x111111, 0x222222),
        menu_path=("Built-in",),
        source_label="Built-in / Preview",
    )
    gui.advanced_palette_preview = None
    gui._current_output_result = lambda: None

    PixelFixGui._update_palette_strip(gui)

    assert len(rectangles) == 4
    assert gui._palette_selection_indices == {2}
    assert gui._palette_selection_anchor_index == 2
    assert palette_info.value == "Palette: Preview: Built-in / Preview (2 colours)"


def test_filtered_builtin_palette_groups_match_name_and_path() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.builtin_palette_entries = [
        app_module.PaletteCatalogEntry(
            label="DB16",
            path=Path("db16.gpl"),
            colors=(0x111111,),
            menu_path=("DawnBringer",),
            source_label="DawnBringer / DB16",
        ),
        app_module.PaletteCatalogEntry(
            label="PICO-8",
            path=Path("pico8.gpl"),
            colors=(0x222222,),
            menu_path=("Minimal",),
            source_label="Minimal / PICO-8",
        ),
        app_module.PaletteCatalogEntry(
            label="Default",
            path=Path("default.gpl"),
            colors=(0x333333,),
            menu_path=(),
            source_label="Default",
        ),
    ]

    assert PixelFixGui._filtered_builtin_palette_groups(gui, "db16") == [
        ("DawnBringer", [gui.builtin_palette_entries[0]])
    ]
    assert PixelFixGui._filtered_builtin_palette_groups(gui, "minimal") == [
        ("Minimal", [gui.builtin_palette_entries[1]])
    ]
    assert PixelFixGui._filtered_builtin_palette_groups(gui, "default") == [
        ("General", [gui.builtin_palette_entries[2]])
    ]


def test_compute_palette_browser_geometry_prefers_left_and_clamps() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.root = SimpleNamespace(
        winfo_screenwidth=lambda: 1280,
        winfo_screenheight=lambda: 720,
    )
    gui.palette_dropdown_button = SimpleNamespace(
        winfo_rootx=lambda: 900,
        winfo_rooty=lambda: 240,
        winfo_width=lambda: 120,
        winfo_height=lambda: 28,
    )

    width, height, x_position, y_position = PixelFixGui._compute_palette_browser_geometry(gui)

    assert width == app_module.PALETTE_BROWSER_WIDTH
    assert height == app_module.PALETTE_BROWSER_HEIGHT
    assert x_position == 900 - width - app_module.PALETTE_BROWSER_GAP
    assert y_position == 240

    gui.palette_dropdown_button = SimpleNamespace(
        winfo_rootx=lambda: 40,
        winfo_rooty=lambda: 680,
        winfo_width=lambda: 100,
        winfo_height=lambda: 24,
    )

    width, height, x_position, y_position = PixelFixGui._compute_palette_browser_geometry(gui)

    assert x_position >= app_module.PALETTE_BROWSER_MARGIN
    assert y_position >= app_module.PALETTE_BROWSER_MARGIN
    assert x_position <= 1280 - width - app_module.PALETTE_BROWSER_MARGIN
    assert y_position <= 720 - height - app_module.PALETTE_BROWSER_MARGIN


def test_get_display_palette_keeps_source_palette_when_adjustments_are_active() -> None:
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
    assert palette == gui.advanced_palette_preview.labels()
    assert source == "Generated"


def test_palette_adjustment_change_refreshes_processed_image_preview() -> None:
    messages: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.process_status_var = SimpleNamespace(set=lambda value: messages.append(value))
    gui._clear_palette_undo_state = lambda: messages.append("clear")
    gui._refresh_output_display_images = lambda: messages.append("refresh-output")
    gui._current_output_result = lambda: SimpleNamespace(structured_palette=None, display_palette_labels=(), stats=SimpleNamespace(stage="palette"))
    gui._update_palette_adjustment_labels = lambda: messages.append("adjust")
    gui._update_scale_info = lambda: messages.append("scale")
    gui._update_palette_strip = lambda: messages.append("palette")
    gui.redraw_canvas = lambda: messages.append("redraw")
    gui._schedule_state_persist = lambda: messages.append("persist")
    gui._refresh_action_states = lambda: messages.append("refresh")
    gui._has_palette_source = lambda: True
    gui._palette_adjustment_selection_indices = lambda: None

    PixelFixGui._handle_settings_transition(
        gui,
        PreviewSettings(),
        PreviewSettings(palette_brightness=15),
    )

    assert messages == [
        "clear",
        "refresh-output",
        "Image adjustment settings updated.",
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
    gui._refresh_output_display_images = lambda: messages.append("refresh-output")
    gui._current_output_result = lambda: SimpleNamespace(structured_palette=None, display_palette_labels=(), stats=SimpleNamespace(stage="palette"))
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

    assert messages[1] == "refresh-output"
    assert messages[2] == "Selected image colours updated."

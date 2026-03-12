from types import SimpleNamespace
from pathlib import Path

from PIL import Image

import pixel_fix.gui.app as app_module
from pixel_fix.gui.app import PaletteUndoState, PixelFixGui
from pixel_fix.gui.processing import (
    ProcessResult,
    ProcessStats,
    add_exterior_outline,
    apply_transparency_fill,
    downsample_image,
    process_image,
    reduce_palette_image,
    remove_exterior_outline,
)
from pixel_fix.gui.state import PreviewSettings
from pixel_fix.palette.advanced import generate_structured_palette
from pixel_fix.palette.sort import PALETTE_SELECT_LIGHTNESS_DARK, PALETTE_SORT_HUE, PALETTE_SORT_LIGHTNESS
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


def test_add_exterior_outline_ignores_internal_holes() -> None:
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


def test_remove_exterior_outline_erodes_only_outside_edge() -> None:
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

    assert messages == ["Palette reduction settings changed. Click Generate Reduced Palette to rebuild the palette.", "persist", "refresh"]


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

    assert gui.active_palette is None
    assert gui.active_palette_source == ""
    assert gui.active_palette_path is None
    assert gui.transparent_colors == set()
    assert gui.downsample_result is None
    assert gui.palette_result is None
    assert gui.palette_add_pick_mode is False
    assert gui.transparency_pick_mode is False
    assert gui.image_state == "loaded_original"
    assert gui.original_display_image is not None


def test_canvas_motion_updates_live_pick_preview() -> None:
    cursor_updates: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.dragging = False
    gui.palette_add_pick_mode = True
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
    gui.palette_add_pick_mode = True
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
    gui.palette_add_pick_mode = False
    gui.transparency_pick_mode = False
    gui.session = SimpleNamespace(history=SimpleNamespace(can_undo=lambda: False))
    gui.downsample_button = WidgetStub()
    gui.generate_override_palette_button = WidgetStub()
    gui.reduce_palette_button = WidgetStub()
    gui.transparency_button = WidgetStub()
    gui.add_outline_button = WidgetStub()
    gui.remove_outline_button = WidgetStub()
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

    PixelFixGui._refresh_action_states(gui)

    assert gui.add_outline_button.state == app_module.tk.NORMAL
    assert gui.remove_outline_button.state == app_module.tk.NORMAL
    assert gui.merge_palette_button.state == app_module.tk.DISABLED
    assert gui.ramp_palette_button.state == app_module.tk.NORMAL


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
    gui.add_outline_button = WidgetStub()
    gui.remove_outline_button = WidgetStub()
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

    PixelFixGui._refresh_action_states(gui)

    assert gui.merge_palette_button.state == app_module.tk.NORMAL
    assert gui.ramp_palette_button.state == app_module.tk.NORMAL
    assert gui.add_outline_button.state == app_module.tk.DISABLED


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

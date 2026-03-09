from types import SimpleNamespace

from PIL import Image

import pixel_fix.gui.app as app_module
from pixel_fix.gui.app import CanvasDisplay, PaletteUndoState, PixelFixGui
from pixel_fix.gui.processing import downsample_image, process_image, reduce_palette_image
from pixel_fix.gui.state import PreviewSettings
from pixel_fix.palette.advanced import generate_structured_palette
from pixel_fix.pipeline import PipelineConfig


def _sample_grid():
    return [
        [(255, 0, 0), (255, 0, 0), (0, 0, 255), (0, 0, 255)],
        [(255, 0, 0), (255, 0, 0), (0, 0, 255), (0, 0, 255)],
        [(0, 255, 0), (0, 255, 0), (255, 255, 0), (255, 255, 0)],
        [(0, 255, 0), (0, 255, 0), (255, 255, 0), (255, 255, 0)],
    ]


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
    gui.palette_display_image = Image.new("RGBA", (reduced.width, reduced.height), (1, 2, 3, 255))
    gui.image_state = "processed_current"
    gui.last_successful_process_snapshot = {"stage": "palette"}
    gui.quick_compare_active = True
    gui.process_status_var = SimpleNamespace(value="", set=lambda value: setattr(gui.process_status_var, "value", value))
    gui._update_palette_strip = lambda: None
    gui._update_image_info = lambda: None
    gui.redraw_canvas = lambda: None
    gui._schedule_state_persist = lambda: None
    gui._refresh_action_states = lambda: None
    gui._clear_palette_undo_state = lambda: setattr(gui, "_palette_undo_state", None)
    gui._palette_undo_state = PaletteUndoState(
        palette_result=None,
        palette_display_image=None,
        image_state="processed_stale",
        last_successful_process_snapshot={"stage": "downsample"},
    )

    assert PixelFixGui._undo_palette_application(gui) is True
    assert gui.palette_result is None
    assert gui.palette_display_image is None
    assert gui.image_state == "processed_stale"
    assert gui.last_successful_process_snapshot == {"stage": "downsample"}
    assert gui.quick_compare_active is False
    assert gui.process_status_var.value == "Reverted the last palette application."
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


def test_add_key_color_allows_twelve_and_blocks_thirteen() -> None:
    messages: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.key_colors = [index for index in range(12)]
    gui.advanced_palette_preview = object()
    gui.process_status_var = SimpleNamespace(set=lambda value: messages.append(value))
    gui._update_key_color_list = lambda: None
    gui._mark_output_stale = lambda message=None: messages.append(message or "")
    gui._update_palette_strip = lambda: None
    gui._refresh_action_states = lambda: None

    PixelFixGui._add_key_color(gui, 0x123456)

    assert len(gui.key_colors) == 12
    assert messages[-1] == "You can only pick up to 12 key colours."


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


def test_scale_overlay_is_disabled_while_picking_key_colours() -> None:
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.original_display_image = Image.new("RGBA", (4, 4), (0, 0, 0, 255))
    gui.quick_compare_active = False
    gui.key_color_pick_mode = True
    gui.view_var = SimpleNamespace(get=lambda: "original")

    assert PixelFixGui._scale_overlay_active(gui) is False


def test_draw_scale_overlay_no_longer_renders_corner_text() -> None:
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    class CanvasStub:
        def create_line(self, *args, **kwargs):
            calls.append(("line", args, kwargs))

        def create_text(self, *args, **kwargs):
            calls.append(("text", args, kwargs))

    gui = PixelFixGui.__new__(PixelFixGui)
    gui.canvas = CanvasStub()
    gui.original_display_image = Image.new("RGBA", (4, 4), (0, 0, 0, 255))
    gui.comparison_original_image = None
    gui.quick_compare_active = False
    gui.key_color_pick_mode = False
    gui.view_var = SimpleNamespace(get=lambda: "original")
    gui.session = SimpleNamespace(current=PreviewSettings(pixel_width=2))
    gui._display_context = CanvasDisplay(0, 0, 40, 40, gui.original_display_image)

    PixelFixGui._draw_scale_overlay(gui)

    assert any(kind == "line" for kind, _args, _kwargs in calls)
    assert not any(kind == "text" for kind, _args, _kwargs in calls)

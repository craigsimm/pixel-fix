from types import SimpleNamespace

from PIL import Image

import pixel_fix.gui.app as app_module
from pixel_fix.gui.app import PaletteUndoState, PixelFixGui
from pixel_fix.gui.processing import ProcessResult, ProcessStats, downsample_image, process_image, reduce_palette_image
from pixel_fix.gui.state import PreviewSettings
from pixel_fix.palette.advanced import generate_structured_palette
from pixel_fix.palette.workspace import ColorWorkspace
from pixel_fix.pipeline import PipelineConfig, PipelinePreparedResult


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
    assert result.stats.anti_alias_pixels_fixed == 0
    assert result.stats.orphan_pixels_replaced == 0
    assert result.stats.gap_pixels_filled == 0
    assert result.display_palette_labels == (0xFF0000, 0x0000FF, 0x00FF00, 0xFFFF00)
    assert progress == [
        (10, "Preparing input"),
        (35, "Downsampling with Nearest Neighbor..."),
    ]


def test_downsample_image_uses_rgba_anti_alias_cleanup() -> None:
    rgba = Image.new("RGBA", (3, 3), (255, 255, 255, 255))
    pixels = rgba.load()
    for y in range(3):
        pixels[0, y] = (0, 0, 0, 255)
        pixels[1, y] = (0, 0, 0, 255)
    pixels[1, 1] = (32, 32, 32, 128)
    rgb_grid = [
        [(0, 0, 0), (0, 0, 0), (255, 255, 255)],
        [(0, 0, 0), (32, 32, 32), (255, 255, 255)],
        [(0, 0, 0), (0, 0, 0), (255, 255, 255)],
    ]

    result = downsample_image(
        rgb_grid,
        PipelineConfig(pixel_width=1, anti_alias_removal_enabled=True, anti_alias_alpha_threshold=224),
        source_rgba=rgba,
    )

    assert result.grid[1][1] == (0, 0, 0)
    assert result.stats.anti_alias_pixels_fixed == 1
    assert result.stats.orphan_pixels_replaced == 0
    assert result.stats.gap_pixels_filled == 0


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
    assert reduced.stats.anti_alias_pixels_fixed == 0
    assert reduced.stats.orphan_pixels_replaced == 0
    assert reduced.stats.gap_pixels_filled == 0
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
    assert second.stats.anti_alias_pixels_fixed == 0
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
    gui.active_palette = None
    gui.active_palette_source = ""
    gui.active_palette_path = None
    gui.advanced_palette_preview = None
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
        palette_display_image=None,
        image_state="processed_stale",
        last_successful_process_snapshot={"stage": "downsample"},
        active_palette=None,
        active_palette_source="",
        active_palette_path=None,
        advanced_palette_preview=None,
        settings=PreviewSettings(),
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


def test_cleanup_setting_change_marks_downsample_stale_and_clears_cache() -> None:
    messages: list[str] = []
    gui = PixelFixGui.__new__(PixelFixGui)
    gui.prepared_input_cache = object()
    gui.prepared_input_cache_key = ("cached",)
    gui.process_status_var = SimpleNamespace(set=lambda value: messages.append(value))
    gui._clear_palette_undo_state = lambda: messages.append("clear")
    gui._mark_output_stale = lambda message=None: messages.append(f"stale:{message}")
    gui._update_key_color_list = lambda: messages.append("list")
    gui._update_palette_adjustment_labels = lambda: messages.append("adjust")
    gui._update_downsample_cleanup_controls = lambda: messages.append("cleanup")
    gui._update_scale_info = lambda: messages.append("scale")
    gui._update_palette_strip = lambda: messages.append("palette")
    gui.redraw_canvas = lambda: messages.append("redraw")
    gui._schedule_state_persist = lambda: messages.append("persist")
    gui._refresh_action_states = lambda: messages.append("refresh")

    PixelFixGui._handle_settings_transition(
        gui,
        PreviewSettings(),
        PreviewSettings(orphan_cleanup_enabled=True),
    )

    assert gui.prepared_input_cache is None
    assert gui.prepared_input_cache_key is None
    assert messages == [
        "clear",
        "stale:Downsample settings changed. Click Downsample to update the preview.",
        "list",
        "adjust",
        "cleanup",
        "scale",
        "palette",
        "redraw",
        "persist",
        "refresh",
    ]


def test_prepare_cache_key_includes_cleanup_settings() -> None:
    assert PixelFixGui._build_prepare_cache_key(PreviewSettings()) != PixelFixGui._build_prepare_cache_key(
        PreviewSettings(orphan_cleanup_enabled=True)
    )
    assert PixelFixGui._build_prepare_cache_key(PreviewSettings()) != PixelFixGui._build_prepare_cache_key(
        PreviewSettings(anti_alias_alpha_threshold=200)
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

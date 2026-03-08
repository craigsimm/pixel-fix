from types import SimpleNamespace

from PIL import Image

from pixel_fix.gui.app import PaletteUndoState, PixelFixGui
from pixel_fix.gui.processing import downsample_image, process_image, reduce_palette_image
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
    progress: list[tuple[int, str]] = []
    reduced = reduce_palette_image(
        downsampled.prepared_input,
        PipelineConfig(pixel_width=2, colors=2, quantizer="topk"),
        progress_callback=lambda percent, message: progress.append((percent, message)),
    )
    assert reduced.stats.stage == "palette"
    assert reduced.stats.pixel_width == 2
    assert reduced.stats.color_count <= 2
    assert reduced.stats.output_size == (2, 2)
    assert progress == [
        (65, "Quantizing to 2 colours with topk..."),
        (90, "Finalizing output..."),
        (100, "Complete"),
    ]


def test_process_image_reuses_prepared_downsample() -> None:
    first = downsample_image(_sample_grid(), PipelineConfig(pixel_width=2))
    progress: list[tuple[int, str]] = []
    second = process_image(
        _sample_grid(),
        PipelineConfig(pixel_width=2, colors=2),
        prepared_input=first.prepared_input,
        progress_callback=lambda percent, message: progress.append((percent, message)),
    )
    assert second.stats.pixel_width == 2
    assert second.stats.color_count <= 2
    assert progress == [
        (10, "Preparing input"),
        (35, "Reusing downsampled image..."),
        (65, "Quantizing to 2 colours with topk..."),
        (90, "Finalizing output..."),
        (100, "Complete"),
    ]


def test_undo_palette_application_restores_previous_preview_state() -> None:
    downsampled = downsample_image(_sample_grid(), PipelineConfig(pixel_width=2))
    reduced = reduce_palette_image(
        downsampled.prepared_input,
        PipelineConfig(pixel_width=2, colors=2, quantizer="topk"),
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

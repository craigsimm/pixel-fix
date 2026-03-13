from pathlib import Path

from pixel_fix.gui.persist import (
    append_process_log,
    coerce_selection_threshold,
    deserialize_settings,
    diff_snapshots,
    load_app_state,
    make_process_snapshot,
    save_app_state,
    serialize_settings,
)
from pixel_fix.gui.state import PreviewSettings


def test_settings_roundtrip() -> None:
    settings = PreviewSettings(
        pixel_width=3,
        downsample_mode="rotsprite",
        palette_reduction_colors=24,
        generated_shades=6,
        auto_detect_count=9,
        contrast_bias=0.7,
        palette_brightness=15,
        palette_contrast=130,
        palette_hue=-20,
        palette_saturation=140,
        palette_dither_mode="blue-noise",
        input_mode="rgba",
        output_mode="indexed",
        quantizer="median-cut",
        dither_mode="ordered",
        cleanup_tool="pencil",
        cleanup_brush_width=5,
        cleanup_brush_shape="round",
    )

    restored = deserialize_settings(serialize_settings(settings))

    assert restored == settings


def test_default_settings_use_manual_pixel_size() -> None:
    settings = PreviewSettings()

    assert settings.pixel_width == 2
    assert settings.downsample_mode == "nearest"
    assert settings.palette_reduction_colors == 16
    assert settings.auto_detect_count == 12
    assert settings.quantizer == "median-cut"
    assert settings.palette_brightness == 0
    assert settings.palette_contrast == 100
    assert settings.palette_hue == 0
    assert settings.palette_saturation == 100
    assert settings.cleanup_tool == "none"
    assert settings.cleanup_brush_width == 1
    assert settings.cleanup_brush_shape == "square"


def test_diff_snapshots_uses_friendly_messages() -> None:
    previous = make_process_snapshot(PreviewSettings(pixel_width=2), None, None)
    current = make_process_snapshot(
        PreviewSettings(
            pixel_width=4,
            downsample_mode="bilinear",
            palette_reduction_colors=24,
            generated_shades=6,
            auto_detect_count=9,
            contrast_bias=0.7,
            palette_brightness=15,
            palette_contrast=130,
            palette_hue=-20,
            palette_saturation=140,
            palette_dither_mode="blue-noise",
            quantizer="kmeans",
            cleanup_tool="eraser",
            cleanup_brush_width=3,
            cleanup_brush_shape="round",
        ),
        [0x000000, 0xFFFFFF],
        "palette.json",
        "Built-in: Example / DB16",
    )

    changes = diff_snapshots(previous, current)

    assert "Pixel size: 2 > 4" in changes
    assert "Resize method: nearest > bilinear" in changes
    assert "Palette reduction colours: 16 > 24" in changes
    assert "Ramp steps: 4 > 6" in changes
    assert "Auto-detect count: 12 > 9" in changes
    assert "Ramp contrast: 1.0 > 0.7" in changes
    assert "Palette brightness: 0 > 15" in changes
    assert "Palette contrast: 100 > 130" in changes
    assert "Palette hue: 0 > -20" in changes
    assert "Palette saturation: 100 > 140" in changes
    assert "Palette reduction method: median-cut > kmeans" in changes
    assert "Dithering method: none > blue-noise" in changes
    assert "Cleanup tool: none > eraser" in changes
    assert "Cleanup brush width: 1 > 3" in changes
    assert "Cleanup brush shape: square > round" in changes
    assert "Palette size: 0 > 2" in changes
    assert "Palette source: none > Built-in: Example / DB16" in changes
    assert "Palette path: none > palette.json" in changes


def test_deserialize_settings_clamps_advanced_palette_controls() -> None:
    restored = deserialize_settings(
        {
            "pixel_width": 0,
            "palette_reduction_colors": 999,
            "generated_shades": 9,
            "auto_detect_count": 99,
            "contrast_bias": -2,
            "palette_brightness": -999,
            "palette_contrast": 999,
            "palette_hue": -999,
            "palette_saturation": 999,
            "quantizer": "topk",
            "palette_dither_mode": "ordered",
            "cleanup_tool": "PAN",
            "cleanup_brush_width": 0,
            "cleanup_brush_shape": "circle",
        }
    )

    assert restored.pixel_width == 1
    assert restored.palette_reduction_colors == 256
    assert restored.generated_shades == 8
    assert restored.auto_detect_count == 24
    assert restored.contrast_bias == 0.1
    assert restored.palette_brightness == -100
    assert restored.palette_contrast == 200
    assert restored.palette_hue == -180
    assert restored.palette_saturation == 200
    assert restored.quantizer == "median-cut"
    assert restored.palette_dither_mode == "ordered"
    assert restored.cleanup_tool == "none"
    assert restored.cleanup_brush_width == 1
    assert restored.cleanup_brush_shape == "square"


def test_diff_snapshots_reports_no_changes() -> None:
    snapshot = make_process_snapshot(PreviewSettings(), None, None)
    assert diff_snapshots(snapshot, snapshot) == ["No settings changed since the previous successful process."]


def test_save_and_load_app_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    data = {
        "settings": {"palette_reduction_colors": 20, "generated_shades": 8, "auto_detect_count": 10},
        "last_output_path": "out.png",
        "selection_threshold": 40,
    }

    save_app_state(data)

    assert load_app_state() == data


def test_selection_threshold_coerces_to_allowed_steps() -> None:
    assert coerce_selection_threshold(0) == 10
    assert coerce_selection_threshold(26) == 30
    assert coerce_selection_threshold(101) == 100


def test_append_process_log_writes_timestamped_entry(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))

    append_process_log(
        source_path_value="example.png",
        source_size=(128, 128),
        processed_size=(32, 32),
        color_count=12,
        changes=["Resize method: nearest > bilinear"],
        success=True,
        message="Downsample complete",
    )

    text = (tmp_path / "pixel-fix" / "process.log").read_text(encoding="utf-8")
    assert "SUCCESS" in text
    assert "Source: example.png" in text
    assert "Processed size: 32x32" in text
    assert "- Resize method: nearest > bilinear" in text


def test_deserialize_settings_normalizes_cleanup_controls() -> None:
    restored = deserialize_settings({
        "cleanup_tool": "PENCIL",
        "cleanup_brush_width": 999,
        "cleanup_brush_shape": "ROUND",
    })

    assert restored.cleanup_tool == "pencil"
    assert restored.cleanup_brush_width == 64
    assert restored.cleanup_brush_shape == "round"

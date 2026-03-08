from pathlib import Path

from pixel_fix.gui.persist import (
    append_process_log,
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
        colors=24,
        input_mode="rgba",
        output_mode="indexed",
        quantizer="kmeans",
        dither_mode="ordered",
    )
    restored = deserialize_settings(serialize_settings(settings))
    assert restored == settings


def test_default_settings_use_manual_pixel_size() -> None:
    assert PreviewSettings().pixel_width == 2
    assert PreviewSettings().downsample_mode == "nearest"


def test_diff_snapshots_uses_friendly_messages() -> None:
    previous = make_process_snapshot(PreviewSettings(pixel_width=2), None, None)
    current = make_process_snapshot(
        PreviewSettings(pixel_width=4, downsample_mode="bilinear"),
        [0x000000, 0xFFFFFF],
        "palette.json",
        "Built-in: Example / DB16",
    )
    changes = diff_snapshots(previous, current)
    assert "Pixel size: 2 > 4" in changes
    assert "Resize method: nearest > bilinear" in changes
    assert "Palette size: 0 > 2" in changes
    assert "Palette source: none > Built-in: Example / DB16" in changes
    assert "Palette path: none > palette.json" in changes


def test_diff_snapshots_reports_no_changes() -> None:
    snapshot = make_process_snapshot(PreviewSettings(), None, None)
    assert diff_snapshots(snapshot, snapshot) == ["No settings changed since the previous successful process."]


def test_save_and_load_app_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    data = {"settings": {"colors": 8}, "last_output_path": "out.png"}
    save_app_state(data)
    assert load_app_state() == data


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

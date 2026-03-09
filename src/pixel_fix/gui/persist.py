from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from .state import PreviewSettings

APP_DIR_NAME = "pixel-fix"
SETTINGS_FILE_NAME = "settings.json"
PROCESS_LOG_FILE_NAME = "process.log"

SETTING_LABELS = {
    "pixel_width": "Pixel size",
    "downsample_mode": "Resize method",
    "palette_reduction_colors": "Palette reduction colours",
    "generated_shades": "Ramp steps",
    "auto_detect_count": "Auto-detect count",
    "contrast_bias": "Ramp contrast",
    "palette_dither_mode": "Dithering method",
    "input_mode": "Input mode",
    "output_mode": "Output mode",
    "quantizer": "Palette reduction method",
    "dither_mode": "Dithering",
    "palette_size": "Palette size",
    "palette_source": "Palette source",
    "palette_path": "Palette path",
}


def get_app_storage_dir() -> Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / APP_DIR_NAME
    return Path.home() / ".pixel-fix"


def settings_path() -> Path:
    return get_app_storage_dir() / SETTINGS_FILE_NAME


def process_log_path() -> Path:
    return get_app_storage_dir() / PROCESS_LOG_FILE_NAME


def ensure_storage_dir() -> Path:
    path = get_app_storage_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def serialize_settings(settings: PreviewSettings) -> dict[str, Any]:
    return {
        "pixel_width": settings.pixel_width,
        "downsample_mode": settings.downsample_mode,
        "palette_reduction_colors": settings.palette_reduction_colors,
        "generated_shades": settings.generated_shades,
        "auto_detect_count": settings.auto_detect_count,
        "contrast_bias": settings.contrast_bias,
        "palette_dither_mode": settings.palette_dither_mode,
        "input_mode": settings.input_mode,
        "output_mode": settings.output_mode,
        "quantizer": settings.quantizer,
        "dither_mode": settings.dither_mode,
    }


def deserialize_settings(data: dict[str, Any] | None) -> PreviewSettings:
    if not data:
        return PreviewSettings()
    return PreviewSettings(
        pixel_width=max(1, _as_int(data.get("pixel_width"), 2)),
        downsample_mode=str(data.get("downsample_mode", "nearest")),
        palette_reduction_colors=_coerce_palette_reduction_colors(data.get("palette_reduction_colors", 16)),
        generated_shades=_coerce_generated_shades(data.get("generated_shades", data.get("ramp_length", 4))),
        auto_detect_count=_coerce_auto_detect_count(data.get("auto_detect_count", 12)),
        contrast_bias=_coerce_ramp_contrast(data.get("contrast_bias", 1.0)),
        palette_dither_mode=str(data.get("palette_dither_mode", data.get("dither_mode", "none"))),
        input_mode=str(data.get("input_mode", "rgba")),
        output_mode=str(data.get("output_mode", "rgba")),
        quantizer=_coerce_palette_reduction_method(data.get("quantizer", "median-cut")),
        dither_mode=str(data.get("dither_mode", "none")),
    )


def load_app_state() -> dict[str, Any]:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_app_state(data: dict[str, Any]) -> None:
    ensure_storage_dir()
    settings_path().write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def make_process_snapshot(
    settings: PreviewSettings,
    active_palette: list[int] | None,
    palette_path_value: str | None,
    palette_source_value: str | None = None,
) -> dict[str, Any]:
    snapshot = serialize_settings(settings)
    snapshot["palette_size"] = len(active_palette or [])
    snapshot["palette_source"] = palette_source_value
    snapshot["palette_path"] = palette_path_value
    return snapshot


def diff_snapshots(previous: dict[str, Any] | None, current: dict[str, Any]) -> list[str]:
    if not previous:
        return ["Initial process settings snapshot recorded."]
    changes: list[str] = []
    for key, label in SETTING_LABELS.items():
        old_value = _format_snapshot_value(key, previous.get(key))
        new_value = _format_snapshot_value(key, current.get(key))
        if old_value != new_value:
            changes.append(f"{label}: {old_value} > {new_value}")
    return changes or ["No settings changed since the previous successful process."]


def append_process_log(
    *,
    source_path_value: str,
    source_size: tuple[int, int],
    processed_size: tuple[int, int] | None,
    color_count: int | None,
    changes: list[str],
    success: bool,
    message: str,
) -> None:
    ensure_storage_dir()
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [
        f"[{timestamp}] {'SUCCESS' if success else 'FAILURE'}",
        f"Source: {source_path_value}",
        f"Source size: {source_size[0]}x{source_size[1]}",
        f"Processed size: {processed_size[0]}x{processed_size[1]}" if processed_size else "Processed size: n/a",
        f"Processed colors: {color_count if color_count is not None else 'n/a'}",
        f"Message: {message}",
        "Changes:",
        *[f"- {change}" for change in changes],
        "",
    ]
    with process_log_path().open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_generated_shades(value: Any) -> int:
    parsed = _as_int(value, 4)
    allowed = (2, 4, 6, 8, 10)
    if parsed in allowed:
        return parsed
    return min(allowed, key=lambda candidate: abs(candidate - parsed))


def _coerce_auto_detect_count(value: Any) -> int:
    return max(1, min(24, _as_int(value, 12)))


def _coerce_palette_reduction_colors(value: Any) -> int:
    return max(1, min(256, _as_int(value, 16)))


def _coerce_ramp_contrast(value: Any) -> float:
    parsed = _as_float(value, 1.0)
    allowed = tuple(index / 10.0 for index in range(1, 11))
    return min(allowed, key=lambda candidate: abs(candidate - parsed))


def _coerce_palette_reduction_method(value: Any) -> str:
    parsed = str(value or "median-cut").strip().lower()
    if parsed == "topk":
        return "median-cut"
    if parsed in {"median-cut", "kmeans"}:
        return parsed
    return "median-cut"


def _format_snapshot_value(key: str, value: Any) -> str:
    if value in (None, ""):
        return "none"
    return str(value)

from __future__ import annotations

import json
from pathlib import Path


def save_palette(path: Path, palette: list[int]) -> None:
    if path.suffix.lower() == ".json":
        data = {"palette": [f"#{(value >> 16) & 0xFF:02x}{(value >> 8) & 0xFF:02x}{value & 0xFF:02x}" for value in palette]}
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return
    path.write_text(_serialize_gpl_palette(path, palette), encoding="utf-8")


def load_palette(path: Path) -> list[int]:
    suffix = path.suffix.lower()
    if suffix == ".gpl":
        return _load_gpl_palette(path)
    return _load_json_palette(path)


def _load_json_palette(path: Path) -> list[int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("palette", [])
    palette: list[int] = []
    for color in raw:
        if isinstance(color, str) and color.startswith("#") and len(color) == 7:
            palette.append(int(color[1:], 16))
        elif isinstance(color, int):
            palette.append(color & 0xFFFFFF)
        else:
            raise ValueError(f"Invalid palette entry: {color!r}")
    if not palette:
        raise ValueError("Palette file is empty")
    return palette


def _load_gpl_palette(path: Path) -> list[int]:
    palette: list[int] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "GIMP Palette":
        raise ValueError("Invalid GPL palette header")

    for line in lines[1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("Name:") or stripped.startswith("Columns:"):
            continue
        parts = stripped.split()
        if len(parts) < 3:
            raise ValueError(f"Invalid GPL palette line: {line!r}")
        try:
            red, green, blue = (int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError as exc:
            raise ValueError(f"Invalid GPL palette line: {line!r}") from exc
        for channel in (red, green, blue):
            if channel < 0 or channel > 255:
                raise ValueError(f"Invalid GPL colour channel: {line!r}")
        palette.append((red << 16) | (green << 8) | blue)

    if not palette:
        raise ValueError("Palette file is empty")
    return palette


def _serialize_gpl_palette(path: Path, palette: list[int]) -> str:
    lines = [
        "GIMP Palette",
        f"Name: {path.stem}",
        "Columns: 8",
        "#",
    ]
    for index, value in enumerate(palette, start=1):
        red = (value >> 16) & 0xFF
        green = (value >> 8) & 0xFF
        blue = value & 0xFF
        lines.append(f"{red:3d} {green:3d} {blue:3d}\tColor {index}")
    return "\n".join(lines) + "\n"

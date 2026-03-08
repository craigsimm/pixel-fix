from __future__ import annotations

import json
from pathlib import Path


def save_palette(path: Path, palette: list[int]) -> None:
    data = {"palette": [f"#{(value >> 16) & 0xFF:02x}{(value >> 8) & 0xFF:02x}{value & 0xFF:02x}" for value in palette]}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_palette(path: Path) -> list[int]:
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

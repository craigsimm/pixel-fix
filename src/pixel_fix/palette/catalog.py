from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .io import load_palette


@dataclass(frozen=True)
class PaletteCatalogEntry:
    label: str
    path: Path
    colors: tuple[int, ...]
    menu_path: tuple[str, ...]
    source_label: str


def discover_palette_catalog(root: Path) -> list[PaletteCatalogEntry]:
    if not root.exists() or not root.is_dir():
        return []
    return _discover_directory(root, ())


def _discover_directory(directory: Path, parent_menu_path: tuple[str, ...]) -> list[PaletteCatalogEntry]:
    folder_label, palette_labels, ordered_names = _load_directory_metadata(directory)
    current_menu_path = parent_menu_path if directory.name == "palettes" else (*parent_menu_path, folder_label)
    entries: list[PaletteCatalogEntry] = []

    files = [path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".gpl"]
    order_lookup = {name: index for index, name in enumerate(ordered_names)}
    files.sort(key=lambda path: (0, order_lookup[path.name]) if path.name in order_lookup else (1, path.name.lower()))

    for path in files:
        try:
            colors = tuple(load_palette(path))
        except Exception:
            continue
        label = palette_labels.get(path.name, path.stem)
        source_label = " / ".join((*current_menu_path, label)) if current_menu_path else label
        entries.append(
            PaletteCatalogEntry(
                label=label,
                path=path.resolve(),
                colors=colors,
                menu_path=current_menu_path,
                source_label=source_label,
            )
        )

    for child in sorted((path for path in directory.iterdir() if path.is_dir()), key=lambda path: path.name.lower()):
        entries.extend(_discover_directory(child, current_menu_path))

    return entries


def _load_directory_metadata(directory: Path) -> tuple[str, dict[str, str], list[str]]:
    folder_label = directory.name
    palette_labels: dict[str, str] = {}
    ordered_names: list[str] = []
    package_path = directory / "package.json"
    if not package_path.exists():
        return folder_label, palette_labels, ordered_names

    try:
        data = json.loads(package_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return folder_label, palette_labels, ordered_names

    folder_label = str(data.get("displayName") or folder_label)
    contributions = data.get("contributes", {}).get("palettes", [])
    if not isinstance(contributions, list):
        return folder_label, palette_labels, ordered_names

    for entry in contributions:
        if not isinstance(entry, dict):
            continue
        raw_path = entry.get("path")
        if not isinstance(raw_path, str):
            continue
        relative = Path(raw_path)
        if relative.suffix.lower() != ".gpl" or relative.parent != Path("."):
            continue
        ordered_names.append(relative.name)
        palette_id = entry.get("id")
        if isinstance(palette_id, str) and palette_id:
            palette_labels[relative.name] = palette_id

    return folder_label, palette_labels, ordered_names

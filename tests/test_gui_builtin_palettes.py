from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path

import pytest

from pixel_fix.gui.app import PixelFixGui


def _write_gpl(path: Path, *entries: tuple[int, int, int, str]) -> None:
    lines = ["GIMP Palette", "Name: Example", "Columns: 4"]
    for red, green, blue, label in entries:
        lines.append(f"{red} {green} {blue} {label}")
    path.write_text("\n".join(lines), encoding="utf-8")


def _create_palette_tree(root: Path) -> Path:
    palette_root = root / "palettes"
    package_dir = palette_root / "dawn"
    package_dir.mkdir(parents=True, exist_ok=True)
    _write_gpl(package_dir / "db16.gpl", (17, 34, 51, "dark"), (171, 205, 239, "light"))
    (package_dir / "package.json").write_text(
        json.dumps(
            {
                "displayName": "DawnBringer",
                "contributes": {"palettes": [{"id": "DB16", "path": "./db16.gpl"}]},
            }
        ),
        encoding="utf-8",
    )
    return palette_root


def _build_gui(monkeypatch, tmp_path: Path, persisted: dict[str, object] | None = None) -> PixelFixGui:
    palette_root = _create_palette_tree(tmp_path)
    monkeypatch.setattr("pixel_fix.gui.app.load_app_state", lambda: dict(persisted or {}))
    monkeypatch.setattr("pixel_fix.gui.app.save_app_state", lambda _data: None)
    monkeypatch.setattr(
        PixelFixGui,
        "_resource_path",
        staticmethod(lambda name: palette_root if name == "palettes" else tmp_path / name),
    )
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk is not available in this environment: {exc}")
    root.withdraw()
    gui = PixelFixGui(root)
    root.update_idletasks()
    return gui


def test_builtin_palette_menu_uses_catalog_tree(monkeypatch, tmp_path: Path) -> None:
    gui = _build_gui(monkeypatch, tmp_path)
    try:
        builtins_menu = gui._menu_items["built_in_palettes"]
        assert builtins_menu.entrycget(0, "label") == "DawnBringer"
        folder_menu = builtins_menu.nametowidget(builtins_menu.entrycget(0, "menu"))
        assert folder_menu.entrycget(0, "label") == "DB16"
        assert gui._menu_items["palette"].entrycget(5, "label") == "Save Current Palette..."
    finally:
        gui.root.destroy()


def test_selecting_builtin_palette_updates_preview_without_processing(monkeypatch, tmp_path: Path) -> None:
    gui = _build_gui(monkeypatch, tmp_path)
    try:
        entry = gui.builtin_palette_entries[0]
        gui._select_builtin_palette(entry)
        assert gui.active_palette == [0x112233, 0xABCDEF]
        assert gui.active_palette_path == str(entry.path)
        assert gui.palette_info_var.get() == "Palette: Built-in: DawnBringer / DB16 (2 colours)"
        assert gui.downsample_result is None
        assert gui.palette_result is None
    finally:
        gui.root.destroy()


def test_persisted_builtin_palette_is_restored_on_startup(monkeypatch, tmp_path: Path) -> None:
    palette_root = _create_palette_tree(tmp_path)
    palette_path = str((palette_root / "dawn" / "db16.gpl").resolve())
    gui = _build_gui(
        monkeypatch,
        tmp_path,
        persisted={
            "active_palette_path": palette_path,
            "active_palette_source": "Built-in: DawnBringer / DB16",
        },
    )
    try:
        assert gui.active_palette == [0x112233, 0xABCDEF]
        assert gui.active_palette_source == "Built-in: DawnBringer / DB16"
        assert gui.palette_info_var.get() == "Palette: Built-in: DawnBringer / DB16 (2 colours)"
    finally:
        gui.root.destroy()

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path

import pytest

import pixel_fix.gui.app as app_module
from pixel_fix.gui.app import PixelFixGui
from pixel_fix.palette.sort import (
    PALETTE_SELECT_LABELS,
    PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES,
    PALETTE_SORT_LIGHTNESS,
)


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
        palette_labels = [
            gui._menu_items["palette"].entrycget(index, "label")
            for index in range(gui._menu_items["palette"].index("end") + 1)
            if gui._menu_items["palette"].type(index) != "separator"
        ]
        assert "Generate Override Palette" not in palette_labels
        assert "Add Colour" in palette_labels
        assert "Sort Current Palette" in palette_labels
        assert gui._menu_items["palette"].entrycget("Sort Current Palette", "state") == "disabled"
        assert "Clear Active Palette" not in palette_labels
        assert "Save Current Palette..." in palette_labels
        sort_menu = gui._menu_items["palette_sort"]
        sort_labels = [
            sort_menu.entrycget(index, "label")
            for index in range(sort_menu.index("end") + 1)
            if sort_menu.type(index) != "separator"
        ]
        assert "Lightness (Dark -> Light)" in sort_labels
        assert "Hue (Red Wheel)" in sort_labels
        assert "Saturation (Low -> High)" in sort_labels
        assert "Chroma (Low -> High)" in sort_labels
        assert "Temperature (Cool -> Warm)" in sort_labels
        assert "Reset To Source Order" not in sort_labels
        preference_labels = [
            gui._menu_items["preferences"].entrycget(index, "label")
            for index in range(gui._menu_items["preferences"].index("end") + 1)
            if gui._menu_items["preferences"].type(index) != "separator"
        ]
        assert "Palette Reduction Method" in preference_labels
        assert "Colour Ramp" in preference_labels
        assert "Dithering Method" in preference_labels
        select_menu = gui._menu_items["select"]
        select_labels = [select_menu.entrycget(index, "label") for index in range(select_menu.index("end") + 1)]
        similarity_label = PALETTE_SELECT_LABELS[PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES]
        assert "Hue" in select_labels
        assert similarity_label in select_labels
        assert select_labels.index("Hue") < select_labels.index(similarity_label)
        assert gui._menu_bar.entrycget("Select", "state") == "disabled"
    finally:
        gui.root.destroy()


def test_mouse_button_preferences_menu_uses_persisted_assignments(monkeypatch, tmp_path: Path) -> None:
    gui = _build_gui(
        monkeypatch,
        tmp_path,
        persisted={
            "right_mouse_action": app_module.MOUSE_BUTTON_ACTION_SWAP_COLORS,
            "middle_mouse_action": app_module.MOUSE_BUTTON_ACTION_ERASER,
        },
    )
    try:
        preference_labels = [
            gui._menu_items["preferences"].entrycget(index, "label")
            for index in range(gui._menu_items["preferences"].index("end") + 1)
            if gui._menu_items["preferences"].type(index) != "separator"
        ]
        assert "Mouse Buttons" in preference_labels

        mouse_buttons_menu = gui._menu_items["preferences_mouse_buttons"]
        mouse_button_labels = [
            mouse_buttons_menu.entrycget(index, "label")
            for index in range(mouse_buttons_menu.index("end") + 1)
        ]
        assert mouse_button_labels == ["Right Mouse Button", "Middle Mouse Button"]
        assert gui.right_mouse_action_var.get() == app_module.MOUSE_BUTTON_ACTION_SWAP_COLORS
        assert gui.middle_mouse_action_var.get() == app_module.MOUSE_BUTTON_ACTION_ERASER
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
        assert gui._menu_items["palette"].entrycget("Sort Current Palette", "state") == "normal"
        assert gui._menu_bar.entrycget("Select", "state") == "normal"
        assert gui.downsample_result is None
        assert gui.palette_result is None
    finally:
        gui.root.destroy()


def test_opening_palette_browser_creates_popover_and_filters_results(monkeypatch, tmp_path: Path) -> None:
    gui = _build_gui(monkeypatch, tmp_path)
    try:
        gui._open_palette_browser()
        gui.root.update_idletasks()

        assert gui._palette_browser_window is not None
        assert gui._palette_browser_window.winfo_exists() == 1
        assert gui._palette_browser_displayed_entries == gui.builtin_palette_entries
        assert gui._palette_browser_empty_label is None

        gui._palette_browser_search_var.set("zzz")
        gui.root.update_idletasks()

        assert gui._palette_browser_displayed_entries == []
        assert gui._palette_browser_empty_label is not None

        gui._palette_browser_search_var.set("db16")
        gui.root.update_idletasks()

        assert gui._palette_browser_displayed_entries == gui.builtin_palette_entries
        assert gui._palette_browser_empty_label is None
    finally:
        gui.root.destroy()


def test_palette_browser_hover_preview_and_close_restore_active_palette(monkeypatch, tmp_path: Path) -> None:
    gui = _build_gui(monkeypatch, tmp_path)
    try:
        entry = gui.builtin_palette_entries[0]
        gui._select_builtin_palette(entry)
        gui._open_palette_browser()
        gui.root.update_idletasks()

        gui._preview_builtin_palette(entry)

        assert gui._builtin_palette_preview_entry == entry
        assert gui.palette_info_var.get() == "Palette: Preview: DawnBringer / DB16 (2 colours)"

        gui._close_palette_browser()

        assert gui._builtin_palette_preview_entry is None
        assert gui.palette_info_var.get() == "Palette: Built-in: DawnBringer / DB16 (2 colours)"
    finally:
        gui.root.destroy()


def test_palette_browser_selects_entry_and_closes(monkeypatch, tmp_path: Path) -> None:
    gui = _build_gui(monkeypatch, tmp_path)
    try:
        entry = gui.builtin_palette_entries[0]
        gui._open_palette_browser()
        gui.root.update_idletasks()

        gui._select_builtin_palette_from_browser(entry)

        assert gui._palette_browser_window is None
        assert gui.active_palette == [0x112233, 0xABCDEF]
        assert gui.active_palette_path == str(entry.path)
    finally:
        gui.root.destroy()


def test_palette_browser_closes_on_escape_and_outside_click(monkeypatch, tmp_path: Path) -> None:
    gui = _build_gui(monkeypatch, tmp_path)
    try:
        gui._open_palette_browser()
        gui.root.update_idletasks()
        assert gui._palette_browser_window is not None

        result = gui._on_palette_browser_escape()

        assert result == "break"
        assert gui._palette_browser_window is None

        gui._open_palette_browser()
        gui.root.update_idletasks()
        assert gui._palette_browser_window is not None

        gui._on_palette_browser_root_click(type("Event", (), {"widget": gui.root})())

        assert gui._palette_browser_window is None
    finally:
        gui.root.destroy()


def test_palette_browser_load_palette_footer_closes_and_delegates(monkeypatch, tmp_path: Path) -> None:
    gui = _build_gui(monkeypatch, tmp_path)
    try:
        calls: list[str] = []
        gui.load_palette_file = lambda: calls.append("load")
        gui._open_palette_browser()
        gui.root.update_idletasks()

        gui._load_palette_file_from_browser()

        assert gui._palette_browser_window is None
        assert calls == ["load"]
    finally:
        gui.root.destroy()


def test_sorting_builtin_palette_does_not_mutate_catalog_entry(monkeypatch, tmp_path: Path) -> None:
    gui = _build_gui(monkeypatch, tmp_path)
    try:
        entry = gui.builtin_palette_entries[0]
        original_colors = list(entry.colors)

        gui._select_builtin_palette(entry)
        gui.sort_current_palette(PALETTE_SORT_LIGHTNESS)

        assert list(entry.colors) == original_colors
        assert gui.active_palette is not None
        assert gui.active_palette_source == "Sorted: Lightness (Dark -> Light)"
        sort_menu = gui._menu_items["palette_sort"]
        sort_labels = [
            sort_menu.entrycget(index, "label")
            for index in range(sort_menu.index("end") + 1)
            if sort_menu.type(index) != "separator"
        ]
        assert "Reset To Source Order" in sort_labels
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
        assert gui.active_palette_path == palette_path
        assert gui.palette_info_var.get() == "Palette: Built-in: DawnBringer / DB16 (2 colours)"
    finally:
        gui.root.destroy()


def test_palette_adjustment_sliders_start_neutral_even_when_persisted(monkeypatch, tmp_path: Path) -> None:
    gui = _build_gui(
        monkeypatch,
        tmp_path,
        persisted={
            "settings": {
                "palette_brightness": 25,
                "palette_contrast": 140,
                "palette_hue": 15,
                "palette_saturation": 160,
            }
        },
    )
    try:
        assert gui.palette_brightness_var.get() == 0
        assert gui.palette_contrast_var.get() == 0
        assert gui.palette_hue_var.get() == 0
        assert gui.palette_saturation_var.get() == 0
        assert gui.session.current.palette_brightness == 0
        assert gui.session.current.palette_contrast == 100
        assert gui.session.current.palette_hue == 0
        assert gui.session.current.palette_saturation == 100
    finally:
        gui.root.destroy()


def test_legacy_outline_adaptive_flag_restores_adaptive_outline_mode(monkeypatch, tmp_path: Path) -> None:
    gui = _build_gui(
        monkeypatch,
        tmp_path,
        persisted={"outline_adaptive": True},
    )
    try:
        assert gui._outline_adaptive_enabled() is True
        assert gui.outline_adaptive_darken_percent_var.get() == 60
        assert gui.outline_add_generated_colours_var.get() is False
    finally:
        gui.root.destroy()


def test_outline_remove_brightness_threshold_defaults_on_startup(monkeypatch, tmp_path: Path) -> None:
    gui = _build_gui(monkeypatch, tmp_path)
    try:
        assert gui.outline_remove_brightness_threshold_enabled_var.get() is False
        assert gui.outline_remove_brightness_threshold_percent_var.get() == 40
        assert gui.outline_remove_brightness_threshold_direction_var.get() == "dark"
    finally:
        gui.root.destroy()


def test_brush_settings_default_on_startup(monkeypatch, tmp_path: Path) -> None:
    gui = _build_gui(monkeypatch, tmp_path)
    try:
        assert gui.brush_width_var.get() == 1
        assert gui.brush_shape_var.get() == "Square"
    finally:
        gui.root.destroy()

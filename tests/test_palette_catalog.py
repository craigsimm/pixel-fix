import json
from pathlib import Path

from pixel_fix.palette.catalog import discover_palette_catalog


def _write_gpl(path: Path, *entries: tuple[int, int, int, str]) -> None:
    lines = ["GIMP Palette", "Name: Example", "Columns: 4"]
    for red, green, blue, label in entries:
        lines.append(f"{red} {green} {blue} {label}")
    path.write_text("\n".join(lines), encoding="utf-8")


def test_discover_palette_catalog_uses_package_metadata_and_recurses(tmp_path: Path) -> None:
    root = tmp_path / "palettes"
    package_dir = root / "dawn"
    package_dir.mkdir(parents=True)
    _write_gpl(package_dir / "db32.gpl", (0, 0, 0, "black"))
    _write_gpl(package_dir / "db16.gpl", (255, 255, 255, "white"))
    (package_dir / "nested").mkdir()
    _write_gpl(package_dir / "nested" / "extra.gpl", (1, 2, 3, "accent"))
    (package_dir / "package.json").write_text(
        json.dumps(
            {
                "displayName": "DawnBringer",
                "contributes": {
                    "palettes": [
                        {"id": "DB16", "path": "./db16.gpl"},
                        {"id": "DB32", "path": "./db32.gpl"},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    entries = discover_palette_catalog(root)

    assert [entry.label for entry in entries[:2]] == ["DB16", "DB32"]
    assert entries[0].menu_path == ("DawnBringer",)
    assert entries[0].source_label == "DawnBringer / DB16"
    assert entries[2].menu_path == ("DawnBringer", "nested")
    assert entries[2].label == "extra"


def test_discover_palette_catalog_falls_back_to_lexical_order_without_metadata(tmp_path: Path) -> None:
    root = tmp_path / "palettes"
    folder = root / "misc"
    folder.mkdir(parents=True)
    _write_gpl(folder / "zeta.gpl", (0, 0, 0, "black"))
    _write_gpl(folder / "alpha.gpl", (255, 255, 255, "white"))

    entries = discover_palette_catalog(root)

    assert [entry.label for entry in entries] == ["alpha", "zeta"]
    assert all(entry.menu_path == ("misc",) for entry in entries)

# AGENTS.md

## Cursor Cloud specific instructions

### Overview

pixel-fix is a Python desktop application (Tkinter + Pillow) for cleaning up AI-generated pixel art. It provides a GUI and a CLI (`pixel-fix` / `pixel-fix-gui` entrypoints). Runtime dependency: `Pillow>=10.0`. System dependency: `python3-tk`.

### Running tests

```bash
python3 -m pytest tests/ -v
```

All 34 tests run without a display server; they test pipeline logic, palette features, grid scoring, GUI state, zoom, persistence, and processing without instantiating Tk windows.

### Running the CLI

See `README.md` for CLI usage. Note: `run_file` is a placeholder that only copies input to output — the CLI does **not** actually process images yet. Use the GUI for real processing.

### Running the GUI

Requires `DISPLAY` to be set (e.g. `DISPLAY=:1`) and `python3-tk` installed:

```bash
python3 -c "from pixel_fix.gui import main; raise SystemExit(main())"
```

The GUI uses a 2-step workflow: (1) set pixel size + Downsample, (2) Apply Palette.

### Gotchas

- No linter is configured in this project.
- The `pixel-fix` and `pixel-fix-gui` scripts install to `~/.local/bin`. Ensure `$HOME/.local/bin` is on `PATH`.
- Labels in the pipeline are **packed integers** (`0xRRGGBB`), not RGB tuples.
- The CLI `--grid` argument shown in `README.md` does not exist in the parser.
- All preset definitions in `gui/presets.py` crash with `TypeError` when applied — they reference fields (`min_island_size`, `cell_sampler`) that don't exist on `PreviewSettings`.
- Loading a JSON palette with `"palette": null` crashes with `TypeError` in `palette/io.py`.

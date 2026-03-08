# AGENTS.md

## Cursor Cloud specific instructions

### Overview

pixel-fix is a pure-Python desktop application for cleaning up AI-generated pixel art. It provides a Tkinter GUI and a CLI (`pixel-fix` / `pixel-fix-gui` entrypoints). There are zero runtime dependencies beyond the Python stdlib (+ `python3-tk` system package for GUI).

### Running tests

```bash
python3 -m pytest tests/ -v
```

All 16 tests run without a display server; they test pipeline logic, palette features, grid scoring, GUI state, and zoom without instantiating Tk windows.

### Running the CLI

See `README.md` for full CLI usage. Quick example:

```bash
pixel-fix input.png output.png --colors 8 --quantizer kmeans --overwrite
```

### Running the GUI

Requires `DISPLAY` to be set (e.g. `DISPLAY=:1`) and `python3-tk` installed:

```bash
python3 -c "from pixel_fix.gui import main; raise SystemExit(main())"
```

### Gotchas

- No linter is configured in this project. If you want to lint, install one (e.g. `ruff`) yourself.
- The `pixel-fix` and `pixel-fix-gui` scripts install to `~/.local/bin`. Ensure `$HOME/.local/bin` is on `PATH`.
- The CLI's `run_file` behavior is currently a minimal placeholder copy; advanced processing is accessible via `run_on_labels` in the pipeline and through the GUI preview path.
- Labels in the pipeline are **packed integers** (`0xRRGGBB`), not RGB tuples.

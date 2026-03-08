# pixel-fix
Pixel-Fix is a tool for cleaning up AI-generated pixel art. It detects inconsistent pixel scaling, reduces noisy colour palettes, and removes stray pixels to restore clean, readable sprites.

## Current status
This repository now includes an executable MVP scaffold:
- A packaged Python project with a `pixel-fix` CLI.
- Modular pipeline stages (`grid`, `resample`, `palette`, `cleanup`, `pipeline`).
- Deterministic candidate-grid scoring and label-grid cleanup primitives.
- Unit tests for scoring, cleanup, and pipeline behavior.

## Quickstart
```bash
python -m pip install -e .
pixel-fix input.png output.png --grid auto --colors 16 --overwrite
```

> Note: image backend integration is intentionally minimal right now. `run_file` currently performs validated file I/O with placeholder copy behavior while algorithmic stages are implemented and testable through `run_on_labels`.


## Windows GUI preview workflow
A Tkinter-based GUI entrypoint is available via `pixel_fix.gui:main` (used by `scripts/pyinstaller_gui_entry.py`).

Current GUI capabilities:
- Live preview updates when tweak controls change (debounced background render).
- Zoom presets for close inspection: `100%`, `200%`, `400%`, `800%`, plus fit-to-window.
- Undo support to revert the latest tweak (`Ctrl+Z` or **Undo** button).

For local development you can launch it with:

```bash
python -c "from pixel_fix.gui import main; raise SystemExit(main())"
```

## Packaging a Windows GUI `.exe` (PyInstaller)
Use a tiny bootstrap script so the packaged binary always launches the GUI entrypoint (`pixel_fix.gui:main`) instead of the CLI.

```bash
python -m pip install pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed --name pixel-fix-gui --paths src scripts/pyinstaller_gui_entry.py
```

Expected output executable path:

```text
dist/pixel-fix-gui.exe
```

This first packaging pass is intentionally minimal and reliability-focused. Icon and additional Windows resource metadata (version info, file icon, etc.) can be added later as optional PyInstaller flags.

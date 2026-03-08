# pixel-fix
pixel-fix helps clean up AI-generated pixel art for game/UI workflows by reducing noisy colors, enforcing a limited palette, and previewing results interactively.

This repository is currently centered on a **Windows-friendly desktop GUI workflow** (Tkinter + PyInstaller packaging), with CLI support available for automation.

## What the Windows app can do
From one interface, you can:

- Open a PNG and see a live processed preview.
- Switch between **processed** and **original** view.
- Zoom to `100%`, `200%`, `400%`, `800%`, or **Fit**.
- Undo tweak changes (`Ctrl+Z` or **Undo**).
- Choose color modes:
  - `RGBA`
  - `Indexed`
  - `Grayscale`
- Extract and manage palettes:
  - Extract unique colors
  - Generate a limited palette
  - Load/save palette JSON files
- Quantize colors with:
  - `topk`
  - `kmeans`
- Apply dithering:
  - `none`
  - `floyd-steinberg`
  - `ordered` (Bayer)
- Replace colors:
  - Exact replacement
  - Tolerance-based replacement
  - Batch mapping through pipeline options

---

## Windows app quick start
### 1) Install for development
```bash
python -m pip install -e .
```

### 2) Launch the GUI
```bash
python -c "from pixel_fix.gui import main; raise SystemExit(main())"
```

### 3) Typical in-app workflow
1. Click **Open Image** and select a PNG.
2. In **Tweaks**, set:
   - Grid mode / pixel width
   - Color count
   - Quantizer and dithering
   - Input/output color modes
3. Use **Palette** actions:
   - **Extract Unique** for all colors in the image
   - **Generate Limited** for a constrained palette
   - **Load Palette** / **Save Palette** for JSON interchange
4. Use **Color Replacement** to normalize stray shades.
5. Compare **processed** vs **original** view and zoom in for pixel-level inspection.

---

## Build a Windows `.exe`
Use PyInstaller with the GUI bootstrap script so the executable launches the desktop app directly.

```bash
python -m pip install pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed --name pixel-fix-gui --paths src scripts/pyinstaller_gui_entry.py
```

Output:

```text
dist/pixel-fix-gui.exe
```

---

## CLI (optional)
The CLI mirrors the same core processing options and is useful for batch workflows.

Example:

```bash
pixel-fix input.png output.png \
  --grid auto \
  --colors 16 \
  --input-mode rgba \
  --output-mode indexed \
  --quantizer kmeans \
  --dither floyd-steinberg \
  --overwrite
```

> Note: file-level `run_file` behavior is currently minimal placeholder copy I/O while most advanced logic is fully implemented and testable via label-grid pipeline processing and the GUI preview path.

---

## Project status
- Packaged Python project with `pixel-fix` and `pixel-fix-gui` entrypoints.
- Modular architecture (`grid`, `resample`, `palette`, `cleanup`, `pipeline`, `gui`).
- Unit tests for core pipeline and palette behaviors.

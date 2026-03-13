<p align="center">
  <img src="pixel-fix.png">
</p>

# pixel-fix

`pixel-fix` is a desktop-first tool for cleaning up pixel-art-like PNGs into something easier to edit, palette, and export.

The current app is a Windows-friendly Tkinter GUI built around a simple staged workflow:

1. Determine pixel scale
2. Downsample
3. Apply palette
4. Adjust palette

The GUI is the main product, and the CLI now reuses the same non-interactive processing stack for headless and batch work.

## Screenshot

![pixel-fix screenshot](screenshot.png)

## Quick Start

### Install for development

```bash
python -m pip install -e .
```

### Launch the GUI

From the repository root:

```bash
python -c "from pixel_fix.gui import main; raise SystemExit(main())"
```

If you are using the project virtual environment directly on Windows:

```powershell
.\.venv\Scripts\python.exe -c "from pixel_fix.gui import main; raise SystemExit(main())"
```

If the script entrypoints are installed and on `PATH`, this also works:

```bash
pixel-fix-gui
```

## What The App Does

From one interface, you can:

- Open a PNG and switch between `Original` and `Processed` views.
- Set a manual `Pixel size` and downsample with:
  - `Nearest Neighbor`
  - `Bilinear Interpolation`
  - `RotSprite`
- Build palettes in several ways:
  - generate a reduced palette with `Median Cut` or `K-Means Clustering`
  - load built-in `.gpl` palettes from the repository
  - load external `.gpl` or legacy `.json` palettes
- Edit the current palette directly:
  - add colours from the original image
  - add colours by hex code
  - merge selected swatches into one perceptual median colour
  - append ramps from selected swatches using the current ramp settings
  - remove selected swatches
  - sort the current palette by lightness, hue, saturation, chroma, or temperature
- Select palette colours quickly:
  - click, `Shift`-click, `Ctrl`-click, and `Ctrl`-drag in the palette strip
  - `All` / `None` buttons
  - `Select` menu commands based on lightness, saturation, chroma, temperature, hue buckets, and near-duplicate similarity
  - `Selection Threshold` preference from `10%` to `100%`
- Adjust the whole palette or just the selected swatches with:
  - `Brightness`
  - `Contrast`
  - `Hue`
  - `Saturation`
- Apply the current palette only when you click `Apply Palette`.
- Remove connected regions to transparency with the processed-image transparency picker.
- Draw directly into the current processed output with `Pencil` using one selected palette colour, adjustable width, and `Square` or `Round` brush shapes.
- Erase pixels back to transparency with `Eraser` using the same width and shape controls.
- Add a 1-pixel exterior outline around the current processed silhouette using one selected palette colour.
- Remove a 1-pixel exterior outline by eroding the outside edge to transparency, with an optional perceptual brightness threshold.
- Toggle `Pixel Perfect` on the outline tools to bevel hard corners and avoid doubled edge pixels, or turn it off for square-corner behavior.
- Use dithering when applying palettes:
  - `None`
  - `Ordered (Bayer)`
  - `Blue Noise`
- Save the processed image as PNG.
- Save the current palette as `.gpl`.

## Recommended Workflow

1. Open an image.
2. Set the pixel size in `1. Determine pixel scale`.
3. Click `Downsample`.
4. Build or load a palette:
   - click `Generate Reduced Palette`
   - load a built-in or external palette
5. Optionally sort, select, merge, ramp, add, remove, or adjust palette colours.
6. Click `Apply Palette`.
7. Optionally use `Make Transparent`, `Pencil`, `Eraser`, `Add Outline`, or `Remove Outline` on the processed result.
8. Compare the result against the original, then save the image or palette.

Important behavior:

- palette generation, palette sorting, palette selection, and palette adjustments update the `Current palette` preview immediately
- the processed image does not change until you click `Apply Palette`

## Current GUI Layout

### 1. Determine pixel scale

The app currently uses an explicit `Pixel size` value rather than automatic grid detection in the main workflow.

If the source image is `512x512` and `Pixel size` is `2`, the working image becomes `256x256`.

### 2. Downsample

Downsampling is handled in [`src/pixel_fix/resample.py`](src/pixel_fix/resample.py). The three resize modes behave differently:

- `Nearest Neighbor`
  - keeps hard source samples
  - best when the source is already very blocky
- `Bilinear Interpolation`
  - smooths during reduction
  - useful when the source is noisy or slightly anti-aliased
- `RotSprite`
  - uses a practical RotSprite-style approximation to protect diagonals before resampling back down

### 3. Apply palette

This stage is where most of the toolset lives.

#### Selection-driven palette workflow

The palette editor is selection-driven. Use `Generate Reduced Palette` or load a palette first, then select swatches in the `Current palette` strip and edit them directly before apply.

Controls in this stage let you:

- generate a reduced palette from the downsampled image
- apply the current palette to the processed image

#### Palette strip editing

The `Current palette` strip is live and editable before apply:

- `+` adds a colour to the current palette
- `-` removes selected colours
- `Merge` replaces the selected swatches with one perceptual median colour
- `Ramp` appends a full ramp for each selected swatch using the current ramp settings
- `All` selects every swatch
- `None` clears selection

Selection-aware editing is built in:

- if no swatches are selected, palette adjustments affect the full current palette
- if swatches are selected, palette adjustments only affect that subset

#### Palette menu tools

The `Palette` menu currently includes:

- input and output colour-mode controls
- built-in palette browser
- add-colour tools
- sort current palette
- load palette
- save current palette

The `Select` menu lets you select colours in the current palette by:

- dark/light lightness
- low/high saturation
- low/high chroma
- cool/warm temperature
- hue buckets: red, yellow, green, cyan, blue, magenta
- one near-duplicate cluster at a time

Similarity selection helps prevent near-duplicate palette bloat by highlighting the single tightest cluster of perceptually similar swatches before you edit.

For similarity cleanup, use this flow:

1. Run `Select > Similarity (Near-Duplicates)`.
2. Review the highlighted swatches in the `Current palette` strip.
3. Click `Merge` to collapse the selected near-duplicates to one perceptual median colour.
4. Click `Apply Palette` to update the processed image.

The similarity cutoff is controlled by `Preferences > Selection Threshold`.
For similarity selection, a lower `Selection Threshold` is stricter and only catches extremely close matches, while a higher `Selection Threshold` is more permissive and can expand the chosen cluster to slightly looser near-duplicates.

#### Processed-image tools

After a processed image exists, you can:

- `Make Transparent`
  - click the processed image to remove only the connected region under the cursor
- `Pencil`
  - draws into the current output image, not the original source
  - requires exactly one selected swatch in the current palette
  - uses the selected swatch colour for every painted pixel
  - supports adjustable `Width` and `Square` / `Round` brush shapes
  - click and drag to paint continuous strokes without gaps
- `Eraser`
  - erases pixels from the current output image to transparency
  - uses the same `Width` and `Square` / `Round` brush controls as `Pencil`
  - click and drag to erase continuous strokes without gaps
- `Add Outline`
  - `Outline Colour` mode supports `Selected Palette` or `Adaptive`
  - `Selected Palette` requires exactly one selected swatch in the current palette
  - `Adaptive` samples adjacent interior pixels, darkens the dominant interior colour, and can optionally add unique generated outline colours to the current palette
  - adaptive darkening defaults to `60%`
  - adds a 1-pixel outline around the outside silhouette only
  - defaults to `Pixel Perfect`, which chamfers hard corners to avoid doubled edges
- `Remove Outline`
  - removes the outer inside edge of the current silhouette by making it transparent
  - optional `Brightness Threshold` can limit removal to only dark or bright candidate edge pixels
  - the threshold uses perceptual lightness from `0%` to `100%`
  - defaults to `Pixel Perfect`, which removes the cleaned edge mask instead of the full square ring

These tools work through the processed image's per-pixel alpha mask, so saved PNGs preserve the transparency.

### 4. Adjust palette

The adjustment stage uses perceptual palette operations from [`src/pixel_fix/palette/adjust.py`](src/pixel_fix/palette/adjust.py):

- `Brightness`
- `Contrast`
- `Hue`
- `Saturation`

These adjustments modify the current palette preview first. The image only updates when you click `Apply Palette`.

## Preferences

The current `Preferences` menu includes:

- checkerboard background
- resize method
- palette reduction method
- colour-ramp options:
  - ramp steps
  - ramp contrast
- dithering method
- selection threshold

## Shortcuts

- `Ctrl+O`: open image
- `Ctrl+S`: save processed image
- `Ctrl+Shift+S`: save processed image as
- `Ctrl+Z`: undo
- `Ctrl+1`: original view
- `Ctrl+2`: processed view
- `Ctrl+0`: fit zoom
- `F5`: downsample
- `F6`: apply palette

## Saved Data

Per-user app data is stored outside the repository under `%APPDATA%\\pixel-fix`.

That includes:

- settings
- recent files
- process log

## Build A Windows Executable

The repository includes PNG icon source files plus a generated `pixel-fix.ico` for Windows packaging.

### Build with the included PowerShell script

```powershell
.\scripts\build_windows_exe.ps1
```

### Manual build

```bash
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed --name pixel-fix-gui --paths src --icon pixel-fix.ico --add-data "pixel-fix.ico;." --add-data "ico-32.png;." scripts/pyinstaller_gui_entry.py
```

Expected output:

```text
dist/pixel-fix-gui.exe
```

## CLI

The package exposes:

- `pixel-fix`
- `pixel-fix-gui`

Use `pixel-fix` for headless single-image or batch processing. The CLI is config-driven: complex workflows live in a JSON job file, and command-line flags only override common top-level settings.

### Commands

```bash
pixel-fix process INPUT OUTPUT [--config JOB.json] [overrides...]
pixel-fix batch INPUT_DIR OUTPUT_DIR [--config JOB.json] [overrides...]
pixel-fix config init PATH
```

There is also a compatibility shim for the old positional form:

```bash
pixel-fix INPUT OUTPUT ...
```

That still runs, but it prints a deprecation warning and internally routes to `process`.

### Create A Starter Job

```bash
pixel-fix config init jobs/basic.json
```

This writes a starter JSON file like:

```json
{
  "pipeline": {
    "pixel_width": 2,
    "downsample_mode": "nearest",
    "palette_reduction_colors": 16,
    "generated_shades": 4,
    "contrast_bias": 1.0,
    "palette_dither_mode": "none",
    "input_mode": "rgba",
    "output_mode": "rgba",
    "quantizer": "median-cut"
  },
  "palette_source": {
    "type": "generate"
  },
  "palette_steps": [],
  "image_steps": [],
  "output": {
    "batch_glob": "*.png",
    "report_path": null,
    "palette_export": {
      "enabled": false,
      "format": "gpl",
      "filename_suffix": ".palette.gpl"
    }
  }
}
```

### Job Format

`pipeline`

- uses the same core setting names as the GUI where practical:
  - `pixel_width`
  - `downsample_mode`
  - `palette_reduction_colors`
  - `generated_shades`
  - `contrast_bias`
  - `palette_dither_mode`
  - `input_mode`
  - `output_mode`
  - `quantizer`
- legacy `topk` is accepted and normalized to `median-cut`

`palette_source`

- `{"type": "generate"}`
- `{"type": "file", "path": "palettes/custom.gpl"}`
- `{"type": "builtin", "path": "dawn/db16.gpl"}`

`palette_steps`

- `select`
- `select_indices`
- `select_all`
- `clear_selection`
- `sort`
- `merge_selected`
- `ramp_selected`
- `remove_selected`
- `add_colors`
- `adjust_palette`

`image_steps`

- `make_transparent_fill`
- `add_outline`
- `remove_outline`

Selection state persists across palette steps and remains available to later image steps, so a workflow like `select -> merge_selected -> add_outline (palette mode)` works the same way every time.

### Example Process Commands

Generate a starter config:

```bash
pixel-fix config init jobs/cleanup.json
```

Process one image with the config as-is:

```bash
pixel-fix process assets/source.png out/source-fixed.png --config jobs/cleanup.json --overwrite
```

Override a few top-level settings without editing the JSON:

```bash
pixel-fix process assets/source.png out/source-fixed.png --config jobs/cleanup.json --pixel-size 3 --colors 12 --builtin-palette dawn/db16.gpl --overwrite
```

Write the final palette beside the output image:

```bash
pixel-fix process assets/source.png out/source-fixed.png --config jobs/cleanup.json --save-palette out/source-fixed.gpl --overwrite
```

### Example Batch Command

Process every PNG under one input root, mirror the folder tree under the output root, and write a JSON batch report:

```bash
pixel-fix batch assets/sprites out/sprites --config jobs/cleanup.json --glob "*.png" --overwrite
```

By default, batch mode continues on per-file errors and writes `pixel-fix-batch-report.json` into the output root. Use `--report PATH` to choose a different report location, or `--fail-fast` to stop at the first failure.

### Example Job With Palette And Image Steps

```json
{
  "pipeline": {
    "pixel_width": 2,
    "downsample_mode": "nearest",
    "palette_reduction_colors": 16,
    "generated_shades": 4,
    "contrast_bias": 1.0,
    "palette_dither_mode": "ordered",
    "input_mode": "rgba",
    "output_mode": "rgba",
    "quantizer": "median-cut"
  },
  "palette_source": {
    "type": "builtin",
    "path": "dawn/db16.gpl"
  },
  "palette_steps": [
    {
      "type": "select",
      "mode": "similarity-near-duplicates",
      "threshold_percent": 30
    },
    {
      "type": "merge_selected"
    },
    {
      "type": "sort",
      "mode": "lightness"
    }
  ],
  "image_steps": [
    {
      "type": "make_transparent_fill",
      "points": [[0, 0]]
    },
    {
      "type": "add_outline",
      "colour_mode": "adaptive",
      "pixel_perfect": true,
      "adaptive_darken_percent": 60,
      "add_generated_colours": true
    },
    {
      "type": "remove_outline",
      "pixel_perfect": false,
      "brightness_threshold": {
        "enabled": true,
        "percent": 40,
        "direction": "dark"
      }
    }
  ],
  "output": {
    "batch_glob": "*.png",
    "report_path": null,
    "palette_export": {
      "enabled": true,
      "format": "gpl",
      "filename_suffix": ".palette.gpl"
    }
  }
}
```

## Project Structure

- [`src/pixel_fix/gui`](src/pixel_fix/gui): Tkinter app, preview logic, persistence, GUI-side processing helpers
- [`src/pixel_fix/cli_workflow.py`](src/pixel_fix/cli_workflow.py): headless CLI job loading, palette/image step execution, and batch reporting
- [`src/pixel_fix/resample.py`](src/pixel_fix/resample.py): downsampling and RotSprite-style resampling
- [`src/pixel_fix/palette`](src/pixel_fix/palette): palette generation, adjustment, sorting, selection, quantization, loading, saving
- [`src/pixel_fix/pipeline.py`](src/pixel_fix/pipeline.py): pipeline integration
- [`tests`](tests): unit tests for GUI behavior, palette logic, processing, and pipeline code

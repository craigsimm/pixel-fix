<p align="center">
  <img src="pixel-fix.png" alt="pixel-fix" width="320">
</p>

# pixel-fix

`pixel-fix` is a desktop-first tool for cleaning up pixel-art-like PNGs into something easier to edit, palette, and export.

The current app is a Windows-friendly Tkinter GUI built around a simple staged workflow:

1. Determine pixel scale
2. Downsample
3. Apply palette
4. Adjust palette

The GUI is the main product. The CLI entrypoint still exists, but the desktop app is the authoritative workflow.

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

### CLI usage

The CLI runs the same base pipeline and then applies optional deterministic post-processing helpers.

```bash
pixel-fix input.png output.png [options]
```

Post-processing order is always:

1. base process
2. transparency ops
3. outline ops
4. save

Supported non-interactive helper flags:

- `--transparent-color #RRGGBB` (repeatable)
- `--add-outline-color #RRGGBB [--outline-pixel-perfect]`
- `--remove-outline [--outline-pixel-perfect] [--outline-brightness-threshold 0-255]`

Click-based connected-region transparency tools remain GUI-only.

Use `--verbose` to print per-image helper stats (pixels changed per operation).

## What The App Does

From one interface, you can:

- Open a PNG and switch between `Original` and `Processed` views.
- Set a manual `Pixel size` and downsample with:
  - `Nearest Neighbor`
  - `Bilinear Interpolation`
  - `RotSprite`
- Build palettes in several ways:
  - manually pick key colours from the original image
  - auto-detect key colours
  - generate structured ramps from those key colours
  - generate a reduced palette with `Median Cut` or `K-Means Clustering`
  - load built-in `.gpl` palettes from the repository
  - load external `.gpl` or legacy `.json` palettes
- Edit the current palette directly:
  - add colours from the original image
  - add colours by hex code
  - remove selected swatches
  - sort the current palette by lightness, hue, saturation, chroma, or temperature
- Select palette colours quickly:
  - click, `Shift`-click, `Ctrl`-click, and `Ctrl`-drag in the palette strip
  - `All` / `None` buttons
  - `Select` menu commands based on lightness, saturation, chroma, temperature, and hue buckets
  - `Selection Threshold` preference from `10%` to `100%`
- Adjust the whole palette or just the selected swatches with:
  - `Brightness`
  - `Contrast`
  - `Hue`
  - `Saturation`
- Apply the current palette only when you click `Apply Palette`.
- Remove connected regions to transparency with the processed-image transparency picker.
- Add a 1-pixel exterior outline around the current processed silhouette using either one selected palette colour (fixed mode) or adaptive per-pixel colours derived from neighbouring pixels.
- Remove a 1-pixel exterior outline by eroding the outside edge to transparency.
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
   - pick key colours and click `Generate Ramps`
   - click `Auto Detect Key Colours` and then `Generate Ramps`
   - click `Generate Reduced Palette`
   - load a built-in or external palette
5. Optionally sort, select, add, remove, or adjust palette colours.
6. Click `Apply Palette`.
7. Optionally use `Make Transparent`, `Add Outline`, or `Remove Outline` on the processed result.
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

#### Key-colour ramp workflow

You can build a structured palette from manually chosen or auto-detected key colours. The ramp generator in [`src/pixel_fix/palette/advanced.py`](src/pixel_fix/palette/advanced.py) works in perceptual colour space and produces grouped ramps instead of a flat list of unrelated RGB values.

Controls in this stage let you:

- pick key colours from the original image
- auto-detect a configurable number of key colours
- remove or clear key colours
- generate ramps
- generate a reduced palette from the downsampled image
- apply the current palette to the processed image

#### Palette strip editing

The `Current palette` strip is live and editable before apply:

- `+` adds a colour to the current palette
- `-` removes selected colours
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
- perceptual similarity to the current swatch selection

Similarity selection helps prevent near-duplicate palette bloat by expanding your selection to swatches that are effectively the same colour family before you edit.

For similarity cleanup, use this flow:

1. Run the similarity select command from `Select`.
2. Review the highlighted swatches in the `Current palette` strip.
3. Click `Merge` to collapse the selected near-duplicates to one perceptual median colour.
4. Click `Apply Palette` to update the processed image.

The selection count is controlled by `Preferences > Selection Threshold`.
For similarity selection, a lower `Selection Threshold` is stricter (only very close matches are selected), while a higher `Selection Threshold` is more permissive and includes less-similar swatches.

#### Processed-image tools

After a processed image exists, you can:

- `Make Transparent`
  - click the processed image to remove only the connected region under the cursor
- `Add Outline`
  - fixed-colour mode requires exactly one selected swatch in the current palette
  - enable `Adaptive` to derive each outline pixel from neighbouring visible pixels instead of a selected swatch
  - adaptive colour picks the dominant neighbouring colour around that outline pixel, then darkens it (20% by default)
  - ties are resolved deterministically by choosing the lower RGB label value
  - adds a 1-pixel outline around the outside silhouette only
- `Remove Outline`
  - removes the outer inside edge of the current silhouette by making it transparent
<<<<<<< ours
=======
  - defaults to `Pixel Perfect`, which removes the cleaned edge mask instead of the full square ring
  - optional `Brightness ≤` threshold only removes edge pixels at or below that brightness value (0-255)
>>>>>>> theirs

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
  - auto detect count
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

## CLI Status

The project ships two entrypoints:

- `pixel-fix` for scripted/automation-friendly runs
- `pixel-fix-gui` for interactive editing

### Feature scope

The CLI is intended for repeatable, non-interactive image processing tasks:

- single-image transforms with explicit flags
- deterministic batch runs over folders/globs
- settings-profile driven runs for CI/build pipelines
- optional machine-readable reports for downstream tooling

### Differences vs GUI interactive tools

The GUI remains the best place to discover and tune results visually (palette editing, iterative preview, click-driven transparency and outline workflows). The CLI focuses on unattended execution, so:

- no live preview loop or canvas-driven selection
- no interactive palette strip edits during execution
- no manual click-to-pick transparency regions
- explicit conflict/error handling suitable for scripts

### Command examples

Single-file process with a palette:

```bash
pixel-fix in/source.png out/clean.png \
  --palette palettes/gb-studio.gpl \
  --pixel-size 2 \
  --downsample-mode rotsprite
```

Thresholded remove-outline run:

```bash
pixel-fix in/outlined.png out/no-outline.png \
  --remove-outline \
  --remove-outline-threshold 0.22 \
  --pixel-perfect
```

Batch processing with a settings profile:

```bash
pixel-fix batch assets/in assets/out \
  --settings profiles/production.json \
  --include "*.png"
```

Batch processing with JSON report output:

```bash
pixel-fix batch assets/in assets/out \
  --settings profiles/production.json \
  --report-json reports/pixel-fix-run.json
```

### Recommended workflow

For production jobs: tune interactively in the GUI first, export the settings profile, then run the CLI in batch mode with that profile.

### Exit codes and automation conflict/error policies

Use these conventions when integrating with CI, build scripts, or asset pipelines:

- `0`: success (all requested outputs written)
- `2`: usage/config error (invalid flags, malformed profile, unsupported mode)
- `3`: input validation error (missing input, unsupported format)
- `4`: output conflict (target exists without overwrite/force policy)
- `5`: processing/runtime error

Conflict and error policy expectations:

- existing outputs should fail fast by default
- `--overwrite` (or equivalent) should be explicit in automation
- batch mode should continue or stop according to an explicit policy flag (for example `--on-error continue|stop`)
- JSON reports should include per-file status and error messages so failures can be triaged without log scraping

## Project Structure

- [`src/pixel_fix/gui`](src/pixel_fix/gui): Tkinter app, preview logic, persistence, GUI-side processing helpers
- [`src/pixel_fix/resample.py`](src/pixel_fix/resample.py): downsampling and RotSprite-style resampling
- [`src/pixel_fix/palette`](src/pixel_fix/palette): palette generation, adjustment, sorting, selection, quantization, loading, saving
- [`src/pixel_fix/pipeline.py`](src/pixel_fix/pipeline.py): pipeline integration
- [`tests`](tests): unit tests for GUI behavior, palette logic, processing, and pipeline code

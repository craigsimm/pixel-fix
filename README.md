# pixel-fix

`pixel-fix` is a desktop-first tool for turning noisy AI-generated "pixel-art-like" images into cleaner, more controllable pixel art.

The project is currently centered on a Windows-friendly Tkinter GUI with a staged workflow:

1. Determine pixel scale
2. Downsample
3. Apply palette
4. Adjust palette

The GUI is the primary, most up-to-date interface. A CLI entrypoint exists, but the desktop app reflects the current workflow much more accurately.

## Quick start

### Install for development

```bash
python -m pip install -e .
```

### Launch the GUI

```bash
python -c "from pixel_fix.gui import main; raise SystemExit(main())"
```

If your Python user scripts directory is on `PATH`, this also works:

```bash
pixel-fix-gui
```

## What the Windows app does

From one interface, you can:

- Open a PNG and inspect it in the original or processed view.
- Pick a manual pixel size, then downsample with:
  - `Nearest Neighbor`
  - `Bilinear Interpolation`
  - `RotSprite`
- Build palettes in several ways:
  - pick up to 24 key colours manually from the original image
  - auto-detect key colours from the original image
  - generate colour ramps from those key colours
  - generate reduced palettes with `Median Cut` or `K-Means Clustering`
  - load bundled `.gpl` palettes from the `palettes/` tree
  - browse for and load external `.gpl` palettes
  - load legacy `.json` palettes
- Adjust the current palette non-destructively with:
  - `Brightness`
  - `Contrast`
  - `Hue`
  - `Saturation`
- Apply the current palette only when you click `Apply Palette`.
- Compare processed vs original quickly with the processed/original view toggle and right-click quick compare.
- Zoom up to `1600%`.
- Save the current palette as `.gpl`.
- Save the processed image as PNG.

## Recommended GUI workflow

1. Open an image.
2. Set the pixel size in `1. Determine pixel scale`.
3. Click `Downsample`.
4. Choose how to build the palette:
   - manual key colours + `Generate Ramps`
   - `Auto Detect Key Colours` + `Generate Ramps`
   - `Generate Reduced Palette`
   - built-in or loaded palette
5. Optionally tweak the current palette in `4. Adjust palette`.
6. Click `Apply Palette`.
7. Compare the result against the original, then save the image or save the palette.

The important design rule is:

- palette-building and palette-adjustment change the `Current palette` preview immediately
- the processed image does not change until `Apply Palette` is clicked

## What happens behind the scenes

### 1. Determine pixel scale

The app currently uses an explicit `Pixel size` value instead of auto grid detection.

That value tells the pipeline how many source pixels should collapse into one output pixel in each direction.

If the source image is `512x512` and the pixel size is `2`, the target working image becomes `256x256`.

### 2. Downsample

Downsampling is handled in [`src/pixel_fix/resample.py`](./src/pixel_fix/resample.py). The three resize modes are intentionally different:

- `Nearest Neighbor`
  - Preserves hard edges and exact source samples.
  - Best when the image already has very clean, blocky structure.
- `Bilinear Interpolation`
  - Smooths before reduction.
  - Useful when the source is noisy or anti-aliased and you want softer averaging.
- `RotSprite`
  - Implemented here as a pragmatic RotSprite-style approximation.
  - Internally it uses repeated `Scale2x`-style enlargement to protect diagonals, then samples back down with nearest-neighbor.
  - This can preserve some sprite-like edge character better than plain bilinear.

The output of this stage is the reduced working image that all later palette work operates on.

### 3. Build or select a palette

The palette stage has multiple branches depending on how you want control.

#### Manual key colours

If you pick key colours yourself, those colours are used as anchors for ramp generation.

Ramp generation is implemented in [`src/pixel_fix/palette/advanced.py`](./src/pixel_fix/palette/advanced.py) and works in perceptual colour space:

- colours are converted from sRGB into `Oklab`
- hue/chroma/lightness operations are performed in `OKLCh`
- each key colour is treated as the center of a ramp
- lighter shades shift slightly warmer
- darker shades shift slightly cooler
- the `Ramp Contrast` control spreads shades further apart

This produces a structured palette made of grouped ramps rather than a flat list of unrelated RGB centroids.

#### Auto-detected key colours

If you use `Auto Detect Key Colours`, the detector scans the original RGBA image and tries to find representative material/object colours.

The current implementation:

- ignores nearly transparent pixels
- builds a weighted histogram of visible colours
- converts those colours into `Oklab` / `OKLCh`
- separates neutral colours from chromatic colours
- finds major hue families on a circular hue histogram
- picks a representative exact source colour from the midtone range of each family

This gives you a starting set of key colours without inventing synthetic colours that were never in the image.

#### Reduced override palettes

If you choose `Generate Reduced Palette`, the app creates a flat override palette from the already-downsampled image.

That happens in [`src/pixel_fix/palette/quantize.py`](./src/pixel_fix/palette/quantize.py):

- `Median Cut`
  - Uses Pillow's median-cut quantizer.
  - Good for quickly extracting a compact palette from noisy input.
- `K-Means Clustering`
  - Uses a simple iterative RGB k-means implementation in this project.
  - Starts from the most common colours and refines cluster centers over several passes.

These methods generate a palette preview only. The image is still untouched until `Apply Palette`.

#### Built-in and external palettes

Palette files are loaded through [`src/pixel_fix/palette/io.py`](./src/pixel_fix/palette/io.py).

Supported formats:

- GIMP `.gpl` files for loading and saving
- legacy JSON palette files used by older versions of this project

The GUI also scans the repository `palettes/` folder recursively and mirrors its folder structure as nested submenus, so bundled palettes stay organized the same way in the app as they are on disk.

### 4. Adjust the current palette

The `4. Adjust palette` section lets you transform the palette globally before applying it.

This logic lives in [`src/pixel_fix/palette/adjust.py`](./src/pixel_fix/palette/adjust.py) and works in perceptual space:

- `Brightness`
  - shifts palette lightness up or down
- `Contrast`
  - expands or compresses palette lightness around the palette's median lightness
- `Hue`
  - rotates hue angles in `OKLCh`
- `Saturation`
  - scales chroma

Important detail:

- the adjustment section does not edit the processed image live
- it derives a new preview palette from the current base palette
- `Apply Palette` is what commits that adjusted palette to the image

After a successful apply, the adjustment sliders reset to neutral because the adjustment has been baked into the palette that was just applied.

### 5. Map image colours to the palette

When a generated ramp palette is used, mapping is perceptual rather than raw RGB.

The advanced palette code uses:

- `Oklab` as the working colour space
- `HyAB` distance for palette mapping

HyAB treats lightness and chromatic difference separately, which is generally more useful than plain Euclidean RGB distance for readable pixel-art ramps.

For larger palettes, the advanced module can also use a small k-d-tree helper for faster nearest-palette lookup.

### 6. Dithering

Palette application can use:

- `None`
- `Ordered (Bayer)`
- `Blue Noise`

For generated ramp palettes, dithering is ramp-aware: the mapper prefers to dither within the same ramp instead of jumping across unrelated material colours. That helps reduce ugly colour speckling.

### 7. Structured palette metadata

The advanced palette workflow does not just return a flat list of colours.

It produces a structured palette model in [`src/pixel_fix/palette/model.py`](./src/pixel_fix/palette/model.py), including:

- ramps
- seed colours
- shade order
- source labels

This makes it easier to support future features such as palette export, palette swapping, or more ramp-aware cleanup logic.

## Current palette preview vs processed image

The `Current palette` strip above the image is a preview of the palette that would be used if you clicked `Apply Palette` right now.

That means it may represent:

- a generated ramp palette
- a reduced override palette
- a built-in or loaded palette
- the current processed palette with pending adjustment sliders applied

This separation is intentional. It lets you audition palette changes quickly without constantly reprocessing the image.

## Saved settings and logs

The app stores per-user data outside the repository under `%APPDATA%\\pixel-fix`.

That includes:

- settings
- the process log
- recent files

The process log records timestamps, file info, and setting changes between successful runs so you can see what changed from one process to the next.

## Build a Windows executable

The repository includes PNG icon source files in the root plus a generated `pixel-fix.ico` for Windows packaging.

### Build with the included PowerShell script

```powershell
.\scripts\build_windows_exe.ps1
```

This script regenerates the Windows icon and builds the GUI executable with PyInstaller.

### Manual build

```bash
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed --name pixel-fix-gui --paths src --icon pixel-fix.ico --add-data "pixel-fix.ico;." --add-data "ico-32.png;." scripts/pyinstaller_gui_entry.py
```

Expected output:

```text
dist/pixel-fix-gui.exe
```

## CLI status

The CLI entrypoint exists and is useful for experimentation, but it currently lags behind the staged GUI workflow.

In particular:

- the GUI is the authoritative implementation for the current user workflow
- `PixelFixPipeline` label-grid processing is real and tested
- file-level CLI `run_file()` behavior is still intentionally minimal

So for real use, the GUI is the recommended path right now.

## Project structure

- [`src/pixel_fix/gui`](./src/pixel_fix/gui): Tkinter desktop app, settings, persistence, preview logic
- [`src/pixel_fix/resample.py`](./src/pixel_fix/resample.py): pixel-size-based downsampling and RotSprite-style approximation
- [`src/pixel_fix/palette`](./src/pixel_fix/palette): palette generation, adjustment, quantization, loading/saving, perceptual colour math
- [`src/pixel_fix/pipeline.py`](./src/pixel_fix/pipeline.py): staged pipeline integration
- [`tests`](./tests): unit tests covering resampling, palette logic, GUI state, and pipeline behavior

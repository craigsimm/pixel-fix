# Bug Report: push validation for `4edd603a8481a197057f4d80acd5660a79d571b0`

## Scope

- Repository: `craigsimm/pixel-fix`
- Trigger: push to `main`
- Head commit: `4edd603a8481a197057f4d80acd5660a79d571b0`
- Compare: `55c7d15b7037...4edd603a8481`
- Validation date: 2026-03-12

## Test execution summary

### Commands run

1. `python3 -m pip install -e . pytest`
2. `python3 -m pytest -q`
3. `python3 -m pytest -q tests/test_cleanup.py tests/test_grid_scoring.py tests/test_pipeline_color_features.py tests/test_palette_catalog.py tests/test_palette_features.py tests/test_pipeline.py tests/test_gui_persist.py tests/test_gui_state.py tests/test_gui_zoom.py`
4. Headless import-stub run for `tests/test_gui_processing.py`

### Results

| Run | Result | Notes |
| --- | --- | --- |
| Full suite (`python3 -m pytest -q`) | Failed | Aborted during collection because `tkinter` is not installed in the runner. |
| Headless-safe subset | Passed | `58 passed in 0.15s` |
| `tests/test_gui_processing.py` with import stubs | Passed with warning | `51 passed, 1 warning in 0.14s` |

## Confirmed bugs

### 1. Full test suite is not portable to headless Linux runners without Tk

- Severity: **major**
- Failure details:
  - `tests/test_gui_builtin_palettes.py` fails during import with `ModuleNotFoundError: No module named 'tkinter'`
  - `tests/test_gui_processing.py` fails during import because `src/pixel_fix/gui/app.py` imports `tkinter`
- Primary references:
  - `tests/test_gui_builtin_palettes.py:4`
  - `tests/test_gui_builtin_palettes.py:46-49`
  - `src/pixel_fix/gui/app.py:5-8`

#### Root cause analysis

The suite assumes `tkinter` is present at import time. `tests/test_gui_builtin_palettes.py` tries to skip only after calling `tk.Tk()`, but that skip path is never reached when the `tkinter` module itself is missing. `tests/test_gui_processing.py` also imports `pixel_fix.gui.app` at module import time, so the entire test session stops before any non-GUI test can finish.

#### Steps to reproduce

1. Use a Linux environment without the `python3-tk` system package.
2. Install project dependencies and pytest.
3. Run `python3 -m pytest -q`.
4. Observe collection aborting with `ModuleNotFoundError: No module named 'tkinter'`.

#### Suggested fix

- Gate Tk-dependent tests with `pytest.importorskip("tkinter")` before importing GUI modules, or
- wrap GUI imports in the tests so missing Tk becomes a skip instead of a collection error, and
- make CI either install Tk explicitly or split GUI tests into a dedicated job.

---

### 2. Palette edit actions still double-apply active adjustment sliders

- Severity: **major**
- Affected behavior:
  - existing palette edits that read from the displayed palette
  - newly exposed selection-based `Merge` and `Ramp` workflow
- Primary references:
  - `src/pixel_fix/gui/app.py:1078-1099`
  - `src/pixel_fix/gui/app.py:1172-1220`

#### Failure details

When palette adjustment sliders are non-neutral, the editor reads the already adjusted display palette through `_editable_palette_labels()`, writes that adjusted result back as the active palette, and then keeps the same adjustment sliders active. The edited palette is therefore adjusted again on display and on the next apply.

Observed reproduction output from a headless script:

- Display before merge: `['0x4a7eb2', '0x7eb2e6']`
- Merge status message: `Merged 2 palette colours into #6498CC. Click Apply Palette to update the preview.`
- Stored active palette after merge: `['0x6498cc']`
- Display after merge: `['0x7cb1e6']`

The stored merged color and the displayed merged color do not match because the brightness adjustment is applied twice.

#### Root cause analysis

`_editable_palette_labels()` calls `_get_display_palette()`, which returns the slider-adjusted palette rather than the underlying source palette. `_apply_palette_edit()` then saves that adjusted palette as the new active palette without neutralizing or rebasing the adjustment state. The newly added `Merge` and `Ramp` actions both use that edit path.

#### Steps to reproduce

1. Open an image and create or load a current palette.
2. Change any palette adjustment slider, for example set brightness to `+20`.
3. Select two palette swatches.
4. Click `Merge` (or use another edit action that mutates the current palette).
5. Observe that the resulting palette preview is shifted beyond the color reported in the status message because the adjustment has been applied again.

#### Suggested fix

- Perform palette edits against the unadjusted source palette from `_current_palette_source_labels()`, or
- reset/rebase adjustments when converting an adjusted preview into a new active palette, and
- add a regression test that exercises merge/ramp with non-neutral adjustment sliders active.

---

### 3. Legacy or non-GUI `dither_mode` is still ignored by pipeline execution

- Severity: **major**
- Primary reference:
  - `src/pixel_fix/pipeline.py:137`

#### Failure details

`PipelineConfig.dither_mode` is intended to support older callers and non-GUI flows, but the pipeline always prefers `palette_dither_mode` first:

```python
dither_mode = self.config.palette_dither_mode or self.config.dither_mode
```

Because `palette_dither_mode` defaults to the truthy string `"none"`, the fallback never activates.

Observed reproduction on a 4x4 grayscale sample using a black/white palette:

- `PipelineConfig(dither_mode="ordered")` produced the same output as `palette_dither_mode="none"`
- It did **not** match the output from `palette_dither_mode="ordered"`

#### Root cause analysis

The precedence logic treats `"none"` as a real override rather than an empty/default sentinel, so the legacy field can never win unless `palette_dither_mode` is manually changed away from its default value.

#### Steps to reproduce

1. Build a `PipelinePreparedResult` or other pipeline entry point with more than two tones.
2. Run reduction with `PipelineConfig(dither_mode="ordered")` and leave `palette_dither_mode` at its default.
3. Compare the output against:
   - `PipelineConfig(palette_dither_mode="none")`
   - `PipelineConfig(palette_dither_mode="ordered")`
4. Observe that the legacy config matches `none`, not `ordered`.

#### Suggested fix

- Treat `"none"` as "no explicit palette dither override" when `dither_mode` is provided by legacy callers, or
- collapse the two settings into one canonical field before running the pipeline.

## Improvement opportunities

### A. Pillow deprecation warning in image grid conversion

- Severity: **minor**
- Reference:
  - `src/pixel_fix/gui/processing.py:231`
  - `src/pixel_fix/gui/processing.py:219`

`Image.Image.getdata()` now emits a deprecation warning under Pillow 12 and is scheduled for removal in Pillow 14. The warning appeared while running `tests/test_gui_processing.py`:

> `DeprecationWarning: Image.Image.getdata is deprecated and will be removed in Pillow 14 (2027-10-15). Use get_flattened_data instead.`

Suggested action:

- replace the deprecated call with the supported Pillow alternative before the runtime upgrade turns this into a hard failure.

### B. Missing regression coverage for palette edits with active adjustments

- Severity: **minor**
- References:
  - New merge/ramp tests exist in `tests/test_gui_processing.py`
  - No test currently combines those edit actions with non-neutral `PreviewSettings` adjustment sliders

Suggested action:

- add focused tests covering `Merge`, `Ramp`, `Sort`, and `Add Colour` while brightness/hue/saturation sliders are active, using the same headless object construction pattern already present in `tests/test_gui_processing.py`.

## Recommended next actions

1. Fix the Tk portability issue so `python3 -m pytest -q` becomes a reliable CI signal.
2. Fix palette edit rebasing so `Merge` and `Ramp` operate on source palette values rather than adjusted previews.
3. Fix `dither_mode` precedence for legacy and non-GUI callers.
4. Remove the Pillow deprecation warning and add the missing regression coverage.

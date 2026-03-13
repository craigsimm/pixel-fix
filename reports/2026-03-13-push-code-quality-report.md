# Push Analysis Report - 2026-03-13

## Scope

- Trigger: push to `main`
- Head commit: `40aabf909ae6683ba4efaef5a0b58e3165ba8207`
- Merge title: `Implement headless batch CLI`
- Compare URL: `https://github.com/craigsimm/pixel-fix/compare/158c40c8421b...40aabf909ae6`

## Environment

- OS: Linux 6.12
- Python: 3.12.3
- Test runner: `pytest 9.0.2`

## Commands Executed

```bash
python3 -m pip install -e . pytest
python3 -m pytest
python3 -m pytest --ignore tests/test_gui_builtin_palettes.py --ignore tests/test_gui_processing.py
```

## Test Summary

### Full suite

- Status: failed during collection
- Result: `77 items / 2 errors`

Collection errors:

1. `tests/test_gui_builtin_palettes.py`
   - `ModuleNotFoundError: No module named 'tkinter'`
2. `tests/test_gui_processing.py`
   - `ModuleNotFoundError: No module named 'tkinter'`

### Non-GUI subset

- Status: passed
- Result: `77 passed, 13 warnings in 0.24s` when excluding the two GUI modules above

Warnings observed:

- `DeprecationWarning: Image.Image.getdata is deprecated and will be removed in Pillow 14`
  - `src/pixel_fix/gui/processing.py:703`
  - `src/pixel_fix/pipeline.py:232`
  - Also triggered in `tests/test_cli.py:190`

## Confirmed Bugs

### 1. GUI test modules fail collection on Linux runners without Tkinter

- Severity: major
- Failing tests:
  - `tests/test_gui_builtin_palettes.py`
  - `tests/test_gui_processing.py`
- Failure details:
  - `ModuleNotFoundError: No module named 'tkinter'`
- Root cause:
  - Both test modules import GUI code at module import time.
  - `tests/test_gui_builtin_palettes.py` imports `tkinter` on line 4 and `PixelFixGui` on line 9 before its runtime skip helper executes.
  - `tests/test_gui_processing.py` imports `pixel_fix.gui.app` and `PixelFixGui` at module scope.
  - `src/pixel_fix/gui/app.py` imports `tkinter` at module scope, so pytest collection aborts before any `pytest.skip(...)` path can run on minimal Linux CI images.
- File references:
  - `tests/test_gui_builtin_palettes.py:4-9`
  - `tests/test_gui_builtin_palettes.py:41-57`
  - `tests/test_gui_processing.py:7-8`
  - `src/pixel_fix/gui/app.py:5`
- Steps to reproduce:
  1. Use a Linux environment without the `tkinter` system package installed.
  2. Install the project and pytest.
  3. Run `python3 -m pytest`.
  4. Observe collection failure before test execution begins.
- Suggested fix:
  - Use `pytest.importorskip("tkinter")` before importing GUI modules.
  - Move `PixelFixGui` imports inside helpers or fixtures that first verify Tk availability.
  - Consider marking GUI tests separately so they only run in jobs that install Tk.

### 2. `pixel-fix process` can crash with a raw Pillow exception on corrupt images

- Severity: major
- Failure details:
  - Reproduced exception:
    - `UnidentifiedImageError: cannot identify image file '/tmp/.../bad.png'`
- Root cause:
  - `main()` only converts `CliJobError`, `FileExistsError`, `FileNotFoundError`, and `ValueError` into clean CLI error output.
  - The image decode path in `run_process_job()` calls `load_png_rgba_image()`, which uses Pillow image open/convert operations that can raise `PIL.UnidentifiedImageError` or related `OSError` subclasses.
  - Batch mode catches broad exceptions per file, but single-file mode does not, so the new CLI paths behave inconsistently.
- File references:
  - `src/pixel_fix/cli.py:64-72`
  - `src/pixel_fix/cli_workflow.py:244-250`
  - `src/pixel_fix/gui/processing.py:695-697`
- Steps to reproduce:
  1. Create a file named `bad.png` containing non-image text.
  2. Run `python3 -m pixel_fix.cli process bad.png out.png --overwrite`.
  3. Observe an uncaught Pillow exception instead of a clean `pixel-fix: ...` CLI error.
- Suggested fix:
  - Catch `PIL.UnidentifiedImageError` and relevant `OSError` cases in the CLI entrypoint or normalize them into `CliJobError` in the workflow layer.

### 3. Transparent PNG input loses alpha in the shared headless pipeline

- Severity: major
- Failure details:
  - Reproduced with a two-pixel RGBA input where the first pixel had alpha `0`.
  - Output after `run_process_job()` became:
    - `[(255, 0, 0, 255), (0, 255, 0, 255)]`
  - The fully transparent source pixel became fully opaque.
- Root cause:
  - `run_process_job()` loads an RGBA image, then immediately converts it to an RGB grid through `image_to_rgb_grid()`.
  - The alpha channel is discarded before processing.
  - Output alpha is only preserved when an explicit transparency mask is constructed later by image-edit steps; original source transparency is not carried through the shared CLI path.
- File references:
  - `src/pixel_fix/cli_workflow.py:249-250`
  - `src/pixel_fix/gui/processing.py:700-704`
- Steps to reproduce:
  1. Create a PNG with at least one fully transparent pixel.
  2. Run `run_process_job()` or `pixel-fix process` with `pixel_width=1`.
  3. Open the output PNG.
  4. Observe previously transparent pixels saved as opaque.
- Suggested fix:
  - Preserve source alpha separately and propagate it into `ProcessResult.alpha_mask`, or introduce an RGBA-aware conversion path for headless processing.

### 4. `output.palette_export.format` is not honored unless the filename suffix also matches

- Severity: minor
- Failure details:
  - Reproduced with:
    - `"format": "json"`
    - `"filename_suffix": ".palette.gpl"`
  - Output file was written as `format-out.palette.gpl`.
  - File contents started with `GIMP Palette`, proving GPL serialization was used.
- Root cause:
  - Job normalization validates and stores `output.palette_export.format`, but `_save_palette_export()` only uses `filename_suffix` to generate the output filename.
  - Actual serializer selection is delegated to `save_palette()`, which chooses format from the target file extension.
  - As a result, the `format` field is misleading unless the suffix is changed too.
- File references:
  - `src/pixel_fix/cli_workflow.py:438-459`
  - `src/pixel_fix/cli_workflow.py:827-848`
- Steps to reproduce:
  1. Configure a job with `output.palette_export.enabled = true`.
  2. Set `output.palette_export.format = "json"`.
  3. Leave `output.palette_export.filename_suffix = ".palette.gpl"`.
  4. Run `run_process_job()` and inspect the palette file.
  5. Observe a GPL file rather than JSON output.
- Suggested fix:
  - Either derive the extension from `format`, or validate that `filename_suffix` is compatible with `format` and fail fast when they disagree.

## Improvement Opportunities

### A. Test environment is underspecified for a `src/` layout package

- Severity: minor
- Observation:
  - The repository uses a `src/` layout, tests import `pixel_fix` directly, and `pyproject.toml` has no pytest path configuration or test extras.
  - In a plain checkout, `pytest` will not work unless the package is installed first.
- File references:
  - `pyproject.toml:19-23`
  - `tests/test_cli.py:9-13`
- Suggestion:
  - Add `[project.optional-dependencies]` with a `test` extra including `pytest`.
  - Optionally add pytest configuration or CI bootstrapping documentation so `python3 -m pytest` works predictably.

### B. Pillow `getdata()` deprecations should be cleaned up before Pillow 14

- Severity: minor
- Observation:
  - Multiple runtime paths still call `Image.getdata()`, which now emits deprecation warnings under Pillow 12.
- File references:
  - `src/pixel_fix/gui/processing.py:691`
  - `src/pixel_fix/gui/processing.py:703`
  - `src/pixel_fix/pipeline.py:232`
- Suggestion:
  - Replace deprecated access with the recommended Pillow API before the removal deadline.

### C. Batch mode repeats static palette-source work per file

- Severity: minor
- Observation:
  - `run_batch_job()` calls `run_process_job()` for every input.
  - File palettes and built-in palette catalogs are reloaded for each file even when the palette source is identical across the whole batch.
- File references:
  - `src/pixel_fix/cli_workflow.py:328-345`
  - `src/pixel_fix/cli_workflow.py:389-399`
  - `src/pixel_fix/cli_workflow.py:531-545`
- Suggestion:
  - Pre-resolve constant palette inputs once per batch job and reuse them inside the loop.

### D. Installed-package resource loading looks fragile for built-in palettes

- Severity: minor
- Observation:
  - Built-in palette discovery relies on repo-relative parent walking from `__file__`.
  - This is usually reliable in editable checkouts but fragile for wheel installs unless the assets are packaged explicitly.
- File references:
  - `src/pixel_fix/cli_workflow.py:868-871`
- Suggestion:
  - Move palette assets under the package tree and load them via `importlib.resources`.

## Missing Coverage

- No CLI regression test that verifies `process` handles corrupt image input gracefully.
- No regression test covering transparent source PNG preservation through the new headless CLI workflow.
- No test asserting that `output.palette_export.format` controls the emitted palette format independently of `filename_suffix`.
- GUI tests do not currently protect collection on runners without Tk installed.

## Recommended Next Actions

1. Fix GUI test collection portability first so Linux CI can complete.
2. Normalize corrupt-image errors into user-friendly CLI failures.
3. Preserve source transparency through the headless workflow.
4. Align palette export behavior so `format` is authoritative or validated.
5. Add test extras and resolve Pillow deprecations before they become breaking changes.

## Current Assessment

- Release readiness: not clean for generic Linux CI
- Functional status of new CLI/batch feature: core non-GUI behavior appears stable
- Blocking issue for repository health: full test suite currently fails on Linux environments without Tkinter

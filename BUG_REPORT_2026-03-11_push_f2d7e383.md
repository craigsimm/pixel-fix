# Bug Report: push validation for `f2d7e38318627e7b1a40614e3dc4856d891a848c`

## Scope

- Repository: `craigsimm/pixel-fix`
- Trigger: push to `main`
- Compare: `d24f8964e639...f2d7e3831862`
- Validation date: 2026-03-11

## Test execution summary

### Full suite

Command:

```bash
python3 -m pytest
```

Result: failed during collection.

Observed failures:

1. `tests/test_gui_builtin_palettes.py`
   - Failure detail: `ModuleNotFoundError: No module named 'tkinter'`
   - Import site: direct test import at `tests/test_gui_builtin_palettes.py:4`
2. `tests/test_gui_processing.py`
   - Failure detail: `ModuleNotFoundError: No module named 'tkinter'`
   - Import site: `src/pixel_fix/gui/app.py:5` via test import path

### Non-GUI subset

Command:

```bash
python3 -m pytest --ignore=tests/test_gui_builtin_palettes.py --ignore=tests/test_gui_processing.py
```

Result: `55 passed in 0.16s`

Conclusion: the current push is blocked by GUI test environment/setup issues, but the remaining suite passes in this environment.

## Confirmed bugs

### 1. GUI test suite is not portable to environments without `tkinter`

- Severity: major
- Affected tests:
  - `tests/test_gui_builtin_palettes.py`
  - `tests/test_gui_processing.py`
- Failure details:
  - Test collection aborts before execution with `ModuleNotFoundError: No module named 'tkinter'`.
- Root cause analysis:
  - The project does not declare any optional GUI test dependency or fallback behavior in `pyproject.toml`, while GUI tests import `tkinter` unconditionally.
  - `tests/test_gui_builtin_palettes.py:4` imports `tkinter` directly.
  - `tests/test_gui_processing.py` imports `pixel_fix.gui.app`, which imports `tkinter` at `src/pixel_fix/gui/app.py:5`.
- Steps to reproduce:
  1. Use a Python environment without the system `tkinter` package installed.
  2. Run `python3 -m pytest`.
  3. Observe collection stop with the two import errors above.
- Suggested fixes:
  - Either provision `tkinter` in CI/test environments, or skip GUI tests when `tkinter` is unavailable.
  - Consider declaring a documented GUI test prerequisite so failures are intentional rather than surprising.

### 2. CLI output path is functionally broken: `run_file()` copies bytes instead of producing processed PNG output

- Severity: critical
- Existing failing test: none
- Failure details:
  - `PixelFixPipeline.run_file()` validates extensions, then calls `copy_as_placeholder()`, which copies input bytes directly to the output path.
  - A JPEG input therefore produces an output file named `.png` whose contents are still JPEG bytes.
- Evidence:
  - `src/pixel_fix/pipeline.py:224-227`
  - `src/pixel_fix/io.py:25-28`
  - `src/pixel_fix/cli.py:30-45`
- Root cause analysis:
  - The CLI still exposes real processing options (`--pixel-size`, `--colors`, `--output-mode`, `--dither`, etc.), but the file-based pipeline path is still a placeholder implementation.
  - This causes silent data-format corruption and ignores user-selected processing settings.
- Steps to reproduce:
  1. Create a JPEG input image.
  2. Run `python3 -m pixel_fix.cli in.jpg out.png`.
  3. Inspect `out.png`; its bytes match the JPEG input instead of a generated PNG.
- Reproduction result from this validation:
  - `{'output_exists': True, 'output_format': 'jpeg', 'same_bytes': True}`
- Suggested fixes:
  - Implement the real file pipeline or reject CLI file processing until the feature is complete.
  - Add end-to-end CLI tests that validate file signatures and visible output changes.

### 3. Default pipeline color reduction silently does nothing when only `colors`/`quantizer` are configured

- Severity: major
- Existing failing test: none
- Failure details:
  - `PipelineConfig.colors` and `PipelineConfig.quantizer` are not wired into `run_prepared_labels()` unless the caller supplies explicit key colors or an override/structured palette.
  - With no explicit palette inputs, the generated structured palette is empty and mapping returns the original labels unchanged.
- Evidence:
  - `src/pixel_fix/pipeline.py:153-177`
  - `src/pixel_fix/palette/advanced.py:491-516`
- Root cause analysis:
  - `run_prepared_labels()` now delegates palette creation to `generate_structured_palette(...)`.
  - `generate_structured_palette()` explicitly discards `colors` and returns an empty palette whenever `key_colors` and `seed_colors` are missing.
  - `map_palette_to_labels()` then hits the empty-palette fast path and returns a copy of the input labels.
- Steps to reproduce:
  1. Run:
     ```python
     from pixel_fix.pipeline import PipelineConfig, PixelFixPipeline
     labels = [[0xFF0000, 0x00FF00], [0x0000FF, 0xFFFFFF]]
     result = PixelFixPipeline(PipelineConfig(pixel_width=1, colors=1)).run_on_labels_detailed(labels)
     ```
  2. Inspect `result.labels` and `result.effective_palette_size`.
  3. Observe that all original colors remain and the effective palette size is `0`.
- Reproduction result from this validation:
  - `{'unique_output_colors': ['0xff', '0xff00', '0xff0000', '0xffffff'], 'effective_palette_size': 0, 'seed_count': 0, 'ramp_count': 0}`
- Suggested fixes:
  - Restore a real reduction path for plain `colors` / `quantizer` usage, or reject configs that do not provide explicit palette inputs.
  - Add a regression test for `PipelineConfig(colors=1)` and similar default cases.

### 4. Legacy `dither_mode` is masked, and the CLI advertises an unsupported mode

- Severity: major
- Existing failing test: none
- Failure details:
  - `self.config.palette_dither_mode or self.config.dither_mode` always prefers `palette_dither_mode` because its default is the non-empty string `"none"`.
  - The CLI still allows `--dither floyd-steinberg`, but `map_palette_to_labels()` rejects that mode with `ValueError`.
- Evidence:
  - `src/pixel_fix/pipeline.py:137`
  - `src/pixel_fix/cli.py:19`
  - `src/pixel_fix/palette/advanced.py:667-696`
- Root cause analysis:
  - The new structured-palette mapping path introduced `palette_dither_mode`, but the fallback logic makes the legacy `dither_mode` setting ineffective by default.
  - CLI choices were not updated to match the new mapping implementation.
- Steps to reproduce:
  1. Compare a pipeline run with `dither_mode="ordered"` against one with `palette_dither_mode="ordered"`.
  2. Observe that only the explicit `palette_dither_mode` run produces ordered dithering output.
  3. Run with `palette_dither_mode="floyd-steinberg"` or use the CLI `--dither floyd-steinberg` path and observe a `ValueError`.
- Reproduction results from this validation:
  - Masked vs explicit ordered-dither output differed:
    - masked run unique colors: `['0xd1d1d1']`
    - explicit ordered-dither run unique colors: `['0xd1d1d1', '0xf8f8f8']`
  - Unsupported mode reproduction:
    - `ValueError: Unsupported dither mode: floyd-steinberg`
- Suggested fixes:
  - Make `palette_dither_mode` nullable, or explicitly honor legacy `dither_mode` when the user sets it.
  - Remove unsupported CLI choices or implement the missing dithering mode in the mapping layer.

### 5. Background GUI jobs can complete into the wrong document after a new image is opened

- Severity: major
- Existing failing test: none
- Failure details:
  - The GUI starts asynchronous worker threads for downsampling and palette application, but image-open flows remain available.
  - Completion handlers then write back into shared GUI state and logs using the current `self.source_path` and current display state rather than a request-specific token.
- Evidence:
  - `src/pixel_fix/gui/app.py:814-849`
  - `src/pixel_fix/gui/app.py:1533-1569`
  - `src/pixel_fix/gui/app.py:1571-1636`
  - `src/pixel_fix/gui/app.py:1768-1776`
  - `src/pixel_fix/gui/app.py:1812-1820`
  - `src/pixel_fix/gui/app.py:2444-2504`
- Root cause analysis:
  - `downsample_current_image()` and `reduce_palette_current_image()` capture no job identifier tied to the currently opened image.
  - `_handle_downsample_success()` and `_handle_palette_success()` append logs using `str(self.source_path)` at completion time, even if `self.source_path` now refers to a different image.
  - `_open_image_path()` mutates shared state immediately and does not guard against in-flight worker completion.
- Steps to reproduce:
  1. Open image A.
  2. Start Downsample or Apply Palette.
  3. Before completion, open image B.
  4. Observe the old job overwrite the new preview state and/or log against image B's path.
- Suggested fixes:
  - Attach a monotonically increasing request token to processing jobs and ignore stale completions.
  - Disable image-open flows while processing, or safely cancel/retire in-flight jobs when a new image is loaded.
  - Add GUI tests for mid-process document switching.

### 6. Failed image loads leave `source_path` mutated to the failed file

- Severity: minor
- Existing failing test: none
- Failure details:
  - `_open_image_path()` assigns `self.source_path = path` before image loading and RGB-grid conversion succeed.
  - On exception, the handler shows an error dialog but does not roll back the path or any partially updated state.
- Evidence:
  - `src/pixel_fix/gui/app.py:814-849`
- Root cause analysis:
  - State mutation occurs too early in the load sequence, and the exception path has no rollback logic.
- Steps to reproduce:
  1. Open a valid image.
  2. Attempt to open a corrupt or invalid `.png`.
  3. Dismiss the error.
  4. Observe that the old image can remain visible while `source_path` now points at the failed file, affecting later logging and status.
- Suggested fixes:
  - Load into temporary locals first, then commit the new path and display state only after success.
  - Add an error-path regression test around `_open_image_path()`.

## Improvement opportunities

### Missing test coverage

1. No end-to-end CLI tests cover `pixel_fix.cli` or `PixelFixPipeline.run_file()`.
2. No regression tests cover the default reduction path driven only by `colors` / `quantizer`.
3. No pipeline test proves that legacy `dither_mode` changes output.
4. No GUI tests exercise:
   - switching images during background processing
   - image-load error rollback
   - palettes larger than `MAX_PALETTE_SWATCHES` (`src/pixel_fix/gui/app.py:72`, `2229-2238`)
5. Persistence tests cover happy paths but not write failures in:
   - `src/pixel_fix/gui/persist.py:110-112`
   - `src/pixel_fix/gui/persist.py:140-164`

### Code quality / best-practice concerns

1. `mapping_seconds` is always reported as `0.0`, which makes performance telemetry misleading.
   - Evidence: `src/pixel_fix/pipeline.py:171-192`
2. The palette display truncates to 256 swatches, but selection/edit flows operate on the full palette, creating correctness risk for larger palettes.
   - Evidence: `src/pixel_fix/gui/app.py:72`, `1009-1026`, `1136-1149`, `2229-2238`
3. Persistence write paths do not handle `OSError`, so read-only/full storage directories can turn normal GUI actions into unhandled exceptions.
   - Evidence: `src/pixel_fix/gui/persist.py:110-112`, `140-164`
4. Ordered and blue-noise dithering still run in Python-level nested loops, which is a likely performance bottleneck on large images.
   - Evidence: `src/pixel_fix/palette/advanced.py:669-694`

## Recommended next actions

1. Fix or temporarily disable the placeholder CLI file path before advertising it as functional.
2. Restore a real default palette-reduction path for `colors` / `quantizer`.
3. Unify dithering settings so the CLI and pipeline expose only supported, effective options.
4. Make GUI processing jobs request-scoped to prevent stale worker completions from mutating the active document.
5. Make GUI tests resilient to environments where `tkinter` is not installed, or explicitly provision it in CI.

# Bug Report: push validation for `55c7d15`

## Context

- Repository: `craigsimm/pixel-fix`
- Trigger: push to `main`
- Commit: `55c7d15b70374dcb2b725489e07423138ecee9cf`
- Commit message: `Update image tag in README`
- Compare: <https://github.com/craigsimm/pixel-fix/compare/8596bff2e643...55c7d15b7037>
- Validation date: 2026-03-11
- Environment: Linux, Python 3.12.3

## Executive summary

The pushed commit only changes `README.md`, but repository validation still surfaces several outstanding product and CI issues:

- The full pytest suite is **not green** on this Linux runner because GUI-related tests fail during collection when `tkinter` is unavailable.
- The non-blocked subset still passes cleanly: **55 passed**.
- The CLI remains a placeholder path that **copies input bytes to the output file** instead of running the pipeline.
- Several GUI and pipeline behaviors are either silently incorrect or under-tested.

## Test execution

### Environment setup

```bash
python3 -m pip install -e . pytest
```

### Full suite

```bash
python3 -m pytest
```

Result:

- `collected 55 items / 2 errors`
- collection failed before the suite completed

Observed failures:

1. `tests/test_gui_builtin_palettes.py`
   - Failure type: collection error
   - Detail: `ModuleNotFoundError: No module named 'tkinter'`
2. `tests/test_gui_processing.py`
   - Failure type: collection error
   - Detail: `ModuleNotFoundError: No module named 'tkinter'`

### Non-blocked subset

```bash
python3 -m pytest tests/test_cleanup.py tests/test_grid_scoring.py tests/test_palette_catalog.py tests/test_palette_features.py tests/test_pipeline.py tests/test_pipeline_color_features.py tests/test_gui_persist.py tests/test_gui_state.py tests/test_gui_zoom.py
```

Result:

- `55 passed in 0.15s`

## Confirmed bugs

### 1. Linux CI is blocked by unconditional `tkinter` imports during GUI test collection

- Severity: **major**
- Affected tests:
  - `tests/test_gui_builtin_palettes.py` (collection failure)
  - `tests/test_gui_processing.py` (collection failure)
- Failure details:
  - `ModuleNotFoundError: No module named 'tkinter'`
- Source references:
  - `src/pixel_fix/gui/app.py:5-10`
  - `tests/test_gui_processing.py:6-7`
  - `tests/test_gui_builtin_palettes.py:4, 9, 46-49`

#### Root cause analysis

`pixel_fix.gui.app` imports `tkinter` and `ImageTk` at module import time. `tests/test_gui_processing.py` imports `pixel_fix.gui.app` directly during test-module import, and `tests/test_gui_builtin_palettes.py` imports `tkinter` at module scope. The only current skip path is inside `_build_gui()` after `tk.Tk()` is called, which is too late to help when `import tkinter` itself fails.

#### Steps to reproduce

1. Use a Linux Python environment without Tk support installed.
2. Run `python3 -m pytest`.
3. Observe collection failing before test execution starts.

#### Suggested fix

- Guard GUI-only tests with `pytest.importorskip("tkinter")` or equivalent module-level protection.
- Either install Tk in CI explicitly or split GUI tests into a job that guarantees Tk availability.

#### Coverage gap

There is no CI/workflow configuration in the repository that ensures GUI tests run in a Tk-capable environment, and the current skip logic does not protect against missing-module import failures.

---

### 2. The shipped CLI does not process images; it only copies input bytes to the output path

- Severity: **major**
- Test name / failure details:
  - No existing automated test currently fails because this path is untested.
  - Runtime reproduction confirms the bug.
- Source references:
  - `pyproject.toml:15-17`
  - `src/pixel_fix/cli.py:9-45`
  - `src/pixel_fix/pipeline.py:224-227`
  - `src/pixel_fix/io.py:16-28`

#### Root cause analysis

The CLI parses real processing options and constructs `PipelineConfig`, but `PixelFixPipeline.run_file()` never invokes the pipeline. It validates the paths and then calls `copy_as_placeholder()`, which performs a raw byte-for-byte copy.

#### Steps to reproduce

1. Create a JPEG input file.
2. Run the CLI with processing options, for example:

   ```bash
   python3 -m pixel_fix.cli input.jpg output.png --colors 2 --dither ordered --save-palette out.gpl --overwrite
   ```

3. Inspect the result.

Observed in validation:

- `output.png` contained the same bytes as `input.jpg`
- the file header remained JPEG (`FF D8 FF`)
- `--save-palette` produced no palette file

#### Impact

- All CLI processing flags are effectively ignored.
- A non-PNG input can be written to a `.png` filename unchanged.
- The published CLI contract is misleading.

#### Suggested fix

- Replace the placeholder `run_file()` path with real load -> prepare -> process -> PNG save behavior.
- Add CLI end-to-end tests that assert the output is actually processed and encoded as PNG.

#### Coverage gap

No tests currently exercise `pixel_fix.cli.main()`, `build_parser()`, or `PixelFixPipeline.run_file()`.

---

### 3. Sorting or editing a palette while adjustment sliders are active can double-apply the adjustment

- Severity: **major**
- Test name / failure details:
  - No existing automated test currently fails.
  - Static inspection shows the active palette is overwritten with an already-adjusted display palette, then adjusted again on apply.
- Source references:
  - `src/pixel_fix/gui/app.py:746-769`
  - `src/pixel_fix/gui/app.py:968-989`
  - `src/pixel_fix/gui/app.py:1036-1057`
  - `src/pixel_fix/gui/app.py:1111-1133`
  - `src/pixel_fix/gui/app.py:1640-1672`
  - `src/pixel_fix/gui/app.py:2328-2336`

#### Root cause analysis

`_get_display_palette()` returns the adjusted palette when sliders are non-neutral. `sort_current_palette()` and palette edit paths use that display palette as their source and store it back into the active palette. Because `_apply_active_palette()` does not reset the sliders, applying the palette later runs the adjustments again on top of an already-adjusted base.

#### Steps to reproduce

1. Open an image and downsample it.
2. Load or generate a palette.
3. Move any palette adjustment slider off neutral.
4. Sort the current palette, or add/remove a palette colour.
5. Click `Apply Palette`.
6. Observe that the applied output reflects the adjustment twice rather than once.

#### Suggested fix

- Base sort/edit operations on the unadjusted source palette, not the current display palette.
- Add a regression test that combines non-neutral adjustments with sort/edit followed by apply.

#### Coverage gap

Current tests cover sort behavior, edit behavior, and adjusted display generation independently, but not the combined non-neutral workflow that triggers the double-apply bug.

---

### 4. Pipeline `colors` and `quantizer` settings are a no-op unless the caller also provides key colours or an override palette

- Severity: **major**
- Test name / failure details:
  - No existing automated test currently fails.
  - Runtime reproduction confirmed that `PipelineConfig(colors=1, quantizer="kmeans")` can leave labels unchanged with an empty effective palette.
- Source references:
  - `src/pixel_fix/pipeline.py:22-38`
  - `src/pixel_fix/pipeline.py:153-166`
  - `src/pixel_fix/palette/advanced.py:491-519`
  - `src/pixel_fix/palette/advanced.py:647-659`

#### Root cause analysis

The default pipeline path calls `generate_structured_palette()` without using `colors` or `quantizer`. That function explicitly discards `colors` and returns an empty structured palette when there are no selected key colours. `map_palette_to_labels()` then treats the empty palette as a no-op and returns the original labels unchanged.

#### Steps to reproduce

1. Run the pipeline with a config such as:

   ```python
   PixelFixPipeline(PipelineConfig(colors=1, quantizer="kmeans")).run_on_labels_detailed(labels)
   ```

2. Do not provide `key_colors`, `palette_override`, `palette_path`, or `structured_palette`.
3. Observe that the output labels remain unchanged and `effective_palette_size` is `0`.

#### Suggested fix

- Either wire `colors`/`quantizer` into a real default palette-reduction path or remove/deprecate them from the generic pipeline contract.
- Add a test asserting that pipeline-level color-reduction settings actually change output.

#### Coverage gap

The existing tests cover key-colour palette generation and explicit overrides, but do not verify that the pipeline’s advertised `colors`/`quantizer` settings have any effect in the default path.

---

### 5. Legacy `dither_mode` is masked by `palette_dither_mode="none"`

- Severity: **major**
- Test name / failure details:
  - No existing automated test currently fails.
  - Static inspection shows the wrong precedence rule in the active pipeline.
- Source references:
  - `src/pixel_fix/pipeline.py:31-36`
  - `src/pixel_fix/pipeline.py:135-137`
  - `src/pixel_fix/cli.py:18-20`
  - `src/pixel_fix/gui/app.py:2360-2364`

#### Root cause analysis

The pipeline resolves the effective dithering mode with:

```python
dither_mode = self.config.palette_dither_mode or self.config.dither_mode
```

Because `palette_dither_mode` defaults to the truthy string `"none"`, it always wins over `dither_mode`, even when the caller explicitly sets only the legacy field.

#### Steps to reproduce

1. Set only `dither_mode` to a non-`none` value.
2. Leave `palette_dither_mode` at its default.
3. Execute `run_prepared_labels()`.
4. Observe from the code path that the effective mode remains `"none"`.

#### Impact

- Legacy callers, including the current CLI, cannot rely on `dither_mode`.
- Fixing `run_file()` alone would still leave `--dither` behavior broken unless this precedence bug is also addressed.

#### Suggested fix

- Use an explicit sentinel such as `None` for the newer field, or resolve precedence with a check that treats `"none"` as a legitimate value rather than an override.
- Add active-pipeline tests for effective dither selection.

#### Coverage gap

Current tests cover settings serialization, not active dither-mode resolution in the pipeline.

---

### 6. Successful palette apply stores a stale process snapshot and logs pre-reset adjustment deltas

- Severity: **minor**
- Test name / failure details:
  - No existing automated test currently fails.
  - Static inspection shows the saved snapshot and process-log changes are computed before slider reset, then persisted after reset.
- Source references:
  - `src/pixel_fix/gui/app.py:1649-1652`
  - `src/pixel_fix/gui/app.py:1848-1890`
  - `src/pixel_fix/gui/persist.py:115-165`

#### Root cause analysis

`reduce_palette_current_image()` captures `snapshot` and `changes` before the palette apply succeeds. `_handle_palette_success()` then resets palette adjustments to neutral but still stores the old snapshot in `last_successful_process_snapshot` and appends log entries based on the pre-reset state. That means the saved "last successful process" can disagree with the visible post-apply GUI state.

#### Steps to reproduce

1. Open an image, downsample it, and prepare a palette.
2. Set palette adjustments away from neutral.
3. Click `Apply Palette`.
4. Observe that the sliders reset to neutral.
5. Trigger another process action and inspect the process log or snapshot diff.
6. The reported changes can include stale adjustment/source deltas from the pre-reset state.

#### Suggested fix

- Rebuild the success snapshot after `_reset_palette_adjustments_to_neutral()`.
- Add an end-to-end test for apply-success persistence/logging behavior.

#### Coverage gap

Existing persistence tests cover snapshot formatting and log writes, but not this state transition after a successful palette apply.

---

### 7. `floyd-steinberg` is still advertised by the CLI but unsupported by the active palette-application path

- Severity: **minor**
- Test name / failure details:
  - No existing automated test currently fails.
  - Runtime reproduction confirmed `ValueError: Unsupported dither mode: floyd-steinberg` when the legacy value is allowed through.
- Source references:
  - `src/pixel_fix/cli.py:18-20`
  - `src/pixel_fix/palette/dither.py:63-70`
  - `src/pixel_fix/palette/advanced.py:667-696`
  - `README.md:85-89`

#### Root cause analysis

The repository still contains a legacy dithering helper that supports `floyd-steinberg`, and the CLI still advertises that option, but the active `map_palette_to_labels()` path only accepts `none`, `ordered`, and `blue-noise`.

#### Steps to reproduce

1. Reach `run_prepared_labels()` with a non-empty palette.
2. Force the active path to use `dither_mode="floyd-steinberg"`.
3. Observe `ValueError: Unsupported dither mode: floyd-steinberg`.

#### Suggested fix

- Remove `floyd-steinberg` from exposed interfaces, or add support for it in the active pipeline path.
- Add tests for supported/unsupported dithering modes in the active mapping path.

#### Coverage gap

There is a unit test for the legacy dithering helper, but not for active-pipeline dithering mode compatibility.

## Improvement opportunities

### 1. Add a real CI workflow with test and report publishing

- Severity: **major improvement**
- Evidence:
  - no `.github/workflows/*` files are present
  - `pyproject.toml` defines packaging metadata only
  - the README does not document a test command or coverage/report generation

#### Recommendation

- Add a push/PR workflow that runs pytest, uploads JUnit XML, and publishes coverage artifacts.
- Include a Tk-capable GUI-test job or isolate GUI tests into an explicitly provisioned environment.

### 2. Built-in palette discovery silently skips broken assets

- Severity: **minor improvement**
- Source references:
  - `src/pixel_fix/palette/catalog.py:34-38`
  - `tests/test_palette_catalog.py:14-56`

#### Why it matters

Invalid `.gpl` files or bad metadata can disappear from the built-in palette menu without any CI failure or user-visible warning.

#### Recommendation

- Add repository-backed tests for the real `palettes/` tree.
- Replace the silent `except Exception: continue` path with diagnostics or a strict validation mode.

### 3. Performance reporting is incomplete because `mapping_seconds` is hard-coded to `0.0`

- Severity: **minor improvement**
- Source references:
  - `src/pixel_fix/pipeline.py:171-192`
  - `src/pixel_fix/gui/processing.py:31-47`

#### Why it matters

The code models mapping timing in reports and UI stats, but the value is never measured, which makes future performance reporting misleading.

#### Recommendation

- Measure `map_palette_to_labels()` with `perf_counter()` and propagate the actual duration.

### 4. Process-log and state handling need more resilience and coverage

- Severity: **minor improvement**
- Source references:
  - `src/pixel_fix/gui/persist.py:100-107`
  - `src/pixel_fix/gui/persist.py:140-165`
  - `tests/test_gui_persist.py:130-167`

#### Why it matters

Corrupt settings are silently discarded, process logs grow without rotation, and failure-path logging/state transitions are lightly tested.

#### Recommendation

- Add tests for malformed settings, failure log entries, and repeated append behavior.
- Consider log rotation or structured log output.

### 5. Quantization and dithering paths are likely performance hotspots at larger image sizes

- Severity: **minor improvement**
- Source references:
  - `src/pixel_fix/palette/quantize.py:52-101`
  - `src/pixel_fix/palette/dither.py`
  - `src/pixel_fix/gui/app.py:1545-1549`

#### Why it matters

The K-means and remap paths use Python-level nested loops over pixels and palette entries. That is acceptable for tiny fixtures but risky for larger real-world images.

#### Recommendation

- Add at least one moderate-size benchmark or smoke test.
- Consider vectorizing hot paths with NumPy or constraining expensive GUI operations for large prepared images.

## Recommended next actions

1. Fix the Linux/Tk collection blocker so the full suite can run in CI.
2. Either implement the CLI pipeline path properly or mark the CLI as explicitly non-production until it is real.
3. Add regression tests for:
   - adjustment + sort/edit + apply
   - pipeline `colors` / `quantizer`
   - active dither precedence and supported modes
   - apply-success snapshot/log state
4. Add repository CI workflow(s) with test and artifact reporting.

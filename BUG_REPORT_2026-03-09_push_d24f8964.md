# Bug Report: push validation for `d24f8964e6395aec5548a5c91e31aa4c6b1277a8`

## Scope

- Trigger: push to `main`
- Head commit: `d24f8964e6395aec5548a5c91e31aa4c6b1277a8`
- Merged PR: #12, `Add downsample cleanup filters`
- Files changed by the push:
  - `src/pixel_fix/gui/app.py`
  - `tests/test_gui_builtin_palettes.py`
  - `tests/test_gui_processing.py`

## Environment

- OS: Linux 6.1.147
- Shell: bash
- Python executable: `python3`

## Test execution summary

### Commands run

1. `python3 -m pip install -e . pytest`
2. `python3 -m pytest`
3. `python3 -m pytest tests --ignore=tests/test_gui_builtin_palettes.py --ignore=tests/test_gui_processing.py`

### Results

- Full suite: failed during collection
- Non-GUI subset: passed
  - `50 passed in 0.16s`

## Confirmed bugs

### 1. Full pytest suite fails on Linux runners without `tkinter`

- Severity: **major**
- Type: CI/test portability bug
- Failure location:
  - `tests/test_gui_builtin_palettes.py` collection
  - `tests/test_gui_processing.py` collection
  - `src/pixel_fix/gui/app.py:5`
  - `tests/test_gui_builtin_palettes.py:4`
  - `tests/test_gui_processing.py:5`
- Failure details:

```text
ERROR tests/test_gui_builtin_palettes.py
E   ModuleNotFoundError: No module named 'tkinter'

ERROR tests/test_gui_processing.py
E   ModuleNotFoundError: No module named 'tkinter'
```

- Root cause analysis:
  - GUI tests import `tkinter` and `pixel_fix.gui.app` at module import time.
  - `src/pixel_fix/gui/app.py` also imports `tkinter` at module import time.
  - The skip logic in `tests/test_gui_builtin_palettes.py` only runs after `tk.Tk()` is called, but collection never reaches that point when `tkinter` is missing.
  - Result: the suite errors during collection instead of cleanly skipping optional GUI tests.
- Steps to reproduce:
  1. Use a Linux environment without Tk support installed.
  2. Install project dependencies and pytest.
  3. Run `python3 -m pytest`.
  4. Observe collection failure before any GUI test can skip itself.
- Suggested fixes:
  - Add `pytest.importorskip("tkinter")` at module level in GUI-dependent tests.
  - Mark GUI tests separately so CI can split GUI and non-GUI lanes.
  - Provision Tk explicitly in a GUI CI job, ideally under Xvfb.

### 2. Built-in palette restoration behavior regressed in this push

- Severity: **major**
- Type: product behavior regression
- Evidence:
  - Current code no longer restores persisted palettes during startup.
  - Previous parent revision (`6b380046bb41`) contained startup restore wiring and persisted `active_palette_path` / `active_palette_source`.
  - Current test changed from `test_persisted_builtin_palette_is_restored_on_startup` to `test_persisted_builtin_palette_is_not_restored_on_startup`.
- Relevant locations:
  - `src/pixel_fix/gui/app.py:132-143`
  - `src/pixel_fix/gui/app.py:229-237` in the parent revision behavior
  - `src/pixel_fix/gui/app.py:850-875`
  - `src/pixel_fix/gui/app.py:2232-2247`
  - `tests/test_gui_builtin_palettes.py:97-112`
- Root cause analysis:
  - The constructor no longer calls `_restore_active_palette(persisted)`.
  - `_persist_state()` no longer writes `active_palette_path` or `active_palette_source`.
  - `_restore_active_palette()` still exists, which indicates the restore path was removed from startup flow rather than deleted as obsolete.
  - The merged test now locks in the non-restore behavior for built-in palettes.
- User-visible impact:
  - A selected built-in palette is lost after closing and reopening the app.
  - The same code path also makes restore behavior for external palettes suspect, because persistence data is no longer written at shutdown.
- Steps to reproduce:
  1. Launch the GUI.
  2. Select a built-in palette such as `DawnBringer / DB16`.
  3. Close the app cleanly.
  4. Reopen the app.
  5. Observe that the active palette is no longer restored.
- Suggested fixes:
  - Decide whether palette restore is intended.
  - If yes, restore by a stable identifier for built-ins and persist the active palette metadata again.
  - If no, remove `_restore_active_palette()` and document the intentional behavior change to avoid dead logic and confusing expectations.

### 3. Changing palette reduction settings can leave a stale generated override palette active

- Severity: **major**
- Type: state invalidation bug
- Relevant locations:
  - `src/pixel_fix/gui/app.py:1257-1283`
  - `src/pixel_fix/gui/app.py:1359-1417`
  - `src/pixel_fix/gui/app.py:2028-2077`
  - `tests/test_gui_processing.py:429-448`
  - `tests/test_gui_processing.py:499-540`
- Root cause analysis:
  - `_generate_override_palette_from_settings()` creates an override palette from the current quantizer and target size.
  - `_handle_settings_transition()` treats `palette_reduction_colors` and `quantizer` changes as informational only, then returns early.
  - It does not clear or invalidate a previously generated override palette.
  - `reduce_palette_current_image()` still prefers the active override palette when `_palette_is_override_mode()` is true.
- Likely impact:
  - The UI can show updated reduction settings while Apply still uses an override palette generated under the old settings.
  - This can make palette application results inconsistent with the visible controls and process snapshot messaging.
- Steps to reproduce:
  1. Open and downsample an image.
  2. Generate a reduced palette using `Median Cut` and a small palette size.
  3. Change the reduction settings to `K-Means Clustering` and a different target size.
  4. Apply the palette without regenerating it.
  5. Observe that the previously generated override palette is still eligible for use.
- Suggested fixes:
  - Invalidate generated override palettes when quantizer or reduction-size settings change.
  - Or disable Apply until the user regenerates the override palette under the new settings.

## Improvement opportunities

### 4. Linux wheel-zoom portability is likely incomplete

- Severity: **minor**
- Relevant locations:
  - `src/pixel_fix/gui/app.py:531-540`
  - `tests/test_gui_zoom.py:1-25`
- Observation:
  - The canvas binds `<MouseWheel>` and `<Control-MouseWheel>`, but there are no `<Button-4>` / `<Button-5>` bindings for Linux/X11 wheel events.
  - Current zoom tests cover helper math only, not real Tk event bindings.
- Why this matters:
  - Mouse-wheel zoom can fail on Linux/X11 even when the rest of the GUI works.
- Suggestions:
  - Add Linux/X11 wheel bindings.
  - Add at least one integration test for real canvas wheel handling in a GUI-enabled CI job.

### 5. CI bootstrap is under-specified

- Severity: **minor**
- Relevant locations:
  - `pyproject.toml:13-24`
  - repository root: no `.github/workflows/*`
- Observation:
  - Runtime dependencies exist, but test dependencies and GUI system prerequisites are not described in project metadata.
  - The runner required a manual pytest install before tests could execute.
- Why this matters:
  - External automation cannot reliably infer the correct test bootstrap.
  - Environment-only failures become harder to distinguish from regressions.
- Suggestions:
  - Add a `test` or `dev` extra that includes pytest.
  - Document the supported test commands and OS-level Tk requirement.
  - Add CI lanes for:
    - non-GUI tests
    - GUI tests with Tk installed

### 6. GUI runtime paths still have lighter coverage than GUI logic helpers

- Severity: **minor**
- Relevant locations:
  - `src/pixel_fix/gui/app.py:1342-1423`
  - `src/pixel_fix/gui/app.py:1529-1645`
  - `src/pixel_fix/gui/app.py:2262-2265`
- Observation:
  - Most new tests exercise `PixelFixGui` methods through stubs and `__new__`, which is useful but does not cover the real Tk event loop, thread handoff, or GUI entrypoint behavior.
- Why this matters:
  - Regressions in worker-thread orchestration, `root.after(...)` callbacks, or startup under headless Linux can slip through.
- Suggestions:
  - Add a small GUI smoke test lane under Xvfb.
  - Add targeted integration tests for threaded downsample/apply success and failure handlers.

## What passed

- Non-GUI product logic appears healthy in this environment.
- The following suites passed:
  - `tests/test_cleanup.py`
  - `tests/test_grid_scoring.py`
  - `tests/test_gui_persist.py`
  - `tests/test_gui_state.py`
  - `tests/test_gui_zoom.py`
  - `tests/test_palette_catalog.py`
  - `tests/test_palette_features.py`
  - `tests/test_pipeline.py`
  - `tests/test_pipeline_color_features.py`

## Recommended next actions

1. Fix GUI test collection so Linux CI can complete a full run.
2. Decide whether palette persistence is meant to remain supported; if yes, restore the startup and shutdown wiring.
3. Invalidate generated override palettes when palette reduction settings change.
4. Add explicit CI and test bootstrap documentation so future validation runs are reproducible.

# Bug Report: push validation for `8596bff2`

## Scope

- Repository: `craigsimm/pixel-fix`
- Branch: `main`
- Push head: `8596bff2e643ba36547b82365eb7524307faeb75`
- Triggering merge: PR `#17` ("Added basic outline features")
- Compare URL: <https://github.com/craigsimm/pixel-fix/compare/f2d7e3831862...8596bff2e643>

## Test execution summary

| Command | Result | Notes |
| --- | --- | --- |
| `python3 -m pytest -q` | Failed during collection | Linux runner does not have `tkinter`, so GUI tests never executed |
| `python3 -m pytest -q tests/test_cleanup.py tests/test_grid_scoring.py tests/test_gui_persist.py tests/test_gui_state.py tests/test_gui_zoom.py tests/test_palette_catalog.py tests/test_palette_features.py tests/test_pipeline.py tests/test_pipeline_color_features.py` | Passed | `55 passed in 0.15s` |

### Collection failures

1. `tests/test_gui_builtin_palettes.py`
   - Failure: `ModuleNotFoundError: No module named 'tkinter'`
2. `tests/test_gui_processing.py`
   - Failure: `ModuleNotFoundError: No module named 'tkinter'`

### Quality signal

- The non-GUI suite is healthy.
- The GUI suite is currently unvalidated in this Linux environment, which is especially important for this push because the merged changes are GUI-facing outline features.

## Bugs found

---

### 1) GUI test suite is blocked on Linux because `tkinter` is not provisioned

- Severity: **major**
- Affected files: `tests/test_gui_builtin_palettes.py`, `tests/test_gui_processing.py`, `src/pixel_fix/gui/app.py`
- Test / evidence:
  - `python3 -m pytest -q`
  - Collection stopped before execution with `ModuleNotFoundError: No module named 'tkinter'`
- Failure details:
  - `tests/test_gui_builtin_palettes.py` cannot import `tkinter as tk`
  - `tests/test_gui_processing.py` cannot import `pixel_fix.gui.app`, because `src/pixel_fix/gui/app.py` imports `tkinter` at module import time
- Root cause analysis:
  - The runner image used for this validation does not provide the stdlib Tk bindings.
  - The project has GUI tests that import Tk at import time, but there is no CI provisioning or skip strategy for environments without Tk.
- Steps to reproduce:
  1. Start from a Linux Python 3.12 environment without Tk support.
  2. Run `python3 -m pip install -e . pytest`.
  3. Run `python3 -m pytest -q`.
  4. Observe collection fail before any GUI test runs.
- Impact:
  - This blocks automated validation of the exact area changed in PR #17.
  - A broken GUI feature can be merged while CI still reports only environment-level collection errors.

---

### 2) Source PNG transparency is discarded before outline logic computes the silhouette

- Severity: **major**
- Affected files: `src/pixel_fix/gui/app.py:822-830`, `src/pixel_fix/gui/processing.py:223-232`, `src/pixel_fix/gui/processing.py:235-314`
- Test / evidence:
  - Existing tests do **not** cover this path.
  - Scripted repro:
    ```python
    from PIL import Image
    from pixel_fix.gui.processing import image_to_rgb_grid, downsample_image, add_exterior_outline
    from pixel_fix.pipeline import PipelineConfig

    img = Image.new("RGBA", (3, 3), (255, 255, 255, 0))
    img.putpixel((1, 1), (0, 0, 255, 255))
    grid = image_to_rgb_grid(img)
    result = downsample_image(grid, PipelineConfig(pixel_width=1))
    updated, changed = add_exterior_outline(result, 0x112233)
    print(result.alpha_mask, changed)
    ```
  - Observed output: `alpha_mask` is `None` and `changed == 0`
- Failure details:
  - Transparent padding is converted to RGB and loses alpha before processing.
  - Outline detection then treats transparent source pixels as visible image content based only on their RGB payload.
- Root cause analysis:
  - `_open_image_path()` keeps an RGBA display image, but processing is fed through `image_to_rgb_grid()`, which strips alpha.
  - `downsample_image()` and `reduce_palette_image()` build `ProcessResult` objects without preserving source alpha.
  - `_effective_visible_mask()` therefore has no reliable transparency information for sprites loaded from transparent PNGs.
- Steps to reproduce:
  1. Load a PNG sprite with transparent padding around opaque artwork.
  2. Downsample it.
  3. Use `Add Outline`.
  4. Observe the outline follows the RGB contents of transparent pixels instead of the visible sprite silhouette, or no outline is added at all.
- Impact:
  - Transparent PNGs are a primary input format for pixel-art workflows.
  - Outline and erosion operations can silently target the wrong silhouette.

---

### 3) Transparency and outline edits made before palette application are lost when `Apply Palette` is used later

- Severity: **major**
- Affected files: `src/pixel_fix/gui/app.py:1436-1508`, `src/pixel_fix/gui/app.py:1637-1684`, `src/pixel_fix/gui/processing.py:270-314`
- Test / evidence:
  - Existing tests cover editing an already-present `palette_result`, but do not cover editing a `downsample_result` and then applying a palette.
  - Scripted repro:
    ```python
    from pixel_fix.gui.processing import downsample_image, apply_transparency_fill, reduce_palette_image
    from pixel_fix.pipeline import PipelineConfig
    from pixel_fix.palette.advanced import generate_structured_palette

    grid = [
        [(255, 0, 0), (255, 0, 0), (0, 0, 255), (0, 0, 255)],
        [(255, 0, 0), (255, 0, 0), (0, 0, 255), (0, 0, 255)],
        [(0, 255, 0), (0, 255, 0), (255, 255, 0), (255, 255, 0)],
        [(0, 255, 0), (0, 255, 0), (255, 255, 0), (255, 255, 0)],
    ]
    down = downsample_image(grid, PipelineConfig(pixel_width=2))
    edited, changed = apply_transparency_fill(down, 0, 0)
    palette = generate_structured_palette(
        down.prepared_input.reduced_labels,
        key_colors=[0xFF0000, 0x0000FF],
        generated_shades=2,
    ).palette
    reduced = reduce_palette_image(
        down.prepared_input,
        PipelineConfig(pixel_width=2, key_colors=(0xFF0000, 0x0000FF), generated_shades=2),
        structured_palette=palette,
    )
    print(edited.alpha_mask, reduced.alpha_mask)
    ```
  - Observed output: edited result has `alpha_mask=((False, True), (True, True))`, but the later palette result has `alpha_mask=None`
- Failure details:
  - If the user makes part of the downsampled image transparent, or adds/removes outline before applying a palette, those edits are not carried forward.
  - `Apply Palette` regenerates from cached prepared labels instead of the edited current result.
- Root cause analysis:
  - `reduce_palette_current_image()` uses `self.prepared_input_cache`, which reflects the original downsample output, not later interactive edits.
  - `reduce_palette_image()` returns a fresh `ProcessResult` without propagating the edited `alpha_mask`.
- Steps to reproduce:
  1. Open an image.
  2. Click `Downsample`.
  3. Use `Make Transparent`, `Add Outline`, or `Remove Outline`.
  4. Click `Apply Palette`.
  5. Observe the earlier transparency/silhouette edit is lost.
- Impact:
  - Users can make visible edits that disappear in the next stage.
  - This is data-loss behavior in the normal staged workflow.

---

### 4) Processed-image edit actions stay enabled on stale output, but saving remains disabled after the edit

- Severity: **major**
- Affected files: `src/pixel_fix/gui/app.py:1436-1508`, `src/pixel_fix/gui/app.py:1703-1713`, `src/pixel_fix/gui/app.py:2475-2479`, `src/pixel_fix/gui/app.py:2509-2553`
- Test / evidence:
  - No existing test covers the stale-state interaction.
  - Code path review shows:
    - `_mark_output_stale()` switches to `processed_stale`
    - `_refresh_action_states()` still enables `Make Transparent`, `Add Outline`, and `Remove Outline` whenever any output exists
    - `save_processed_image()` and `save_processed_image_as()` hard-return unless `image_state == "processed_current"`
- Failure details:
  - The UI can allow users to mutate a stale preview, redraw it, and show a success message.
  - The same edited image still cannot be saved because the handlers never promote the state back to `processed_current`.
- Root cause analysis:
  - State gating is inconsistent between editing actions and save actions.
  - Interactive edit handlers update result objects and display images, but do not update `image_state` or `last_successful_process_snapshot`.
- Steps to reproduce:
  1. Produce a processed image.
  2. Change a setting that marks output stale.
  3. Use `Add Outline`, `Remove Outline`, or `Make Transparent`.
  4. Observe the image changes visually.
  5. Try to save; save remains disabled or returns early because the state is still `processed_stale`.
- Impact:
  - The UI presents an edited image that the app still treats as unsaveable.
  - This is likely to confuse users and produce inconsistent document state.

---

### 5) Undo after an image edit can unexpectedly roll back newer settings changes

- Severity: **minor**
- Affected files: `src/pixel_fix/gui/app.py:1719-1784`, `src/pixel_fix/gui/app.py:2438-2466`
- Test / evidence:
  - No current test sequences an image edit, a later settings-only change, and then `Undo`.
- Failure details:
  - `Undo` prioritizes `_undo_palette_application()` before settings history.
  - Some later settings transitions do not clear the pending image undo snapshot.
- Root cause analysis:
  - `_capture_palette_undo_state()` stores the full `PreviewSettings`.
  - `_handle_settings_transition()` intentionally does not clear `_palette_undo_state` for some settings changes.
  - A later Ctrl+Z can therefore restore older settings from the image-edit snapshot instead of undoing only the most recent setting change.
- Steps to reproduce:
  1. Create a processed image.
  2. Use `Add Outline`, `Remove Outline`, or `Make Transparent`.
  3. Change a setting such as auto-detect count or palette reduction settings.
  4. Press `Undo`.
  5. Observe both the image edit and later settings can roll back together.
- Impact:
  - Undo semantics become surprising and non-local.
  - Users may lose a later settings change they did not intend to undo.

---

### 6) Undo restores the pixels after outline edits, but not the palette selection state that made the action available

- Severity: **minor**
- Affected files: `src/pixel_fix/gui/app.py:133-148`, `src/pixel_fix/gui/app.py:950-960`, `src/pixel_fix/gui/app.py:1752-1784`, `src/pixel_fix/gui/app.py:2516-2530`
- Test / evidence:
  - Existing undo tests validate image restoration but do not validate palette selection restoration.
- Failure details:
  - After undoing an outline operation, the selected swatch can be cleared even though the pre-edit UI required exactly one selected colour.
- Root cause analysis:
  - `PaletteUndoState` does not store `_palette_selection_indices` or `_palette_selection_anchor_index`.
  - `_undo_palette_application()` calls `_set_active_palette(...)`, and `_set_active_palette(...)` clears palette selection.
- Steps to reproduce:
  1. Select exactly one palette swatch.
  2. Use `Add Outline`.
  3. Press `Undo`.
  4. Observe the image is restored, but the palette selection is cleared.
- Impact:
  - The restored UI does not match the pre-edit state.
  - Users must manually reselect the swatch to repeat or adjust the action.

## Improvement opportunities

1. **Provision Tk in CI or explicitly skip GUI tests in environments without it**
   - The current collection failure hides real GUI regressions.

2. **Add integration tests that use real RGBA fixtures**
   - Current outline tests build synthetic `ProcessResult` values and do not exercise image loading, alpha preservation, or stage-to-stage propagation.

3. **Add coverage for stage transitions**
   - Missing tests:
     - edit downsample result, then apply palette
     - mark output stale, then use processed-image tools
     - undo after image edit plus later settings change
     - undo should restore palette selection state

4. **Align test fixtures with production semantics**
   - `tests/test_gui_processing.py::_result_from_labels()` currently treats `0x000000` as transparent in `alpha_mask`, which does not match the default behavior of real pipeline outputs where `alpha_mask` is usually `None`.

5. **Clarify or constrain `Remove Outline` behavior**
   - The current implementation is an outside-edge erosion operation. It can erase one-pixel-wide shapes entirely, which may be surprising for a command named `Remove Outline`.

## Suggested priority

1. Fix alpha preservation from source PNGs into processing results.
2. Preserve interactive transparency/outline edits when moving from downsample to palette application.
3. Resolve stale-state editing/save inconsistencies.
4. Restore GUI test execution in CI.
5. Tighten undo and selection restoration behavior.

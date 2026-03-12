# Bug Report: push validation for `802bbcf2a35d27effe0547fb07a526297a618add`

## Validation summary

- Repository: `craigsimm/pixel-fix`
- Trigger: push to `main`
- Head commit: `802bbcf2a35d27effe0547fb07a526297a618add`
- Environment: Ubuntu Linux, Python 3.12.3

### Commands run

```bash
python3 -m pip install -e . pytest
python3 -m pytest -q
sudo apt-get update && sudo apt-get install -y python3-tk
python3 -m pytest -q
```

### Test results

1. Initial run on a fresh Linux environment failed during collection:
   - `tests/test_gui_builtin_palettes.py`
   - `tests/test_gui_processing.py`
   - Error: `ModuleNotFoundError: No module named 'tkinter'`
2. After installing `python3-tk`, the suite passed:
   - `114 passed, 5 skipped, 1 warning in 0.24s`

## Bugs found

### 1. Major: palette merge and ramp edits double-apply active adjustment sliders

- Severity: **major**
- Affected code:
  - `src/pixel_fix/gui/app.py:672-679`
  - `src/pixel_fix/gui/app.py:1099-1107`
  - `src/pixel_fix/gui/app.py:1180-1228`
  - `src/pixel_fix/gui/app.py:2226-2235`

#### Failure details

The new merge/ramp workflows materialize edits from the **already adjusted display palette**, then save that result as the new active palette. Because the adjustment sliders remain active, `_get_display_palette()` adjusts the newly stored palette a second time on the next render.

Observed reproduction output:

```text
MERGE before_display= ['4A7EB2', 'A1C3E6', 'CC8844']
MERGE after_active = ['75A0CC', 'CC8844']
MERGE after_display= ['8DB9E6', 'E7A15E']
MERGE double_apply= True

RAMP before_display= ['4A7EB2', 'E7A15E']
RAMP after_active = ['4A7EB2', 'E7A15E', '475E85', '3E7EBC', '62A4AC', 'C2807D', 'F09D49', 'F7C798']
RAMP after_display= ['6296CC', 'FFBB77', '5D759E', '5697D6', '7BBDC5', 'DD9895', 'FFB764', 'FFE1B1']
RAMP double_apply= True
```

#### Root cause analysis

- `_merge_selected_palette_colors()` and `_ramp_selected_palette_colors()` both start from `_editable_palette_labels()`.
- `_editable_palette_labels()` pulls from `_get_display_palette()`, which returns the palette **after** brightness/contrast/hue/saturation adjustments.
- `_apply_palette_edit()` stores the edited labels as a new `active_palette`.
- On the next redraw, `_get_display_palette()` sees a non-neutral adjustment state and adjusts the new `active_palette` again.

#### Steps to reproduce

1. Load or generate a palette.
2. Move a palette adjustment slider away from neutral, for example `palette_brightness = 20`.
3. Select two or more swatches and click **Merge**, or select swatches and click **Ramp**.
4. Compare the stored edited palette with the next displayed palette render.
5. The visible colours shift again even though the edit was already derived from the adjusted display.

#### Suggested fix

- Perform merge/ramp edits from the unadjusted base palette, not the adjusted display palette; or
- Materialize the edit and immediately reset/rebase the adjustment state so the new palette is not adjusted twice.

---

### 2. Major: Reset Sort Order restores the wrong palette after sorting an edited palette

- Severity: **major**
- Affected code:
  - `src/pixel_fix/gui/app.py:1015-1027`
  - `src/pixel_fix/gui/app.py:1038-1049`
  - `src/pixel_fix/gui/app.py:1051-1073`

#### Failure details

When the current palette source is `"Edited Palette"`, `sort_current_palette()` does not capture that edited palette as the reset source. `reset_palette_sort_order()` can therefore restore an older generated/source palette instead of the palette the user just edited.

Observed reproduction output:

```text
SORT reset_source= Generated
SORT reset_labels= ['00CDB8', '00FF00', 'D7FF62', '4F4F4F', '777777', 'A1A1A1', 'A81C5F', 'FF0000', 'FF8551']
SORT restored_active= ['00CDB8', '00FF00', 'D7FF62', '4F4F4F', '777777', 'A1A1A1', 'A81C5F', 'FF0000', 'FF8551']
SORT expected_edited= ['112233', '445566', '778899']
SORT wrong_reset= True
```

#### Root cause analysis

`_palette_sort_source()` deliberately excludes active palettes whose source starts with `"Edited Palette"`. In that case it falls back to `advanced_palette_preview` or the current processed result, which may be stale relative to the palette the user just edited.

#### Steps to reproduce

1. Create or load a palette.
2. Edit it so the active source becomes `"Edited Palette"`.
3. Sort the palette.
4. Click **Reset Sort Order**.
5. The reset action restores the older generated/source palette instead of the edited one that was just sorted.

#### Suggested fix

- Treat `"Edited Palette"` as a valid reset source in `_palette_sort_source()`.
- Add a regression test that sorts an edited palette and verifies reset returns the edited pre-sort order.

---

### 3. Major: fresh Linux test runs fail until `python3-tk` is installed

- Severity: **major**
- Failing tests:
  - `tests/test_gui_builtin_palettes.py`
  - `tests/test_gui_processing.py`
- Failure detail:

```text
ImportError while importing test module '/workspace/tests/test_gui_builtin_palettes.py'
E   ModuleNotFoundError: No module named 'tkinter'

ImportError while importing test module '/workspace/tests/test_gui_processing.py'
E   ModuleNotFoundError: No module named 'tkinter'
```

#### Root cause analysis

The GUI code and GUI-facing tests import `tkinter` at module import time, but the project bootstrap does not provision the system package required on Ubuntu (`python3-tk`). The README also does not document the dependency.

#### Steps to reproduce

1. Start from a fresh Ubuntu/Python environment without `python3-tk`.
2. Run:

   ```bash
   python3 -m pip install -e . pytest
   python3 -m pytest -q
   ```

3. Test collection fails before the suite can run.

#### Suggested fix

- Install `python3-tk` in CI and any documented local setup path.
- Optionally gate or skip GUI tests with a clear message when Tk is unavailable.

---

### 4. Minor: Pillow deprecation warning from `Image.getdata()`

- Severity: **minor**
- Warning surfaced by:
  - `tests/test_gui_processing.py::test_open_image_path_clears_palette_and_transparency_state`
- Affected code:
  - `src/pixel_fix/gui/processing.py:346-347`
  - `src/pixel_fix/gui/processing.py:358-359`

#### Failure details

```text
DeprecationWarning: Image.Image.getdata is deprecated and will be removed in Pillow 14 (2027-10-15). Use get_flattened_data instead.
```

#### Root cause analysis

`load_png_grid()` and `image_to_rgb_grid()` still call `list(rgb.getdata())`, which now emits a deprecation warning on current Pillow releases.

#### Steps to reproduce

1. Install current Pillow.
2. Run:

   ```bash
   python3 -m pytest -q
   ```

3. Inspect the warning summary.

#### Suggested fix

- Replace `getdata()` usage with the Pillow-supported flattened pixel API before Pillow 14 removes it.

## Improvement opportunities

### Missing test coverage

- `tests/test_gui_processing.py` covers merge, ramp, and sort/reset flows only in neutral/simple states.
- It does **not** currently cover:
  - merge/ramp while palette adjustments are active
  - sort/reset after the palette source becomes `"Edited Palette"`
- Adding those tests would have caught the first two regressions.

### CI/bootstrap gap

- The repo currently requires a non-Python system package for GUI imports, but the setup path does not declare it.
- This makes the suite appear broken on clean Linux runners even though the application code is otherwise passing.

### Performance watch item

- The new pixel-perfect outline cleanup in `src/pixel_fix/gui/processing.py` repeatedly scans the full mask until convergence.
- I did not measure a concrete regression during this validation, but larger sprites are worth profiling because the algorithm performs whole-grid passes in both directions per iteration.

## Recommended next actions

1. Fix the active-adjustment double-apply path for merge and ramp edits.
2. Fix sort reset so `"Edited Palette"` snapshots restore the correct pre-sort order.
3. Add `python3-tk` to CI/bootstrap docs or skip GUI tests cleanly when Tk is missing.
4. Replace deprecated Pillow `getdata()` usage.
5. Add regression tests for the two palette-state bugs.

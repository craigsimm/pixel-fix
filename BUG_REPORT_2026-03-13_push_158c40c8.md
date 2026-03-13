# Bug Report: push validation for `158c40c8`

## Scope

- Repository: `craigsimm/pixel-fix`
- Trigger: push to `main`
- Head commit: `158c40c8421b481c8d3bedf790a78dee869a224a`
- Compare: https://github.com/craigsimm/pixel-fix/compare/e698dc7df024...158c40c8421b
- Environment: Linux 6.12, Python 3.12.3

## Validation run

Commands used:

```bash
python3 -m pip install -e . pytest Pillow
apt-get install -y python3-tk
python3 -m pytest -q -rs
git diff --check
```

Result summary:

- `6 failed`
- `111 passed`
- `14 skipped`
- `1 warning`

`git diff --check` reported no whitespace or conflict-marker issues.

## Confirmed bugs

### 1. Default `Add Outline` path crashes with `NameError`

- Severity: **major**
- Affected area: `src/pixel_fix/gui/processing.py`
- Root cause:
  - `add_exterior_outline()` still writes `next_grid[y][x] = outline_rgb` on the non-adaptive branch.
  - The `outline_rgb` local was removed during the adaptive-outline refactor, but the non-adaptive path still references it.
  - Evidence from history: commit `9076fa44c3135866c1fcff8a79adc1aa33fd9193` deleted the old `outline_rgb` assignment while restructuring the function.
- Failure location:
  - `src/pixel_fix/gui/processing.py:118`

#### Failing tests that confirm this bug

| Test | Failure details |
| --- | --- |
| `tests/test_gui_processing.py::test_add_exterior_outline_defaults_to_pixel_perfect_diamond` | `NameError: name 'outline_rgb' is not defined` |
| `tests/test_gui_processing.py::test_add_exterior_outline_square_mode_keeps_full_ring` | `NameError: name 'outline_rgb' is not defined` |
| `tests/test_gui_processing.py::test_add_exterior_outline_pixel_perfect_ignores_internal_holes` | `NameError: name 'outline_rgb' is not defined` |
| `tests/test_gui_processing.py::test_add_exterior_outline_pixel_perfect_stair_step_has_no_full_2x2_blocks` | `NameError: name 'outline_rgb' is not defined` |
| `tests/test_gui_processing.py::test_add_outline_from_selection_updates_output_and_undo_restores` | GUI path fails after `_add_outline_from_selection()` reaches `add_exterior_outline()` |
| `tests/test_gui_processing.py::test_add_outline_from_selection_can_use_square_mode` | GUI path fails after `_add_outline_from_selection()` reaches `add_exterior_outline()` |

#### User impact

- The standard outline workflow is broken when adaptive mode is off.
- The failure is not limited to the low-level helper; the GUI action also crashes when a user selects a palette colour and clicks `Add Outline`.
- Pixel-perfect and square-corner variants are both affected.

#### Steps to reproduce

##### Direct API

1. Run:
   ```bash
   python3 -m pytest -q tests/test_gui_processing.py -k "add_exterior_outline or add_outline_from_selection"
   ```
2. Observe `NameError: name 'outline_rgb' is not defined` from `src/pixel_fix/gui/processing.py:118`.

##### GUI flow

1. Launch the app and process any image until a processed result exists.
2. Select exactly one palette swatch.
3. Leave adaptive outline mode disabled.
4. Click `Add Outline`.
5. Observe that the action fails when `add_exterior_outline()` hits the undefined local.

## Improvement opportunities and additional issues

### 2. README describes similarity-threshold behavior that the code does not implement

- Severity: **major**
- Type: product/documentation mismatch
- Evidence:
  - `README.md:189-190` says similarity selection uses `Selection Threshold` as a strictness control.
  - `src/pixel_fix/palette/sort.py:121-132` uses `threshold_percent` only to compute how many colours to select (`target_count`), not how similar they must be.
  - `tests/test_gui_processing.py:34-38` and `tests/test_palette_features.py:37-41` skip similarity-selection tests because no similarity mode exists in `PALETTE_SELECT_MODES`.
- Why it matters:
  - The README advertises a user-facing feature and semantics that are not available in this build.
  - This is likely to confuse users and can lead to incorrect support expectations.
- Suggested follow-up:
  - Either implement an actual similarity-selection mode plus threshold semantics, or remove/soften the README claims until that feature ships.

#### Steps to reproduce

1. Read the similarity-selection section in `README.md`.
2. Inspect `src/pixel_fix/palette/sort.py` and note that `PALETTE_SELECT_MODES` contains only lightness, saturation, chroma, temperature, and hue buckets.
3. Run:
   ```bash
   python3 -m pytest -q -rs
   ```
4. Observe skipped tests reporting `Similarity palette selection mode is not available in this build.`

### 3. Pillow deprecation warning remains in image loading helpers

- Severity: **minor**
- Type: code quality / forward-compatibility
- Evidence:
  - Warning emitted during test run:
    - `src/pixel_fix/gui/processing.py:447`
  - Affected call sites:
    - `src/pixel_fix/gui/processing.py:435`
    - `src/pixel_fix/gui/processing.py:447`
- Warning text:
  - `Image.Image.getdata is deprecated and will be removed in Pillow 14 (2027-10-15). Use get_flattened_data instead.`
- Why it matters:
  - This does not currently fail tests, but it will turn into a runtime compatibility problem on newer Pillow releases.
- Suggested follow-up:
  - Replace `list(rgb.getdata())` with the supported Pillow API and add a small regression test if needed.

#### Steps to reproduce

1. Run:
   ```bash
   python3 -m pytest -q -rs
   ```
2. Observe the warning in the pytest summary.

### 4. Built-in palette GUI tests still skip on headless display availability

- Severity: **minor**
- Type: CI coverage gap
- Evidence:
  - `python3 -m pytest -q -rs` reports:
    - `SKIPPED [5] tests/test_gui_builtin_palettes.py:49: Tk is not available in this environment: couldn't connect to display ":1"`
- Why it matters:
  - CI is not fully validating built-in palette GUI flows on this Linux runner.
  - A regression in those flows could land without failing the suite.
- Suggested follow-up:
  - Provide a reliable virtual display in CI or split more GUI logic into display-independent units.

### 5. Brush-processing tests self-skip because the APIs are absent

- Severity: **minor**
- Type: missing functionality or dead-test ambiguity
- Evidence:
  - `python3 -m pytest -q -rs` reports:
    - `SKIPPED [3] tests/test_gui_processing.py:450: Brush-processing API is not available in this build: brush_footprint, apply_pencil_operation, apply_eraser_operation`
    - `SKIPPED [2] tests/test_gui_processing.py:522: GUI brush interaction API is not available in this build`
- Why it matters:
  - The current suite contains placeholder expectations around missing APIs, which reduces confidence about whether brush support is intentionally deferred or partially removed.
- Suggested follow-up:
  - Decide whether brush support is in scope; then either implement the API surface or remove/replace the placeholder tests with explicit non-support assertions.

## Performance notes

- No acute runtime bottleneck surfaced in this validation run.
- After dependencies were installed, the full pytest suite completed in under one second of test execution time (`0.48s` reported by pytest).

## Recommended next actions

1. Restore the non-adaptive `outline_rgb` assignment in `add_exterior_outline()` and rerun the six failing outline tests.
2. Reconcile the README with the actual selection feature set, or implement the missing similarity-selection behavior.
3. Update the Pillow image-data access calls before Pillow 14 removes the deprecated API.
4. Improve CI coverage for Tk/display-dependent flows and decide how brush-placeholder tests should be handled.

## Operational note

- I could create a report branch/PR, but I do not have a writable check-run/status tool in this environment, so I could not directly update a CI check run status with a bug-report link from here.

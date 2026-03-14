# Bug Report: push validation for `13c3c9b78156f9ad7b4f31990562988f905f610d`

## Validation summary

- Repository: `craigsimm/pixel-fix`
- Trigger: push to `main`
- Validated commit: `13c3c9b78156f9ad7b4f31990562988f905f610d`
- Environment: Ubuntu Linux, Python 3.12.3

## Commands run

1. `python3 -m pip install -e . pytest`
2. `PYTHONPATH=src python3 -m pytest -q -rs`
3. `sudo apt-get update && sudo apt-get install -y python3-tk`
4. `PYTHONPATH=src python3 -m pytest -q -rs`

## Final test result

- After installing the missing GUI dependency: `179 passed, 8 skipped, 14 warnings in 0.34s`
- Initial unprepared run failed during collection with 2 errors before any tests executed

## Bugs found

### 1. Linux test collection fails when `tkinter` is unavailable

- **Severity:** major
- **Affected tests / failure details:**
  - `tests/test_gui_builtin_palettes.py` failed during import with `ModuleNotFoundError: No module named 'tkinter'`
  - `tests/test_gui_processing.py` failed during import because `src/pixel_fix/gui/app.py` imports `tkinter` at module load time
- **Observed output:**

  ```text
  ERROR collecting tests/test_gui_builtin_palettes.py
  E   ModuleNotFoundError: No module named 'tkinter'

  ERROR collecting tests/test_gui_processing.py
  E   ModuleNotFoundError: No module named 'tkinter'
  ```

- **Root cause analysis:**
  - The suite assumes the system package behind `tkinter` is present.
  - `tests/test_gui_builtin_palettes.py:4` imports `tkinter as tk` directly.
  - `tests/test_gui_processing.py:7` imports `pixel_fix.gui.app`, and `src/pixel_fix/gui/app.py:5` imports `tkinter as tk` at module import time.
  - Because the dependency is required before tests can even decide whether to skip, the entire suite aborts during collection on minimal Linux runners.
- **Steps to reproduce:**
  1. Start from a Linux environment without `python3-tk` installed.
  2. Install Python dependencies only: `python3 -m pip install -e . pytest`
  3. Run `PYTHONPATH=src python3 -m pytest -q -rs`
  4. Observe collection aborting with the two `tkinter` import errors above.
- **Suggested fixes:**
  - Add `python3-tk` to CI machine setup for Linux jobs that run GUI-related tests.
  - Or make GUI tests resilient to missing Tk by guarding imports and skipping before module-level Tk imports execute.
  - Or split GUI and non-GUI test jobs so the headless core suite can still run when Tk is missing.

### 2. Pillow deprecation warnings indicate future runtime breakage

- **Severity:** minor
- **Affected tests / failure details:**
  - `tests/test_cli.py` emitted 10 warnings referencing `src/pixel_fix/gui/processing.py:703`
  - `tests/test_gui_processing.py` emitted 1 warning referencing `src/pixel_fix/gui/processing.py:703`
  - `tests/test_pipeline.py::test_run_file_writes_real_png_output` emitted 1 warning referencing `src/pixel_fix/pipeline.py:232`
  - `tests/test_cli.py::test_process_job_matches_direct_headless_pipeline` emitted 2 warnings from `tests/test_cli.py:190`
- **Observed warning:**

  ```text
  DeprecationWarning: Image.Image.getdata is deprecated and will be removed in Pillow 14 (2027-10-15). Use get_flattened_data instead.
  ```

- **Root cause analysis:**
  - The runtime still uses `Image.getdata()` in image conversion paths:
    - `src/pixel_fix/gui/processing.py:691`
    - `src/pixel_fix/gui/processing.py:703`
    - `src/pixel_fix/pipeline.py:232`
  - Tests also use the deprecated API directly in `tests/test_cli.py:190`.
  - Pillow 14 will remove this API, so the warning is an early indicator of a future hard failure if not addressed.
- **Steps to reproduce:**
  1. Install dependencies with Pillow 12 or newer.
  2. Run `PYTHONPATH=src python3 -m pytest -q -rs`
  3. Review the warning summary at the end of the run.
- **Suggested fixes:**
  - Replace `Image.getdata()` with `get_flattened_data()` or another supported access path in both runtime and tests.
  - Add a warning-cleanliness check in CI if deprecation regressions should fail fast.

## Improvement opportunities

### A. Built-in palette GUI coverage is skipped on headless validation

- **Evidence:** `8 skipped` from `tests/test_gui_builtin_palettes.py:53`
- **Current skip reason:** `Tk is not available in this environment: couldn't connect to display ":1"`
- **Impact:** built-in palette menu wiring and related UI integration do not execute on the default headless validation path, so regressions in that area can merge without CI feedback.
- **Recommendation:** run GUI tests under `xvfb-run` or provide a working display fixture in CI; otherwise move more menu/state logic into display-independent units and cover those directly.

### B. Image conversion paths allocate full Python lists in hot paths

- **Evidence:**
  - `src/pixel_fix/gui/processing.py:691`
  - `src/pixel_fix/gui/processing.py:703`
  - `src/pixel_fix/pipeline.py:232`
- **Impact:** each path converts the whole image into a Python list before reshaping, which increases memory pressure on larger images and overlaps with the deprecation issue above.
- **Recommendation:** switch to supported flattened image access and evaluate whether reshaping can avoid intermediate list materialization for large images.

### C. Core validation depends on external OS packages not declared in Python packaging

- **Evidence:** the suite required `python3-tk`, which is not expressible through `pyproject.toml` and is not documented by the automated test command itself.
- **Impact:** fresh Linux runners can appear broken even though project code is healthy, producing noisy red builds and slower diagnosis.
- **Recommendation:** document Linux GUI-test prerequisites in the repository and install them explicitly in CI/bootstrap scripts.

## Suggested next actions

1. Update CI/bootstrap steps to install `python3-tk` before running the full suite, or split GUI tests into a separate job with the correct system dependencies.
2. Replace deprecated Pillow `getdata()` usage in runtime and tests before Pillow 14 removes it.
3. Enable the skipped GUI palette tests in a headless display environment so built-in palette workflows are continuously validated.

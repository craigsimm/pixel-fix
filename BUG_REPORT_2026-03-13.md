# Bug Report - 2026-03-13 Push Analysis

## Overview

- Trigger: push to `main`
- Compared range: `802bbcf2a35d...e698dc7df024`
- Head commit: `e698dc7df02495ba794a4b850f6a0a6d25f87315`
- Files changed in push head commit: `tests/test_gui_processing.py`

## Environment

- OS: Linux 6.12.58+
- Python: `Python 3.12.3`
- Test setup command:
  - `python3 -m pip install -e . pytest`

## Commands Run

### Full suite

```bash
python3 -m pytest -q
```

### Non-GUI subset used to isolate the failure

```bash
python3 -m pytest -q \
  tests/test_cleanup.py \
  tests/test_grid_scoring.py \
  tests/test_gui_persist.py \
  tests/test_gui_state.py \
  tests/test_gui_zoom.py \
  tests/test_palette_catalog.py \
  tests/test_palette_features.py \
  tests/test_pipeline.py \
  tests/test_pipeline_color_features.py
```

## Test Results Summary

- Full suite: failed during collection with 2 import errors
- Non-GUI subset: 58 passed

This indicates the current regression is concentrated in GUI test collection and environment handling, not in the non-GUI image-processing or palette logic.

## Bugs Found

### 1. Full test suite aborts during collection when Tkinter is unavailable

- Severity: major
- Affected tests:
  - `tests/test_gui_builtin_palettes.py`
  - `tests/test_gui_processing.py`
- Failure type: import-time collection error

#### Failure details

`python3 -m pytest -q` fails before executing tests:

```text
ERROR collecting tests/test_gui_builtin_palettes.py
ModuleNotFoundError: No module named 'tkinter'

ERROR collecting tests/test_gui_processing.py
ModuleNotFoundError: No module named 'tkinter'
```

#### Root cause analysis

The GUI tests are written to skip when Tk is unavailable, but the skip logic is reached too late.

- `tests/test_gui_builtin_palettes.py:4` imports `tkinter` at module scope.
- `tests/test_gui_processing.py:7-8` imports `pixel_fix.gui.app` and `PixelFixGui` at module scope.
- `src/pixel_fix/gui/app.py:5` imports `tkinter` at module scope.

Because these imports happen during pytest collection, environments without the system Tk package never reach the later `pytest.skip(...)` guards inside helper functions such as `_build_gui(...)` or `_require_brush_*`.

#### Steps to reproduce

1. Use a Linux Python environment without the Tk system package installed.
2. Install the project and pytest:
   ```bash
   python3 -m pip install -e . pytest
   ```
3. Run:
   ```bash
   python3 -m pytest -q
   ```
4. Observe collection failing with `ModuleNotFoundError: No module named 'tkinter'`.

#### Impact

- Blocks the entire test suite in headless or minimal Linux CI environments.
- Prevents unrelated tests from running, which hides true product regressions behind an environment-sensitive collection failure.
- Makes the newly added brush tests in `tests/test_gui_processing.py` effectively unusable in environments where Tk is absent.

#### Recommended fixes

1. Add collection-safe guards in GUI tests:
   - use `pytest.importorskip("tkinter")`, or
   - move Tk-dependent imports inside helpers/tests after availability checks.
2. Separate pure brush-processing helpers from the Tk app module so they can be tested without importing `pixel_fix.gui.app`.
3. Ensure CI runners that are expected to execute GUI tests install the Tk system dependency.

## Improvement Opportunities

### 1. Test architecture: brush logic is coupled to the Tk application module

- Category: code quality / best practice
- Severity: major

The new brush tests in `tests/test_gui_processing.py` are validating logic that is largely non-visual, but they import `pixel_fix.gui.app`, which hard-depends on Tk. This prevents isolated testing of brush behavior and makes logic tests fail for environment reasons rather than behavioral reasons.

Suggestion:

- Move brush footprint and stroke operations into a GUI-independent module.
- Keep only event wiring and canvas interactions in `PixelFixGui`.
- Test the pure logic module directly.

### 2. Packaging and environment expectations are not explicit for GUI execution

- Category: best practice / developer experience
- Severity: minor

`pyproject.toml:13` lists only `Pillow` and `numpy`. That is correct for pip-installable dependencies, but the project does not declare or document that Tk must exist as a system dependency for GUI import and GUI-test execution on Linux.

Suggestion:

- Document the Linux Tk requirement in `README.md`.
- Optionally add a startup check with a clearer error message for missing Tk.

### 3. Missing CI coverage for minimal Linux environments

- Category: missing test coverage / CI quality
- Severity: major

No in-repository GitHub Actions workflow was present under `.github/workflows`, and this regression reached `main` despite being reproducible in a plain Linux environment without Tk. That suggests either missing CI coverage for this scenario or external CI that does not exercise it.

Suggestion:

- Add at least one CI job that runs `python3 -m pytest -q` in the same environment class used by automation.
- Either install Tk in that job or explicitly deselect GUI tests there and run them in a separate GUI-capable job.

### 4. Optional-dependency failure mode is not directly tested

- Category: missing test coverage
- Severity: minor

There is no evidence of a test asserting that GUI tests cleanly skip, rather than crash, when Tk is unavailable.

Suggestion:

- Add a small collection-safety test strategy or CI lane that confirms GUI tests are skipped cleanly when Tk is absent.

## Recommended Priority Order

1. Fix collection-time Tk handling in GUI tests.
2. Decide whether CI should install Tk or split GUI and non-GUI test jobs.
3. Refactor brush logic into a GUI-independent module.
4. Document Linux Tk requirements and add coverage for the no-Tk scenario.

## Current Status

- Full suite status: failing
- Confirmed non-GUI functional status: passing for the 58-test non-GUI subset
- CI/check-run update status: not updated from this automation run because no check-run update tool or writable GitHub checks integration was available in this environment

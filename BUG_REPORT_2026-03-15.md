# Automated Test and Bug Report

Date: 2026-03-15
Repository: craigsimm/pixel-fix
Analyzed push: 8a9feae907ac85ef21166ac05ddccd0ed44b6cab
Merged PR reference: #39 - Implement palette browser popover

## Executive Summary

- Full suite status: failed during collection
- Confirmed passing subset: 96 tests passed
- Confirmed collection failures: 2 test modules
- Confirmed warnings: 15 Pillow deprecation warnings

The current codebase does not show broad functional regressions in the non-GUI paths. The primary problem is that the full test suite cannot run in a minimal Linux environment because `tkinter` is imported at module load time before the GUI tests can skip themselves. A secondary issue is use of Pillow's deprecated `Image.getdata()` API in production code, which is already warning and will become a hard break in Pillow 14.

## Environment

- OS: linux 6.12.58+
- Python: 3.12.3
- Test runner: pytest 9.0.2
- Installed for this run: editable package plus pytest

## Commands Run

### 1) Full suite

```bash
python3 -m pytest
```

Result: failed during test collection

### 2) Non-Tk subset

```bash
python3 -m pytest tests/test_cli.py tests/test_cleanup.py tests/test_grid_scoring.py tests/test_palette_catalog.py tests/test_palette_features.py tests/test_pipeline.py tests/test_pipeline_color_features.py tests/test_gui_persist.py tests/test_gui_state.py tests/test_gui_zoom.py
```

Result: `96 passed, 15 warnings in 0.43s`

## Bugs Found

### 1) Full test suite fails to collect on systems without Tk installed

- Severity: major
- Affected tests:
  - `tests/test_gui_builtin_palettes.py` (module collection failure)
  - `tests/test_gui_processing.py` (module collection failure)
- Failure details:

```text
ModuleNotFoundError: No module named 'tkinter'
```

Observed stack roots:

- `tests/test_gui_builtin_palettes.py:4` imports `tkinter as tk`
- `tests/test_gui_processing.py:7` imports `pixel_fix.gui.app as app_module`
- `src/pixel_fix/gui/app.py:5` imports `tkinter as tk`

#### Root cause analysis

The GUI-related tests are intended to skip when Tk is unavailable, but the skip logic is too late for one of the modules and incomplete for the other:

1. `tests/test_gui_builtin_palettes.py` imports `tkinter` at module scope before reaching the `try/except tk.TclError` logic inside `_build_gui`.
2. `tests/test_gui_processing.py` imports `pixel_fix.gui.app` at module scope, which itself imports `tkinter` immediately.
3. In a Linux environment without the Tk runtime/package, test collection aborts before pytest can execute any skip logic.

This means the suite is not portable to common CI/container images unless they explicitly install Tk.

#### Steps to reproduce

1. Use a Linux environment with Python installed but without the `tkinter` package/runtime.
2. Install project dependencies and pytest.
3. Run:

```bash
python3 -m pytest
```

4. Observe collection fail with `ModuleNotFoundError: No module named 'tkinter'`.

#### Suggested fixes

- Move GUI-only imports behind conditional guards or helper functions in tests.
- Use `pytest.importorskip("tkinter")` in GUI test modules before importing Tk-dependent app modules.
- Decide whether Linux CI should:
  - install Tk explicitly, or
  - treat GUI tests as optional and skip them when Tk is unavailable.
- If the GUI is a supported product path in CI, add a dedicated job with the required Tk packages installed.

### 2) Production code uses a Pillow API already marked deprecated

- Severity: minor
- Surfaced by:
  - `tests/test_cli.py`
  - `tests/test_pipeline.py::test_run_file_writes_real_png_output`
- Warning details:

```text
DeprecationWarning: Image.Image.getdata is deprecated and will be removed in Pillow 14 (2027-10-15). Use get_flattened_data instead.
```

Relevant production locations:

- `src/pixel_fix/gui/processing.py:1011`
- `src/pixel_fix/gui/processing.py:1023`
- `src/pixel_fix/pipeline.py:232`

#### Root cause analysis

Several image-loading paths flatten pixel data with `list(rgb.getdata())`. Pillow 12 emits deprecation warnings for this API and documents removal in Pillow 14. The code still works today, but it has a dated dependency on an API with a published removal timeline.

#### Steps to reproduce

1. Install Pillow 12.x or newer.
2. Run:

```bash
python3 -m pytest tests/test_cli.py tests/test_pipeline.py
```

3. Observe deprecation warnings originating from the locations listed above.

#### Suggested fixes

- Replace deprecated `getdata()` calls with the Pillow-supported replacement API.
- Add a CI mode that treats `DeprecationWarning` as an error for first-party code.

## Improvement Opportunities

### A) No repository-local GitHub Actions workflow or visible check runs

- Type: process / CI gap
- Impact: pushes currently have no repository-local automated status signal or check-run link for test outcomes
- Evidence:
  - no files found under `.github/workflows/*`
  - `gh run list -L 5` returned no workflow runs

#### Recommendation

- Add at least one GitHub Actions workflow that:
  - installs test dependencies
  - installs Tk for GUI coverage or explicitly splits GUI tests into a dedicated job
  - runs pytest
  - uploads artifacts or publishes a summary
  - fails on test errors and optionally on deprecations

### B) Missing coverage for "Tk unavailable" behavior

- Type: missing test coverage
- Impact: the current suite does not validate that GUI tests degrade cleanly on headless/minimal environments

#### Recommendation

- Add an environment-compatibility test strategy that verifies either:
  - Tk-dependent tests are skipped cleanly when Tk is absent, or
  - the supported CI image always includes Tk and asserts that assumption explicitly

### C) Potential memory overhead in image flattening paths

- Type: performance risk
- Impact: large images are converted into full Python lists in multiple paths, which can create avoidable memory pressure
- Evidence:
  - `src/pixel_fix/gui/processing.py:1011`
  - `src/pixel_fix/gui/processing.py:1023`
  - `src/pixel_fix/pipeline.py:232`

#### Recommendation

- Review whether all call sites need eager `list(...)` materialization.
- Benchmark large-image paths and consider more streaming-friendly or array-native handling where practical.

## Recommended Priority Order

1. Fix or explicitly gate Tk-dependent test collection failures.
2. Add CI workflow coverage so pushes produce a reliable status signal.
3. Replace deprecated Pillow APIs before the Pillow 14 removal window.
4. Review image-loading memory behavior on large inputs.

## Current Overall Assessment

- Non-GUI application and CLI logic: appears healthy in this run
- GUI test portability: broken in minimal Linux environments
- Code quality trend: acceptable, but with deprecations that should be cleaned up soon
- CI maturity: incomplete for automated push validation

## CI Status Update Note

This automation could collect results and produce this report, but it could not directly update a GitHub check run from within the available toolset. The repository also does not currently expose a local GitHub Actions workflow that would publish a native status/check link automatically.

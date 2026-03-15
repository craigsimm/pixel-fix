# Automated Test and Bug Report - 2026-03-15

## Trigger Context

- Repository: `craigsimm/pixel-fix`
- Trigger: push to `main`
- Head commit: `637d6d045cda285aaabe938544c3650dfb44e4e2`
- Commit title: `Merge pull request #37 from craigsimm/bug-fixes-14-03-2026`

## Test Execution Summary

### Commands run

1. `python3 -m pip install -e . pytest`
2. `python3 -m pytest`
3. `sudo apt-get install -y python3-tk`
4. `python3 -m pytest`
5. `python3 -m pytest -rs`

### Final suite result

- `214 passed`
- `8 skipped`
- `0 failed`
- `16 warnings`

### Important note

The repository code passed once the runner was configured with `python3-tk`. The primary issues found were CI/environment readiness and forward-compatibility warnings rather than a confirmed functional regression in the newly merged code.

## Findings

### 1. Missing Tk dependency breaks test collection on a clean runner

- Severity: **major**
- Category: CI / environment
- Affected tests:
  - `tests/test_gui_builtin_palettes.py`
  - `tests/test_gui_processing.py`
- Failure detail:
  - `ModuleNotFoundError: No module named 'tkinter'`
  - The first `python3 -m pytest` run stopped during collection with `2 errors`.
- Root cause analysis:
  - GUI tests import `tkinter` directly or import modules that require it at import time.
  - The runner did not have the system package `python3-tk` installed.
  - Because `tkinter` is provided by the OS package rather than a Python wheel, `pip install -e .` is not enough to prepare the environment.
- Steps to reproduce:
  1. Start from a Linux runner without `python3-tk`.
  2. Run `python3 -m pip install -e . pytest`.
  3. Run `python3 -m pytest`.
  4. Observe collection failures with `ModuleNotFoundError: No module named 'tkinter'`.
- Impact:
  - CI can report a broken build even when application code is healthy.
  - GUI-related tests never execute, so regressions in those paths can be hidden behind environment failures.
- Suggested remediation:
  - Install `python3-tk` in the CI image before running tests.
  - Document the OS-level dependency in developer setup instructions and CI provisioning.
  - Consider isolating pure logic from Tk imports where possible so non-GUI tests can still collect on minimal runners.

### 2. Built-in palette GUI tests are skipped in headless environments

- Severity: **minor**
- Category: test coverage gap
- Affected tests:
  - `tests/test_gui_builtin_palettes.py` (`8 skipped`)
- Failure detail:
  - `Tk is not available in this environment: couldn't connect to display ":1"`
  - Reported by `python3 -m pytest -rs`
- Root cause analysis:
  - The tests create a real `tk.Tk()` root in `_build_gui(...)`.
  - Even after installing `python3-tk`, the current runner has no usable X display for those cases.
  - The suite handles this by skipping, which keeps the run green but leaves this area unverified.
- Steps to reproduce:
  1. Install `python3-tk` on a headless Linux runner without a working display server.
  2. Run `python3 -m pytest -rs tests/test_gui_builtin_palettes.py`.
  3. Observe the tests being skipped with `couldn't connect to display ":1"`.
- Impact:
  - Built-in palette menu, selection, persistence, and related GUI behavior are not covered in CI on headless runners.
  - Regressions in those flows can ship undetected.
- Suggested remediation:
  - Run GUI tests under `xvfb-run` or equivalent virtual display support in CI.
  - Alternatively, refactor the affected tests to reduce reliance on a real display where practical.

### 3. Pillow 14 compatibility risk from deprecated `Image.getdata()`

- Severity: **minor**
- Category: code quality / future compatibility
- Affected locations:
  - `src/pixel_fix/gui/processing.py:916`
  - `src/pixel_fix/gui/processing.py:928`
  - `src/pixel_fix/pipeline.py:232`
  - `tests/test_cli.py:196`
- Failure detail:
  - Current test runs emit:
    - `DeprecationWarning: Image.Image.getdata is deprecated and will be removed in Pillow 14 (2027-10-15). Use get_flattened_data instead.`
- Root cause analysis:
  - The code and one test still rely on the deprecated Pillow API.
  - The suite passes today, but the warning indicates future breakage once Pillow 14 becomes the baseline.
- Steps to reproduce:
  1. Install the project with a current Pillow release.
  2. Run `python3 -m pytest -rs`.
  3. Observe deprecation warnings pointing to the files above.
- Impact:
  - No current functional failure.
  - Future dependency updates may convert these warnings into runtime failures.
- Suggested remediation:
  - Replace `list(rgb.getdata())` with the supported Pillow API indicated by the warning.
  - Update the related test assertion in `tests/test_cli.py` to match the same approach.
  - Consider treating deprecation warnings as CI failures for first-party code paths.

## Improvement Opportunities

### Code quality

- Remove deprecated Pillow calls before the Pillow 14 removal window.
- Reduce import-time coupling between GUI modules and Tk where possible to improve test portability.

### Performance

- No obvious runtime performance regression was identified from the available tests.
- If RampForge-8 palette generation is performance-sensitive on large images, add a benchmark or timing guard because the current suite focuses on correctness rather than throughput.

### Missing test coverage

- Built-in palette GUI paths are not covered in this headless CI environment due the display requirement.
- There is no explicit automated check in this run for performance characteristics of the new RampForge-8 recovery path.

### Best practice gaps

- CI environment requirements are not fully encoded in a reproducible way for GUI-capable tests.
- Deprecation warnings are currently allowed to accumulate in first-party code.

## Overall Assessment

- Functional status after environment setup: **pass**
- Confirmed application regressions in the merged code: **none found by the executed suite**
- Actionable follow-up items: **3**

## Recommended Next Actions

1. Add `python3-tk` to CI provisioning.
2. Run GUI tests with a virtual display such as Xvfb.
3. Replace deprecated `Image.getdata()` usage in application code and tests.

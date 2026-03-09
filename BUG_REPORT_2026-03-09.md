# Bug Report - 2026-03-09

## Validation scope

- Repository: `craigsimm/pixel-fix`
- Trigger: push to `main` at `e892ac0c98d42caee4fbcda76d287a4c23103169`
- Compare range inspected: `30d35e35f4a6..e892ac0c98d42caee4fbcda76d287a4c23103169`
- Files changed in pushed range: `README.md`
- Validation environment: Linux 6.1, Python 3.12.3

## Commands executed

```bash
python3 -m pip install -e . pytest
python3 -m pytest -q
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
python3 -m compileall src tests
```

## Result summary

- Full pytest run: failed during test collection
- Non-Tk subset: `42 passed`
- Syntax compilation: passed

## Bugs found

### 1. Full test suite fails on Linux/headless environments without Tk

- Severity: **major**
- Failing tests:
  - `tests/test_gui_builtin_palettes.py` (collection error)
  - `tests/test_gui_processing.py` (collection error)
- Failure details:

```text
E   ModuleNotFoundError: No module named 'tkinter'
```

- Affected lines:
  - `tests/test_gui_builtin_palettes.py:4`
  - `tests/test_gui_processing.py:5`
  - `src/pixel_fix/gui/app.py:5`

- Root cause analysis:
  - `tests/test_gui_builtin_palettes.py` imports `tkinter` at module import time.
  - `tests/test_gui_processing.py` imports `pixel_fix.gui.app` at module import time.
  - `src/pixel_fix/gui/app.py` imports `tkinter` unconditionally at the top of the module.
  - The intended graceful skip in `tests/test_gui_builtin_palettes.py` happens inside `_build_gui()`, which is too late because collection has already failed before the test body runs.
  - As a result, a Linux runner that does not have the OS-level Tk package installed cannot even collect the suite.

- Steps to reproduce:
  1. Start from a clean Linux environment without `tkinter` installed.
  2. Install the project and pytest:
     ```bash
     python3 -m pip install -e . pytest
     ```
  3. Run:
     ```bash
     python3 -m pytest -q
     ```
  4. Observe collection failing before tests execute.

- User impact:
  - Blocks full-suite validation on common Linux CI runners and minimal developer environments.
  - Makes push-time quality checks unreliable, because failures are caused by environment-sensitive imports rather than application regressions.

- Suggested remediation:
  - Guard GUI-only tests with `pytest.importorskip("tkinter")` at module level.
  - Consider isolating non-GUI logic from the Tkinter UI module so unit tests can import processing helpers without importing `tkinter`.
  - If Linux GUI support is expected, document and provision the required system package in CI and developer setup instructions.

## Improvement opportunities

### A. Test dependencies are not declared for fresh environments

- Category: missing test coverage / best practice
- Severity: **minor**
- Evidence:
  - The repository does not declare `pytest` in `pyproject.toml`.
  - A fresh environment could not run the suite until `pytest` was installed manually.

- Why it matters:
  - Push validation is less reproducible when test tooling is not declared in project metadata.
  - New contributors and automation runners need out-of-band knowledge to execute the test suite.

- Suggestion:
  - Add a dedicated test or dev dependency group in `pyproject.toml` so validation is bootstrapable from project metadata.

### B. README quick-start omits Linux Tk dependency guidance

- Category: documentation / best practice
- Severity: **minor**
- Evidence:
  - `README.md` describes the GUI as the primary workflow and shows `python -m pip install -e .`, but does not note that Linux environments may also require an OS package providing `tkinter`.

- Why it matters:
  - Developers following the documented setup can hit import failures despite completing the Python install step successfully.
  - This gap is more visible after the latest docs-focused push because the README is the only changed file in the compare range.

- Suggestion:
  - Add a short platform note for Linux users describing the required system package (for example, distro-specific Tk bindings).

### C. No repository CI workflow is checked in

- Category: process / code quality
- Severity: **minor**
- Evidence:
  - No files were found under `.github/workflows/`.

- Why it matters:
  - Pushes do not appear to have a repository-native automated test job.
  - There is no built-in check run to publish pass/fail state or link back to a validation report.

- Suggestion:
  - Add a lightweight GitHub Actions workflow that installs the project, installs test dependencies, runs pytest, and publishes artifacts or summaries.

## Overall assessment

- The pushed range itself only changes documentation, and no functional regression attributable to `README.md` was observed.
- The repository still contains one existing **major** validation issue: GUI-related tests are not resilient to environments where Tk is unavailable.
- Aside from that environment-sensitive collection failure, the validated non-GUI test subset is healthy (`42 passed`), and source/test files compile successfully.

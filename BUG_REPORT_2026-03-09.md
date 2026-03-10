# Bug Report - 2026-03-09

## Scope

Automation was triggered by a push to `main` and ran repository validation on Linux.

## Commands Executed

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
python3 -m pixel_fix.cli --help
python3 -m pixel_fix.cli --grid auto input.png output.png
```

## Test Summary

- Full suite status: failed during collection
- Failing modules during collection: `tests/test_gui_builtin_palettes.py`, `tests/test_gui_processing.py`
- Passing subset: 42 tests passed when the two Tk-dependent modules were excluded

## Findings

### 1. Major - GUI test modules fail collection on Linux when `tkinter` is unavailable

**Test names / failure details**

- `tests/test_gui_builtin_palettes.py` fails at import time with:
  - `ModuleNotFoundError: No module named 'tkinter'`
- `tests/test_gui_processing.py` fails at import time with:
  - `ModuleNotFoundError: No module named 'tkinter'`

**Evidence**

- `tests/test_gui_builtin_palettes.py:4` imports `tkinter as tk` at module load time.
- `src/pixel_fix/gui/app.py:5` imports `tkinter as tk` at module load time.
- `tests/test_gui_processing.py:5-6` imports `pixel_fix.gui.app`, which immediately imports `tkinter`.

**Root cause analysis**

The GUI tests are designed to skip when Tk cannot create a window, but that fallback is too late. The imports happen before the test bodies run, so environments without the `python3-tk` system package fail during collection instead of skipping cleanly.

This turns a missing optional desktop dependency into a hard CI failure on Linux.

**Severity**

Major

**Steps to reproduce**

1. Use a Linux Python environment without `tkinter` installed.
2. Install the project and pytest:
   ```bash
   python3 -m pip install -e . pytest
   ```
3. Run:
   ```bash
   python3 -m pytest -q
   ```
4. Observe collection failure before any GUI test can skip itself.

**Suggested remediation**

- Add `pytest.importorskip("tkinter")` or equivalent guard at module level in Tk-dependent tests.
- Consider lazy-importing GUI modules or providing a clearer optional-dependency boundary for desktop-only code.
- If GUI tests must run in CI, install the platform package that provides `tkinter`.

---

### 2. Major - CLI file processing path is still a placeholder copy and can emit an invalid `.png`

**Failure details**

- `src/pixel_fix/pipeline.py:226-229` implements `run_file()` by validating extensions and then calling `copy_as_placeholder(...)`.
- `src/pixel_fix/io.py:25-28` defines `copy_as_placeholder()` as a raw byte-for-byte copy.
- Manual reproduction showed that a JPEG input written to `output.png`:
  - exits with status `0`
  - writes output bytes identical to the JPEG input
  - does **not** produce a valid PNG header

**Observed reproduction output**

```text
returncode= 0
output_header= ffd8ffe000104a46
is_png_header= False
same_bytes= True
```

**Root cause analysis**

The CLI advertises a file-processing workflow, but the current implementation bypasses image decoding, the label-grid pipeline, and PNG encoding. The result is silent success with incorrect output format and no actual processing.

This is especially dangerous for `.jpg -> .png` usage because the output file extension claims PNG while the file contents remain JPEG bytes.

**Severity**

Major

**Steps to reproduce**

1. Create any JPEG image.
2. Run:
   ```bash
   python3 -m pixel_fix.cli sample.jpg output.png
   ```
3. Inspect the output file header or open it in an image tool.
4. Observe that `output.png` contains JPEG bytes rather than processed PNG data.

**Suggested remediation**

- Implement `run_file()` using the same processing path as the tested label-grid pipeline and save the actual processed image.
- Until that is finished, fail fast with a clear error instead of silently copying bytes.
- Add tests that cover:
  - PNG output header validity
  - actual pixel changes for non-trivial inputs
  - JPEG input to PNG output conversion

---

### 3. Minor - README CLI example is out of sync with the actual parser

**Failure details**

- `README.md:96-103` documents:
  - `pixel-fix input.png output.png --grid auto ...`
- `src/pixel_fix/cli.py:9-23` does not define a `--grid` option.
- Reproduction:
  ```bash
  python3 -m pixel_fix.cli --grid auto input.png output.png
  ```
  returns:
  - `error: unrecognized arguments: --grid output.png`

**Root cause analysis**

The README example reflects an older or planned interface rather than the shipped parser, so users following the docs will fail before they can evaluate the CLI.

**Severity**

Minor

**Steps to reproduce**

1. Copy the CLI example from the README.
2. Run it as documented.
3. Observe the argument parsing error.

**Suggested remediation**

- Update the README example to use current flags such as `--pixel-size`.
- Add a smoke test that validates the documented CLI invocation pattern stays aligned with `build_parser()`.

## Improvement Opportunities

### Code quality / best practice

- Treat `tkinter` as an optional desktop dependency boundary instead of a mandatory import for all environments.
- Replace placeholder production paths with explicit errors when behavior is not ready for end users.
- Align documentation claims with the actual shipped CLI.

### Missing test coverage

- No tests currently exercise `pixel_fix.cli` argument parsing or `PixelFixPipeline.run_file()`.
- Add end-to-end CLI tests covering:
  - parser flags
  - output format correctness
  - overwrite behavior
  - palette load/save paths

### Performance

- No concrete performance regression was identified during this automation run.
- Once `run_file()` is implemented for real image processing, add profiling on larger inputs because palette generation and repeated conversions are likely hotspots.

### Additional low-priority follow-up

- `src/pixel_fix/grid/hough_mesh.py` is explicitly marked as a heuristic placeholder and is not referenced by the current test suite. If this path is intended for future runtime use, add integration coverage before enabling it in user-facing workflows.

## Recommended CI Outcome

Current push should be treated as **failed** for quality verification because the full test suite does not pass in the Linux automation environment and the CLI path still contains a production-facing placeholder implementation.

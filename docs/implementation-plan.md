# Pixel-Fix Implementation Plan (No Timeline)

## 1. Product definition
- Define the core goal: recover true editable pixel art from AI-generated pixel-art-like images.
- Lock MVP scope:
  - Input formats: PNG and JPEG (single image first).
  - Output format: PNG.
  - Grid assumptions: axis-aligned for MVP.
  - Alpha handling: preserve alpha with threshold controls.
  - Default palette behavior: quantize without dithering.
- Define MVP success criteria:
  - Grid recovered on representative test inputs.
  - Significant reduction in stray pixels and near-duplicate colours.
  - Deterministic output for fixed parameters.

## 2. Repository architecture
- Package structure:
  - `pixel_fix/io.py` for loading/saving and alpha handling.
  - `pixel_fix/preprocess.py` for normalization.
  - `pixel_fix/grid/` for grid detectors (`hough_mesh`, `projection_fft`, `divisor_fastpath`) and scoring.
  - `pixel_fix/resample.py` for per-cell colour selection.
  - `pixel_fix/palette/` for quantization and colour distance utilities.
  - `pixel_fix/cleanup/` for island removal and line cleanup heuristics.
  - `pixel_fix/pipeline.py` for stage orchestration.
  - `pixel_fix/cli.py` for command-line interface.
- Quality and tooling structure:
  - `tests/` with unit, property, and golden tests.
  - `data/` fixtures and synthetic degradations.
  - `scripts/` benchmarking and report scripts.

## 3. Baseline pipeline
1. Preprocess image (alpha threshold, transparent border trim, optional nearest-neighbor pre-upscale).
2. Recover grid via Canny → morphological closing → probabilistic Hough → line clustering → mesh creation.
3. Resample one output pixel per mesh cell (mode default, median optional).
4. Quantize palette to target size (no dithering by default).
5. Clean up recovered grid (island removal, hole fill, conservative jaggy/gap fixes).
6. Export true-resolution result and optional nearest-neighbor preview upscale.

## 4. Robustness improvements
- Add projection/autocorrelation-based periodic detector.
- Keep divisor/block detector as a fast path for ideal integer-scaled cases.
- Add candidate-scoring system:
  - edge alignment along grid lines,
  - inter-line spacing consistency,
  - per-cell entropy/variance.
- Support manual pixel-width override and debug candidate reporting.

## 5. Evaluation and regression strategy
- Build synthetic degradation generator from clean sprites:
  - non-integer scaling blur,
  - JPEG artifacts,
  - colour jitter,
  - alpha fringe,
  - local warp/mixed scale.
- Track metrics:
  - final unique colour count,
  - palette drift (e.g., ΔE-based),
  - small-component count,
  - outline endpoint count,
  - grid confidence score,
  - SSIM for cases with known references.
- Test layers:
  - unit tests for core algorithms,
  - property tests for reversibility on ideal inputs,
  - golden image tests with deterministic or tolerance-based comparisons.

## 6. CLI contract
- Core options:
  - `--grid {auto,hough,fft,divisor}`
  - `--pixel-width`
  - `--colors`
  - `--cell-sampler {mode,median}`
  - `--min-island-size`
  - `--jaggy-strength`
  - `--dither {none,ordered,floyd-steinberg}`
  - `--save-intermediate DIR`
  - `--report-metrics`
- Ensure deterministic output behavior by default.

## 7. Optional advanced features
- Local/windowed mixed-scale grid estimation and stitching.
- Optional graph-cut or Dense CRF smoothing mode behind a feature flag.
- Optional interactive UI for mesh overlay and parameter tuning.
- Optional high-quality native quantizer backend integration.

## 8. Implementation order
1. CLI/config and stage interfaces.
2. Hough-based mesh detector.
3. Cell resampler.
4. Palette quantizer.
5. Cleanup heuristics.
6. Evaluation harness and regression tests.
7. Secondary detectors and candidate scoring.
8. Advanced smoothing and interactive UI.

## 9. Risk management
- Highest risk: incorrect grid detection.
  - Mitigate with multi-detector strategy, candidate scoring, and manual overrides.
- Secondary risk: cleanup removes intentional detail.
  - Mitigate with conservative defaults and protect-mask options.
- Third risk: quantization adds artefacts.
  - Mitigate with no-dither default and perceptual colour distance checks.

## 10. Definition of done
- Tool reliably outputs editable low-resolution sprites from representative AI-style inputs.
- Colour count reduced toward target without severe contour damage.
- Small stray components and broken outline endpoints decrease on evaluation set.
- Unit, property, and golden regression checks pass.
- Debug artifacts and overrides are available for failure analysis.

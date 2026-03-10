# Developer notes

## Synthetic fixture quality thresholds

The CSEA-style e2e tests (`tests/test_csea_e2e.py`) use JSON fixtures in `tests/fixtures/` and enforce these thresholds:

- **Grid detection bounds**: expected scale exact, phase within ±1, purity >= 0.82.
- **Outline continuity**: connected-component continuity score must improve by >= 0.12.
- **Palette exactness**: palette cardinality of output must equal override palette cardinality exactly.
- **Flat-region denoising**: masked Oklab variance after processing must be <= 35% of pre-process variance.
- **Perceptual distance envelope**: p95 Oklab/HyAB delta between noisy and output <= 0.50.

## Determinism notes

- Fixtures are generated with fixed seeds and committed as golden JSON.
- Tests set `numpy` and `random` seeds before clustering-path checks.
- If clustering internals change, preserve explicit seeding in tests and only update fixture/thresholds with justification.

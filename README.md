# pixel-fix
Pixel-Fix is a tool for cleaning up AI-generated pixel art. It detects inconsistent pixel scaling, reduces noisy colour palettes, and removes stray pixels to restore clean, readable sprites.

## Current status
This repository now includes an executable MVP scaffold:
- A packaged Python project with a `pixel-fix` CLI.
- Modular pipeline stages (`grid`, `resample`, `palette`, `cleanup`, `pipeline`).
- Deterministic candidate-grid scoring and label-grid cleanup primitives.
- Unit tests for scoring, cleanup, and pipeline behavior.

See [`docs/implementation-plan.md`](docs/implementation-plan.md) for the milestone plan.

## Quickstart
```bash
python -m pip install -e .
pixel-fix input.png output.png --grid auto --colors 16 --overwrite
```

> Note: image backend integration is intentionally minimal right now. `run_file` currently performs validated file I/O with placeholder copy behavior while algorithmic stages are implemented and testable through `run_on_labels`.

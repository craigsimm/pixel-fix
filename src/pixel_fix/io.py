from __future__ import annotations

from pathlib import Path

SUPPORTED_INPUT_EXTENSIONS = {".png", ".jpg", ".jpeg"}
SUPPORTED_OUTPUT_EXTENSIONS = {".png"}


def validate_input_path(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    if path.suffix.lower() not in SUPPORTED_INPUT_EXTENSIONS:
        raise ValueError(f"Unsupported input extension: {path.suffix}")


def validate_output_path(path: Path, overwrite: bool = False) -> None:
    if path.suffix.lower() not in SUPPORTED_OUTPUT_EXTENSIONS:
        raise ValueError("Output must be a .png file")
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"Refusing to overwrite existing file: {path}. Use --overwrite to allow it."
        )


def copy_as_placeholder(input_path: Path, output_path: Path) -> None:
    """Minimal no-dependency write path until image backends are integrated."""

    output_path.write_bytes(input_path.read_bytes())

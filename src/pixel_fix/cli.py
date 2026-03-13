from __future__ import annotations

import argparse
<<<<<<< ours
<<<<<<< ours
import json
<<<<<<< ours
from dataclasses import asdict, replace
=======
import traceback
from dataclasses import dataclass
>>>>>>> theirs
=======
from dataclasses import dataclass
>>>>>>> theirs
=======
import sys
>>>>>>> theirs
from pathlib import Path
from time import perf_counter

<<<<<<< ours
from pixel_fix.io import SUPPORTED_INPUT_EXTENSIONS

from pixel_fix.gui.processing import (
    ProcessResult,
    ProcessStats,
    image_to_rgb_grid,
    load_png_rgba_image,
    remove_exterior_outline,
)
from pixel_fix.pipeline import PipelineConfig, PipelinePreparedResult, PixelFixPipeline

CONFLICT_MODES = ("overwrite", "skip", "fail")


@dataclass
class FileRunResult:
    input: Path
    output: Path
    status: str
    error_reason: str | None = None
    traceback: str | None = None

    def to_dict(self, include_error_details: bool = False) -> dict[str, str]:
        data: dict[str, str] = {
            "input": str(self.input),
            "output": str(self.output),
            "status": self.status,
        }
        if include_error_details:
            if self.error_reason is not None:
                data["error_reason"] = self.error_reason
            if self.traceback is not None:
                data["traceback"] = self.traceback
        return data


@dataclass
class RunSummary:
    total_files_discovered: int
    processed_count: int
    skipped_count: int
    failed_count: int
    elapsed_seconds: float

    def to_dict(self) -> dict[str, int | float]:
        return {
            "total_files_discovered": self.total_files_discovered,
            "processed_count": self.processed_count,
            "skipped_count": self.skipped_count,
            "failed_count": self.failed_count,
            "elapsed_seconds": self.elapsed_seconds,
        }


def _discover_inputs(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    if input_path.is_dir():
        return sorted(
            path
            for path in input_path.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_INPUT_EXTENSIONS
        )
    raise FileNotFoundError(f"Input path not found: {input_path}")


def _resolve_output(input_root: Path, output_root: Path, input_path: Path, *, is_batch: bool) -> Path:
    if not is_batch:
        if output_root.is_dir():
            return output_root / f"{input_path.stem}.png"
        return output_root
    relative = input_path.relative_to(input_root)
    return (output_root / relative).with_suffix(".png")


def _print_summary(summary: RunSummary) -> None:
    print("Run summary")
    print(f"  Total files discovered: {summary.total_files_discovered}")
    print(f"  Processed: {summary.processed_count}")
    print(f"  Skipped: {summary.skipped_count}")
    print(f"  Failed: {summary.failed_count}")
    print(f"  Elapsed seconds: {summary.elapsed_seconds:.3f}")
=======
from PIL import Image

from pixel_fix.io import validate_input_path, validate_output_path
from pixel_fix.pipeline import PipelineConfig
from pixel_fix.gui.processing import (
    ProcessResult,
    add_exterior_outline,
    image_to_rgb_grid,
    load_png_rgba_image,
    process_image,
    remove_exterior_outline,
)


@dataclass(frozen=True)
class OperationSummary:
    name: str
    pixels_changed: int


def _parse_hex_color(value: str) -> int:
    stripped = value.strip()
    if len(stripped) != 7 or not stripped.startswith("#"):
        raise argparse.ArgumentTypeError("Expected #RRGGBB format")
    try:
        return int(stripped[1:], 16)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected #RRGGBB format") from exc
>>>>>>> theirs


<<<<<<< ours
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Recover editable pixel art from noisy AI outputs")
    subparsers = parser.add_subparsers(dest="command")

    process = subparsers.add_parser("process", help="Process one image")
    _add_common_process_arguments(process)
    process.add_argument("input", type=Path, help="Input image path (png/jpg/jpeg)")
    process.add_argument("output", type=Path, help="Output image path (png)")
    process.add_argument("--conflict", choices=CONFLICT_MODES, default="fail")
    process.add_argument("--settings", type=Path, default=None, help="Settings profile JSON path to load")
    process.set_defaults(handler=_handle_process)

    batch = subparsers.add_parser("batch", help="Process multiple images")
    _add_common_process_arguments(batch)
    batch.add_argument("input", type=Path, help="Input root directory")
    batch.add_argument("output", type=Path, help="Output root directory")
    batch.add_argument("--glob", default="*.png", help="Input pattern to match")
    batch.add_argument("--recursive", action="store_true", help="Recursively discover files")
    batch.add_argument("--continue-on-error", action="store_true")
    batch.add_argument("--conflict", choices=CONFLICT_MODES, default="fail")
    batch.add_argument("--settings", type=Path, default=None, help="Settings profile JSON path to load")
    batch.add_argument("--report", type=Path, default=None, help="Path to write JSON report")
    batch.set_defaults(handler=_handle_batch)

    return parser


def _add_common_process_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pixel-size", type=int, default=1)
    parser.add_argument("--downsample-mode", choices=["nearest", "bilinear", "rotsprite"], default="nearest")
    parser.add_argument("--colors", type=int, default=16)
    parser.add_argument("--input-mode", choices=["rgba", "indexed", "grayscale"], default="rgba")
    parser.add_argument("--output-mode", choices=["rgba", "indexed", "grayscale"], default="rgba")
    parser.add_argument("--quantizer", choices=["topk", "kmeans"], default="topk")
    parser.add_argument("--dither", choices=["none", "floyd-steinberg", "ordered"], default="none")
    parser.add_argument("--palette", type=Path, default=None, help="Palette JSON path to load")
    parser.add_argument("--save-palette", type=Path, default=None, help="Write generated palette JSON")
<<<<<<< ours
<<<<<<< ours
    parser.add_argument(
        "--outline-threshold",
        type=int,
        default=0,
        help="Only persist exterior outline removal when changed pixels >= threshold",
    )
=======
=======
    parser.add_argument("--transparent-color", type=_parse_hex_color, action="append", default=[], help="Mark a #RRGGBB label as transparent (repeatable)")
    parser.add_argument("--add-outline-color", type=_parse_hex_color, default=None, help="Add exterior outline using #RRGGBB")
    parser.add_argument("--remove-outline", action="store_true", help="Remove one-pixel exterior outline to transparency")
    parser.add_argument("--outline-pixel-perfect", action="store_true", help="Use pixel-perfect cleanup on outline add/remove")
    parser.add_argument("--outline-brightness-threshold", type=int, default=255, help="Only remove outline pixels with brightness <= threshold (0-255)")
    parser.add_argument("--verbose", action="store_true", help="Print per-image operation summaries")
>>>>>>> theirs
    parser.add_argument("--overwrite", action="store_true")
<<<<<<< ours
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--report-json", type=Path, default=None, help="Write machine-readable run report JSON")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--debug", action="store_true")
=======
    parser.add_argument("--verbose", action="store_true", help="Print processing progress")
>>>>>>> theirs
    return parser
>>>>>>> theirs


<<<<<<< ours
def _load_profile(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Settings profile must be a JSON object")
    return data


def _config_from_args(args: argparse.Namespace, *, overwrite: bool, settings: dict[str, object] | None = None) -> PipelineConfig:
    settings = settings or {}
    config = PipelineConfig()
    if settings:
        valid_keys = set(asdict(config).keys())
        patch = {key: value for key, value in settings.items() if key in valid_keys}
        config = replace(config, **patch)
    return replace(
        config,
=======
def _build_output_image(result: ProcessResult, transparent_labels: set[int]) -> Image.Image:
    image = Image.new("RGBA", (result.width, result.height))
    alpha_mask = result.alpha_mask
    pixels: list[tuple[int, int, int, int]] = []
    for y, row in enumerate(result.grid):
        for x, (red, green, blue) in enumerate(row):
            label = (red << 16) | (green << 8) | blue
            is_visible = True if alpha_mask is None else bool(alpha_mask[y][x])
            alpha = 0 if (not is_visible or label in transparent_labels) else 255
            pixels.append((red, green, blue, alpha))
    image.putdata(pixels)
    return image


def apply_cli_post_processing(
    result: ProcessResult,
    *,
    transparent_labels: set[int],
    add_outline_label: int | None,
    remove_outline: bool,
    outline_pixel_perfect: bool,
    outline_brightness_threshold: int,
) -> tuple[ProcessResult, list[OperationSummary]]:
    summaries: list[OperationSummary] = []

    visible_mask = result.alpha_mask
    transparent_changed = 0
    for y, row in enumerate(result.grid):
        for x, (red, green, blue) in enumerate(row):
            is_visible = True if visible_mask is None else bool(visible_mask[y][x])
            if not is_visible:
                continue
            label = (red << 16) | (green << 8) | blue
            if label in transparent_labels:
                transparent_changed += 1
    if transparent_labels:
        summaries.append(OperationSummary(name="transparency", pixels_changed=transparent_changed))

    if add_outline_label is not None:
        result, changed = add_exterior_outline(
            result,
            add_outline_label,
            transparent_labels=transparent_labels,
            pixel_perfect=outline_pixel_perfect,
        )
        summaries.append(OperationSummary(name="add_outline", pixels_changed=changed))

    if remove_outline:
        result, changed = remove_exterior_outline(
            result,
            transparent_labels=transparent_labels,
            pixel_perfect=outline_pixel_perfect,
            brightness_threshold=outline_brightness_threshold,
        )
        summaries.append(OperationSummary(name="remove_outline", pixels_changed=changed))

    return result, summaries


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not 0 <= args.outline_brightness_threshold <= 255:
        parser.error("--outline-brightness-threshold must be between 0 and 255")

    validate_input_path(args.input)
    validate_output_path(args.output, overwrite=args.overwrite)

    config = PipelineConfig(
>>>>>>> theirs
=======
def _add_pipeline_options(parser: argparse.ArgumentParser) -> None:
    pipeline = parser.add_argument_group("pipeline settings")
    pipeline.add_argument("--pixel-size", type=int, default=1)
    pipeline.add_argument("--downsample-mode", choices=["nearest", "bilinear", "rotsprite"], default="nearest")
    pipeline.add_argument("--colors", type=int, default=16)
    pipeline.add_argument("--input-mode", choices=["rgba", "indexed", "grayscale"], default="rgba")
    pipeline.add_argument("--output-mode", choices=["rgba", "indexed", "grayscale"], default="rgba")
    pipeline.add_argument("--quantizer", choices=["topk", "kmeans"], default="topk")
    pipeline.add_argument("--dither", choices=["none", "floyd-steinberg", "ordered"], default="none")
    pipeline.add_argument("--palette", type=Path, default=None, help="Palette JSON path to load")
    pipeline.add_argument("--save-palette", type=Path, default=None, help="Write generated palette JSON")


def _build_config(args: argparse.Namespace, *, overwrite: bool) -> PipelineConfig:
    return PipelineConfig(
>>>>>>> theirs
        pixel_width=args.pixel_size,
        downsample_mode=args.downsample_mode,
        colors=args.colors,
        input_mode=args.input_mode,
        output_mode=args.output_mode,
        quantizer=args.quantizer,
        dither_mode=args.dither,
        palette_path=args.palette,
        save_palette_path=args.save_palette,
        overwrite=overwrite,
<<<<<<< ours
    )

<<<<<<< ours

def _resolve_conflict(path: Path, mode: str) -> bool:
    if not path.exists():
        return True
    if mode == "overwrite":
        return True
    if mode == "skip":
        return False
    raise FileExistsError(f"Refusing to overwrite existing file: {path}")




def _validate_image_file(path: Path) -> None:
    # Force decode to fail early for corrupt inputs.
    load_png_rgba_image(str(path))

def _apply_thresholded_outline_removal(output_path: Path, threshold: int) -> int:
    if threshold <= 0:
        return 0
    image = load_png_rgba_image(str(output_path))
    grid = image_to_rgb_grid(image)
    result = ProcessResult(
        grid=grid,
        width=image.width,
        height=image.height,
        prepared_input=PipelinePreparedResult(
            reduced_labels=[],
            pixel_width=1,
            grid_method="manual",
            input_size=(image.width, image.height),
            initial_color_count=0,
        ),
        stats=ProcessStats(
            stage="outline",
            pixel_width=1,
            resize_method="nearest",
            input_size=(image.width, image.height),
            output_size=(image.width, image.height),
            initial_color_count=0,
            color_count=0,
            elapsed_seconds=0.0,
        ),
=======
>>>>>>> theirs
    )
    updated, changed = remove_exterior_outline(result)
    if changed < threshold:
        return 0
    alpha = updated.alpha_mask
    rgba = image.convert("RGBA")
    pixels = list(rgba.getdata())
    next_pixels = []
    for index, (r, g, b, a) in enumerate(pixels):
        x = index % image.width
        y = index // image.width
        visible = True if alpha is None else alpha[y][x]
        next_pixels.append((r, g, b, a if visible else 0))
    rgba.putdata(next_pixels)
    rgba.save(output_path)
    return changed


def _handle_process(args: argparse.Namespace) -> int:
    settings = _load_profile(args.settings)
    should_write = _resolve_conflict(args.output, args.conflict)
    if not should_write:
        return 0
    config = _config_from_args(args, overwrite=True, settings=settings)
    _validate_image_file(args.input)
    PixelFixPipeline(config).run_file(args.input, args.output)
    _apply_thresholded_outline_removal(args.output, args.outline_threshold)
    return 0


<<<<<<< ours
def _discover_inputs(root: Path, pattern: str, recursive: bool) -> list[Path]:
    iterator = root.rglob(pattern) if recursive else root.glob(pattern)
    return sorted(path for path in iterator if path.is_file())


def _handle_batch(args: argparse.Namespace) -> int:
    settings = _load_profile(args.settings)
    config = _config_from_args(args, overwrite=True, settings=settings)
=======
def _resolve_batch_inputs(args: argparse.Namespace) -> list[Path]:
    if args.input_dir is None and args.glob is None:
        raise ValueError("Batch mode requires --input-dir and/or --glob.")

    if args.glob is not None:
        base = args.input_dir or Path.cwd()
        paths = list(base.rglob(args.glob)) if args.recursive else list(base.glob(args.glob))
    else:
        iterator = args.input_dir.rglob("*") if args.recursive else args.input_dir.glob("*")
        paths = [path for path in iterator if path.is_file()]

    return sorted(path for path in paths if path.is_file())


def _build_batch_output_path(input_path: Path, output_dir: Path) -> Path:
    return output_dir / f"{input_path.stem}.png"


def _run_process(args: argparse.Namespace) -> int:
    config = _build_config(args, overwrite=args.overwrite)
>>>>>>> theirs
    pipeline = PixelFixPipeline(config)
<<<<<<< ours

    discovered = _discover_inputs(args.input, args.glob, args.recursive)
    summary: dict[str, object] = {
        "pattern": args.glob,
        "recursive": bool(args.recursive),
        "discovered": len(discovered),
        "processed": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
    }

    for source in discovered:
        relative = source.relative_to(args.input)
        target = args.output / relative.with_suffix(".png")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            should_write = _resolve_conflict(target, args.conflict)
            if not should_write:
                summary["skipped"] = int(summary["skipped"]) + 1
                continue
            _validate_image_file(source)
            pipeline.run_file(source, target)
            _apply_thresholded_outline_removal(target, args.outline_threshold)
            summary["processed"] = int(summary["processed"]) + 1
        except Exception as exc:
            summary["failed"] = int(summary["failed"]) + 1
            cast_errors = summary["errors"]
            assert isinstance(cast_errors, list)
            cast_errors.append({"input": str(source), "error": str(exc)})
            if not args.continue_on_error:
                if args.report is not None:
                    args.report.parent.mkdir(parents=True, exist_ok=True)
                    args.report.write_text(json.dumps(summary, indent=2), encoding="utf-8")
                raise

    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(summary, indent=2), encoding="utf-8")
=======
    source_image = load_png_rgba_image(str(args.input))
    base = process_image(image_to_rgb_grid(source_image), config)

    transparent_labels = set(args.transparent_color)
    processed, summaries = apply_cli_post_processing(
        base,
        transparent_labels=transparent_labels,
        add_outline_label=args.add_outline_color,
        remove_outline=args.remove_outline,
        outline_pixel_perfect=args.outline_pixel_perfect,
        outline_brightness_threshold=args.outline_brightness_threshold,
    )
    output = _build_output_image(processed, transparent_labels)
    output.save(args.output, format="PNG")

    if args.verbose:
        print(f"Processed {args.input} -> {args.output}")
        print("Operation order: base process -> transparency ops -> outline ops -> save")
        for summary in summaries:
            print(f"  {summary.name}: {summary.pixels_changed} pixels changed")

>>>>>>> theirs
    return 0
=======
    include_error_details = args.verbose or args.debug

    start = perf_counter()
    discovered_inputs = _discover_inputs(args.input)
    is_batch = args.input.is_dir()
    if is_batch and args.output.suffix:
        raise ValueError("When input is a directory, output must be a directory path")

    results: list[FileRunResult] = []
    failed_count = 0
    processed_count = 0
    skipped_count = 0

    for input_path in discovered_inputs:
        output_path = _resolve_output(args.input, args.output, input_path, is_batch=is_batch)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            pipeline.run_file(input_path, output_path)
            results.append(FileRunResult(input=input_path, output=output_path, status="processed"))
            processed_count += 1
        except FileExistsError as exc:
            skipped_count += 1
            result = FileRunResult(input=input_path, output=output_path, status="skipped")
            if include_error_details:
                result.error_reason = str(exc)
                result.traceback = traceback.format_exc()
            results.append(result)
            if args.debug:
                print(f"Skipped {input_path}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed_count += 1
            result = FileRunResult(input=input_path, output=output_path, status="failed")
            if include_error_details:
                result.error_reason = str(exc)
                result.traceback = traceback.format_exc()
            results.append(result)
            if include_error_details:
                print(f"Failed {input_path}: {exc}")
            if not args.continue_on_error:
                break

    summary = RunSummary(
        total_files_discovered=len(discovered_inputs),
        processed_count=processed_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
        elapsed_seconds=perf_counter() - start,
    )
    _print_summary(summary)

    if args.report_json is not None:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        report_data = {
            "summary": summary.to_dict(),
            "files": [result.to_dict(include_error_details=include_error_details) for result in results],
        }
        args.report_json.write_text(json.dumps(report_data, indent=2), encoding="utf-8")

    return 1 if failed_count else 0
>>>>>>> theirs


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or [])
    if argv and argv[0] not in {"process", "batch", "-h", "--help"}:
        argv = ["process", *argv]
    parser = build_parser()
    args = parser.parse_args(argv)

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 2
    return handler(args)


def _run_batch(args: argparse.Namespace) -> int:
    input_paths = _resolve_batch_inputs(args)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    overwrite = args.on_conflict == "overwrite"
    config = _build_config(args, overwrite=overwrite)
    pipeline = PixelFixPipeline(config)
<<<<<<< ours

    failures = 0
    for input_path in input_paths:
        output_path = _build_batch_output_path(input_path, output_dir)
        if output_path.exists() and args.on_conflict == "skip":
            continue
        if output_path.exists() and args.on_conflict == "fail":
            failures += 1
            if not args.continue_on_error:
                return 1
            continue

        try:
            pipeline.run_file(input_path, output_path)
        except Exception as exc:  # pragma: no cover - broad by design for CLI resilience
            failures += 1
            print(f"Failed to process {input_path}: {exc}", file=sys.stderr)
            if not args.continue_on_error:
                return 1

    if failures > 0 and not args.continue_on_error:
        return 1
=======
    if args.verbose:
        pipeline.run_file_with_progress(
            args.input,
            args.output,
            progress_callback=lambda percent, message: print(f"[{percent:3d}%] {message}"),
        )
    else:
        pipeline.run_file(args.input, args.output)
>>>>>>> theirs
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Recover editable pixel art from noisy AI outputs")
    subparsers = parser.add_subparsers(dest="command")

    process = subparsers.add_parser("process", help="Process a single image")
    process.add_argument("input", type=Path, help="Input image path (png/jpg/jpeg)")
    process.add_argument("output", type=Path, help="Output image path (png)")
    _add_pipeline_options(process)
    process.add_argument("--overwrite", action="store_true")

    batch = subparsers.add_parser("batch", help="Process multiple images")
    _add_pipeline_options(batch)
    batch.add_argument("--input-dir", type=Path, default=None, help="Directory containing input images")
    batch.add_argument("--glob", dest="glob", default=None, help="Glob pattern to select input images")
    batch.add_argument("--output-dir", type=Path, required=True, help="Directory for output images")
    batch.add_argument("--recursive", action="store_true", help="Recursively scan --input-dir")
    batch.add_argument(
        "--on-conflict",
        choices=["skip", "overwrite", "fail"],
        default="fail",
        help="Behavior when an output file already exists",
    )
    batch.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue processing remaining files when one fails; exits non-zero unless this is enabled.",
    )

    return parser


def _normalize_argv(argv: list[str] | None) -> list[str]:
    raw = list(sys.argv[1:] if argv is None else argv)
    if not raw:
        return raw

    if raw[0] in {"process", "batch", "-h", "--help"}:
        return raw

    print(
        "Deprecation warning: implicit single-file mode is deprecated; use `process <input> <output>`.",
        file=sys.stderr,
    )
    return ["process", *raw]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(_normalize_argv(argv))

    if args.command == "process":
        return _run_process(args)
    if args.command == "batch":
        return _run_batch(args)

    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pixel_fix.cli_workflow import (
    CliJobError,
    apply_job_overrides,
    load_job_spec,
    run_batch_job,
    run_process_job,
    write_default_job_config,
)

PROCESS_COMMANDS = {"process", "batch", "config"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Recover editable pixel art from noisy AI outputs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    process_parser = subparsers.add_parser("process", help="Process one image headlessly")
    _add_common_process_options(process_parser)
    process_parser.add_argument("input", type=Path, help="Input image path")
    process_parser.add_argument("output", type=Path, help="Output PNG path")
    process_parser.add_argument("--save-palette", type=Path, default=None, help="Optional output palette path (.gpl or .json)")

    batch_parser = subparsers.add_parser("batch", help="Process a directory tree with one shared job config")
    _add_common_process_options(batch_parser)
    batch_parser.add_argument("input_dir", type=Path, help="Input directory")
    batch_parser.add_argument("output_dir", type=Path, help="Output directory")
    batch_parser.add_argument("--glob", dest="batch_glob", default=None, help="Recursive input glob, default: *.png")
    batch_parser.add_argument("--report", type=Path, default=None, help="Batch report JSON path")
    batch_parser.add_argument("--fail-fast", action="store_true", help="Stop on the first per-file failure")

    config_parser = subparsers.add_parser("config", help="Create or manage CLI job files")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    init_parser = config_subparsers.add_parser("init", help="Write a starter JSON job file")
    init_parser.add_argument("path", type=Path, help="Path to write the starter config")
    init_parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing config file")

    return parser


def build_legacy_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Recover editable pixel art from noisy AI outputs")
    parser.add_argument("input", type=Path, help="Input image path (png/jpg/jpeg)")
    parser.add_argument("output", type=Path, help="Output image path (png)")
    parser.add_argument("--pixel-size", type=int, default=None)
    parser.add_argument("--downsample-mode", choices=["nearest", "bilinear", "rotsprite"], default=None)
    parser.add_argument("--colors", type=int, default=None)
    parser.add_argument("--input-mode", choices=["rgba", "indexed", "grayscale"], default=None)
    parser.add_argument("--output-mode", choices=["rgba", "indexed", "grayscale"], default=None)
    parser.add_argument("--quantizer", choices=["topk", "median-cut", "kmeans"], default=None)
    parser.add_argument("--dither", choices=["none", "ordered", "blue-noise", "floyd-steinberg"], default=None)
    parser.add_argument("--palette", type=Path, default=None, help="Palette file to load")
    parser.add_argument("--save-palette", type=Path, default=None, help="Write the final palette")
    parser.add_argument("--config", type=Path, default=None, help="CLI job JSON")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    try:
        if _should_use_legacy_parser(args_list):
            return _run_legacy(args_list)
        return _run_command(args_list)
    except (CliJobError, FileExistsError, FileNotFoundError, ValueError) as exc:
        print(f"pixel-fix: {exc}", file=sys.stderr)
        return 1


def _add_common_process_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, default=None, help="CLI job JSON")
    parser.add_argument("--pixel-size", type=int, default=None, help="Override pipeline.pixel_width")
    parser.add_argument("--downsample-mode", choices=["nearest", "bilinear", "rotsprite"], default=None)
    parser.add_argument("--colors", type=int, default=None, help="Override pipeline.palette_reduction_colors")
    parser.add_argument("--generated-shades", type=int, default=None, help="Override pipeline.generated_shades")
    parser.add_argument("--contrast-bias", type=float, default=None, help="Override pipeline.contrast_bias")
    parser.add_argument("--palette-dither", choices=["none", "ordered", "blue-noise"], default=None)
    parser.add_argument("--input-mode", choices=["rgba", "indexed", "grayscale"], default=None)
    parser.add_argument("--output-mode", choices=["rgba", "indexed", "grayscale"], default=None)
    parser.add_argument("--quantizer", choices=["median-cut", "kmeans", "topk"], default=None)
    parser.add_argument("--palette-file", type=Path, default=None, help="Override palette_source with a palette file")
    parser.add_argument("--builtin-palette", type=str, default=None, help="Override palette_source with a built-in palette path like dawn/db16.gpl")
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting existing outputs")


def _should_use_legacy_parser(argv: list[str]) -> bool:
    if not argv:
        return False
    if argv[0] in PROCESS_COMMANDS:
        return False
    if argv[0] in {"-h", "--help"}:
        return False
    return True


def _run_command(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "process":
        job = _resolve_job(args)
        result = run_process_job(
            args.input,
            args.output,
            job,
            overwrite=args.overwrite,
            palette_output_path=args.save_palette,
        )
        palette_clause = f" and palette {result.palette_path}" if result.palette_path is not None else ""
        print(f"Processed {result.input_path} -> {result.output_path}{palette_clause}")
        return 0
    if args.command == "batch":
        job = _resolve_job(args)
        result = run_batch_job(
            args.input_dir,
            args.output_dir,
            job,
            overwrite=args.overwrite,
            fail_fast=args.fail_fast,
            report_path=args.report,
        )
        print(
            f"Batch processed {result.processed} file(s) with {result.failed} failure(s). "
            f"Report: {result.report_path}"
        )
        return 0 if result.failed == 0 else 1
    if args.command == "config" and args.config_command == "init":
        path = write_default_job_config(args.path, overwrite=args.overwrite)
        print(f"Wrote starter CLI job file to {path.resolve()}")
        return 0
    raise CliJobError("Unsupported command.")


def _run_legacy(argv: list[str]) -> int:
    parser = build_legacy_parser()
    args = parser.parse_args(argv)
    print(
        "Deprecation warning: use 'pixel-fix process INPUT OUTPUT ...' instead of the legacy positional form.",
        file=sys.stderr,
    )
    job = _resolve_job(args, legacy_dither=True)
    result = run_process_job(
        args.input,
        args.output,
        job,
        overwrite=args.overwrite,
        palette_output_path=args.save_palette,
    )
    palette_clause = f" and palette {result.palette_path}" if result.palette_path is not None else ""
    print(f"Processed {result.input_path} -> {result.output_path}{palette_clause}")
    return 0


def _resolve_job(args: argparse.Namespace, *, legacy_dither: bool = False):
    job = load_job_spec(args.config, cwd=Path.cwd())
    palette_dither = getattr(args, "palette_dither", None)
    if legacy_dither and getattr(args, "dither", None) is not None:
        palette_dither = args.dither
    return apply_job_overrides(
        job,
        pixel_width=getattr(args, "pixel_size", None),
        downsample_mode=getattr(args, "downsample_mode", None),
        palette_reduction_colors=getattr(args, "colors", None),
        generated_shades=getattr(args, "generated_shades", None),
        contrast_bias=getattr(args, "contrast_bias", None),
        palette_dither_mode=palette_dither,
        input_mode=getattr(args, "input_mode", None),
        output_mode=getattr(args, "output_mode", None),
        quantizer=getattr(args, "quantizer", None),
        palette_file=getattr(args, "palette_file", None) or getattr(args, "palette", None),
        builtin_palette=getattr(args, "builtin_palette", None),
        batch_glob=getattr(args, "batch_glob", None),
        report_path=getattr(args, "report", None),
        save_palette_path=getattr(args, "save_palette", None),
    )


if __name__ == "__main__":
    raise SystemExit(main())

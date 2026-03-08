from __future__ import annotations

import argparse
from pathlib import Path

from pixel_fix.pipeline import PipelineConfig, PixelFixPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Recover editable pixel art from noisy AI outputs")
    parser.add_argument("input", type=Path, help="Input image path (png/jpg/jpeg)")
    parser.add_argument("output", type=Path, help="Output image path (png)")
    parser.add_argument("--grid", choices=["auto", "hough", "fft", "divisor"], default="auto")
    parser.add_argument("--pixel-width", type=int, default=None)
    parser.add_argument("--colors", type=int, default=16)
    parser.add_argument("--cell-sampler", choices=["mode", "median"], default="mode")
    parser.add_argument("--min-island-size", type=int, default=2)
    parser.add_argument("--line-color", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    config = PipelineConfig(
        grid=args.grid,
        pixel_width=args.pixel_width,
        colors=args.colors,
        cell_sampler=args.cell_sampler,
        min_island_size=args.min_island_size,
        line_color=args.line_color,
        overwrite=args.overwrite,
    )

    pipeline = PixelFixPipeline(config)
    pipeline.run_file(args.input, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

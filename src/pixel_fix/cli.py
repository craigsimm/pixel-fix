from __future__ import annotations

import argparse
from pathlib import Path

from pixel_fix.pipeline import PipelineConfig, PixelFixPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Recover editable pixel art from noisy AI outputs")
    parser.add_argument("input", type=Path, help="Input image path (png/jpg/jpeg)")
    parser.add_argument("output", type=Path, help="Output image path (png)")
    parser.add_argument("--pixel-size", type=int, default=1)
    parser.add_argument("--downsample-mode", choices=["nearest", "bilinear", "rotsprite"], default="nearest")
    parser.add_argument("--colors", type=int, default=16)
    parser.add_argument("--input-mode", choices=["rgba", "indexed", "grayscale"], default="rgba")
    parser.add_argument("--output-mode", choices=["rgba", "indexed", "grayscale"], default="rgba")
    parser.add_argument("--quantizer", choices=["topk", "kmeans"], default="topk")
    parser.add_argument("--dither", choices=["none", "floyd-steinberg", "ordered"], default="none")
    parser.add_argument("--palette", type=Path, default=None, help="Palette JSON path to load")
    parser.add_argument("--save-palette", type=Path, default=None, help="Write generated palette JSON")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    config = PipelineConfig(
        pixel_width=args.pixel_size,
        downsample_mode=args.downsample_mode,
        colors=args.colors,
        input_mode=args.input_mode,
        output_mode=args.output_mode,
        quantizer=args.quantizer,
        dither_mode=args.dither,
        palette_path=args.palette,
        save_palette_path=args.save_palette,
        overwrite=args.overwrite,
    )

    pipeline = PixelFixPipeline(config)
    pipeline.run_file(args.input, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

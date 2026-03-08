from __future__ import annotations

from pathlib import Path

from PIL import Image


ICON_SIZES = [(16, 16), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)]


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source_path = repo_root / "ico-512.png"
    output_path = repo_root / "pixel-fix.ico"

    with Image.open(source_path) as image:
        image = image.convert("RGBA")
        image.save(output_path, format="ICO", sizes=ICON_SIZES)

    print(output_path)
    print("sizes:", ", ".join(f"{width}x{height}" for width, height in ICON_SIZES))


if __name__ == "__main__":
    main()

from __future__ import annotations

from PIL import Image

from pixel_fix.types import LabelGrid

RESAMPLE_MODES = ("nearest", "bilinear", "rotsprite")


def target_size_for_pixel_width(width: int, height: int, pixel_width: int) -> tuple[int, int]:
    if pixel_width <= 0:
        raise ValueError("pixel_width must be > 0")
    return (
        max(1, (width + pixel_width - 1) // pixel_width),
        max(1, (height + pixel_width - 1) // pixel_width),
    )


def resize_labels(labels: LabelGrid, pixel_width: int, method: str = "nearest") -> LabelGrid:
    if pixel_width <= 0:
        raise ValueError("pixel_width must be > 0")
    if method not in RESAMPLE_MODES:
        raise ValueError(f"Unsupported resample mode: {method}")

    height = len(labels)
    width = len(labels[0]) if height else 0
    if width == 0 or height == 0:
        return []

    target_size = target_size_for_pixel_width(width, height, pixel_width)
    image = _labels_to_image(labels)
    if method == "nearest":
        resized = image.resize(target_size, Image.Resampling.NEAREST)
    elif method == "bilinear":
        resized = image.resize(target_size, Image.Resampling.BILINEAR)
    else:
        resized = _rotsprite_resize(image, target_size)
    return _image_to_labels(resized)


def _labels_to_image(labels: LabelGrid) -> Image.Image:
    height = len(labels)
    width = len(labels[0]) if height else 0
    image = Image.new("RGB", (width, height))
    if width == 0 or height == 0:
        return image
    image.putdata(
        [
            ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)
            for row in labels
            for value in row
        ]
    )
    return image


def _image_to_labels(image: Image.Image) -> LabelGrid:
    rgb = image.convert("RGB")
    width, height = rgb.size
    if width == 0 or height == 0:
        return []
    pixels = rgb.load()
    return [
        [((pixels[x, y][0] << 16) | (pixels[x, y][1] << 8) | pixels[x, y][2]) for x in range(width)]
        for y in range(height)
    ]


def _rotsprite_resize(image: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    working = image.convert("RGB")
    # A pragmatic RotSprite-style approximation: smooth diagonals with Scale2x, then
    # sample the result with nearest-neighbor so colors stay crisp.
    while working.width < target_size[0] * 2 and working.height < target_size[1] * 2:
        working = _scale2x(working)
    if working.width < image.width * 4 and working.height < image.height * 4:
        working = _scale2x(_scale2x(image.convert("RGB")))
    return working.resize(target_size, Image.Resampling.NEAREST)


def _scale2x(image: Image.Image) -> Image.Image:
    source = image.convert("RGB")
    width, height = source.size
    if width == 0 or height == 0:
        return source.copy()

    src = source.load()
    target = Image.new("RGB", (width * 2, height * 2))
    dst = target.load()

    for y in range(height):
        for x in range(width):
            a = src[x, y - 1] if y > 0 else src[x, y]
            b = src[x - 1, y] if x > 0 else src[x, y]
            c = src[x, y]
            d = src[x + 1, y] if x < width - 1 else src[x, y]
            e = src[x, y + 1] if y < height - 1 else src[x, y]

            if a != e and b != d:
                e0 = b if b == a else c
                e1 = d if a == d else c
                e2 = b if b == e else c
                e3 = d if e == d else c
            else:
                e0 = e1 = e2 = e3 = c

            dst[x * 2, y * 2] = e0
            dst[x * 2 + 1, y * 2] = e1
            dst[x * 2, y * 2 + 1] = e2
            dst[x * 2 + 1, y * 2 + 1] = e3
    return target

from pathlib import Path

import numpy as np
from PIL import Image

from pixel_fix.palette.advanced import detect_key_colors_from_image, generate_structured_palette
from pixel_fix.palette.color_modes import convert_mode, extract_unique_colors, to_indexed
from pixel_fix.palette.dither import apply_dither
from pixel_fix.palette.io import load_palette, save_palette
from pixel_fix.palette.quantize import generate_palette, remap_to_palette
from pixel_fix.palette.replace import replace_batch, replace_exact, replace_tolerance
from pixel_fix.palette.workspace import ColorWorkspace, hyab_distance


def test_color_mode_grayscale_conversion() -> None:
    labels = [[0xFF0000, 0x00FF00]]
    out = convert_mode(labels, "grayscale")
    assert ((out[0][0] >> 16) & 0xFF) == ((out[0][0] >> 8) & 0xFF) == (out[0][0] & 0xFF)


def test_unique_palette_and_indexed_limit() -> None:
    labels = [[1, 2], [3, 2]]
    unique = extract_unique_colors(labels)
    assert unique == [1, 2, 3]
    indexed, palette = to_indexed(labels, max_colors=2)
    assert len(palette) == 2
    assert len(indexed) == 2


def test_palette_io_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "palette.json"
    save_palette(path, [0x112233, 0xabcdef])
    loaded = load_palette(path)
    assert loaded == [0x112233, 0xABCDEF]


def test_gpl_palette_loads_with_comments_and_headers(tmp_path: Path) -> None:
    path = tmp_path / "palette.gpl"
    path.write_text(
        "\n".join(
            (
                "GIMP Palette",
                "Name: Example",
                "Columns: 2",
                "# comment",
                "17 34 51 First",
                "171 205 239 Second",
            )
        ),
        encoding="utf-8",
    )
    loaded = load_palette(path)
    assert loaded == [0x112233, 0xABCDEF]


def test_gpl_palette_rejects_invalid_colour_lines(tmp_path: Path) -> None:
    path = tmp_path / "broken.gpl"
    path.write_text("GIMP Palette\nnot-a-colour\n", encoding="utf-8")
    try:
        load_palette(path)
    except ValueError as exc:
        assert "Invalid GPL palette" in str(exc)
    else:
        raise AssertionError("Expected invalid GPL data to raise ValueError")


def test_quantizer_and_dither_pipeline_bits() -> None:
    labels = [[0x010101, 0xFEFEFE], [0x101010, 0xEEEEEE]]
    palette = generate_palette(labels, colors=2, method="kmeans")
    assert len(palette) == 2
    mapped = remap_to_palette(labels, palette)
    dithered = apply_dither(mapped, palette, "ordered")
    assert {v for row in dithered for v in row}.issubset(set(palette))


def test_color_replacement_variants() -> None:
    labels = [[0x101010, 0x202020], [0x111111, 0x303030]]
    assert replace_exact(labels, 0x202020, 0xAAAAAA)[0][1] == 0xAAAAAA
    tol = replace_tolerance(labels, 0x101010, 0xBBBBBB, tolerance=2)
    assert tol[1][0] == 0xBBBBBB
    batch = replace_batch(labels, {0x303030: 0xCCCCCC})
    assert batch[1][1] == 0xCCCCCC


def test_oklab_workspace_roundtrip_and_cache_reuse() -> None:
    workspace = ColorWorkspace()
    labels = np.asarray([0x112233, 0xABCDEF, 0x112233], dtype=np.int64)
    converted = workspace.labels_to_oklab(labels)
    assert converted.shape == (3, 3)
    assert workspace.cache_size() == 2
    workspace.labels_to_oklab(labels)
    assert workspace.cache_size() == 2

    rebuilt = [workspace.oklab_to_label(color) for color in converted]
    for actual, expected in zip(rebuilt, labels.tolist(), strict=True):
        for shift in (16, 8, 0):
            assert abs(((actual >> shift) & 0xFF) - ((expected >> shift) & 0xFF)) <= 1


def test_hyab_distance_prefers_perceptually_similar_colour() -> None:
    workspace = ColorWorkspace()
    points = workspace.labels_to_oklab(np.asarray([0x808080, 0x8A8A8A, 0x33AA00], dtype=np.int64))
    similar = float(hyab_distance(points[0:1], points[1:2])[0])
    different = float(hyab_distance(points[0:1], points[2:3])[0])
    assert similar < different


def test_generate_structured_palette_builds_monotonic_ramps() -> None:
    labels = [
        [0x6AAAD8, 0x6AAAD8, 0x355E7D],
        [0xD8B06A, 0x6AAAD8, 0x355E7D],
        [0x254060, 0xD8B06A, 0x254060],
    ]
    computation = generate_structured_palette(
        labels,
        key_colors=[0x6AAAD8, 0xD8B06A, 0x355E7D],
        generated_shades=4,
        contrast_bias=1.2,
    )
    palette = computation.palette
    assert palette.source_mode == "advanced"
    assert len(palette.ramps) == 3
    assert palette.generated_shades == 4
    for ramp in palette.ramps:
        lightness = [color.oklab[0] for color in ramp.colors]
        assert lightness == sorted(lightness)
        assert len(ramp.colors) == 5
        assert ramp.colors[len(ramp.colors) // 2].is_seed


def test_generate_structured_palette_caps_key_colours_at_twelve() -> None:
    computation = generate_structured_palette(
        [],
        key_colors=[index for index in range(16)],
        generated_shades=2,
    )
    assert len(computation.palette.key_colors) == 12
    assert len(computation.palette.ramps) == 12


def test_detect_key_colors_ignores_transparent_pixels() -> None:
    image = Image.new("RGBA", (4, 1))
    image.putdata(
        [
            (255, 0, 0, 0),
            (255, 0, 0, 0),
            (0, 0, 255, 255),
            (0, 0, 255, 255),
        ]
    )
    assert detect_key_colors_from_image(image) == [0x0000FF]


def test_detect_key_colors_picks_dominant_midtone() -> None:
    mid = (180, 40, 40, 255)
    dark = (90, 10, 10, 255)
    light = (250, 170, 170, 255)
    image = Image.new("RGBA", (16, 1))
    image.putdata([mid] * 10 + [dark] * 3 + [light] * 3)
    detected = detect_key_colors_from_image(image, max_colors=1)
    assert detected == [0xB42828]


def test_detect_key_colors_includes_neutral_family_when_significant() -> None:
    gray = (136, 136, 136, 255)
    red = (220, 60, 60, 255)
    blue = (70, 110, 220, 255)
    image = Image.new("RGBA", (10, 10))
    image.putdata(([gray] * 20) + ([red] * 40) + ([blue] * 40))
    detected = detect_key_colors_from_image(image)
    assert 0x888888 in detected
    assert 0xDC3C3C in detected
    assert 0x466EDC in detected


def test_detect_key_colors_drops_minor_hue_families() -> None:
    red = (220, 60, 60, 255)
    blue = (70, 110, 220, 255)
    green = (40, 200, 70, 255)
    image = Image.new("RGBA", (10, 10))
    image.putdata(([red] * 49) + ([blue] * 49) + ([green] * 2))
    detected = detect_key_colors_from_image(image)
    assert 0x28C846 not in detected
    assert 0xDC3C3C in detected
    assert 0x466EDC in detected


def test_detect_key_colors_returns_exact_source_colours() -> None:
    colors = [
        (217, 150, 83, 255),
        (95, 164, 233, 255),
        (44, 80, 120, 255),
        (189, 204, 109, 255),
    ]
    image = Image.new("RGBA", (4, 4))
    image.putdata(colors * 4)
    detected = detect_key_colors_from_image(image, max_colors=4)
    valid = {(red << 16) | (green << 8) | blue for red, green, blue, _alpha in colors}
    assert set(detected).issubset(valid)


def test_detect_key_colors_backfills_toward_requested_count() -> None:
    colors = [
        (90, 20, 20, 255),
        (140, 30, 30, 255),
        (190, 45, 45, 255),
        (240, 120, 120, 255),
        (50, 90, 210, 255),
    ]
    image = Image.new("RGBA", (25, 1))
    image.putdata(colors * 5)
    detected = detect_key_colors_from_image(image, max_colors=4)
    valid = {(red << 16) | (green << 8) | blue for red, green, blue, _alpha in colors}
    assert len(detected) == 4
    assert set(detected).issubset(valid)

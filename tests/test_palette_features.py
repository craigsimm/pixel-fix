from pathlib import Path

from pixel_fix.palette.color_modes import convert_mode, extract_unique_colors, to_indexed
from pixel_fix.palette.dither import apply_dither
from pixel_fix.palette.io import load_palette, save_palette
from pixel_fix.palette.quantize import generate_palette, remap_to_palette
from pixel_fix.palette.replace import replace_batch, replace_exact, replace_tolerance


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

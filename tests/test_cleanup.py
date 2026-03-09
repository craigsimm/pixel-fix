from PIL import Image

from pixel_fix.cleanup.components import remove_small_islands
from pixel_fix.cleanup.filters import clean_orphan_pixels, remove_anti_aliased_edges
from pixel_fix.cleanup.line_rules import bridge_single_pixel_gaps


def test_remove_small_island_relabels_singletons():
    grid = [
        [1, 1, 1],
        [1, 2, 1],
        [1, 1, 1],
    ]
    out = remove_small_islands(grid, min_size=2, connectivity=8)
    assert out[1][1] == 1


def test_bridge_single_pixel_gap_fills_line_hole():
    grid = [[3, 0, 3]]
    out = bridge_single_pixel_gaps(grid, target_label=3)
    assert out[0] == [3, 3, 3]


def test_clean_orphan_pixels_relabels_singletons() -> None:
    dark = 0x101010
    light = 0xF0F0F0
    grid = [
        [dark, dark, dark],
        [dark, light, dark],
        [dark, dark, dark],
    ]
    result = clean_orphan_pixels(grid, min_similar_neighbors=1, fill_gaps=False)
    assert result.labels[1][1] == dark
    assert result.orphan_pixels_replaced == 1
    assert result.gap_pixels_filled == 0


def test_clean_orphan_pixels_preserves_endpoint_with_one_similar_neighbour() -> None:
    dark = 0x101010
    light = 0xF0F0F0
    grid = [
        [dark, dark, light],
        [light, light, light],
        [light, light, light],
    ]
    result = clean_orphan_pixels(grid, min_similar_neighbors=1, fill_gaps=False)
    assert result.labels == grid
    assert result.orphan_pixels_replaced == 0


def test_clean_orphan_pixels_fills_single_gap() -> None:
    dark = 0x101010
    light = 0xF0F0F0
    grid = [
        [dark, dark, dark],
        [dark, light, dark],
        [dark, dark, dark],
    ]
    result = clean_orphan_pixels(grid, min_similar_neighbors=0, fill_gaps=True)
    assert result.labels[1][1] == dark
    assert result.orphan_pixels_replaced == 0
    assert result.gap_pixels_filled == 1


def test_remove_anti_aliased_edges_snaps_high_contrast_pixels() -> None:
    image = Image.new("RGBA", (3, 3), (255, 255, 255, 255))
    pixels = image.load()
    for y in range(3):
        pixels[0, y] = (0, 0, 0, 255)
        pixels[1, y] = (0, 0, 0, 255)
    pixels[1, 1] = (32, 32, 32, 128)

    result = remove_anti_aliased_edges(image, alpha_cutoff=224)

    assert result.image.getpixel((1, 1)) == (0, 0, 0, 255)
    assert result.replaced_pixels == 1


def test_remove_anti_aliased_edges_ignores_low_contrast_pixels() -> None:
    image = Image.new("RGBA", (3, 3), (100, 100, 100, 255))
    pixels = image.load()
    pixels[0, 0] = (102, 102, 102, 255)
    pixels[2, 2] = (108, 108, 108, 255)
    pixels[1, 1] = (105, 105, 105, 128)

    result = remove_anti_aliased_edges(image, alpha_cutoff=224)

    assert result.image.getpixel((1, 1)) == (105, 105, 105, 128)
    assert result.replaced_pixels == 0

from pixel_fix.cleanup.components import remove_small_islands
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

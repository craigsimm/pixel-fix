from pixel_fix.cleanup.components import remove_small_islands


def test_remove_small_island_relabels_singletons():
    grid = [
        [1, 1, 1],
        [1, 2, 1],
        [1, 1, 1],
    ]
    out = remove_small_islands(grid, min_size=2, connectivity=8)
    assert out[1][1] == 1

from pixel_fix.pipeline import PipelineConfig, PixelFixPipeline


def test_pipeline_grayscale_and_replacement() -> None:
    labels = [
        [0xFF0000, 0x00FF00],
        [0x0000FF, 0x00FF00],
    ]
    cfg = PipelineConfig(
        grid="divisor",
        pixel_width=1,
        colors=2,
        min_island_size=1,
        input_mode="rgba",
        output_mode="grayscale",
        replace_src=0x959595,
        replace_dst=0x101010,
        replace_tolerance=5,
    )
    out = PixelFixPipeline(cfg).run_on_labels(labels)
    for row in out:
        for v in row:
            r = (v >> 16) & 0xFF
            g = (v >> 8) & 0xFF
            b = v & 0xFF
            assert r == g == b


def test_pipeline_accepts_palette_override() -> None:
    labels = [[0x000000, 0xFFFFFF]]
    cfg = PipelineConfig(grid="divisor", pixel_width=1, colors=2, min_island_size=1)
    out = PixelFixPipeline(cfg).run_on_labels(labels, palette_override=[0x123456])
    assert out == [[0x123456, 0x123456]]

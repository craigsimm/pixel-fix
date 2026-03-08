from pixel_fix.pipeline import PipelineConfig, PixelFixPipeline


def test_pipeline_grayscale_output() -> None:
    labels = [
        [0xFF0000, 0x00FF00],
        [0x0000FF, 0x00FF00],
    ]
    out = PixelFixPipeline(
        PipelineConfig(
            pixel_width=1,
            colors=2,
            input_mode="rgba",
            output_mode="grayscale",
        )
    ).run_on_labels(labels)
    for row in out:
        for value in row:
            r = (value >> 16) & 0xFF
            g = (value >> 8) & 0xFF
            b = value & 0xFF
            assert r == g == b


def test_pipeline_accepts_palette_override() -> None:
    labels = [[0x000000, 0xFFFFFF]]
    out = PixelFixPipeline(PipelineConfig(pixel_width=1, colors=2)).run_on_labels(labels, palette_override=[0x123456])
    assert out == [[0x123456, 0x123456]]

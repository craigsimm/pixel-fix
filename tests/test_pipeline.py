from pixel_fix.pipeline import PipelineConfig, PixelFixPipeline


def test_run_on_labels_reduces_to_palette_budget():
    labels = [
        [0, 1, 2, 3],
        [0, 1, 2, 3],
        [4, 5, 6, 7],
        [4, 5, 6, 7],
    ]
    cfg = PipelineConfig(grid="divisor", pixel_width=2, colors=2, min_island_size=1)
    pipeline = PixelFixPipeline(cfg)
    out = pipeline.run_on_labels(labels)
    colors = {value for row in out for value in row}
    assert len(colors) <= 2

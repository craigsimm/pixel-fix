from pixel_fix.pipeline import PipelineConfig, PixelFixPipeline


def test_prepare_labels_uses_manual_pixel_size_and_resize_mode():
    labels = [
        [0, 1, 2, 3],
        [0, 1, 2, 3],
        [4, 5, 6, 7],
        [4, 5, 6, 7],
    ]
    prepared = PixelFixPipeline(PipelineConfig(pixel_width=2, downsample_mode="nearest")).prepare_labels(labels)
    assert prepared.pixel_width == 2
    assert prepared.grid_method == "manual"
    assert prepared.input_size == (4, 4)
    assert len(prepared.reduced_labels) == 2
    assert len(prepared.reduced_labels[0]) == 2


def test_run_on_labels_reduces_to_palette_budget():
    labels = [
        [0, 1, 2, 3],
        [0, 1, 2, 3],
        [4, 5, 6, 7],
        [4, 5, 6, 7],
    ]
    out = PixelFixPipeline(PipelineConfig(pixel_width=2, colors=2)).run_on_labels(labels)
    colors = {value for row in out for value in row}
    assert len(colors) <= 2

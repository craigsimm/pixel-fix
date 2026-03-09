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
    assert prepared.anti_alias_pixels_fixed == 0
    assert prepared.orphan_pixels_replaced == 0
    assert prepared.gap_pixels_filled == 0


def test_prepare_labels_applies_orphan_cleanup_and_reports_counts():
    dark = 0x101010
    light = 0xF0F0F0
    labels = [
        [dark, dark, dark],
        [dark, light, dark],
        [dark, dark, dark],
    ]
    prepared = PixelFixPipeline(
        PipelineConfig(
            pixel_width=1,
            orphan_cleanup_enabled=True,
            orphan_min_similar_neighbors=1,
            orphan_fill_gaps=False,
        )
    ).prepare_labels(labels)
    assert prepared.reduced_labels[1][1] == dark
    assert prepared.orphan_pixels_replaced == 1
    assert prepared.gap_pixels_filled == 0
    assert prepared.anti_alias_pixels_fixed == 0


def test_run_on_labels_uses_generated_palette_size():
    labels = [
        [0, 1, 2, 3],
        [0, 1, 2, 3],
        [4, 5, 6, 7],
        [4, 5, 6, 7],
    ]
    result = PixelFixPipeline(
        PipelineConfig(pixel_width=2, key_colors=(0, 4), generated_shades=2)
    ).run_on_labels_detailed(labels)
    assert result.structured_palette is not None
    assert result.structured_palette.generated_shades == 2
    assert result.structured_palette.key_colors == [0, 4]
    assert result.effective_palette_size == 6
    output_colors = {value for row in result.labels for value in row}
    assert output_colors.issubset(set(result.structured_palette.labels()))


def test_run_on_labels_returns_structured_palette_metadata():
    labels = [
        [0xFF0000, 0xFF0000, 0x0000FF],
        [0xFF0000, 0x00FF00, 0x0000FF],
        [0xFFFF00, 0x00FF00, 0x0000FF],
    ]
    result = PixelFixPipeline(
        PipelineConfig(pixel_width=1, key_colors=(0xFF0000, 0x00FF00, 0x0000FF), generated_shades=2)
    ).run_on_labels_detailed(labels)
    assert result.structured_palette is not None
    assert result.structured_palette.source_mode == "advanced"
    assert result.histogram_size == 4
    assert result.seed_count == len(result.structured_palette.key_colors)
    assert result.ramp_count == len(result.structured_palette.ramps)
    assert result.effective_palette_size == result.structured_palette.palette_size()


def test_run_on_labels_carries_cleanup_counts_into_result():
    dark = 0x101010
    light = 0xF0F0F0
    labels = [
        [dark, dark, dark],
        [dark, light, dark],
        [dark, dark, dark],
    ]
    result = PixelFixPipeline(
        PipelineConfig(
            pixel_width=1,
            orphan_cleanup_enabled=True,
            orphan_min_similar_neighbors=1,
            orphan_fill_gaps=False,
            palette_strategy="override",
        )
    ).run_on_labels_detailed(labels, palette_override=[dark])
    assert result.orphan_pixels_replaced == 1
    assert result.removed_isolated_pixels == 1
    assert result.gap_pixels_filled == 0

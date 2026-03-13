import json

import pytest
from PIL import Image

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


def test_run_file_processes_png_and_preserves_alpha(tmp_path):
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    palette_path = tmp_path / "palette.json"
    palette_path.write_text(json.dumps({"palette": ["#ff0000", "#00ff00"]}), encoding="utf-8")

    source = Image.new("RGBA", (2, 2))
    source.putdata([
        (255, 0, 0, 255),
        (0, 0, 255, 255),
        (0, 255, 0, 128),
        (255, 255, 255, 0),
    ])
    source.save(input_path, format="PNG")

    pipeline = PixelFixPipeline(PipelineConfig(pixel_width=1, palette_path=palette_path, overwrite=True))
    pipeline.run_file(input_path, output_path)

    with Image.open(output_path) as output:
        rendered = output.convert("RGBA")
        assert rendered.size == (2, 2)
        assert rendered.getpixel((1, 1))[3] == 0


def test_run_file_keeps_output_overwrite_check(tmp_path):
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    Image.new("RGBA", (1, 1), (255, 0, 0, 255)).save(input_path, format="PNG")
    output_path.write_bytes(b"existing")

    pipeline = PixelFixPipeline(PipelineConfig(pixel_width=1, overwrite=False))
    with pytest.raises(FileExistsError):
        pipeline.run_file(input_path, output_path)


def test_run_file_with_progress_reports_updates(tmp_path):
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    Image.new("RGBA", (1, 1), (128, 64, 32, 255)).save(input_path, format="PNG")

    updates: list[tuple[int, str]] = []
    pipeline = PixelFixPipeline(PipelineConfig(pixel_width=1, overwrite=True))
    pipeline.run_file_with_progress(input_path, output_path, progress_callback=lambda p, m: updates.append((p, m)))

    assert output_path.exists()
    assert updates
    assert updates[-1][0] == 100

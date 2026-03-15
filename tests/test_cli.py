from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
import pytest

import pixel_fix.cli_workflow as workflow
from pixel_fix.cli import build_parser, main
from pixel_fix.cli_workflow import CliJobError, apply_job_overrides, load_job_spec, resolve_builtin_palette, run_batch_job, run_process_job
from pixel_fix.gui.processing import downsample_image, image_to_rgb_grid, load_png_rgba_image, reduce_palette_image
from pixel_fix.palette.io import load_palette, save_palette
from pixel_fix.palette.workspace import ColorWorkspace


def _write_png(path: Path, pixels: list[tuple[int, int, int, int]], size: tuple[int, int]) -> None:
    image = Image.new("RGBA", size)
    image.putdata(pixels)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def _write_jpeg(path: Path, pixels: list[tuple[int, int, int]], size: tuple[int, int]) -> None:
    image = Image.new("RGB", size)
    image.putdata(pixels)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="JPEG")


def _write_gpl(path: Path, colors: list[int]) -> None:
    save_palette(path, colors)


def test_cli_parser_accepts_process_batch_and_config_init() -> None:
    parser = build_parser()

    process_args = parser.parse_args(["process", "in.png", "out.png"])
    assert process_args.command == "process"
    assert process_args.input == Path("in.png")
    assert process_args.output == Path("out.png")
    quantizer_args = parser.parse_args(["process", "in.png", "out.png", "--quantizer", "rampforge-8"])
    assert quantizer_args.quantizer == "rampforge-8"

    batch_args = parser.parse_args(["batch", "inputs", "outputs"])
    assert batch_args.command == "batch"
    assert batch_args.input_dir == Path("inputs")
    assert batch_args.output_dir == Path("outputs")

    config_args = parser.parse_args(["config", "init", "job.json"])
    assert config_args.command == "config"
    assert config_args.config_command == "init"
    assert config_args.path == Path("job.json")


def test_legacy_cli_route_processes_image_and_warns(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    input_path = tmp_path / "input.jpg"
    output_path = tmp_path / "output.png"
    _write_jpeg(
        input_path,
        [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)],
        (2, 2),
    )

    code = main([str(input_path), str(output_path), "--pixel-size", "1", "--overwrite"])

    assert code == 0
    assert "Deprecation warning" in capsys.readouterr().err
    with Image.open(output_path) as output_image:
        assert output_image.format == "PNG"
        assert output_image.size == (2, 2)


def test_cli_overrides_beat_json_config(tmp_path: Path) -> None:
    config_path = tmp_path / "job.json"
    config_path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "pixel_width": 5,
                    "palette_reduction_colors": 3,
                    "quantizer": "kmeans",
                }
            }
        ),
        encoding="utf-8",
    )

    job = load_job_spec(config_path)
    overridden = apply_job_overrides(job, pixel_width=2, palette_reduction_colors=8, quantizer="topk")
    rampforge = apply_job_overrides(job, quantizer="rampforge-8")

    assert overridden.settings.pixel_width == 2
    assert overridden.settings.palette_reduction_colors == 8
    assert overridden.settings.quantizer == "median-cut"
    assert rampforge.settings.quantizer == "rampforge-8"


def test_resolve_builtin_palette_uses_catalog_relative_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    palette_root = tmp_path / "palettes" / "dawn"
    palette_root.mkdir(parents=True)
    _write_gpl(palette_root / "db16.gpl", [0x112233, 0xABCDEF])
    monkeypatch.setattr(workflow, "_resource_path", lambda name: tmp_path / name)

    entry = resolve_builtin_palette("dawn/db16.gpl")

    assert list(entry.colors) == [0x112233, 0xABCDEF]


def test_invalid_step_type_fails_with_clear_error(tmp_path: Path) -> None:
    config_path = tmp_path / "job.json"
    config_path.write_text(
        json.dumps(
            {
                "palette_steps": [{"type": "not-a-real-step"}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(CliJobError, match="palette_steps\\[0\\]\\.type"):
        load_job_spec(config_path)


def test_selection_dependent_operation_fails_cleanly(tmp_path: Path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    _write_png(
        input_path,
        [
            (0, 0, 0, 255),
            (255, 0, 0, 255),
            (0, 255, 0, 255),
            (0, 0, 255, 255),
        ],
        (2, 2),
    )
    config_path = tmp_path / "job.json"
    config_path.write_text(
        json.dumps(
            {
                "palette_steps": [{"type": "merge_selected"}],
            }
        ),
        encoding="utf-8",
    )
    job = load_job_spec(config_path)

    with pytest.raises(CliJobError, match="merge_selected requires 2 or more selected colours"):
        run_process_job(input_path, output_path, job, overwrite=True)


def test_process_job_matches_direct_headless_pipeline(tmp_path: Path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    _write_png(
        input_path,
        [
            (255, 0, 0, 255),
            (255, 0, 0, 255),
            (0, 0, 255, 255),
            (0, 0, 255, 255),
            (255, 0, 0, 255),
            (255, 0, 0, 255),
            (0, 0, 255, 255),
            (0, 0, 255, 255),
            (0, 255, 0, 255),
            (0, 255, 0, 255),
            (255, 255, 0, 255),
            (255, 255, 0, 255),
            (0, 255, 0, 255),
            (0, 255, 0, 255),
            (255, 255, 0, 255),
            (255, 255, 0, 255),
        ],
        (4, 4),
    )
    config_path = tmp_path / "job.json"
    config_path.write_text(json.dumps({"pipeline": {"pixel_width": 2}}), encoding="utf-8")
    job = load_job_spec(config_path)

    run_process_job(input_path, output_path, job, overwrite=True)

    image = load_png_rgba_image(str(input_path))
    grid = image_to_rgb_grid(image)
    downsampled = downsample_image(grid, workflow._build_pipeline_config(job.settings))
    palette_source = workflow._load_initial_palette(job, downsampled.prepared_input.reduced_labels)
    result = reduce_palette_image(
        downsampled.prepared_input,
        workflow._build_pipeline_config(job.settings, palette_size=len(palette_source.labels)),
        palette_override=palette_source.labels,
        structured_palette=palette_source.structured_palette,
    )
    expected = workflow.process_result_to_rgba_image(result)
    with Image.open(output_path) as actual:
        assert list(actual.getdata()) == list(expected.getdata())


def test_process_job_accepts_rampforge_8_quantizer(tmp_path: Path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    _write_png(
        input_path,
        [
            (170, 85, 51, 255),
            (170, 85, 51, 255),
            (68, 119, 170, 255),
            (68, 119, 170, 255),
            (85, 170, 85, 255),
            (85, 170, 85, 255),
            (170, 51, 85, 255),
            (170, 51, 85, 255),
        ],
        (4, 2),
    )
    config_path = tmp_path / "job.json"
    config_path.write_text(
        json.dumps({"pipeline": {"pixel_width": 1, "palette_reduction_colors": 2, "quantizer": "rampforge-8"}}),
        encoding="utf-8",
    )
    job = load_job_spec(config_path)

    image = load_png_rgba_image(str(input_path))
    grid = image_to_rgb_grid(image)
    downsampled = downsample_image(grid, workflow._build_pipeline_config(job.settings))
    source = workflow._load_initial_palette(job, downsampled.prepared_input.reduced_labels, workspace=ColorWorkspace())

    assert source.structured_palette is not None
    assert source.structured_palette.source_mode == "rampforge-8"

    run_process_job(input_path, output_path, job, overwrite=True)

    assert output_path.exists()


def test_transparency_fill_preserves_alpha_in_saved_png(tmp_path: Path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    _write_png(
        input_path,
        [
            (255, 0, 0, 255),
            (0, 255, 0, 255),
            (0, 0, 255, 255),
        ],
        (3, 1),
    )
    config_path = tmp_path / "job.json"
    config_path.write_text(
        json.dumps({"pipeline": {"pixel_width": 1}, "image_steps": [{"type": "make_transparent_fill", "x": 0, "y": 0}]}),
        encoding="utf-8",
    )
    job = load_job_spec(config_path)

    run_process_job(input_path, output_path, job, overwrite=True)

    with Image.open(output_path) as output:
        assert output.getpixel((0, 0))[3] == 0
        assert output.getpixel((1, 0))[3] == 255
        assert output.getpixel((2, 0))[3] == 255


def test_palette_outline_step_works_headlessly(tmp_path: Path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    palette_path = tmp_path / "palette.gpl"
    _write_png(
        input_path,
        [
            (0, 0, 0, 255),
            (0, 0, 0, 255),
            (0, 0, 0, 255),
            (0, 0, 0, 255),
            (102, 153, 204, 255),
            (0, 0, 0, 255),
            (0, 0, 0, 255),
            (0, 0, 0, 255),
            (0, 0, 0, 255),
        ],
        (3, 3),
    )
    _write_gpl(palette_path, [0x000000, 0x6699CC, 0x112233])
    config_path = tmp_path / "job.json"
    config_path.write_text(
        json.dumps(
            {
                "pipeline": {"pixel_width": 1},
                "palette_source": {"type": "file", "path": str(palette_path)},
                "palette_steps": [{"type": "select_indices", "indices": [2]}],
                "image_steps": [
                    {"type": "make_transparent_fill", "x": 0, "y": 0},
                    {"type": "add_outline", "colour_mode": "palette", "pixel_perfect": False},
                ],
            }
        ),
        encoding="utf-8",
    )
    job = load_job_spec(config_path)

    run_process_job(input_path, output_path, job, overwrite=True)

    with Image.open(output_path) as output:
        assert output.getpixel((1, 0))[3] == 255
        assert output.getpixel((1, 0))[:3] == (0x11, 0x22, 0x33)


def test_adaptive_outline_can_append_generated_palette_colours(tmp_path: Path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    palette_path = tmp_path / "palette.gpl"
    saved_palette_path = tmp_path / "result.gpl"
    _write_png(
        input_path,
        [
            (0, 0, 0, 255),
            (0, 0, 0, 255),
            (0, 0, 0, 255),
            (0, 0, 0, 255),
            (102, 153, 204, 255),
            (0, 0, 0, 255),
            (0, 0, 0, 255),
            (0, 0, 0, 255),
            (0, 0, 0, 255),
        ],
        (3, 3),
    )
    _write_gpl(palette_path, [0x000000, 0x6699CC])
    config_path = tmp_path / "job.json"
    config_path.write_text(
        json.dumps(
            {
                "pipeline": {"pixel_width": 1},
                "palette_source": {"type": "file", "path": str(palette_path)},
                "image_steps": [
                    {"type": "make_transparent_fill", "x": 0, "y": 0},
                    {
                        "type": "add_outline",
                        "colour_mode": "adaptive",
                        "pixel_perfect": False,
                        "adaptive_darken_percent": 60,
                        "add_generated_colours": True,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    job = load_job_spec(config_path)

    run_process_job(input_path, output_path, job, overwrite=True, palette_output_path=saved_palette_path)

    with Image.open(output_path) as output:
        assert output.getpixel((1, 0))[3] == 255
        assert output.getpixel((1, 0))[:3] != (0x66, 0x99, 0xCC)
    saved_palette = load_palette(saved_palette_path)
    assert 0x6699CC in saved_palette
    assert len(saved_palette) > 2


def test_remove_outline_threshold_filters_saved_output(tmp_path: Path) -> None:
    input_path = tmp_path / "input.png"
    output_path = tmp_path / "output.png"
    palette_path = tmp_path / "palette.gpl"
    _write_png(
        input_path,
        [
            (0, 0, 0, 255), (0, 0, 0, 255), (0, 0, 0, 255), (0, 0, 0, 255), (0, 0, 0, 255),
            (0, 0, 0, 255), (32, 32, 32, 255), (32, 32, 32, 255), (32, 32, 32, 255), (0, 0, 0, 255),
            (0, 0, 0, 255), (224, 224, 224, 255), (128, 128, 128, 255), (224, 224, 224, 255), (0, 0, 0, 255),
            (0, 0, 0, 255), (224, 224, 224, 255), (224, 224, 224, 255), (224, 224, 224, 255), (0, 0, 0, 255),
            (0, 0, 0, 255), (0, 0, 0, 255), (0, 0, 0, 255), (0, 0, 0, 255), (0, 0, 0, 255),
        ],
        (5, 5),
    )
    _write_gpl(palette_path, [0x000000, 0x202020, 0x808080, 0xE0E0E0])
    config_path = tmp_path / "job.json"
    config_path.write_text(
        json.dumps(
                {
                    "pipeline": {"pixel_width": 1},
                    "palette_source": {"type": "file", "path": str(palette_path)},
                    "image_steps": [
                    {"type": "make_transparent_fill", "x": 0, "y": 0},
                    {
                        "type": "remove_outline",
                        "pixel_perfect": False,
                        "brightness_threshold": {"enabled": True, "percent": 40, "direction": "dark"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    job = load_job_spec(config_path)

    run_process_job(input_path, output_path, job, overwrite=True)

    with Image.open(output_path) as output:
        assert output.getpixel((1, 1))[3] == 0
        assert output.getpixel((2, 1))[3] == 0
        assert output.getpixel((3, 1))[3] == 0
        assert output.getpixel((1, 2))[3] == 255


def test_batch_processing_mirrors_tree_and_reports_failures(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    output_dir = tmp_path / "outputs"
    _write_png(input_dir / "good.png", [(255, 0, 0, 255)], (1, 1))
    _write_png(input_dir / "nested" / "also-good.png", [(0, 255, 0, 255)], (1, 1))
    (input_dir / "bad.png").write_text("not a real png", encoding="utf-8")
    job = load_job_spec(None, cwd=tmp_path)

    result = run_batch_job(input_dir, output_dir, job, overwrite=True)

    assert result.processed == 2
    assert result.failed == 1
    assert (output_dir / "good.png").exists()
    assert (output_dir / "nested" / "also-good.png").exists()
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["failed"] == 1
    assert any(file_report["status"] == "error" for file_report in report["files"])


def test_batch_fail_fast_stops_after_first_error(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    output_dir = tmp_path / "outputs"
    (input_dir / "a-bad.png").parent.mkdir(parents=True, exist_ok=True)
    (input_dir / "a-bad.png").write_text("not a real png", encoding="utf-8")
    _write_png(input_dir / "b-good.png", [(255, 0, 0, 255)], (1, 1))
    job = load_job_spec(None, cwd=tmp_path)

    result = run_batch_job(input_dir, output_dir, job, overwrite=True, fail_fast=True)

    assert result.processed == 0
    assert result.failed == 1
    assert not (output_dir / "b-good.png").exists()

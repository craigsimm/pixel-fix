from __future__ import annotations

<<<<<<< ours
<<<<<<< ours
import json
from pathlib import Path

<<<<<<< ours
import pytest
from PIL import Image

from pixel_fix import cli
from pixel_fix.gui.processing import ProcessResult, ProcessStats, image_to_rgb_grid, load_png_rgba_image, remove_exterior_outline
from pixel_fix.pipeline import PipelineConfig, PipelinePreparedResult


def _write_png(path: Path, *, color: tuple[int, int, int, int] = (255, 0, 0, 255), size: tuple[int, int] = (3, 3)) -> None:
    image = Image.new("RGBA", size, color)
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        image.convert("RGB").save(path)
    else:
        image.save(path)


def _alpha_values(path: Path) -> list[int]:
    with Image.open(path) as image:
        return [alpha for *_rgb, alpha in image.convert("RGBA").getdata()]


def test_parser_defaults_and_required_positional_arguments() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["process", "input.png", "output.png"])

    assert args.input == Path("input.png")
    assert args.output == Path("output.png")
    assert args.pixel_size == 1
    assert args.downsample_mode == "nearest"
    assert args.colors == 16
    assert args.input_mode == "rgba"
    assert args.output_mode == "rgba"
    assert args.quantizer == "topk"
    assert args.dither == "none"
    assert args.outline_threshold == 0


def test_parser_rejects_invalid_choice() -> None:
    parser = cli.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["process", "in.png", "out.png", "--downsample-mode", "bad"])


def test_process_creates_output_file(tmp_path: Path) -> None:
    source = tmp_path / "in.png"
    output = tmp_path / "out.png"
    _write_png(source)

    code = cli.main(["process", str(source), str(output)])

    assert code == 0
    assert output.exists()
    assert output.read_bytes() == source.read_bytes()


@pytest.mark.parametrize(
    ("mode", "expect_exists", "expect_error"),
    [
        ("overwrite", True, None),
        ("skip", True, None),
        ("fail", True, FileExistsError),
    ],
)
def test_process_conflict_modes(tmp_path: Path, mode: str, expect_exists: bool, expect_error: type[Exception] | None) -> None:
    source = tmp_path / "in.png"
    output = tmp_path / "out.png"
    _write_png(source, color=(1, 2, 3, 255))
    _write_png(output, color=(9, 9, 9, 255))
    before = output.read_bytes()

    if expect_error is not None:
        with pytest.raises(expect_error):
            cli.main(["process", str(source), str(output), "--conflict", mode])
        assert output.read_bytes() == before
        return

    code = cli.main(["process", str(source), str(output), "--conflict", mode])
    assert code == 0
    if mode == "overwrite":
        assert output.read_bytes() == source.read_bytes()
    else:
        assert output.read_bytes() == before
    assert output.exists() is expect_exists


def test_process_loads_settings_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "in.png"
    output = tmp_path / "out.png"
    settings_path = tmp_path / "settings.json"
    _write_png(source)
    settings_path.write_text(json.dumps({"palette_strategy": "override", "generated_shades": 2}), encoding="utf-8")

    captured: dict[str, PipelineConfig] = {}

    class FakePipeline:
        def __init__(self, config: PipelineConfig):
            captured["config"] = config

        def run_file(self, _in: Path, out: Path) -> None:
            out.write_bytes(source.read_bytes())

    monkeypatch.setattr(cli, "PixelFixPipeline", FakePipeline)

    cli.main(["process", str(source), str(output), "--settings", str(settings_path)])

    assert captured["config"].palette_strategy == "override"
    assert captured["config"].generated_shades == 2


def test_batch_discovers_files_by_glob_and_recursive(tmp_path: Path) -> None:
    input_root = tmp_path / "in"
    output_root = tmp_path / "out"
    nested = input_root / "nested"
    nested.mkdir(parents=True)
    _write_png(input_root / "a.png")
    _write_png(nested / "b.png")
    _write_png(input_root / "c.jpg")

    cli.main(["batch", str(input_root), str(output_root), "--glob", "*.png"])
    assert (output_root / "a.png").exists()
    assert not (output_root / "nested" / "b.png").exists()

    cli.main(["batch", str(input_root), str(output_root), "--glob", "*.png", "--recursive", "--conflict", "overwrite"])
    assert (output_root / "nested" / "b.png").exists()


def test_batch_continue_on_error_and_report_generation(tmp_path: Path) -> None:
    input_root = tmp_path / "in"
    output_root = tmp_path / "out"
    report = tmp_path / "report.json"
    input_root.mkdir()
    good = input_root / "good.png"
    bad = input_root / "bad.png"
    _write_png(good)
    bad.write_bytes(b"not-an-image")

    code = cli.main(
        [
            "batch",
            str(input_root),
            str(output_root),
            "--continue-on-error",
            "--report",
            str(report),
            "--glob",
            "*.png",
        ]
    )

    assert code == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["discovered"] == 2
    assert data["processed"] == 1
    assert data["failed"] == 1
    assert data["errors"]


def test_batch_stops_on_error_without_continue_flag(tmp_path: Path) -> None:
    input_root = tmp_path / "in"
    output_root = tmp_path / "out"
    input_root.mkdir()
    _write_png(input_root / "ok.png")
    (input_root / "broken.png").write_bytes(b"invalid")

    with pytest.raises(Exception):
        cli.main(["batch", str(input_root), str(output_root), "--glob", "*.png"])


def test_outline_threshold_regression_matches_remove_exterior_outline(tmp_path: Path) -> None:
    output = tmp_path / "outlined.png"
    image = Image.new("RGBA", (5, 5), (0, 0, 0, 0))
    for y in range(1, 4):
        for x in range(1, 4):
            image.putpixel((x, y), (200, 40, 40, 255))
    image.save(output)

    source_rgba = load_png_rgba_image(str(output))
    source_grid = image_to_rgb_grid(source_rgba)
    result = ProcessResult(
        grid=source_grid,
        width=source_rgba.width,
        height=source_rgba.height,
        prepared_input=PipelinePreparedResult(
            reduced_labels=[],
            pixel_width=1,
            grid_method="manual",
            input_size=(source_rgba.width, source_rgba.height),
            initial_color_count=0,
        ),
        stats=ProcessStats(
            stage="test",
            pixel_width=1,
            resize_method="nearest",
            input_size=(source_rgba.width, source_rgba.height),
            output_size=(source_rgba.width, source_rgba.height),
            initial_color_count=0,
            color_count=0,
            elapsed_seconds=0.0,
        ),
    )
    _updated, changed = remove_exterior_outline(result)
    assert changed > 0

    before = _alpha_values(output)
    skipped = cli._apply_thresholded_outline_removal(output, threshold=changed + 1)
    assert skipped == 0
    assert _alpha_values(output) == before

    applied = cli._apply_thresholded_outline_removal(output, threshold=changed)
    assert applied == changed
    assert any(alpha == 0 for alpha in _alpha_values(output))
=======
from pixel_fix import cli


def _run_cli(monkeypatch, argv: list[str]) -> int:
    monkeypatch.setattr("sys.argv", ["pixel-fix", *argv])
    return cli.main()


def test_cli_writes_summary_report_and_succeeds_for_batch(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    report_path = tmp_path / "report.json"
    input_dir.mkdir()
    (input_dir / "a.png").write_bytes(b"a")
    (input_dir / "b.jpg").write_bytes(b"b")

    exit_code = _run_cli(
        monkeypatch,
        [str(input_dir), str(output_dir), "--report-json", str(report_path)],
    )

    assert exit_code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["summary"]["total_files_discovered"] == 2
    assert report["summary"]["processed_count"] == 2
    assert report["summary"]["skipped_count"] == 0
    assert report["summary"]["failed_count"] == 0
    assert len(report["files"]) == 2
    assert all("error_reason" not in item for item in report["files"])


def test_cli_failed_items_include_error_details_only_in_verbose(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    report_default = tmp_path / "report-default.json"
    report_verbose = tmp_path / "report-verbose.json"
    input_dir.mkdir()
    (input_dir / "ok.png").write_bytes(b"ok")
    (input_dir / "bad.bmp").write_bytes(b"bad")

    # Force discovery to include an unsupported extension file to exercise failure path.
    monkeypatch.setattr(cli, "_discover_inputs", lambda _path: [input_dir / "ok.png", input_dir / "bad.bmp"])

    exit_code = _run_cli(
        monkeypatch,
        [str(input_dir), str(output_dir), "--continue-on-error", "--report-json", str(report_default)],
    )
    assert exit_code == 1
    default_report = json.loads(report_default.read_text(encoding="utf-8"))
    failed_default = [item for item in default_report["files"] if item["status"] == "failed"]
    assert len(failed_default) == 1
    assert "error_reason" not in failed_default[0]
    assert "traceback" not in failed_default[0]

    exit_code_verbose = _run_cli(
        monkeypatch,
        [
            str(input_dir),
            str(output_dir),
            "--continue-on-error",
            "--verbose",
            "--report-json",
            str(report_verbose),
        ],
    )
    assert exit_code_verbose == 1
    verbose_report = json.loads(report_verbose.read_text(encoding="utf-8"))
    failed_verbose = [item for item in verbose_report["files"] if item["status"] == "failed"]
    assert len(failed_verbose) == 1
    assert "error_reason" in failed_verbose[0]
    assert "Unsupported input extension" in failed_verbose[0]["error_reason"]
    assert "traceback" in failed_verbose[0]


def test_cli_exit_code_obeys_continue_on_error(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    report_stop = tmp_path / "report-stop.json"
    report_continue = tmp_path / "report-continue.json"
    input_dir.mkdir()
    (input_dir / "a.png").write_bytes(b"a")
    (input_dir / "bad.bmp").write_bytes(b"bad")
    (input_dir / "c.png").write_bytes(b"c")

    monkeypatch.setattr(
        cli,
        "_discover_inputs",
        lambda _path: [input_dir / "a.png", input_dir / "bad.bmp", input_dir / "c.png"],
    )

    exit_code_stop = _run_cli(monkeypatch, [str(input_dir), str(output_dir), "--report-json", str(report_stop)])
    assert exit_code_stop == 1
    report_without_continue = json.loads(report_stop.read_text(encoding="utf-8"))
    assert len(report_without_continue["files"]) == 2
    assert report_without_continue["summary"]["processed_count"] == 1
    assert report_without_continue["summary"]["failed_count"] == 1

    exit_code_continue = _run_cli(
        monkeypatch,
        [str(input_dir), str(output_dir), "--continue-on-error", "--overwrite", "--report-json", str(report_continue)],
    )
    assert exit_code_continue == 1
    report_with_continue = json.loads(report_continue.read_text(encoding="utf-8"))
    assert len(report_with_continue["files"]) == 3
    assert report_with_continue["summary"]["processed_count"] == 2
    assert report_with_continue["summary"]["failed_count"] == 1
>>>>>>> theirs
=======
from pixel_fix.cli import apply_cli_post_processing
from pixel_fix.gui.processing import ProcessResult, ProcessStats
from pixel_fix.pipeline import PipelinePreparedResult


def _result_from_labels(labels: list[list[int]]) -> ProcessResult:
    grid = [[((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF) for value in row] for row in labels]
    height = len(grid)
    width = len(grid[0]) if height else 0
    prepared = PipelinePreparedResult(
        reduced_labels=labels,
        pixel_width=1,
        grid_method="manual",
        input_size=(width, height),
        initial_color_count=len({value for row in labels for value in row}),
    )
    return ProcessResult(
        grid=grid,
        width=width,
        height=height,
        stats=ProcessStats(
            stage="palette",
            pixel_width=1,
            resize_method="nearest",
            input_size=(width, height),
            output_size=(width, height),
            initial_color_count=prepared.initial_color_count,
            color_count=prepared.initial_color_count,
            elapsed_seconds=0.0,
        ),
        prepared_input=prepared,
    )


def test_apply_cli_post_processing_reports_operation_counts() -> None:
    result = _result_from_labels(
        [
            [0x000000, 0x000000, 0x000000],
            [0x000000, 0x778899, 0x000000],
            [0x000000, 0x000000, 0x000000],
        ]
    )

    _, summaries = apply_cli_post_processing(
        result,
        transparent_labels={0x000000},
        add_outline_label=0x112233,
        remove_outline=False,
        outline_pixel_perfect=True,
        outline_brightness_threshold=255,
    )

    assert [summary.name for summary in summaries] == ["transparency", "add_outline"]
    assert summaries[0].pixels_changed == 8
    assert summaries[1].pixels_changed == 4
>>>>>>> theirs
=======
from pathlib import Path

from pixel_fix import cli


def test_implicit_process_mode_still_works(tmp_path: Path) -> None:
    input_path = tmp_path / "in.png"
    output_path = tmp_path / "out.png"
    input_path.write_bytes(b"fake")

    exit_code = cli.main([str(input_path), str(output_path)])

    assert exit_code == 0
    assert output_path.exists()


def test_batch_returns_non_zero_on_failure(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    output_dir = tmp_path / "outputs"
    input_dir.mkdir()
    (input_dir / "ok.png").write_bytes(b"ok")

    exit_code = cli.main([
        "batch",
        "--input-dir",
        str(input_dir),
        "--output-dir",
        str(output_dir),
        "--glob",
        "*.txt",
    ])

    assert exit_code == 0

    exit_code = cli.main([
        "batch",
        "--input-dir",
        str(input_dir),
        "--output-dir",
        str(output_dir),
    ])

    assert exit_code == 0

    (output_dir / "ok.png").write_bytes(b"existing")
    exit_code = cli.main([
        "batch",
        "--input-dir",
        str(input_dir),
        "--output-dir",
        str(output_dir),
    ])
    assert exit_code == 1


def test_batch_continue_on_error_returns_zero(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    output_dir = tmp_path / "outputs"
    input_dir.mkdir()
    (input_dir / "bad.txt").write_bytes(b"bad")

    exit_code = cli.main([
        "batch",
        "--input-dir",
        str(input_dir),
        "--output-dir",
        str(output_dir),
        "--continue-on-error",
    ])

    assert exit_code == 0
>>>>>>> theirs

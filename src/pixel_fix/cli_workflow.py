from __future__ import annotations

import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from PIL import Image

from pixel_fix.gui.persist import deserialize_settings
from pixel_fix.gui.processing import (
    OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK,
    OUTLINE_REMOVE_BRIGHTNESS_THRESHOLD_DEFAULT,
    ProcessResult,
    add_exterior_outline,
    apply_transparency_fill,
    downsample_image,
    image_to_rgb_grid,
    load_png_rgba_image,
    remove_exterior_outline,
    reduce_palette_image,
)
from pixel_fix.gui.state import PreviewSettings
from pixel_fix.io import validate_input_path, validate_output_path
from pixel_fix.palette.adjust import PaletteAdjustments, adjust_palette_labels
from pixel_fix.palette.catalog import PaletteCatalogEntry, discover_palette_catalog
from pixel_fix.palette.edit import generate_ramp_palette_labels, merge_palette_labels
from pixel_fix.palette.io import load_palette, save_palette
from pixel_fix.palette.quantize import generate_palette
from pixel_fix.palette.sort import (
    PALETTE_SELECT_MODES,
    PALETTE_SORT_MODES,
    select_palette_indices,
    sort_palette_labels,
)
from pixel_fix.palette.workspace import ColorWorkspace
from pixel_fix.pipeline import PipelineConfig

ALLOWED_DOWNSAMPLE_MODES = {"nearest", "bilinear", "rotsprite"}
ALLOWED_PALETTE_DITHER_MODES = {"none", "ordered", "blue-noise"}
ALLOWED_COLOR_MODES = {"rgba", "indexed", "grayscale"}
ALLOWED_QUANTIZERS = {"median-cut", "kmeans"}
ALLOWED_OUTLINE_COLOUR_MODES = {"palette", "adaptive"}
ALLOWED_BRIGHTNESS_DIRECTIONS = {"dark", "bright"}
ALLOWED_PALETTE_EXPORT_FORMATS = {"gpl", "json"}
PALETTE_STEP_TYPES = {
    "select",
    "select_indices",
    "select_all",
    "clear_selection",
    "sort",
    "merge_selected",
    "ramp_selected",
    "remove_selected",
    "add_colors",
    "adjust_palette",
}
IMAGE_STEP_TYPES = {"make_transparent_fill", "add_outline", "remove_outline"}
DEFAULT_BATCH_GLOB = "*.png"
DEFAULT_BATCH_REPORT_NAME = "pixel-fix-batch-report.json"


class CliJobError(ValueError):
    pass


@dataclass(frozen=True)
class PaletteSourceSpec:
    type: str = "generate"
    path: str | None = None


@dataclass(frozen=True)
class PaletteExportSpec:
    enabled: bool = False
    format: str = "gpl"
    filename_suffix: str = ".palette.gpl"


@dataclass(frozen=True)
class JobSpec:
    settings: PreviewSettings
    palette_source: PaletteSourceSpec
    palette_steps: tuple[dict[str, Any], ...]
    image_steps: tuple[dict[str, Any], ...]
    palette_export: PaletteExportSpec
    batch_glob: str = DEFAULT_BATCH_GLOB
    report_path: str | None = None
    base_dir: Path = Path.cwd()


@dataclass(frozen=True)
class ProcessExecutionResult:
    input_path: Path
    output_path: Path
    palette_path: Path | None
    palette_size: int
    image_size: tuple[int, int]


@dataclass(frozen=True)
class BatchFileReport:
    input_path: str
    output_path: str
    status: str
    palette_path: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class BatchExecutionResult:
    output_dir: Path
    report_path: Path
    processed: int
    failed: int
    files: tuple[BatchFileReport, ...]


def build_default_job_config() -> dict[str, Any]:
    return {
        "pipeline": {
            "pixel_width": 2,
            "downsample_mode": "nearest",
            "palette_reduction_colors": 16,
            "generated_shades": 4,
            "contrast_bias": 1.0,
            "palette_dither_mode": "none",
            "input_mode": "rgba",
            "output_mode": "rgba",
            "quantizer": "median-cut",
        },
        "palette_source": {
            "type": "generate",
        },
        "palette_steps": [],
        "image_steps": [],
        "output": {
            "batch_glob": DEFAULT_BATCH_GLOB,
            "report_path": None,
            "palette_export": {
                "enabled": False,
                "format": "gpl",
                "filename_suffix": ".palette.gpl",
            },
        },
    }


def write_default_job_config(path: Path, *, overwrite: bool = False) -> Path:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing config: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_default_job_config(), indent=2), encoding="utf-8")
    return path


def load_job_spec(config_path: Path | None, *, cwd: Path | None = None) -> JobSpec:
    base_dir = (cwd or Path.cwd()).resolve()
    raw: dict[str, Any] = {}
    if config_path is not None:
        try:
            raw_data = json.loads(config_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise CliJobError(f"Config file not found: {config_path}") from exc
        except json.JSONDecodeError as exc:
            raise CliJobError(f"Invalid JSON in config {config_path}: {exc}") from exc
        if not isinstance(raw_data, dict):
            raise CliJobError("CLI config must be a JSON object.")
        raw = raw_data
        base_dir = config_path.resolve().parent
    return _normalize_job_spec(raw, base_dir=base_dir)


def apply_job_overrides(
    job: JobSpec,
    *,
    pixel_width: int | None = None,
    downsample_mode: str | None = None,
    palette_reduction_colors: int | None = None,
    generated_shades: int | None = None,
    contrast_bias: float | None = None,
    palette_dither_mode: str | None = None,
    input_mode: str | None = None,
    output_mode: str | None = None,
    quantizer: str | None = None,
    palette_file: Path | None = None,
    builtin_palette: str | None = None,
    batch_glob: str | None = None,
    report_path: Path | None = None,
    save_palette_path: Path | None = None,
) -> JobSpec:
    settings = job.settings
    if pixel_width is not None:
        settings = replace(settings, pixel_width=max(1, int(pixel_width)))
    if downsample_mode is not None:
        settings = replace(settings, downsample_mode=_coerce_downsample_mode(downsample_mode))
    if palette_reduction_colors is not None:
        settings = replace(settings, palette_reduction_colors=max(1, min(256, int(palette_reduction_colors))))
    if generated_shades is not None:
        settings = deserialize_settings({**_settings_to_pipeline_dict(settings), "generated_shades": generated_shades})
    if contrast_bias is not None:
        settings = deserialize_settings({**_settings_to_pipeline_dict(settings), "contrast_bias": contrast_bias})
    if palette_dither_mode is not None:
        settings = replace(settings, palette_dither_mode=_coerce_palette_dither_mode(palette_dither_mode))
    if input_mode is not None:
        settings = replace(settings, input_mode=_coerce_color_mode(input_mode, label="input_mode"))
    if output_mode is not None:
        settings = replace(settings, output_mode=_coerce_color_mode(output_mode, label="output_mode"))
    if quantizer is not None:
        settings = replace(settings, quantizer=_coerce_quantizer(quantizer))

    palette_source = job.palette_source
    if palette_file is not None:
        palette_source = PaletteSourceSpec(type="file", path=str(palette_file))
    elif builtin_palette is not None:
        palette_source = PaletteSourceSpec(type="builtin", path=str(builtin_palette))

    palette_export = job.palette_export
    if save_palette_path is not None:
        export_format = "json" if save_palette_path.suffix.lower() == ".json" else "gpl"
        palette_export = PaletteExportSpec(enabled=True, format=export_format, filename_suffix=save_palette_path.name)

    return JobSpec(
        settings=settings,
        palette_source=palette_source,
        palette_steps=job.palette_steps,
        image_steps=job.image_steps,
        palette_export=palette_export,
        batch_glob=batch_glob or job.batch_glob,
        report_path=str(report_path) if report_path is not None else job.report_path,
        base_dir=job.base_dir,
    )


def run_process_job(
    input_path: Path,
    output_path: Path,
    job: JobSpec,
    *,
    overwrite: bool = False,
    palette_output_path: Path | None = None,
) -> ProcessExecutionResult:
    validate_input_path(input_path)
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    validate_output_path(output_path, overwrite=overwrite)

    image = load_png_rgba_image(str(input_path))
    grid = image_to_rgb_grid(image)
    workspace = ColorWorkspace()

    downsample_config = _build_pipeline_config(job.settings)
    downsampled = downsample_image(grid, downsample_config)
    current_palette = _load_initial_palette(job, downsampled.prepared_input.reduced_labels)
    selection: list[int] = []

    current_palette, selection = _apply_palette_steps(
        current_palette,
        selection,
        job.palette_steps,
        settings=job.settings,
        workspace=workspace,
    )
    if not current_palette:
        raise CliJobError("The current palette is empty after palette steps.")

    reduce_config = _build_pipeline_config(job.settings, palette_size=len(current_palette))
    result = reduce_palette_image(
        downsampled.prepared_input,
        reduce_config,
        palette_override=current_palette,
    )
    result, current_palette, selection = _apply_image_steps(
        result,
        current_palette,
        selection,
        job.image_steps,
        workspace=workspace,
    )

    process_result_to_rgba_image(result).save(output_path)
    saved_palette_path = _save_palette_export(
        current_palette,
        output_path,
        job.palette_export,
        explicit_output_path=palette_output_path,
        overwrite=overwrite,
    )
    return ProcessExecutionResult(
        input_path=input_path.resolve(),
        output_path=output_path,
        palette_path=saved_palette_path,
        palette_size=len(current_palette),
        image_size=(result.width, result.height),
    )


def run_batch_job(
    input_dir: Path,
    output_dir: Path,
    job: JobSpec,
    *,
    overwrite: bool = False,
    fail_fast: bool = False,
    report_path: Path | None = None,
) -> BatchExecutionResult:
    input_root = input_dir.resolve()
    output_root = output_dir.resolve()
    if not input_root.exists() or not input_root.is_dir():
        raise CliJobError(f"Input directory not found: {input_root}")
    try:
        output_root.relative_to(input_root)
    except ValueError:
        pass
    else:
        raise CliJobError("Batch output directory must not be inside the input directory.")
    if input_root == output_root:
        raise CliJobError("Batch output directory must be different from the input directory.")

    report_target = _resolve_report_path(job, output_root, report_path)
    files = tuple(_discover_batch_inputs(input_root, job.batch_glob))
    output_root.mkdir(parents=True, exist_ok=True)

    reports: list[BatchFileReport] = []
    processed = 0
    failed = 0
    for source in files:
        relative = source.relative_to(input_root)
        target = (output_root / relative).with_suffix(".png")
        try:
            result = run_process_job(source, target, job, overwrite=overwrite)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            reports.append(
                BatchFileReport(
                    input_path=str(source),
                    output_path=str(target),
                    status="error",
                    error=str(exc),
                )
            )
            if fail_fast:
                break
            continue
        processed += 1
        reports.append(
            BatchFileReport(
                input_path=str(source),
                output_path=str(result.output_path),
                palette_path=str(result.palette_path) if result.palette_path is not None else None,
                status="ok",
            )
        )

    report_target.parent.mkdir(parents=True, exist_ok=True)
    report_payload = {
        "input_dir": str(input_root),
        "output_dir": str(output_root),
        "processed": processed,
        "failed": failed,
        "batch_glob": job.batch_glob,
        "files": [report.__dict__ for report in reports],
    }
    report_target.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
    return BatchExecutionResult(
        output_dir=output_root,
        report_path=report_target,
        processed=processed,
        failed=failed,
        files=tuple(reports),
    )


def process_result_to_rgba_image(result: ProcessResult) -> Image.Image:
    image = Image.new("RGBA", (result.width, result.height))
    if result.width <= 0 or result.height <= 0:
        return image
    alpha_mask = result.alpha_mask
    data: list[tuple[int, int, int, int]] = []
    for y, row in enumerate(result.grid):
        for x, (red, green, blue) in enumerate(row):
            is_visible = True if alpha_mask is None else bool(alpha_mask[y][x])
            data.append((red, green, blue, 255 if is_visible else 0))
    image.putdata(data)
    return image


def resolve_builtin_palette(path_value: str) -> PaletteCatalogEntry:
    normalized = path_value.replace("\\", "/").strip("/").lower()
    root = _resource_path("palettes")
    for entry in discover_palette_catalog(root):
        try:
            relative = entry.path.relative_to(root).as_posix().lower()
        except ValueError:
            continue
        if relative == normalized:
            return entry
    raise CliJobError(f"Unknown built-in palette: {path_value}")


def _normalize_job_spec(raw: dict[str, Any], *, base_dir: Path) -> JobSpec:
    pipeline_data = raw.get("pipeline")
    if pipeline_data is None:
        pipeline_data = build_default_job_config()["pipeline"]
    if not isinstance(pipeline_data, dict):
        raise CliJobError("Config field 'pipeline' must be an object.")
    settings = deserialize_settings(pipeline_data)
    settings = replace(
        settings,
        downsample_mode=_coerce_downsample_mode(pipeline_data.get("downsample_mode", settings.downsample_mode)),
        palette_dither_mode=_coerce_palette_dither_mode(pipeline_data.get("palette_dither_mode", settings.palette_dither_mode)),
        input_mode=_coerce_color_mode(pipeline_data.get("input_mode", settings.input_mode), label="input_mode"),
        output_mode=_coerce_color_mode(pipeline_data.get("output_mode", settings.output_mode), label="output_mode"),
        quantizer=_coerce_quantizer(pipeline_data.get("quantizer", settings.quantizer)),
    )

    palette_source_data = raw.get("palette_source") or {"type": "generate"}
    if not isinstance(palette_source_data, dict):
        raise CliJobError("Config field 'palette_source' must be an object.")
    source_type = str(palette_source_data.get("type", "generate")).strip().lower()
    if source_type not in {"generate", "file", "builtin"}:
        raise CliJobError("palette_source.type must be one of: generate, file, builtin.")
    source_path = palette_source_data.get("path")
    if source_type in {"file", "builtin"} and not isinstance(source_path, str):
        raise CliJobError(f"palette_source.path is required for type '{source_type}'.")
    palette_source = PaletteSourceSpec(type=source_type, path=source_path if isinstance(source_path, str) else None)

    palette_steps = _normalize_steps(raw.get("palette_steps", []), allowed_types=PALETTE_STEP_TYPES, section="palette_steps")
    image_steps = _normalize_steps(raw.get("image_steps", []), allowed_types=IMAGE_STEP_TYPES, section="image_steps")

    output_data = raw.get("output") or {}
    if not isinstance(output_data, dict):
        raise CliJobError("Config field 'output' must be an object.")
    palette_export_data = output_data.get("palette_export") or {}
    if not isinstance(palette_export_data, dict):
        raise CliJobError("output.palette_export must be an object.")
    export_enabled = bool(palette_export_data.get("enabled", False))
    export_format = str(palette_export_data.get("format", "gpl")).strip().lower()
    if export_format not in ALLOWED_PALETTE_EXPORT_FORMATS:
        raise CliJobError("output.palette_export.format must be 'gpl' or 'json'.")
    export_suffix = palette_export_data.get("filename_suffix")
    if export_suffix is None:
        export_suffix = f".palette.{export_format}"
    if not isinstance(export_suffix, str) or not export_suffix:
        raise CliJobError("output.palette_export.filename_suffix must be a non-empty string.")
    batch_glob = output_data.get("batch_glob", DEFAULT_BATCH_GLOB)
    if not isinstance(batch_glob, str) or not batch_glob.strip():
        raise CliJobError("output.batch_glob must be a non-empty string.")
    report_path = output_data.get("report_path")
    if report_path is not None and not isinstance(report_path, str):
        raise CliJobError("output.report_path must be a string when provided.")

    return JobSpec(
        settings=settings,
        palette_source=palette_source,
        palette_steps=tuple(palette_steps),
        image_steps=tuple(image_steps),
        palette_export=PaletteExportSpec(enabled=export_enabled, format=export_format, filename_suffix=export_suffix),
        batch_glob=batch_glob,
        report_path=report_path,
        base_dir=base_dir,
    )


def _normalize_steps(raw_steps: Any, *, allowed_types: set[str], section: str) -> list[dict[str, Any]]:
    if raw_steps is None:
        return []
    if not isinstance(raw_steps, list):
        raise CliJobError(f"Config field '{section}' must be an array.")
    normalized: list[dict[str, Any]] = []
    for index, step in enumerate(raw_steps):
        if not isinstance(step, dict):
            raise CliJobError(f"{section}[{index}] must be an object.")
        step_type = str(step.get("type", "")).strip().lower()
        if step_type not in allowed_types:
            allowed = ", ".join(sorted(allowed_types))
            raise CliJobError(f"{section}[{index}].type must be one of: {allowed}.")
        normalized_step = dict(step)
        normalized_step["type"] = step_type
        normalized.append(normalized_step)
    return normalized


def _coerce_downsample_mode(value: object) -> str:
    normalized = str(value or "nearest").strip().lower()
    if normalized not in ALLOWED_DOWNSAMPLE_MODES:
        raise CliJobError(f"Unsupported downsample mode: {value}")
    return normalized


def _coerce_palette_dither_mode(value: object) -> str:
    normalized = str(value or "none").strip().lower()
    if normalized == "floyd-steinberg":
        return "ordered"
    if normalized not in ALLOWED_PALETTE_DITHER_MODES:
        raise CliJobError(f"Unsupported palette dither mode: {value}")
    return normalized


def _coerce_color_mode(value: object, *, label: str) -> str:
    normalized = str(value or "rgba").strip().lower()
    if normalized not in ALLOWED_COLOR_MODES:
        raise CliJobError(f"Unsupported {label}: {value}")
    return normalized


def _coerce_quantizer(value: object) -> str:
    normalized = str(value or "median-cut").strip().lower()
    if normalized == "topk":
        return "median-cut"
    if normalized not in ALLOWED_QUANTIZERS:
        raise CliJobError(f"Unsupported quantizer: {value}")
    return normalized


def _settings_to_pipeline_dict(settings: PreviewSettings) -> dict[str, Any]:
    return {
        "pixel_width": settings.pixel_width,
        "downsample_mode": settings.downsample_mode,
        "palette_reduction_colors": settings.palette_reduction_colors,
        "generated_shades": settings.generated_shades,
        "contrast_bias": settings.contrast_bias,
        "palette_dither_mode": settings.palette_dither_mode,
        "input_mode": settings.input_mode,
        "output_mode": settings.output_mode,
        "quantizer": settings.quantizer,
    }


def _load_initial_palette(job: JobSpec, labels: list[list[int]]) -> list[int]:
    source = job.palette_source
    if source.type == "generate":
        palette = generate_palette(labels, job.settings.palette_reduction_colors, method=job.settings.quantizer)
    elif source.type == "file":
        if source.path is None:
            raise CliJobError("palette_source.path is required for file palettes.")
        palette = load_palette(_resolve_job_path(job, source.path))
    else:
        if source.path is None:
            raise CliJobError("palette_source.path is required for built-in palettes.")
        palette = list(resolve_builtin_palette(source.path).colors)
    if not palette:
        raise CliJobError("Palette source produced no colours.")
    return list(palette)


def _apply_palette_steps(
    palette: list[int],
    selection: list[int],
    steps: tuple[dict[str, Any], ...],
    *,
    settings: PreviewSettings,
    workspace: ColorWorkspace,
) -> tuple[list[int], list[int]]:
    current_palette = list(palette)
    current_selection = _normalize_selection(selection, len(current_palette))
    for step in steps:
        step_type = step["type"]
        if step_type == "select":
            mode = str(step.get("mode", "")).strip().lower()
            if mode not in PALETTE_SELECT_MODES:
                raise CliJobError(f"Unsupported palette select mode: {mode}")
            threshold_percent = step.get("threshold_percent", 30)
            current_selection = select_palette_indices(current_palette, mode, int(threshold_percent), workspace)
            continue
        if step_type == "select_indices":
            indices = _parse_indices(step.get("indices"), palette_size=len(current_palette))
            if not indices:
                raise CliJobError("select_indices requires at least one valid palette index.")
            current_selection = indices
            continue
        if step_type == "select_all":
            current_selection = list(range(len(current_palette)))
            continue
        if step_type == "clear_selection":
            current_selection = []
            continue
        if step_type == "sort":
            mode = str(step.get("mode", "")).strip().lower()
            if mode not in PALETTE_SORT_MODES:
                raise CliJobError(f"Unsupported palette sort mode: {mode}")
            before = list(current_palette)
            current_palette = sort_palette_labels(current_palette, mode, workspace)
            current_selection = _remap_selection_after_sort(before, current_palette, current_selection)
            continue
        if step_type == "merge_selected":
            selected = _require_selection(current_selection, minimum=2, message="merge_selected requires 2 or more selected colours.")
            merged_label = merge_palette_labels([current_palette[index] for index in selected], workspace=workspace)
            selected_set = set(selected)
            first_selected = selected[0]
            merged_palette: list[int] = []
            for index, label in enumerate(current_palette):
                if index == first_selected:
                    merged_palette.append(merged_label)
                if index not in selected_set:
                    merged_palette.append(label)
            current_palette = merged_palette
            current_selection = [first_selected]
            continue
        if step_type == "ramp_selected":
            selected = _require_selection(current_selection, minimum=1, message="ramp_selected requires at least one selected colour.")
            ramp_labels = generate_ramp_palette_labels(
                [current_palette[index] for index in selected],
                generated_shades=settings.generated_shades,
                contrast_bias=settings.contrast_bias,
                workspace=workspace,
            )
            current_palette.extend(ramp_labels)
            continue
        if step_type == "remove_selected":
            selected = _require_selection(current_selection, minimum=1, message="remove_selected requires at least one selected colour.")
            selected_set = set(selected)
            current_palette = [label for index, label in enumerate(current_palette) if index not in selected_set]
            current_selection = []
            continue
        if step_type == "add_colors":
            raw_colors = step.get("colors")
            if not isinstance(raw_colors, list) or not raw_colors:
                raise CliJobError("add_colors requires a non-empty 'colors' array.")
            for value in raw_colors:
                label = _parse_color_label(value)
                if label not in current_palette:
                    current_palette.append(label)
            continue
        if step_type == "adjust_palette":
            scope = str(step.get("scope", "all")).strip().lower()
            if scope not in {"all", "selected"}:
                raise CliJobError("adjust_palette.scope must be 'all' or 'selected'.")
            selected_indices = None
            if scope == "selected":
                selected = _require_selection(
                    current_selection,
                    minimum=1,
                    message="adjust_palette with scope 'selected' requires at least one selected colour.",
                )
                selected_indices = set(selected)
            adjustments = PaletteAdjustments(
                brightness=int(step.get("brightness", 0)),
                contrast=int(step.get("contrast", 100)),
                hue=int(step.get("hue", 0)),
                saturation=int(step.get("saturation", 100)),
            )
            current_palette = adjust_palette_labels(
                current_palette,
                adjustments,
                workspace=workspace,
                selected_indices=selected_indices,
            )
            continue
        raise CliJobError(f"Unsupported palette step type: {step_type}")

    return current_palette, _normalize_selection(current_selection, len(current_palette))


def _apply_image_steps(
    result: ProcessResult,
    palette: list[int],
    selection: list[int],
    steps: tuple[dict[str, Any], ...],
    *,
    workspace: ColorWorkspace,
) -> tuple[ProcessResult, list[int], list[int]]:
    current_result = result
    current_palette = list(palette)
    current_selection = _normalize_selection(selection, len(current_palette))
    for step in steps:
        step_type = step["type"]
        if step_type == "make_transparent_fill":
            for x, y in _parse_points(step):
                current_result, _changed = apply_transparency_fill(current_result, x, y)
            continue
        if step_type == "add_outline":
            colour_mode = str(step.get("colour_mode", "palette")).strip().lower()
            if colour_mode not in ALLOWED_OUTLINE_COLOUR_MODES:
                raise CliJobError("add_outline.colour_mode must be 'palette' or 'adaptive'.")
            pixel_perfect = bool(step.get("pixel_perfect", True))
            adaptive = colour_mode == "adaptive"
            outline_label = current_palette[0] if current_palette else 0
            if not adaptive:
                selected = _require_selection(
                    current_selection,
                    minimum=1,
                    maximum=1,
                    message="add_outline in palette mode requires exactly one selected colour.",
                )
                outline_label = current_palette[selected[0]]
            adaptive_darken_percent = int(step.get("adaptive_darken_percent", 60))
            add_generated_colours = bool(step.get("add_generated_colours", False))
            current_result, _changed, generated = add_exterior_outline(
                current_result,
                outline_label,
                pixel_perfect=pixel_perfect,
                adaptive=adaptive,
                adaptive_darken_percent=adaptive_darken_percent,
                workspace=workspace,
            )
            if adaptive and add_generated_colours:
                existing = set(current_palette)
                for label in generated:
                    if label not in existing:
                        current_palette.append(label)
                        existing.add(label)
            continue
        if step_type == "remove_outline":
            pixel_perfect = bool(step.get("pixel_perfect", True))
            threshold = step.get("brightness_threshold") or {}
            if not isinstance(threshold, dict):
                raise CliJobError("remove_outline.brightness_threshold must be an object when provided.")
            current_result, _changed = remove_exterior_outline(
                current_result,
                pixel_perfect=pixel_perfect,
                brightness_threshold_enabled=bool(threshold.get("enabled", False)),
                brightness_threshold_percent=int(threshold.get("percent", OUTLINE_REMOVE_BRIGHTNESS_THRESHOLD_DEFAULT)),
                brightness_threshold_direction=_coerce_brightness_direction(
                    threshold.get("direction", OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK)
                ),
                workspace=workspace,
            )
            continue
        raise CliJobError(f"Unsupported image step type: {step_type}")
    return current_result, current_palette, _normalize_selection(current_selection, len(current_palette))


def _parse_indices(raw: Any, *, palette_size: int) -> list[int]:
    if not isinstance(raw, list):
        raise CliJobError("indices must be an array of integers.")
    normalized = sorted({int(value) for value in raw if 0 <= int(value) < palette_size})
    return normalized


def _require_selection(
    selection: list[int],
    *,
    minimum: int,
    maximum: int | None = None,
    message: str,
) -> list[int]:
    count = len(selection)
    if count < minimum:
        raise CliJobError(message)
    if maximum is not None and count > maximum:
        raise CliJobError(message)
    return list(selection)


def _normalize_selection(selection: list[int], palette_size: int) -> list[int]:
    return sorted({index for index in selection if 0 <= index < palette_size})


def _remap_selection_after_sort(before: list[int], after: list[int], selection: list[int]) -> list[int]:
    counts: dict[int, int] = {}
    for index in selection:
        if 0 <= index < len(before):
            label = before[index]
            counts[label] = counts.get(label, 0) + 1
    remapped: list[int] = []
    for index, label in enumerate(after):
        remaining = counts.get(label, 0)
        if remaining <= 0:
            continue
        remapped.append(index)
        counts[label] = remaining - 1
    return remapped


def _parse_color_label(value: Any) -> int:
    if isinstance(value, int):
        return value & 0xFFFFFF
    if not isinstance(value, str):
        raise CliJobError(f"Unsupported colour value: {value!r}")
    normalized = value.strip().lower()
    if normalized.startswith("#"):
        normalized = normalized[1:]
    if len(normalized) != 6 or any(character not in "0123456789abcdef" for character in normalized):
        raise CliJobError(f"Colours must use #RRGGBB syntax: {value!r}")
    return int(normalized, 16)


def _parse_points(step: dict[str, Any]) -> list[tuple[int, int]]:
    raw_points = step.get("points")
    if raw_points is None:
        if "x" in step and "y" in step:
            return [(int(step["x"]), int(step["y"]))]
        raise CliJobError("make_transparent_fill requires either 'points' or both 'x' and 'y'.")
    if not isinstance(raw_points, list) or not raw_points:
        raise CliJobError("make_transparent_fill.points must be a non-empty array.")
    points: list[tuple[int, int]] = []
    for raw_point in raw_points:
        if not isinstance(raw_point, (list, tuple)) or len(raw_point) != 2:
            raise CliJobError("Each transparency fill point must be a two-item array: [x, y].")
        points.append((int(raw_point[0]), int(raw_point[1])))
    return points


def _coerce_brightness_direction(value: object) -> str:
    normalized = str(value or OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK).strip().lower()
    if normalized not in ALLOWED_BRIGHTNESS_DIRECTIONS:
        raise CliJobError("Brightness threshold direction must be 'dark' or 'bright'.")
    return normalized


def _build_pipeline_config(settings: PreviewSettings, *, palette_size: int | None = None) -> PipelineConfig:
    return PipelineConfig(
        pixel_width=settings.pixel_width,
        downsample_mode=settings.downsample_mode,
        colors=max(1, palette_size or settings.palette_reduction_colors),
        palette_strategy="override",
        key_colors=(),
        generated_shades=settings.generated_shades,
        contrast_bias=settings.contrast_bias,
        palette_dither_mode=settings.palette_dither_mode,
        input_mode=settings.input_mode,
        output_mode=settings.output_mode,
        quantizer=settings.quantizer,
        dither_mode=settings.dither_mode,
    )


def _resolve_job_path(job: JobSpec, path_value: str) -> Path:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = job.base_dir / path
    return path.resolve()


def _save_palette_export(
    palette: list[int],
    output_path: Path,
    palette_export: PaletteExportSpec,
    *,
    explicit_output_path: Path | None,
    overwrite: bool,
) -> Path | None:
    if explicit_output_path is not None:
        target = explicit_output_path.resolve()
        if target.exists() and not overwrite:
            raise FileExistsError(f"Refusing to overwrite existing palette file: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        save_palette(target, palette)
        return target
    if not palette_export.enabled:
        return None
    target = output_path.parent / f"{output_path.stem}{palette_export.filename_suffix}"
    if target.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing palette file: {target}")
    save_palette(target, palette)
    return target


def _resolve_report_path(job: JobSpec, output_root: Path, override: Path | None) -> Path:
    if override is not None:
        return override.resolve()
    if job.report_path:
        path = Path(job.report_path).expanduser()
        if not path.is_absolute():
            path = job.base_dir / path
        return path.resolve()
    return (output_root / DEFAULT_BATCH_REPORT_NAME).resolve()


def _discover_batch_inputs(input_root: Path, pattern: str) -> list[Path]:
    files = [path.resolve() for path in input_root.rglob(pattern) if path.is_file()]
    files.sort()
    return files


def _resource_path(name: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")) / name
    return Path(__file__).resolve().parents[2] / name

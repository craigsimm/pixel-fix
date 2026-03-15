from pathlib import Path

import numpy as np
from PIL import Image

from pixel_fix.palette.adjust import PaletteAdjustments, adjust_palette_labels, adjust_structured_palette
from pixel_fix.palette.advanced import (
    RAMPFORGE_8_CONTRAST_BIAS,
    RAMPFORGE_8_GENERATED_SHADES,
    _RAMPFORGE_8_ORANGE_MODE,
    _Rampforge8RecoveryCandidate,
    _Rampforge8ReplaceableSlot,
    _append_rampforge_8_neutral_ramps,
    _generate_seed_ramp,
    _rampforge_8_assignment_key,
    _rampforge_8_label_mode,
    _select_rampforge_8_anchors,
    _seed_shade_index,
    _unique_mapping_candidates,
    build_weighted_dataset,
    detect_key_colors_from_image,
    generate_structured_palette,
)
from pixel_fix.palette.color_modes import convert_mode, extract_unique_colors, to_indexed
from pixel_fix.palette.dither import apply_dither
from pixel_fix.palette.edit import generate_ramp_palette_labels, merge_palette_labels
from pixel_fix.palette.io import load_palette, save_palette
from pixel_fix.palette.model import StructuredPalette
from pixel_fix.palette.quantize import generate_palette, generate_palette_source, remap_to_palette
from pixel_fix.palette.replace import replace_batch, replace_exact, replace_tolerance
from pixel_fix.palette.sort import (
    PALETTE_SELECT_CHROMA_HIGH,
    PALETTE_SELECT_CHROMA_LOW,
    PALETTE_SELECT_HUE_CYAN,
    PALETTE_SELECT_HUE_BLUE,
    PALETTE_SELECT_HUE_GREEN,
    PALETTE_SELECT_HUE_MAGENTA,
    PALETTE_SELECT_HUE_RED,
    PALETTE_SELECT_HUE_YELLOW,
    PALETTE_SELECT_LIGHTNESS_DARK,
    PALETTE_SELECT_LIGHTNESS_LIGHT,
    PALETTE_SELECT_SATURATION_HIGH,
    PALETTE_SELECT_SATURATION_LOW,
    PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES,
    PALETTE_SELECT_TEMPERATURE_COOL,
    PALETTE_SELECT_TEMPERATURE_WARM,
    PALETTE_SORT_CHROMA,
    PALETTE_SORT_HUE,
    PALETTE_SORT_LIGHTNESS,
    PALETTE_SORT_SATURATION,
    PALETTE_SORT_TEMPERATURE,
    _palette_metrics,
    _selection_ranking,
    select_palette_indices,
    sort_palette_labels,
)
from pixel_fix.palette.workspace import ColorWorkspace, hyab_distance


def _rampforge_vivid_candidates(labels: list[list[int]], mode: str, workspace: ColorWorkspace) -> set[int]:
    dataset = build_weighted_dataset(labels, workspace)
    selected_indices = select_palette_indices(dataset.labels.tolist(), mode, 20, workspace)
    shortlist = [int(dataset.labels[index]) for index in selected_indices]
    if not shortlist:
        return set()
    ranked = _selection_ranking(_palette_metrics(shortlist, workspace), mode)
    candidate_ranked = [
        metric
        for metric in ranked
        if metric.lightness >= 0.35
    ] or ranked
    vivid_count = max(1, (len(candidate_ranked) + 1) // 2)
    vivid = candidate_ranked[:vivid_count] or candidate_ranked
    return {int(metric.label) for metric in vivid}


def _build_rampforge_baseline_palette(labels: list[list[int]], workspace: ColorWorkspace) -> StructuredPalette:
    dataset = build_weighted_dataset(labels, workspace)
    selected = _select_rampforge_8_anchors(dataset, workspace)
    baseline = generate_structured_palette(
        labels,
        key_colors=selected,
        generated_shades=RAMPFORGE_8_GENERATED_SHADES,
        contrast_bias=RAMPFORGE_8_CONTRAST_BIAS,
        workspace=workspace,
        source_mode="rampforge-8",
        source_label="Generated: RampForge-8",
    ).palette
    if dataset.size > 0:
        _append_rampforge_8_neutral_ramps(baseline, workspace)
    return baseline


def _weighted_palette_error(labels: list[list[int]], palette: StructuredPalette, workspace: ColorWorkspace) -> float:
    dataset = build_weighted_dataset(labels, workspace)
    if dataset.size == 0 or not palette.ramps:
        return 0.0
    palette_colors = palette.flattened_colors()
    palette_oklab = np.asarray([color.oklab for color in palette_colors], dtype=np.float64)
    primary_indices, _secondary_indices, _ramp_indices = _unique_mapping_candidates(dataset.labels, palette, workspace)
    distances = hyab_distance(dataset.oklab, palette_oklab[primary_indices]).astype(np.float64, copy=False)
    return float(np.sum(distances * dataset.counts))


def test_color_mode_grayscale_conversion() -> None:
    labels = [[0xFF0000, 0x00FF00]]
    out = convert_mode(labels, "grayscale")
    assert ((out[0][0] >> 16) & 0xFF) == ((out[0][0] >> 8) & 0xFF) == (out[0][0] & 0xFF)


def test_unique_palette_and_indexed_limit() -> None:
    labels = [[1, 2], [3, 2]]
    unique = extract_unique_colors(labels)
    assert unique == [1, 2, 3]
    indexed, palette = to_indexed(labels, max_colors=2)
    assert len(palette) == 2
    assert len(indexed) == 2


def test_palette_io_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "palette.gpl"
    save_palette(path, [0x112233, 0xabcdef])
    text = path.read_text(encoding="utf-8")
    assert text.startswith("GIMP Palette")
    loaded = load_palette(path)
    assert loaded == [0x112233, 0xABCDEF]


def test_sort_palette_by_lightness_orders_dark_to_light() -> None:
    workspace = ColorWorkspace()
    labels = [0xEEEEEE, 0x222222, 0x888888]

    sorted_labels = sort_palette_labels(labels, PALETTE_SORT_LIGHTNESS, workspace)

    assert sorted_labels == [0x222222, 0x888888, 0xEEEEEE]


def test_sort_palette_by_hue_groups_neutrals_then_orders_hues() -> None:
    workspace = ColorWorkspace()
    labels = [0x00FF00, 0x777777, 0xFF0000, 0x0000FF]

    sorted_labels = sort_palette_labels(labels, PALETTE_SORT_HUE, workspace)

    assert sorted_labels[0] == 0x777777
    assert sorted_labels[1:] == [0xFF0000, 0x00FF00, 0x0000FF]


def test_sort_palette_by_saturation_places_greys_first() -> None:
    workspace = ColorWorkspace()
    labels = [0x666666, 0xAA8844, 0xFF0000]

    sorted_labels = sort_palette_labels(labels, PALETTE_SORT_SATURATION, workspace)

    assert sorted_labels[0] == 0x666666
    assert sorted_labels[-1] == 0xFF0000


def test_sort_palette_by_chroma_uses_oklab_chroma() -> None:
    workspace = ColorWorkspace()
    labels = [0x777777, 0x7A7876, 0xFF0000]

    sorted_labels = sort_palette_labels(labels, PALETTE_SORT_CHROMA, workspace)

    assert sorted_labels[0] == 0x777777
    assert sorted_labels[-1] == 0xFF0000


def test_sort_palette_by_temperature_orders_cool_before_warm() -> None:
    workspace = ColorWorkspace()
    labels = [0xFFAA00, 0x0088FF, 0x999999, 0xFF2200]

    sorted_labels = sort_palette_labels(labels, PALETTE_SORT_TEMPERATURE, workspace)

    assert sorted_labels[0] == 0x999999
    assert sorted_labels[1] == 0x0088FF
    assert sorted_labels[-1] in {0xFFAA00, 0xFF2200}


def test_sort_palette_preserves_input_order_for_equal_keys() -> None:
    workspace = ColorWorkspace()
    labels = [0x112233, 0x112233, 0x445566]

    sorted_labels = sort_palette_labels(labels, PALETTE_SORT_LIGHTNESS, workspace)

    assert sorted_labels[:2] == [0x112233, 0x112233]


def test_select_palette_by_lightness_uses_threshold_and_preserves_original_order() -> None:
    workspace = ColorWorkspace()
    labels = [0xEEEEEE, 0x222222, 0x888888, 0x444444]

    dark_indices = select_palette_indices(labels, PALETTE_SELECT_LIGHTNESS_DARK, 30, workspace)
    light_indices = select_palette_indices(labels, PALETTE_SELECT_LIGHTNESS_LIGHT, 30, workspace)

    assert dark_indices == [1, 3]
    assert light_indices == [0, 2]


def test_select_palette_by_saturation_and_chroma_targets_expected_indices() -> None:
    workspace = ColorWorkspace()
    labels = [0x666666, 0x889977, 0xFF0000, 0x7A7876]

    low_saturation = select_palette_indices(labels, PALETTE_SELECT_SATURATION_LOW, 50, workspace)
    high_saturation = select_palette_indices(labels, PALETTE_SELECT_SATURATION_HIGH, 50, workspace)
    low_chroma = select_palette_indices(labels, PALETTE_SELECT_CHROMA_LOW, 50, workspace)
    high_chroma = select_palette_indices(labels, PALETTE_SELECT_CHROMA_HIGH, 50, workspace)

    assert low_saturation == [0, 3]
    assert high_saturation == [1, 2]
    assert low_chroma == [0, 3]
    assert high_chroma == [1, 2]


def test_select_palette_by_temperature_prefers_chromatic_colours() -> None:
    workspace = ColorWorkspace()
    labels = [0x999999, 0x0088FF, 0xFFAA00, 0xFF2200]

    cool_indices = select_palette_indices(labels, PALETTE_SELECT_TEMPERATURE_COOL, 50, workspace)
    warm_indices = select_palette_indices(labels, PALETTE_SELECT_TEMPERATURE_WARM, 50, workspace)

    assert cool_indices == [1, 3]
    assert warm_indices == [2, 3]


def test_select_palette_by_hue_bucket_excludes_neutrals_and_caps_at_eligible_count() -> None:
    workspace = ColorWorkspace()
    labels = [0x777777, 0x3366FF, 0x00FFFF]

    blue_indices = select_palette_indices(labels, PALETTE_SELECT_HUE_BLUE, 100, workspace)

    assert blue_indices == [1, 2]


def test_select_palette_by_similarity_targets_single_tight_cluster_in_original_order() -> None:
    workspace = ColorWorkspace()
    labels = [0x101010, 0x111111, 0x80FF00, 0x80FE00, 0xB040A0, 0x00B0FF]

    selected = select_palette_indices(labels, PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES, 70, workspace)

    assert selected == [2, 3]
    assert selected == sorted(selected)


def test_similarity_selection_edge_cases_cover_empty_single_and_no_match_palettes() -> None:
    workspace = ColorWorkspace()

    assert select_palette_indices([], PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES, 50, workspace) == []
    assert select_palette_indices([0x123456], PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES, 50, workspace) == []
    assert (
        select_palette_indices(
            [0x101010, 0x80FF00, 0xB040A0, 0x00B0FF],
            PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES,
            100,
            workspace,
        )
        == []
    )


def test_similarity_selection_threshold_is_monotonic_for_cluster_growth() -> None:
    workspace = ColorWorkspace()
    labels = [0x80FF00, 0x80FE00, 0x81FD00, 0x5500AA]

    strict = select_palette_indices(labels, PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES, 10, workspace)
    loose = select_palette_indices(labels, PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES, 100, workspace)

    assert strict == sorted(strict)
    assert loose == sorted(loose)
    assert len(strict) < len(loose)
    assert set(strict).issubset(set(loose))
    assert strict == [0, 1]
    assert loose == [0, 1, 2]


def test_similarity_selection_tie_break_prefers_tighter_cluster() -> None:
    workspace = ColorWorkspace()
    labels = [0x101010, 0x111111, 0x121212, 0x80FF00, 0x80FE00, 0x80FD00]

    selected = select_palette_indices(labels, PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES, 20, workspace)

    assert selected == [3, 4, 5]


def test_similarity_selection_output_can_be_merged_with_merge_palette_labels() -> None:
    workspace = ColorWorkspace()
    labels = [0x335577, 0x345678, 0xFFCC00, 0x10C0A0, 0x11BFA1]

    selected = select_palette_indices(labels, PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES, 60, workspace)
    merged = merge_palette_labels([labels[index] for index in selected], workspace=workspace)

    assert selected == [0, 1]
    assert isinstance(merged, int)
    assert 0 <= merged <= 0xFFFFFF


def test_json_palette_load_remains_supported(tmp_path: Path) -> None:
    path = tmp_path / "palette.json"
    path.write_text('{"palette": ["#112233", "#abcdef"]}', encoding="utf-8")
    loaded = load_palette(path)
    assert loaded == [0x112233, 0xABCDEF]


def test_gpl_palette_loads_with_comments_and_headers(tmp_path: Path) -> None:
    path = tmp_path / "palette.gpl"
    path.write_text(
        "\n".join(
            (
                "GIMP Palette",
                "Name: Example",
                "Columns: 2",
                "# comment",
                "17 34 51 First",
                "171 205 239 Second",
            )
        ),
        encoding="utf-8",
    )
    loaded = load_palette(path)
    assert loaded == [0x112233, 0xABCDEF]


def test_gpl_palette_rejects_invalid_colour_lines(tmp_path: Path) -> None:
    path = tmp_path / "broken.gpl"
    path.write_text("GIMP Palette\nnot-a-colour\n", encoding="utf-8")
    try:
        load_palette(path)
    except ValueError as exc:
        assert "Invalid GPL palette" in str(exc)
    else:
        raise AssertionError("Expected invalid GPL data to raise ValueError")


def test_quantizer_and_dither_pipeline_bits() -> None:
    labels = [[0x010101, 0xFEFEFE], [0x101010, 0xEEEEEE]]
    palette = generate_palette(labels, colors=2, method="kmeans")
    assert len(palette) == 2
    mapped = remap_to_palette(labels, palette)
    dithered = apply_dither(mapped, palette, "ordered")
    assert {v for row in dithered for v in row}.issubset(set(palette))


def test_generate_palette_supports_median_cut() -> None:
    labels = [
        [0x112233, 0x112233, 0x445566, 0x445566],
        [0x778899, 0x778899, 0xAABBCC, 0xAABBCC],
    ]
    palette = generate_palette(labels, colors=2, method="median-cut")
    assert len(palette) == 2
    assert all(isinstance(value, int) for value in palette)


def test_generate_palette_source_supports_rampforge_8() -> None:
    labels = [
        [0xAA5533, 0xAA5533, 0x4477AA, 0x4477AA],
        [0x55AA55, 0x55AA55, 0xAA3355, 0xAA3355],
    ]

    palette = generate_palette_source(labels, colors=2, method="rampforge-8")

    assert isinstance(palette, StructuredPalette)
    assert palette.source_mode == "rampforge-8"
    assert palette.generated_shades == 4
    assert palette.contrast_bias == 0.6
    assert 2 <= len(palette.ramps) <= 12
    assert all(len(ramp.colors) == 5 for ramp in palette.ramps)
    flattened = {color.label for ramp in palette.ramps for color in ramp.colors}
    assert 0x000000 in flattened
    assert 0xFFFFFF in flattened


def test_generate_palette_source_rampforge_8_recovery_recovers_missed_source_label_and_preserves_structure() -> None:
    workspace = ColorWorkspace()
    labels = [
        [0x8A5A30, 0x8A5A30, 0x8A5A30, 0x8A5A30, 0xC54444],
        [0x8A5A30, 0xC77A21, 0xD4B030, 0x55AA33, 0x4477AA],
        [0xAA55AA, 0x33AACC, 0x8C1E1E, 0x8C1E1E, 0x8A5A30],
        [0xAA5533, 0x6A4125, 0xDCC322, 0x2E63D8, 0x8A5A30],
    ]

    baseline = _build_rampforge_baseline_palette(labels, workspace)
    palette = generate_palette_source(labels, colors=99, method="rampforge-8")

    baseline_labels = {color.label for color in baseline.flattened_colors()}
    final_labels = {color.label for color in palette.flattened_colors()}
    source_labels = set(extract_unique_colors(labels))

    assert 0x8C1E1E not in baseline_labels
    assert 0x8C1E1E in final_labels
    assert len(palette.ramps) == len(baseline.ramps)
    assert palette.palette_size() == baseline.palette_size()
    assert palette.generated_shades == baseline.generated_shades
    assert [ramp.seed_label for ramp in palette.ramps] == [ramp.seed_label for ramp in baseline.ramps]
    assert [[color.label for color in ramp.colors] for ramp in palette.ramps[-2:]] == [
        [color.label for color in ramp.colors] for ramp in baseline.ramps[-2:]
    ]
    assert final_labels.difference(baseline_labels).issubset(source_labels)


def test_generate_palette_source_rampforge_8_merges_near_duplicates() -> None:
    workspace = ColorWorkspace()
    labels = [
        [0xAA5544, 0xAA5544, 0xAA5544, 0x55AA55],
        [0xAB5645, 0xAB5645, 0xAB5645, 0x55AA55],
    ]

    palette = generate_palette_source(labels, colors=99, method="rampforge-8")
    source_labels = extract_unique_colors(labels)
    green_candidates = {
        source_labels[index] for index in select_palette_indices(source_labels, PALETTE_SELECT_HUE_GREEN, 20, workspace)
    }
    seed_labels = [ramp.seed_label for ramp in palette.ramps[:-2]]

    assert isinstance(palette, StructuredPalette)
    assert len(palette.ramps) == 4
    assert any(label in green_candidates for label in seed_labels)


def test_generate_palette_source_rampforge_8_keeps_sparse_green_and_yellow_hues() -> None:
    workspace = ColorWorkspace()
    labels = [
        [0xAA5533, 0xAA5533, 0xAA5533, 0xAA5533],
        [0xAA5533, 0xAA5533, 0xAA5533, 0xAA5533],
        [0x4477AA, 0x4477AA, 0x55AA33, 0xD4B030],
        [0x4477AA, 0xAA3355, 0xAA3355, 0xAA3355],
    ]

    palette = generate_palette_source(labels, colors=99, method="rampforge-8")
    source_labels = extract_unique_colors(labels)
    green_candidates = {
        source_labels[index] for index in select_palette_indices(source_labels, PALETTE_SELECT_HUE_GREEN, 20, workspace)
    }
    yellow_candidates = {
        source_labels[index] for index in select_palette_indices(source_labels, PALETTE_SELECT_HUE_YELLOW, 20, workspace)
    }
    seed_labels = [ramp.seed_label for ramp in palette.ramps[:-2]]

    assert any(label in green_candidates for label in seed_labels)
    assert any(label in yellow_candidates for label in seed_labels)


def test_generate_palette_source_rampforge_8_keeps_all_sparse_canonical_hues() -> None:
    workspace = ColorWorkspace()
    labels = [
        [0x8A5A30, 0x8A5A30, 0x8A5A30, 0x777777],
        [0xC54444, 0xD4B030, 0x55AA33, 0x33AACC],
        [0x4477AA, 0xAA55AA, 0x8A5A30, 0x8A5A30],
    ]

    palette = generate_palette_source(labels, colors=99, method="rampforge-8")
    seed_labels = [ramp.seed_label for ramp in palette.ramps[:-2]]
    for mode in (
        PALETTE_SELECT_HUE_RED,
        PALETTE_SELECT_HUE_YELLOW,
        PALETTE_SELECT_HUE_GREEN,
        PALETTE_SELECT_HUE_CYAN,
        PALETTE_SELECT_HUE_BLUE,
        PALETTE_SELECT_HUE_MAGENTA,
    ):
        candidates = _rampforge_vivid_candidates(labels, mode, workspace)
        assert any(label in candidates for label in seed_labels)


def test_generate_palette_source_rampforge_8_keeps_sparse_vivid_yellow_and_blue_hues() -> None:
    workspace = ColorWorkspace()
    labels = [
        [0x8A5A30, 0x8A5A30, 0x8A5A30, 0x8A5A30, 0xA9662F],
        [0x8A5A30, 0x8A5A30, 0xAA5533, 0x8A5A30, 0x8A5A30],
        [0x8A5A30, 0x6A4125, 0x8A5A30, 0xDCC322, 0x8A5A30],
        [0x8A5A30, 0x8A5A30, 0x2E63D8, 0x8A5A30, 0x8A5A30],
    ]

    palette = generate_palette_source(labels, colors=99, method="rampforge-8")
    seed_labels = [ramp.seed_label for ramp in palette.ramps[:-2]]
    seed_metrics = {int(metric.label): metric for metric in _palette_metrics(seed_labels, workspace)}
    yellow_candidates = _rampforge_vivid_candidates(labels, PALETTE_SELECT_HUE_YELLOW, workspace)
    blue_candidates = _rampforge_vivid_candidates(labels, PALETTE_SELECT_HUE_BLUE, workspace)

    chosen_yellows = [label for label in seed_labels if label in yellow_candidates]
    chosen_blues = [label for label in seed_labels if label in blue_candidates]

    assert chosen_yellows
    assert chosen_blues
    assert all(not seed_metrics[label].is_neutral for label in chosen_yellows)
    assert all(not seed_metrics[label].is_neutral for label in chosen_blues)


def test_generate_palette_source_rampforge_8_keeps_distinct_red_orange_and_yellow_hues() -> None:
    labels = [
        [0x8A5A30, 0x8A5A30, 0x8A5A30, 0x8A5A30, 0xC54444],
        [0x8A5A30, 0x8A5A30, 0xC77A21, 0x8A5A30, 0x8A5A30],
        [0x8A5A30, 0x8A5A30, 0xD4B030, 0x55AA33, 0x4477AA],
        [0x8A5A30, 0x8A5A30, 0xAA55AA, 0x8A5A30, 0x8A5A30],
    ]

    palette = generate_palette_source(labels, colors=99, method="rampforge-8")
    seed_labels = {ramp.seed_label for ramp in palette.ramps[:-2]}

    assert 0xC54444 in seed_labels
    assert 0xC77A21 in seed_labels
    assert 0xD4B030 in seed_labels


def test_generate_seed_ramp_keeps_red_shadows_in_warm_family() -> None:
    workspace = ColorWorkspace()
    ramp = _generate_seed_ramp(0xC54444, 0, RAMPFORGE_8_GENERATED_SHADES, RAMPFORGE_8_CONTRAST_BIAS, workspace)
    seed_idx = _seed_shade_index(RAMPFORGE_8_GENERATED_SHADES)
    dark_modes = [_rampforge_8_label_mode(ramp.colors[index].label, workspace) for index in range(seed_idx)]

    assert all(mode is not None for mode in dark_modes)
    assert any(mode == PALETTE_SELECT_HUE_RED for mode in dark_modes)
    assert all(mode in {PALETTE_SELECT_HUE_RED, _RAMPFORGE_8_ORANGE_MODE, PALETTE_SELECT_HUE_MAGENTA} for mode in dark_modes)


def test_generate_seed_ramp_keeps_yellow_ramp_in_warm_family() -> None:
    workspace = ColorWorkspace()
    ramp = _generate_seed_ramp(0xDCC322, 0, RAMPFORGE_8_GENERATED_SHADES, RAMPFORGE_8_CONTRAST_BIAS, workspace)
    seed_idx = _seed_shade_index(RAMPFORGE_8_GENERATED_SHADES)
    warm_modes = [_rampforge_8_label_mode(color.label, workspace) for color in ramp.colors if color.shade_index != seed_idx]
    dark_modes = [_rampforge_8_label_mode(ramp.colors[index].label, workspace) for index in range(seed_idx)]

    assert all(mode is not None for mode in warm_modes)
    assert all(mode in {_RAMPFORGE_8_ORANGE_MODE, PALETTE_SELECT_HUE_YELLOW} for mode in warm_modes)
    assert any(mode == _RAMPFORGE_8_ORANGE_MODE for mode in dark_modes)


def test_generate_palette_source_rampforge_8_prefers_midtone_bucket_representatives_over_dark_outliers() -> None:
    workspace = ColorWorkspace()
    labels = [
        [0x8A5A30, 0x8A5A30, 0x8A5A30, 0x8A5A30, 0xAA5533],
        [0x121B46, 0x4070D8, 0x5C4508, 0xC49A18, 0x8A5A30],
        [0x8A5A30, 0x8A5A30, 0xAA6A33, 0x8A5A30, 0x8A5A30],
        [0x8A5A30, 0x8A5A30, 0x8A5A30, 0x8A5A30, 0x8A5A30],
    ]

    palette = generate_palette_source(labels, colors=99, method="rampforge-8")
    seed_metrics = {int(metric.label): metric for metric in _palette_metrics([ramp.seed_label for ramp in palette.ramps[:-2]], workspace)}
    blue_candidates = {0x121B46, 0x4070D8}
    yellow_candidates = {0x5C4508, 0xC49A18}

    chosen_blue = next(label for label in seed_metrics if label in blue_candidates)
    chosen_yellow = next(label for label in seed_metrics if label in yellow_candidates)

    assert seed_metrics[chosen_blue].lightness >= 0.35
    assert seed_metrics[chosen_yellow].lightness >= 0.35


def test_generate_palette_source_rampforge_8_avoids_neutralish_chromatic_seed_when_vivid_hues_exist() -> None:
    workspace = ColorWorkspace()
    labels = [
        [0x111111, 0xF2F2F2, 0x8A5A30, 0x8A5A30, 0x8A5A30],
        [0x6A6A6A, 0x8A5A30, 0xAA6A33, 0x8A5A30, 0xAA5533],
        [0x8A5A30, 0x8A5A30, 0x8A5A30, 0xDCC322, 0x8A5A30],
        [0x8A5A30, 0x8A5A30, 0x2E63D8, 0x8A5A30, 0x8A5A30],
    ]

    palette = generate_palette_source(labels, colors=99, method="rampforge-8")
    seed_labels = [ramp.seed_label for ramp in palette.ramps[:-2]]
    flattened = {color.label for ramp in palette.ramps for color in ramp.colors}
    yellow_candidates = _rampforge_vivid_candidates(labels, PALETTE_SELECT_HUE_YELLOW, workspace)
    blue_candidates = _rampforge_vivid_candidates(labels, PALETTE_SELECT_HUE_BLUE, workspace)

    assert 0x000000 in flattened
    assert 0xFFFFFF in flattened
    assert any(label in yellow_candidates for label in seed_labels)
    assert any(label in blue_candidates for label in seed_labels)
    assert all(not metric.is_neutral for metric in _palette_metrics(seed_labels, workspace))


def test_generate_palette_source_rampforge_8_recovery_reduces_weighted_mapping_error() -> None:
    workspace = ColorWorkspace()
    labels = [
        [0x8A5A30, 0x8A5A30, 0x8A5A30, 0x8A5A30, 0xC54444],
        [0x8A5A30, 0xC77A21, 0xD4B030, 0x55AA33, 0x4477AA],
        [0xAA55AA, 0x33AACC, 0x8C1E1E, 0x8C1E1E, 0x8A5A30],
        [0xAA5533, 0x6A4125, 0xDCC322, 0x2E63D8, 0x8A5A30],
    ]

    baseline = _build_rampforge_baseline_palette(labels, workspace)
    palette = generate_palette_source(labels, colors=99, method="rampforge-8")

    assert _weighted_palette_error(labels, palette, workspace) <= _weighted_palette_error(labels, baseline, workspace)


def test_generate_palette_source_rampforge_8_recovers_second_rich_red_variant() -> None:
    workspace = ColorWorkspace()
    labels = [
        [0x8A5A30, 0x8A5A30, 0x8A5A30, 0xC54444, 0xC54444],
        [0x8A5A30, 0xC77A21, 0xD4B030, 0x55AA33, 0x4477AA],
        [0xAA55AA, 0x33AACC, 0xA92D2D, 0xA92D2D, 0x8A5A30],
        [0xAA5533, 0x6A4125, 0xDCC322, 0x2E63D8, 0x8A5A30],
    ]

    baseline = _build_rampforge_baseline_palette(labels, workspace)
    palette = generate_palette_source(labels, colors=99, method="rampforge-8")
    baseline_labels = {color.label for color in baseline.flattened_colors()}
    final_labels = {color.label for color in palette.flattened_colors()}

    assert 0xA92D2D not in baseline_labels
    assert 0xA92D2D in final_labels


def test_rampforge_8_recovery_prefers_same_family_slots_for_warm_candidates() -> None:
    red_slot = _Rampforge8ReplaceableSlot(
        palette_index=0,
        ramp_index=0,
        ramp_mode=PALETTE_SELECT_HUE_RED,
        shade_index=0,
        lightness=0.38,
        seed_lightness=0.50,
        mapped_weight=0.0,
        redundancy_distance=0.0,
        outer_distance=2,
    )
    blue_slot = _Rampforge8ReplaceableSlot(
        palette_index=1,
        ramp_index=1,
        ramp_mode=PALETTE_SELECT_HUE_BLUE,
        shade_index=0,
        lightness=0.38,
        seed_lightness=0.50,
        mapped_weight=0.0,
        redundancy_distance=0.0,
        outer_distance=2,
    )
    candidate = _Rampforge8RecoveryCandidate(
        label=0x8C1E1E,
        mode=PALETTE_SELECT_HUE_RED,
        lightness=0.35,
        weight=1.0,
        weighted_error=1.0,
        score=1.0,
    )

    assert _rampforge_8_assignment_key(red_slot, candidate) < _rampforge_8_assignment_key(blue_slot, candidate)


def test_generate_palette_source_rampforge_8_recovery_skips_near_duplicate_source_candidates() -> None:
    workspace = ColorWorkspace()
    labels = [
        [0xC54444, 0xC54444, 0x8A5A30, 0x8A5A30, 0x8A5A30],
        [0xC64343, 0x8A5A30, 0xC77A21, 0xD4B030, 0x55AA33],
        [0x4477AA, 0xAA55AA, 0x33AACC, 0x8A5A30, 0x8A5A30],
    ]

    baseline = _build_rampforge_baseline_palette(labels, workspace)
    palette = generate_palette_source(labels, colors=99, method="rampforge-8")

    assert any(label in {0xC54444, 0xC64343} for label in {ramp.seed_label for ramp in baseline.ramps[:-2]})
    assert any(label in {0xC54444, 0xC64343} for label in {color.label for color in palette.flattened_colors()})
    assert 0xC64343 not in {color.label for color in palette.flattened_colors()}


def test_generate_palette_source_rampforge_8_recovery_is_noop_without_missing_candidates() -> None:
    workspace = ColorWorkspace()
    labels = [
        [0x101010, 0x101010, 0xF0F0F0],
        [0xF0F0F0, 0x101010, 0xF0F0F0],
    ]

    baseline = _build_rampforge_baseline_palette(labels, workspace)
    palette = generate_palette_source(labels, colors=99, method="rampforge-8")

    assert [color.label for color in palette.flattened_colors()] == [color.label for color in baseline.flattened_colors()]


def test_generate_palette_source_rampforge_8_handles_empty_input() -> None:
    palette = generate_palette_source([], colors=4, method="rampforge-8")

    assert isinstance(palette, StructuredPalette)
    assert palette.source_mode == "rampforge-8"
    assert palette.palette_size() == 0


def test_color_replacement_variants() -> None:
    labels = [[0x101010, 0x202020], [0x111111, 0x303030]]
    assert replace_exact(labels, 0x202020, 0xAAAAAA)[0][1] == 0xAAAAAA
    tol = replace_tolerance(labels, 0x101010, 0xBBBBBB, tolerance=2)
    assert tol[1][0] == 0xBBBBBB
    batch = replace_batch(labels, {0x303030: 0xCCCCCC})
    assert batch[1][1] == 0xCCCCCC


def test_oklab_workspace_roundtrip_and_cache_reuse() -> None:
    workspace = ColorWorkspace()
    labels = np.asarray([0x112233, 0xABCDEF, 0x112233], dtype=np.int64)
    converted = workspace.labels_to_oklab(labels)
    assert converted.shape == (3, 3)
    assert workspace.cache_size() == 2
    workspace.labels_to_oklab(labels)
    assert workspace.cache_size() == 2

    rebuilt = [workspace.oklab_to_label(color) for color in converted]
    for actual, expected in zip(rebuilt, labels.tolist(), strict=True):
        for shift in (16, 8, 0):
            assert abs(((actual >> shift) & 0xFF) - ((expected >> shift) & 0xFF)) <= 1


def test_hyab_distance_prefers_perceptually_similar_colour() -> None:
    workspace = ColorWorkspace()
    points = workspace.labels_to_oklab(np.asarray([0x808080, 0x8A8A8A, 0x33AA00], dtype=np.int64))
    similar = float(hyab_distance(points[0:1], points[1:2])[0])
    different = float(hyab_distance(points[0:1], points[2:3])[0])
    assert similar < different


def test_generate_structured_palette_builds_monotonic_ramps() -> None:
    labels = [
        [0x6AAAD8, 0x6AAAD8, 0x355E7D],
        [0xD8B06A, 0x6AAAD8, 0x355E7D],
        [0x254060, 0xD8B06A, 0x254060],
    ]
    computation = generate_structured_palette(
        labels,
        key_colors=[0x6AAAD8, 0xD8B06A, 0x355E7D],
        generated_shades=4,
        contrast_bias=1.2,
    )
    palette = computation.palette
    assert palette.source_mode == "advanced"
    assert len(palette.ramps) == 3
    assert palette.generated_shades == 4
    for ramp in palette.ramps:
        lightness = [color.oklab[0] for color in ramp.colors]
        assert lightness == sorted(lightness)
        assert len(ramp.colors) == 5
        assert ramp.colors[len(ramp.colors) // 2].is_seed


def test_generate_structured_palette_caps_key_colours_at_twenty_four() -> None:
    computation = generate_structured_palette(
        [],
        key_colors=[index for index in range(32)],
        generated_shades=2,
    )
    assert len(computation.palette.key_colors) == 24
    assert len(computation.palette.ramps) == 24


def test_merge_palette_labels_uses_oklab_channel_median() -> None:
    workspace = ColorWorkspace()
    labels = [0xFF0000, 0x00FF00, 0x0000FF]

    merged = merge_palette_labels(labels, workspace=workspace)
    expected = workspace.oklab_to_label(np.median(workspace.labels_to_oklab(labels), axis=0))

    assert merged == expected


def test_generate_ramp_palette_labels_matches_existing_seed_ramp() -> None:
    labels = generate_ramp_palette_labels(
        [0x336699],
        generated_shades=2,
        contrast_bias=0.7,
    )
    expected = generate_structured_palette(
        [],
        key_colors=[0x336699],
        generated_shades=2,
        contrast_bias=0.7,
    ).palette.labels()

    assert labels == expected


def test_generate_ramp_palette_labels_supports_more_than_twenty_four_seeds() -> None:
    labels = generate_ramp_palette_labels(
        [index for index in range(25)],
        generated_shades=2,
        contrast_bias=1.0,
    )

    assert len(labels) == 25 * 3


def test_adjust_palette_labels_changes_palette_in_oklab_space() -> None:
    labels = [0x336699, 0x88AACC, 0xCC8844]
    adjusted = adjust_palette_labels(
        labels,
        PaletteAdjustments(brightness=15, contrast=130, hue=20, saturation=140),
    )
    assert len(adjusted) == len(labels)
    assert adjusted != labels
    assert all(isinstance(value, int) and 0 <= value <= 0xFFFFFF for value in adjusted)


def test_adjust_palette_labels_only_changes_selected_indices() -> None:
    labels = [0x336699, 0x88AACC, 0xCC8844]

    adjusted = adjust_palette_labels(
        labels,
        PaletteAdjustments(brightness=15, contrast=130, hue=20, saturation=140),
        selected_indices={1},
    )

    assert adjusted[0] == labels[0]
    assert adjusted[1] != labels[1]
    assert adjusted[2] == labels[2]


def test_adjust_structured_palette_preserves_ramp_structure() -> None:
    palette = generate_structured_palette(
        [],
        key_colors=[0x336699, 0xCC8844],
        generated_shades=2,
    ).palette
    adjusted = adjust_structured_palette(
        palette,
        PaletteAdjustments(brightness=10, contrast=120, saturation=130),
    )
    assert len(adjusted.ramps) == len(palette.ramps)
    assert [len(ramp.colors) for ramp in adjusted.ramps] == [len(ramp.colors) for ramp in palette.ramps]
    assert adjusted.labels() != palette.labels()
    for ramp in adjusted.ramps:
        seed_color = next(color for color in ramp.colors if color.is_seed)
        assert ramp.seed_label == seed_color.label


def test_adjust_structured_palette_only_changes_selected_indices() -> None:
    palette = generate_structured_palette(
        [],
        key_colors=[0x336699, 0xCC8844],
        generated_shades=2,
    ).palette

    adjusted = adjust_structured_palette(
        palette,
        PaletteAdjustments(brightness=10, contrast=120, saturation=130),
        selected_indices={1},
    )

    original_labels = palette.labels()
    adjusted_labels = adjusted.labels()
    assert adjusted_labels[0] == original_labels[0]
    assert adjusted_labels[1] != original_labels[1]
    assert adjusted_labels[2:] == original_labels[2:]


def test_detect_key_colors_ignores_transparent_pixels() -> None:
    image = Image.new("RGBA", (4, 1))
    image.putdata(
        [
            (255, 0, 0, 0),
            (255, 0, 0, 0),
            (0, 0, 255, 255),
            (0, 0, 255, 255),
        ]
    )
    assert detect_key_colors_from_image(image) == [0x0000FF]


def test_detect_key_colors_picks_dominant_midtone() -> None:
    mid = (180, 40, 40, 255)
    dark = (90, 10, 10, 255)
    light = (250, 170, 170, 255)
    image = Image.new("RGBA", (16, 1))
    image.putdata([mid] * 10 + [dark] * 3 + [light] * 3)
    detected = detect_key_colors_from_image(image, max_colors=1)
    assert detected == [0xB42828]


def test_detect_key_colors_includes_neutral_family_when_significant() -> None:
    gray = (136, 136, 136, 255)
    red = (220, 60, 60, 255)
    blue = (70, 110, 220, 255)
    image = Image.new("RGBA", (10, 10))
    image.putdata(([gray] * 20) + ([red] * 40) + ([blue] * 40))
    detected = detect_key_colors_from_image(image)
    assert 0x888888 in detected
    assert 0xDC3C3C in detected
    assert 0x466EDC in detected


def test_detect_key_colors_drops_minor_hue_families() -> None:
    red = (220, 60, 60, 255)
    blue = (70, 110, 220, 255)
    green = (40, 200, 70, 255)
    image = Image.new("RGBA", (10, 10))
    image.putdata(([red] * 49) + ([blue] * 49) + ([green] * 2))
    detected = detect_key_colors_from_image(image)
    assert 0x28C846 not in detected
    assert 0xDC3C3C in detected
    assert 0x466EDC in detected


def test_detect_key_colors_returns_exact_source_colours() -> None:
    colors = [
        (217, 150, 83, 255),
        (95, 164, 233, 255),
        (44, 80, 120, 255),
        (189, 204, 109, 255),
    ]
    image = Image.new("RGBA", (4, 4))
    image.putdata(colors * 4)
    detected = detect_key_colors_from_image(image, max_colors=4)
    valid = {(red << 16) | (green << 8) | blue for red, green, blue, _alpha in colors}
    assert set(detected).issubset(valid)


def test_detect_key_colors_backfills_toward_requested_count() -> None:
    colors = [
        (90, 20, 20, 255),
        (140, 30, 30, 255),
        (190, 45, 45, 255),
        (240, 120, 120, 255),
        (50, 90, 210, 255),
    ]
    image = Image.new("RGBA", (25, 1))
    image.putdata(colors * 5)
    detected = detect_key_colors_from_image(image, max_colors=4)
    valid = {(red << 16) | (green << 8) | blue for red, green, blue, _alpha in colors}
    assert len(detected) == 4
    assert set(detected).issubset(valid)

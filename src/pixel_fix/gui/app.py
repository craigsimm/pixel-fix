from __future__ import annotations

import sys
import threading
import tkinter as tk
from dataclasses import dataclass, replace
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageDraw, ImageTk

from pixel_fix.palette.adjust import PaletteAdjustments, adjust_structured_palette
from pixel_fix.palette.advanced import detect_key_colors_from_image, generate_structured_palette, structured_palette_from_override
from pixel_fix.palette.color_modes import extract_unique_colors
from pixel_fix.palette.io import load_palette, save_palette
from pixel_fix.palette.catalog import PaletteCatalogEntry, discover_palette_catalog
from pixel_fix.palette.model import StructuredPalette, clone_structured_palette
from pixel_fix.palette.quantize import generate_palette as generate_override_palette
from pixel_fix.palette.sort import (
    PALETTE_SELECT_DIRECT_MODES,
    PALETTE_SELECT_HUE_MODES,
    PALETTE_SELECT_LABELS,
    PALETTE_SELECT_MODES,
    PALETTE_SORT_CHROMA,
    PALETTE_SORT_HUE,
    PALETTE_SORT_LABELS,
    PALETTE_SORT_LIGHTNESS,
    PALETTE_SORT_MODES,
    PALETTE_SORT_SATURATION,
    PALETTE_SORT_TEMPERATURE,
    select_palette_indices,
    sort_palette_labels,
)
from pixel_fix.palette.workspace import ColorWorkspace
from pixel_fix.pipeline import PipelineConfig
from pixel_fix.resample import resize_labels, target_size_for_pixel_width

from .persist import (
    append_process_log,
    coerce_selection_threshold,
    deserialize_settings,
    diff_snapshots,
    load_app_state,
    make_process_snapshot,
    save_app_state,
    serialize_settings,
)
from .processing import (
    ProcessResult,
    RGBGrid,
    add_exterior_outline,
    apply_transparency_fill,
    display_resize_method,
    downsample_image,
    grid_to_pil_image,
    image_to_rgb_grid,
    labels_to_rgb,
    load_png_rgba_image,
    remove_exterior_outline,
    reduce_palette_image,
    rgb_to_labels,
)
from .state import PreviewSettings, SettingsSession
from .zoom import ZOOM_PRESETS, choose_fit_zoom, clamp_zoom, zoom_in, zoom_out

OPEN_HAND_CURSOR = "hand2"
CLOSED_HAND_CURSOR = "fleur"
PRIMARY_BUTTON_INACTIVE_BG = "#111C42"
PRIMARY_BUTTON_INACTIVE_FG = "#207BC8"
PRIMARY_BUTTON_ACTIVE_BG = "#42BAF0"
PRIMARY_BUTTON_ACTIVE_FG = "#FFFFFF"
PRIMARY_BUTTON_HOVER_BG = "#7FD9F8"
PRIMARY_BUTTON_HOVER_FG = "#FFFFFF"
MAX_PALETTE_SWATCHES = 256
PALETTE_SWATCH_SIZE = 18
PALETTE_SWATCH_GAP = 4
MAX_RECENT_FILES = 10
MAX_KEY_COLORS = 24
SELECTION_THRESHOLD_OPTIONS = tuple(range(10, 101, 10))
PALETTE_SORT_OPTIONS = (
    (PALETTE_SORT_LABELS[PALETTE_SORT_LIGHTNESS], PALETTE_SORT_LIGHTNESS),
    (PALETTE_SORT_LABELS[PALETTE_SORT_HUE], PALETTE_SORT_HUE),
    (PALETTE_SORT_LABELS[PALETTE_SORT_SATURATION], PALETTE_SORT_SATURATION),
    (PALETTE_SORT_LABELS[PALETTE_SORT_CHROMA], PALETTE_SORT_CHROMA),
    (PALETTE_SORT_LABELS[PALETTE_SORT_TEMPERATURE], PALETTE_SORT_TEMPERATURE),
)
PALETTE_SELECT_OPTIONS = tuple((PALETTE_SELECT_LABELS[mode], mode) for mode in PALETTE_SELECT_DIRECT_MODES)
PALETTE_SELECT_HUE_OPTIONS = tuple((PALETTE_SELECT_LABELS[mode].removeprefix("Hue (").removesuffix(")"), mode) for mode in PALETTE_SELECT_HUE_MODES)

RESIZE_OPTIONS = (
    ("Nearest Neighbor", "nearest"),
    ("Bilinear Interpolation", "bilinear"),
    ("RotSprite", "rotsprite"),
)
QUANTIZER_OPTIONS = (
    ("Median Cut", "median-cut"),
    ("K-Means Clustering", "kmeans"),
)
DITHER_OPTIONS = (
    ("None", "none"),
    ("Ordered (Bayer)", "ordered"),
    ("Blue Noise", "blue-noise"),
)
GENERATED_SHADES_OPTIONS = (2, 4, 6, 8, 10)
AUTO_DETECT_COUNT_OPTIONS = tuple(range(1, MAX_KEY_COLORS + 1))
RAMP_CONTRAST_OPTIONS = tuple(range(10, 101, 10))
COLOR_MODE_OPTIONS = (
    ("RGBA", "rgba"),
    ("Indexed", "indexed"),
    ("Grayscale", "grayscale"),
)

RESIZE_DISPLAY_TO_VALUE = {label: value for (label, value) in RESIZE_OPTIONS}
RESIZE_VALUE_TO_DISPLAY = {value: label for (label, value) in RESIZE_OPTIONS}
QUANTIZER_DISPLAY_TO_VALUE = {label: value for (label, value) in QUANTIZER_OPTIONS}
QUANTIZER_VALUE_TO_DISPLAY = {value: label for (label, value) in QUANTIZER_OPTIONS}
DITHER_DISPLAY_TO_VALUE = {label: value for (label, value) in DITHER_OPTIONS}
DITHER_VALUE_TO_DISPLAY = {value: label for (label, value) in DITHER_OPTIONS}
COLOR_MODE_DISPLAY_TO_VALUE = {label: value for (label, value) in COLOR_MODE_OPTIONS}
COLOR_MODE_VALUE_TO_DISPLAY = {value: label for (label, value) in COLOR_MODE_OPTIONS}


@dataclass
class CanvasDisplay:
    image_left: int
    image_top: int
    display_width: int
    display_height: int
    sample_image: Image.Image | None


@dataclass
class PaletteUndoState:
    palette_result: ProcessResult | None
    downsample_display_image: Image.Image | None
    palette_display_image: Image.Image | None
    image_state: str
    last_successful_process_snapshot: dict[str, object] | None
    active_palette: list[int] | None
    active_palette_source: str
    active_palette_path: str | None
    advanced_palette_preview: StructuredPalette | None
    transparent_colors: tuple[int, ...]
    settings: PreviewSettings
    downsample_result: ProcessResult | None = None
    palette_sort_reset_labels: tuple[int, ...] = ()
    palette_sort_reset_source: str | None = None
    palette_sort_reset_path: str | None = None


class PixelFixGui:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Pixel-Fix")
        self.root.geometry("1660x920")
        self._configure_window_icon()

        persisted = load_app_state()
        persisted_settings = deserialize_settings(persisted.get("settings"))
        self.session = SettingsSession(
            replace(
                persisted_settings,
                palette_brightness=0,
                palette_contrast=100,
                palette_hue=0,
                palette_saturation=100,
            )
        )
        self.source_path: Path | None = None
        self.original_grid: RGBGrid | None = None
        self.original_display_image: Image.Image | None = None
        self.downsample_result: ProcessResult | None = None
        self.palette_result: ProcessResult | None = None
        self.downsample_display_image: Image.Image | None = None
        self.palette_display_image: Image.Image | None = None
        self.comparison_original_image: Image.Image | None = None
        self._comparison_original_key: tuple[object, ...] | None = None
        self.prepared_input_cache = None
        self.prepared_input_cache_key: tuple[object, ...] | None = None
        self.workspace = ColorWorkspace()
        self.active_palette: list[int] | None = None
        self.active_palette_source = ""
        self.active_palette_path: str | None = None
        self.transparent_colors: set[int] = set()
        self.key_colors: list[int] = []
        self.advanced_palette_preview: StructuredPalette | None = None
        self.key_color_pick_mode = False
        self.palette_add_pick_mode = False
        self.transparency_pick_mode = False
        self._palette_selection_indices: set[int] = set()
        self._palette_selection_anchor_index: int | None = None
        self._palette_ctrl_drag_active = False
        self._palette_ctrl_drag_anchor_index: int | None = None
        self._palette_ctrl_drag_indices: set[int] = set()
        self._palette_ctrl_drag_initial_selection: set[int] = set()
        self._palette_hit_regions: list[tuple[int, int, int, int]] = []
        self._displayed_palette: list[int] = []
        self._adjusted_palette_cache_key: tuple[object, ...] | None = None
        self._adjusted_palette_cache: StructuredPalette | None = None
        self._palette_sort_reset_labels: list[int] | None = None
        self._palette_sort_reset_source: str | None = None
        self._palette_sort_reset_path: str | None = None
        self.builtin_palette_entries = discover_palette_catalog(self._resource_path("palettes"))
        self._builtin_palette_by_path = {str(entry.path): entry for entry in self.builtin_palette_entries}
        self.last_output_path = persisted.get("last_output_path")
        self.last_successful_process_snapshot = persisted.get("last_successful_process_snapshot")
        self.recent_files = self._normalize_recent_files(persisted.get("recent_files"))
        self.image_state = "loaded_original"

        self.zoom = clamp_zoom(int(persisted.get("zoom", 100)))
        self.pan_x = 0
        self.pan_y = 0
        self.dragging = False
        self.drag_origin = (0, 0)
        self.drag_pan_start = (0, 0)
        self.quick_compare_active = False
        self._display_context: CanvasDisplay | None = None
        self._image_ref: ImageTk.PhotoImage | None = None
        self._persist_after_id: str | None = None
        self._suspend_control_events = False
        self._palette_undo_state: PaletteUndoState | None = None

        self.view_var = tk.StringVar(value=str(persisted.get("view_mode", "original")))
        if self.view_var.get() not in {"original", "processed"}:
            self.view_var.set("original")
        self.selection_threshold_var = tk.IntVar(value=coerce_selection_threshold(persisted.get("selection_threshold", 30)))
        self.pixel_width_var = tk.IntVar()
        self.downsample_mode_var = tk.StringVar()
        self.palette_reduction_colors_var = tk.IntVar()
        self.generated_shades_var = tk.StringVar()
        self.auto_detect_count_var = tk.StringVar()
        self.contrast_bias_var = tk.DoubleVar()
        self.palette_brightness_var = tk.IntVar()
        self.palette_contrast_var = tk.IntVar()
        self.palette_hue_var = tk.IntVar()
        self.palette_saturation_var = tk.IntVar()
        self.palette_dither_var = tk.StringVar()
        self.input_mode_var = tk.StringVar()
        self.output_mode_var = tk.StringVar()
        self.quantizer_var = tk.StringVar()
        self.dither_var = tk.StringVar()
        self.checkerboard_var = tk.BooleanVar(value=bool(persisted.get("checkerboard", False)))
        self.process_status_var = tk.StringVar(value="Open a PNG image to begin.")
        self.scale_info_var = tk.StringVar(value="Open an image to set the pixel size.")
        self.key_colors_label_var = tk.StringVar(value="Key colours (0)")
        self.palette_info_var = tk.StringVar(value="Palette: none")
        self.image_info_var = tk.StringVar(value="No image  -  100%")
        self.pick_preview_var = tk.StringVar(value="")
        self.palette_brightness_value_var = tk.StringVar(value="0")
        self.palette_contrast_value_var = tk.StringVar(value="0%")
        self.palette_hue_value_var = tk.StringVar(value="0 deg")
        self.palette_saturation_value_var = tk.StringVar(value="0%")

        self._menu_items: dict[str, tk.Menu] = {}
        self._build_menu_bar()
        self._build_layout()
        self._sync_controls_from_settings(self.session.current)
        self._update_scale_info()
        self._update_palette_strip()
        self._update_image_info()
        self._refresh_action_states()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_window_icon(self) -> None:
        ico_path = self._resource_path("pixel-fix.ico")
        if ico_path.exists():
            try:
                self.root.iconbitmap(default=str(ico_path))
            except tk.TclError:
                pass
        icon_path = self._resource_path("ico-32.png")
        if icon_path.exists():
            try:
                self.root.iconphoto(True, tk.PhotoImage(file=str(icon_path)))
            except tk.TclError:
                pass

    @staticmethod
    def _resource_path(name: str) -> Path:
        if hasattr(sys, "_MEIPASS"):
            return Path(getattr(sys, "_MEIPASS")) / name
        return Path(__file__).resolve().parents[3] / name

    def _build_menu_bar(self) -> None:
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Open...", accelerator="Ctrl+O", command=self.open_image)
        self.recent_menu = tk.Menu(file_menu, tearoff=False)
        file_menu.add_cascade(label="Recent", menu=self.recent_menu)
        file_menu.add_separator()
        file_menu.add_command(label="Save", accelerator="Ctrl+S", command=self.save_processed_image)
        file_menu.add_command(label="Save As...", accelerator="Ctrl+Shift+S", command=self.save_processed_image_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", accelerator="Alt+F4", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=False)
        edit_menu.add_command(label="Undo", accelerator="Ctrl+Z", command=self.undo)
        edit_menu.add_command(label="Downsample", accelerator="F5", command=self.downsample_current_image)
        edit_menu.add_command(label="Apply Palette", accelerator="F6", command=self.reduce_palette_current_image)
        menubar.add_cascade(label="Edit", menu=edit_menu)

        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_radiobutton(label="Original", value="original", variable=self.view_var, accelerator="Ctrl+1", command=self._on_view_changed)
        view_menu.add_radiobutton(label="Processed", value="processed", variable=self.view_var, accelerator="Ctrl+2", command=self._on_view_changed)
        menubar.add_cascade(label="View", menu=view_menu)

        palette_menu = tk.Menu(menubar, tearoff=False)
        input_menu = tk.Menu(palette_menu, tearoff=False)
        for label, _value in COLOR_MODE_OPTIONS:
            input_menu.add_radiobutton(label=label, value=label, variable=self.input_mode_var, command=self._on_settings_changed)
        output_menu = tk.Menu(palette_menu, tearoff=False)
        for label, _value in COLOR_MODE_OPTIONS:
            output_menu.add_radiobutton(label=label, value=label, variable=self.output_mode_var, command=self._on_settings_changed)
        built_in_menu = tk.Menu(palette_menu, tearoff=False)
        add_colour_menu = tk.Menu(palette_menu, tearoff=False)
        sort_menu = tk.Menu(palette_menu, tearoff=False)
        add_colour_menu.add_command(label="Pick From Original", command=self._start_palette_add_pick_mode)
        add_colour_menu.add_command(label="Enter Hex Code...", command=self._prompt_add_palette_color_hex)
        palette_menu.add_cascade(label="Input Mode", menu=input_menu)
        palette_menu.add_cascade(label="Output Mode", menu=output_menu)
        palette_menu.add_separator()
        palette_menu.add_cascade(label="Built-in Palettes", menu=built_in_menu)
        palette_menu.add_cascade(label="Add Colour", menu=add_colour_menu)
        palette_menu.add_cascade(label="Sort Current Palette", menu=sort_menu)
        palette_menu.add_command(label="Load Palette...", command=self.load_palette_file)
        palette_menu.add_command(label="Save Current Palette...", command=self.save_palette_file)
        menubar.add_cascade(label="Palette", menu=palette_menu)

        select_menu = tk.Menu(menubar, tearoff=False)
        select_hue_menu = tk.Menu(select_menu, tearoff=False)
        for label, mode in PALETTE_SELECT_OPTIONS:
            select_menu.add_command(label=label, command=lambda value=mode: self.select_current_palette(value))
        select_menu.add_cascade(label="Hue", menu=select_hue_menu)
        for label, mode in PALETTE_SELECT_HUE_OPTIONS:
            select_hue_menu.add_command(label=label, command=lambda value=mode: self.select_current_palette(value))
        menubar.add_cascade(label="Select", menu=select_menu)

        zoom_menu = tk.Menu(menubar, tearoff=False)
        for value in ZOOM_PRESETS:
            zoom_menu.add_command(label=f"{value}%", command=lambda zoom=value: self._set_zoom(zoom))
        zoom_menu.add_separator()
        zoom_menu.add_command(label="Fit", accelerator="Ctrl+0", command=self.zoom_fit)
        menubar.add_cascade(label="Zoom", menu=zoom_menu)

        preferences_menu = tk.Menu(menubar, tearoff=False)
        resize_menu = tk.Menu(preferences_menu, tearoff=False)
        for label, _value in RESIZE_OPTIONS:
            resize_menu.add_radiobutton(label=label, value=label, variable=self.downsample_mode_var, command=self._on_settings_changed)
        palette_reduction_menu = tk.Menu(preferences_menu, tearoff=False)
        for label, _value in QUANTIZER_OPTIONS:
            palette_reduction_menu.add_radiobutton(label=label, value=label, variable=self.quantizer_var, command=self._on_settings_changed)
        colour_ramp_menu = tk.Menu(preferences_menu, tearoff=False)
        auto_detect_menu = tk.Menu(colour_ramp_menu, tearoff=False)
        for value in AUTO_DETECT_COUNT_OPTIONS:
            auto_detect_menu.add_radiobutton(label=str(value), value=str(value), variable=self.auto_detect_count_var, command=self._on_settings_changed)
        ramp_steps_menu = tk.Menu(colour_ramp_menu, tearoff=False)
        for value in GENERATED_SHADES_OPTIONS:
            ramp_steps_menu.add_radiobutton(label=str(value), value=str(value), variable=self.generated_shades_var, command=self._on_settings_changed)
        ramp_contrast_menu = tk.Menu(colour_ramp_menu, tearoff=False)
        for value in RAMP_CONTRAST_OPTIONS:
            ramp_contrast_menu.add_radiobutton(label=f"{value}%", value=value / 100.0, variable=self.contrast_bias_var, command=self._on_settings_changed)
        colour_ramp_menu.add_cascade(label="Auto Detect Count", menu=auto_detect_menu)
        colour_ramp_menu.add_cascade(label="Ramp Steps", menu=ramp_steps_menu)
        colour_ramp_menu.add_cascade(label="Ramp Contrast", menu=ramp_contrast_menu)
        dithering_menu = tk.Menu(preferences_menu, tearoff=False)
        for label, _value in DITHER_OPTIONS:
            dithering_menu.add_radiobutton(label=label, value=label, variable=self.palette_dither_var, command=self._on_settings_changed)
        selection_threshold_menu = tk.Menu(preferences_menu, tearoff=False)
        for value in SELECTION_THRESHOLD_OPTIONS:
            selection_threshold_menu.add_radiobutton(
                label=f"{value}%",
                value=value,
                variable=self.selection_threshold_var,
                command=self._on_selection_threshold_changed,
            )
        preferences_menu.add_checkbutton(label="Checkerboard background", variable=self.checkerboard_var, command=self._on_overlay_changed)
        preferences_menu.add_separator()
        preferences_menu.add_cascade(label="Resize Method", menu=resize_menu)
        preferences_menu.add_cascade(label="Palette Reduction Method", menu=palette_reduction_menu)
        preferences_menu.add_cascade(label="Colour Ramp", menu=colour_ramp_menu)
        preferences_menu.add_cascade(label="Dithering Method", menu=dithering_menu)
        preferences_menu.add_cascade(label="Selection Threshold", menu=selection_threshold_menu)
        menubar.add_cascade(label="Preferences", menu=preferences_menu)

        self._menu_bar = menubar
        self.root.config(menu=menubar)
        self._menu_items["file"] = file_menu
        self._menu_items["edit"] = edit_menu
        self._menu_items["view"] = view_menu
        self._menu_items["palette"] = palette_menu
        self._menu_items["select"] = select_menu
        self._menu_items["select_hue"] = select_hue_menu
        self._menu_items["palette_input"] = input_menu
        self._menu_items["palette_output"] = output_menu
        self._menu_items["built_in_palettes"] = built_in_menu
        self._menu_items["palette_add"] = add_colour_menu
        self._menu_items["palette_sort"] = sort_menu
        self._menu_items["preferences"] = preferences_menu
        self._menu_items["preferences_resize"] = resize_menu
        self._menu_items["preferences_palette_reduction"] = palette_reduction_menu
        self._menu_items["preferences_colour_ramp"] = colour_ramp_menu
        self._menu_items["preferences_dithering"] = dithering_menu
        self._menu_items["preferences_selection_threshold"] = selection_threshold_menu
        self._populate_builtin_palette_menu()
        self._populate_palette_sort_menu()
        self._refresh_recent_menu()

    def _build_layout(self) -> None:
        body = ttk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        sidebar = ttk.Frame(body, width=360)
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        sidebar.pack_propagate(False)

        scale_section = self._create_section(sidebar, "1. Determine pixel scale")
        row = ttk.Frame(scale_section)
        row.pack(fill=tk.X)
        ttk.Label(row, text="Pixel size").pack(side=tk.LEFT)
        self.pixel_width_spinbox = ttk.Spinbox(row, from_=1, to=512, textvariable=self.pixel_width_var, width=8, command=self._on_settings_changed)
        self.pixel_width_spinbox.pack(side=tk.RIGHT)
        ttk.Label(scale_section, textvariable=self.scale_info_var, wraplength=300).pack(anchor=tk.W, pady=(6, 0))

        downsample_section = self._create_section(sidebar, "2. Downsample")
        self.downsample_button = tk.Button(downsample_section, text="Downsample", command=self.downsample_current_image, relief=tk.FLAT, padx=14, pady=4)
        self.downsample_button.pack(anchor=tk.W, pady=(4, 0))

        palette_section = self._create_section(sidebar, "3. Apply palette")
        ttk.Label(palette_section, textvariable=self.key_colors_label_var).pack(anchor=tk.W)
        self.key_color_listbox = tk.Listbox(
            palette_section,
            height=8,
            selectmode=tk.EXTENDED,
            exportselection=False,
            activestyle="dotbox",
        )
        self.key_color_listbox.pack(fill=tk.X, pady=(6, 0))
        self.key_color_listbox.bind("<<ListboxSelect>>", lambda _event: self._refresh_action_states(), add="+")
        button_row = ttk.Frame(palette_section)
        button_row.pack(fill=tk.X, pady=(6, 0))
        self.pick_seed_button = ttk.Button(button_row, text="Pick Colour", command=self._toggle_seed_pick_mode)
        self.pick_seed_button.pack(side=tk.LEFT)
        self.auto_detect_button = ttk.Button(button_row, text="Auto Detect Key Colours", command=self._auto_detect_key_colors)
        self.auto_detect_button.pack(side=tk.LEFT, padx=(6, 0))
        button_row = ttk.Frame(palette_section)
        button_row.pack(fill=tk.X, pady=(6, 0))
        self.remove_seed_button = ttk.Button(button_row, text="Remove Selected", command=self._remove_selected_seed)
        self.remove_seed_button.pack(side=tk.LEFT)
        self.clear_seeds_button = ttk.Button(button_row, text="Clear All", command=self._clear_advanced_seeds)
        self.clear_seeds_button.pack(side=tk.LEFT, padx=(6, 0))
        row = ttk.Frame(palette_section)
        row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(row, text="Palette Reduction").pack(side=tk.LEFT)
        self.palette_reduction_spinbox = ttk.Spinbox(
            row,
            from_=1,
            to=256,
            textvariable=self.palette_reduction_colors_var,
            width=8,
            command=self._on_settings_changed,
        )
        self.palette_reduction_spinbox.pack(side=tk.RIGHT)
        self.generate_ramps_button = ttk.Button(palette_section, text="Generate Ramps", command=self._regenerate_all_ramps)
        self.generate_ramps_button.pack(anchor=tk.W, pady=(8, 0))
        self.generate_override_palette_button = ttk.Button(
            palette_section,
            text="Generate Reduced Palette",
            command=self.generate_palette_from_image,
        )
        self.generate_override_palette_button.pack(anchor=tk.W, pady=(8, 0))
        self.reduce_palette_button = tk.Button(palette_section, text="Apply Palette", command=self.reduce_palette_current_image, relief=tk.FLAT, padx=14, pady=4)
        self.reduce_palette_button.pack(anchor=tk.W, pady=(8, 0))
        self.transparency_button = ttk.Button(palette_section, text="Make Transparent", command=self._toggle_transparency_pick_mode)
        self.transparency_button.pack(anchor=tk.W, pady=(8, 0))
        outline_row = ttk.Frame(palette_section)
        outline_row.pack(fill=tk.X, pady=(8, 0))
        self.add_outline_button = ttk.Button(outline_row, text="Add Outline", command=self._add_outline_from_selection)
        self.add_outline_button.pack(side=tk.LEFT)
        self.remove_outline_button = ttk.Button(outline_row, text="Remove Outline", command=self._remove_outline)
        self.remove_outline_button.pack(side=tk.LEFT, padx=(6, 0))

        adjust_section = self._create_section(sidebar, "4. Adjust palette")
        self.palette_adjustment_controls: list[tk.Scale] = []
        self.palette_brightness_scale = self._create_palette_adjustment_row(
            adjust_section,
            label="Brightness",
            variable=self.palette_brightness_var,
            value_var=self.palette_brightness_value_var,
            from_=-100,
            to=100,
        )
        self.palette_contrast_scale = self._create_palette_adjustment_row(
            adjust_section,
            label="Contrast",
            variable=self.palette_contrast_var,
            value_var=self.palette_contrast_value_var,
            from_=-100,
            to=100,
        )
        self.palette_hue_scale = self._create_palette_adjustment_row(
            adjust_section,
            label="Hue",
            variable=self.palette_hue_var,
            value_var=self.palette_hue_value_var,
            from_=-180,
            to=180,
        )
        self.palette_saturation_scale = self._create_palette_adjustment_row(
            adjust_section,
            label="Saturation",
            variable=self.palette_saturation_var,
            value_var=self.palette_saturation_value_var,
            from_=-100,
            to=100,
        )

        workspace = ttk.Frame(body)
        workspace.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        palette_frame = ttk.LabelFrame(workspace, text="Current palette")
        palette_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(palette_frame, textvariable=self.palette_info_var).pack(anchor=tk.W, padx=8, pady=(6, 2))
        palette_row = ttk.Frame(palette_frame)
        palette_row.pack(fill=tk.X, padx=8, pady=(0, 8))
        palette_actions = ttk.Frame(palette_row)
        palette_actions.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        self.add_palette_color_button = ttk.Button(palette_actions, text="+", width=3, command=self._toggle_palette_add_pick_mode)
        self.add_palette_color_button.pack(anchor=tk.N)
        self.remove_palette_color_button = ttk.Button(palette_actions, text="-", width=3, command=self._remove_selected_palette_colors)
        self.remove_palette_color_button.pack(anchor=tk.N, pady=(4, 0))
        self.select_all_palette_button = ttk.Button(palette_actions, text="All", width=4, command=self._select_all_palette_colors)
        self.select_all_palette_button.pack(anchor=tk.N, pady=(8, 0))
        self.clear_palette_selection_button = ttk.Button(palette_actions, text="None", width=4, command=self._clear_palette_selection)
        self.clear_palette_selection_button.pack(anchor=tk.N, pady=(4, 0))
        self.palette_canvas = tk.Canvas(palette_row, height=60, background="#1e1e1e", highlightthickness=0)
        self.palette_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.palette_canvas.bind("<ButtonPress-1>", self._on_palette_canvas_click)
        self.palette_canvas.bind("<B1-Motion>", self._on_palette_canvas_drag)
        self.palette_canvas.bind("<ButtonRelease-1>", self._on_palette_canvas_release)
        self.palette_canvas.bind("<Double-Button-1>", self._on_palette_canvas_double_click)
        self.palette_canvas.bind("<ButtonPress-3>", self._on_palette_canvas_right_click)

        content_row = ttk.Frame(workspace)
        content_row.pack(fill=tk.BOTH, expand=True)

        preview_frame = ttk.Frame(content_row)
        preview_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(preview_frame, background="#222", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        zoom_controls = ttk.Frame(preview_frame)
        zoom_controls.place(relx=1.0, rely=1.0, x=-12, y=-12, anchor=tk.SE)
        self.zoom_out_button = ttk.Button(zoom_controls, text="-", width=3, command=lambda: self._set_zoom(zoom_out(self.zoom)))
        self.zoom_out_button.pack(side=tk.LEFT, padx=(0, 4))
        self.zoom_in_button = ttk.Button(zoom_controls, text="+", width=3, command=lambda: self._set_zoom(zoom_in(self.zoom)))
        self.zoom_in_button.pack(side=tk.LEFT)

        status = ttk.Frame(self.root)
        status.pack(fill=tk.X, padx=10, pady=(0, 8))
        ttk.Label(status, textvariable=self.process_status_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        status_right = ttk.Frame(status)
        status_right.pack(side=tk.RIGHT)
        self.pick_preview_frame = ttk.Frame(status_right)
        self.pick_preview_swatch = tk.Label(self.pick_preview_frame, width=2, height=1, bg="#2A2A2A", relief=tk.SOLID, bd=1)
        self.pick_preview_swatch.pack(side=tk.LEFT)
        self.pick_preview_label = ttk.Label(self.pick_preview_frame, textvariable=self.pick_preview_var, width=9)
        self.pick_preview_label.pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(status_right, textvariable=self.image_info_var).pack(side=tk.RIGHT)

        self.canvas.bind("<Configure>", lambda _event: self.redraw_canvas())
        self.canvas.bind("<MouseWheel>", self._on_zoom_wheel)
        self.canvas.bind("<Control-MouseWheel>", self._on_zoom_wheel)
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Motion>", self._on_canvas_motion)
        self.canvas.bind("<Leave>", self._on_canvas_leave)
        self.canvas.bind("<ButtonPress-3>", self._on_quick_compare_press)
        self.canvas.bind("<ButtonRelease-3>", self._on_quick_compare_release)

        self.pixel_width_spinbox.bind("<KeyRelease>", self._on_settings_changed, add="+")
        self.pixel_width_spinbox.bind("<<Increment>>", self._on_settings_changed, add="+")
        self.pixel_width_spinbox.bind("<<Decrement>>", self._on_settings_changed, add="+")
        self.palette_reduction_spinbox.bind("<KeyRelease>", self._on_settings_changed, add="+")
        self.palette_reduction_spinbox.bind("<<Increment>>", self._on_settings_changed, add="+")
        self.palette_reduction_spinbox.bind("<<Decrement>>", self._on_settings_changed, add="+")

        self._configure_primary_button(self.downsample_button)
        self._configure_primary_button(self.reduce_palette_button)
        self._update_palette_adjustment_labels()
        self._bind_shortcuts()

    def _create_section(self, parent: ttk.Frame, title: str) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text=title)
        frame.pack(fill=tk.X, pady=(0, 10))
        return frame

    def _create_palette_adjustment_row(
        self,
        parent: ttk.LabelFrame,
        *,
        label: str,
        variable: tk.IntVar,
        value_var: tk.StringVar,
        from_: int,
        to: int,
    ) -> tk.Scale:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(row, text=label).pack(side=tk.LEFT)
        ttk.Label(row, textvariable=value_var).pack(side=tk.RIGHT)
        scale = tk.Scale(
            parent,
            from_=from_,
            to=to,
            orient=tk.HORIZONTAL,
            resolution=1,
            showvalue=False,
            variable=variable,
            command=self._on_palette_adjustment_scale,
            highlightthickness=0,
            relief=tk.FLAT,
        )
        scale.pack(fill=tk.X)
        self.palette_adjustment_controls.append(scale)
        return scale

    def _configure_primary_button(self, button: tk.Button) -> None:
        button._pixel_fix_hovered = False  # type: ignore[attr-defined]
        button.configure(
            bd=0,
            highlightthickness=0,
            activebackground=PRIMARY_BUTTON_HOVER_BG,
            activeforeground=PRIMARY_BUTTON_HOVER_FG,
            disabledforeground=PRIMARY_BUTTON_INACTIVE_FG,
        )
        button.bind("<Enter>", lambda _event, target=button: self._set_primary_button_hover(target, True), add="+")
        button.bind("<Leave>", lambda _event, target=button: self._set_primary_button_hover(target, False), add="+")
        self._refresh_primary_button_style(button)

    def _set_primary_button_hover(self, button: tk.Button, hovered: bool) -> None:
        button._pixel_fix_hovered = hovered  # type: ignore[attr-defined]
        self._refresh_primary_button_style(button)

    def _refresh_primary_button_style(self, button: tk.Button) -> None:
        hovered = bool(getattr(button, "_pixel_fix_hovered", False))
        enabled = str(button.cget("state")) != str(tk.DISABLED)
        if enabled and hovered:
            bg = PRIMARY_BUTTON_HOVER_BG
            fg = PRIMARY_BUTTON_HOVER_FG
        elif enabled:
            bg = PRIMARY_BUTTON_ACTIVE_BG
            fg = PRIMARY_BUTTON_ACTIVE_FG
        else:
            bg = PRIMARY_BUTTON_INACTIVE_BG
            fg = PRIMARY_BUTTON_INACTIVE_FG
        button.configure(bg=bg, fg=fg)

    def _on_palette_adjustment_scale(self, _value: str | None = None) -> None:
        self._update_palette_adjustment_labels()
        self._on_settings_changed()

    def _update_palette_adjustment_labels(self) -> None:
        self.palette_brightness_value_var.set(str(int(self.palette_brightness_var.get())))
        self.palette_contrast_value_var.set(f"{int(self.palette_contrast_var.get())}%")
        self.palette_hue_value_var.set(f"{int(self.palette_hue_var.get())} deg")
        self.palette_saturation_value_var.set(f"{int(self.palette_saturation_var.get())}%")

    def _clear_processed_results(self) -> None:
        self.downsample_result = None
        self.palette_result = None
        self.downsample_display_image = None
        self.palette_display_image = None
        self.prepared_input_cache = None
        self.prepared_input_cache_key = None
        self.transparent_colors = set()
        self._palette_selection_indices = set()
        self._palette_selection_anchor_index = None

    def _palette_adjustments(self, settings: PreviewSettings | None = None) -> PaletteAdjustments:
        session = getattr(self, "session", None)
        current = settings or getattr(session, "current", PreviewSettings())
        return PaletteAdjustments(
            brightness=current.palette_brightness,
            contrast=current.palette_contrast,
            hue=current.palette_hue,
            saturation=current.palette_saturation,
        )

    def _current_palette_source_labels(self) -> tuple[list[int], str]:
        active_palette = getattr(self, "active_palette", None)
        if active_palette:
            return list(active_palette), getattr(self, "active_palette_source", "") or "Active"
        advanced_palette_preview = getattr(self, "advanced_palette_preview", None)
        if advanced_palette_preview is not None:
            return advanced_palette_preview.labels(), advanced_palette_preview.source_label or "Generated"
        current = self._current_output_result()
        if current is None:
            return ([], "none")
        if current.structured_palette is not None:
            source = current.structured_palette.source_label or current.stats.stage.title()
            return current.structured_palette.labels(), source
        if current.display_palette_labels:
            return list(current.display_palette_labels), current.stats.stage.title()
        return ([], "none")

    def _adjusted_palette_cache_token(self, adjustments: PaletteAdjustments) -> tuple[object, ...]:
        selection = tuple(sorted(self._palette_adjustment_selection_indices() or ()))
        current = self._current_output_result()
        return (
            adjustments.brightness,
            adjustments.contrast,
            adjustments.hue,
            adjustments.saturation,
            selection,
            id(getattr(self, "active_palette", None)) if getattr(self, "active_palette", None) is not None else None,
            id(getattr(self, "advanced_palette_preview", None)) if getattr(self, "advanced_palette_preview", None) is not None else None,
            id(current) if current is not None else None,
            id(current.structured_palette) if current is not None and current.structured_palette is not None else None,
        )

    def _current_base_structured_palette(self) -> StructuredPalette | None:
        workspace = getattr(self, "workspace", None) or ColorWorkspace()
        active_palette = getattr(self, "active_palette", None)
        if active_palette:
            return structured_palette_from_override(
                active_palette,
                workspace=workspace,
                source_label=getattr(self, "active_palette_source", "") or "Active",
            )
        advanced_palette_preview = getattr(self, "advanced_palette_preview", None)
        if advanced_palette_preview is not None:
            return clone_structured_palette(advanced_palette_preview)
        current = self._current_output_result()
        if current is not None and current.structured_palette is not None:
            return clone_structured_palette(current.structured_palette)
        if current is not None and current.display_palette_labels:
            return structured_palette_from_override(
                list(current.display_palette_labels),
                workspace=workspace,
                source_label=current.stats.stage.title(),
            )
        return None

    def _current_adjusted_structured_palette(self, settings: PreviewSettings | None = None) -> StructuredPalette | None:
        adjustments = self._palette_adjustments(settings)
        cache_key = self._adjusted_palette_cache_token(adjustments)
        cached_key = getattr(self, "_adjusted_palette_cache_key", None)
        cached_palette = getattr(self, "_adjusted_palette_cache", None)
        if cached_key == cache_key and cached_palette is not None:
            return clone_structured_palette(cached_palette)
        base_palette = self._current_base_structured_palette()
        if base_palette is None or base_palette.palette_size() == 0:
            self._adjusted_palette_cache_key = cache_key
            self._adjusted_palette_cache = None
            return None
        if adjustments.is_neutral():
            adjusted_palette = base_palette
        else:
            adjusted_palette = adjust_structured_palette(
                base_palette,
                adjustments,
                workspace=getattr(self, "workspace", None) or ColorWorkspace(),
                selected_indices=self._palette_adjustment_selection_indices(),
            )
        self._adjusted_palette_cache_key = cache_key
        self._adjusted_palette_cache = clone_structured_palette(adjusted_palette)
        return adjusted_palette

    def _has_palette_source(self) -> bool:
        palette, _source = self._current_palette_source_labels()
        return bool(palette)

    def _adjusted_palette_source_label(self, palette: StructuredPalette, settings: PreviewSettings | None = None) -> str:
        source = palette.source_label or "Palette"
        if self._palette_adjustments(settings).is_neutral():
            return source
        if self._palette_adjustment_selection_indices():
            return f"{source} (Adjusted Selection)"
        return f"{source} (Adjusted)"

    def _palette_adjustment_selection_indices(self) -> set[int] | None:
        palette, _source = self._current_palette_source_labels()
        if not palette:
            return None
        selection = getattr(self, "_palette_selection_indices", set())
        valid = {index for index in selection if 0 <= index < len(palette)}
        return valid or None

    def _reset_palette_adjustments_to_neutral(self) -> None:
        if not hasattr(self, "session"):
            return
        neutral = replace(
            self.session.current,
            palette_brightness=0,
            palette_contrast=100,
            palette_hue=0,
            palette_saturation=100,
        )
        self.session.current = neutral
        self._sync_controls_from_settings(neutral)

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-o>", lambda _event: self.open_image())
        self.root.bind("<Control-s>", lambda _event: self.save_processed_image())
        self.root.bind("<Control-S>", lambda _event: self.save_processed_image_as())
        self.root.bind("<Control-z>", lambda _event: self.undo())
        self.root.bind("<F5>", lambda _event: self.downsample_current_image())
        self.root.bind("<F6>", lambda _event: self.reduce_palette_current_image())
        self.root.bind("<Control-1>", lambda _event: self._set_view("original"))
        self.root.bind("<Control-2>", lambda _event: self._set_view("processed"))
        self.root.bind("<Control-0>", lambda _event: self.zoom_fit())
        self.root.bind("<Control-equal>", lambda _event: self._set_zoom(zoom_in(self.zoom)))
        self.root.bind("<Control-minus>", lambda _event: self._set_zoom(zoom_out(self.zoom)))

    def open_image(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("PNG images", "*.png")])
        if path:
            self._open_image_path(Path(path))

    def _open_image_path(self, path: Path) -> None:
        try:
            self.source_path = path
            self.original_display_image = load_png_rgba_image(str(path))
            self.original_grid = image_to_rgb_grid(self.original_display_image)
            self.comparison_original_image = None
            self._comparison_original_key = None
            self._clear_processed_results()
            self.transparent_colors = set()
            self._palette_selection_indices = set()
            self._palette_selection_anchor_index = None
            self._palette_hit_regions = []
            self._displayed_palette = []
            self.key_colors = []
            self.advanced_palette_preview = None
            self._set_pick_mode(None)
            self._clear_palette_undo_state()
            self._set_active_palette(None, "", None)
            self.quick_compare_active = False
            self.pan_x = 0
            self.pan_y = 0
            self.image_state = "loaded_original"
            self._record_recent_file(path)
            self._set_view("original")
            self.process_status_var.set(
                f"Loaded {path.name}: {self.original_display_image.width}x{self.original_display_image.height}. Adjust the pixel size, then click Downsample."
            )
            self.root.update_idletasks()
            self.zoom_fit()
            self._update_scale_info()
            self._update_key_color_list()
            self._update_palette_strip()
            self.redraw_canvas()
            self._refresh_action_states()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Failed to load image", str(exc))

    def _refresh_recent_menu(self) -> None:
        self.recent_menu.delete(0, tk.END)
        if not self.recent_files:
            self.recent_menu.add_command(label="(empty)", state=tk.DISABLED)
            return
        for path in self.recent_files:
            self.recent_menu.add_command(label=path, command=lambda value=path: self._open_recent(value))

    def _open_recent(self, path_value: str) -> None:
        path = Path(path_value)
        if not path.exists():
            messagebox.showwarning("Missing file", f"Recent file not found:\n{path}")
            self.recent_files = [item for item in self.recent_files if item != path_value]
            self._refresh_recent_menu()
            self._schedule_state_persist()
            return
        self._open_image_path(path)

    def _record_recent_file(self, path: Path) -> None:
        normalized = str(path)
        self.recent_files = [item for item in self.recent_files if item != normalized]
        self.recent_files.insert(0, normalized)
        self.recent_files = self.recent_files[:MAX_RECENT_FILES]
        self._refresh_recent_menu()
        self._schedule_state_persist()

    def _populate_builtin_palette_menu(self) -> None:
        menu = self._menu_items["built_in_palettes"]
        menu.delete(0, tk.END)
        if not self.builtin_palette_entries:
            menu.add_command(label="(none)", state=tk.DISABLED)
            return

        submenus: dict[tuple[str, ...], tk.Menu] = {(): menu}
        for entry in self.builtin_palette_entries:
            parent_path: tuple[str, ...] = ()
            parent_menu = menu
            for folder_label in entry.menu_path:
                parent_path = (*parent_path, folder_label)
                if parent_path not in submenus:
                    submenu = tk.Menu(parent_menu, tearoff=False)
                    parent_menu.add_cascade(label=folder_label, menu=submenu)
                    submenus[parent_path] = submenu
                parent_menu = submenus[parent_path]
            parent_menu.add_command(label=entry.label, command=lambda value=entry: self._select_builtin_palette(value))

    def _populate_palette_sort_menu(self) -> None:
        menu = self._menu_items["palette_sort"]
        menu.delete(0, tk.END)
        for label, mode in PALETTE_SORT_OPTIONS:
            menu.add_command(label=label, command=lambda value=mode: self.sort_current_palette(value))
        if self._palette_sort_reset_labels is not None:
            menu.add_separator()
            menu.add_command(label="Reset To Source Order", command=self.reset_palette_sort_order)

    def _restore_active_palette(self, persisted: dict[str, object]) -> bool:
        path_value = persisted.get("active_palette_path")
        if not isinstance(path_value, str) or not path_value:
            return False

        resolved_path = self._resolve_palette_path(path_value)
        if resolved_path is None:
            self._set_active_palette(None, "", None)
            return True

        entry = self._builtin_palette_by_path.get(resolved_path)
        try:
            palette = list(entry.colors) if entry is not None else load_palette(Path(resolved_path))
        except Exception:  # noqa: BLE001
            self._set_active_palette(None, "", None)
            return True

        source_value = persisted.get("active_palette_source")
        if entry is not None:
            source = f"Built-in: {entry.source_label}"
        elif isinstance(source_value, str) and source_value:
            source = source_value
        else:
            source = f"Loaded: {Path(resolved_path).name}"
        self._set_active_palette(palette, source, resolved_path)
        return False

    @staticmethod
    def _resolve_palette_path(path_value: str | Path | None) -> str | None:
        if path_value in (None, ""):
            return None
        path = Path(path_value)
        if not path.exists():
            return None
        return str(path.resolve())

    def _set_active_palette(
        self,
        palette: list[int] | tuple[int, ...] | None,
        source: str,
        path_value: str | None,
    ) -> None:
        self.active_palette = list(palette) if palette else None
        self.active_palette_source = source
        self.active_palette_path = path_value
        self._palette_selection_indices = set()
        self._palette_selection_anchor_index = None
        if not source.startswith("Sorted:"):
            self._palette_sort_reset_labels = None
            self._palette_sort_reset_source = None
            self._palette_sort_reset_path = None
        if hasattr(self, "_menu_items") and "palette_sort" in self._menu_items:
            self._populate_palette_sort_menu()

    def _apply_active_palette(
        self,
        palette: list[int] | tuple[int, ...] | None,
        source: str,
        path_value: str | None,
        *,
        message: str | None,
        mark_stale: bool = True,
        capture_undo: bool = False,
    ) -> None:
        if capture_undo:
            self._capture_palette_undo_state()
        else:
            self._clear_palette_undo_state()
        self._set_active_palette(palette, source, path_value)
        if mark_stale:
            self._mark_output_stale(message)
        elif message:
            self.process_status_var.set(message)
        self._update_palette_strip()
        self._schedule_state_persist()
        self._refresh_action_states()

    def _select_builtin_palette(self, entry: PaletteCatalogEntry) -> None:
        message = f"Selected built-in palette {entry.label} ({len(entry.colors)} colours). Click Apply Palette to use it."
        self._apply_active_palette(
            entry.colors,
            f"Built-in: {entry.source_label}",
            str(entry.path),
            message=message,
        )

    def clear_active_palette(self) -> None:
        if not self.active_palette:
            return
        self._apply_active_palette(None, "", None, message="Cleared the active palette.")
        self._update_palette_strip()

    def _selection_threshold_percent(self) -> int:
        return coerce_selection_threshold(self.selection_threshold_var.get())

    def _on_selection_threshold_changed(self) -> None:
        threshold = self._selection_threshold_percent()
        if self.selection_threshold_var.get() != threshold:
            self.selection_threshold_var.set(threshold)
        self.process_status_var.set(f"Selection threshold set to {threshold}%.")
        self._schedule_state_persist()
        self._refresh_action_states()

    def select_current_palette(self, mode: str) -> None:
        if mode not in PALETTE_SELECT_MODES:
            raise ValueError(f"Unsupported palette selection mode: {mode}")
        palette, _source = self._get_display_palette()
        if not palette:
            self.process_status_var.set("There is no current palette to select.")
            return
        threshold = self._selection_threshold_percent()
        indices = select_palette_indices(palette, mode, threshold, self.workspace)
        if hasattr(self, "_reset_palette_ctrl_drag_state"):
            self._reset_palette_ctrl_drag_state()
        self._palette_selection_indices = set(indices)
        self._palette_selection_anchor_index = indices[0] if indices else None
        self._update_palette_strip()
        self._refresh_action_states()
        label = PALETTE_SELECT_LABELS[mode]
        count = len(indices)
        self.process_status_var.set(f"Selected {count} palette colour{'s' if count != 1 else ''} by {label} at {threshold}%.")

    def sort_current_palette(self, mode: str) -> None:
        if mode not in PALETTE_SORT_MODES:
            raise ValueError(f"Unsupported palette sort mode: {mode}")
        palette, _source = self._get_display_palette()
        if not palette:
            self.process_status_var.set("There is no current palette to sort.")
            return
        if self._palette_sort_reset_labels is None:
            reset_source = self._palette_sort_source()
            if reset_source is not None:
                self._palette_sort_reset_labels = list(reset_source[0])
                self._palette_sort_reset_source = reset_source[1]
                self._palette_sort_reset_path = reset_source[2]
        sorted_palette = sort_palette_labels(palette, mode, self.workspace)
        label = PALETTE_SORT_LABELS[mode]
        self._apply_active_palette(
            sorted_palette,
            f"Sorted: {label}",
            None,
            message=f"Sorted current palette by {label}. Click Apply Palette to update the preview.",
            capture_undo=True,
        )

    def reset_palette_sort_order(self) -> None:
        if self._palette_sort_reset_labels is None:
            self.process_status_var.set("There is no source palette order to restore.")
            return
        source = self._palette_sort_reset_source or "Source"
        self._apply_active_palette(
            list(self._palette_sort_reset_labels),
            source,
            self._palette_sort_reset_path,
            message=f"Reset current palette to source order from {source}. Click Apply Palette to update the preview.",
            capture_undo=True,
        )

    def _palette_sort_source(self) -> tuple[list[int], str, str | None] | None:
        if self.active_palette is not None and self.active_palette_path is not None:
            return (list(self.active_palette), self.active_palette_source or "Active", self.active_palette_path)
        if self.active_palette is not None and not self.active_palette_source.startswith(("Sorted:", "Edited Palette")):
            return (list(self.active_palette), self.active_palette_source or "Active", self.active_palette_path)
        if self.advanced_palette_preview is not None:
            return (
                self.advanced_palette_preview.labels(),
                self.advanced_palette_preview.source_label or "Generated",
                None,
            )
        current = self._current_output_result()
        if current is None:
            return None
        if current.structured_palette is not None:
            return (
                current.structured_palette.labels(),
                current.structured_palette.source_label or current.stats.stage.title(),
                None,
            )
        if current.display_palette_labels:
            return (list(current.display_palette_labels), current.stats.stage.title(), None)
        return None

    def _set_pick_mode(self, mode: str | None) -> None:
        self.key_color_pick_mode = mode == "key"
        self.palette_add_pick_mode = mode == "palette"
        self.transparency_pick_mode = mode == "transparency"
        self._set_pick_preview(None)
        if mode == "key":
            self._set_view("original")
            self.process_status_var.set("Click the original preview to add a key colour.")
        elif mode == "palette":
            self._set_view("original")
            self.process_status_var.set("Click the original preview to add a colour to the current palette.")
        elif mode == "transparency":
            self._set_view("processed")
            self.process_status_var.set("Click the processed preview to remove a connected region.")

    def _editable_palette_labels(self) -> list[int]:
        palette, _source = self._get_display_palette()
        return list(palette)

    @staticmethod
    def _parse_hex_palette_colour(value: str) -> int:
        normalized = value.strip().upper()
        if normalized.startswith("#"):
            normalized = normalized[1:]
        if len(normalized) != 6 or any(character not in "0123456789ABCDEF" for character in normalized):
            raise ValueError("Enter a colour in #RRGGBB format.")
        return int(normalized, 16)

    def _apply_palette_edit(self, palette: list[int], message: str) -> None:
        self._palette_selection_indices = set()
        self._palette_selection_anchor_index = None
        self._apply_active_palette(
            palette,
            "Edited Palette",
            None,
            message=message,
            capture_undo=True,
        )

    def _add_colour_to_current_palette(self, label: int) -> bool:
        palette = self._editable_palette_labels()
        if label in palette:
            self.process_status_var.set(f"#{label:06X} is already in the current palette.")
            return False
        palette.append(label)
        self._apply_palette_edit(palette, f"Added #{label:06X} to the current palette. Click Apply Palette to update the preview.")
        return True

    def _remove_selected_palette_colors(self) -> None:
        palette = self._editable_palette_labels()
        if not palette:
            self.process_status_var.set("There is no current palette to edit.")
            return
        selected = sorted(index for index in self._palette_selection_indices if 0 <= index < len(palette))
        if not selected:
            self.process_status_var.set("Select one or more palette colours to remove.")
            return
        remaining = [label for index, label in enumerate(palette) if index not in set(selected)]
        removed_count = len(palette) - len(remaining)
        self._apply_palette_edit(
            remaining,
            f"Removed {removed_count} palette colour{'s' if removed_count != 1 else ''}. Click Apply Palette to update the preview.",
        )

    def _start_palette_add_pick_mode(self) -> None:
        if self.original_display_image is None or self.image_state == "processing":
            self.process_status_var.set("Open an image before adding colours to the current palette.")
            return
        self._set_pick_mode("palette")
        self._refresh_action_states()

    def _toggle_palette_add_pick_mode(self) -> None:
        if self.palette_add_pick_mode:
            self._set_pick_mode(None)
            self.process_status_var.set("Palette colour pick cancelled.")
        else:
            self._start_palette_add_pick_mode()
            return
        self._refresh_action_states()

    def _prompt_add_palette_color_hex(self) -> None:
        value = simpledialog.askstring("Add Palette Colour", "Enter a hex colour (#RRGGBB):", parent=self.root)
        if value is None:
            return
        try:
            label = self._parse_hex_palette_colour(value)
        except ValueError as exc:
            messagebox.showerror("Invalid colour", str(exc))
            return
        self._add_colour_to_current_palette(label)
        self._refresh_action_states()

    def _palette_is_override_mode(self) -> bool:
        return self.active_palette is not None

    def _current_key_colors(self) -> list[int]:
        return list(self.key_colors)

    def _update_key_color_list(self) -> None:
        if hasattr(self, "key_colors_label_var"):
            self.key_colors_label_var.set(f"Key colours ({len(self.key_colors)})")
        if not hasattr(self, "key_color_listbox"):
            return
        selected_indices = set(int(index) for index in self.key_color_listbox.curselection())
        self.key_color_listbox.delete(0, tk.END)
        for index, label in enumerate(self.key_colors):
            entry = f"#{label:06X}"
            self.key_color_listbox.insert(tk.END, entry)
            try:
                red = (label >> 16) & 0xFF
                green = (label >> 8) & 0xFF
                blue = label & 0xFF
                luminance = (0.299 * red) + (0.587 * green) + (0.114 * blue)
                self.key_color_listbox.itemconfig(index, bg=f"#{label:06x}", fg="#000000" if luminance >= 140 else "#ffffff")
            except tk.TclError:
                pass
            if index in selected_indices:
                self.key_color_listbox.selection_set(index)

    def _build_advanced_palette_preview(
        self,
        *,
        key_colors: list[int] | None = None,
        message: str | None = None,
    ) -> None:
        if self._palette_is_override_mode():
            return
        selected = list(self.key_colors if key_colors is None else key_colors)
        if not selected:
            self.advanced_palette_preview = None
            self._update_palette_strip()
            self._refresh_action_states()
            if message:
                self.process_status_var.set(message)
            return
        settings = self._read_settings_from_controls(strict=False)
        computation = generate_structured_palette(
            [],
            key_colors=selected,
            generated_shades=settings.generated_shades,
            contrast_bias=settings.contrast_bias,
            workspace=self.workspace,
            source_label="Generated",
        )
        self.advanced_palette_preview = computation.palette
        self._update_palette_strip()
        if message:
            self.process_status_var.set(message)
        self._refresh_action_states()

    def _ensure_advanced_palette_preview(self, *, force_regenerate: bool) -> None:
        del force_regenerate
        self._update_palette_strip()
        self._refresh_action_states()

    def _clear_advanced_seeds(self) -> None:
        if not self.key_colors:
            return
        self.key_colors = []
        self.key_color_pick_mode = False
        self.advanced_palette_preview = None
        self._update_key_color_list()
        self._mark_output_stale("Cleared all key colours. Pick colours, then click Generate Ramps.")
        self._update_palette_strip()
        self._refresh_action_states()

    def _remove_selected_seed(self) -> None:
        if not self.key_colors:
            return
        selected = [int(index) for index in self.key_color_listbox.curselection()]
        if not selected:
            self.process_status_var.set("Select one or more key colours to remove.")
            return
        for index in sorted(selected, reverse=True):
            del self.key_colors[index]
        self.advanced_palette_preview = None
        self._update_key_color_list()
        self._mark_output_stale("Key colours changed. Click Generate Ramps to rebuild the palette.")
        self._update_palette_strip()
        self._refresh_action_states()

    def _toggle_seed_pick_mode(self) -> None:
        if self.original_display_image is None or self._palette_is_override_mode():
            return
        if self.key_color_pick_mode:
            self._set_pick_mode(None)
            self.process_status_var.set("Colour pick cancelled.")
        else:
            self._set_pick_mode("key")
        self._refresh_action_states()

    def _toggle_transparency_pick_mode(self) -> None:
        if self._current_output_image() is None or self.image_state == "processing":
            self.process_status_var.set("Create a processed image before making colours transparent.")
            return
        if self.transparency_pick_mode:
            self._set_pick_mode(None)
            self.process_status_var.set("Transparency pick cancelled.")
        else:
            self._set_pick_mode("transparency")
        self._refresh_action_states()

    def _auto_detect_key_colors(self) -> None:
        if self.original_display_image is None or self._palette_is_override_mode() or self.image_state == "processing":
            return
        self.key_color_pick_mode = False
        requested_count = getattr(getattr(self, "session", None), "current", None)
        requested_count = getattr(requested_count, "auto_detect_count", MAX_KEY_COLORS)

        def progress_callback(_percent: int, message: str) -> None:
            self.process_status_var.set(message)
            self.root.update_idletasks()

        try:
            detected = detect_key_colors_from_image(
                self.original_display_image,
                max_colors=requested_count,
                workspace=self.workspace,
                progress_callback=progress_callback,
            )
        except Exception as exc:  # noqa: BLE001
            self.process_status_var.set(f"Auto-detect failed: {exc}")
            self._refresh_action_states()
            return

        if not detected:
            self.process_status_var.set("No visible colours were found for auto-detection.")
            self._refresh_action_states()
            return

        self.key_colors = detected
        self.advanced_palette_preview = None
        if hasattr(self, "key_color_listbox"):
            self.key_color_listbox.selection_clear(0, tk.END)
        self._update_key_color_list()
        self._mark_output_stale(f"Detected {len(detected)} key colours. Click Generate Ramps to rebuild the palette.")
        self._update_palette_strip()
        self._refresh_action_states()

    def _regenerate_all_ramps(self) -> None:
        if not self.key_colors:
            self.process_status_var.set("Pick at least one key colour before generating ramps.")
            return
        self._build_advanced_palette_preview(
            key_colors=self._current_key_colors(),
            message=f"Generated ramps from {len(self.key_colors)} key colour{'s' if len(self.key_colors) != 1 else ''}. Click Apply Palette to use them.",
        )
        self._mark_output_stale()

    def _regenerate_selected_ramp(self) -> None:
        self._regenerate_all_ramps()

    def _on_palette_settings_changed(self, _event: tk.Event | None = None) -> None:
        self._on_settings_changed(_event)

    def _displayed_structured_palette(self) -> StructuredPalette | None:
        return self._current_adjusted_structured_palette()

    def _active_pick_view(self) -> str | None:
        if self.key_color_pick_mode or self.palette_add_pick_mode:
            return "original"
        if self.transparency_pick_mode:
            return "processed"
        return None

    def _set_pick_preview(self, label: int | None) -> None:
        preview_var = getattr(self, "pick_preview_var", None)
        preview_frame = getattr(self, "pick_preview_frame", None)
        preview_swatch = getattr(self, "pick_preview_swatch", None)
        if preview_var is None:
            return
        if label is None:
            preview_var.set("")
            if preview_frame is not None and hasattr(preview_frame, "pack_forget"):
                preview_frame.pack_forget()
            return
        hex_value = f"#{label:06X}"
        preview_var.set(hex_value)
        if preview_swatch is not None and hasattr(preview_swatch, "configure"):
            preview_swatch.configure(bg=hex_value)
        if preview_frame is None or not hasattr(preview_frame, "pack"):
            return
        manager = preview_frame.winfo_manager() if hasattr(preview_frame, "winfo_manager") else ""
        if not manager:
            preview_frame.pack(side=tk.LEFT, padx=(0, 12))

    def _update_pick_preview(self, canvas_x: int, canvas_y: int) -> None:
        pick_view = self._active_pick_view()
        if pick_view is None:
            self._set_pick_preview(None)
            return
        sampled = self._sample_label_from_preview(canvas_x, canvas_y, view=pick_view)
        self._set_pick_preview(sampled)

    def _preview_image_coordinates(self, canvas_x: int, canvas_y: int, *, view: str) -> tuple[int, int] | None:
        if self._display_context is None or self._get_effective_view() != view:
            return None
        if not self._point_is_over_image(canvas_x, canvas_y):
            return None
        width = self._display_context.sample_image.width if self._display_context.sample_image is not None else 0
        height = self._display_context.sample_image.height if self._display_context.sample_image is not None else 0
        if width <= 0 or height <= 0:
            return None
        relative_x = (canvas_x - self._display_context.image_left) / max(1, self._display_context.display_width)
        relative_y = (canvas_y - self._display_context.image_top) / max(1, self._display_context.display_height)
        image_x = min(width - 1, max(0, int(relative_x * width)))
        image_y = min(height - 1, max(0, int(relative_y * height)))
        return image_x, image_y

    def _sample_point_from_preview(self, canvas_x: int, canvas_y: int, *, view: str) -> tuple[int, int, int] | None:
        coordinates = self._preview_image_coordinates(canvas_x, canvas_y, view=view)
        if coordinates is None or self._display_context is None or self._display_context.sample_image is None:
            return None
        image_x, image_y = coordinates
        pixel = self._display_context.sample_image.getpixel((image_x, image_y))
        if len(pixel) >= 4 and int(pixel[3]) == 0:
            return None
        red, green, blue = pixel[:3]
        return image_x, image_y, (int(red) << 16) | (int(green) << 8) | int(blue)

    def _sample_label_from_preview(self, canvas_x: int, canvas_y: int, *, view: str) -> int | None:
        sampled = self._sample_point_from_preview(canvas_x, canvas_y, view=view)
        if sampled is None:
            return None
        return sampled[2]

    def _add_key_color(self, label: int) -> None:
        if label in self.key_colors:
            self.process_status_var.set(f"#{label:06X} is already in the key-colour list.")
            return
        if len(self.key_colors) >= MAX_KEY_COLORS:
            self.process_status_var.set(f"You can only pick up to {MAX_KEY_COLORS} key colours.")
            return
        self.key_colors.append(label)
        self.advanced_palette_preview = None
        self._update_key_color_list()
        self._mark_output_stale(f"Added key colour #{label:06X}. Click Generate Ramps to rebuild the palette.")
        self._update_palette_strip()
        self._refresh_action_states()

    def _add_transparent_region(self, image_x: int, image_y: int, label: int) -> bool:
        current = self._current_output_result()
        if current is None:
            return False
        updated, changed = apply_transparency_fill(current, image_x, image_y)
        if changed <= 0:
            self.process_status_var.set("That region is already transparent.")
            return False
        self._capture_palette_undo_state()
        if getattr(self, "palette_result", None) is not None:
            self.palette_result = updated
        else:
            self.downsample_result = updated
        self._refresh_output_display_images()
        self.process_status_var.set(
            f"Made {changed} pixel{'s' if changed != 1 else ''} of #{label:06X} transparent. Press Undo to restore it."
        )
        self.redraw_canvas()
        self._refresh_action_states()
        return True

    def _selected_palette_outline_label(self) -> int | None:
        displayed = getattr(self, "_displayed_palette", [])
        selected = sorted(index for index in getattr(self, "_palette_selection_indices", set()) if 0 <= index < len(displayed))
        if len(selected) != 1:
            return None
        return displayed[selected[0]]

    def _set_current_output_result(self, result: ProcessResult) -> None:
        if getattr(self, "palette_result", None) is not None:
            self.palette_result = result
        else:
            self.downsample_result = result

    def _add_outline_from_selection(self) -> None:
        current = self._current_output_result()
        if current is None or self.image_state == "processing":
            return
        outline_label = self._selected_palette_outline_label()
        if outline_label is None:
            self.process_status_var.set("Select exactly one palette colour to add an outline.")
            return
        updated, changed = add_exterior_outline(current, outline_label, transparent_labels=getattr(self, "transparent_colors", set()))
        if changed <= 0:
            self.process_status_var.set("No exterior outline pixels were available to add.")
            return
        self._capture_palette_undo_state()
        self.transparent_colors = set()
        self._set_current_output_result(updated)
        self._refresh_output_display_images()
        self._set_view("processed")
        self.process_status_var.set(
            f"Added outline to {changed} pixel{'s' if changed != 1 else ''} with #{outline_label:06X}. Press Undo to restore it."
        )
        self._update_palette_strip()
        self._update_image_info()
        self.redraw_canvas()
        self._refresh_action_states()

    def _remove_outline(self) -> None:
        current = self._current_output_result()
        if current is None or self.image_state == "processing":
            return
        updated, changed = remove_exterior_outline(current, transparent_labels=getattr(self, "transparent_colors", set()))
        if changed <= 0:
            self.process_status_var.set("No exterior outline pixels were found to remove.")
            return
        self._capture_palette_undo_state()
        self.transparent_colors = set()
        self._set_current_output_result(updated)
        self._refresh_output_display_images()
        self._set_view("processed")
        self.process_status_var.set(f"Removed {changed} outline pixel{'s' if changed != 1 else ''}. Press Undo to restore it.")
        self._update_palette_strip()
        self._update_image_info()
        self.redraw_canvas()
        self._refresh_action_states()

    def extract_unique_palette(self) -> None:
        source_grid = self._palette_source_grid()
        if source_grid is None:
            return
        palette = extract_unique_colors(rgb_to_labels(source_grid))
        self._apply_active_palette(
            palette,
            "Extracted",
            None,
            message=f"Extracted {len(palette)} colours. Click Apply Palette to update the preview.",
        )

    def generate_palette_from_image(self) -> None:
        try:
            settings = self._read_settings_from_controls(strict=False)
        except Exception:
            settings = self.session.current
        self.session.current = settings
        self._generate_override_palette_from_settings(settings)

    def _generate_override_palette_from_settings(self, settings: PreviewSettings) -> None:
        if self.image_state == "processing":
            return
        source_labels = self._override_palette_source_labels()
        if source_labels is None:
            self.process_status_var.set("Downsample the image before generating an override palette.")
            return
        palette_size = self._override_palette_target_size(source_labels, settings)
        if palette_size <= 0:
            self.process_status_var.set("No colours are available to build an override palette.")
            return
        method = settings.quantizer
        label = QUANTIZER_VALUE_TO_DISPLAY.get(method, method)
        try:
            palette = generate_override_palette(source_labels, palette_size, method=method)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Failed to generate override palette", str(exc))
            return
        if not palette:
            self.process_status_var.set("No colours were generated for the override palette.")
            return
        self._apply_active_palette(
            palette,
            f"Generated Override: {label}",
            None,
            message=f"Generated a {len(palette)}-colour override palette with {label}. Click Apply Palette to use it.",
        )

    def load_palette_file(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[
                ("GIMP Palette", "*.gpl"),
                ("Palette files", "*.gpl *.json"),
                ("Palette JSON", "*.json"),
            ]
        )
        if not path:
            return
        try:
            palette = load_palette(Path(path))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Failed to load palette", str(exc))
            return
        resolved_path = self._resolve_palette_path(path) or str(Path(path))
        self._apply_active_palette(
            palette,
            f"Loaded: {Path(path).name}",
            resolved_path,
            message=f"Loaded palette from {Path(path).name}. Click Apply Palette to update the preview.",
        )

    def save_palette_file(self) -> None:
        palette, _source = self._get_display_palette()
        if not palette:
            return
        path = filedialog.asksaveasfilename(defaultextension=".gpl", filetypes=[("GIMP Palette", "*.gpl")])
        if not path:
            return
        try:
            save_palette(Path(path), palette)
            self.process_status_var.set(f"Saved palette to {Path(path).name}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Failed to save palette", str(exc))

    def downsample_current_image(self) -> None:
        if self.original_grid is None or self.source_path is None:
            return
        try:
            settings = self._read_settings_from_controls(strict=True)
        except ValueError as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return
        self.session.current = settings
        snapshot_palette, snapshot_source = self._get_display_palette()
        snapshot = make_process_snapshot(settings, snapshot_palette, self.active_palette_path, snapshot_source)
        changes = diff_snapshots(self.last_successful_process_snapshot, snapshot)
        source_size = (len(self.original_grid[0]), len(self.original_grid)) if self.original_grid else (0, 0)

        self._set_pick_mode(None)
        self.image_state = "processing"
        self.quick_compare_active = False
        self.process_status_var.set("Preparing input...")
        self._refresh_action_states()
        config = self._build_pipeline_config(settings)

        def progress_callback(_percent: int, message: str) -> None:
            self.root.after(0, lambda: self.process_status_var.set(message))

        def worker() -> None:
            try:
                result = downsample_image(
                    self.original_grid or [],
                    config,
                    progress_callback=progress_callback,
                )
                self.root.after(0, lambda: self._handle_downsample_success(result, snapshot, changes, source_size, self._build_prepare_cache_key(settings)))
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                self.root.after(0, lambda message=message: self._handle_stage_failure(message, changes, source_size))

        threading.Thread(target=worker, daemon=True).start()

    def reduce_palette_current_image(self) -> None:
        if self.prepared_input_cache is None or self.source_path is None:
            self.process_status_var.set("Downsample the image before applying a palette.")
            return
        adjusted_palette = self._current_adjusted_structured_palette()
        if adjusted_palette is None or adjusted_palette.palette_size() == 0:
            self.process_status_var.set("Create, load, or adjust a palette before applying it.")
            return
        try:
            settings = self._read_settings_from_controls(strict=True)
        except ValueError as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return
        self.session.current = settings
        snapshot_palette, snapshot_source = self._get_display_palette()
        snapshot = make_process_snapshot(settings, snapshot_palette, self.active_palette_path, snapshot_source)
        changes = diff_snapshots(self.last_successful_process_snapshot, snapshot)
        source_size = (len(self.original_grid[0]), len(self.original_grid)) if self.original_grid else (0, 0)
        self._capture_palette_undo_state()

        self._set_pick_mode(None)
        self.image_state = "processing"
        self.quick_compare_active = False
        self.process_status_var.set("Applying palette...")
        self._refresh_action_states()
        config = self._build_pipeline_config(settings)
        apply_override_palette: list[int] | None = None
        apply_override_source: str | None = None
        apply_override_path: str | None = None
        apply_structured_palette: StructuredPalette | None = None
        if self._palette_is_override_mode() or adjusted_palette.source_mode == "override":
            apply_override_palette = adjusted_palette.labels()
            apply_override_source = adjusted_palette.source_label or self.active_palette_source or "Override"
            apply_override_path = self.active_palette_path if self.active_palette is not None else None
        else:
            apply_structured_palette = adjusted_palette

        def progress_callback(_percent: int, message: str) -> None:
            self.root.after(0, lambda: self.process_status_var.set(message))

        def worker() -> None:
            try:
                result = reduce_palette_image(
                    self.prepared_input_cache,
                    config,
                    palette_override=apply_override_palette,
                    structured_palette=apply_structured_palette,
                    progress_callback=progress_callback,
                )
                self.root.after(
                    0,
                    lambda: self._handle_palette_success(
                        result,
                        snapshot,
                        changes,
                        source_size,
                        applied_override_palette=apply_override_palette,
                        applied_override_source=apply_override_source,
                        applied_override_path=apply_override_path,
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                self.root.after(0, lambda message=message: self._handle_stage_failure(message, changes, source_size))

        threading.Thread(target=worker, daemon=True).start()

    def save_processed_image(self) -> None:
        if self.image_state != "processed_current":
            return
        if not self.last_output_path:
            self.save_processed_image_as()
            return
        self._save_processed_png(Path(self.last_output_path))

    def save_processed_image_as(self) -> None:
        if self.image_state != "processed_current":
            return
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG images", "*.png")])
        if not path:
            return
        self._save_processed_png(Path(path))

    def undo(self) -> None:
        if self._undo_palette_application():
            return
        if not self.session.history.can_undo():
            self.process_status_var.set("Nothing to undo.")
            return
        previous = self.session.current
        restored = self.session.undo()
        self._sync_controls_from_settings(restored)
        self._handle_settings_transition(previous, restored, "Settings restored from undo.")

    def _capture_palette_undo_state(self) -> None:
        self._palette_undo_state = PaletteUndoState(
            palette_result=getattr(self, "palette_result", None),
            downsample_result=getattr(self, "downsample_result", None),
            downsample_display_image=self.downsample_display_image.copy() if getattr(self, "downsample_display_image", None) is not None else None,
            palette_display_image=self.palette_display_image.copy() if getattr(self, "palette_display_image", None) is not None else None,
            image_state=self.image_state,
            last_successful_process_snapshot=dict(self.last_successful_process_snapshot) if isinstance(self.last_successful_process_snapshot, dict) else self.last_successful_process_snapshot,
            active_palette=list(self.active_palette) if getattr(self, "active_palette", None) is not None else None,
            active_palette_source=getattr(self, "active_palette_source", ""),
            active_palette_path=getattr(self, "active_palette_path", None),
            advanced_palette_preview=clone_structured_palette(getattr(self, "advanced_palette_preview", None)),
            transparent_colors=tuple(sorted(getattr(self, "transparent_colors", set()))),
            settings=self.session.current,
            palette_sort_reset_labels=tuple(getattr(self, "_palette_sort_reset_labels", None) or ()),
            palette_sort_reset_source=getattr(self, "_palette_sort_reset_source", None),
            palette_sort_reset_path=getattr(self, "_palette_sort_reset_path", None),
        )

    def _clear_palette_undo_state(self) -> None:
        self._palette_undo_state = None

    def _undo_palette_application(self) -> bool:
        if self._palette_undo_state is None:
            return False
        state = self._palette_undo_state
        self.downsample_result = state.downsample_result
        self.palette_result = state.palette_result
        self.downsample_display_image = state.downsample_display_image.copy() if state.downsample_display_image is not None else None
        self.palette_display_image = state.palette_display_image.copy() if state.palette_display_image is not None else None
        self.image_state = state.image_state
        self.last_successful_process_snapshot = (
            dict(state.last_successful_process_snapshot) if isinstance(state.last_successful_process_snapshot, dict) else state.last_successful_process_snapshot
        )
        self._set_active_palette(state.active_palette, state.active_palette_source, state.active_palette_path)
        self.advanced_palette_preview = clone_structured_palette(state.advanced_palette_preview)
        self.transparent_colors = set(state.transparent_colors)
        self._palette_sort_reset_labels = list(state.palette_sort_reset_labels) if state.palette_sort_reset_labels else None
        self._palette_sort_reset_source = state.palette_sort_reset_source
        self._palette_sort_reset_path = state.palette_sort_reset_path
        self.session.current = state.settings
        self._sync_controls_from_settings(state.settings)
        self.comparison_original_image = None
        self._comparison_original_key = None
        if hasattr(self, "_menu_items") and "palette_sort" in self._menu_items:
            self._populate_palette_sort_menu()
        self.quick_compare_active = False
        self._clear_palette_undo_state()
        self.process_status_var.set("Reverted the last image change.")
        self._update_palette_strip()
        self._update_image_info()
        self.redraw_canvas()
        self._schedule_state_persist()
        self._refresh_action_states()
        return True

    def _build_output_display_image(self, result: ProcessResult | None) -> Image.Image | None:
        if result is None:
            return None
        image = Image.new("RGBA", (result.width, result.height))
        if result.width <= 0 or result.height <= 0:
            return image
        alpha_mask = result.alpha_mask
        transparent = getattr(self, "transparent_colors", set())
        data: list[tuple[int, int, int, int]] = []
        for y, row in enumerate(result.grid):
            for x, (red, green, blue) in enumerate(row):
                label = (red << 16) | (green << 8) | blue
                is_visible = True if alpha_mask is None else bool(alpha_mask[y][x])
                alpha = 0 if (not is_visible or label in transparent) else 255
                data.append((red, green, blue, alpha))
        image.putdata(data)
        return image

    def _refresh_output_display_images(self) -> None:
        self.downsample_display_image = self._build_output_display_image(getattr(self, "downsample_result", None))
        self.palette_display_image = self._build_output_display_image(getattr(self, "palette_result", None))

    def _handle_downsample_success(
        self,
        result: ProcessResult,
        snapshot: dict[str, object],
        changes: list[str],
        source_size: tuple[int, int],
        cache_key: tuple[object, ...],
    ) -> None:
        self.downsample_result = result
        self.palette_result = None
        self.transparent_colors = set()
        self._palette_selection_indices = set()
        self._refresh_output_display_images()
        self.comparison_original_image = None
        self._comparison_original_key = None
        self.prepared_input_cache = result.prepared_input
        self.prepared_input_cache_key = cache_key
        self.image_state = "processed_current"
        self.last_successful_process_snapshot = snapshot
        self._clear_palette_undo_state()
        self._set_view("processed")
        self.root.update_idletasks()
        self.zoom_fit()
        status_message = f"Downsampled to {result.width}x{result.height} with {display_resize_method(result.stats.resize_method)} in {result.stats.elapsed_seconds:.2f}s."
        self.process_status_var.set(status_message)
        append_process_log(
            source_path_value=str(self.source_path),
            source_size=source_size,
            processed_size=result.stats.output_size,
            color_count=result.stats.color_count,
            changes=changes,
            success=True,
            message="Downsample complete",
        )
        self._update_palette_strip()
        self._update_image_info()
        self.redraw_canvas()
        self._schedule_state_persist()
        self._refresh_action_states()

    def _handle_palette_success(
        self,
        result: ProcessResult,
        snapshot: dict[str, object],
        changes: list[str],
        source_size: tuple[int, int],
        *,
        applied_override_palette: list[int] | None = None,
        applied_override_source: str | None = None,
        applied_override_path: str | None = None,
    ) -> None:
        self.palette_result = result
        self._palette_selection_indices = set()
        if applied_override_palette is not None:
            self._set_active_palette(applied_override_palette, applied_override_source or "Override", applied_override_path)
            self.advanced_palette_preview = None
        elif result.structured_palette is not None and result.structured_palette.source_mode == "advanced":
            self.advanced_palette_preview = result.structured_palette
        self.transparent_colors = set()
        self._refresh_output_display_images()
        self._reset_palette_adjustments_to_neutral()
        self.image_state = "processed_current"
        self.last_successful_process_snapshot = snapshot
        self._set_view("processed")
        self.root.update_idletasks()
        self.zoom_fit()
        self.process_status_var.set(
            f"Applied {result.stats.palette_strategy} palette with {result.stats.color_count} colours across {max(result.stats.ramp_count, 1)} ramps in {result.stats.elapsed_seconds:.2f}s."
        )
        append_process_log(
            source_path_value=str(self.source_path),
            source_size=source_size,
            processed_size=result.stats.output_size,
            color_count=result.stats.color_count,
            changes=changes,
            success=True,
            message="Palette application complete",
        )
        self._update_palette_strip()
        self._update_image_info()
        self.redraw_canvas()
        self._schedule_state_persist()
        self._refresh_action_states()

    def _handle_stage_failure(self, message: str, changes: list[str], source_size: tuple[int, int]) -> None:
        self._clear_palette_undo_state()
        self.image_state = "processed_stale" if self._current_output_result() is not None else "loaded_original"
        self.process_status_var.set(message)
        append_process_log(
            source_path_value=str(self.source_path) if self.source_path is not None else "unknown",
            source_size=source_size,
            processed_size=None,
            color_count=None,
            changes=changes,
            success=False,
            message=message,
        )
        messagebox.showerror("Processing failed", message)
        self._refresh_action_states()

    def _save_processed_png(self, path: Path) -> None:
        image = self._current_output_image()
        if image is None:
            return
        image.save(path, format="PNG")
        self.last_output_path = str(path)
        self.process_status_var.set(f"Saved image to {path.name}")
        self._schedule_state_persist()
        self._refresh_action_states()

    def redraw_canvas(self) -> None:
        self.canvas.delete("all")
        sample_image = self._get_sample_image()
        self._display_context = None
        if sample_image is None:
            text = "Open an image to begin." if self.original_display_image is None else "Click Downsample to create the resized preview."
            self.canvas.create_text(max(self.canvas.winfo_width() // 2, 200), max(self.canvas.winfo_height() // 2, 150), text=text, fill="#cfcfcf", font=("Segoe UI", 11))
            self._update_image_info()
            return

        base_width = max(1, sample_image.width)
        base_height = max(1, sample_image.height)
        display_width = max(1, round(base_width * (self.zoom / 100)))
        display_height = max(1, round(base_height * (self.zoom / 100)))
        canvas_width = max(1, self.canvas.winfo_width())
        canvas_height = max(1, self.canvas.winfo_height())
        self._clamp_pan(display_width, display_height, canvas_width, canvas_height)
        image_left = (canvas_width - display_width) // 2 if display_width <= canvas_width else -self.pan_x
        image_top = (canvas_height - display_height) // 2 if display_height <= canvas_height else -self.pan_y
        self._display_context = CanvasDisplay(image_left, image_top, display_width, display_height, sample_image)

        rendered = self._render_display_image(sample_image, display_width, display_height)
        self._image_ref = ImageTk.PhotoImage(rendered)
        self.canvas.create_image(image_left, image_top, image=self._image_ref, anchor=tk.NW)
        self._update_image_info()

    def _render_display_image(self, sample_image: Image.Image, display_width: int, display_height: int) -> Image.Image:
        background = self._build_background(sample_image.size)
        composited = Image.alpha_composite(background, sample_image.convert("RGBA"))
        return composited.resize((display_width, display_height), Image.Resampling.NEAREST)

    def _build_background(self, size: tuple[int, int]) -> Image.Image:
        width, height = size
        if width <= 0 or height <= 0:
            return Image.new("RGBA", (1, 1), (34, 34, 34, 255))
        if not self.checkerboard_var.get():
            return Image.new("RGBA", size, (34, 34, 34, 255))
        background = Image.new("RGBA", size, (220, 220, 220, 255))
        draw = ImageDraw.Draw(background)
        for y in range(0, height, 8):
            for x in range(0, width, 8):
                if ((x // 8) + (y // 8)) % 2 == 0:
                    draw.rectangle((x, y, x + 7, y + 7), fill=(180, 180, 180, 255))
        return background

    def _get_effective_view(self) -> str:
        if self.quick_compare_active and self.view_var.get() == "processed":
            return "original"
        return self.view_var.get()

    def _get_sample_image(self) -> Image.Image | None:
        if self.original_display_image is None:
            return None
        if self._get_effective_view() == "original":
            return self._get_comparison_original_image()
        return self._current_output_image()

    def _current_output_result(self) -> ProcessResult | None:
        return getattr(self, "palette_result", None) or getattr(self, "downsample_result", None)

    def _current_output_image(self) -> Image.Image | None:
        return getattr(self, "palette_display_image", None) or getattr(self, "downsample_display_image", None)

    def _get_comparison_original_image(self) -> Image.Image | None:
        if self.original_display_image is None:
            return None
        current = self._current_output_result()
        if current is None or self.original_grid is None:
            return self.original_display_image
        key = (
            current.stats.pixel_width,
            current.stats.resize_method,
            current.width,
            current.height,
        )
        if self._comparison_original_key != key or self.comparison_original_image is None:
            resized = resize_labels(
                rgb_to_labels(self.original_grid),
                current.stats.pixel_width,
                method=current.stats.resize_method,
            )
            self.comparison_original_image = grid_to_pil_image(labels_to_rgb(resized)).convert("RGBA")
            self._comparison_original_key = key
        return self.comparison_original_image

    def _palette_source_grid(self) -> RGBGrid | None:
        if self.downsample_result is not None:
            return self.downsample_result.grid
        return self.original_grid

    def _override_palette_source_labels(self) -> list[list[int]] | None:
        if self.prepared_input_cache is None:
            return None
        return self.prepared_input_cache.reduced_labels

    def _override_palette_target_size(self, labels: list[list[int]], settings: PreviewSettings) -> int:
        unique_count = len(extract_unique_colors(labels))
        if unique_count <= 0:
            return 0
        target = settings.palette_reduction_colors
        return max(1, min(target, unique_count))

    def _on_canvas_press(self, event: tk.Event) -> None:
        if self.key_color_pick_mode:
            sampled = self._sample_label_from_preview(event.x, event.y, view="original")
            if sampled is not None:
                self._add_key_color(sampled)
                self._set_pick_mode(None)
                self._refresh_action_states()
            return
        if self.palette_add_pick_mode:
            sampled = self._sample_label_from_preview(event.x, event.y, view="original")
            if sampled is not None:
                self._add_colour_to_current_palette(sampled)
                self._set_pick_mode(None)
                self._refresh_action_states()
            return
        if self.transparency_pick_mode:
            sampled = self._sample_point_from_preview(event.x, event.y, view="processed")
            if sampled is not None:
                image_x, image_y, label = sampled
                self._add_transparent_region(image_x, image_y, label)
                self._set_pick_mode(None)
                self._refresh_action_states()
            return
        if not self._point_is_over_image(event.x, event.y):
            return
        self.dragging = True
        self.drag_origin = (event.x, event.y)
        self.drag_pan_start = (self.pan_x, self.pan_y)
        self.canvas.configure(cursor=CLOSED_HAND_CURSOR)

    def _on_canvas_drag(self, event: tk.Event) -> None:
        if not self.dragging or self._display_context is None:
            return
        canvas_width = max(1, self.canvas.winfo_width())
        canvas_height = max(1, self.canvas.winfo_height())
        if self._display_context.display_width > canvas_width:
            self.pan_x = max(0, self.drag_pan_start[0] - (event.x - self.drag_origin[0]))
        if self._display_context.display_height > canvas_height:
            self.pan_y = max(0, self.drag_pan_start[1] - (event.y - self.drag_origin[1]))
        self.redraw_canvas()

    def _on_canvas_release(self, _event: tk.Event) -> None:
        self.dragging = False
        self.canvas.configure(cursor=self._cursor_for_pointer())

    def _on_canvas_motion(self, event: tk.Event) -> None:
        if self.dragging:
            self.canvas.configure(cursor=CLOSED_HAND_CURSOR)
        elif self.key_color_pick_mode or self.palette_add_pick_mode or self.transparency_pick_mode:
            self.canvas.configure(cursor="crosshair")
            self._update_pick_preview(event.x, event.y)
        else:
            self._set_pick_preview(None)
            self.canvas.configure(cursor=OPEN_HAND_CURSOR if self._point_is_over_image(event.x, event.y) else "")

    def _on_canvas_leave(self, _event: tk.Event) -> None:
        self._set_pick_preview(None)
        if not self.dragging:
            self.canvas.configure(cursor="")

    def _on_quick_compare_press(self, _event: tk.Event) -> None:
        if self.view_var.get() != "processed" or self._current_output_image() is None:
            return
        self.quick_compare_active = True
        self.redraw_canvas()

    def _on_quick_compare_release(self, _event: tk.Event) -> None:
        if not self.quick_compare_active:
            return
        self.quick_compare_active = False
        self.redraw_canvas()

    def _cursor_for_pointer(self) -> str:
        if self.key_color_pick_mode or self.palette_add_pick_mode or self.transparency_pick_mode:
            return "crosshair"
        return OPEN_HAND_CURSOR if self._point_is_over_image() else ""

    def _palette_hit_test(self, x: int, y: int) -> tuple[int, int] | None:
        for index, (x0, y0, x1, y1) in enumerate(self._palette_hit_regions):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return index, self._displayed_palette[index]
        return None

    def _reset_palette_ctrl_drag_state(self) -> None:
        self._palette_ctrl_drag_active = False
        self._palette_ctrl_drag_anchor_index = None
        self._palette_ctrl_drag_indices = set()
        self._palette_ctrl_drag_initial_selection = set()

    def _finalize_palette_ctrl_drag(self, *, toggle_if_single: bool) -> None:
        if not getattr(self, "_palette_ctrl_drag_active", False):
            return
        drag_indices = set(getattr(self, "_palette_ctrl_drag_indices", set()))
        initial_selection = set(getattr(self, "_palette_ctrl_drag_initial_selection", set()))
        anchor_index = getattr(self, "_palette_ctrl_drag_anchor_index", None)
        updated_selection = set(getattr(self, "_palette_selection_indices", set()))
        updated_anchor = getattr(self, "_palette_selection_anchor_index", None)
        if len(drag_indices) <= 1 and toggle_if_single:
            index = next(iter(drag_indices), None)
            if index is not None:
                updated_selection = set(initial_selection)
                if index in updated_selection:
                    updated_selection.remove(index)
                else:
                    updated_selection.add(index)
                updated_anchor = index if updated_selection else None
        else:
            updated_selection = initial_selection | drag_indices
            updated_anchor = anchor_index if updated_selection else None
        changed = (
            updated_selection != getattr(self, "_palette_selection_indices", set())
            or updated_anchor != getattr(self, "_palette_selection_anchor_index", None)
        )
        self._palette_selection_indices = updated_selection
        self._palette_selection_anchor_index = updated_anchor
        self._reset_palette_ctrl_drag_state()
        if changed:
            self._update_palette_strip()
            self._refresh_action_states()

    def _on_palette_canvas_click(self, event: tk.Event) -> None:
        hit = self._palette_hit_test(event.x, event.y)
        self._reset_palette_ctrl_drag_state()
        if hit is None:
            self._palette_selection_indices = set()
            self._palette_selection_anchor_index = None
        else:
            index, _label = hit
            state = int(getattr(event, "state", 0))
            ctrl_down = bool(state & 0x0004)
            shift_down = bool(state & 0x0001)
            anchor = getattr(self, "_palette_selection_anchor_index", None)
            if ctrl_down and not shift_down:
                self._palette_ctrl_drag_active = True
                self._palette_ctrl_drag_anchor_index = index
                self._palette_ctrl_drag_indices = {index}
                self._palette_ctrl_drag_initial_selection = set(self._palette_selection_indices)
                return
            if shift_down and anchor is not None:
                start = min(anchor, index)
                end = max(anchor, index)
                range_selection = set(range(start, end + 1))
                if ctrl_down:
                    self._palette_selection_indices |= range_selection
                else:
                    self._palette_selection_indices = range_selection
            elif ctrl_down:
                if index in self._palette_selection_indices:
                    self._palette_selection_indices.remove(index)
                else:
                    self._palette_selection_indices.add(index)
                self._palette_selection_anchor_index = index
            else:
                self._palette_selection_indices = {index}
                self._palette_selection_anchor_index = index
        self._update_palette_strip()
        self._refresh_action_states()

    def _on_palette_canvas_drag(self, event: tk.Event) -> None:
        if not getattr(self, "_palette_ctrl_drag_active", False):
            return
        state = int(getattr(event, "state", 0))
        if not (state & 0x0004):
            self._finalize_palette_ctrl_drag(toggle_if_single=False)
            return
        hit = self._palette_hit_test(event.x, event.y)
        if hit is None:
            return
        index, _label = hit
        drag_indices = set(getattr(self, "_palette_ctrl_drag_indices", set()))
        if index in drag_indices:
            return
        drag_indices.add(index)
        self._palette_ctrl_drag_indices = drag_indices
        self._palette_selection_indices = set(getattr(self, "_palette_ctrl_drag_initial_selection", set())) | drag_indices
        self._palette_selection_anchor_index = getattr(self, "_palette_ctrl_drag_anchor_index", None)
        self._update_palette_strip()
        self._refresh_action_states()

    def _on_palette_canvas_release(self, _event: tk.Event) -> None:
        self._finalize_palette_ctrl_drag(toggle_if_single=True)

    def _on_palette_canvas_double_click(self, event: tk.Event) -> None:
        self._on_palette_canvas_click(event)

    def _on_palette_canvas_right_click(self, event: tk.Event) -> None:
        del event
        self._reset_palette_ctrl_drag_state()
        self._palette_selection_indices = set()
        self._palette_selection_anchor_index = None
        self._update_palette_strip()
        self._refresh_action_states()

    def _select_all_palette_colors(self) -> None:
        if not self._displayed_palette:
            self.process_status_var.set("There is no current palette to select.")
            return
        self._palette_selection_indices = set(range(len(self._displayed_palette)))
        self._palette_selection_anchor_index = 0 if self._displayed_palette else None
        self._update_palette_strip()
        self._refresh_action_states()
        self.process_status_var.set(f"Selected {len(self._palette_selection_indices)} palette colours.")

    def _clear_palette_selection(self) -> None:
        if not self._palette_selection_indices:
            return
        self._palette_selection_indices = set()
        self._palette_selection_anchor_index = None
        self._update_palette_strip()
        self._refresh_action_states()

    def _point_is_over_image(self, x: int | None = None, y: int | None = None) -> bool:
        if self._display_context is None:
            return False
        px = self.canvas.winfo_pointerx() - self.canvas.winfo_rootx() if x is None else x
        py = self.canvas.winfo_pointery() - self.canvas.winfo_rooty() if y is None else y
        return (
            self._display_context.image_left <= px <= self._display_context.image_left + self._display_context.display_width
            and self._display_context.image_top <= py <= self._display_context.image_top + self._display_context.display_height
        )

    def _on_zoom_wheel(self, event: tk.Event) -> None:
        if self.original_display_image is None:
            return
        self._set_zoom(zoom_in(self.zoom) if event.delta > 0 else zoom_out(self.zoom))

    def _set_zoom(self, value: int) -> None:
        self.zoom = clamp_zoom(value)
        self.redraw_canvas()
        self._schedule_state_persist()

    def zoom_fit(self) -> None:
        sample_image = self._get_sample_image() or self.original_display_image
        if sample_image is None:
            return
        self.zoom = choose_fit_zoom(sample_image.width, sample_image.height, max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height()))
        self.pan_x = 0
        self.pan_y = 0
        self.redraw_canvas()
        self._schedule_state_persist()

    def _clamp_pan(self, display_width: int, display_height: int, canvas_width: int, canvas_height: int) -> None:
        self.pan_x = min(max(self.pan_x, 0), max(0, display_width - canvas_width))
        self.pan_y = min(max(self.pan_y, 0), max(0, display_height - canvas_height))

    def _on_view_changed(self) -> None:
        self.redraw_canvas()
        self._schedule_state_persist()

    def _set_view(self, value: str) -> None:
        self.view_var.set(value)
        self.redraw_canvas()

    def _update_scale_info(self) -> None:
        if self.original_display_image is None:
            self.scale_info_var.set("Open an image to set the pixel size.")
            return
        pixel_width = max(1, int(self.pixel_width_var.get() or self.session.current.pixel_width))
        output_width, output_height = target_size_for_pixel_width(self.original_display_image.width, self.original_display_image.height, pixel_width)
        self.scale_info_var.set(f"Pixel size: {pixel_width} px  Output: {output_width}x{output_height}")

    def _update_palette_strip(self) -> None:
        if hasattr(self, "_menu_items") and "palette_sort" in self._menu_items:
            self._populate_palette_sort_menu()
        self.palette_canvas.delete("all")
        self._palette_hit_regions = []
        palette, source = self._get_display_palette()
        if not palette:
            self._displayed_palette = []
            self._palette_selection_indices = set()
            self._palette_selection_anchor_index = None
            self.palette_info_var.set("Palette: none")
            self.palette_canvas.configure(height=60)
            return
        displayed = palette[:MAX_PALETTE_SWATCHES]
        self._displayed_palette = list(displayed)
        self._palette_selection_indices = {index for index in self._palette_selection_indices if 0 <= index < len(displayed)}
        anchor_index = getattr(self, "_palette_selection_anchor_index", None)
        if anchor_index is not None and anchor_index >= len(displayed):
            self._palette_selection_anchor_index = None
        suffix = "" if len(displayed) == len(palette) else f" (showing first {len(displayed)})"
        selected_count = len(self._palette_selection_indices)
        selection_suffix = f", {selected_count} selected" if selected_count else ""
        self.palette_info_var.set(f"Palette: {source} ({len(palette)} colours{selection_suffix}){suffix}")
        columns = max(1, max(200, self.palette_canvas.winfo_width()) // (PALETTE_SWATCH_SIZE + PALETTE_SWATCH_GAP))
        for index, colour in enumerate(displayed):
            row = index // columns
            col = index % columns
            x0 = 8 + col * (PALETTE_SWATCH_SIZE + PALETTE_SWATCH_GAP)
            y0 = 8 + row * (PALETTE_SWATCH_SIZE + PALETTE_SWATCH_GAP)
            x1 = x0 + PALETTE_SWATCH_SIZE
            y1 = y0 + PALETTE_SWATCH_SIZE
            selected = index in self._palette_selection_indices
            self.palette_canvas.create_rectangle(
                x0,
                y0,
                x1,
                y1,
                fill=f"#{colour:06x}",
                outline="#FFFFFF" if selected else "#000000",
                width=3 if selected else 1,
            )
            if selected:
                self.palette_canvas.create_rectangle(x0 + 3, y0 + 3, x1 - 3, y1 - 3, outline="#000000", width=1)
            self._palette_hit_regions.append((x0, y0, x1, y1))
        total_rows = ((len(displayed) - 1) // columns) + 1
        self.palette_canvas.configure(height=min(110, 8 + total_rows * (PALETTE_SWATCH_SIZE + PALETTE_SWATCH_GAP)))

    def _get_display_palette(self) -> tuple[list[int], str]:
        palette, source = self._current_palette_source_labels()
        if not palette:
            return ([], "none")
        if self._palette_adjustments().is_neutral():
            return palette, source
        adjusted_palette = self._current_adjusted_structured_palette()
        if adjusted_palette is not None:
            return adjusted_palette.labels(), self._adjusted_palette_source_label(adjusted_palette)
        return palette, source

    def _update_image_info(self) -> None:
        filename = self.source_path.name if self.source_path is not None else "No image"
        current = self._current_output_result()
        resolution = f"{current.width}x{current.height}" if current is not None else "-"
        self.image_info_var.set(f"{filename}  {resolution}  {self.zoom}%")

    def _read_settings_from_controls(self, *, strict: bool) -> PreviewSettings:
        pixel_width = max(1, int(self.pixel_width_var.get()))
        if strict and pixel_width <= 0:
            raise ValueError("Pixel size must be at least 1.")
        return PreviewSettings(
            pixel_width=pixel_width,
            downsample_mode=RESIZE_DISPLAY_TO_VALUE.get(self.downsample_mode_var.get(), "nearest"),
            palette_reduction_colors=max(1, min(256, int(self.palette_reduction_colors_var.get() or 16))),
            generated_shades=max(2, min(10, int(self.generated_shades_var.get() or 4))),
            auto_detect_count=max(1, min(MAX_KEY_COLORS, int(self.auto_detect_count_var.get() or MAX_KEY_COLORS))),
            contrast_bias=max(0.1, min(1.0, float(self.contrast_bias_var.get() or 1.0))),
            palette_brightness=max(-100, min(100, int(self.palette_brightness_var.get() or 0))),
            palette_contrast=max(0, min(200, int(self.palette_contrast_var.get() or 0) + 100)),
            palette_hue=max(-180, min(180, int(self.palette_hue_var.get() or 0))),
            palette_saturation=max(0, min(200, int(self.palette_saturation_var.get() or 0) + 100)),
            palette_dither_mode=DITHER_DISPLAY_TO_VALUE.get(self.palette_dither_var.get(), "none"),
            input_mode=COLOR_MODE_DISPLAY_TO_VALUE.get(self.input_mode_var.get(), "rgba"),
            output_mode=COLOR_MODE_DISPLAY_TO_VALUE.get(self.output_mode_var.get(), "rgba"),
            quantizer=QUANTIZER_DISPLAY_TO_VALUE.get(self.quantizer_var.get(), QUANTIZER_OPTIONS[0][1]),
            dither_mode=DITHER_DISPLAY_TO_VALUE.get(self.dither_var.get(), "none"),
        )

    def _sync_controls_from_settings(self, settings: PreviewSettings) -> None:
        self._suspend_control_events = True
        try:
            self.pixel_width_var.set(settings.pixel_width)
            self.downsample_mode_var.set(RESIZE_VALUE_TO_DISPLAY.get(settings.downsample_mode, RESIZE_OPTIONS[0][0]))
            self.palette_reduction_colors_var.set(settings.palette_reduction_colors)
            self.generated_shades_var.set(str(settings.generated_shades))
            self.auto_detect_count_var.set(str(settings.auto_detect_count))
            self.contrast_bias_var.set(settings.contrast_bias)
            self.palette_brightness_var.set(settings.palette_brightness)
            self.palette_contrast_var.set(settings.palette_contrast - 100)
            self.palette_hue_var.set(settings.palette_hue)
            self.palette_saturation_var.set(settings.palette_saturation - 100)
            self.palette_dither_var.set(DITHER_VALUE_TO_DISPLAY.get(settings.palette_dither_mode, DITHER_OPTIONS[0][0]))
            self.input_mode_var.set(COLOR_MODE_VALUE_TO_DISPLAY.get(settings.input_mode, COLOR_MODE_OPTIONS[0][0]))
            self.output_mode_var.set(COLOR_MODE_VALUE_TO_DISPLAY.get(settings.output_mode, COLOR_MODE_OPTIONS[0][0]))
            self.quantizer_var.set(QUANTIZER_VALUE_TO_DISPLAY.get(settings.quantizer, QUANTIZER_OPTIONS[0][0]))
            self.dither_var.set(DITHER_VALUE_TO_DISPLAY.get(settings.dither_mode, DITHER_OPTIONS[0][0]))
        finally:
            self._suspend_control_events = False
        self._update_palette_adjustment_labels()

    def _on_settings_changed(self, _event: tk.Event | None = None) -> None:
        if self._suspend_control_events or self.image_state == "processing":
            return
        try:
            previous = self.session.current
            updated = self._read_settings_from_controls(strict=False)
        except Exception:
            return
        if updated == previous:
            self._update_scale_info()
            return
        self.session.apply(**vars(updated))
        self._handle_settings_transition(previous, updated)

    def _handle_settings_transition(self, previous: PreviewSettings, updated: PreviewSettings, message: str | None = None) -> None:
        downsample_changed = (
            previous.pixel_width != updated.pixel_width
            or previous.downsample_mode != updated.downsample_mode
            or previous.input_mode != updated.input_mode
        )
        ramp_generation_changed = (
            previous.generated_shades != updated.generated_shades
            or previous.contrast_bias != updated.contrast_bias
        )
        auto_detect_changed = previous.auto_detect_count != updated.auto_detect_count
        palette_reduction_changed = (
            previous.palette_reduction_colors != updated.palette_reduction_colors
            or previous.quantizer != updated.quantizer
        )
        palette_adjustment_changed = (
            previous.palette_brightness != updated.palette_brightness
            or previous.palette_contrast != updated.palette_contrast
            or previous.palette_hue != updated.palette_hue
            or previous.palette_saturation != updated.palette_saturation
        )
        palette_apply_changed = (
            previous.palette_dither_mode != updated.palette_dither_mode
            or previous.output_mode != updated.output_mode
            or previous.dither_mode != updated.dither_mode
        )
        if downsample_changed:
            self._clear_palette_undo_state()
            self.prepared_input_cache = None
            self.prepared_input_cache_key = None
            message = message or "Downsample settings changed. Click Downsample to update the preview."
        elif ramp_generation_changed:
            self._clear_palette_undo_state()
            self.advanced_palette_preview = None
            message = message or "Ramp settings changed. Click Generate Ramps to rebuild the palette."
        elif auto_detect_changed:
            self.process_status_var.set(f"Auto-detect count set to {updated.auto_detect_count}.")
            self._schedule_state_persist()
            self._refresh_action_states()
            return
        elif palette_reduction_changed:
            self.process_status_var.set("Palette reduction settings changed. Click Generate Reduced Palette to rebuild the palette.")
            self._schedule_state_persist()
            self._refresh_action_states()
            return
        elif palette_adjustment_changed:
            self._clear_palette_undo_state()
            if self._has_palette_source():
                if self._palette_adjustment_selection_indices():
                    message = message or "Selected palette colours changed. Click Apply Palette to update the preview."
                else:
                    message = message or "Palette adjustments changed. Click Apply Palette to update the preview."
            else:
                self.process_status_var.set("Palette adjustment settings updated.")
                self._update_palette_adjustment_labels()
                self._update_palette_strip()
                self.redraw_canvas()
                self._schedule_state_persist()
                self._refresh_action_states()
                return
        elif palette_apply_changed:
            self._clear_palette_undo_state()
            message = message or "Palette settings changed. Click Apply Palette to update the preview."
        self._mark_output_stale(message)
        self._update_key_color_list()
        self._update_palette_adjustment_labels()
        self._update_scale_info()
        self._update_palette_strip()
        self.redraw_canvas()
        self._schedule_state_persist()
        self._refresh_action_states()

    def _mark_output_stale(self, message: str | None = None) -> None:
        if self.image_state == "processing":
            return
        if self._current_output_result() is not None:
            self.image_state = "processed_stale"
        elif getattr(self, "original_grid", None) is not None:
            self.image_state = "loaded_original"
        if message:
            self.process_status_var.set(message)

    def _build_pipeline_config(self, settings: PreviewSettings) -> PipelineConfig:
        return PipelineConfig(
            pixel_width=settings.pixel_width,
            downsample_mode=settings.downsample_mode,
            colors=len(self.key_colors) * (settings.generated_shades + 1),
            palette_strategy="override" if self._palette_is_override_mode() else "advanced",
            key_colors=tuple(self._current_key_colors()),
            generated_shades=settings.generated_shades,
            contrast_bias=settings.contrast_bias,
            palette_dither_mode=settings.palette_dither_mode,
            input_mode=settings.input_mode,
            output_mode=settings.output_mode,
            quantizer=settings.quantizer,
            dither_mode=settings.dither_mode,
        )

    @staticmethod
    def _build_prepare_cache_key(settings: PreviewSettings) -> tuple[object, ...]:
        return (
            settings.pixel_width,
            settings.downsample_mode,
            settings.input_mode,
        )

    def _refresh_action_states(self) -> None:
        busy = self.image_state == "processing"
        has_image = self.original_grid is not None
        has_output = self._current_output_result() is not None
        has_downsample = self.prepared_input_cache is not None
        has_palette_source = self._has_palette_source()
        can_save = self.image_state == "processed_current" and has_output
        has_palette_selection = bool(self._palette_selection_indices)
        valid_palette_selection = [
            index for index in getattr(self, "_palette_selection_indices", set()) if 0 <= index < len(getattr(self, "_displayed_palette", []))
        ]
        has_single_palette_selection = len(valid_palette_selection) == 1
        can_undo = (self._palette_undo_state is not None) or self.session.history.can_undo()
        advanced_editable = has_image and not busy and not self._palette_is_override_mode()
        for widget, enabled in (
            (self.downsample_button, has_image and not busy),
            (self.generate_ramps_button, advanced_editable and bool(self.key_colors)),
            (self.generate_override_palette_button, has_downsample and not busy),
            (self.reduce_palette_button, has_downsample and not busy and has_palette_source),
            (self.transparency_button, has_output and not busy),
            (self.add_outline_button, has_output and not busy and has_single_palette_selection),
            (self.remove_outline_button, has_output and not busy),
            (self.zoom_in_button, has_image and not busy),
            (self.zoom_out_button, has_image and not busy),
            (self.pick_seed_button, advanced_editable),
            (self.auto_detect_button, advanced_editable),
            (self.remove_seed_button, advanced_editable and bool(self.key_color_listbox.curselection())),
            (self.clear_seeds_button, advanced_editable and bool(self.key_colors)),
            (self.add_palette_color_button, has_image and not busy),
            (self.select_all_palette_button, has_palette_source and not busy),
            (self.clear_palette_selection_button, has_palette_selection and not busy),
            (self.remove_palette_color_button, has_palette_source and has_palette_selection and not busy),
        ):
            widget.configure(state=tk.NORMAL if enabled else tk.DISABLED)
        self.pick_seed_button.configure(text="Cancel Pick" if self.key_color_pick_mode else "Pick Colour")
        self.transparency_button.configure(text="Cancel Transparency" if self.transparency_pick_mode else "Make Transparent")
        self.pixel_width_spinbox.configure(state="normal" if has_image and not busy else "disabled")
        self.palette_reduction_spinbox.configure(state="normal" if has_image and not busy else "disabled")
        self.key_color_listbox.configure(state=tk.NORMAL if advanced_editable else tk.DISABLED)
        adjustment_state = tk.NORMAL if has_palette_source and not busy else tk.DISABLED
        for control in getattr(self, "palette_adjustment_controls", []):
            control.configure(state=adjustment_state)
        self._menu_items["view"].entryconfigure("Processed", state=tk.NORMAL if has_output else tk.DISABLED)
        self._menu_items["file"].entryconfigure("Save", state=tk.NORMAL if can_save else tk.DISABLED)
        self._menu_items["file"].entryconfigure("Save As...", state=tk.NORMAL if can_save else tk.DISABLED)
        self._menu_items["edit"].entryconfigure("Undo", state=tk.NORMAL if can_undo and not busy else tk.DISABLED)
        self._menu_items["edit"].entryconfigure("Downsample", state=tk.NORMAL if has_image and not busy else tk.DISABLED)
        self._menu_items["edit"].entryconfigure(
            "Apply Palette",
            state=tk.NORMAL if has_downsample and not busy and has_palette_source else tk.DISABLED,
        )
        self._menu_items["palette"].entryconfigure("Input Mode", state=tk.NORMAL if not busy else tk.DISABLED)
        self._menu_items["palette"].entryconfigure("Output Mode", state=tk.NORMAL if not busy else tk.DISABLED)
        self._menu_items["palette"].entryconfigure("Built-in Palettes", state=tk.NORMAL if not busy else tk.DISABLED)
        self._menu_items["palette"].entryconfigure("Add Colour", state=tk.NORMAL if not busy else tk.DISABLED)
        self._menu_items["palette"].entryconfigure("Sort Current Palette", state=tk.NORMAL if self._has_palette_source() and not busy else tk.DISABLED)
        self._menu_items["palette"].entryconfigure("Load Palette...", state=tk.NORMAL if not busy else tk.DISABLED)
        self._menu_items["palette"].entryconfigure("Save Current Palette...", state=tk.NORMAL if self._has_palette_source() and not busy else tk.DISABLED)
        if hasattr(self, "_menu_bar"):
            self._menu_bar.entryconfigure("Select", state=tk.NORMAL if has_palette_source and not busy else tk.DISABLED)
        self._menu_items["palette_add"].entryconfigure("Pick From Original", state=tk.NORMAL if has_image and not busy else tk.DISABLED)
        self._menu_items["palette_add"].entryconfigure("Enter Hex Code...", state=tk.NORMAL if not busy else tk.DISABLED)
        self._menu_items["preferences"].entryconfigure("Resize Method", state=tk.NORMAL if not busy else tk.DISABLED)
        self._menu_items["preferences"].entryconfigure("Palette Reduction Method", state=tk.NORMAL if not busy else tk.DISABLED)
        self._menu_items["preferences"].entryconfigure("Colour Ramp", state=tk.NORMAL if not busy else tk.DISABLED)
        self._menu_items["preferences"].entryconfigure("Dithering Method", state=tk.NORMAL if not busy else tk.DISABLED)
        self._menu_items["preferences"].entryconfigure("Selection Threshold", state=tk.NORMAL if not busy else tk.DISABLED)
        self._refresh_primary_button_style(self.downsample_button)
        self._refresh_primary_button_style(self.reduce_palette_button)

    def _image_x_to_canvas(self, value: int, image_width: int) -> int:
        if self._display_context is None:
            return 0
        return self._display_context.image_left + round((value / max(image_width, 1)) * self._display_context.display_width)

    def _image_y_to_canvas(self, value: int, image_height: int) -> int:
        if self._display_context is None:
            return 0
        return self._display_context.image_top + round((value / max(image_height, 1)) * self._display_context.display_height)

    def _on_overlay_changed(self) -> None:
        self.redraw_canvas()
        self._schedule_state_persist()

    def _schedule_state_persist(self) -> None:
        if self._persist_after_id is not None:
            self.root.after_cancel(self._persist_after_id)
        self._persist_after_id = self.root.after(200, self._persist_state)

    def _persist_state(self) -> None:
        self._persist_after_id = None
        settings_data = serialize_settings(self.session.current)
        for field in ("palette_brightness", "palette_contrast", "palette_hue", "palette_saturation"):
            settings_data.pop(field, None)
        save_app_state(
            {
                "settings": settings_data,
                "last_output_path": self.last_output_path,
                "last_successful_process_snapshot": self.last_successful_process_snapshot,
                "zoom": self.zoom,
                "selection_threshold": self._selection_threshold_percent(),
                "checkerboard": self.checkerboard_var.get(),
                "view_mode": self.view_var.get(),
                "recent_files": self.recent_files,
            }
        )

    def _on_close(self) -> None:
        if self._persist_after_id is not None:
            self.root.after_cancel(self._persist_after_id)
        self._persist_state()
        self.root.destroy()

    @staticmethod
    def _normalize_recent_files(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if isinstance(item, str)]


def main() -> int:
    root = tk.Tk()
    PixelFixGui(root)
    root.mainloop()
    return 0

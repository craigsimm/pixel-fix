from __future__ import annotations

import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass, replace
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageDraw, ImageTk

from pixel_fix.palette.io import load_palette, save_palette
from pixel_fix.palette.adjust import PaletteAdjustments, adjust_structured_palette
from pixel_fix.palette.advanced import structured_palette_from_override
from pixel_fix.palette.catalog import PaletteCatalogEntry, discover_palette_catalog
from pixel_fix.palette.color_modes import extract_unique_colors
from pixel_fix.palette.edit import generate_ramp_palette_labels, merge_palette_labels
from pixel_fix.palette.model import StructuredPalette, clone_structured_palette
from pixel_fix.palette.quantize import generate_palette as generate_override_palette
from pixel_fix.palette.sort import (
    PALETTE_SELECT_DIRECT_MODES,
    PALETTE_SELECT_HUE_MODES,
    PALETTE_SELECT_LABELS,
    PALETTE_SELECT_MODES,
    PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES,
    PALETTE_SELECT_SPECIAL_MODES,
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
    BRUSH_SHAPE_ROUND,
    BRUSH_SHAPE_SQUARE,
    BRUSH_WIDTH_DEFAULT,
    BRUSH_WIDTH_MAX,
    OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_BRIGHT,
    OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK,
    OUTLINE_REMOVE_BRIGHTNESS_THRESHOLD_DEFAULT,
    ProcessResult,
    RGBGrid,
    add_exterior_outline,
    apply_eraser_operation,
    apply_eraser_operations,
    apply_pencil_operation,
    apply_pencil_operations,
    apply_transparency_fill,
    brush_footprint,
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
from .theme import (
    APP_ACCENT,
    APP_BG,
    APP_BORDER,
    APP_HOVER_BG,
    HEADER_FONT_FAMILY,
    HEADER_FONT_SIZE,
    APP_MUTED_TEXT,
    APP_SURFACE_BG,
    APP_TEXT,
    PIXEL_FONT_FAMILY,
    UI_FONT_SIZE,
    load_font_family,
)
from .tooltips import Tooltip
from .zoom import ZOOM_PRESETS, choose_fit_zoom, clamp_zoom, zoom_in, zoom_out

OPEN_HAND_CURSOR = "hand2"
CLOSED_HAND_CURSOR = "fleur"
MAX_PALETTE_SWATCHES = 256
PALETTE_SWATCH_SIZE = 18
PALETTE_SWATCH_GAP = 0
SECTION_CONTENT_PADDING = 8
TOOL_BUTTON_PADDING = (0, 0)
TOOL_BUTTON_WIDTH = 40
TOOL_BUTTON_HEIGHT = 40
ACTIVE_COLOR_SLOT_PRIMARY = "primary"
ACTIVE_COLOR_SLOT_SECONDARY = "secondary"
ACTIVE_COLOR_DEFAULT_LABEL = 0xFFFFFF
ACTIVE_COLOR_BACK_BOUNDS = (2, 2, 17, 17)
ACTIVE_COLOR_FRONT_BOUNDS = (12, 12, 27, 27)
ACTIVE_COLOR_PREVIEW_PLACEHOLDER_FRONT = (0, 255, 0, 255)
ACTIVE_COLOR_PREVIEW_PLACEHOLDER_BACK = (0, 255, 255, 255)
ACTIVE_COLOR_PREVIEW_TEMPLATE_NONE = "current_no_transparent.png"
ACTIVE_COLOR_PREVIEW_TEMPLATE_FRONT_TRANSPARENT = "current_transparent_primary.png"
ACTIVE_COLOR_PREVIEW_TEMPLATE_BACK_TRANSPARENT = "current_transparent_secondary.png"
PALETTE_DROPDOWN_POST_X_OFFSET = 164
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
PALETTE_SELECT_SPECIAL_OPTIONS = tuple((PALETTE_SELECT_LABELS[mode], mode) for mode in PALETTE_SELECT_SPECIAL_MODES)

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
OUTLINE_COLOUR_MODE_PALETTE = "palette"
OUTLINE_COLOUR_MODE_ADAPTIVE = "adaptive"
OUTLINE_ADAPTIVE_DARKEN_DEFAULT = 60
CANVAS_TOOL_MODE_PALETTE_PICK = "palette-pick"
CANVAS_TOOL_MODE_ACTIVE_COLOR_PICK = "active-color-pick"
CANVAS_TOOL_MODE_TRANSPARENCY_PICK = "transparency-pick"
CANVAS_TOOL_MODE_PENCIL = "pencil"
CANVAS_TOOL_MODE_ERASER = "eraser"


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
        self._configure_theme()

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
        self.advanced_palette_preview: StructuredPalette | None = None
        self.canvas_tool_mode: str | None = None
        self.palette_add_pick_mode = False
        self.transparency_pick_mode = False
        self._brush_stroke_active = False
        self._brush_stroke_last_point: tuple[int, int] | None = None
        self._brush_stroke_changed_pixels = 0
        self._brush_stroke_tool_mode: str | None = None
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
        self._builtin_palette_menu_entries: dict[tuple[tk.Menu, int], PaletteCatalogEntry] = {}
        self._builtin_palette_menus: list[tk.Menu] = []
        self._builtin_palette_preview_entry: PaletteCatalogEntry | None = None
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
        self._tool_button_icons: dict[tuple[str, bool], ImageTk.PhotoImage] = {}
        self._tool_button_assets: dict[str, str] = {}
        self._tool_button_enabled: dict[str, bool] = {}
        self._tool_button_frames: dict[str, tk.Frame] = {}
        self._active_color_preview_templates: dict[str, Image.Image] = {}
        self._active_color_preview_image_ref: ImageTk.PhotoImage | None = None
        self._tooltips: list[Tooltip] = []
        self._persist_after_id: str | None = None
        self._suspend_control_events = False
        self._palette_undo_state: PaletteUndoState | None = None
        self._palette_redo_state: PaletteUndoState | None = None
        primary_label, secondary_label, transparent_slot, active_slot = self._initial_active_color_state(persisted)
        self.primary_color_label = primary_label
        self.secondary_color_label = secondary_label
        self.transparent_color_slot = transparent_slot
        self.active_color_slot = active_slot

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
        self.outline_pixel_perfect_var = tk.BooleanVar(value=bool(persisted.get("outline_pixel_perfect", True)))
        self.outline_colour_mode_var = tk.StringVar(value=self._initial_outline_colour_mode(persisted))
        self.outline_adaptive_darken_percent_var = tk.IntVar(
            value=self._coerce_outline_adaptive_darken_percent(persisted.get("outline_adaptive_darken_percent", OUTLINE_ADAPTIVE_DARKEN_DEFAULT))
        )
        self.outline_add_generated_colours_var = tk.BooleanVar(value=bool(persisted.get("outline_add_generated_colours", False)))
        self.outline_remove_brightness_threshold_enabled_var = tk.BooleanVar(
            value=bool(persisted.get("outline_remove_brightness_threshold_enabled", False))
        )
        self.outline_remove_brightness_threshold_percent_var = tk.IntVar(
            value=self._coerce_outline_remove_brightness_threshold_percent(
                persisted.get("outline_remove_brightness_threshold_percent", OUTLINE_REMOVE_BRIGHTNESS_THRESHOLD_DEFAULT)
            )
        )
        self.outline_remove_brightness_threshold_direction_var = tk.StringVar(
            value=self._coerce_outline_remove_brightness_direction(
                persisted.get("outline_remove_brightness_threshold_direction", OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK)
            )
        )
        self.brush_width_var = tk.IntVar(value=self._coerce_brush_width(persisted.get("brush_width", BRUSH_WIDTH_DEFAULT)))
        self.brush_shape_var = tk.StringVar(value=self._coerce_brush_shape(persisted.get("brush_shape", BRUSH_SHAPE_SQUARE)).title())
        self.process_status_var = tk.StringVar(value="Open a PNG image to begin.")
        self.scale_info_var = tk.StringVar(value="Open an image to set the pixel size.")
        self.palette_info_var = tk.StringVar(value="Palette: none")
        self.image_info_var = tk.StringVar(value="No image  -  100%")
        self.pick_preview_var = tk.StringVar(value="")
        self.palette_brightness_value_var = tk.StringVar(value="0%")
        self.palette_contrast_value_var = tk.StringVar(value="0%")
        self.palette_hue_value_var = tk.StringVar(value="0%")
        self.palette_saturation_value_var = tk.StringVar(value="0%")
        self.palette_dropdown_var = tk.StringVar(value="Built-in palettes")

        self._menu_items: dict[str, tk.Menu] = {}
        self._build_menu_bar()
        self._build_layout()
        self._sync_controls_from_settings(self.session.current)
        self._update_scale_info()
        self._update_palette_strip()
        self._refresh_active_color_preview()
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

    def _configure_theme(self) -> None:
        self.ui_font_family = load_font_family(self.root, self._resource_path("fonts/pixelmix.ttf"), PIXEL_FONT_FAMILY)
        self.ui_header_font_family = load_font_family(self.root, self._resource_path("fonts/pixelmix.ttf"), HEADER_FONT_FAMILY)
        self.ui_font = tkfont.Font(root=self.root, name="PixelFixBaseFont", family=self.ui_font_family, size=UI_FONT_SIZE)
        self.ui_header_font = tkfont.Font(
            root=self.root,
            name="PixelFixHeaderFont",
            family=self.ui_header_font_family,
            size=HEADER_FONT_SIZE,
        )
        self.root.configure(background=APP_BG)
        self.root.option_add("*Font", self.ui_font)
        self.root.option_add("*Background", APP_BG)
        self.root.option_add("*Foreground", APP_TEXT)
        self.root.option_add("*highlightBackground", APP_BORDER)
        self.root.option_add("*highlightColor", APP_BORDER)
        self.root.option_add("*insertBackground", APP_TEXT)
        self.root.option_add("*selectBackground", APP_HOVER_BG)
        self.root.option_add("*selectForeground", APP_TEXT)

        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", background=APP_BG, foreground=APP_TEXT, font=self.ui_font)
        style.configure("TFrame", background=APP_BG)
        style.configure("TLabel", background=APP_BG, foreground=APP_TEXT)
        style.configure(
            "TLabelframe",
            background=APP_BG,
            foreground=APP_TEXT,
            bordercolor=APP_BORDER,
            borderwidth=1,
            darkcolor=APP_BORDER,
            lightcolor=APP_BORDER,
            relief=tk.SOLID,
        )
        style.configure("TLabelframe.Label", background=APP_BG, foreground=APP_TEXT, font=self.ui_header_font)
        style.configure(
            "TButton",
            background=APP_SURFACE_BG,
            foreground=APP_TEXT,
            bordercolor=APP_BORDER,
            darkcolor=APP_BORDER,
            lightcolor=APP_BORDER,
            padding=(6, 4),
        )
        style.map(
            "TButton",
            background=[("pressed", APP_ACCENT), ("active", APP_HOVER_BG), ("disabled", APP_BG)],
            foreground=[("pressed", APP_BG), ("disabled", APP_MUTED_TEXT)],
            bordercolor=[("pressed", APP_ACCENT), ("active", APP_BORDER)],
            darkcolor=[("pressed", APP_ACCENT), ("active", APP_BORDER), ("disabled", APP_BORDER)],
            lightcolor=[("pressed", APP_ACCENT), ("active", APP_BORDER), ("disabled", APP_BORDER)],
        )
        style.configure(
            "TMenubutton",
            background=APP_SURFACE_BG,
            foreground=APP_TEXT,
            bordercolor=APP_BORDER,
            darkcolor=APP_BORDER,
            lightcolor=APP_BORDER,
            arrowcolor=APP_TEXT,
            padding=(6, 4),
        )
        style.map(
            "TMenubutton",
            background=[("pressed", APP_ACCENT), ("active", APP_HOVER_BG), ("disabled", APP_BG)],
            foreground=[("pressed", APP_BG), ("disabled", APP_MUTED_TEXT)],
            bordercolor=[("pressed", APP_ACCENT), ("active", APP_BORDER), ("disabled", APP_BORDER)],
            darkcolor=[("pressed", APP_ACCENT), ("active", APP_BORDER), ("disabled", APP_BORDER)],
            lightcolor=[("pressed", APP_ACCENT), ("active", APP_BORDER), ("disabled", APP_BORDER)],
            arrowcolor=[("pressed", APP_BG), ("disabled", APP_MUTED_TEXT)],
        )
        style.configure(
            "ToolButton.TButton",
            background=APP_SURFACE_BG,
            foreground=APP_TEXT,
            bordercolor=APP_SURFACE_BG,
            borderwidth=0,
            darkcolor=APP_SURFACE_BG,
            lightcolor=APP_SURFACE_BG,
            padding=TOOL_BUTTON_PADDING,
            relief=tk.FLAT,
        )
        style.map(
            "ToolButton.TButton",
            background=[("pressed", APP_ACCENT), ("active", APP_HOVER_BG), ("disabled", APP_BG)],
            foreground=[("pressed", APP_BG), ("disabled", APP_MUTED_TEXT)],
            bordercolor=[("pressed", APP_ACCENT), ("active", APP_HOVER_BG), ("disabled", APP_BG)],
            darkcolor=[("pressed", APP_ACCENT), ("active", APP_HOVER_BG), ("disabled", APP_BG)],
            lightcolor=[("pressed", APP_ACCENT), ("active", APP_HOVER_BG), ("disabled", APP_BG)],
        )
        style.configure(
            "ToolButtonDisabled.TButton",
            background=APP_SURFACE_BG,
            foreground=APP_MUTED_TEXT,
            bordercolor=APP_SURFACE_BG,
            borderwidth=0,
            darkcolor=APP_SURFACE_BG,
            lightcolor=APP_SURFACE_BG,
            padding=TOOL_BUTTON_PADDING,
            relief=tk.FLAT,
        )
        style.map(
            "ToolButtonDisabled.TButton",
            background=[("pressed", APP_SURFACE_BG), ("active", APP_SURFACE_BG), ("disabled", APP_SURFACE_BG)],
            foreground=[("pressed", APP_MUTED_TEXT), ("active", APP_MUTED_TEXT), ("disabled", APP_MUTED_TEXT)],
            bordercolor=[("pressed", APP_SURFACE_BG), ("active", APP_SURFACE_BG), ("disabled", APP_SURFACE_BG)],
            darkcolor=[("pressed", APP_SURFACE_BG), ("active", APP_SURFACE_BG), ("disabled", APP_SURFACE_BG)],
            lightcolor=[("pressed", APP_SURFACE_BG), ("active", APP_SURFACE_BG), ("disabled", APP_SURFACE_BG)],
        )
        style.configure(
            "ToolButtonActive.TButton",
            background=APP_ACCENT,
            foreground=APP_BG,
            bordercolor=APP_ACCENT,
            darkcolor=APP_ACCENT,
            lightcolor=APP_ACCENT,
            borderwidth=0,
            padding=TOOL_BUTTON_PADDING,
            relief=tk.FLAT,
        )
        style.map(
            "ToolButtonActive.TButton",
            background=[("pressed", APP_ACCENT), ("active", APP_ACCENT), ("disabled", APP_BG)],
            foreground=[("pressed", APP_BG), ("active", APP_BG), ("disabled", APP_MUTED_TEXT)],
            bordercolor=[("pressed", APP_ACCENT), ("active", APP_ACCENT), ("disabled", APP_BORDER)],
            darkcolor=[("pressed", APP_ACCENT), ("active", APP_ACCENT), ("disabled", APP_BORDER)],
            lightcolor=[("pressed", APP_ACCENT), ("active", APP_ACCENT), ("disabled", APP_BORDER)],
        )
        style.configure(
            "TCheckbutton",
            background=APP_BG,
            foreground=APP_TEXT,
            indicatorbackground=APP_BG,
            indicatorforeground=APP_TEXT,
            upperbordercolor=APP_BORDER,
            lowerbordercolor=APP_BORDER,
            padding=(2, 2),
        )
        style.map(
            "TCheckbutton",
            background=[("active", APP_BG), ("disabled", APP_BG)],
            foreground=[("disabled", APP_MUTED_TEXT)],
            indicatorbackground=[("disabled", APP_BG), ("pressed", APP_ACCENT), ("selected", APP_ACCENT)],
            indicatorforeground=[("disabled", APP_MUTED_TEXT), ("selected", APP_BG)],
            upperbordercolor=[("disabled", APP_BORDER), ("pressed", APP_ACCENT), ("selected", APP_ACCENT), ("active", APP_BORDER)],
            lowerbordercolor=[("disabled", APP_BORDER), ("pressed", APP_ACCENT), ("selected", APP_ACCENT), ("active", APP_BORDER)],
        )
        style.configure(
            "TRadiobutton",
            background=APP_BG,
            foreground=APP_TEXT,
            indicatorbackground=APP_BG,
            indicatorforeground=APP_TEXT,
            upperbordercolor=APP_BORDER,
            lowerbordercolor=APP_BORDER,
            padding=(2, 2),
        )
        style.map(
            "TRadiobutton",
            background=[("active", APP_BG), ("disabled", APP_BG)],
            foreground=[("disabled", APP_MUTED_TEXT)],
            indicatorbackground=[("disabled", APP_BG), ("pressed", APP_ACCENT), ("selected", APP_ACCENT)],
            indicatorforeground=[("disabled", APP_MUTED_TEXT), ("selected", APP_BG)],
            upperbordercolor=[("disabled", APP_BORDER), ("pressed", APP_ACCENT), ("selected", APP_ACCENT), ("active", APP_BORDER)],
            lowerbordercolor=[("disabled", APP_BORDER), ("pressed", APP_ACCENT), ("selected", APP_ACCENT), ("active", APP_BORDER)],
        )
        style.configure(
            "TSpinbox",
            arrowsize=10,
            arrowcolor=APP_TEXT,
            bordercolor=APP_BORDER,
            darkcolor=APP_BORDER,
            fieldbackground=APP_SURFACE_BG,
            foreground=APP_TEXT,
            lightcolor=APP_BORDER,
            padding=(4, 2),
        )
        style.map(
            "TSpinbox",
            arrowcolor=[("disabled", APP_MUTED_TEXT)],
            fieldbackground=[("disabled", APP_BG), ("readonly", APP_SURFACE_BG)],
            foreground=[("disabled", APP_MUTED_TEXT)],
            bordercolor=[("disabled", APP_BORDER), ("focus", APP_BORDER)],
            darkcolor=[("disabled", APP_BORDER), ("focus", APP_BORDER)],
            lightcolor=[("disabled", APP_BORDER), ("focus", APP_BORDER)],
        )

    def _new_menu(self, master: tk.Misc) -> tk.Menu:
        return tk.Menu(
            master,
            tearoff=False,
            activebackground=APP_HOVER_BG,
            activeforeground=APP_TEXT,
            background=APP_BG,
            bd=0,
            disabledforeground=APP_MUTED_TEXT,
            fg=APP_TEXT,
            font=self.ui_font,
            relief=tk.FLAT,
            selectcolor=APP_ACCENT,
        )

    @staticmethod
    def _coerce_outline_colour_mode(value: object) -> str:
        normalized = str(value or OUTLINE_COLOUR_MODE_PALETTE).strip().lower()
        if normalized == OUTLINE_COLOUR_MODE_ADAPTIVE:
            return OUTLINE_COLOUR_MODE_ADAPTIVE
        return OUTLINE_COLOUR_MODE_PALETTE

    @staticmethod
    def _coerce_outline_adaptive_darken_percent(value: object) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = OUTLINE_ADAPTIVE_DARKEN_DEFAULT
        return max(0, min(100, parsed))

    @staticmethod
    def _coerce_outline_remove_brightness_threshold_percent(value: object) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = OUTLINE_REMOVE_BRIGHTNESS_THRESHOLD_DEFAULT
        return max(0, min(100, parsed))

    @staticmethod
    def _coerce_outline_remove_brightness_direction(value: object) -> str:
        normalized = str(value or OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK).strip().lower()
        if normalized == OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_BRIGHT:
            return OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_BRIGHT
        return OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK

    @staticmethod
    def _coerce_brush_width(value: object) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = BRUSH_WIDTH_DEFAULT
        return max(1, min(BRUSH_WIDTH_MAX, parsed))

    @staticmethod
    def _coerce_brush_shape(value: object) -> str:
        normalized = str(value or BRUSH_SHAPE_SQUARE).strip().lower()
        if normalized == BRUSH_SHAPE_ROUND:
            return BRUSH_SHAPE_ROUND
        return BRUSH_SHAPE_SQUARE

    @classmethod
    def _initial_outline_colour_mode(cls, persisted: dict[str, object]) -> str:
        if "outline_colour_mode" in persisted:
            return cls._coerce_outline_colour_mode(persisted.get("outline_colour_mode"))
        return OUTLINE_COLOUR_MODE_ADAPTIVE if bool(persisted.get("outline_adaptive", False)) else OUTLINE_COLOUR_MODE_PALETTE

    def _build_menu_bar(self) -> None:
        menubar = self._new_menu(self.root)

        file_menu = self._new_menu(menubar)
        file_menu.add_command(label="Open...", accelerator="Ctrl+O", command=self.open_image)
        self.recent_menu = self._new_menu(file_menu)
        file_menu.add_cascade(label="Recent", menu=self.recent_menu)
        file_menu.add_separator()
        file_menu.add_command(label="Save", accelerator="Ctrl+S", command=self.save_processed_image)
        file_menu.add_command(label="Save As...", accelerator="Ctrl+Shift+S", command=self.save_processed_image_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", accelerator="Alt+F4", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        edit_menu = self._new_menu(menubar)
        edit_menu.add_command(label="Undo", accelerator="Ctrl+Z", command=self.undo)
        edit_menu.add_command(label="Redo", accelerator="Ctrl+Y", command=self.redo)
        edit_menu.add_command(label="Downsample", accelerator="F5", command=self.downsample_current_image)
        edit_menu.add_command(label="Apply Palette", accelerator="F6", command=self.reduce_palette_current_image)
        menubar.add_cascade(label="Edit", menu=edit_menu)

        view_menu = self._new_menu(menubar)
        view_menu.add_radiobutton(label="Original", value="original", variable=self.view_var, accelerator="Ctrl+1", command=self._on_view_changed)
        view_menu.add_radiobutton(label="Processed", value="processed", variable=self.view_var, accelerator="Ctrl+2", command=self._on_view_changed)
        menubar.add_cascade(label="View", menu=view_menu)

        palette_menu = self._new_menu(menubar)
        input_menu = self._new_menu(palette_menu)
        for label, _value in COLOR_MODE_OPTIONS:
            input_menu.add_radiobutton(label=label, value=label, variable=self.input_mode_var, command=self._on_settings_changed)
        output_menu = self._new_menu(palette_menu)
        for label, _value in COLOR_MODE_OPTIONS:
            output_menu.add_radiobutton(label=label, value=label, variable=self.output_mode_var, command=self._on_settings_changed)
        built_in_menu = self._new_menu(palette_menu)
        add_colour_menu = self._new_menu(palette_menu)
        sort_menu = self._new_menu(palette_menu)
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

        select_menu = self._new_menu(menubar)
        select_hue_menu = self._new_menu(select_menu)
        for label, mode in PALETTE_SELECT_OPTIONS:
            select_menu.add_command(label=label, command=lambda value=mode: self.select_current_palette(value))
        select_menu.add_cascade(label="Hue", menu=select_hue_menu)
        for label, mode in PALETTE_SELECT_HUE_OPTIONS:
            select_hue_menu.add_command(label=label, command=lambda value=mode: self.select_current_palette(value))
        for label, mode in PALETTE_SELECT_SPECIAL_OPTIONS:
            select_menu.add_command(label=label, command=lambda value=mode: self.select_current_palette(value))
        menubar.add_cascade(label="Select", menu=select_menu)

        zoom_menu = self._new_menu(menubar)
        for value in ZOOM_PRESETS:
            zoom_menu.add_command(label=f"{value}%", command=lambda zoom=value: self._set_zoom(zoom))
        zoom_menu.add_separator()
        zoom_menu.add_command(label="Fit", accelerator="Ctrl+0", command=self.zoom_fit)
        menubar.add_cascade(label="Zoom", menu=zoom_menu)

        preferences_menu = self._new_menu(menubar)
        resize_menu = self._new_menu(preferences_menu)
        for label, _value in RESIZE_OPTIONS:
            resize_menu.add_radiobutton(label=label, value=label, variable=self.downsample_mode_var, command=self._on_settings_changed)
        palette_reduction_menu = self._new_menu(preferences_menu)
        for label, _value in QUANTIZER_OPTIONS:
            palette_reduction_menu.add_radiobutton(label=label, value=label, variable=self.quantizer_var, command=self._on_settings_changed)
        colour_ramp_menu = self._new_menu(preferences_menu)
        ramp_steps_menu = self._new_menu(colour_ramp_menu)
        for value in GENERATED_SHADES_OPTIONS:
            ramp_steps_menu.add_radiobutton(label=str(value), value=str(value), variable=self.generated_shades_var, command=self._on_settings_changed)
        ramp_contrast_menu = self._new_menu(colour_ramp_menu)
        for value in RAMP_CONTRAST_OPTIONS:
            ramp_contrast_menu.add_radiobutton(label=f"{value}%", value=value / 100.0, variable=self.contrast_bias_var, command=self._on_settings_changed)
        colour_ramp_menu.add_cascade(label="Ramp Steps", menu=ramp_steps_menu)
        colour_ramp_menu.add_cascade(label="Ramp Contrast", menu=ramp_contrast_menu)
        dithering_menu = self._new_menu(preferences_menu)
        for label, _value in DITHER_OPTIONS:
            dithering_menu.add_radiobutton(label=label, value=label, variable=self.palette_dither_var, command=self._on_settings_changed)
        selection_threshold_menu = self._new_menu(preferences_menu)
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

        scale_section = self._create_section(sidebar, "Pixel scale")
        row = ttk.Frame(scale_section)
        row.pack(fill=tk.X)
        self.pixel_width_spinbox = ttk.Spinbox(row, from_=1, to=512, textvariable=self.pixel_width_var, width=8, command=self._on_settings_changed)
        self.pixel_width_spinbox.pack(side=tk.LEFT)
        self.downsample_button = ttk.Button(row, text="Downsample", command=self.downsample_current_image)
        self.downsample_button.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(scale_section, textvariable=self.scale_info_var, wraplength=300).pack(anchor=tk.W, pady=(6, 0))

        palette_section = self._create_section(sidebar, "Options")
        brush_settings_row = ttk.Frame(palette_section)
        brush_settings_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(brush_settings_row, text="Width").pack(side=tk.LEFT)
        self.brush_width_spinbox = ttk.Spinbox(
            brush_settings_row,
            from_=1,
            to=BRUSH_WIDTH_MAX,
            textvariable=self.brush_width_var,
            width=5,
            command=self._on_brush_width_changed,
        )
        self.brush_width_spinbox.pack(side=tk.LEFT, padx=(8, 0))
        self.brush_shape_dropdown_button = ttk.Menubutton(
            brush_settings_row,
            textvariable=self.brush_shape_var,
        )
        self.brush_shape_dropdown_button.pack(side=tk.LEFT, padx=(10, 0))
        self.brush_shape_dropdown_menu = self._new_menu(self.brush_shape_dropdown_button)
        for shape in (BRUSH_SHAPE_SQUARE, BRUSH_SHAPE_ROUND):
            display_value = shape.title()
            self.brush_shape_dropdown_menu.add_command(
                label=display_value,
                command=lambda value=display_value: self._select_brush_shape(value),
            )
        self.brush_shape_dropdown_button.configure(menu=self.brush_shape_dropdown_menu)
        outline_row = ttk.Frame(palette_section)
        outline_row.pack(fill=tk.X, pady=(8, 0))
        self.outline_pixel_perfect_toggle = ttk.Checkbutton(
            outline_row,
            text="Pixel Perfect",
            variable=self.outline_pixel_perfect_var,
            command=self._on_outline_pixel_perfect_changed,
        )
        self.outline_pixel_perfect_toggle.pack(side=tk.LEFT)
        outline_mode_row = ttk.Frame(palette_section)
        outline_mode_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(outline_mode_row, text="Outline Colour").pack(side=tk.LEFT)
        self.outline_palette_mode_button = ttk.Radiobutton(
            outline_mode_row,
            text="Selected Palette",
            value=OUTLINE_COLOUR_MODE_PALETTE,
            variable=self.outline_colour_mode_var,
            command=self._on_outline_colour_mode_changed,
        )
        self.outline_palette_mode_button.pack(side=tk.LEFT, padx=(10, 0))
        self.outline_adaptive_mode_button = ttk.Radiobutton(
            outline_mode_row,
            text="Adaptive",
            value=OUTLINE_COLOUR_MODE_ADAPTIVE,
            variable=self.outline_colour_mode_var,
            command=self._on_outline_colour_mode_changed,
        )
        self.outline_adaptive_mode_button.pack(side=tk.LEFT, padx=(10, 0))
        outline_adaptive_row = ttk.Frame(palette_section)
        outline_adaptive_row.pack(fill=tk.X, pady=(6, 0))
        self.outline_adaptive_darken_label = ttk.Label(outline_adaptive_row, text="Darken %")
        self.outline_adaptive_darken_label.pack(side=tk.LEFT)
        self.outline_adaptive_darken_spinbox = ttk.Spinbox(
            outline_adaptive_row,
            from_=0,
            to=100,
            textvariable=self.outline_adaptive_darken_percent_var,
            width=5,
            command=self._on_outline_adaptive_darken_changed,
        )
        self.outline_adaptive_darken_spinbox.pack(side=tk.LEFT, padx=(8, 0))
        self.outline_add_generated_colours_toggle = ttk.Checkbutton(
            outline_adaptive_row,
            text="Add Generated Colours",
            variable=self.outline_add_generated_colours_var,
            command=self._on_outline_add_generated_colours_changed,
        )
        self.outline_add_generated_colours_toggle.pack(side=tk.LEFT, padx=(10, 0))
        outline_remove_filter_row = ttk.Frame(palette_section)
        outline_remove_filter_row.pack(fill=tk.X, pady=(6, 0))
        self.outline_remove_brightness_threshold_toggle = ttk.Checkbutton(
            outline_remove_filter_row,
            text="Brightness Threshold",
            variable=self.outline_remove_brightness_threshold_enabled_var,
            command=self._on_outline_remove_brightness_threshold_enabled_changed,
        )
        self.outline_remove_brightness_threshold_toggle.pack(side=tk.LEFT)
        self.outline_remove_brightness_threshold_spinbox = ttk.Spinbox(
            outline_remove_filter_row,
            from_=0,
            to=100,
            textvariable=self.outline_remove_brightness_threshold_percent_var,
            width=5,
            command=self._on_outline_remove_brightness_threshold_percent_changed,
        )
        self.outline_remove_brightness_threshold_spinbox.pack(side=tk.LEFT, padx=(8, 0))
        self.outline_remove_brightness_direction_dark_button = ttk.Radiobutton(
            outline_remove_filter_row,
            text="Dark",
            value=OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK,
            variable=self.outline_remove_brightness_threshold_direction_var,
            command=self._on_outline_remove_brightness_threshold_direction_changed,
        )
        self.outline_remove_brightness_direction_dark_button.pack(side=tk.LEFT, padx=(10, 0))
        self.outline_remove_brightness_direction_bright_button = ttk.Radiobutton(
            outline_remove_filter_row,
            text="Bright",
            value=OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_BRIGHT,
            variable=self.outline_remove_brightness_threshold_direction_var,
            command=self._on_outline_remove_brightness_threshold_direction_changed,
        )
        self.outline_remove_brightness_direction_bright_button.pack(side=tk.LEFT, padx=(6, 0))

        tools_section = self._create_section(sidebar, "Tools")
        tool_grid = ttk.Frame(tools_section)
        tool_grid.pack(anchor=tk.W, pady=(4, 0))
        pencil_cell, self.pencil_button = self._create_tool_button("pencil_button", tool_grid, "icon_pencil.png", self._toggle_pencil_mode, "Pencil")
        eraser_cell, self.eraser_button = self._create_tool_button("eraser_button", tool_grid, "icon_eraser.png", self._toggle_eraser_mode, "Eraser")
        palette_picker_cell, self.palette_picker_button = self._create_tool_button(
            "palette_picker_button",
            tool_grid,
            "icon_eyedrop.png",
            self._toggle_active_color_pick_mode,
            "Colour Picker",
        )
        bucket_cell, self.bucket_button = self._create_tool_button(
            "bucket_button",
            tool_grid,
            "icon_bucket.png",
            self._notify_bucket_unavailable,
            "Bucket (Not Implemented)",
        )
        circle_cell, self.circle_button = self._create_tool_button(
            "circle_button",
            tool_grid,
            "icon_circle.png",
            lambda: self._notify_placeholder_tool("Circle"),
            "Circle (Placeholder)",
        )
        square_cell, self.square_button = self._create_tool_button(
            "square_button",
            tool_grid,
            "icon_square.png",
            lambda: self._notify_placeholder_tool("Square"),
            "Square (Placeholder)",
        )
        add_outline_cell, self.add_outline_button = self._create_tool_button(
            "add_outline_button",
            tool_grid,
            "icon_outline_add.png",
            self._add_outline_from_selection,
            "Add Outline",
        )
        remove_outline_cell, self.remove_outline_button = self._create_tool_button(
            "remove_outline_button",
            tool_grid,
            "icon_outline_remove.png",
            self._remove_outline,
            "Remove Outline",
        )
        undo_cell, self.undo_button = self._create_tool_button(
            "undo_button",
            tool_grid,
            "icon_undo.png",
            self.undo,
            "Undo",
        )
        redo_cell, self.redo_button = self._create_tool_button(
            "redo_button",
            tool_grid,
            "icon_redo.png",
            self.redo,
            "Redo",
        )
        view_original_cell, self.view_original_button = self._create_tool_button(
            "view_original_button",
            tool_grid,
            "icon_view_original.png",
            lambda: self._set_view_from_toolbar("original"),
            "View Original",
        )
        view_processed_cell, self.view_processed_button = self._create_tool_button(
            "view_processed_button",
            tool_grid,
            "icon_view_processed.png",
            lambda: self._set_view_from_toolbar("processed"),
            "View Current",
        )
        transparency_cell, self.active_color_transparent_button = self._create_tool_button(
            "active_color_transparent_button",
            tool_grid,
            "icon_transparency.png",
            self._make_active_color_transparent,
            "Make Active Colour Transparent",
        )
        swap_cell, self.swap_active_colors_button = self._create_tool_button(
            "swap_active_colors_button",
            tool_grid,
            "icon_palette_swap.png",
            self._swap_active_colors,
            "Swap Primary And Secondary Colours",
        )
        for index, cell in enumerate(
            (
                pencil_cell,
                eraser_cell,
                palette_picker_cell,
                bucket_cell,
                circle_cell,
                square_cell,
                add_outline_cell,
                remove_outline_cell,
                undo_cell,
                redo_cell,
                view_original_cell,
                view_processed_cell,
                transparency_cell,
                swap_cell,
            )
        ):
            row_index, column_index = divmod(index, 2)
            cell.grid(
                row=row_index,
                column=column_index,
                sticky="nw",
                padx=0,
                pady=0,
            )
        for column_index in range(2):
            tool_grid.grid_columnconfigure(column_index, minsize=TOOL_BUTTON_WIDTH)
        active_color_controls = ttk.Frame(tools_section, width=TOOL_BUTTON_WIDTH * 2, height=TOOL_BUTTON_HEIGHT)
        active_color_controls.pack(anchor=tk.W, pady=(8, 0))
        active_color_controls.pack_propagate(False)
        self.active_color_preview_label = tk.Label(
            active_color_controls,
            background=APP_BG,
            bd=0,
            highlightthickness=0,
        )
        self.active_color_preview_label.place(x=TOOL_BUTTON_WIDTH, rely=0.5, anchor=tk.CENTER)
        self.active_color_preview_label.bind("<ButtonPress-1>", self._on_active_color_preview_click)
        palette_section.pack_forget()
        palette_section.pack(fill=tk.X, pady=(0, 10))

        self.palette_column = ttk.Frame(body, width=280)
        self.palette_column.pack(side=tk.RIGHT, fill=tk.Y)
        self.palette_column.pack_propagate(False)
        self.palette_column.grid_rowconfigure(0, weight=3)
        self.palette_column.grid_rowconfigure(1, weight=2)
        self.palette_column.grid_columnconfigure(0, weight=1)

        workspace = ttk.Frame(body)
        workspace.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(0, 10))

        self.palette_frame = ttk.LabelFrame(self.palette_column, text="PALETTE")
        self.palette_frame.grid(row=0, column=0, sticky="nsew")
        self.palette_frame.grid_rowconfigure(0, weight=1)
        self.palette_frame.grid_columnconfigure(0, weight=1)
        palette_swatches = ttk.Frame(self.palette_frame)
        palette_swatches.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 8))
        palette_swatches.grid_rowconfigure(0, weight=1)
        palette_swatches.grid_columnconfigure(0, weight=1)
        self.palette_canvas = tk.Canvas(palette_swatches, background=APP_BG, bd=0, highlightthickness=0)
        self.palette_canvas.grid(row=0, column=0, sticky="nsew")
        self.palette_scrollbar = ttk.Scrollbar(palette_swatches, orient=tk.VERTICAL, command=self.palette_canvas.yview)
        self.palette_scrollbar.grid(row=0, column=1, sticky="ns")
        self.palette_canvas.configure(yscrollcommand=self.palette_scrollbar.set)
        self.palette_canvas.bind("<ButtonPress-1>", self._on_palette_canvas_click)
        self.palette_canvas.bind("<B1-Motion>", self._on_palette_canvas_drag)
        self.palette_canvas.bind("<ButtonRelease-1>", self._on_palette_canvas_release)
        self.palette_canvas.bind("<Double-Button-1>", self._on_palette_canvas_double_click)
        self.palette_canvas.bind("<ButtonPress-3>", self._on_palette_canvas_right_click)
        self.palette_canvas.bind("<MouseWheel>", self._on_palette_mouse_wheel, add="+")
        self.palette_dropdown_button = ttk.Menubutton(self.palette_frame, textvariable=self.palette_dropdown_var)
        self.palette_dropdown_button.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        self.palette_dropdown_menu = self._new_menu(self.palette_dropdown_button)
        self.palette_dropdown_button.configure(menu=self.palette_dropdown_menu)
        self.palette_dropdown_button.bind("<ButtonPress-1>", self._show_palette_dropdown_menu, add="+")
        self._populate_palette_dropdown_menu()
        palette_actions = ttk.Frame(self.palette_frame)
        palette_actions.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
        palette_actions_top = ttk.Frame(palette_actions)
        palette_actions_top.pack(fill=tk.X)
        self.add_palette_color_button = ttk.Button(palette_actions_top, text="+", width=3, command=self._toggle_palette_add_pick_mode)
        self.add_palette_color_button.grid(row=0, column=0, sticky="ew")
        self.remove_palette_color_button = ttk.Button(palette_actions_top, text="-", width=3, command=self._remove_selected_palette_colors)
        self.remove_palette_color_button.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.reduce_palette_button = ttk.Button(palette_actions_top, text="Apply", command=self.reduce_palette_current_image)
        self.reduce_palette_button.grid(row=0, column=2, sticky="ew", padx=(4, 0))
        for index in range(3):
            palette_actions_top.grid_columnconfigure(index, weight=1)
        palette_actions_middle = ttk.Frame(palette_actions)
        palette_actions_middle.pack(fill=tk.X, pady=(4, 0))
        self.merge_palette_button = ttk.Button(palette_actions_middle, text="Merge", command=self._merge_selected_palette_colors)
        self.merge_palette_button.grid(row=0, column=0, sticky="ew")
        self.ramp_palette_button = ttk.Button(palette_actions_middle, text="Ramp", command=self._ramp_selected_palette_colors)
        self.ramp_palette_button.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        for index in range(2):
            palette_actions_middle.grid_columnconfigure(index, weight=1)
        palette_actions_bottom = ttk.Frame(palette_actions)
        palette_actions_bottom.pack(fill=tk.X, pady=(4, 0))
        self.select_all_palette_button = ttk.Button(palette_actions_bottom, text="Select All", command=self._select_all_palette_colors)
        self.select_all_palette_button.grid(row=0, column=0, sticky="ew")
        self.clear_palette_selection_button = ttk.Button(palette_actions_bottom, text="Select None", command=self._clear_palette_selection)
        self.clear_palette_selection_button.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.invert_palette_selection_button = ttk.Button(
            palette_actions_bottom,
            text="Inverse",
            command=self._invert_palette_selection,
        )
        self.invert_palette_selection_button.grid(row=0, column=2, sticky="ew", padx=(4, 0))
        for index in range(3):
            palette_actions_bottom.grid_columnconfigure(index, weight=1)

        adjust_section = self._create_section(self.palette_column, "Adjust")
        adjust_section.pack_forget()
        adjust_section.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        reduction_row = ttk.Frame(adjust_section)
        reduction_row.pack(fill=tk.X)
        self.palette_reduction_spinbox = ttk.Spinbox(
            reduction_row,
            from_=1,
            to=256,
            textvariable=self.palette_reduction_colors_var,
            width=8,
            command=self._on_settings_changed,
        )
        self.palette_reduction_spinbox.pack(side=tk.LEFT)
        self.generate_override_palette_button = ttk.Button(
            reduction_row,
            text="Reduce Palette",
            command=self.generate_palette_from_image,
        )
        self.generate_override_palette_button.pack(side=tk.LEFT, padx=(8, 0))
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
        body.bind("<Configure>", self._on_body_configure, add="+")
        self.root.after_idle(lambda: self._update_palette_column_width(max(body.winfo_width(), self.root.winfo_width())))

        content_row = ttk.Frame(workspace)
        content_row.pack(fill=tk.BOTH, expand=True)

        preview_frame = ttk.Frame(content_row)
        preview_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(preview_frame, background=APP_BG, bd=0, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        zoom_controls = ttk.Frame(preview_frame)
        zoom_controls.place(relx=1.0, rely=1.0, x=-12, y=-12, anchor=tk.SE)
        zoom_out_cell, self.zoom_out_button = self._create_tool_button(
            "zoom_out_button",
            zoom_controls,
            "icon_zoom_out.png",
            lambda: self._set_zoom(zoom_out(self.zoom)),
            "Zoom Out",
        )
        zoom_out_cell.pack(side=tk.LEFT)
        zoom_in_cell, self.zoom_in_button = self._create_tool_button(
            "zoom_in_button",
            zoom_controls,
            "icon_zoom_in.png",
            lambda: self._set_zoom(zoom_in(self.zoom)),
            "Zoom In",
        )
        zoom_in_cell.pack(side=tk.LEFT)

        status = ttk.Frame(self.root)
        status.pack(fill=tk.X, padx=10, pady=(0, 8))
        ttk.Label(status, textvariable=self.process_status_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        status_right = ttk.Frame(status)
        status_right.pack(side=tk.RIGHT)
        self.pick_preview_frame = ttk.Frame(status_right)
        self.pick_preview_swatch = tk.Label(
            self.pick_preview_frame,
            width=2,
            height=1,
            bg=APP_SURFACE_BG,
            fg=APP_TEXT,
            relief=tk.SOLID,
            bd=1,
        )
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
        self.brush_width_spinbox.bind("<KeyRelease>", self._on_brush_width_changed, add="+")
        self.brush_width_spinbox.bind("<<Increment>>", self._on_brush_width_changed, add="+")
        self.brush_width_spinbox.bind("<<Decrement>>", self._on_brush_width_changed, add="+")
        self.outline_adaptive_darken_spinbox.bind("<KeyRelease>", self._on_outline_adaptive_darken_changed, add="+")
        self.outline_adaptive_darken_spinbox.bind("<<Increment>>", self._on_outline_adaptive_darken_changed, add="+")
        self.outline_adaptive_darken_spinbox.bind("<<Decrement>>", self._on_outline_adaptive_darken_changed, add="+")
        self.outline_remove_brightness_threshold_spinbox.bind(
            "<KeyRelease>",
            self._on_outline_remove_brightness_threshold_percent_changed,
            add="+",
        )
        self.outline_remove_brightness_threshold_spinbox.bind(
            "<<Increment>>",
            self._on_outline_remove_brightness_threshold_percent_changed,
            add="+",
        )
        self.outline_remove_brightness_threshold_spinbox.bind(
            "<<Decrement>>",
            self._on_outline_remove_brightness_threshold_percent_changed,
            add="+",
        )

        self._update_palette_adjustment_labels()
        self._refresh_outline_control_states()
        self._bind_shortcuts()

    def _create_section(self, parent: ttk.Frame, title: str) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text=title.upper(), padding=SECTION_CONTENT_PADDING)
        frame.pack(fill=tk.X, pady=(0, 10))
        return frame

    @staticmethod
    def _coerce_active_color_label(value: object, default: int = ACTIVE_COLOR_DEFAULT_LABEL) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return max(0, min(0xFFFFFF, parsed))

    @staticmethod
    def _coerce_active_color_slot(value: object) -> str:
        normalized = str(value or "").strip().lower()
        if normalized == ACTIVE_COLOR_SLOT_SECONDARY:
            return ACTIVE_COLOR_SLOT_SECONDARY
        return ACTIVE_COLOR_SLOT_PRIMARY

    @classmethod
    def _coerce_transparent_color_slot(cls, value: object) -> str | None:
        normalized = str(value or "").strip().lower()
        if normalized in {ACTIVE_COLOR_SLOT_PRIMARY, ACTIVE_COLOR_SLOT_SECONDARY}:
            return normalized
        return None

    @classmethod
    def _initial_active_color_state(cls, persisted: dict[str, object]) -> tuple[int, int, str | None, str]:
        primary_label = cls._coerce_active_color_label(persisted.get("primary_color_label"), ACTIVE_COLOR_DEFAULT_LABEL)
        secondary_label = cls._coerce_active_color_label(persisted.get("secondary_color_label"), ACTIVE_COLOR_DEFAULT_LABEL)
        default_transparent = ACTIVE_COLOR_SLOT_SECONDARY if "transparent_color_slot" not in persisted else None
        transparent_slot = cls._coerce_transparent_color_slot(persisted.get("transparent_color_slot", default_transparent))
        active_slot = cls._coerce_active_color_slot(persisted.get("active_color_slot"))
        return (primary_label, secondary_label, transparent_slot, active_slot)

    @staticmethod
    def _other_active_color_slot(slot: str) -> str:
        if slot == ACTIVE_COLOR_SLOT_SECONDARY:
            return ACTIVE_COLOR_SLOT_PRIMARY
        return ACTIVE_COLOR_SLOT_SECONDARY

    def _active_color_slot_value(self) -> str:
        return self._coerce_active_color_slot(getattr(self, "active_color_slot", ACTIVE_COLOR_SLOT_PRIMARY))

    def _transparent_color_slot_value(self) -> str | None:
        return self._coerce_transparent_color_slot(getattr(self, "transparent_color_slot", None))

    def _slot_color_label(self, slot: str) -> int:
        if self._coerce_active_color_slot(slot) == ACTIVE_COLOR_SLOT_SECONDARY:
            return self._coerce_active_color_label(getattr(self, "secondary_color_label", ACTIVE_COLOR_DEFAULT_LABEL))
        return self._coerce_active_color_label(getattr(self, "primary_color_label", ACTIVE_COLOR_DEFAULT_LABEL))

    def _slot_is_transparent(self, slot: str) -> bool:
        return self._transparent_color_slot_value() == self._coerce_active_color_slot(slot)

    def _set_slot_color_label(self, slot: str, label: int) -> None:
        normalized_slot = self._coerce_active_color_slot(slot)
        if normalized_slot == ACTIVE_COLOR_SLOT_SECONDARY:
            self.secondary_color_label = self._coerce_active_color_label(label)
        else:
            self.primary_color_label = self._coerce_active_color_label(label)

    def _set_active_color_slot(self, slot: str, *, persist: bool = True) -> None:
        self.active_color_slot = self._coerce_active_color_slot(slot)
        self._refresh_active_color_preview()
        if persist:
            self._schedule_state_persist_if_ready()

    def _schedule_state_persist_if_ready(self) -> None:
        root = getattr(self, "root", None)
        if root is None or not hasattr(root, "after"):
            return
        self._schedule_state_persist()

    def _assign_palette_color_to_slot(self, slot: str, label: int) -> None:
        normalized_slot = self._coerce_active_color_slot(slot)
        self._set_slot_color_label(normalized_slot, label)
        if self._transparent_color_slot_value() == normalized_slot:
            self.transparent_color_slot = None
        self._refresh_active_color_preview()
        self._schedule_state_persist_if_ready()
        self._refresh_action_states()

    def _swap_active_colors(self) -> None:
        primary_label = self._slot_color_label(ACTIVE_COLOR_SLOT_PRIMARY)
        secondary_label = self._slot_color_label(ACTIVE_COLOR_SLOT_SECONDARY)
        self.primary_color_label = secondary_label
        self.secondary_color_label = primary_label
        transparent_slot = self._transparent_color_slot_value()
        if transparent_slot is not None:
            self.transparent_color_slot = self._other_active_color_slot(transparent_slot)
        self._refresh_active_color_preview()
        self._schedule_state_persist_if_ready()
        self._refresh_action_states()

    def _make_active_color_transparent(self) -> None:
        self.transparent_color_slot = self._active_color_slot_value()
        self._refresh_active_color_preview()
        self._schedule_state_persist_if_ready()
        self._refresh_action_states()

    def _rendered_active_color_slots(self) -> tuple[str, str]:
        front_slot = self._active_color_slot_value()
        return front_slot, self._other_active_color_slot(front_slot)

    def _active_color_preview_template_name(self) -> str:
        front_slot, back_slot = self._rendered_active_color_slots()
        if self._slot_is_transparent(front_slot):
            return ACTIVE_COLOR_PREVIEW_TEMPLATE_FRONT_TRANSPARENT
        if self._slot_is_transparent(back_slot):
            return ACTIVE_COLOR_PREVIEW_TEMPLATE_BACK_TRANSPARENT
        return ACTIVE_COLOR_PREVIEW_TEMPLATE_NONE

    def _active_color_preview_template(self, asset_name: str) -> Image.Image:
        cached = self._active_color_preview_templates.get(asset_name)
        if cached is not None:
            return cached.copy()
        asset_path = self._resource_path(f"assets/{asset_name}")
        if not asset_path.exists():
            asset_path = Path(__file__).resolve().parents[3] / "assets" / asset_name
        with Image.open(asset_path) as image:
            template = image.convert("RGBA")
        self._active_color_preview_templates[asset_name] = template
        return template.copy()

    @staticmethod
    def _label_to_rgba(label: int) -> tuple[int, int, int, int]:
        return ((label >> 16) & 0xFF, (label >> 8) & 0xFF, label & 0xFF, 255)

    def _build_active_color_preview_image(self) -> Image.Image:
        front_slot, back_slot = self._rendered_active_color_slots()
        image = self._active_color_preview_template(self._active_color_preview_template_name())
        front_colour = self._label_to_rgba(self._slot_color_label(front_slot))
        back_colour = self._label_to_rgba(self._slot_color_label(back_slot))
        pixels = image.load()
        for y in range(image.height):
            for x in range(image.width):
                pixel = pixels[x, y]
                if pixel == ACTIVE_COLOR_PREVIEW_PLACEHOLDER_FRONT:
                    pixels[x, y] = front_colour
                elif pixel == ACTIVE_COLOR_PREVIEW_PLACEHOLDER_BACK:
                    pixels[x, y] = back_colour
        return image

    def _refresh_active_color_preview(self) -> None:
        widget = getattr(self, "active_color_preview_label", None)
        if widget is None or not hasattr(widget, "configure"):
            return
        image = ImageTk.PhotoImage(self._build_active_color_preview_image())
        self._active_color_preview_image_ref = image
        widget.configure(image=image)

    def _active_color_preview_hit_slot(self, x: int, y: int) -> str | None:
        front_slot, back_slot = self._rendered_active_color_slots()
        front_x0, front_y0, front_x1, front_y1 = ACTIVE_COLOR_FRONT_BOUNDS
        if front_x0 <= x <= front_x1 and front_y0 <= y <= front_y1:
            return front_slot
        back_x0, back_y0, back_x1, back_y1 = ACTIVE_COLOR_BACK_BOUNDS
        if back_x0 <= x <= back_x1 and back_y0 <= y <= back_y1:
            return back_slot
        return None

    def _on_active_color_preview_click(self, event: tk.Event) -> None:
        slot = self._active_color_preview_hit_slot(event.x, event.y)
        if slot is None:
            return
        self._set_active_color_slot(slot)

    def _tool_button_icon(self, asset_name: str, *, disabled: bool = False) -> ImageTk.PhotoImage:
        cache_key = (asset_name, disabled)
        cached_icon = self._tool_button_icons.get(cache_key)
        if cached_icon is not None:
            return cached_icon
        asset_path = self._resource_path(f"assets/{asset_name}")
        if not asset_path.exists():
            asset_path = Path(__file__).resolve().parents[3] / "assets" / asset_name
        with Image.open(asset_path) as image:
            rgba = image.convert("RGBA")
            if disabled:
                alpha = rgba.getchannel("A").point(lambda value: (value * 3) // 4)
                rgba = rgba.copy()
                rgba.putalpha(alpha)
            fitted = Image.new("RGBA", (TOOL_BUTTON_WIDTH - 2, TOOL_BUTTON_HEIGHT - 2), (0, 0, 0, 0))
            offset_x = (fitted.width - rgba.width) // 2
            offset_y = (fitted.height - rgba.height) // 2
            fitted.paste(rgba, (offset_x, offset_y), rgba)
            cached_icon = ImageTk.PhotoImage(fitted)
        self._tool_button_icons[cache_key] = cached_icon
        return cached_icon

    def _create_tool_button(
        self,
        widget_name: str,
        parent: ttk.Frame,
        asset_name: str,
        command: object,
        tooltip_text: str,
    ) -> tuple[tk.Frame, ttk.Button]:
        cell = tk.Frame(parent, width=TOOL_BUTTON_WIDTH, height=TOOL_BUTTON_HEIGHT, bg=APP_BORDER, bd=0, highlightthickness=0)
        cell.grid_propagate(False)
        self._tool_button_assets[widget_name] = asset_name
        self._tool_button_enabled[widget_name] = True
        button = ttk.Button(
            cell,
            image=self._tool_button_icon(asset_name),
            command=lambda name=widget_name, callback=command: self._invoke_tool_button(name, callback),
            style="ToolButton.TButton",
        )
        button.place(x=1, y=1, width=TOOL_BUTTON_WIDTH - 2, height=TOOL_BUTTON_HEIGHT - 2)
        button.bind(
            "<ButtonPress-1>",
            lambda event, name=widget_name: "break" if not self._tool_button_enabled.get(name, True) else None,
            add="+",
        )
        self._tool_button_frames[widget_name] = cell
        self._tooltips.append(Tooltip(button, tooltip_text))
        return cell, button

    def _invoke_tool_button(self, widget_name: str, command: object) -> None:
        if not self._tool_button_enabled.get(widget_name, True):
            return
        if callable(command):
            command()

    def _set_tool_button_enabled(self, widget_name: str, enabled: bool) -> None:
        if not hasattr(self, "_tool_button_enabled"):
            self._tool_button_enabled = {}
        self._tool_button_enabled[widget_name] = enabled
        widget = getattr(self, widget_name, None)
        if widget is None or not hasattr(widget, "configure"):
            return
        if isinstance(widget, ttk.Button):
            asset_name = getattr(self, "_tool_button_assets", {}).get(widget_name)
            if asset_name is not None:
                widget.configure(image=self._tool_button_icon(asset_name, disabled=not enabled))
            if hasattr(widget, "state"):
                widget.state(("!disabled",))
            return
        widget.configure(state=tk.NORMAL if enabled else tk.DISABLED)

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
            activebackground=APP_HOVER_BG,
            background=APP_BG,
            fg=APP_TEXT,
            highlightthickness=0,
            relief=tk.FLAT,
            sliderrelief=tk.FLAT,
            troughcolor=APP_SURFACE_BG,
        )
        scale.pack(fill=tk.X)
        self.palette_adjustment_controls.append(scale)
        return scale

    def _on_body_configure(self, event: tk.Event) -> None:
        self._update_palette_column_width(event.width)

    def _update_palette_column_width(self, body_width: int) -> None:
        palette_width = max(220, round(body_width * 0.2))
        if hasattr(self, "palette_column"):
            self.palette_column.configure(width=palette_width)

    def _on_palette_adjustment_scale(self, _value: str | None = None) -> None:
        self._update_palette_adjustment_labels()
        self._on_settings_changed()

    def _update_palette_adjustment_labels(self) -> None:
        self.palette_brightness_value_var.set(f"{int(self.palette_brightness_var.get())}%")
        self.palette_contrast_value_var.set(f"{int(self.palette_contrast_var.get())}%")
        self.palette_hue_value_var.set(f"{int(self.palette_hue_var.get())}%")
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
        self.root.bind("<Control-y>", lambda _event: self.redo())
        self.root.bind("<Control-Y>", lambda _event: self.redo())
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
            self.advanced_palette_preview = None
            self._set_pick_mode(None)
            self._clear_palette_undo_state()
            self._clear_palette_redo_state()
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
        self._builtin_palette_menu_entries = {}
        self._builtin_palette_menus = []
        self._register_builtin_palette_menu(menu)
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
                    submenu = self._new_menu(parent_menu)
                    self._register_builtin_palette_menu(submenu)
                    parent_menu.add_cascade(label=folder_label, menu=submenu)
                    submenus[parent_path] = submenu
                parent_menu = submenus[parent_path]
            parent_menu.add_command(label=entry.label, command=lambda value=entry: self._select_builtin_palette(value))
            index = parent_menu.index(tk.END)
            if isinstance(index, int):
                self._builtin_palette_menu_entries[(parent_menu, index)] = entry

    def _populate_palette_dropdown_menu(self) -> None:
        menu = getattr(self, "palette_dropdown_menu", None)
        if menu is None:
            return
        menu.delete(0, tk.END)
        self._register_builtin_palette_menu(menu)
        if not self.builtin_palette_entries:
            menu.add_command(label="(none)", state=tk.DISABLED)
            if hasattr(self, "palette_dropdown_button"):
                self.palette_dropdown_button.configure(state=tk.DISABLED)
            self._update_palette_dropdown_label()
            return
        if hasattr(self, "palette_dropdown_button"):
            self.palette_dropdown_button.configure(state=tk.NORMAL)
        for entry in self.builtin_palette_entries:
            menu.add_command(label=entry.source_label, command=lambda value=entry: self._select_builtin_palette(value))
            index = menu.index(tk.END)
            if isinstance(index, int):
                self._builtin_palette_menu_entries[(menu, index)] = entry
        self._update_palette_dropdown_label()

    def _register_builtin_palette_menu(self, menu: tk.Menu) -> None:
        if menu in self._builtin_palette_menus:
            return
        self._builtin_palette_menus.append(menu)
        menu.bind("<<MenuSelect>>", lambda _event, target=menu: self._on_builtin_palette_menu_select(target), add="+")
        menu.bind("<Unmap>", lambda _event: self.root.after_idle(self._clear_builtin_palette_preview_if_menu_closed), add="+")

    def _on_builtin_palette_menu_select(self, menu: tk.Menu) -> None:
        try:
            index = menu.index(tk.ACTIVE)
        except tk.TclError:
            index = None
        if not isinstance(index, int):
            self._clear_builtin_palette_preview()
            return
        preview_entry = self._builtin_palette_menu_entries.get((menu, index))
        if preview_entry is None:
            self._clear_builtin_palette_preview()
            return
        if getattr(self, "_builtin_palette_preview_entry", None) == preview_entry:
            return
        self._builtin_palette_preview_entry = preview_entry
        self._update_palette_dropdown_label()
        self._update_palette_strip()

    def _clear_builtin_palette_preview(self) -> None:
        if getattr(self, "_builtin_palette_preview_entry", None) is None:
            return
        self._builtin_palette_preview_entry = None
        self._update_palette_dropdown_label()
        self._update_palette_strip()

    def _clear_builtin_palette_preview_if_menu_closed(self) -> None:
        if any(menu.winfo_ismapped() for menu in getattr(self, "_builtin_palette_menus", [])):
            return
        self._clear_builtin_palette_preview()

    def _update_palette_dropdown_label(self) -> None:
        variable = getattr(self, "palette_dropdown_var", None)
        if variable is None:
            return
        preview_entry = getattr(self, "_builtin_palette_preview_entry", None)
        if preview_entry is not None:
            variable.set(preview_entry.source_label)
            return
        active_path = getattr(self, "active_palette_path", None)
        if active_path:
            entry = self._builtin_palette_by_path.get(str(active_path))
            if entry is not None:
                variable.set(entry.source_label)
                return
        variable.set("Built-in palettes")

    def _show_palette_dropdown_menu(self, _event: tk.Event | None = None) -> str:
        button = getattr(self, "palette_dropdown_button", None)
        menu = getattr(self, "palette_dropdown_menu", None)
        if button is None or menu is None:
            return "break"
        try:
            x_position = max(0, button.winfo_rootx() - PALETTE_DROPDOWN_POST_X_OFFSET)
            y_position = button.winfo_rooty() + button.winfo_height()
            menu.tk_popup(x_position, y_position)
        finally:
            menu.grab_release()
        return "break"

    def _on_palette_mouse_wheel(self, event: tk.Event) -> str:
        canvas = getattr(self, "palette_canvas", None)
        if canvas is None:
            return "break"
        delta = getattr(event, "delta", 0)
        if delta == 0:
            return "break"
        canvas.yview_scroll(-1 if delta > 0 else 1, "units")
        return "break"

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
        self._update_palette_dropdown_label()
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
            self._clear_palette_redo_state()
        self._set_active_palette(palette, source, path_value)
        if mark_stale:
            self._mark_output_stale(message)
        elif message:
            self.process_status_var.set(message)
        self._update_palette_strip()
        self._schedule_state_persist()
        self._refresh_action_states()

    def _select_builtin_palette(self, entry: PaletteCatalogEntry) -> None:
        self._clear_builtin_palette_preview()
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
        if mode == PALETTE_SELECT_SIMILARITY_NEAR_DUPLICATES and not indices:
            self.process_status_var.set(f"No near-duplicate palette colours found at {threshold}%.")
            return
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

    @staticmethod
    def _coerce_canvas_tool_mode(value: object) -> str | None:
        normalized = str(value or "").strip().lower()
        if normalized in {
            CANVAS_TOOL_MODE_PALETTE_PICK,
            CANVAS_TOOL_MODE_ACTIVE_COLOR_PICK,
            CANVAS_TOOL_MODE_TRANSPARENCY_PICK,
            CANVAS_TOOL_MODE_PENCIL,
            CANVAS_TOOL_MODE_ERASER,
        }:
            return normalized
        return None

    def _canvas_tool_mode_value(self) -> str | None:
        mode = self._coerce_canvas_tool_mode(getattr(self, "canvas_tool_mode", None))
        if mode is not None:
            return mode
        if getattr(self, "palette_add_pick_mode", False):
            return CANVAS_TOOL_MODE_PALETTE_PICK
        if getattr(self, "transparency_pick_mode", False):
            return CANVAS_TOOL_MODE_TRANSPARENCY_PICK
        return None

    def _set_canvas_tool_mode(self, mode: str | None) -> None:
        normalized = self._coerce_canvas_tool_mode(mode)
        self.canvas_tool_mode = normalized
        self.palette_add_pick_mode = normalized == CANVAS_TOOL_MODE_PALETTE_PICK
        self.transparency_pick_mode = normalized == CANVAS_TOOL_MODE_TRANSPARENCY_PICK
        self._reset_brush_stroke_state()
        self._set_pick_preview(None)
        if normalized == CANVAS_TOOL_MODE_PALETTE_PICK:
            self._set_view("original")
            self.process_status_var.set("Click the original preview to add a colour to the current palette.")
        elif normalized == CANVAS_TOOL_MODE_ACTIVE_COLOR_PICK:
            self._set_view("processed")
            self.process_status_var.set("Click the processed preview to set the active colour.")
        elif normalized == CANVAS_TOOL_MODE_TRANSPARENCY_PICK:
            self._set_view("processed")
            self.process_status_var.set("Click the processed preview to remove a connected region.")
        elif normalized == CANVAS_TOOL_MODE_PENCIL:
            self._set_view("processed")
            self.process_status_var.set("Click and drag on the processed preview to draw with the primary colour.")
        elif normalized == CANVAS_TOOL_MODE_ERASER:
            self._set_view("processed")
            self.process_status_var.set("Click and drag on the processed preview to erase pixels to transparency.")
        canvas = getattr(self, "canvas", None)
        if canvas is not None and hasattr(canvas, "configure") and not getattr(self, "dragging", False):
            canvas.configure(cursor=self._cursor_for_pointer())
        self._refresh_tool_button_styles()

    def _set_pick_mode(self, mode: str | None) -> None:
        translated = {
            "palette": CANVAS_TOOL_MODE_PALETTE_PICK,
            "transparency": CANVAS_TOOL_MODE_TRANSPARENCY_PICK,
            None: None,
        }.get(mode, None)
        self._set_canvas_tool_mode(translated)

    def _brush_width(self) -> int:
        variable = getattr(self, "brush_width_var", None)
        if variable is None:
            return BRUSH_WIDTH_DEFAULT
        getter = getattr(variable, "get", None)
        try:
            value = getter() if callable(getter) else variable
        except Exception:
            value = BRUSH_WIDTH_DEFAULT
        return self._coerce_brush_width(value)

    def _brush_shape(self) -> str:
        variable = getattr(self, "brush_shape_var", None)
        if variable is None:
            return BRUSH_SHAPE_SQUARE
        getter = getattr(variable, "get", None)
        try:
            value = getter() if callable(getter) else variable
        except Exception:
            value = BRUSH_SHAPE_SQUARE
        return self._coerce_brush_shape(value)

    def _reset_brush_stroke_state(self) -> None:
        self._brush_stroke_active = False
        self._brush_stroke_last_point = None
        self._brush_stroke_changed_pixels = 0
        self._brush_stroke_tool_mode = None

    @staticmethod
    def _is_brush_tool_mode(mode: str | None) -> bool:
        return mode in {CANVAS_TOOL_MODE_PENCIL, CANVAS_TOOL_MODE_ERASER}

    def _brush_tool_mode_active(self) -> bool:
        return self._is_brush_tool_mode(self._canvas_tool_mode_value())

    @staticmethod
    def _brush_tool_display_name(mode: str | None) -> str:
        if mode == CANVAS_TOOL_MODE_ERASER:
            return "Eraser"
        return "Pencil"

    def _selected_palette_brush_label(self) -> int | None:
        if self._slot_is_transparent(ACTIVE_COLOR_SLOT_PRIMARY):
            return None
        return self._slot_color_label(ACTIVE_COLOR_SLOT_PRIMARY)

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
        self._set_canvas_tool_mode(CANVAS_TOOL_MODE_PALETTE_PICK)
        self._refresh_action_states()

    def _start_active_color_pick_mode(self) -> None:
        if self._current_output_result() is None or self.image_state == "processing":
            self.process_status_var.set("Create a processed image before picking a colour.")
            return
        self._set_canvas_tool_mode(CANVAS_TOOL_MODE_ACTIVE_COLOR_PICK)
        self._refresh_action_states()

    def _toggle_palette_add_pick_mode(self) -> None:
        if self._canvas_tool_mode_value() == CANVAS_TOOL_MODE_PALETTE_PICK:
            self._set_canvas_tool_mode(None)
            self.process_status_var.set("Palette colour pick cancelled.")
        else:
            self._start_palette_add_pick_mode()
            return
        self._refresh_action_states()

    def _toggle_active_color_pick_mode(self) -> None:
        if self._canvas_tool_mode_value() == CANVAS_TOOL_MODE_ACTIVE_COLOR_PICK:
            self._set_canvas_tool_mode(None)
            self.process_status_var.set("Active colour pick cancelled.")
        else:
            self._start_active_color_pick_mode()
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

    def _selected_palette_indices(self, palette: list[int]) -> list[int]:
        return sorted(index for index in self._palette_selection_indices if 0 <= index < len(palette))

    def _toggle_transparency_pick_mode(self) -> None:
        if self._current_output_image() is None or self.image_state == "processing":
            self.process_status_var.set("Create a processed image before making colours transparent.")
            return
        if self._canvas_tool_mode_value() == CANVAS_TOOL_MODE_TRANSPARENCY_PICK:
            self._set_canvas_tool_mode(None)
            self.process_status_var.set("Transparency pick cancelled.")
        else:
            self._set_canvas_tool_mode(CANVAS_TOOL_MODE_TRANSPARENCY_PICK)
        self._refresh_action_states()

    def _start_pencil_mode(self) -> None:
        if self._current_output_result() is None or self.image_state == "processing":
            self.process_status_var.set("Create a processed image before drawing.")
            return
        if self._selected_palette_brush_label() is None:
            self.process_status_var.set("Set a non-transparent primary colour to draw.")
            return
        self._set_canvas_tool_mode(CANVAS_TOOL_MODE_PENCIL)
        self._refresh_action_states()

    def _toggle_pencil_mode(self) -> None:
        if self._canvas_tool_mode_value() == CANVAS_TOOL_MODE_PENCIL:
            self._set_canvas_tool_mode(None)
            self.process_status_var.set("Pencil cancelled.")
        else:
            self._start_pencil_mode()
            return
        self._refresh_action_states()

    def _toggle_eraser_mode(self) -> None:
        if self._current_output_result() is None or self.image_state == "processing":
            self.process_status_var.set("Create a processed image before erasing.")
            return
        if self._canvas_tool_mode_value() == CANVAS_TOOL_MODE_ERASER:
            self._set_canvas_tool_mode(None)
            self.process_status_var.set("Eraser cancelled.")
        else:
            self._set_canvas_tool_mode(CANVAS_TOOL_MODE_ERASER)
        self._refresh_action_states()

    def _notify_bucket_unavailable(self) -> None:
        self.process_status_var.set("Bucket fill is not implemented yet.")

    def _notify_placeholder_tool(self, tool_name: str) -> None:
        self.process_status_var.set(f"{tool_name} tool is not implemented yet.")

    def _merge_selected_palette_colors(self) -> None:
        palette = self._editable_palette_labels()
        if not palette:
            self.process_status_var.set("There is no current palette to edit.")
            return
        selected = self._selected_palette_indices(palette)
        if len(selected) < 2:
            self.process_status_var.set("Select 2 or more palette colours to merge.")
            return
        merged_label = merge_palette_labels([palette[index] for index in selected], workspace=self.workspace)
        selected_set = set(selected)
        first_selected = selected[0]
        merged_palette: list[int] = []
        for index, label in enumerate(palette):
            if index == first_selected:
                merged_palette.append(merged_label)
            if index not in selected_set:
                merged_palette.append(label)
        self._apply_palette_edit(
            merged_palette,
            f"Merged {len(selected)} palette colour{'s' if len(selected) != 1 else ''} into #{merged_label:06X}. Click Apply Palette to update the preview.",
        )

    def _ramp_selected_palette_colors(self) -> None:
        palette = self._editable_palette_labels()
        if not palette:
            self.process_status_var.set("There is no current palette to edit.")
            return
        selected = self._selected_palette_indices(palette)
        if not selected:
            self.process_status_var.set("Select one or more palette colours to ramp.")
            return
        try:
            settings = self._read_settings_from_controls(strict=False)
        except Exception:
            settings = getattr(getattr(self, "session", None), "current", PreviewSettings())
        ramp_labels = generate_ramp_palette_labels(
            [palette[index] for index in selected],
            generated_shades=settings.generated_shades,
            contrast_bias=settings.contrast_bias,
            workspace=self.workspace,
        )
        if not ramp_labels:
            self.process_status_var.set("No ramp colours were generated from the selection.")
            return
        updated_palette = palette + ramp_labels
        self._apply_palette_edit(
            updated_palette,
            f"Appended {len(ramp_labels)} ramp colour{'s' if len(ramp_labels) != 1 else ''} from {len(selected)} selected palette colour{'s' if len(selected) != 1 else ''}. Click Apply Palette to update the preview.",
        )

    def _on_palette_settings_changed(self, _event: tk.Event | None = None) -> None:
        self._on_settings_changed(_event)

    def _displayed_structured_palette(self) -> StructuredPalette | None:
        return self._current_adjusted_structured_palette()

    def _active_pick_view(self) -> str | None:
        mode = self._canvas_tool_mode_value()
        if mode == CANVAS_TOOL_MODE_PALETTE_PICK:
            return "original"
        if mode in {CANVAS_TOOL_MODE_ACTIVE_COLOR_PICK, CANVAS_TOOL_MODE_TRANSPARENCY_PICK}:
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

    def _apply_brush_stroke(self, image_x: int, image_y: int) -> int:
        current = self._current_output_result()
        if current is None:
            return 0
        mode = getattr(self, "_brush_stroke_tool_mode", None) or self._canvas_tool_mode_value()
        width = self._brush_width()
        shape = self._brush_shape()
        if mode == CANVAS_TOOL_MODE_PENCIL:
            label = self._selected_palette_brush_label()
            if label is None:
                return 0
            updated, changed = apply_pencil_operation(current, image_x, image_y, label, width=width, shape=shape)
        elif mode == CANVAS_TOOL_MODE_ERASER:
            updated, changed = apply_eraser_operation(current, image_x, image_y, width=width, shape=shape)
        else:
            return 0
        if changed <= 0:
            return 0
        self.transparent_colors = set()
        self._set_current_output_result(updated)
        self._refresh_output_display_images()
        self.redraw_canvas()
        return changed

    def _refresh_current_output_display_image(self) -> None:
        current = self._current_output_result()
        updated_image = self._build_output_display_image(current)
        if getattr(self, "palette_result", None) is not None:
            self.palette_display_image = updated_image
        else:
            self.downsample_display_image = updated_image

    def _apply_brush_segment(self, points: list[tuple[int, int]]) -> int:
        current = self._current_output_result()
        if current is None or not points:
            return 0
        mode = getattr(self, "_brush_stroke_tool_mode", None) or self._canvas_tool_mode_value()
        width = self._brush_width()
        shape = self._brush_shape()
        if mode == CANVAS_TOOL_MODE_PENCIL:
            label = self._selected_palette_brush_label()
            if label is None:
                return 0
            updated, changed = apply_pencil_operations(current, points, label=label, width=width, shape=shape)
        elif mode == CANVAS_TOOL_MODE_ERASER:
            updated, changed = apply_eraser_operations(current, points, width=width, shape=shape)
        else:
            return 0
        if changed <= 0:
            return 0
        self.transparent_colors = set()
        self._set_current_output_result(updated)
        self._refresh_current_output_display_image()
        self.redraw_canvas()
        return changed

    @staticmethod
    def _interpolate_brush_points(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
        x0, y0 = start
        x1, y1 = end
        delta_x = abs(x1 - x0)
        delta_y = abs(y1 - y0)
        step_x = 1 if x0 < x1 else -1
        step_y = 1 if y0 < y1 else -1
        error = delta_x - delta_y
        points: list[tuple[int, int]] = []
        while True:
            points.append((x0, y0))
            if x0 == x1 and y0 == y1:
                return points
            doubled_error = error * 2
            if doubled_error > -delta_y:
                error -= delta_y
                x0 += step_x
            if doubled_error < delta_x:
                error += delta_x
                y0 += step_y

    def _record_brush_stroke(self, image_x: int, image_y: int) -> None:
        last_point = getattr(self, "_brush_stroke_last_point", None)
        points = [(image_x, image_y)] if last_point is None else self._interpolate_brush_points(last_point, (image_x, image_y))
        changed = self._apply_brush_segment(points)
        if isinstance(changed, int) and changed > 0:
            self._brush_stroke_changed_pixels += changed
        self._brush_stroke_last_point = (image_x, image_y)

    def _selected_palette_outline_label(self) -> int | None:
        displayed = getattr(self, "_displayed_palette", [])
        selected = sorted(index for index in getattr(self, "_palette_selection_indices", set()) if 0 <= index < len(displayed))
        if len(selected) != 1:
            return None
        return displayed[selected[0]]

    def _outline_pixel_perfect_enabled(self) -> bool:
        variable = getattr(self, "outline_pixel_perfect_var", None)
        if variable is None:
            return True
        getter = getattr(variable, "get", None)
        if callable(getter):
            return bool(getter())
        return bool(variable)

    def _outline_colour_mode(self) -> str:
        variable = getattr(self, "outline_colour_mode_var", None)
        if variable is None:
            return OUTLINE_COLOUR_MODE_PALETTE
        getter = getattr(variable, "get", None)
        try:
            value = getter() if callable(getter) else variable
        except Exception:
            value = OUTLINE_COLOUR_MODE_PALETTE
        return self._coerce_outline_colour_mode(value)

    def _outline_adaptive_enabled(self) -> bool:
        return self._outline_colour_mode() == OUTLINE_COLOUR_MODE_ADAPTIVE

    def _outline_adaptive_darken_percent(self) -> int:
        variable = getattr(self, "outline_adaptive_darken_percent_var", None)
        if variable is None:
            return OUTLINE_ADAPTIVE_DARKEN_DEFAULT
        getter = getattr(variable, "get", None)
        try:
            value = getter() if callable(getter) else variable
        except Exception:
            value = OUTLINE_ADAPTIVE_DARKEN_DEFAULT
        return self._coerce_outline_adaptive_darken_percent(value)

    def _outline_add_generated_colours_enabled(self) -> bool:
        variable = getattr(self, "outline_add_generated_colours_var", None)
        if variable is None:
            return False
        getter = getattr(variable, "get", None)
        if callable(getter):
            try:
                return bool(getter())
            except Exception:
                return False
        return bool(variable)

    def _outline_remove_brightness_threshold_enabled(self) -> bool:
        variable = getattr(self, "outline_remove_brightness_threshold_enabled_var", None)
        if variable is None:
            return False
        getter = getattr(variable, "get", None)
        if callable(getter):
            try:
                return bool(getter())
            except Exception:
                return False
        return bool(variable)

    def _outline_remove_brightness_threshold_percent(self) -> int:
        variable = getattr(self, "outline_remove_brightness_threshold_percent_var", None)
        if variable is None:
            return OUTLINE_REMOVE_BRIGHTNESS_THRESHOLD_DEFAULT
        getter = getattr(variable, "get", None)
        try:
            value = getter() if callable(getter) else variable
        except Exception:
            value = OUTLINE_REMOVE_BRIGHTNESS_THRESHOLD_DEFAULT
        return self._coerce_outline_remove_brightness_threshold_percent(value)

    def _outline_remove_brightness_threshold_direction(self) -> str:
        variable = getattr(self, "outline_remove_brightness_threshold_direction_var", None)
        if variable is None:
            return OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK
        getter = getattr(variable, "get", None)
        try:
            value = getter() if callable(getter) else variable
        except Exception:
            value = OUTLINE_REMOVE_BRIGHTNESS_DIRECTION_DARK
        return self._coerce_outline_remove_brightness_direction(value)

    def _outline_remove_brightness_threshold_description(self) -> str:
        direction = self._outline_remove_brightness_threshold_direction()
        threshold = self._outline_remove_brightness_threshold_percent()
        return f"{direction} brightness threshold at {threshold}%"

    def _refresh_brush_control_states(self) -> None:
        busy = getattr(self, "image_state", "") == "processing"
        has_output = self._current_output_result() is not None if hasattr(self, "_current_output_result") else False
        can_erase = has_output and not busy
        can_draw = can_erase and (self._selected_palette_brush_label() is not None if hasattr(self, "_selected_palette_brush_label") else False)
        self._set_tool_button_enabled("pencil_button", can_draw)
        self._set_tool_button_enabled("eraser_button", can_erase)
        spinbox = getattr(self, "brush_width_spinbox", None)
        if spinbox is not None and hasattr(spinbox, "configure"):
            spinbox.configure(state="normal" if can_erase else "disabled")
        dropdown = getattr(self, "brush_shape_dropdown_button", None)
        if dropdown is not None and hasattr(dropdown, "configure"):
            dropdown.configure(state=tk.NORMAL if can_erase else tk.DISABLED)

    def _refresh_outline_control_states(self) -> None:
        adaptive = self._outline_adaptive_enabled()
        remove_threshold = self._outline_remove_brightness_threshold_enabled()
        busy = getattr(self, "image_state", "") == "processing"
        has_output = self._current_output_result() is not None if hasattr(self, "_current_output_result") else False
        mode_state = tk.NORMAL if has_output and not busy else tk.DISABLED
        adaptive_state = "normal" if adaptive and has_output and not busy else "disabled"
        remove_threshold_toggle_state = tk.NORMAL if has_output and not busy else tk.DISABLED
        remove_threshold_state = "normal" if remove_threshold and has_output and not busy else "disabled"
        for widget_name in ("outline_palette_mode_button", "outline_adaptive_mode_button"):
            widget = getattr(self, widget_name, None)
            if widget is not None and hasattr(widget, "configure"):
                widget.configure(state=mode_state)
        toggle = getattr(self, "outline_add_generated_colours_toggle", None)
        if toggle is not None and hasattr(toggle, "configure"):
            toggle.configure(state=tk.NORMAL if adaptive and has_output and not busy else tk.DISABLED)
        spinbox = getattr(self, "outline_adaptive_darken_spinbox", None)
        if spinbox is not None and hasattr(spinbox, "configure"):
            spinbox.configure(state=adaptive_state)
        remove_toggle = getattr(self, "outline_remove_brightness_threshold_toggle", None)
        if remove_toggle is not None and hasattr(remove_toggle, "configure"):
            remove_toggle.configure(state=remove_threshold_toggle_state)
        remove_spinbox = getattr(self, "outline_remove_brightness_threshold_spinbox", None)
        if remove_spinbox is not None and hasattr(remove_spinbox, "configure"):
            remove_spinbox.configure(state=remove_threshold_state)
        for widget_name in (
            "outline_remove_brightness_direction_dark_button",
            "outline_remove_brightness_direction_bright_button",
        ):
            widget = getattr(self, widget_name, None)
            if widget is not None and hasattr(widget, "configure"):
                widget.configure(state=remove_threshold_state)

    def _on_brush_width_changed(self, _event: tk.Event | None = None) -> None:
        width = self._brush_width()
        variable = getattr(self, "brush_width_var", None)
        getter = getattr(variable, "get", None)
        setter = getattr(variable, "set", None)
        if variable is not None and callable(getter) and callable(setter) and getter() != width:
            setter(width)
        self._schedule_state_persist()

    def _select_brush_shape(self, value: str) -> None:
        variable = getattr(self, "brush_shape_var", None)
        setter = getattr(variable, "set", None)
        if variable is not None and callable(setter):
            setter(value)
        self._on_brush_shape_changed()

    def _on_brush_shape_changed(self) -> None:
        shape = self._brush_shape()
        variable = getattr(self, "brush_shape_var", None)
        getter = getattr(variable, "get", None)
        setter = getattr(variable, "set", None)
        display_value = shape.title()
        if variable is not None and callable(getter) and callable(setter) and getter() != display_value:
            setter(display_value)
        self._schedule_state_persist()

    def _set_current_output_result(self, result: ProcessResult) -> None:
        if getattr(self, "palette_result", None) is not None:
            self.palette_result = result
        else:
            self.downsample_result = result

    def _add_outline_from_selection(self) -> None:
        current = self._current_output_result()
        if current is None or self.image_state == "processing":
            return
        adaptive = self._outline_adaptive_enabled()
        outline_label: int | None = 0
        if not adaptive:
            outline_label = self._selected_palette_outline_label()
            if outline_label is None:
                self.process_status_var.set("Select exactly one palette colour to add an outline.")
                return
        pixel_perfect = self._outline_pixel_perfect_enabled()
        darken_percent = self._outline_adaptive_darken_percent()
        updated, changed, generated_labels = add_exterior_outline(
            current,
            outline_label if outline_label is not None else 0,
            transparent_labels=getattr(self, "transparent_colors", set()),
            pixel_perfect=pixel_perfect,
            adaptive=adaptive,
            adaptive_darken_percent=darken_percent,
            workspace=getattr(self, "workspace", None),
        )
        if changed <= 0:
            if adaptive:
                if pixel_perfect:
                    self.process_status_var.set("No adaptive pixel-perfect exterior outline pixels were available to add.")
                else:
                    self.process_status_var.set("No adaptive exterior outline pixels were available to add.")
            elif pixel_perfect:
                self.process_status_var.set("No pixel-perfect exterior outline pixels were available to add.")
            else:
                self.process_status_var.set("No exterior outline pixels were available to add.")
            return
        self._capture_palette_undo_state()
        appended_count = 0
        self.transparent_colors = set()
        self._set_current_output_result(updated)
        if adaptive and self._outline_add_generated_colours_enabled():
            editable_palette = self._editable_palette_labels()
            if editable_palette:
                existing = set(editable_palette)
                appended_labels = [label for label in generated_labels if label not in existing]
                if appended_labels:
                    previous_selection = set(getattr(self, "_palette_selection_indices", set()))
                    previous_anchor = getattr(self, "_palette_selection_anchor_index", None)
                    self._set_active_palette(editable_palette + appended_labels, "Edited Palette", None)
                    self._palette_selection_indices = {
                        index for index in previous_selection if 0 <= index < len(getattr(self, "active_palette", []) or [])
                    }
                    anchor = previous_anchor if isinstance(previous_anchor, int) else None
                    self._palette_selection_anchor_index = (
                        anchor if anchor is not None and 0 <= anchor < len(getattr(self, "active_palette", []) or []) else None
                    )
                    appended_count = len(appended_labels)
        self._refresh_output_display_images()
        self._set_view("processed")
        if adaptive:
            palette_clause = (
                f" Added {appended_count} generated palette colour{'s' if appended_count != 1 else ''} to the current palette."
                if appended_count
                else ""
            )
            if pixel_perfect:
                self.process_status_var.set(
                    f"Added adaptive pixel-perfect outline to {changed} pixel{'s' if changed != 1 else ''} at {darken_percent}% darkening."
                    f"{palette_clause} Press Undo to restore it."
                )
            else:
                self.process_status_var.set(
                    f"Added adaptive outline to {changed} pixel{'s' if changed != 1 else ''} at {darken_percent}% darkening."
                    f"{palette_clause} Press Undo to restore it."
                )
        elif pixel_perfect:
            self.process_status_var.set(
                f"Added pixel-perfect outline to {changed} pixel{'s' if changed != 1 else ''} with #{outline_label:06X}. Press Undo to restore it."
            )
        else:
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
        pixel_perfect = self._outline_pixel_perfect_enabled()
        brightness_threshold_enabled = self._outline_remove_brightness_threshold_enabled()
        brightness_threshold_percent = self._outline_remove_brightness_threshold_percent()
        brightness_threshold_direction = self._outline_remove_brightness_threshold_direction()
        updated, changed = remove_exterior_outline(
            current,
            transparent_labels=getattr(self, "transparent_colors", set()),
            pixel_perfect=pixel_perfect,
            brightness_threshold_enabled=brightness_threshold_enabled,
            brightness_threshold_percent=brightness_threshold_percent,
            brightness_threshold_direction=brightness_threshold_direction,
            workspace=getattr(self, "workspace", None),
        )
        if changed <= 0:
            if brightness_threshold_enabled:
                if pixel_perfect:
                    self.process_status_var.set(
                        f"No pixel-perfect edge pixels met the {self._outline_remove_brightness_threshold_description()}."
                    )
                else:
                    self.process_status_var.set(
                        f"No exterior outline pixels met the {self._outline_remove_brightness_threshold_description()}."
                    )
            elif pixel_perfect:
                self.process_status_var.set("No pixel-perfect edge pixels were found to remove.")
            else:
                self.process_status_var.set("No exterior outline pixels were found to remove.")
            return
        self._capture_palette_undo_state()
        self.transparent_colors = set()
        self._set_current_output_result(updated)
        self._refresh_output_display_images()
        self._set_view("processed")
        if brightness_threshold_enabled:
            if pixel_perfect:
                self.process_status_var.set(
                    f"Removed {changed} pixel-perfect edge pixel{'s' if changed != 1 else ''} using the "
                    f"{self._outline_remove_brightness_threshold_description()}. Press Undo to restore it."
                )
            else:
                self.process_status_var.set(
                    f"Removed {changed} outline pixel{'s' if changed != 1 else ''} using the "
                    f"{self._outline_remove_brightness_threshold_description()}. Press Undo to restore it."
                )
        elif pixel_perfect:
            self.process_status_var.set(
                f"Removed {changed} pixel-perfect edge pixel{'s' if changed != 1 else ''}. Press Undo to restore it."
            )
        else:
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
        history = getattr(getattr(self, "session", None), "history", None)
        can_undo = getattr(history, "can_undo", None)
        if not callable(can_undo) or not can_undo():
            self.process_status_var.set("Nothing to undo.")
            return
        previous = self.session.current
        restored = self.session.undo()
        self._sync_controls_from_settings(restored)
        self._handle_settings_transition(previous, restored, "Settings restored from undo.")

    def redo(self) -> None:
        if self._redo_palette_application():
            return
        history = getattr(getattr(self, "session", None), "history", None)
        can_redo = getattr(history, "can_redo", None)
        if not callable(can_redo) or not can_redo():
            self.process_status_var.set("Nothing to redo.")
            return
        previous = self.session.current
        restored = self.session.redo()
        self._sync_controls_from_settings(restored)
        self._handle_settings_transition(previous, restored, "Settings restored from redo.")

    def _capture_palette_state(self) -> PaletteUndoState:
        return PaletteUndoState(
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

    def _capture_palette_undo_state(self) -> None:
        self._palette_undo_state = self._capture_palette_state()
        self._clear_palette_redo_state()

    def _clear_palette_undo_state(self) -> None:
        self._palette_undo_state = None

    def _clear_palette_redo_state(self) -> None:
        self._palette_redo_state = None

    def _restore_palette_state(self, state: PaletteUndoState) -> None:
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

    def _undo_palette_application(self) -> bool:
        if self._palette_undo_state is None:
            return False
        self._palette_redo_state = self._capture_palette_state()
        state = self._palette_undo_state
        self._restore_palette_state(state)
        self._clear_palette_undo_state()
        self.process_status_var.set("Reverted the last image change.")
        self._update_palette_strip()
        self._update_image_info()
        self.redraw_canvas()
        self._schedule_state_persist()
        self._refresh_action_states()
        return True

    def _redo_palette_application(self) -> bool:
        if self._palette_redo_state is None:
            return False
        self._palette_undo_state = self._capture_palette_state()
        state = self._palette_redo_state
        self._restore_palette_state(state)
        self._clear_palette_redo_state()
        self.process_status_var.set("Reapplied the last undone image change.")
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
        self._clear_palette_redo_state()
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
        self._clear_palette_redo_state()
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
        self._clear_palette_redo_state()
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
            self.canvas.create_text(
                max(self.canvas.winfo_width() // 2, 200),
                max(self.canvas.winfo_height() // 2, 150),
                text=text,
                fill=APP_TEXT,
                font=self.ui_font,
            )
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
            return Image.new("RGBA", (1, 1), (34, 35, 35, 255))
        if not self.checkerboard_var.get():
            return Image.new("RGBA", size, (34, 35, 35, 255))
        background = Image.new("RGBA", size, (34, 35, 35, 255))
        draw = ImageDraw.Draw(background)
        for y in range(0, height, 8):
            for x in range(0, width, 8):
                if ((x // 8) + (y // 8)) % 2 == 0:
                    draw.rectangle((x, y, x + 7, y + 7), fill=(48, 52, 52, 255))
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
        mode = self._canvas_tool_mode_value()
        if getattr(self, "original_display_image", None) is None and mode is None:
            self.open_image()
            return
        if mode == CANVAS_TOOL_MODE_ACTIVE_COLOR_PICK:
            sampled = self._sample_label_from_preview(event.x, event.y, view="processed")
            if sampled is not None:
                self._assign_palette_color_to_slot(self._active_color_slot_value(), sampled)
                self._set_canvas_tool_mode(None)
                self._refresh_action_states()
            return
        if mode == CANVAS_TOOL_MODE_PALETTE_PICK:
            sampled = self._sample_label_from_preview(event.x, event.y, view="original")
            if sampled is not None:
                self._add_colour_to_current_palette(sampled)
                self._set_canvas_tool_mode(None)
                self._refresh_action_states()
            return
        if mode == CANVAS_TOOL_MODE_TRANSPARENCY_PICK:
            sampled = self._sample_point_from_preview(event.x, event.y, view="processed")
            if sampled is not None:
                image_x, image_y, label = sampled
                self._add_transparent_region(image_x, image_y, label)
                self._set_canvas_tool_mode(None)
                self._refresh_action_states()
            return
        if self._is_brush_tool_mode(mode):
            coordinates = self._preview_image_coordinates(event.x, event.y, view="processed")
            if coordinates is None:
                return
            image_x, image_y = coordinates
            self._brush_stroke_active = True
            self._brush_stroke_tool_mode = mode
            self._brush_stroke_last_point = None
            self._brush_stroke_changed_pixels = 0
            self._capture_palette_undo_state()
            self._record_brush_stroke(image_x, image_y)
            self.canvas.configure(cursor="crosshair")
            return
        if not self._point_is_over_image(event.x, event.y):
            return
        self.dragging = True
        self.drag_origin = (event.x, event.y)
        self.drag_pan_start = (self.pan_x, self.pan_y)
        self.canvas.configure(cursor=CLOSED_HAND_CURSOR)

    def _on_canvas_drag(self, event: tk.Event) -> None:
        if getattr(self, "_brush_stroke_active", False) and self._is_brush_tool_mode(getattr(self, "_brush_stroke_tool_mode", None)):
            coordinates = self._preview_image_coordinates(event.x, event.y, view="processed")
            if coordinates is None:
                return
            image_x, image_y = coordinates
            self._record_brush_stroke(image_x, image_y)
            return
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
        if getattr(self, "_brush_stroke_active", False):
            changed = int(getattr(self, "_brush_stroke_changed_pixels", 0) or 0)
            if changed > 0:
                mode = getattr(self, "_brush_stroke_tool_mode", None)
                tool_name = self._brush_tool_display_name(mode)
                self.process_status_var.set(
                    f"{tool_name} changed {changed} pixel{'s' if changed != 1 else ''}. Press Undo to restore it."
                )
                self._refresh_action_states()
            else:
                clear_undo = getattr(self, "_clear_palette_undo_state", None)
                if callable(clear_undo):
                    clear_undo()
            self._reset_brush_stroke_state()
            self.canvas.configure(cursor=self._cursor_for_pointer())
            return
        self.dragging = False
        self.canvas.configure(cursor=self._cursor_for_pointer())

    def _on_canvas_motion(self, event: tk.Event) -> None:
        if self.dragging:
            self.canvas.configure(cursor=CLOSED_HAND_CURSOR)
        elif self._brush_tool_mode_active():
            self._set_pick_preview(None)
            self.canvas.configure(cursor="crosshair")
        elif self._active_pick_view() is not None:
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
        if self._canvas_tool_mode_value() is not None:
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
        assigned_primary = False
        if hit is None:
            self._palette_selection_indices = set()
            self._palette_selection_anchor_index = None
        else:
            index, label = hit
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
                self._assign_palette_color_to_slot(ACTIVE_COLOR_SLOT_PRIMARY, label)
                assigned_primary = True
        self._update_palette_strip()
        if not assigned_primary:
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
        hit = self._palette_hit_test(event.x, event.y)
        self._reset_palette_ctrl_drag_state()
        if hit is None:
            self._palette_selection_indices = set()
            self._palette_selection_anchor_index = None
            self._update_palette_strip()
            self._refresh_action_states()
            return
        _index, label = hit
        self._assign_palette_color_to_slot(ACTIVE_COLOR_SLOT_SECONDARY, label)

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

    def _invert_palette_selection(self) -> None:
        if not self._displayed_palette:
            self.process_status_var.set("There is no current palette to select.")
            return
        all_indices = set(range(len(self._displayed_palette)))
        current_selection = {
            index for index in getattr(self, "_palette_selection_indices", set()) if 0 <= index < len(self._displayed_palette)
        }
        inverted = all_indices - current_selection
        self._palette_selection_indices = inverted
        self._palette_selection_anchor_index = min(inverted) if inverted else None
        self._update_palette_strip()
        self._refresh_action_states()
        self.process_status_var.set(f"Inverted palette selection. {len(inverted)} palette colour{'s' if len(inverted) != 1 else ''} selected.")

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

    def _apply_view_selection(self, value: str, *, persist: bool) -> None:
        self.view_var.set("processed" if value == "processed" else "original")
        self.redraw_canvas()
        self._refresh_tool_button_styles()
        if persist:
            self._schedule_state_persist()

    def _on_view_changed(self) -> None:
        self._apply_view_selection(self.view_var.get(), persist=True)

    def _set_view(self, value: str) -> None:
        self._apply_view_selection(value, persist=False)

    def _set_view_from_toolbar(self, value: str) -> None:
        self._apply_view_selection(value, persist=True)

    def _update_scale_info(self) -> None:
        if self.original_display_image is None:
            self.scale_info_var.set("Open an image to set the pixel size.")
            return
        pixel_width = max(1, int(self.pixel_width_var.get() or self.session.current.pixel_width))
        output_width, output_height = target_size_for_pixel_width(self.original_display_image.width, self.original_display_image.height, pixel_width)
        self.scale_info_var.set(f"Pixel size: {pixel_width} px  Output: {output_width}x{output_height}")

    def _current_image_colour_count(self) -> int | None:
        current = self._current_output_result()
        if current is not None:
            return getattr(current.stats, "color_count", None)
        original_grid = getattr(self, "original_grid", None)
        if not original_grid:
            return None
        return len({colour for row in original_grid for colour in row})

    def _update_palette_strip(self) -> None:
        if hasattr(self, "_menu_items") and "palette_sort" in self._menu_items:
            self._populate_palette_sort_menu()
        self.palette_canvas.delete("all")
        self._palette_hit_regions = []
        preview_entry = getattr(self, "_builtin_palette_preview_entry", None)
        preview_active = preview_entry is not None
        if preview_entry is not None:
            palette = list(preview_entry.colors)
            source = f"Preview: {preview_entry.source_label}"
        else:
            palette, source = self._get_display_palette()
        if not palette:
            self._displayed_palette = []
            if not preview_active:
                self._palette_selection_indices = set()
                self._palette_selection_anchor_index = None
            palette_frame = getattr(self, "palette_frame", None)
            if palette_frame is not None and hasattr(palette_frame, "configure"):
                palette_frame.configure(text="PALETTE")
            self.palette_info_var.set("Palette: none")
            self.palette_canvas.yview_moveto(0)
            self.palette_canvas.configure(scrollregion=(0, 0, 0, 0))
            return
        displayed = palette[:MAX_PALETTE_SWATCHES]
        self._displayed_palette = list(displayed)
        display_selection = {index for index in self._palette_selection_indices if 0 <= index < len(displayed)}
        if not preview_active:
            self._palette_selection_indices = display_selection
        anchor_index = getattr(self, "_palette_selection_anchor_index", None)
        if not preview_active and anchor_index is not None and anchor_index >= len(displayed):
            self._palette_selection_anchor_index = None
        suffix = "" if len(displayed) == len(palette) else f" (showing first {len(displayed)})"
        selected_count = len(display_selection)
        selection_suffix = f", {selected_count} selected" if selected_count else ""
        palette_frame = getattr(self, "palette_frame", None)
        if palette_frame is not None and hasattr(palette_frame, "configure"):
            palette_frame.configure(text=f"PALETTE ({len(palette)})")
        self.palette_info_var.set(f"Palette: {source} ({len(palette)} colours{selection_suffix}){suffix}")
        scrollbar = getattr(self, "palette_scrollbar", None)
        scrollbar_width = scrollbar.winfo_width() if scrollbar is not None and scrollbar.winfo_ismapped() else 0
        available_width = max(PALETTE_SWATCH_SIZE, self.palette_canvas.winfo_width() - scrollbar_width)
        columns = max(1, available_width // PALETTE_SWATCH_SIZE)
        for index, colour in enumerate(displayed):
            row = index // columns
            col = index % columns
            x0 = col * PALETTE_SWATCH_SIZE
            y0 = row * PALETTE_SWATCH_SIZE
            x1 = x0 + PALETTE_SWATCH_SIZE - 1
            y1 = y0 + PALETTE_SWATCH_SIZE - 1
            selected = index in display_selection
            border_width = 2 if selected else 1
            border_colour = APP_ACCENT if selected else APP_BG
            self.palette_canvas.create_rectangle(x0, y0, x1, y1, fill=border_colour, outline="")
            self.palette_canvas.create_rectangle(
                x0 + border_width,
                y0 + border_width,
                x1 - border_width,
                y1 - border_width,
                fill=f"#{colour:06x}",
                outline="",
            )
            self._palette_hit_regions.append((x0, y0, x1, y1))
        total_rows = ((len(displayed) - 1) // columns) + 1
        self.palette_canvas.configure(scrollregion=(0, 0, columns * PALETTE_SWATCH_SIZE, total_rows * PALETTE_SWATCH_SIZE))

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
        if current is not None:
            resolution = f"{current.width}x{current.height}"
        elif self.original_display_image is not None:
            resolution = f"{self.original_display_image.width}x{self.original_display_image.height}"
        else:
            resolution = "-"
        colour_count = self._current_image_colour_count()
        colour_text = f"{colour_count} colours" if colour_count is not None else "-"
        self.image_info_var.set(f"{filename}  {resolution}  {colour_text}  {self.zoom}%")

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
            self.process_status_var.set("Ramp settings changed. Select palette colours and click Ramp to append new ramps.")
            self._schedule_state_persist()
            self._refresh_action_states()
            return
        elif auto_detect_changed:
            self.process_status_var.set(f"Auto-detect count set to {updated.auto_detect_count}.")
            self._schedule_state_persist()
            self._refresh_action_states()
            return
        elif palette_reduction_changed:
            self.process_status_var.set("Palette reduction settings changed. Click Reduce Palette to rebuild the palette.")
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
        palette_labels, _source = self._current_palette_source_labels()
        return PipelineConfig(
            pixel_width=settings.pixel_width,
            downsample_mode=settings.downsample_mode,
            colors=max(1, len(palette_labels) if palette_labels else settings.palette_reduction_colors),
            palette_strategy="override" if self._palette_is_override_mode() else "advanced",
            key_colors=(),
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
        adaptive_outline = self._outline_adaptive_enabled()
        can_merge_palette = has_palette_source and len(valid_palette_selection) >= 2 and not busy
        can_ramp_palette = has_palette_source and len(valid_palette_selection) >= 1 and not busy
        history = getattr(getattr(self, "session", None), "history", None)
        history_can_undo = getattr(history, "can_undo", None)
        history_can_redo = getattr(history, "can_redo", None)
        can_undo = (getattr(self, "_palette_undo_state", None) is not None) or (callable(history_can_undo) and history_can_undo())
        can_redo = (getattr(self, "_palette_redo_state", None) is not None) or (callable(history_can_redo) and history_can_redo())
        for widget_name, enabled in (
            ("downsample_button", has_image and not busy),
            ("generate_override_palette_button", has_downsample and not busy),
            ("reduce_palette_button", has_downsample and not busy and has_palette_source),
            ("add_palette_color_button", has_image and not busy),
            ("merge_palette_button", can_merge_palette),
            ("ramp_palette_button", can_ramp_palette),
            ("select_all_palette_button", has_palette_source and not busy),
            ("clear_palette_selection_button", has_palette_selection and not busy),
            ("invert_palette_selection_button", has_palette_source and not busy),
            ("remove_palette_color_button", has_palette_source and has_palette_selection and not busy),
        ):
            widget = getattr(self, widget_name, None)
            if widget is not None and hasattr(widget, "configure"):
                widget.configure(state=tk.NORMAL if enabled else tk.DISABLED)
        self._set_tool_button_enabled("palette_picker_button", has_output and not busy)
        self._set_tool_button_enabled("add_outline_button", has_output and not busy and (adaptive_outline or has_single_palette_selection))
        self._set_tool_button_enabled("remove_outline_button", has_output and not busy)
        self._set_tool_button_enabled("undo_button", can_undo and not busy)
        self._set_tool_button_enabled("redo_button", can_redo and not busy)
        self._set_tool_button_enabled("view_original_button", has_image and not busy)
        self._set_tool_button_enabled("view_processed_button", has_output and not busy)
        self._set_tool_button_enabled("zoom_in_button", has_image and not busy)
        self._set_tool_button_enabled("zoom_out_button", has_image and not busy)
        pixel_width_spinbox = getattr(self, "pixel_width_spinbox", None)
        if pixel_width_spinbox is not None and hasattr(pixel_width_spinbox, "configure"):
            pixel_width_spinbox.configure(state="normal" if has_image and not busy else "disabled")
        palette_reduction_spinbox = getattr(self, "palette_reduction_spinbox", None)
        if palette_reduction_spinbox is not None and hasattr(palette_reduction_spinbox, "configure"):
            palette_reduction_spinbox.configure(state="normal" if has_image and not busy else "disabled")
        adjustment_state = tk.NORMAL if has_palette_source and not busy else tk.DISABLED
        for control in getattr(self, "palette_adjustment_controls", []):
            control.configure(state=adjustment_state)
        self._menu_items["view"].entryconfigure("Processed", state=tk.NORMAL if has_output else tk.DISABLED)
        self._menu_items["file"].entryconfigure("Save", state=tk.NORMAL if can_save else tk.DISABLED)
        self._menu_items["file"].entryconfigure("Save As...", state=tk.NORMAL if can_save else tk.DISABLED)
        self._menu_items["edit"].entryconfigure("Undo", state=tk.NORMAL if can_undo and not busy else tk.DISABLED)
        self._menu_items["edit"].entryconfigure("Redo", state=tk.NORMAL if can_redo and not busy else tk.DISABLED)
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
        self._refresh_brush_control_states()
        self._refresh_outline_control_states()
        self._refresh_tool_button_styles()

    def _refresh_tool_button_styles(self) -> None:
        tool_mode = self._canvas_tool_mode_value()
        view_var = getattr(self, "view_var", None)
        view_getter = getattr(view_var, "get", None)
        current_view = view_getter() if callable(view_getter) else None
        active_states = {
            "pencil_button": tool_mode == CANVAS_TOOL_MODE_PENCIL,
            "eraser_button": tool_mode == CANVAS_TOOL_MODE_ERASER,
            "palette_picker_button": tool_mode == CANVAS_TOOL_MODE_ACTIVE_COLOR_PICK,
            "view_original_button": current_view == "original",
            "view_processed_button": current_view == "processed",
        }
        enabled_map = getattr(self, "_tool_button_enabled", {})
        for widget_name, active in active_states.items():
            widget = getattr(self, widget_name, None)
            enabled = enabled_map.get(widget_name, True)
            border_frame = getattr(self, "_tool_button_frames", {}).get(widget_name)
            if border_frame is not None and hasattr(border_frame, "configure"):
                border_frame.configure(bg=APP_ACCENT if active and enabled else APP_BORDER)
            if widget is not None and hasattr(widget, "configure"):
                if active and enabled:
                    widget.configure(style="ToolButtonActive.TButton")
                elif enabled:
                    widget.configure(style="ToolButton.TButton")
                else:
                    widget.configure(style="ToolButtonDisabled.TButton")

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

    def _on_outline_pixel_perfect_changed(self) -> None:
        self._schedule_state_persist()

    def _on_outline_colour_mode_changed(self) -> None:
        mode = self._outline_colour_mode()
        if getattr(self, "outline_colour_mode_var", None) is not None and self.outline_colour_mode_var.get() != mode:
            self.outline_colour_mode_var.set(mode)
        self._refresh_outline_control_states()
        self._schedule_state_persist()
        self._refresh_action_states()

    def _on_outline_adaptive_darken_changed(self, _event: tk.Event | None = None) -> None:
        percent = self._outline_adaptive_darken_percent()
        if getattr(self, "outline_adaptive_darken_percent_var", None) is not None and self.outline_adaptive_darken_percent_var.get() != percent:
            self.outline_adaptive_darken_percent_var.set(percent)
        self._schedule_state_persist()

    def _on_outline_add_generated_colours_changed(self) -> None:
        self._schedule_state_persist()

    def _on_outline_remove_brightness_threshold_enabled_changed(self) -> None:
        self._refresh_outline_control_states()
        self._schedule_state_persist()

    def _on_outline_remove_brightness_threshold_percent_changed(self, _event: tk.Event | None = None) -> None:
        threshold = self._outline_remove_brightness_threshold_percent()
        variable = getattr(self, "outline_remove_brightness_threshold_percent_var", None)
        getter = getattr(variable, "get", None)
        setter = getattr(variable, "set", None)
        if variable is not None and callable(getter) and callable(setter) and getter() != threshold:
            setter(threshold)
        self._schedule_state_persist()

    def _on_outline_remove_brightness_threshold_direction_changed(self) -> None:
        direction = self._outline_remove_brightness_threshold_direction()
        variable = getattr(self, "outline_remove_brightness_threshold_direction_var", None)
        getter = getattr(variable, "get", None)
        setter = getattr(variable, "set", None)
        if variable is not None and callable(getter) and callable(setter) and getter() != direction:
            setter(direction)
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
                "outline_pixel_perfect": self._outline_pixel_perfect_enabled(),
                "outline_colour_mode": self._outline_colour_mode(),
                "outline_adaptive_darken_percent": self._outline_adaptive_darken_percent(),
                "outline_add_generated_colours": self._outline_add_generated_colours_enabled(),
                "outline_remove_brightness_threshold_enabled": self._outline_remove_brightness_threshold_enabled(),
                "outline_remove_brightness_threshold_percent": self._outline_remove_brightness_threshold_percent(),
                "outline_remove_brightness_threshold_direction": self._outline_remove_brightness_threshold_direction(),
                "brush_width": self._brush_width(),
                "brush_shape": self._brush_shape(),
                "view_mode": self.view_var.get(),
                "primary_color_label": self._slot_color_label(ACTIVE_COLOR_SLOT_PRIMARY),
                "secondary_color_label": self._slot_color_label(ACTIVE_COLOR_SLOT_SECONDARY),
                "transparent_color_slot": self._transparent_color_slot_value(),
                "active_color_slot": self._active_color_slot_value(),
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

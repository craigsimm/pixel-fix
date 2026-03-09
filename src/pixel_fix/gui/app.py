from __future__ import annotations

import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageTk

from pixel_fix.palette.advanced import detect_key_colors_from_image, generate_structured_palette
from pixel_fix.palette.color_modes import extract_unique_colors
from pixel_fix.palette.io import load_palette, save_palette
from pixel_fix.palette.catalog import PaletteCatalogEntry, discover_palette_catalog
from pixel_fix.palette.model import StructuredPalette
from pixel_fix.palette.workspace import ColorWorkspace
from pixel_fix.pipeline import PipelineConfig
from pixel_fix.resample import resize_labels, target_size_for_pixel_width

from .persist import (
    append_process_log,
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
    display_resize_method,
    downsample_image,
    grid_to_pil_image,
    labels_to_rgb,
    load_png_grid,
    load_png_rgba_image,
    reduce_palette_image,
    rgb_to_labels,
)
from .state import PreviewSettings, SettingsSession
from .zoom import ZOOM_PRESETS, choose_fit_zoom, clamp_zoom, zoom_in, zoom_out

OPEN_HAND_CURSOR = "hand2"
CLOSED_HAND_CURSOR = "fleur"
MAX_PALETTE_SWATCHES = 256
PALETTE_SWATCH_SIZE = 18
PALETTE_SWATCH_GAP = 4
MAX_RECENT_FILES = 10
MAX_KEY_COLORS = 12

RESIZE_OPTIONS = (
    ("Nearest Neighbor", "nearest"),
    ("Bilinear Interpolation", "bilinear"),
    ("RotSprite", "rotsprite"),
)
QUANTIZER_OPTIONS = (
    ("Fast top colours (topk)", "topk"),
    ("Clustered colours (k-means)", "kmeans"),
)
DITHER_OPTIONS = (
    ("None", "none"),
    ("Ordered (Bayer)", "ordered"),
    ("Blue Noise", "blue-noise"),
)
GENERATED_SHADES_OPTIONS = (2, 4, 6, 8, 10)
AUTO_DETECT_COUNT_OPTIONS = tuple(range(1, MAX_KEY_COLORS + 1))
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
    palette_display_image: Image.Image | None
    image_state: str
    last_successful_process_snapshot: dict[str, object] | None


class PixelFixGui:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Pixel-Fix")
        self.root.geometry("1380x920")
        self._configure_window_icon()

        persisted = load_app_state()
        self.session = SettingsSession(deserialize_settings(persisted.get("settings")))
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
        self.key_colors: list[int] = []
        self.advanced_palette_preview: StructuredPalette | None = None
        self.key_color_pick_mode = False
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
        self.pixel_width_var = tk.IntVar()
        self.downsample_mode_var = tk.StringVar()
        self.generated_shades_var = tk.StringVar()
        self.auto_detect_count_var = tk.StringVar()
        self.contrast_bias_var = tk.DoubleVar()
        self.palette_dither_var = tk.StringVar()
        self.input_mode_var = tk.StringVar()
        self.output_mode_var = tk.StringVar()
        self.quantizer_var = tk.StringVar()
        self.dither_var = tk.StringVar()
        self.checkerboard_var = tk.BooleanVar(value=bool(persisted.get("checkerboard", False)))
        self.pixel_grid_var = tk.BooleanVar(value=bool(persisted.get("pixel_grid", False)))
        self.process_status_var = tk.StringVar(value="Open a PNG image to begin.")
        self.scale_info_var = tk.StringVar(value="Open an image to set the pixel size.")
        self.palette_info_var = tk.StringVar(value="Palette: none")
        self.image_info_var = tk.StringVar(value="No image  -  100%")

        self._menu_items: dict[str, tk.Menu] = {}
        self._build_menu_bar()
        self._build_layout()
        self._sync_controls_from_settings(self.session.current)
        palette_restore_needs_persist = self._restore_active_palette(persisted)
        self._update_scale_info()
        self._update_palette_strip()
        self._update_image_info()
        self._refresh_action_states()
        if palette_restore_needs_persist:
            self._schedule_state_persist()
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
        palette_menu.add_cascade(label="Input Mode", menu=input_menu)
        palette_menu.add_cascade(label="Output Mode", menu=output_menu)
        palette_menu.add_separator()
        palette_menu.add_cascade(label="Built-in Palettes", menu=built_in_menu)
        palette_menu.add_command(label="Load Palette...", command=self.load_palette_file)
        palette_menu.add_command(label="Save Current Palette...", command=self.save_palette_file)
        palette_menu.add_command(label="Clear Active Palette", command=self.clear_active_palette)
        menubar.add_cascade(label="Palette", menu=palette_menu)

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
        preferences_menu.add_checkbutton(label="Checkerboard background", variable=self.checkerboard_var, command=self._on_overlay_changed)
        preferences_menu.add_checkbutton(label="Pixel grid overlay", variable=self.pixel_grid_var, command=self._on_overlay_changed)
        preferences_menu.add_separator()
        preferences_menu.add_cascade(label="Resize Method", menu=resize_menu)
        menubar.add_cascade(label="Preferences", menu=preferences_menu)

        self.root.config(menu=menubar)
        self._menu_items["file"] = file_menu
        self._menu_items["edit"] = edit_menu
        self._menu_items["view"] = view_menu
        self._menu_items["palette"] = palette_menu
        self._menu_items["palette_input"] = input_menu
        self._menu_items["palette_output"] = output_menu
        self._menu_items["built_in_palettes"] = built_in_menu
        self._menu_items["preferences"] = preferences_menu
        self._menu_items["preferences_resize"] = resize_menu
        self._populate_builtin_palette_menu()
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
        self.downsample_button = tk.Button(downsample_section, text="Downsample", command=self.downsample_current_image, bg="#2d7d46", fg="white", relief=tk.FLAT, padx=14, pady=4)
        self.downsample_button.pack(anchor=tk.W, pady=(4, 0))

        palette_section = self._create_section(sidebar, "3. Apply palette")
        ttk.Label(palette_section, text="Key colours").pack(anchor=tk.W)
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
        ttk.Label(row, text="Auto Detect Count").pack(side=tk.LEFT)
        self.auto_detect_count_combo = ttk.Combobox(
            row,
            textvariable=self.auto_detect_count_var,
            values=[str(value) for value in AUTO_DETECT_COUNT_OPTIONS],
            state="readonly",
            width=8,
        )
        self.auto_detect_count_combo.pack(side=tk.RIGHT)
        self.auto_detect_count_combo.bind("<<ComboboxSelected>>", self._on_settings_changed, add="+")
        row = ttk.Frame(palette_section)
        row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(row, text="Generated Shades").pack(side=tk.LEFT)
        self.generated_shades_combo = ttk.Combobox(
            row,
            textvariable=self.generated_shades_var,
            values=[str(value) for value in GENERATED_SHADES_OPTIONS],
            state="readonly",
            width=8,
        )
        self.generated_shades_combo.pack(side=tk.RIGHT)
        self.generated_shades_combo.bind("<<ComboboxSelected>>", self._on_palette_settings_changed, add="+")
        row = ttk.Frame(palette_section)
        row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(row, text="Contrast Bias").pack(side=tk.LEFT)
        self.contrast_bias_scale = ttk.Scale(
            row,
            from_=0.0,
            to=200.0,
            variable=self.contrast_bias_var,
            command=lambda _value: self._on_palette_settings_changed(),
        )
        self.contrast_bias_scale.pack(side=tk.RIGHT, fill=tk.X, expand=True)
        row = ttk.Frame(palette_section)
        row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(row, text="Dithering").pack(side=tk.LEFT)
        self.palette_dither_combo = ttk.Combobox(
            row,
            textvariable=self.palette_dither_var,
            values=[label for (label, _value) in DITHER_OPTIONS],
            state="readonly",
            width=18,
        )
        self.palette_dither_combo.pack(side=tk.RIGHT, fill=tk.X, expand=True)
        self.palette_dither_combo.bind("<<ComboboxSelected>>", self._on_palette_settings_changed, add="+")
        self.generate_ramps_button = ttk.Button(palette_section, text="Generate Ramps", command=self._regenerate_all_ramps)
        self.generate_ramps_button.pack(anchor=tk.W, pady=(8, 0))
        self.reduce_palette_button = tk.Button(palette_section, text="Apply Palette", command=self.reduce_palette_current_image, bg="#2d7d46", fg="white", relief=tk.FLAT, padx=14, pady=4)
        self.reduce_palette_button.pack(anchor=tk.W, pady=(8, 0))

        workspace = ttk.Frame(body)
        workspace.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        palette_frame = ttk.LabelFrame(workspace, text="Current palette")
        palette_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(palette_frame, textvariable=self.palette_info_var).pack(anchor=tk.W, padx=8, pady=(6, 2))
        self.palette_canvas = tk.Canvas(palette_frame, height=60, background="#1e1e1e", highlightthickness=0)
        self.palette_canvas.pack(fill=tk.X, padx=8, pady=(0, 8))

        preview_frame = ttk.Frame(workspace)
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
        ttk.Label(status, textvariable=self.image_info_var).pack(side=tk.RIGHT)

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

        self._bind_shortcuts()

    def _create_section(self, parent: ttk.Frame, title: str) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text=title)
        frame.pack(fill=tk.X, pady=(0, 10))
        return frame

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
            preserve_palette = self.active_palette_path is not None and self.active_palette is not None
            preserved_palette = list(self.active_palette) if preserve_palette and self.active_palette is not None else None
            preserved_source = self.active_palette_source if preserve_palette else ""
            preserved_path = self.active_palette_path if preserve_palette else None
            self.source_path = path
            self.original_grid = load_png_grid(str(path))
            self.original_display_image = load_png_rgba_image(str(path))
            self.downsample_result = None
            self.palette_result = None
            self.downsample_display_image = None
            self.palette_display_image = None
            self.comparison_original_image = None
            self._comparison_original_key = None
            self.prepared_input_cache = None
            self.prepared_input_cache_key = None
            self.key_colors = []
            self.advanced_palette_preview = None
            self.key_color_pick_mode = False
            self._clear_palette_undo_state()
            self._set_active_palette(preserved_palette, preserved_source, preserved_path)
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

    def _apply_active_palette(
        self,
        palette: list[int] | tuple[int, ...] | None,
        source: str,
        path_value: str | None,
        *,
        message: str | None,
        mark_stale: bool = True,
    ) -> None:
        self._set_active_palette(palette, source, path_value)
        self._clear_palette_undo_state()
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

    def _palette_is_override_mode(self) -> bool:
        return self.active_palette is not None

    def _current_key_colors(self) -> list[int]:
        return list(self.key_colors)

    def _update_key_color_list(self) -> None:
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
        self.key_color_pick_mode = not self.key_color_pick_mode
        if self.key_color_pick_mode:
            self._set_view("original")
            self.process_status_var.set("Click the original preview to add a key colour.")
        else:
            self.process_status_var.set("Colour pick cancelled.")
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
        if self._palette_is_override_mode():
            return None
        if self.advanced_palette_preview is not None:
            return self.advanced_palette_preview
        current = self._current_output_result()
        if current is not None:
            return current.structured_palette
        return None

    def _sample_label_from_preview(self, canvas_x: int, canvas_y: int) -> int | None:
        if self._display_context is None or self._get_effective_view() != "original":
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
        pixel = self._display_context.sample_image.getpixel((image_x, image_y))
        red, green, blue = pixel[:3]
        return (int(red) << 16) | (int(green) << 8) | int(blue)

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
        source_grid = self._palette_source_grid()
        if source_grid is None:
            return
        self.process_status_var.set("Use Pick Colour and Generate Ramps for the manual palette workflow.")

    def load_palette_file(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[
                ("Palette files", "*.json *.gpl"),
                ("GIMP Palette", "*.gpl"),
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
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Palette JSON", "*.json")])
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

        self.image_state = "processing"
        self.quick_compare_active = False
        self.process_status_var.set("Preparing input...")
        self._refresh_action_states()
        config = self._build_pipeline_config(settings)

        def progress_callback(_percent: int, message: str) -> None:
            self.root.after(0, lambda: self.process_status_var.set(message))

        def worker() -> None:
            try:
                result = downsample_image(self.original_grid or [], config, progress_callback=progress_callback)
                self.root.after(0, lambda: self._handle_downsample_success(result, snapshot, changes, source_size, self._build_prepare_cache_key(settings)))
            except Exception as exc:  # noqa: BLE001
                self.root.after(0, lambda: self._handle_stage_failure(str(exc), changes, source_size))

        threading.Thread(target=worker, daemon=True).start()

    def reduce_palette_current_image(self) -> None:
        if self.prepared_input_cache is None or self.source_path is None:
            self.process_status_var.set("Downsample the image before applying a palette.")
            return
        if self.active_palette is None and self.advanced_palette_preview is None:
            self.process_status_var.set("Pick key colours and click Generate Ramps before applying the palette.")
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

        self.image_state = "processing"
        self.quick_compare_active = False
        self.process_status_var.set("Applying palette...")
        self._refresh_action_states()
        config = self._build_pipeline_config(settings)

        def progress_callback(_percent: int, message: str) -> None:
            self.root.after(0, lambda: self.process_status_var.set(message))

        def worker() -> None:
            try:
                result = reduce_palette_image(
                    self.prepared_input_cache,
                    config,
                    palette_override=self.active_palette,
                    structured_palette=None if self.active_palette is not None else self.advanced_palette_preview,
                    progress_callback=progress_callback,
                )
                self.root.after(0, lambda: self._handle_palette_success(result, snapshot, changes, source_size))
            except Exception as exc:  # noqa: BLE001
                self.root.after(0, lambda: self._handle_stage_failure(str(exc), changes, source_size))

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
            palette_result=self.palette_result,
            palette_display_image=self.palette_display_image.copy() if self.palette_display_image is not None else None,
            image_state=self.image_state,
            last_successful_process_snapshot=dict(self.last_successful_process_snapshot) if isinstance(self.last_successful_process_snapshot, dict) else self.last_successful_process_snapshot,
        )

    def _clear_palette_undo_state(self) -> None:
        self._palette_undo_state = None

    def _undo_palette_application(self) -> bool:
        if self._palette_undo_state is None:
            return False
        state = self._palette_undo_state
        self.palette_result = state.palette_result
        self.palette_display_image = state.palette_display_image.copy() if state.palette_display_image is not None else None
        self.image_state = state.image_state
        self.last_successful_process_snapshot = (
            dict(state.last_successful_process_snapshot) if isinstance(state.last_successful_process_snapshot, dict) else state.last_successful_process_snapshot
        )
        self.quick_compare_active = False
        self._clear_palette_undo_state()
        self.process_status_var.set("Reverted the last palette application.")
        self._update_palette_strip()
        self._update_image_info()
        self.redraw_canvas()
        self._schedule_state_persist()
        self._refresh_action_states()
        return True

    def _handle_downsample_success(
        self,
        result: ProcessResult,
        snapshot: dict[str, object],
        changes: list[str],
        source_size: tuple[int, int],
        cache_key: tuple[object, ...],
    ) -> None:
        self.downsample_result = result
        self.downsample_display_image = grid_to_pil_image(result.grid).convert("RGBA")
        self.palette_result = None
        self.palette_display_image = None
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
        self.process_status_var.set(
            f"Downsampled to {result.width}x{result.height} with {display_resize_method(result.stats.resize_method)} in {result.stats.elapsed_seconds:.2f}s."
        )
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
    ) -> None:
        self.palette_result = result
        self.palette_display_image = grid_to_pil_image(result.grid).convert("RGBA")
        if result.structured_palette is not None and result.structured_palette.source_mode == "advanced":
            self.advanced_palette_preview = result.structured_palette
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
        image.convert("RGB").save(path, format="PNG")
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
        self._draw_scale_overlay()
        self._update_image_info()

    def _render_display_image(self, sample_image: Image.Image, display_width: int, display_height: int) -> Image.Image:
        background = self._build_background(sample_image.size)
        composited = Image.alpha_composite(background, sample_image.convert("RGBA"))
        rendered = composited.resize((display_width, display_height), Image.Resampling.NEAREST)
        if self.pixel_grid_var.get() and self.zoom >= 400 and sample_image.width > 0 and sample_image.height > 0:
            draw = ImageDraw.Draw(rendered)
            cell_width = max(1, display_width // sample_image.width)
            cell_height = max(1, display_height // sample_image.height)
            if cell_width >= 4 and cell_height >= 4:
                for x in range(0, display_width + 1, cell_width):
                    draw.line((x, 0, x, display_height), fill=(0, 0, 0, 100))
                for y in range(0, display_height + 1, cell_height):
                    draw.line((0, y, display_width, y), fill=(0, 0, 0, 100))
        return rendered

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

    def _draw_scale_overlay(self) -> None:
        if not self._scale_overlay_active() or self._display_context is None or self.original_display_image is None:
            return
        sample_image = self._display_context.sample_image
        if sample_image is None:
            return
        width, height = sample_image.size
        step = self._overlay_grid_step(sample_image)

        for image_x in range(0, width + 1, step):
            x = self._image_x_to_canvas(image_x, width)
            self.canvas.create_line(x, self._display_context.image_top, x, self._display_context.image_top + self._display_context.display_height, fill="#4cc2ff", width=1)
        for image_y in range(0, height + 1, step):
            y = self._image_y_to_canvas(image_y, height)
            self.canvas.create_line(self._display_context.image_left, y, self._display_context.image_left + self._display_context.display_width, y, fill="#4cc2ff", width=1)

    def _scale_overlay_active(self) -> bool:
        return (
            self.original_display_image is not None
            and self._get_effective_view() == "original"
            and not self.quick_compare_active
            and not self.key_color_pick_mode
        )

    def _overlay_grid_step(self, sample_image: Image.Image) -> int:
        if sample_image is self.comparison_original_image:
            return 1
        return max(1, self.session.current.pixel_width)

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
        return self.palette_result or self.downsample_result

    def _current_output_image(self) -> Image.Image | None:
        return self.palette_display_image or self.downsample_display_image

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

    def _on_canvas_press(self, event: tk.Event) -> None:
        if self.key_color_pick_mode:
            sampled = self._sample_label_from_preview(event.x, event.y)
            if sampled is not None:
                self._add_key_color(sampled)
                self.key_color_pick_mode = False
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
        elif self.key_color_pick_mode:
            self.canvas.configure(cursor="crosshair")
        else:
            self.canvas.configure(cursor=OPEN_HAND_CURSOR if self._point_is_over_image(event.x, event.y) else "")

    def _on_canvas_leave(self, _event: tk.Event) -> None:
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
        if self.key_color_pick_mode:
            return "crosshair"
        return OPEN_HAND_CURSOR if self._point_is_over_image() else ""

    def _palette_hit_test(self, x: int, y: int) -> tuple[int, int] | None:
        del x, y
        return None

    def _on_palette_canvas_click(self, event: tk.Event) -> None:
        del event

    def _on_palette_canvas_double_click(self, event: tk.Event) -> None:
        del event

    def _on_palette_canvas_right_click(self, event: tk.Event) -> None:
        del event

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
        self.palette_canvas.delete("all")
        structured = self._displayed_structured_palette()
        palette, source = self._get_display_palette()
        if structured is not None and structured.ramps and not self._palette_is_override_mode():
            total_colours = structured.palette_size()
            self.palette_info_var.set(
                f"Palette: {structured.source_label or 'Generated'} ({total_colours} colours from {len(structured.key_colors)} key colour{'s' if len(structured.key_colors) != 1 else ''})"
            )
            row_height = PALETTE_SWATCH_SIZE + PALETTE_SWATCH_GAP + 10
            for ramp_index, ramp in enumerate(structured.ramps):
                y0 = 8 + ramp_index * row_height
                self.palette_canvas.create_text(8, y0 + (PALETTE_SWATCH_SIZE // 2), anchor=tk.W, fill="#d7d7d7", text=f"K{ramp_index + 1}")
                for shade_index, colour in enumerate(ramp.colors):
                    x0 = 34 + shade_index * (PALETTE_SWATCH_SIZE + PALETTE_SWATCH_GAP)
                    self.palette_canvas.create_rectangle(
                        x0,
                        y0,
                        x0 + PALETTE_SWATCH_SIZE,
                        y0 + PALETTE_SWATCH_SIZE,
                        fill=f"#{colour.label:06x}",
                        outline="#000000",
                        width=3 if colour.is_seed else 1,
                    )
            total_height = 8 + len(structured.ramps) * row_height
            self.palette_canvas.configure(height=max(70, min(220, total_height)))
            return
        if not palette:
            self.palette_info_var.set("Palette: none")
            self.palette_canvas.configure(height=60)
            return
        displayed = palette[:MAX_PALETTE_SWATCHES]
        suffix = "" if len(displayed) == len(palette) else f" (showing first {len(displayed)})"
        self.palette_info_var.set(f"Palette: {source} ({len(palette)} colours){suffix}")
        columns = max(1, max(200, self.palette_canvas.winfo_width()) // (PALETTE_SWATCH_SIZE + PALETTE_SWATCH_GAP))
        for index, colour in enumerate(displayed):
            row = index // columns
            col = index % columns
            x0 = 8 + col * (PALETTE_SWATCH_SIZE + PALETTE_SWATCH_GAP)
            y0 = 8 + row * (PALETTE_SWATCH_SIZE + PALETTE_SWATCH_GAP)
            self.palette_canvas.create_rectangle(x0, y0, x0 + PALETTE_SWATCH_SIZE, y0 + PALETTE_SWATCH_SIZE, fill=f"#{colour:06x}", outline="#000000")
        total_rows = ((len(displayed) - 1) // columns) + 1
        self.palette_canvas.configure(height=min(110, 8 + total_rows * (PALETTE_SWATCH_SIZE + PALETTE_SWATCH_GAP)))

    def _get_display_palette(self) -> tuple[list[int], str]:
        if self.active_palette:
            return self.active_palette, self.active_palette_source or "active"
        if self.advanced_palette_preview is not None:
            return self.advanced_palette_preview.labels(), self.advanced_palette_preview.source_label or "generated"
        current = self._current_output_result()
        if current is not None and current.structured_palette is not None:
            return current.structured_palette.labels(), current.structured_palette.source_label or current.stats.stage
        if current is not None:
            return extract_unique_colors(rgb_to_labels(current.grid)), current.stats.stage
        return ([], "none")

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
            generated_shades=max(2, min(10, int(self.generated_shades_var.get() or 4))),
            auto_detect_count=max(1, min(MAX_KEY_COLORS, int(self.auto_detect_count_var.get() or MAX_KEY_COLORS))),
            contrast_bias=max(0.0, min(2.0, float(self.contrast_bias_var.get()) / 100.0)),
            palette_dither_mode=DITHER_DISPLAY_TO_VALUE.get(self.palette_dither_var.get(), "none"),
            input_mode=COLOR_MODE_DISPLAY_TO_VALUE.get(self.input_mode_var.get(), "rgba"),
            output_mode=COLOR_MODE_DISPLAY_TO_VALUE.get(self.output_mode_var.get(), "rgba"),
            quantizer=QUANTIZER_DISPLAY_TO_VALUE.get(self.quantizer_var.get(), "topk"),
            dither_mode=DITHER_DISPLAY_TO_VALUE.get(self.dither_var.get(), "none"),
        )

    def _sync_controls_from_settings(self, settings: PreviewSettings) -> None:
        self._suspend_control_events = True
        try:
            self.pixel_width_var.set(settings.pixel_width)
            self.downsample_mode_var.set(RESIZE_VALUE_TO_DISPLAY.get(settings.downsample_mode, RESIZE_OPTIONS[0][0]))
            self.generated_shades_var.set(str(settings.generated_shades))
            self.auto_detect_count_var.set(str(settings.auto_detect_count))
            self.contrast_bias_var.set(settings.contrast_bias * 100.0)
            self.palette_dither_var.set(DITHER_VALUE_TO_DISPLAY.get(settings.palette_dither_mode, DITHER_OPTIONS[0][0]))
            self.input_mode_var.set(COLOR_MODE_VALUE_TO_DISPLAY.get(settings.input_mode, COLOR_MODE_OPTIONS[0][0]))
            self.output_mode_var.set(COLOR_MODE_VALUE_TO_DISPLAY.get(settings.output_mode, COLOR_MODE_OPTIONS[0][0]))
            self.quantizer_var.set(QUANTIZER_VALUE_TO_DISPLAY.get(settings.quantizer, QUANTIZER_OPTIONS[0][0]))
            self.dither_var.set(DITHER_VALUE_TO_DISPLAY.get(settings.dither_mode, DITHER_OPTIONS[0][0]))
        finally:
            self._suspend_control_events = False

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
        palette_apply_changed = (
            previous.palette_dither_mode != updated.palette_dither_mode
            or previous.output_mode != updated.output_mode
            or previous.quantizer != updated.quantizer
            or previous.dither_mode != updated.dither_mode
        )
        if downsample_changed:
            self._clear_palette_undo_state()
            self.prepared_input_cache = None
            self.prepared_input_cache_key = None
            message = message or "Pixel scale changed. Click Downsample to update the preview."
        elif ramp_generation_changed:
            self._clear_palette_undo_state()
            self.advanced_palette_preview = None
            message = message or "Ramp settings changed. Click Generate Ramps to rebuild the palette."
        elif auto_detect_changed:
            self.process_status_var.set(f"Auto-detect count set to {updated.auto_detect_count}.")
            self._schedule_state_persist()
            self._refresh_action_states()
            return
        elif palette_apply_changed:
            self._clear_palette_undo_state()
            message = message or "Palette settings changed. Click Apply Palette to update the preview."
        self._mark_output_stale(message)
        self._update_key_color_list()
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
        elif self.original_grid is not None:
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
        return (settings.pixel_width, settings.downsample_mode, settings.input_mode)

    def _refresh_action_states(self) -> None:
        busy = self.image_state == "processing"
        has_image = self.original_grid is not None
        has_output = self._current_output_result() is not None
        has_downsample = self.prepared_input_cache is not None
        has_generated_palette = self.advanced_palette_preview is not None
        can_save = self.image_state == "processed_current" and has_output
        has_active_palette = bool(self.active_palette)
        can_undo = (self._palette_undo_state is not None) or self.session.history.can_undo()
        advanced_editable = has_image and not busy and not self._palette_is_override_mode()
        for widget, enabled in (
            (self.downsample_button, has_image and not busy),
            (self.generate_ramps_button, advanced_editable and bool(self.key_colors)),
            (self.reduce_palette_button, has_downsample and not busy and (has_active_palette or has_generated_palette)),
            (self.zoom_in_button, has_image and not busy),
            (self.zoom_out_button, has_image and not busy),
            (self.pick_seed_button, advanced_editable),
            (self.auto_detect_button, advanced_editable),
            (self.remove_seed_button, advanced_editable and bool(self.key_color_listbox.curselection())),
            (self.clear_seeds_button, advanced_editable and bool(self.key_colors)),
        ):
            widget.configure(state=tk.NORMAL if enabled else tk.DISABLED)
        self.pick_seed_button.configure(text="Cancel Pick" if self.key_color_pick_mode else "Pick Colour")
        self.pixel_width_spinbox.configure(state="normal" if has_image and not busy else "disabled")
        self.key_color_listbox.configure(state=tk.NORMAL if advanced_editable else tk.DISABLED)
        self.auto_detect_count_combo.configure(state="readonly" if advanced_editable else "disabled")
        self.generated_shades_combo.configure(state="readonly" if advanced_editable else "disabled")
        self.contrast_bias_scale.configure(state="normal" if advanced_editable else "disabled")
        self.palette_dither_combo.configure(state="readonly" if advanced_editable else "disabled")
        self._menu_items["view"].entryconfigure("Processed", state=tk.NORMAL if has_output else tk.DISABLED)
        self._menu_items["file"].entryconfigure("Save", state=tk.NORMAL if can_save else tk.DISABLED)
        self._menu_items["file"].entryconfigure("Save As...", state=tk.NORMAL if can_save else tk.DISABLED)
        self._menu_items["edit"].entryconfigure("Undo", state=tk.NORMAL if can_undo and not busy else tk.DISABLED)
        self._menu_items["edit"].entryconfigure("Downsample", state=tk.NORMAL if has_image and not busy else tk.DISABLED)
        self._menu_items["edit"].entryconfigure(
            "Apply Palette",
            state=tk.NORMAL if has_downsample and not busy and (has_active_palette or has_generated_palette) else tk.DISABLED,
        )
        self._menu_items["palette"].entryconfigure("Input Mode", state=tk.NORMAL if not busy else tk.DISABLED)
        self._menu_items["palette"].entryconfigure("Output Mode", state=tk.NORMAL if not busy else tk.DISABLED)
        self._menu_items["palette"].entryconfigure("Built-in Palettes", state=tk.NORMAL if not busy else tk.DISABLED)
        self._menu_items["palette"].entryconfigure("Load Palette...", state=tk.NORMAL if not busy else tk.DISABLED)
        self._menu_items["palette"].entryconfigure("Save Current Palette...", state=tk.NORMAL if bool(self._get_display_palette()[0]) and not busy else tk.DISABLED)
        self._menu_items["palette"].entryconfigure("Clear Active Palette", state=tk.NORMAL if has_active_palette and not busy else tk.DISABLED)
        self._menu_items["preferences"].entryconfigure("Resize Method", state=tk.NORMAL if not busy else tk.DISABLED)

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
        save_app_state(
            {
                "settings": serialize_settings(self.session.current),
                "active_palette_path": self.active_palette_path,
                "active_palette_source": self.active_palette_source,
                "last_output_path": self.last_output_path,
                "last_successful_process_snapshot": self.last_successful_process_snapshot,
                "zoom": self.zoom,
                "checkerboard": self.checkerboard_var.get(),
                "pixel_grid": self.pixel_grid_var.get(),
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

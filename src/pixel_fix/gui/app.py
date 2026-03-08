from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from pixel_fix.palette.color_modes import extract_unique_colors
from pixel_fix.palette.io import load_palette, save_palette
from pixel_fix.palette.quantize import generate_palette
from pixel_fix.pipeline import PipelineConfig

from .processing import RGBGrid, render_preview, rgb_to_labels
from .state import PreviewSettings, SettingsSession
from .zoom import ZOOM_PRESETS, choose_fit_zoom, zoom_in, zoom_out


class PixelFixGui:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Pixel-Fix Preview")
        self.root.geometry("1260x860")

        self.session = SettingsSession()
        self.original_grid: RGBGrid | None = None
        self.preview_grid: RGBGrid | None = None
        self.source_path: Path | None = None
        self.render_version = 0
        self.active_palette: list[int] | None = None

        self.zoom = 100
        self.zoom_var = tk.IntVar(value=self.zoom)
        self.view_var = tk.StringVar(value="processed")
        self.status_var = tk.StringVar(value="Open a PNG image to begin.")

        self._image_ref: tk.PhotoImage | None = None
        self._debounce_id: str | None = None

        self._build_layout()

    def _build_layout(self) -> None:
        top = ttk.Frame(self.root)
        top.pack(fill=tk.X, padx=8, pady=8)

        ttk.Button(top, text="Open Image", command=self.open_image).pack(side=tk.LEFT)
        ttk.Button(top, text="Undo", command=self.undo).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(top, text="View:").pack(side=tk.LEFT, padx=(12, 0))
        ttk.Combobox(top, textvariable=self.view_var, values=("processed", "original"), state="readonly", width=10).pack(side=tk.LEFT)
        self.view_var.trace_add("write", lambda *_: self.redraw_canvas())

        ttk.Label(top, text="Zoom:").pack(side=tk.LEFT, padx=(12, 0))
        ttk.Combobox(top, textvariable=self.zoom_var, values=ZOOM_PRESETS, state="readonly", width=6).pack(side=tk.LEFT)
        self.zoom_var.trace_add("write", lambda *_: self._apply_zoom(self.zoom_var.get()))

        ttk.Button(top, text="-", width=3, command=self.zoom_step_out).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(top, text="+", width=3, command=self.zoom_step_in).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(top, text="Fit", command=self.zoom_fit).pack(side=tk.LEFT, padx=(6, 0))

        body = ttk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        controls = ttk.LabelFrame(body, text="Tweaks")
        controls.pack(side=tk.LEFT, fill=tk.Y)

        self.grid_var = tk.StringVar(value="auto")
        self.pixel_width_var = tk.StringVar(value="")
        self.colors_var = tk.IntVar(value=16)
        self.sampler_var = tk.StringVar(value="mode")
        self.min_island_var = tk.IntVar(value=2)
        self.bridge_var = tk.BooleanVar(value=False)
        self.line_color_var = tk.StringVar(value="0")

        self.input_mode_var = tk.StringVar(value="rgba")
        self.output_mode_var = tk.StringVar(value="rgba")
        self.quantizer_var = tk.StringVar(value="topk")
        self.dither_var = tk.StringVar(value="none")

        self.replace_enabled_var = tk.BooleanVar(value=False)
        self.replace_src_var = tk.StringVar(value="")
        self.replace_dst_var = tk.StringVar(value="")
        self.replace_tol_var = tk.IntVar(value=0)

        self._add_combo(controls, "Grid", self.grid_var, ("auto", "hough", "fft", "divisor"))
        self._add_entry(controls, "Pixel width", self.pixel_width_var)
        self._add_spin(controls, "Colors", self.colors_var, 2, 256)
        self._add_combo(controls, "Sampler", self.sampler_var, ("mode", "median"))
        self._add_spin(controls, "Min island", self.min_island_var, 1, 32)
        self._add_combo(controls, "Input mode", self.input_mode_var, ("rgba", "indexed", "grayscale"))
        self._add_combo(controls, "Output mode", self.output_mode_var, ("rgba", "indexed", "grayscale"))
        self._add_combo(controls, "Quantizer", self.quantizer_var, ("topk", "kmeans"))
        self._add_combo(controls, "Dithering", self.dither_var, ("none", "floyd-steinberg", "ordered"))

        line = ttk.Frame(controls)
        line.pack(fill=tk.X, padx=8, pady=4)
        ttk.Checkbutton(line, text="Bridge 1px gaps", variable=self.bridge_var, command=self._on_settings_changed).pack(side=tk.LEFT)
        self._add_entry(controls, "Line color", self.line_color_var)

        repl = ttk.LabelFrame(controls, text="Color Replacement")
        repl.pack(fill=tk.X, padx=8, pady=6)
        ttk.Checkbutton(repl, text="Enable", variable=self.replace_enabled_var, command=self._on_settings_changed).pack(anchor=tk.W, padx=4, pady=2)
        self._add_entry(repl, "From (#RRGGBB)", self.replace_src_var)
        self._add_entry(repl, "To (#RRGGBB)", self.replace_dst_var)
        self._add_spin(repl, "Tolerance", self.replace_tol_var, 0, 255)

        palette_actions = ttk.LabelFrame(controls, text="Palette")
        palette_actions.pack(fill=tk.X, padx=8, pady=6)
        ttk.Button(palette_actions, text="Extract Unique", command=self.extract_unique_palette).pack(fill=tk.X, padx=4, pady=2)
        ttk.Button(palette_actions, text="Generate Limited", command=self.generate_palette_from_image).pack(fill=tk.X, padx=4, pady=2)
        ttk.Button(palette_actions, text="Load Palette", command=self.load_palette_file).pack(fill=tk.X, padx=4, pady=2)
        ttk.Button(palette_actions, text="Save Palette", command=self.save_palette_file).pack(fill=tk.X, padx=4, pady=2)

        for variable in (
            self.grid_var,
            self.pixel_width_var,
            self.colors_var,
            self.sampler_var,
            self.min_island_var,
            self.line_color_var,
            self.input_mode_var,
            self.output_mode_var,
            self.quantizer_var,
            self.dither_var,
            self.replace_src_var,
            self.replace_dst_var,
            self.replace_tol_var,
        ):
            variable.trace_add("write", lambda *_: self._on_settings_changed())

        canvas_wrap = ttk.Frame(body)
        canvas_wrap.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(canvas_wrap, background="#222")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<ButtonPress-1>", self._start_pan)
        self.canvas.bind("<B1-Motion>", self._pan)
        self.canvas.bind("<Control-MouseWheel>", self._on_zoom_wheel)

        status = ttk.Label(self.root, textvariable=self.status_var, anchor=tk.W)
        status.pack(fill=tk.X, padx=8, pady=(0, 8))

    def _add_combo(self, parent: ttk.Widget, label: str, variable: tk.StringVar, values: tuple[str, ...]) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(row, text=label, width=16).pack(side=tk.LEFT)
        ttk.Combobox(row, textvariable=variable, values=values, state="readonly", width=14).pack(side=tk.RIGHT)

    def _add_entry(self, parent: ttk.Widget, label: str, variable: tk.StringVar) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(row, text=label, width=16).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=variable, width=16).pack(side=tk.RIGHT)

    def _add_spin(self, parent: ttk.Widget, label: str, variable: tk.IntVar, min_value: int, max_value: int) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(row, text=label, width=16).pack(side=tk.LEFT)
        ttk.Spinbox(row, from_=min_value, to=max_value, textvariable=variable, width=8).pack(side=tk.RIGHT)

    def open_image(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("PNG images", "*.png")])
        if not path:
            return
        try:
            self.source_path = Path(path)
            self.original_grid = self._load_png_grid(self.source_path)
            self.preview_grid = self.original_grid
            self.status_var.set(f"Loaded {self.source_path.name}: {len(self.original_grid[0])}x{len(self.original_grid)}")
            self.redraw_canvas()
            self.schedule_preview_render()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Failed to load image", str(exc))

    def extract_unique_palette(self) -> None:
        if self.original_grid is None:
            return
        labels = rgb_to_labels(self.original_grid)
        self.active_palette = extract_unique_colors(labels)
        self.status_var.set(f"Extracted {len(self.active_palette)} unique colors")
        self.schedule_preview_render()

    def generate_palette_from_image(self) -> None:
        if self.original_grid is None:
            return
        labels = rgb_to_labels(self.original_grid)
        self.active_palette = generate_palette(labels, colors=max(2, int(self.colors_var.get())), method=self.quantizer_var.get())
        self.status_var.set(f"Generated palette with {len(self.active_palette)} colors")
        self.schedule_preview_render()

    def load_palette_file(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Palette JSON", "*.json")])
        if not path:
            return
        try:
            self.active_palette = load_palette(Path(path))
            self.status_var.set(f"Loaded palette with {len(self.active_palette)} colors")
            self.schedule_preview_render()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Failed to load palette", str(exc))

    def save_palette_file(self) -> None:
        if not self.active_palette:
            messagebox.showwarning("No palette", "Extract or generate a palette first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Palette JSON", "*.json")])
        if not path:
            return
        save_palette(Path(path), self.active_palette)
        self.status_var.set(f"Saved palette to {Path(path).name}")

    def _load_png_grid(self, path: Path) -> RGBGrid:
        img = tk.PhotoImage(file=str(path))
        width, height = img.width(), img.height()
        grid: RGBGrid = []
        for y in range(height):
            row: list[tuple[int, int, int]] = []
            for x in range(width):
                pixel = img.get(x, y)
                if isinstance(pixel, tuple):
                    r, g, b = pixel[:3]
                else:
                    r, g, b = self.root.winfo_rgb(pixel)
                    r //= 256
                    g //= 256
                    b //= 256
                row.append((int(r), int(g), int(b)))
            grid.append(row)
        return grid

    def _grid_to_photoimage(self, grid: RGBGrid) -> tk.PhotoImage:
        height = len(grid)
        width = len(grid[0]) if height else 0
        image = tk.PhotoImage(width=width, height=height)
        for y, row in enumerate(grid):
            color_row = "{" + " ".join(f"#{r:02x}{g:02x}{b:02x}" for (r, g, b) in row) + "}"
            image.put(color_row, to=(0, y))
        return image

    def _get_active_grid(self) -> RGBGrid | None:
        if self.view_var.get() == "original":
            return self.original_grid
        return self.preview_grid or self.original_grid

    def redraw_canvas(self) -> None:
        grid = self._get_active_grid()
        if not grid:
            return
        image = self._grid_to_photoimage(grid)
        factor = max(1, self.zoom // 100)
        zoomed = image.zoom(factor, factor)
        self._image_ref = zoomed
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=zoomed, anchor=tk.NW)
        self.canvas.configure(scrollregion=(0, 0, zoomed.width(), zoomed.height()))

    def _on_settings_changed(self) -> None:
        if self.original_grid is None:
            return
        previous = self.session.current
        new = PreviewSettings(
            grid=self.grid_var.get(),
            pixel_width=self._parse_optional_int(self.pixel_width_var.get()),
            colors=max(2, int(self.colors_var.get())),
            cell_sampler=self.sampler_var.get(),
            min_island_size=max(1, int(self.min_island_var.get())),
            line_color=self._parse_optional_int(self.line_color_var.get()) if self.bridge_var.get() else None,
            input_mode=self.input_mode_var.get(),
            output_mode=self.output_mode_var.get(),
            quantizer=self.quantizer_var.get(),
            dither_mode=self.dither_var.get(),
            replace_src=self._parse_color(self.replace_src_var.get()) if self.replace_enabled_var.get() else None,
            replace_dst=self._parse_color(self.replace_dst_var.get()) if self.replace_enabled_var.get() else None,
            replace_tolerance=max(0, int(self.replace_tol_var.get())),
        )
        if new != previous:
            self.session.apply(**new.__dict__)
            self.schedule_preview_render()

    @staticmethod
    def _parse_optional_int(value: str) -> int | None:
        stripped = value.strip()
        if not stripped:
            return None
        return int(stripped)

    @staticmethod
    def _parse_color(value: str) -> int | None:
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.startswith("#"):
            stripped = stripped[1:]
        if len(stripped) != 6:
            raise ValueError("Color must be #RRGGBB")
        return int(stripped, 16)

    def schedule_preview_render(self) -> None:
        if self._debounce_id is not None:
            self.root.after_cancel(self._debounce_id)
        self._debounce_id = self.root.after(200, self._start_preview_render)

    def _start_preview_render(self) -> None:
        if self.original_grid is None:
            return
        self.render_version += 1
        render_id = self.render_version
        settings = self.session.current
        self.status_var.set("Rendering preview...")

        def worker() -> None:
            config = PipelineConfig(
                grid=settings.grid,
                pixel_width=settings.pixel_width,
                colors=settings.colors,
                cell_sampler=settings.cell_sampler,
                min_island_size=settings.min_island_size,
                line_color=settings.line_color,
                input_mode=settings.input_mode,
                output_mode=settings.output_mode,
                quantizer=settings.quantizer,
                dither_mode=settings.dither_mode,
                replace_src=settings.replace_src,
                replace_dst=settings.replace_dst,
                replace_tolerance=settings.replace_tolerance,
            )
            preview = render_preview(self.original_grid or [], config, palette_override=self.active_palette)
            self.root.after(0, lambda: self._apply_render_result(render_id, preview))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_render_result(self, render_id: int, preview: RGBGrid) -> None:
        if render_id != self.render_version:
            return
        self.preview_grid = preview
        if preview:
            self.status_var.set(f"Preview ready: {len(preview[0])}x{len(preview)} @ {self.zoom}%")
        self.redraw_canvas()

    def undo(self) -> None:
        if not self.session.history.can_undo():
            self.status_var.set("Nothing to undo.")
            return
        settings = self.session.undo()
        self._sync_controls_from_settings(settings)
        self.schedule_preview_render()

    def _sync_controls_from_settings(self, settings: PreviewSettings) -> None:
        self.grid_var.set(settings.grid)
        self.pixel_width_var.set("" if settings.pixel_width is None else str(settings.pixel_width))
        self.colors_var.set(settings.colors)
        self.sampler_var.set(settings.cell_sampler)
        self.min_island_var.set(settings.min_island_size)
        self.bridge_var.set(settings.line_color is not None)
        self.line_color_var.set("" if settings.line_color is None else str(settings.line_color))
        self.input_mode_var.set(settings.input_mode)
        self.output_mode_var.set(settings.output_mode)
        self.quantizer_var.set(settings.quantizer)
        self.dither_var.set(settings.dither_mode)
        self.replace_enabled_var.set(settings.replace_src is not None and settings.replace_dst is not None)
        self.replace_src_var.set("" if settings.replace_src is None else f"#{settings.replace_src:06x}")
        self.replace_dst_var.set("" if settings.replace_dst is None else f"#{settings.replace_dst:06x}")
        self.replace_tol_var.set(settings.replace_tolerance)

    def _apply_zoom(self, value: int) -> None:
        self.zoom = value
        self.redraw_canvas()

    def zoom_step_in(self) -> None:
        self.zoom_var.set(zoom_in(self.zoom))

    def zoom_step_out(self) -> None:
        self.zoom_var.set(zoom_out(self.zoom))

    def zoom_fit(self) -> None:
        grid = self._get_active_grid()
        if not grid:
            return
        self.zoom_var.set(choose_fit_zoom(len(grid[0]), len(grid), self.canvas.winfo_width(), self.canvas.winfo_height()))

    def _start_pan(self, event: tk.Event) -> None:
        self.canvas.scan_mark(event.x, event.y)

    def _pan(self, event: tk.Event) -> None:
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_zoom_wheel(self, event: tk.Event) -> None:
        if event.delta > 0:
            self.zoom_step_in()
        else:
            self.zoom_step_out()


def main() -> int:
    root = tk.Tk()
    app = PixelFixGui(root)
    root.bind("<Control-z>", lambda _: app.undo())
    root.bind("<Control-0>", lambda _: app.zoom_fit())
    root.bind("<Control-1>", lambda _: app.zoom_var.set(100))
    root.bind("<Control-2>", lambda _: app.zoom_var.set(200))
    root.bind("<Control-4>", lambda _: app.zoom_var.set(400))
    root.bind("<Control-8>", lambda _: app.zoom_var.set(800))
    root.mainloop()
    return 0

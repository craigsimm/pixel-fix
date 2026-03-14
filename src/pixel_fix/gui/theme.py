from __future__ import annotations

import ctypes
import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path

APP_BG = "#222323"
APP_SURFACE_BG = "#2B2D2D"
APP_HOVER_BG = "#343838"
APP_ACCENT = "#7FD9F8"
APP_BORDER = "#F0F6F0"
APP_TEXT = "#F0F6F0"
APP_MUTED_TEXT = "#8D968D"
PIXEL_FONT_FAMILY = "pixelmix"
HEADER_FONT_FAMILY = PIXEL_FONT_FAMILY
UI_FONT_SIZE = 6
HEADER_FONT_SIZE = UI_FONT_SIZE


def load_font_family(root: tk.Misc, font_path: Path, family: str) -> str:
    if family.lower() in {name.lower() for name in tkfont.families(root)}:
        return family
    if sys.platform == "win32" and font_path.exists():
        added = ctypes.windll.gdi32.AddFontResourceExW(str(font_path), 0x10, 0)
        if added:
            try:
                ctypes.windll.user32.SendMessageW(0xFFFF, 0x001D, 0, 0)
            except OSError:
                pass
    if family.lower() in {name.lower() for name in tkfont.families(root)}:
        return family
    return "TkFixedFont"

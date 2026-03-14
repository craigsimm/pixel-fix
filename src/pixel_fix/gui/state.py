from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class PreviewSettings:
    pixel_width: int = 2
    downsample_mode: str = "nearest"
    palette_reduction_colors: int = 16
    generated_shades: int = 4
    auto_detect_count: int = 12
    contrast_bias: float = 1.0
    palette_brightness: int = 0
    palette_contrast: int = 100
    palette_hue: int = 0
    palette_saturation: int = 100
    palette_dither_mode: str = "none"
    input_mode: str = "rgba"
    output_mode: str = "rgba"
    quantizer: str = "median-cut"
    dither_mode: str = "none"


class UndoHistory:
    def __init__(self) -> None:
        self._undo: list[PreviewSettings] = []
        self._redo: list[PreviewSettings] = []

    def push(self, settings: PreviewSettings) -> None:
        self._undo.append(settings)
        self._redo.clear()

    def push_undo(self, settings: PreviewSettings) -> None:
        self._undo.append(settings)

    def pop(self) -> PreviewSettings | None:
        if not self._undo:
            return None
        return self._undo.pop()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def push_redo(self, settings: PreviewSettings) -> None:
        self._redo.append(settings)

    def pop_redo(self) -> PreviewSettings | None:
        if not self._redo:
            return None
        return self._redo.pop()

    def can_redo(self) -> bool:
        return bool(self._redo)

    def clear_redo(self) -> None:
        self._redo.clear()


class SettingsSession:
    def __init__(self, initial: PreviewSettings | None = None) -> None:
        self.current = initial or PreviewSettings()
        self.history = UndoHistory()

    def apply(self, **changes: object) -> PreviewSettings:
        updated = replace(self.current, **changes)
        if updated != self.current:
            self.history.push(self.current)
            self.current = updated
        return self.current

    def undo(self) -> PreviewSettings:
        previous = self.history.pop()
        if previous is not None:
            self.history.push_redo(self.current)
            self.current = previous
        return self.current

    def redo(self) -> PreviewSettings:
        next_value = self.history.pop_redo()
        if next_value is not None:
            self.history.push_undo(self.current)
            self.current = next_value
        return self.current

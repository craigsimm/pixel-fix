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
    palette_dither_mode: str = "none"
    input_mode: str = "rgba"
    output_mode: str = "rgba"
    quantizer: str = "median-cut"
    dither_mode: str = "none"


class UndoHistory:
    def __init__(self) -> None:
        self._undo: list[PreviewSettings] = []

    def push(self, settings: PreviewSettings) -> None:
        self._undo.append(settings)

    def pop(self) -> PreviewSettings | None:
        if not self._undo:
            return None
        return self._undo.pop()

    def can_undo(self) -> bool:
        return bool(self._undo)


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
            self.current = previous
        return self.current

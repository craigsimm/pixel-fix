from __future__ import annotations

ZOOM_PRESETS = (100, 200, 400, 800)


def clamp_zoom(value: int) -> int:
    return min(ZOOM_PRESETS, key=lambda preset: abs(preset - value))


def zoom_in(current: int) -> int:
    current = clamp_zoom(current)
    for preset in ZOOM_PRESETS:
        if preset > current:
            return preset
    return ZOOM_PRESETS[-1]


def zoom_out(current: int) -> int:
    current = clamp_zoom(current)
    for preset in reversed(ZOOM_PRESETS):
        if preset < current:
            return preset
    return ZOOM_PRESETS[0]


def choose_fit_zoom(image_width: int, image_height: int, viewport_width: int, viewport_height: int) -> int:
    if image_width <= 0 or image_height <= 0 or viewport_width <= 0 or viewport_height <= 0:
        return 100
    fit = min((viewport_width / image_width), (viewport_height / image_height)) * 100
    if fit <= ZOOM_PRESETS[0]:
        return ZOOM_PRESETS[0]
    if fit >= ZOOM_PRESETS[-1]:
        return ZOOM_PRESETS[-1]
    valid = [preset for preset in ZOOM_PRESETS if preset <= fit]
    return valid[-1] if valid else ZOOM_PRESETS[0]

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GuideState:
    left: int | None = None
    right: int | None = None
    top: int | None = None
    bottom: int | None = None
    image_width: int | None = None
    image_height: int | None = None

    @property
    def initialized(self) -> bool:
        return None not in {
            self.left,
            self.right,
            self.top,
            self.bottom,
            self.image_width,
            self.image_height,
        }


@dataclass(frozen=True)
class GuideMetrics:
    is_valid: bool
    pixel_width: int | None
    output_size: tuple[int, int] | None
    message: str


def initialize_guides(image_width: int, image_height: int, suggested_size: int | None = None) -> GuideState:
    size_limit = max(1, min(image_width, image_height))
    size = suggested_size if suggested_size is not None else max(1, min(image_width, image_height) // 16)
    size = max(1, min(size_limit, int(size)))
    left = max(0, min(image_width - size, (image_width - size) // 2))
    top = max(0, min(image_height - size, (image_height - size) // 2))
    return GuideState(
        left=left,
        right=left + size,
        top=top,
        bottom=top + size,
        image_width=image_width,
        image_height=image_height,
    )


def is_guide_state_compatible(state: GuideState, image_width: int, image_height: int) -> bool:
    return state.initialized and state.image_width == image_width and state.image_height == image_height


def normalize_guide_state(state: GuideState, image_width: int, image_height: int) -> GuideState | None:
    if not state.initialized:
        return None
    left = max(0, min(image_width, int(state.left or 0)))
    right = max(0, min(image_width, int(state.right or 0)))
    top = max(0, min(image_height, int(state.top or 0)))
    bottom = max(0, min(image_height, int(state.bottom or 0)))
    left, right = sorted((left, right))
    top, bottom = sorted((top, bottom))
    size = min(right - left, bottom - top)
    if size < 1:
        return None
    right = left + size
    bottom = top + size
    if right > image_width:
        right = image_width
        left = right - size
    if bottom > image_height:
        bottom = image_height
        top = bottom - size
    if left < 0 or top < 0 or right <= left or bottom <= top:
        return None
    return GuideState(
        left=left,
        right=right,
        top=top,
        bottom=bottom,
        image_width=image_width,
        image_height=image_height,
    )


def guide_metrics(state: GuideState, image_width: int, image_height: int) -> GuideMetrics:
    normalized = normalize_guide_state(state, image_width, image_height)
    if normalized is None:
        return GuideMetrics(
            is_valid=False,
            pixel_width=None,
            output_size=None,
            message="Place guides to determine pixel size.",
        )
    pixel_width = normalized.right - normalized.left
    if pixel_width < 1:
        return GuideMetrics(
            is_valid=False,
            pixel_width=None,
            output_size=None,
            message="Place guides to determine pixel size.",
        )
    return GuideMetrics(
        is_valid=True,
        pixel_width=pixel_width,
        output_size=(max(1, image_width // pixel_width), max(1, image_height // pixel_width)),
        message=f"Pixel size: {pixel_width} px  Output: {max(1, image_width // pixel_width)}x{max(1, image_height // pixel_width)}",
    )


def guide_state_summary(state: GuideState, image_width: int, image_height: int) -> str:
    normalized = normalize_guide_state(state, image_width, image_height)
    if normalized is None:
        return "none"
    return f"L{normalized.left} R{normalized.right} T{normalized.top} B{normalized.bottom}"


def move_guide_edge(state: GuideState, edge: str, boundary: int, image_width: int, image_height: int) -> GuideState:
    normalized = normalize_guide_state(state, image_width, image_height)
    if normalized is None:
        normalized = initialize_guides(image_width, image_height)
    boundary = int(round(boundary))

    if edge == "top":
        bottom = normalized.bottom
        top = max(0, min(boundary, bottom - 1))
        size = bottom - top
        left = normalized.left
        right = left + size
        if right > image_width:
            right = image_width
            left = right - size
        return GuideState(left=left, right=right, top=top, bottom=bottom, image_width=image_width, image_height=image_height)
    if edge == "bottom":
        top = normalized.top
        bottom = min(image_height, max(boundary, top + 1))
        size = bottom - top
        left = normalized.left
        right = left + size
        if right > image_width:
            right = image_width
            left = right - size
        return GuideState(left=left, right=right, top=top, bottom=bottom, image_width=image_width, image_height=image_height)
    if edge == "left":
        right = normalized.right
        left = max(0, min(boundary, right - 1))
        size = right - left
        top = normalized.top
        bottom = top + size
        if bottom > image_height:
            bottom = image_height
            top = bottom - size
        return GuideState(left=left, right=right, top=top, bottom=bottom, image_width=image_width, image_height=image_height)
    if edge == "right":
        left = normalized.left
        right = min(image_width, max(boundary, left + 1))
        size = right - left
        top = normalized.top
        bottom = top + size
        if bottom > image_height:
            bottom = image_height
            top = bottom - size
        return GuideState(left=left, right=right, top=top, bottom=bottom, image_width=image_width, image_height=image_height)
    return normalized

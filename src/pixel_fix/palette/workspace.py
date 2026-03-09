from __future__ import annotations

from dataclasses import dataclass, field
from math import pi
from typing import Iterable

import numpy as np


def _unpack_labels(labels: np.ndarray) -> np.ndarray:
    flat = labels.astype(np.int64, copy=False).reshape(-1)
    red = (flat >> 16) & 0xFF
    green = (flat >> 8) & 0xFF
    blue = flat & 0xFF
    return np.stack((red, green, blue), axis=1).astype(np.float64) / 255.0


def _pack_rgb(rgb: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.rint(rgb * 255.0), 0, 255).astype(np.int64)
    return (clipped[:, 0] << 16) | (clipped[:, 1] << 8) | clipped[:, 2]


def srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    return np.where(
        rgb <= 0.04045,
        rgb / 12.92,
        ((rgb + 0.055) / 1.055) ** 2.4,
    )


def linear_to_srgb(rgb: np.ndarray) -> np.ndarray:
    return np.where(
        rgb <= 0.0031308,
        rgb * 12.92,
        1.055 * np.power(np.clip(rgb, 0.0, None), 1 / 2.4) - 0.055,
    )


def linear_to_oklab(rgb: np.ndarray) -> np.ndarray:
    l = 0.4122214708 * rgb[:, 0] + 0.5363325363 * rgb[:, 1] + 0.0514459929 * rgb[:, 2]
    m = 0.2119034982 * rgb[:, 0] + 0.6806995451 * rgb[:, 1] + 0.1073969566 * rgb[:, 2]
    s = 0.0883024619 * rgb[:, 0] + 0.2817188376 * rgb[:, 1] + 0.6299787005 * rgb[:, 2]

    l_root = np.cbrt(l)
    m_root = np.cbrt(m)
    s_root = np.cbrt(s)

    return np.stack(
        (
            0.2104542553 * l_root + 0.7936177850 * m_root - 0.0040720468 * s_root,
            1.9779984951 * l_root - 2.4285922050 * m_root + 0.4505937099 * s_root,
            0.0259040371 * l_root + 0.7827717662 * m_root - 0.8086757660 * s_root,
        ),
        axis=1,
    )


def oklab_to_linear(oklab: np.ndarray) -> np.ndarray:
    l_root = oklab[:, 0] + 0.3963377774 * oklab[:, 1] + 0.2158037573 * oklab[:, 2]
    m_root = oklab[:, 0] - 0.1055613458 * oklab[:, 1] - 0.0638541728 * oklab[:, 2]
    s_root = oklab[:, 0] - 0.0894841775 * oklab[:, 1] - 1.2914855480 * oklab[:, 2]

    l = l_root**3
    m = m_root**3
    s = s_root**3
    return np.stack(
        (
            +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
        ),
        axis=1,
    )


def hyab_distance(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    delta_l = np.abs(left[..., 0] - right[..., 0])
    delta_ab = np.sqrt(np.sum((left[..., 1:] - right[..., 1:]) ** 2, axis=-1))
    return delta_l + delta_ab


def oklab_to_oklch(oklab: np.ndarray) -> np.ndarray:
    chroma = np.sqrt(oklab[:, 1] ** 2 + oklab[:, 2] ** 2)
    hue = np.mod(np.arctan2(oklab[:, 2], oklab[:, 1]), 2 * np.pi)
    return np.stack((oklab[:, 0], chroma, hue), axis=1)


def oklch_to_oklab(oklch: np.ndarray) -> np.ndarray:
    return np.stack(
        (
            oklch[:, 0],
            oklch[:, 1] * np.cos(oklch[:, 2]),
            oklch[:, 1] * np.sin(oklch[:, 2]),
        ),
        axis=1,
    )


def circular_lerp(start: float, end: float, weight: float) -> float:
    delta = ((end - start + pi) % (2 * pi)) - pi
    return (start + delta * weight) % (2 * pi)


@dataclass
class ColorWorkspace:
    _oklab_cache: dict[int, tuple[float, float, float]] = field(default_factory=dict)

    def labels_to_oklab(self, labels: Iterable[int] | np.ndarray) -> np.ndarray:
        label_array = np.asarray(list(labels) if not isinstance(labels, np.ndarray) else labels, dtype=np.int64)
        original_shape = label_array.shape
        flat = label_array.reshape(-1)
        if flat.size == 0:
            return np.empty((*original_shape, 3), dtype=np.float64)

        unique, inverse = np.unique(flat, return_inverse=True)
        missing = [int(label) for label in unique if int(label) not in self._oklab_cache]
        if missing:
            missing_array = np.asarray(missing, dtype=np.int64)
            rgb = _unpack_labels(missing_array)
            oklab = linear_to_oklab(srgb_to_linear(rgb))
            for index, label in enumerate(missing_array):
                self._oklab_cache[int(label)] = tuple(float(value) for value in oklab[index])
        cached = np.asarray([self._oklab_cache[int(label)] for label in unique], dtype=np.float64)
        return cached[inverse].reshape(*original_shape, 3)

    def label_to_oklab(self, label: int) -> np.ndarray:
        return self.labels_to_oklab(np.asarray([label], dtype=np.int64))[0]

    def oklab_to_label(self, oklab: np.ndarray | tuple[float, float, float]) -> int:
        values = np.asarray(oklab, dtype=np.float64).reshape(1, 3)
        srgb = linear_to_srgb(oklab_to_linear(values))
        label = int(_pack_rgb(np.clip(srgb, 0.0, 1.0))[0])
        self._oklab_cache[label] = tuple(float(value) for value in self.labels_to_oklab(np.asarray([label], dtype=np.int64))[0])
        return label

    def labels_to_srgb(self, labels: Iterable[int] | np.ndarray) -> np.ndarray:
        label_array = np.asarray(list(labels) if not isinstance(labels, np.ndarray) else labels, dtype=np.int64)
        return _unpack_labels(label_array.reshape(-1)).reshape(*label_array.shape, 3)

    def cache_size(self) -> int:
        return len(self._oklab_cache)

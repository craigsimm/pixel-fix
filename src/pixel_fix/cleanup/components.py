from __future__ import annotations

from collections import Counter, deque

from pixel_fix.types import LabelGrid


def _neighbors(y: int, x: int, h: int, w: int, connectivity: int) -> list[tuple[int, int]]:
    steps4 = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    steps8 = steps4 + [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    steps = steps8 if connectivity == 8 else steps4
    out: list[tuple[int, int]] = []
    for dy, dx in steps:
        ny, nx = y + dy, x + dx
        if 0 <= ny < h and 0 <= nx < w:
            out.append((ny, nx))
    return out


def remove_small_islands(labels: LabelGrid, min_size: int, connectivity: int = 4) -> LabelGrid:
    if min_size <= 1:
        return [row[:] for row in labels]
    if connectivity not in {4, 8}:
        raise ValueError("connectivity must be 4 or 8")

    h = len(labels)
    w = len(labels[0]) if h else 0
    out = [row[:] for row in labels]
    visited = [[False] * w for _ in range(h)]

    for y in range(h):
        for x in range(w):
            if visited[y][x]:
                continue
            label = out[y][x]
            q = deque([(y, x)])
            visited[y][x] = True
            comp: list[tuple[int, int]] = []
            while q:
                cy, cx = q.popleft()
                comp.append((cy, cx))
                for ny, nx in _neighbors(cy, cx, h, w, connectivity):
                    if not visited[ny][nx] and out[ny][nx] == label:
                        visited[ny][nx] = True
                        q.append((ny, nx))

            if len(comp) >= min_size:
                continue

            comp_set = set(comp)
            neighbor_labels: list[int] = []
            for cy, cx in comp:
                for ny, nx in _neighbors(cy, cx, h, w, 8):
                    if (ny, nx) not in comp_set:
                        neighbor_labels.append(out[ny][nx])

            if not neighbor_labels:
                continue
            replacement = Counter(neighbor_labels).most_common(1)[0][0]
            for cy, cx in comp:
                out[cy][cx] = replacement

    return out

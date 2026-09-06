"""Расположение юнитов техники внутри зоны.

Позиция юнита зависит только от (seed, zone_index, cls_index, unit_index) —
не от того, какие ещё юниты присутствуют в этот день. Так один и тот же
"экскаватор №0" стоит на одном месте все сутки съёмки, даже если соседние
юниты то появляются, то исчезают из-за отклонений (R1/R4).
"""
from __future__ import annotations

from scripts.synth.rng import rng_for

GRID_COLS = 4
GRID_ROWS = 3
MARGIN = 0.22


def unit_anchor(
    seed: int,
    zone_index: int,
    zone_bbox: tuple[int, int, int, int],
    cls_index: int,
    unit_index: int,
) -> tuple[float, float]:
    x0, y0, x1, y1 = zone_bbox
    w, h = x1 - x0, y1 - y0
    cell_w, cell_h = w / GRID_COLS, h / GRID_ROWS

    cell_id = (zone_index * 97 + cls_index * 13 + unit_index * 7) % (GRID_COLS * GRID_ROWS)
    col, row = cell_id % GRID_COLS, cell_id // GRID_COLS

    rng = rng_for(seed, zone_index, cls_index, unit_index)
    jx = rng.uniform(MARGIN, 1 - MARGIN)
    jy = rng.uniform(MARGIN, 1 - MARGIN)

    x = x0 + (col + jx) * cell_w
    y = y0 + (row + jy) * cell_h
    return x, y


def frame_jitter(
    seed: int,
    day_index: int,
    frame_index: int,
    zone_index: int,
    cls_index: int,
    unit_index: int,
    amplitude: float,
) -> tuple[float, float]:
    if amplitude <= 0:
        return 0.0, 0.0
    rng = rng_for(seed, day_index, frame_index, zone_index, cls_index, unit_index)
    return rng.uniform(-amplitude, amplitude), rng.uniform(-amplitude, amplitude)

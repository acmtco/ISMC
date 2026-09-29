"""Оценка качества кадра — контракт `quality` в `docs/02-data-contract.md`.

Честность важнее красивых цифр (docs/01-principles.md, правило 4): чем хуже кадр
(размыт, ночь, залеплен объектив), тем ниже `score`. Аналитика использует
`score < 0.5`, чтобы не формировать отклонения на плохих данных.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# Дисперсия лапласиана резкого кадра (эмпирический ориентир для 640x480+;
# ниже — кадр считается тем более размытым).
SHARP_VARIANCE_REF = 400.0

NIGHT_BRIGHTNESS_THRESHOLD = 70.0
SATURATED_VALUE = 250
SATURATED_FRACTION_THRESHOLD = 0.02

# Сетка для оценки перекрытия/залепленности объектива: ячейки с низкой
# локальной дисперсией (однородное пятно) считаются перекрытыми.
OCCLUSION_GRID = 8
OCCLUSION_CELL_VARIANCE_THRESHOLD = 25.0


@dataclass(frozen=True)
class Quality:
    blur: float
    night: bool
    occlusion: float
    score: float

    def as_dict(self) -> dict:
        return {
            "blur": round(self.blur, 2),
            "night": self.night,
            "occlusion": round(self.occlusion, 2),
            "score": round(self.score, 2),
        }


def _clip01(x: float) -> float:
    return min(max(x, 0.0), 1.0)


def blur_score(gray: np.ndarray) -> float:
    """0 — идеально резко, 1 — сильно размыто."""
    variance = cv2.Laplacian(gray, cv2.CV_64F).var()
    return _clip01(1.0 - variance / SHARP_VARIANCE_REF)


def is_night(gray: np.ndarray) -> tuple[bool, float]:
    """Средняя яркость + доля насыщенных пикселей (блики фонарей/фар в темноте)."""
    mean_brightness = float(gray.mean())
    saturated_fraction = float(np.mean(gray >= SATURATED_VALUE))
    night = mean_brightness < NIGHT_BRIGHTNESS_THRESHOLD and (
        saturated_fraction < 0.2  # сплошная засветка — не ночь, а пересвет объектива днём
    )
    return night, mean_brightness


def occlusion_fraction(gray: np.ndarray) -> float:
    """Доля кадра, похожая на однородное пятно (грязный/залепленный объектив)."""
    h, w = gray.shape
    cell_h, cell_w = h // OCCLUSION_GRID, w // OCCLUSION_GRID
    if cell_h == 0 or cell_w == 0:
        return 0.0
    occluded_cells = 0
    total_cells = 0
    for row in range(OCCLUSION_GRID):
        for col in range(OCCLUSION_GRID):
            cell = gray[row * cell_h : (row + 1) * cell_h, col * cell_w : (col + 1) * cell_w]
            total_cells += 1
            if cell.var() < OCCLUSION_CELL_VARIANCE_THRESHOLD:
                occluded_cells += 1
    return occluded_cells / total_cells if total_cells else 0.0


def assess_quality(image: np.ndarray) -> Quality:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    blur = blur_score(gray)
    night, _ = is_night(gray)
    occlusion = occlusion_fraction(gray)

    score = 1.0 - 0.5 * blur - (0.4 if night else 0.0) - 0.6 * occlusion
    return Quality(blur=blur, night=night, occlusion=occlusion, score=_clip01(score))

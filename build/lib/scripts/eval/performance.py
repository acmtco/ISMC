"""Кадров/сек и оценочная стоимость обработки (docs/04-metrics.md, раздел 7).

Меряем фактическую пропускную способность перцепции БЕЗ инференса детектора
(весов ещё нет — см. `pipeline_run.py`): оценка качества кадра, признаки
состояния (оптический поток, HSV), склейка треков. Время самого
YOLO-инференса в это число не входит — это честно отражено в отчёте, а не
подогнано под ожидания (docs/01-principles.md, правило 4).
"""
from __future__ import annotations

from dataclasses import dataclass

# Допущение для оценки стоимости — почасовая ставка недорогого CPU-инстанса
# в облаке; ориентир, требует уточнения перед публикацией на питче
# (docs/04-metrics.md, раздел 7: "считать честно, с указанием допущений").
CPU_HOUR_COST_RUB = 3.0


@dataclass(frozen=True)
class PerformanceEstimate:
    fps_cpu_perception_only: float
    seconds_per_camera_day: float
    cost_per_camera_day_rub: float
    cost_per_1000_cameras_per_day_rub: float


def estimate_performance(
    fps: float, frames_per_camera_day: float, cpu_hour_cost_rub: float = CPU_HOUR_COST_RUB
) -> PerformanceEstimate:
    seconds_per_day = frames_per_camera_day / fps if fps > 0 else 0.0
    cost_per_day = (seconds_per_day / 3600) * cpu_hour_cost_rub
    return PerformanceEstimate(
        fps_cpu_perception_only=fps,
        seconds_per_camera_day=seconds_per_day,
        cost_per_camera_day_rub=cost_per_day,
        cost_per_1000_cameras_per_day_rub=cost_per_day * 1000,
    )

"""MAE/MAPE суточных `mh_active` против ground truth (docs/04-metrics.md,
раздел 4). Сравнивает агрегат по выходу `run_realistic_pipeline` (реальные
признаки, предсказанное состояние) с агрегатом по самому ground truth
(истинное состояние) — расхождение отражает ошибку классификатора
состояния + оценки качества кадра, не ошибку детектора (боксы/классы общие).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from services.analytics.machine_hours import aggregate_machine_hours


@dataclass(frozen=True)
class MachineHoursError:
    mae_active_hours: float
    mape_active_pct: float
    mae_present_hours: float
    bias_active_hours: float
    n_rows: int


def evaluate_machine_hours(
    predicted_detections: list[dict], ground_truth_records: list[dict], *, object_id: str
) -> MachineHoursError:
    predicted_rows = aggregate_machine_hours(predicted_detections, object_id=object_id)
    truth_rows = aggregate_machine_hours(ground_truth_records, object_id=object_id)

    truth_by_key = {(r["date"], r["zone_id"], r["cls"]): r for r in truth_rows}
    pred_by_key = {(r["date"], r["zone_id"], r["cls"]): r for r in predicted_rows}
    keys = set(truth_by_key) | set(pred_by_key)

    errors_active: list[float] = []
    errors_present: list[float] = []
    pct_errors: list[float] = []

    for key in keys:
        truth = truth_by_key.get(key)
        pred = pred_by_key.get(key)
        truth_active = truth["mh_active"] if truth else 0.0
        pred_active = pred["mh_active"] if pred else 0.0
        truth_present = truth["mh_present"] if truth else 0.0
        pred_present = pred["mh_present"] if pred else 0.0

        errors_active.append(pred_active - truth_active)
        errors_present.append(pred_present - truth_present)
        if truth_active > 0:
            pct_errors.append(abs(pred_active - truth_active) / truth_active * 100)

    errors_active_arr = np.array(errors_active) if errors_active else np.array([0.0])
    errors_present_arr = np.array(errors_present) if errors_present else np.array([0.0])

    return MachineHoursError(
        mae_active_hours=float(np.mean(np.abs(errors_active_arr))),
        mape_active_pct=float(np.mean(pct_errors)) if pct_errors else 0.0,
        mae_present_hours=float(np.mean(np.abs(errors_present_arr))),
        bias_active_hours=float(np.mean(errors_active_arr)),
        n_rows=len(keys),
    )

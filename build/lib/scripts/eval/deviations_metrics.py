"""Precision/recall/F1 выявления отклонений против `expected_deviations.jsonl`,
по типам Р1-Р4, плюс средняя задержка обнаружения (docs/04-metrics.md,
раздел 5). Р0 (низкое доверие) сознательно не участвует в этом сравнении —
это не аномалия, которую нужно "поймать", а служебная метка (см. докстринг
`services/analytics/deviations.py`).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import numpy as np

from scripts.synth.scenario import Scenario
from services.analytics.deviations import DeviationEngine
from services.analytics.machine_hours import daily_quality

DEVIATION_TYPES = ("R1_resource_gap", "R2_idle", "R3_front_mismatch", "R4_silence")


@dataclass(frozen=True)
class DeviationTypeMetrics:
    type: str
    expected: int
    detected: int
    matched: int
    precision: float | None
    recall: float | None
    f1: float | None
    mean_delay_days: float | None


@dataclass(frozen=True)
class DeviationEvaluation:
    by_type: list[DeviationTypeMetrics]
    overall: DeviationTypeMetrics
    detected_raw: list[dict]


def _periods_overlap(a_from: str, a_to: str, b_from: str, b_to: str) -> bool:
    return date.fromisoformat(a_from) <= date.fromisoformat(b_to) and date.fromisoformat(
        b_from
    ) <= date.fromisoformat(a_to)


def _match(detected: list[dict], expected: list[dict]) -> list[tuple[dict, dict]]:
    """Жадное сопоставление 1:1 по (type, zone_id) с пересекающимися периодами."""
    pairs = []
    used_expected: set[int] = set()
    for det in detected:
        for i, exp in enumerate(expected):
            if i in used_expected:
                continue
            if det["zone_id"] != exp["zone_id"]:
                continue
            if _periods_overlap(
                det["period"]["from"],
                det["period"]["to"],
                exp["period"]["from"],
                exp["period"]["to"],
            ):
                pairs.append((det, exp))
                used_expected.add(i)
                break
    return pairs


def build_schedule_dicts(scenario: Scenario) -> list[dict]:
    """`planned_mh` выводится из типичного состава сценария (count ×
    active_ratio × окно активности × число суток) — эвристика для оценки:
    синтетический сценарий не несёт реальных объёмов/норм, в отличие от
    настоящего `schedule.json`. `active_ratio` обязателен: без него план
    предполагал бы 100%-ную загрузку техники каждый день, и Р1 (дефицит)
    ложно срабатывал бы на любой обычный день с типичной (не 100%) занятостью
    — а не только в дни внедрённого дефицита."""
    schedule = []
    for entry in scenario.schedule:
        work_type = scenario.work_types[entry.work_type]
        daily_hours = sum(end - start for start, end in work_type.active_hours)
        total_days = (entry.date_to - entry.date_from).days + 1
        planned_mh = {
            cls: spec.count * spec.active_ratio * daily_hours * total_days
            for cls, spec in work_type.classes.items()
        }
        schedule.append(
            {
                "work_id": entry.work_id,
                "name": entry.work_type,
                "work_type": entry.work_type,
                "zone_id": entry.zone_id,
                "start_plan": entry.date_from.isoformat(),
                "finish_plan": entry.date_to.isoformat(),
                "planned_mh": planned_mh,
            }
        )
    return schedule


def _type_metrics(
    type_label: str, det_t: list[dict], exp_t: list[dict]
) -> tuple[DeviationTypeMetrics, list[int]]:
    pairs = _match(det_t, exp_t)
    precision = len(pairs) / len(det_t) if det_t else None
    recall = len(pairs) / len(exp_t) if exp_t else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and (precision + recall) > 0
        else None
    )
    delays = [
        (date.fromisoformat(det["period"]["from"]) - date.fromisoformat(exp["period"]["from"])).days
        for det, exp in pairs
    ]
    metrics = DeviationTypeMetrics(
        type=type_label,
        expected=len(exp_t),
        detected=len(det_t),
        matched=len(pairs),
        precision=precision,
        recall=recall,
        f1=f1,
        mean_delay_days=float(np.mean(delays)) if delays else None,
    )
    return metrics, delays


def evaluate_deviations(
    *,
    scenario: Scenario,
    machine_hours: list[dict],
    detections: list[dict],
    expected_deviations: list[dict],
    engine: DeviationEngine,
    as_of: datetime,
) -> DeviationEvaluation:
    schedule = build_schedule_dicts(scenario)
    dq = daily_quality(detections)
    detected = engine.run(
        schedule=schedule, machine_hours=machine_hours, daily_quality=dq, as_of=as_of
    )

    by_type = []
    all_delays: list[int] = []
    all_matched = all_detected = all_expected = 0

    for dtype in DEVIATION_TYPES:
        det_t = [d for d in detected if d["type"] == dtype]
        exp_t = [e for e in expected_deviations if e["type"] == dtype]
        metrics, delays = _type_metrics(dtype, det_t, exp_t)
        by_type.append(metrics)
        all_matched += metrics.matched
        all_detected += metrics.detected
        all_expected += metrics.expected
        all_delays.extend(delays)

    overall_precision = all_matched / all_detected if all_detected else None
    overall_recall = all_matched / all_expected if all_expected else None
    overall_f1 = (
        2 * overall_precision * overall_recall / (overall_precision + overall_recall)
        if overall_precision is not None
        and overall_recall is not None
        and (overall_precision + overall_recall) > 0
        else None
    )
    overall = DeviationTypeMetrics(
        type="Всего",
        expected=all_expected,
        detected=all_detected,
        matched=all_matched,
        precision=overall_precision,
        recall=overall_recall,
        f1=overall_f1,
        mean_delay_days=float(np.mean(all_delays)) if all_delays else None,
    )

    return DeviationEvaluation(by_type=by_type, overall=overall, detected_raw=detected)

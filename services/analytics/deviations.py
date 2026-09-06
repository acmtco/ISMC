"""Правила Р0-Р4 (docs/03-deviation-rules.md, шаг 3). Все пороги —
`config/thresholds.yaml`, ни одного магического числа в коде.

Классификация идёт по суткам, по приоритету (честнее один явный диагноз на
день, чем несколько противоречащих друг другу):

    R0 (нет данных) > R4 (тишина) > R1 (дефицит) > R3 (несоответствие) > R2 (простой)

Затем однотипные подряд идущие сутки одной зоны схлопываются в один
"пробег" (`_consecutive_runs`), который становится одной карточкой
отклонения — если пробег короче минимума правила (см. thresholds.yaml),
отклонение по этим суткам не формируется вовсе (не понижается до другого
правила: упрощение, см. докстринг класса `DeviationEngine`).

`match_score` здесь считается без ритма (`observed_rhythm=None` -> вклад
ритма нейтральный 1.0): подсчёт реальных "рейсов техники" требует данных о
заходе/выходе из зоны по трекам, которых нет в контракте `machine_hours.jsonl`
— честная, задокументированная упрощённая версия Р3(б).
"""
from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from services.analytics import forecast as forecast_mod
from services.analytics.economics import CostReference, idle_cost_rub
from services.analytics.machine_hours import DayQuality
from services.analytics.matching import (
    MatchingConfig,
    WorkSignature,
    best_competing_match,
    load_signatures,
    match_score,
)
from services.analytics.ru_text import ru_count_list

FrameLookup = Callable[[str, date, date], list[str]]

DEVIATION_TYPES = (
    "R0_low_confidence",
    "R1_resource_gap",
    "R2_idle",
    "R3_front_mismatch",
    "R4_silence",
)


# ---------------------------------------------------------------------------
# Пороги
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Thresholds:
    r1_fact_vs_plan_ratio: float
    r1_min_consecutive_days: int
    r1_min_coverage: float
    r1_high_severity_delay_days: int
    r2_utilization_max: float
    r2_min_mh_present_per_shift: float
    r2_high_severity_period_cost_rub: float
    r3_low_match_score: float
    r3_competing_match_score: float
    r3_high_severity_min_days: int
    r4_min_consecutive_days: int
    r4_min_coverage: float
    r0_min_coverage: float
    r0_min_quality_score: float

    @classmethod
    def from_yaml(cls, path: Path) -> Thresholds:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        r1, r2, r3, r4, r0 = (
            raw["r1_resource_gap"],
            raw["r2_idle"],
            raw["r3_front_mismatch"],
            raw["r4_silence"],
            raw["r0_low_confidence"],
        )
        return cls(
            r1_fact_vs_plan_ratio=float(r1["fact_vs_plan_ratio"]),
            r1_min_consecutive_days=int(r1["min_consecutive_days"]),
            r1_min_coverage=float(r1["min_coverage"]),
            r1_high_severity_delay_days=int(r1["high_severity_delay_days"]),
            r2_utilization_max=float(r2["utilization_max"]),
            r2_min_mh_present_per_shift=float(r2["min_mh_present_per_shift"]),
            r2_high_severity_period_cost_rub=float(r2["high_severity_period_cost_rub"]),
            r3_low_match_score=float(r3["low_match_score"]),
            r3_competing_match_score=float(r3["competing_match_score"]),
            r3_high_severity_min_days=int(r3["high_severity_min_days"]),
            r4_min_consecutive_days=int(r4["min_consecutive_days"]),
            r4_min_coverage=float(r4["min_coverage"]),
            r0_min_coverage=float(r0["min_coverage"]),
            r0_min_quality_score=float(r0["min_quality_score"]),
        )


# ---------------------------------------------------------------------------
# Входные данные
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScheduleEntry:
    work_id: str
    name: str
    work_type: str | None
    zone_id: str | None
    start_plan: date
    finish_plan: date
    planned_mh: dict[str, float]

    def covers(self, day: date) -> bool:
        return self.start_plan <= day <= self.finish_plan

    @classmethod
    def from_dict(cls, raw: dict) -> ScheduleEntry:
        return cls(
            work_id=raw["work_id"],
            name=raw.get("name", raw["work_id"]),
            work_type=raw.get("work_type"),
            zone_id=raw.get("zone_id"),
            start_plan=date.fromisoformat(raw["start_plan"]),
            finish_plan=date.fromisoformat(raw["finish_plan"]),
            planned_mh=dict(raw.get("planned_mh") or {}),
        )


def _load_schedule(raw_entries: list[dict]) -> list[ScheduleEntry]:
    return [ScheduleEntry.from_dict(r) for r in raw_entries]


def _index_machine_hours(rows: list[dict]) -> dict[tuple[str, date], dict[str, dict]]:
    """(zone_id, date) -> {cls: row}."""
    index: dict[tuple[str, date], dict[str, dict]] = defaultdict(dict)
    for row in rows:
        key = (row["zone_id"], date.fromisoformat(row["date"]))
        index[key][row["cls"]] = row
    return index


# ---------------------------------------------------------------------------
# Классификация суток
# ---------------------------------------------------------------------------


@dataclass
class DayClassification:
    day: date
    zone_id: str
    type: str | None
    subtype: str | None  # только для R3: "forbidden" | "competing" | "no_schedule"
    work: ScheduleEntry | None
    mh_present: dict[str, float]
    mh_active: dict[str, float]
    mh_idle: dict[str, float]
    units_seen: dict[str, int]
    utilization: dict[str, float]
    quality: DayQuality


def _classify_day(
    *,
    day: date,
    zone_id: str,
    work: ScheduleEntry | None,
    rows_by_cls: dict[str, dict],
    quality: DayQuality,
    signatures: dict[str, WorkSignature],
    matching_config: MatchingConfig,
    thresholds: Thresholds,
) -> DayClassification:
    mh_present = {cls: r["mh_present"] for cls, r in rows_by_cls.items()}
    mh_active = {cls: r["mh_active"] for cls, r in rows_by_cls.items()}
    mh_idle = {cls: r["mh_idle"] for cls, r in rows_by_cls.items()}
    units_seen = {cls: r["units_seen"] for cls, r in rows_by_cls.items()}
    utilization = {cls: r["utilization"] for cls, r in rows_by_cls.items()}

    base = dict(
        day=day,
        zone_id=zone_id,
        work=work,
        mh_present=mh_present,
        mh_active=mh_active,
        mh_idle=mh_idle,
        units_seen=units_seen,
        utilization=utilization,
        quality=quality,
    )

    low_confidence = (
        quality.coverage < thresholds.r0_min_coverage
        or quality.avg_quality_score < thresholds.r0_min_quality_score
    )
    if low_confidence:
        return DayClassification(type="R0_low_confidence", subtype=None, **base)

    total_present = sum(mh_present.values())

    if work is None:
        if total_present > 0:
            return DayClassification(type="R3_front_mismatch", subtype="no_schedule", **base)
        return DayClassification(type=None, subtype=None, **base)

    signature = signatures.get(work.work_type) if work.work_type else None

    if total_present == 0:
        return DayClassification(type="R4_silence", subtype=None, **base)

    if signature is not None:
        work_days = (work.finish_plan - work.start_plan).days + 1
        deficient = any(
            mh_active.get(cls, 0.0) < thresholds.r1_fact_vs_plan_ratio * (planned / work_days)
            for cls, planned in work.planned_mh.items()
            if cls in signature.required and work_days > 0
        )
        if deficient and quality.coverage >= thresholds.r1_min_coverage:
            return DayClassification(type="R1_resource_gap", subtype=None, **base)

        forbidden_present = any(mh_present.get(cls, 0.0) > 0 for cls in signature.forbidden)
        own_score = match_score(mh_present, signature, matching_config)
        competitor = best_competing_match(mh_present, work.work_type, signatures, matching_config)
        competing = (
            own_score < thresholds.r3_low_match_score
            and competitor is not None
            and competitor.score > thresholds.r3_competing_match_score
        )
        if forbidden_present or competing:
            subtype = "forbidden" if forbidden_present else "competing"
            return DayClassification(type="R3_front_mismatch", subtype=subtype, **base)

        expected = {**signature.required, **signature.supporting}
        idle_classes = [
            cls
            for cls in expected
            if utilization.get(cls, 0.0) < thresholds.r2_utilization_max
            and mh_present.get(cls, 0.0) >= thresholds.r2_min_mh_present_per_shift
        ]
        if idle_classes:
            return DayClassification(type="R2_idle", subtype=None, **base)

    return DayClassification(type=None, subtype=None, **base)


def _consecutive_runs(
    classifications: list[DayClassification],
) -> list[tuple[str, date, date, list[DayClassification]]]:
    """Схлопывает подряд идущие сутки одного типа в "пробеги"."""
    runs: list[tuple[str, date, date, list[DayClassification]]] = []
    current_type: str | None = None
    current_days: list[DayClassification] = []
    prev_day: date | None = None

    for c in classifications:
        contiguous = (
            c.type is not None
            and c.type == current_type
            and prev_day is not None
            and (c.day - prev_day).days == 1
        )
        if contiguous:
            current_days.append(c)
        else:
            if current_type is not None:
                runs.append((current_type, current_days[0].day, current_days[-1].day, current_days))
            current_type = c.type
            current_days = [c] if c.type is not None else []
        prev_day = c.day

    if current_type is not None:
        runs.append((current_type, current_days[0].day, current_days[-1].day, current_days))
    return runs


_MIN_RUN_LENGTH = {
    "R0_low_confidence": 1,
    "R4_silence": None,  # подставляется из thresholds
    "R1_resource_gap": None,
    "R2_idle": 1,
    "R3_front_mismatch": 1,
}


# ---------------------------------------------------------------------------
# Формулировки на русском (CLAUDE.md, правило 5)
# ---------------------------------------------------------------------------


def _zone_title(zone_id: str) -> str:
    return zone_id


def _explain_r1(
    work: ScheduleEntry, days: list[DayClassification], zone_id: str
) -> tuple[str, str]:
    last = days[-1]
    key_cls = sorted(work.planned_mh.keys())
    observed_counts = {cls: last.units_seen.get(cls, 0) for cls in key_cls}
    n_days = len(days)
    explanation = (
        f"{n_days}-е сутки подряд на {_zone_title(zone_id)} по работе «{work.name}» "
        f"техники меньше плана: {ru_count_list(observed_counts)}. "
        f"Проверьте фактический состав техники против графика."
    )
    recommendation = (
        f"Вывести на {_zone_title(zone_id)} недостающую технику по «{work.name}» "
        f"либо согласовать сдвиг срока."
    )
    return explanation, recommendation


def _explain_r2(
    days: list[DayClassification], zone_id: str, cost_ref: CostReference
) -> tuple[str, str]:
    total_idle: dict[str, float] = defaultdict(float)
    for d in days:
        for cls, hours in d.mh_idle.items():
            total_idle[cls] += hours
    cost = idle_cost_rub(dict(total_idle), cost_ref)
    counts = {cls: max(d.units_seen.get(cls, 0) for d in days) for cls in total_idle}
    explanation = (
        f"В {_zone_title(zone_id)} простаивает техника: {ru_count_list(counts)}. "
        f"Потери простоя за период — {cost:,.0f} ₽.".replace(",", " ")
    )
    recommendation = (
        f"Проверить причину простоя техники в {_zone_title(zone_id)} "
        f"(ожидание фронта, поломка, отсутствие материала)."
    )
    return explanation, recommendation


def _explain_r3(
    days: list[DayClassification],
    zone_id: str,
    work: ScheduleEntry | None,
    signature: WorkSignature | None,
) -> tuple[str, str]:
    subtype = days[-1].subtype
    work_name = work.name if work else ""
    if subtype == "no_schedule":
        explanation = (
            f"В {_zone_title(zone_id)} зафиксирована активность техники, хотя по графику "
            f"на {days[0].day.isoformat()}-{days[-1].day.isoformat()} работ не запланировано."
        )
    elif subtype == "forbidden":
        forbidden_classes = signature.forbidden if signature else []
        present = {cls: max(d.units_seen.get(cls, 0) for d in days) for cls in forbidden_classes}
        present = {cls: v for cls, v in present.items() if v > 0}
        explanation = (
            f"В {_zone_title(zone_id)} обнаружена техника, не свойственная работе «{work_name}»: "
            f"{ru_count_list(present) if present else 'см. карточку'}."
        )
    else:
        explanation = (
            f"Состав техники в {_zone_title(zone_id)} не похож на плановую работу «{work_name}»: "
            f"похоже на другой вид работ."
        )
    recommendation = (
        f"Сверить фактический состав техники в {_zone_title(zone_id)} "
        f"с графиком и нарядами подрядчика."
    )
    return explanation, recommendation


def _explain_r4(
    work: ScheduleEntry, days: list[DayClassification], zone_id: str
) -> tuple[str, str]:
    n_days = len(days)
    explanation = (
        f"По графику в {_zone_title(zone_id)} должна идти работа «{work.name}», "
        f"но техника не зафиксирована {n_days} суток подряд."
    )
    recommendation = (
        f"Связаться с подрядчиком: подтвердить причину отсутствия техники в {_zone_title(zone_id)}."
    )
    return explanation, recommendation


def _explain_r0(days: list[DayClassification], zone_id: str) -> tuple[str, str]:
    coverage = days[-1].quality.coverage
    explanation = (
        f"Недостаточно данных по {_zone_title(zone_id)} за "
        f"{days[0].day.isoformat()}-{days[-1].day.isoformat()}: низкое качество кадров "
        f"или недостаточное покрытие (coverage={coverage:.2f}). Отклонения не формируются."
    )
    recommendation = (
        f"Проверить камеру (объектив, освещение/ночная подсветка) для {_zone_title(zone_id)}."
    )
    return explanation, recommendation


# ---------------------------------------------------------------------------
# Движок
# ---------------------------------------------------------------------------


@dataclass
class DeviationEngine:
    """Собирает отклонения по всем зонам/суткам из уже готовых `schedule.json`
    и `machine_hours.jsonl`.

    Упрощения (задокументированы, не спрятаны):
    - на зону в момент времени берётся только ПЕРВАЯ покрывающая эту дату
      работа графика (в реальном графике параллельные работы в одной зоне —
      редкость, но если они есть, вторая и последующие сейчас игнорируются);
    - Р3(б) считается без ритма (см. докстринг модуля);
    - пробег короче минимума правила не понижается до другого правила, а
      просто не формирует отклонение по этим суткам.
    """

    signatures: dict[str, WorkSignature]
    matching_config: MatchingConfig
    thresholds: Thresholds
    forecast_config: forecast_mod.ForecastConfig
    spi_thresholds: forecast_mod.SpiThresholds
    cost_ref: CostReference

    @classmethod
    def load(
        cls,
        *,
        work_signatures_path: Path,
        matching_config_path: Path,
        thresholds_path: Path,
        machine_hour_cost_path: Path,
    ) -> DeviationEngine:
        return cls(
            signatures=load_signatures(work_signatures_path),
            matching_config=MatchingConfig.from_yaml(matching_config_path),
            thresholds=Thresholds.from_yaml(thresholds_path),
            forecast_config=forecast_mod.ForecastConfig.from_yaml(thresholds_path),
            spi_thresholds=forecast_mod.SpiThresholds.from_yaml(thresholds_path),
            cost_ref=CostReference.from_json(machine_hour_cost_path),
        )

    def run(
        self,
        *,
        schedule: list[dict],
        machine_hours: list[dict],
        daily_quality: dict[date, DayQuality],
        as_of: datetime,
        frame_uri_lookup: FrameLookup | None = None,
    ) -> list[dict]:
        entries = _load_schedule(schedule)
        mh_index = _index_machine_hours(machine_hours)

        zones = {e.zone_id for e in entries if e.zone_id} | {z for z, _ in mh_index}
        days = sorted(daily_quality)

        deviations: list[dict] = []
        for zone_id in sorted(zones):
            classifications = []
            for day in days:
                work = next(
                    (e for e in entries if e.zone_id == zone_id and e.covers(day)), None
                )
                rows_by_cls = mh_index.get((zone_id, day), {})
                classifications.append(
                    _classify_day(
                        day=day,
                        zone_id=zone_id,
                        work=work,
                        rows_by_cls=rows_by_cls,
                        quality=daily_quality[day],
                        signatures=self.signatures,
                        matching_config=self.matching_config,
                        thresholds=self.thresholds,
                    )
                )

            for rule_type, run_from, run_to, run_days in _consecutive_runs(classifications):
                min_len = self._min_run_length(rule_type)
                if len(run_days) < min_len:
                    continue
                deviations.append(
                    self._build_deviation(
                        zone_id,
                        rule_type,
                        run_from,
                        run_to,
                        run_days,
                        as_of,
                        frame_uri_lookup,
                        mh_index,
                    )
                )

        deviations.sort(key=lambda d: (d["zone_id"], d["period"]["from"]))
        for i, d in enumerate(deviations, start=1):
            d["deviation_id"] = f"D-{i:04d}"
        return deviations

    def _min_run_length(self, rule_type: str) -> int:
        if rule_type == "R4_silence":
            return self.thresholds.r4_min_consecutive_days
        if rule_type == "R1_resource_gap":
            return self.thresholds.r1_min_consecutive_days
        return _MIN_RUN_LENGTH[rule_type]

    def _build_deviation(
        self,
        zone_id: str,
        rule_type: str,
        run_from: date,
        run_to: date,
        run_days: list[DayClassification],
        as_of: datetime,
        frame_uri_lookup: FrameLookup | None,
        mh_index: dict[tuple[str, date], dict[str, dict]],
    ) -> dict:
        work = run_days[-1].work
        last = run_days[-1]

        observed: dict[str, Any] = {}
        expected: dict[str, Any] = {}
        spi = None
        delay_days = None
        idle_cost = 0.0

        if rule_type == "R1_resource_gap":
            explanation, recommendation = _explain_r1(work, run_days, zone_id)
            observed = {cls: last.units_seen.get(cls, 0) for cls in work.planned_mh}
            signature = self.signatures.get(work.work_type) if work.work_type else None
            expected_classes = signature.expected_classes() if signature else {}
            expected = {
                cls: expected_classes[cls] for cls in work.planned_mh if cls in expected_classes
            }
            fc = self._forecast_for(work, run_to, mh_index)
            spi, delay_days = fc.spi, fc.delay_days
            high_delay = (
                delay_days is not None and delay_days > self.thresholds.r1_high_severity_delay_days
            )
            severity = "high" if high_delay else "medium"

        elif rule_type == "R2_idle":
            explanation, recommendation = _explain_r2(run_days, zone_id, self.cost_ref)
            total_idle: dict[str, float] = defaultdict(float)
            for d in run_days:
                for cls, hours in d.mh_idle.items():
                    total_idle[cls] += hours
            observed = {cls: round(h, 2) for cls, h in total_idle.items()}
            idle_cost = idle_cost_rub(dict(total_idle), self.cost_ref)
            severity = (
                "high" if idle_cost > self.thresholds.r2_high_severity_period_cost_rub else "medium"
            )

        elif rule_type == "R3_front_mismatch":
            signature = self.signatures.get(work.work_type) if work and work.work_type else None
            explanation, recommendation = _explain_r3(run_days, zone_id, work, signature)
            is_no_schedule_run = all(d.subtype == "no_schedule" for d in run_days)
            severity = (
                "high"
                if is_no_schedule_run and len(run_days) >= self.thresholds.r3_high_severity_min_days
                else "medium"
            )

        elif rule_type == "R4_silence":
            explanation, recommendation = _explain_r4(work, run_days, zone_id)
            signature = self.signatures.get(work.work_type) if work.work_type else None
            expected = (
                {cls: rng.typical for cls, rng in signature.required.items()} if signature else {}
            )
            severity = "high"

        else:  # R0_low_confidence
            explanation, recommendation = _explain_r0(run_days, zone_id)
            severity = "low"

        frames = frame_uri_lookup(zone_id, run_from, run_to) if frame_uri_lookup else []

        return {
            "deviation_id": "",  # проставляется в run() после сортировки
            "detected_at": as_of.isoformat(),
            "period": {"from": run_from.isoformat(), "to": run_to.isoformat()},
            "work_id": work.work_id if work else None,
            "zone_id": zone_id,
            "type": rule_type,
            "severity": severity,
            "observed": observed,
            "expected": expected,
            "impact": {
                "spi": spi,
                "delay_days": delay_days,
                "idle_cost_rub": round(idle_cost, 2),
            },
            "explanation": explanation,
            "recommendation": recommendation,
            "evidence": {
                "frames": frames,
                "chart": "mh_plan_vs_fact",
                "confidence": round(sum(d.quality.confidence for d in run_days) / len(run_days), 2),
            },
        }

    def _forecast_for(
        self,
        work: ScheduleEntry,
        as_of: date,
        mh_index: dict[tuple[str, date], dict[str, dict]],
    ) -> forecast_mod.ForecastResult:
        planned_total = sum(work.planned_mh.values())
        mh_fact_by_date: dict[date, float] = {}
        day = work.start_plan
        while day <= as_of:
            rows = mh_index.get((work.zone_id, day), {})
            mh_fact_by_date[day] = sum(
                rows[cls]["mh_active"] for cls in work.planned_mh if cls in rows
            )
            day += timedelta(days=1)

        return forecast_mod.forecast_work(
            planned_mh_total=planned_total,
            start_plan=work.start_plan,
            finish_plan=work.finish_plan,
            mh_fact_by_date=mh_fact_by_date,
            as_of=as_of,
            config=self.forecast_config,
            spi_thresholds=self.spi_thresholds,
        )


def write_deviations(records: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False))
            f.write("\n")

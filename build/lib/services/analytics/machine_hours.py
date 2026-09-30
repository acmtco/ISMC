"""Агрегация `detections.jsonl` в суточные машино-часы (docs/02, раздел 4).

`camera_id -> object_id` этот модуль не резолвит (это `objects.json`) —
`object_id` передаётся вызывающей стороной.

Правила:
- `state == "parked"` не учитывается в машино-часах вовсе (не present, не
  active) — техника "на приколе" не в работе (docs/04-metrics.md, раздел 6,
  "Устойчивость": "Припаркованная техника ... не учитывает в МЧ").
- `state == "unknown"` тоже не учитывается — раз система не смогла
  классифицировать состояние, честнее не засчитывать часы, чем гадать
  (docs/01-principles.md, правило 4).
- `quality.score < 0.5` (см. docs/02 §3 "Правило качества") — кадр не
  участвует в расчёте, но учитывается в `coverage`/`confidence` дня.
- Длительность, которую "закрывает" кадр — интервал до следующего кадра,
  ограниченный `max_gap_sec` (иначе редкий ночной кадр приписал бы себе
  весь ночной промежуток).
"""
from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date as Date
from datetime import datetime
from pathlib import Path

QUALITY_SCORE_THRESHOLD = 0.5  # docs/02 §3
COUNTED_STATES = ("active", "idle")  # parked/unknown исключены из МЧ


def _parse_ts(record: dict) -> datetime:
    return datetime.fromisoformat(record["ts"])


def iter_detections(path: Path) -> Iterable[dict]:
    """Пусто, если файла ещё нет — например, камеру ещё ни разу не опрашивали
    (docs/01-principles.md, правило 2: система обязана работать и без данных)."""
    path = Path(path)
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _frame_durations_hours(
    timestamps: list[datetime], nominal_interval_sec: float, max_gap_sec: float
) -> list[float]:
    """Длительность (в часах), которую "отвечает" каждый кадр — интервал до
    следующего кадра, ограниченный `max_gap_sec`. Последнему кадру суток
    приписывается номинальный интервал съёмки."""
    durations = []
    for i, ts in enumerate(timestamps):
        if i + 1 < len(timestamps):
            gap = (timestamps[i + 1] - ts).total_seconds()
            durations.append(min(gap, max_gap_sec) / 3600)
        else:
            durations.append(min(nominal_interval_sec, max_gap_sec) / 3600)
    return durations


@dataclass
class DayQuality:
    coverage: float
    avg_quality_score: float
    confidence: float


@dataclass
class _ClassAccumulator:
    mh_present: float = 0.0
    mh_active: float = 0.0
    track_ids: set = field(default_factory=set)


def _group_by_day(detections: Iterable[dict]) -> dict[Date, list[dict]]:
    by_day: dict[Date, list[dict]] = defaultdict(list)
    for record in sorted(detections, key=lambda r: r["ts"]):
        by_day[_parse_ts(record).date()].append(record)
    return by_day


def daily_quality(
    detections: Iterable[dict],
    *,
    nominal_interval_sec: float = 1200.0,
    max_gap_sec: float = 3600.0,
    quality_threshold: float = QUALITY_SCORE_THRESHOLD,
) -> dict[Date, DayQuality]:
    """Покрытие/уверенность по суткам — по всем кадрам камеры, независимо от
    того, есть ли в них техника (нужно, чтобы отличать R4 "тишина" от
    R0 "не хватает данных", даже если по зоне вообще нет строк в МЧ)."""
    result: dict[Date, DayQuality] = {}
    for day, day_records in _group_by_day(detections).items():
        timestamps = [_parse_ts(r) for r in day_records]
        durations = _frame_durations_hours(timestamps, nominal_interval_sec, max_gap_sec)

        good_duration = 0.0
        total_duration = 0.0
        good_scores = []
        for record, duration in zip(day_records, durations, strict=True):
            total_duration += duration
            score = record["quality"]["score"]
            if score >= quality_threshold:
                good_duration += duration
                good_scores.append(score)

        coverage = good_duration / total_duration if total_duration > 0 else 0.0
        avg_score = sum(good_scores) / len(good_scores) if good_scores else 0.0
        result[day] = DayQuality(
            coverage=round(coverage, 2),
            avg_quality_score=round(avg_score, 2),
            confidence=round(avg_score * coverage, 2),
        )
    return result


def aggregate_machine_hours(
    detections: Iterable[dict],
    *,
    object_id: str,
    nominal_interval_sec: float = 1200.0,
    max_gap_sec: float = 3600.0,
    quality_threshold: float = QUALITY_SCORE_THRESHOLD,
) -> list[dict]:
    """Строки `machine_hours.jsonl` (docs/02, раздел 4) — по одной на
    (дата, зона, класс), где класс наблюдался хотя бы в одном пригодном кадре."""
    output: list[dict] = []
    for day, day_records in sorted(_group_by_day(detections).items()):
        timestamps = [_parse_ts(r) for r in day_records]
        durations = _frame_durations_hours(timestamps, nominal_interval_sec, max_gap_sec)

        acc: dict[tuple[str, str], _ClassAccumulator] = defaultdict(_ClassAccumulator)
        for record, duration in zip(day_records, durations, strict=True):
            if record["quality"]["score"] < quality_threshold:
                continue
            for obj in record["objects"]:
                zone_id = obj.get("zone_id")
                if zone_id is None or obj["state"] not in COUNTED_STATES:
                    continue
                a = acc[(zone_id, obj["cls"])]
                a.mh_present += duration
                if obj["state"] == "active":
                    a.mh_active += duration
                a.track_ids.add(obj["track_id"])

        day_q = daily_quality(
            day_records,
            nominal_interval_sec=nominal_interval_sec,
            max_gap_sec=max_gap_sec,
            quality_threshold=quality_threshold,
        )[day]

        for (zone_id, cls), a in sorted(acc.items()):
            mh_idle = a.mh_present - a.mh_active
            zone_utilization = round(a.mh_active / a.mh_present, 2) if a.mh_present > 0 else 0.0
            output.append(
                {
                    "date": day.isoformat(),
                    "object_id": object_id,
                    "zone_id": zone_id,
                    "cls": cls,
                    "units_seen": len(a.track_ids),
                    "mh_present": round(a.mh_present, 2),
                    "mh_active": round(a.mh_active, 2),
                    "mh_idle": round(mh_idle, 2),
                    "utilization": zone_utilization,
                    "coverage": day_q.coverage,
                    "confidence": day_q.confidence,
                }
            )

    return output


def write_machine_hours(records: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False))
            f.write("\n")

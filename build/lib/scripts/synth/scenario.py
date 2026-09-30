"""Загрузка и валидация сценария синтетического бенчмарка (YAML).

Формат сценария — не часть основного контракта данных (docs/02), это входной
файл только для `make_synthetic.py`. Пример — `data/ref/scenario_demo.yaml`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from scripts.synth.classes import CLASSES


class ScenarioError(ValueError):
    pass


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


@dataclass(frozen=True)
class Zone:
    zone_id: str
    polygon: list[tuple[int, int]]

    def bbox(self) -> tuple[int, int, int, int]:
        xs = [p[0] for p in self.polygon]
        ys = [p[1] for p in self.polygon]
        return min(xs), min(ys), max(xs), max(ys)


@dataclass(frozen=True)
class ClassSpec:
    count: int
    active_ratio: float


@dataclass(frozen=True)
class WorkType:
    work_type: str
    zone_id: str
    classes: dict[str, ClassSpec]
    active_hours: list[tuple[int, int]]

    def is_active_hour(self, hour: int) -> bool:
        return any(start <= hour < end for start, end in self.active_hours)


@dataclass(frozen=True)
class ScheduleEntry:
    work_id: str
    work_type: str
    zone_id: str
    date_from: date
    date_to: date

    def covers(self, day: date) -> bool:
        return self.date_from <= day <= self.date_to


@dataclass(frozen=True)
class InjectedDeviation:
    deviation_id: str
    type: str
    work_id: str
    zone_id: str
    date_from: date
    date_to: date
    severity: str = "high"
    params: dict[str, Any] = field(default_factory=dict)

    def covers(self, day: date) -> bool:
        return self.date_from <= day <= self.date_to


@dataclass(frozen=True)
class WeatherEvent:
    date_from: date
    date_to: date
    condition: str  # rain | fog

    def covers(self, day: date) -> bool:
        return self.date_from <= day <= self.date_to


@dataclass(frozen=True)
class Scenario:
    seed: int
    days: int
    object_id: str
    camera_id: str
    start_date: date
    frame_size: tuple[int, int]
    capture_interval_min: int
    day_start_hour: int
    day_end_hour: int
    night_frames_per_night: int
    zones: list[Zone]
    work_types: dict[str, WorkType]
    schedule: list[ScheduleEntry]
    injected_deviations: list[InjectedDeviation]
    weather: list[WeatherEvent]

    def zone(self, zone_id: str) -> Zone:
        for z in self.zones:
            if z.zone_id == zone_id:
                return z
        raise ScenarioError(f"неизвестная зона: {zone_id!r}")

    def weather_on(self, day: date) -> str | None:
        for w in self.weather:
            if w.covers(day):
                return w.condition
        return None

    def schedule_on(self, day: date) -> list[ScheduleEntry]:
        return [s for s in self.schedule if s.covers(day)]

    def deviations_for(self, work_id: str, day: date) -> list[InjectedDeviation]:
        return [
            d for d in self.injected_deviations if d.work_id == work_id and d.covers(day)
        ]


def _require(mapping: dict, key: str, ctx: str) -> Any:
    if key not in mapping:
        raise ScenarioError(f"в сценарии не хватает поля {key!r} ({ctx})")
    return mapping[key]


def load_scenario(path: Path) -> Scenario:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ScenarioError(f"сценарий {path} должен быть YAML-словарём верхнего уровня")

    zones = [
        Zone(zone_id=z["zone_id"], polygon=[tuple(p) for p in z["polygon"]])
        for z in _require(raw, "zones", "верхний уровень")
    ]
    zone_ids = {z.zone_id for z in zones}

    work_types: dict[str, WorkType] = {}
    for wt in _require(raw, "work_types", "верхний уровень"):
        classes = {}
        for cls, spec in wt["classes"].items():
            if cls not in CLASSES:
                raise ScenarioError(f"неизвестный класс техники: {cls!r}")
            classes[cls] = ClassSpec(
                count=int(spec["count"]), active_ratio=float(spec["active_ratio"])
            )
        if wt["zone_id"] not in zone_ids:
            raise ScenarioError(f"work_type {wt['work_type']!r} ссылается на неизвестную зону")
        work_types[wt["work_type"]] = WorkType(
            work_type=wt["work_type"],
            zone_id=wt["zone_id"],
            classes=classes,
            active_hours=[tuple(h) for h in wt["active_hours"]],
        )

    schedule = [
        ScheduleEntry(
            work_id=s["work_id"],
            work_type=s["work_type"],
            zone_id=s["zone_id"],
            date_from=_parse_date(s["date_from"]),
            date_to=_parse_date(s["date_to"]),
        )
        for s in _require(raw, "schedule", "верхний уровень")
    ]
    for s in schedule:
        if s.work_type not in work_types:
            raise ScenarioError(f"work {s.work_id!r} ссылается на неизвестный work_type")

    injected = [
        InjectedDeviation(
            deviation_id=d["deviation_id"],
            type=d["type"],
            work_id=d["work_id"],
            zone_id=d["zone_id"],
            date_from=_parse_date(d["date_from"]),
            date_to=_parse_date(d["date_to"]),
            severity=d.get("severity", "high"),
            params=d.get("params", {}),
        )
        for d in raw.get("injected_deviations", [])
    ]

    weather = [
        WeatherEvent(
            date_from=_parse_date(w["date_from"]),
            date_to=_parse_date(w["date_to"]),
            condition=w["condition"],
        )
        for w in raw.get("weather", [])
    ]

    frame_size = tuple(raw.get("frame_size", [960, 540]))

    return Scenario(
        seed=int(raw.get("seed", 0)),
        days=int(_require(raw, "days", "верхний уровень")),
        object_id=raw.get("object_id", "OBJ-001"),
        camera_id=raw.get("camera_id", "CAM-01"),
        start_date=_parse_date(_require(raw, "start_date", "верхний уровень")),
        frame_size=(int(frame_size[0]), int(frame_size[1])),
        capture_interval_min=int(raw.get("capture_interval_min", 20)),
        day_start_hour=int(raw.get("day_start_hour", 7)),
        day_end_hour=int(raw.get("day_end_hour", 18)),
        night_frames_per_night=int(raw.get("night_frames_per_night", 2)),
        zones=zones,
        work_types=work_types,
        schedule=schedule,
        injected_deviations=injected,
        weather=weather,
    )

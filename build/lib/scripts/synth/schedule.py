"""Применение сценарных отклонений к плановому составу техники на сутки.

Каждый тип отклонения (см. docs/03-deviation-rules.md) по-своему меняет
"эффективный" состав техники на день для работы `work_id`:

- R1_resource_gap    — снижает `count` ключевых классов (`params.counts`)
- R2_idle            — снижает `active_ratio` при сохранении `count`
                        (`params.active_ratio`)
- R3_front_mismatch  — добавляет технику, не свойственную виду работ
                        (`params.extra_classes`), помечена `forbidden=True`
- R4_silence         — обнуляет `count` всех классов работы (техники нет)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from scripts.synth.scenario import Scenario, ScheduleEntry


@dataclass(frozen=True)
class EffectiveClass:
    count: int
    active_ratio: float
    forbidden: bool = False


@dataclass(frozen=True)
class EffectiveWork:
    work_id: str
    work_type: str
    zone_id: str
    active_hours: list[tuple[int, int]]
    classes: dict[str, EffectiveClass]


def effective_work_for_day(scenario: Scenario, entry: ScheduleEntry, day: date) -> EffectiveWork:
    work_type = scenario.work_types[entry.work_type]
    classes: dict[str, EffectiveClass] = {
        cls: EffectiveClass(count=spec.count, active_ratio=spec.active_ratio)
        for cls, spec in work_type.classes.items()
    }

    for dev in scenario.deviations_for(entry.work_id, day):
        if dev.type == "R1_resource_gap":
            for cls, count in dev.params.get("counts", {}).items():
                base = classes.get(cls, EffectiveClass(0, 0.0))
                classes[cls] = EffectiveClass(count=int(count), active_ratio=base.active_ratio)
        elif dev.type == "R2_idle":
            for cls, ratio in dev.params.get("active_ratio", {}).items():
                base = classes.get(cls, EffectiveClass(0, 0.0))
                classes[cls] = EffectiveClass(count=base.count, active_ratio=float(ratio))
        elif dev.type == "R3_front_mismatch":
            for cls, count in dev.params.get("extra_classes", {}).items():
                classes[cls] = EffectiveClass(count=int(count), active_ratio=0.7, forbidden=True)
        elif dev.type == "R4_silence":
            classes = {cls: EffectiveClass(count=0, active_ratio=0.0) for cls in classes}
        else:
            raise ValueError(f"неизвестный тип отклонения: {dev.type!r}")

    return EffectiveWork(
        work_id=entry.work_id,
        work_type=entry.work_type,
        zone_id=entry.zone_id,
        active_hours=work_type.active_hours,
        classes=classes,
    )


def effective_works_for_day(scenario: Scenario, day: date) -> list[EffectiveWork]:
    return [effective_work_for_day(scenario, entry, day) for entry in scenario.schedule_on(day)]

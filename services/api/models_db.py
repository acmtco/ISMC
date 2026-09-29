"""Таблицы SQLite (SQLModel) — читающая модель поверх файловых контрактов.

Системой записи для `objects.json`/`schedule.json` остаются файлы (docs/01-principles.md,
правило 1 — "контракты данных важнее кода"); в БД они попадают через
`services/api/seed.py` (импорт) и обновляются POST-эндпоинтами. Сырые кадры
(`detections.jsonl`) в БД не хранятся — их слишком много, и они и так лежат
файлом рядом с камерой; здесь — только производные агрегаты
(`machine_hours`, `deviations`), которые нужно быстро отдавать по API.
"""
from __future__ import annotations

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


class ObjectRecord(SQLModel, table=True):
    __tablename__ = "objects"

    object_id: str = Field(primary_key=True)
    name: str
    address: str = ""
    timezone: str = "Europe/Moscow"


class CameraRecord(SQLModel, table=True):
    __tablename__ = "cameras"

    camera_id: str = Field(primary_key=True)
    object_id: str = Field(foreign_key="objects.object_id", index=True)
    title: str = ""
    source_kind: str = "replay"
    source_uri: str = ""
    capture_interval_sec: int = 1200


class ZoneRecord(SQLModel, table=True):
    __tablename__ = "zones"

    zone_id: str = Field(primary_key=True)
    camera_id: str = Field(foreign_key="cameras.camera_id", index=True)
    title: str = ""
    polygon: list = Field(sa_column=Column(JSON))
    area_m2: float | None = None


class ScheduleWorkRecord(SQLModel, table=True):
    __tablename__ = "schedule_works"

    work_id: str = Field(primary_key=True)
    object_id: str = Field(foreign_key="objects.object_id", index=True)
    wbs: str = ""
    name: str
    work_type: str | None = None
    zone_id: str | None = Field(default=None, index=True)
    start_plan: str
    finish_plan: str
    volume_unit: str | None = None
    volume_qty: float | None = None
    planned_mh: dict = Field(default_factory=dict, sa_column=Column(JSON))
    predecessors: list = Field(default_factory=list, sa_column=Column(JSON))


class MachineHourRecord(SQLModel, table=True):
    """Поле контракта `cls` (docs/02 §4) здесь называется `equipment_class`:
    `cls` — зарезервированное имя первого параметра `SQLModel.__new__`, и
    поле с таким же именем ловит `TypeError: got multiple values for
    argument 'cls'` при конструировании с `cls=...` как kwarg. `from_row()`
    переводит контрактный ключ `cls` в `equipment_class`."""

    __tablename__ = "machine_hours"
    __table_args__ = (
        UniqueConstraint(
            "date", "object_id", "zone_id", "equipment_class", name="uq_machine_hour_row"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    date: str = Field(index=True)
    object_id: str = Field(foreign_key="objects.object_id", index=True)
    zone_id: str
    equipment_class: str
    units_seen: int
    mh_present: float
    mh_active: float
    mh_idle: float
    utilization: float
    coverage: float
    confidence: float

    @classmethod
    def from_row(cls, row: dict) -> MachineHourRecord:
        """`row` — строка из `machine_hours.aggregate_machine_hours()` (ключ `cls`)."""
        return cls(
            date=row["date"],
            object_id=row["object_id"],
            zone_id=row["zone_id"],
            equipment_class=row["cls"],
            units_seen=row["units_seen"],
            mh_present=row["mh_present"],
            mh_active=row["mh_active"],
            mh_idle=row["mh_idle"],
            utilization=row["utilization"],
            coverage=row["coverage"],
            confidence=row["confidence"],
        )


class DeviationRecord(SQLModel, table=True):
    __tablename__ = "deviations"

    deviation_id: str = Field(primary_key=True)
    object_id: str = Field(foreign_key="objects.object_id", index=True)
    detected_at: str
    period_from: str
    period_to: str
    work_id: str | None = None
    zone_id: str
    type: str = Field(index=True)
    severity: str
    observed: dict = Field(default_factory=dict, sa_column=Column(JSON))
    expected: dict = Field(default_factory=dict, sa_column=Column(JSON))
    spi: float | None = None
    delay_days: int | None = None
    idle_cost_rub: float = 0.0
    explanation: str
    recommendation: str
    evidence_frames: list = Field(default_factory=list, sa_column=Column(JSON))
    evidence_chart: str = "mh_plan_vs_fact"
    evidence_confidence: float = 0.0
    status: str = "open"  # open | acted — см. POST /api/deviations/{id}/act
    act_generated_at: str | None = None

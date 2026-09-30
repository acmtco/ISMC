"""Доступ к данным для роутеров: SQLite (SQLModel) + файловые контракты.

Системой записи для сырых кадров остаются файлы `detections.jsonl`
(`services/api/config.detections_path`) — в БД попадают только производные
агрегаты (`machine_hours`, `deviations`) и относительно статичная
конфигурация (`objects`, `cameras`, `zones`, `schedule_works`).
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

from sqlmodel import Session, select

from services.analytics.economics import CostReference, utilization
from services.analytics.forecast import ForecastConfig, SpiThresholds, forecast_work
from services.api.models_db import (
    CameraRecord,
    DeviationRecord,
    MachineHourRecord,
    ObjectRecord,
    ScheduleWorkRecord,
    ZoneRecord,
)
from services.api.schemas import (
    CameraOut,
    DeviationOut,
    EconomicsOut,
    EvidenceOut,
    GanttOut,
    ImpactOut,
    LiveStateOut,
    ObjectDetailOut,
    ObjectOut,
    PeriodOut,
    ScheduleImportResult,
    ScheduleWorkOut,
    UtilizationRowOut,
    VolumeOut,
    WorkProgressOut,
    ZoneIn,
    ZoneOut,
    ZonesUpdateResult,
)

# ---------------------------------------------------------------------------
# objects / cameras / zones
# ---------------------------------------------------------------------------


def _zone_out(z: ZoneRecord) -> ZoneOut:
    return ZoneOut(zone_id=z.zone_id, title=z.title, polygon=z.polygon, area_m2=z.area_m2)


def list_objects(session: Session) -> list[ObjectOut]:
    rows = session.exec(select(ObjectRecord)).all()
    return [
        ObjectOut(object_id=r.object_id, name=r.name, address=r.address, timezone=r.timezone)
        for r in rows
    ]


def get_object_detail(session: Session, object_id: str) -> ObjectDetailOut | None:
    obj = session.get(ObjectRecord, object_id)
    if obj is None:
        return None
    cameras = session.exec(select(CameraRecord).where(CameraRecord.object_id == object_id)).all()
    camera_outs = []
    for cam in cameras:
        zones = session.exec(select(ZoneRecord).where(ZoneRecord.camera_id == cam.camera_id)).all()
        camera_outs.append(
            CameraOut(
                camera_id=cam.camera_id,
                title=cam.title,
                source_kind=cam.source_kind,
                source_uri=cam.source_uri,
                capture_interval_sec=cam.capture_interval_sec,
                zones=[_zone_out(z) for z in zones],
            )
        )
    return ObjectDetailOut(
        object_id=obj.object_id,
        name=obj.name,
        address=obj.address,
        timezone=obj.timezone,
        cameras=camera_outs,
    )


def update_zones(
    session: Session, camera_id: str, zones_in: list[ZoneIn]
) -> ZonesUpdateResult | None:
    camera = session.get(CameraRecord, camera_id)
    if camera is None:
        return None
    existing = session.exec(select(ZoneRecord).where(ZoneRecord.camera_id == camera_id)).all()
    for z in existing:
        session.delete(z)

    zones_out = []
    for z in zones_in:
        record = ZoneRecord(
            zone_id=z.zone_id,
            camera_id=camera_id,
            title=z.title,
            polygon=z.polygon,
            area_m2=z.area_m2,
        )
        session.add(record)
        zones_out.append(_zone_out(record))
    session.commit()
    return ZonesUpdateResult(camera_id=camera_id, zones=zones_out)


# ---------------------------------------------------------------------------
# live — последний кадр по каждой камере (detections.jsonl, не БД)
# ---------------------------------------------------------------------------


def _read_last_json_line(path: Path, chunk_size: int = 8192) -> dict | None:
    """Хвостовое чтение без загрузки всего файла — на камеро-сутках детекций
    это может быть заметный файл."""
    if not path.exists():
        return None
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        if file_size == 0:
            return None
        buffer = b""
        pos = file_size
        while pos > 0:
            read_size = min(chunk_size, pos)
            pos -= read_size
            f.seek(pos)
            buffer = f.read(read_size) + buffer
            lines = [ln for ln in buffer.split(b"\n") if ln.strip()]
            if lines and (pos == 0 or len(lines) > 1):
                return json.loads(lines[-1])
    return None


def get_live_state(session: Session, object_id: str) -> LiveStateOut | None:
    from services.api.schemas import DetectionFrameOut

    obj = session.get(ObjectRecord, object_id)
    if obj is None:
        return None
    cameras = session.exec(select(CameraRecord).where(CameraRecord.object_id == object_id)).all()

    from services.api.config import detections_path

    frames = []
    for cam in cameras:
        record = _read_last_json_line(detections_path(cam.camera_id))
        if record:
            frames.append(DetectionFrameOut(**record))
    return LiveStateOut(object_id=object_id, ts=datetime.now(UTC).isoformat(), cameras=frames)


def iter_detections_range(
    path: Path, date_from: date | None, date_to: date | None
) -> Iterator[dict]:
    """Стримит строки `detections.jsonl` в хронологическом порядке, отфильтрованные
    по датам (используется `/replay`, где файл может быть большим)."""
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            ts = datetime.fromisoformat(record["ts"])
            if date_from is not None and ts.date() < date_from:
                continue
            if date_to is not None and ts.date() > date_to:
                continue
            yield record


# ---------------------------------------------------------------------------
# schedule
# ---------------------------------------------------------------------------


def _schedule_work_out(record: ScheduleWorkRecord) -> ScheduleWorkOut:
    return ScheduleWorkOut(
        work_id=record.work_id,
        wbs=record.wbs,
        name=record.name,
        work_type=record.work_type,
        zone_id=record.zone_id,
        start_plan=record.start_plan,
        finish_plan=record.finish_plan,
        volume=VolumeOut(unit=record.volume_unit, qty=record.volume_qty),
        planned_mh=record.planned_mh,
        predecessors=record.predecessors,
    )


def _schedule_works_for(session: Session, object_id: str) -> list[ScheduleWorkRecord]:
    query = select(ScheduleWorkRecord).where(ScheduleWorkRecord.object_id == object_id)
    return list(session.exec(query).all())


def import_schedule(session: Session, object_id: str, entries: list[dict]) -> ScheduleImportResult:
    """Полная замена графика объекта — просто и предсказуемо для повторного импорта."""
    existing = _schedule_works_for(session, object_id)
    for e in existing:
        session.delete(e)

    works_out = []
    for entry in entries:
        volume = entry.get("volume") or {}
        record = ScheduleWorkRecord(
            work_id=entry["work_id"],
            object_id=object_id,
            wbs=entry.get("wbs", ""),
            name=entry["name"],
            work_type=entry.get("work_type"),
            zone_id=entry.get("zone_id"),
            start_plan=entry["start_plan"],
            finish_plan=entry["finish_plan"],
            volume_unit=volume.get("unit"),
            volume_qty=volume.get("qty"),
            planned_mh=entry.get("planned_mh") or {},
            predecessors=entry.get("predecessors") or [],
        )
        session.add(record)
        works_out.append(_schedule_work_out(record))
    session.commit()
    return ScheduleImportResult(object_id=object_id, imported_count=len(entries), works=works_out)


def list_schedule_works(session: Session, object_id: str) -> list[ScheduleWorkRecord]:
    return _schedule_works_for(session, object_id)


# ---------------------------------------------------------------------------
# gantt (work_progress) и economics
# ---------------------------------------------------------------------------


def get_gantt(
    session: Session,
    object_id: str,
    date_from: date,
    date_to: date,
    forecast_cfg: ForecastConfig,
    spi_thresholds_cfg: SpiThresholds,
) -> GanttOut:
    works = list_schedule_works(session, object_id)
    rows: list[WorkProgressOut] = []

    for w in works:
        start = date.fromisoformat(w.start_plan)
        finish = date.fromisoformat(w.finish_plan)
        if finish < date_from or start > date_to:
            continue

        mh_rows = session.exec(
            select(MachineHourRecord).where(
                MachineHourRecord.object_id == object_id,
                MachineHourRecord.zone_id == w.zone_id,
            )
        ).all()
        mh_fact_by_date: dict[date, float] = defaultdict(float)
        for r in mh_rows:
            if r.equipment_class in w.planned_mh:
                mh_fact_by_date[date.fromisoformat(r.date)] += r.mh_active

        planned_total = sum(w.planned_mh.values())
        result = forecast_work(
            planned_mh_total=planned_total,
            start_plan=start,
            finish_plan=finish,
            mh_fact_by_date=dict(mh_fact_by_date),
            as_of=date_to,
            config=forecast_cfg,
            spi_thresholds=spi_thresholds_cfg,
        )
        rows.append(
            WorkProgressOut(
                date=date_to.isoformat(),
                work_id=w.work_id,
                name=w.name,
                mh_plan_to_date=result.mh_plan_to_date,
                mh_fact_to_date=result.mh_fact_to_date,
                spi=result.spi,
                rate_mh_per_day=result.rate_mh_per_day,
                forecast_finish=(
                    result.forecast_finish.isoformat() if result.forecast_finish else None
                ),
                delay_days=result.delay_days,
                status=result.status,
            )
        )

    period = {"from": date_from.isoformat(), "to": date_to.isoformat()}
    return GanttOut(object_id=object_id, period=period, works=rows)


def get_economics(
    session: Session, object_id: str, date_from: date, date_to: date, cost_ref: CostReference
) -> EconomicsOut:
    rows = session.exec(
        select(MachineHourRecord).where(
            MachineHourRecord.object_id == object_id,
            MachineHourRecord.date >= date_from.isoformat(),
            MachineHourRecord.date <= date_to.isoformat(),
        )
    ).all()

    totals: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"mh_present": 0.0, "mh_active": 0.0, "mh_idle": 0.0}
    )
    for r in rows:
        acc = totals[(r.zone_id, r.equipment_class)]
        acc["mh_present"] += r.mh_present
        acc["mh_active"] += r.mh_active
        acc["mh_idle"] += r.mh_idle

    by_class = []
    total_cost = 0.0
    for (zone_id, cls), vals in sorted(totals.items()):
        cost = cost_ref.cost_of(cls, vals["mh_idle"])
        total_cost += cost
        by_class.append(
            UtilizationRowOut(
                zone_id=zone_id,
                cls=cls,
                mh_present=round(vals["mh_present"], 2),
                mh_active=round(vals["mh_active"], 2),
                mh_idle=round(vals["mh_idle"], 2),
                utilization=round(utilization(vals["mh_active"], vals["mh_present"]), 2),
                idle_cost_rub=round(cost, 2),
            )
        )

    return EconomicsOut(
        object_id=object_id,
        period={"from": date_from.isoformat(), "to": date_to.isoformat()},
        total_idle_cost_rub=round(total_cost, 2),
        by_class=by_class,
    )


# ---------------------------------------------------------------------------
# deviations
# ---------------------------------------------------------------------------


def _deviation_out(r: DeviationRecord) -> DeviationOut:
    return DeviationOut(
        deviation_id=r.deviation_id,
        detected_at=r.detected_at,
        period=PeriodOut(**{"from": r.period_from, "to": r.period_to}),
        work_id=r.work_id,
        zone_id=r.zone_id,
        type=r.type,
        severity=r.severity,
        observed=r.observed,
        expected=r.expected,
        impact=ImpactOut(spi=r.spi, delay_days=r.delay_days, idle_cost_rub=r.idle_cost_rub),
        explanation=r.explanation,
        recommendation=r.recommendation,
        evidence=EvidenceOut(
            frames=r.evidence_frames, chart=r.evidence_chart, confidence=r.evidence_confidence
        ),
        status=r.status,
    )


def list_deviations(
    session: Session, object_id: str, type_filter: str | None
) -> list[DeviationOut]:
    query = select(DeviationRecord).where(DeviationRecord.object_id == object_id)
    if type_filter:
        query = query.where(DeviationRecord.type == type_filter)
    rows = session.exec(query.order_by(DeviationRecord.period_from)).all()
    return [_deviation_out(r) for r in rows]


def get_deviation(session: Session, deviation_id: str) -> DeviationOut | None:
    r = session.get(DeviationRecord, deviation_id)
    return _deviation_out(r) if r else None


def get_deviation_record(session: Session, deviation_id: str) -> DeviationRecord | None:
    return session.get(DeviationRecord, deviation_id)


def mark_deviation_acted(session: Session, record: DeviationRecord, generated_at: datetime) -> None:
    record.status = "acted"
    record.act_generated_at = generated_at.isoformat()
    session.add(record)
    session.commit()

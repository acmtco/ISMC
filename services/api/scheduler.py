"""APScheduler: опрос камер в режиме `live` + ночной пересчёт агрегатов.

`HG_MODE=replay` (по умолчанию, безопасно для демо) отключает опрос камер —
данные для replay-камер уже предрассчитаны заранее, крутить их по расписанию
не нужно (CLAUDE.md, правило 3). Опрос применяется только к камерам с
`source.kind` в `rtsp`/`hls`/`folder`, когда система целиком запущена в
режиме `live`.

Ночной пересчёт не зависит от режима: он просто агрегирует то, что уже лежит
в `detections.jsonl` каждой камеры, в `machine_hours`/`deviations` в БД —
если детектору не из чего считать (нет обученных весов, нет новых кадров),
это не ошибка, а нормальное состояние на раннем этапе проекта.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime

import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlmodel import Session, select

from services.analytics.machine_hours import aggregate_machine_hours, daily_quality, iter_detections
from services.api import config
from services.api.db import get_engine
from services.api.models_db import (
    CameraRecord,
    DeviationRecord,
    MachineHourRecord,
    ObjectRecord,
    ScheduleWorkRecord,
)
from services.perception.detect import Detector, DetectorConfig
from services.perception.pipeline import IncrementalPipeline, PipelineConfig
from services.perception.source import open_source
from services.perception.state import StateClassifier
from services.perception.zones import Zone as PerceptionZone
from services.perception.zones import load_zones

logger = logging.getLogger("hronograf.scheduler")

LIVE_SOURCE_KINDS = ("rtsp", "hls", "folder")

# Состояние `IncrementalPipeline` по камере переживает между тиками опроса,
# пока жив процесс API (перезапуск процесса начинает треки заново — см.
# README сервиса).
_pipeline_state: dict[str, IncrementalPipeline] = {}
_last_polled_ts: dict[str, str] = {}


@dataclass
class SchedulerConfig:
    poll_interval_sec: int
    nightly_hour: int
    nightly_minute: int

    @classmethod
    def from_yaml(cls, path) -> SchedulerConfig:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))["scheduler"]
        return cls(
            poll_interval_sec=int(raw["poll_interval_sec"]),
            nightly_hour=int(raw["nightly_hour"]),
            nightly_minute=int(raw["nightly_minute"]),
        )


def _is_live_mode() -> bool:
    return os.environ.get("HG_MODE", "replay") == "live"


def poll_camera(camera: CameraRecord, zones: list[PerceptionZone]) -> int:
    """Прогоняет новые кадры камеры через перцепцию, дописывая её
    `detections.jsonl`. Возвращает число обработанных кадров; 0, если
    опрашивать нечего (или ещё нет весов детектора)."""
    if camera.source_kind not in LIVE_SOURCE_KINDS:
        return 0

    pipeline = _pipeline_state.get(camera.camera_id)
    if pipeline is None:
        try:
            detector_config = DetectorConfig.from_yaml(config.config_dir() / "perception.yaml")
            detector = Detector(detector_config)
            _ = detector.model  # форсируем загрузку весов, чтобы поймать отсутствие файла здесь
        except FileNotFoundError as exc:
            logger.warning("камера %s: пропускаю опрос — %s", camera.camera_id, exc)
            return 0

        from services.perception.track import YoloTracker

        tracker = YoloTracker(detector)
        state_path = config.models_dir() / "state.joblib"
        try:
            state_classifier = StateClassifier.load(state_path)
        except FileNotFoundError:
            logger.warning(
                "камера %s: пропускаю опрос — нет обученной модели состояния (%s)",
                camera.camera_id,
                state_path,
            )
            return 0

        pipeline_config = PipelineConfig(camera_id=camera.camera_id, zones=zones)
        pipeline = IncrementalPipeline(pipeline_config, tracker, state_classifier)
        _pipeline_state[camera.camera_id] = pipeline

    source = open_source({"kind": camera.source_kind, "uri": camera.source_uri})
    out_path = config.detections_path(camera.camera_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    last_ts = _last_polled_ts.get(camera.camera_id)
    processed = 0
    with out_path.open("a", encoding="utf-8") as f:
        for frame in source.iter_frames():
            ts_iso = frame.ts.isoformat()
            if last_ts is not None and ts_iso <= last_ts:
                continue
            record = pipeline.process_frame(frame)
            f.write(json.dumps(record, ensure_ascii=False))
            f.write("\n")
            _last_polled_ts[camera.camera_id] = ts_iso
            processed += 1

    return processed


def poll_cameras_job() -> None:
    if not _is_live_mode():
        return
    with Session(get_engine()) as session:
        cameras = session.exec(select(CameraRecord)).all()
        for camera in cameras:
            try:
                zones_json = load_zones(config.objects_json_path(), camera.camera_id)
            except (FileNotFoundError, ValueError):
                zones_json = []
            try:
                count = poll_camera(camera, zones_json)
                if count:
                    logger.info("камера %s: добавлено кадров %d", camera.camera_id, count)
            except Exception:  # noqa: BLE001 — один сбой камеры не должен ронять весь опрос
                logger.exception("камера %s: ошибка опроса", camera.camera_id)


def recompute_object(session: Session, object_id: str, camera_ids: list[str]) -> int:
    """Пересчитывает `machine_hours`/`deviations` объекта из уже накопленных
    `detections.jsonl`. Возвращает число сформированных отклонений."""
    all_detections: list[dict] = []
    for camera_id in camera_ids:
        path = config.detections_path(camera_id)
        all_detections.extend(iter_detections(path))

    if not all_detections:
        return 0

    mh_rows = aggregate_machine_hours(all_detections, object_id=object_id)
    dq = daily_quality(all_detections)

    mh_query = select(MachineHourRecord).where(MachineHourRecord.object_id == object_id)
    for row in session.exec(mh_query).all():
        session.delete(row)
    # Сброс удалений до вставки обязателен: у `machine_hours` уникальный ключ
    # (дата, объект, зона, класс), и при повторном пересчёте новая строка
    # совпадает со старой. Без flush автосброс выполнит INSERT раньше DELETE
    # и упрётся в constraint — то есть ночной пересчёт падал бы каждый раз,
    # кроме самого первого.
    session.flush()
    for row in mh_rows:
        session.add(MachineHourRecord.from_row(row))

    schedule_query = select(ScheduleWorkRecord).where(ScheduleWorkRecord.object_id == object_id)
    schedule = session.exec(schedule_query).all()
    schedule_dicts = [
        {
            "work_id": s.work_id,
            "name": s.name,
            "work_type": s.work_type,
            "zone_id": s.zone_id,
            "start_plan": s.start_plan,
            "finish_plan": s.finish_plan,
            "planned_mh": s.planned_mh,
        }
        for s in schedule
    ]

    engine = config.deviation_engine()
    deviations = engine.run(
        schedule=schedule_dicts,
        machine_hours=mh_rows,
        daily_quality=dq,
        as_of=datetime.now(UTC),
    )

    zone_to_object = {s.zone_id: object_id for s in schedule if s.zone_id}
    dev_query = select(DeviationRecord).where(DeviationRecord.object_id == object_id)
    for row in session.exec(dev_query).all():
        session.delete(row)
    # Та же причина, что и у `machine_hours` выше: `deviation_id` детерминирован
    # (тип + зона + период), поэтому при повторном пересчёте он совпадает с уже
    # существующим первичным ключом.
    session.flush()
    for dev in deviations:
        session.add(
            DeviationRecord(
                deviation_id=dev["deviation_id"],
                object_id=zone_to_object.get(dev["zone_id"], object_id),
                detected_at=dev["detected_at"],
                period_from=dev["period"]["from"],
                period_to=dev["period"]["to"],
                work_id=dev["work_id"],
                zone_id=dev["zone_id"],
                type=dev["type"],
                severity=dev["severity"],
                observed=dev["observed"],
                expected=dev["expected"],
                spi=dev["impact"]["spi"],
                delay_days=dev["impact"]["delay_days"],
                idle_cost_rub=dev["impact"]["idle_cost_rub"],
                explanation=dev["explanation"],
                recommendation=dev["recommendation"],
                evidence_frames=dev["evidence"]["frames"],
                evidence_chart=dev["evidence"]["chart"],
                evidence_confidence=dev["evidence"]["confidence"],
            )
        )
    session.commit()
    return len(deviations)


def nightly_recompute_job() -> None:
    with Session(get_engine()) as session:
        objects = session.exec(select(ObjectRecord)).all()
        for obj in objects:
            camera_query = select(CameraRecord).where(CameraRecord.object_id == obj.object_id)
            camera_ids = [c.camera_id for c in session.exec(camera_query).all()]
            try:
                n = recompute_object(session, obj.object_id, camera_ids)
                logger.info("пересчёт %s: %d отклонений", obj.object_id, n)
            except Exception:  # noqa: BLE001 — сбой одного объекта не должен ронять пересчёт остальных
                logger.exception("пересчёт %s: ошибка", obj.object_id)


def create_scheduler(scheduler_config: SchedulerConfig) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(
        poll_cameras_job,
        IntervalTrigger(seconds=scheduler_config.poll_interval_sec),
        id="poll_cameras",
        replace_existing=True,
    )
    scheduler.add_job(
        nightly_recompute_job,
        CronTrigger(hour=scheduler_config.nightly_hour, minute=scheduler_config.nightly_minute),
        id="nightly_recompute",
        replace_existing=True,
    )
    return scheduler

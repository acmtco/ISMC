"""Наполняет БД из файловых конфигов при старте — идемпотентно (upsert).

Источник истины остаётся файловым (`objects.json`, `schedule.json` —
docs/01-principles.md, правило 1); БД — читающая проекция поверх них для быстрой отдачи
по API. Если файлов нет (чистый чекаут без данных), сидинг молча пропускается
— система обязана запускаться и на пустых данных (docs/01-principles.md, правило 2).
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlmodel import Session

from services.api.models_db import CameraRecord, ObjectRecord, ZoneRecord
from services.api.repositories import import_schedule


def seed_objects(session: Session, objects_json_path: Path) -> list[str]:
    """Возвращает список `object_id`, загруженных из файла (для дальнейшего
    сидинга их графиков)."""
    if not objects_json_path.exists():
        return []

    raw = json.loads(objects_json_path.read_text(encoding="utf-8"))
    entries = raw if isinstance(raw, list) else [raw]
    object_ids = []

    for entry in entries:
        object_id = entry["object_id"]
        object_ids.append(object_id)

        obj = session.get(ObjectRecord, object_id)
        obj = obj or ObjectRecord(object_id=object_id, name=object_id)
        obj.name = entry.get("name", object_id)
        obj.address = entry.get("address", "")
        obj.timezone = entry.get("timezone", "Europe/Moscow")
        session.add(obj)

        for cam in entry.get("cameras", []):
            camera_id = cam["camera_id"]
            source = cam.get("source", {})
            camera = session.get(CameraRecord, camera_id) or CameraRecord(
                camera_id=camera_id, object_id=object_id
            )
            camera.object_id = object_id
            camera.title = cam.get("title", "")
            camera.source_kind = source.get("kind", "replay")
            camera.source_uri = source.get("uri", "")
            camera.capture_interval_sec = int(cam.get("capture_interval_sec", 1200))
            session.add(camera)

            for zone in cam.get("zones", []):
                zone_id = zone["zone_id"]
                zone_record = session.get(ZoneRecord, zone_id) or ZoneRecord(
                    zone_id=zone_id, camera_id=camera_id, polygon=zone["polygon"]
                )
                zone_record.camera_id = camera_id
                zone_record.title = zone.get("title", zone_id)
                zone_record.polygon = zone["polygon"]
                zone_record.area_m2 = zone.get("area_m2")
                session.add(zone_record)

    session.commit()
    return object_ids


def seed_schedule(session: Session, schedule_json_path: Path, object_id: str) -> None:
    if not schedule_json_path.exists():
        return
    entries = json.loads(schedule_json_path.read_text(encoding="utf-8"))
    import_schedule(session, object_id, entries)


def seed_all(session: Session, *, objects_json_path: Path, schedule_json_path: Path) -> None:
    object_ids = seed_objects(session, objects_json_path)
    for object_id in object_ids:
        seed_schedule(session, schedule_json_path, object_id)

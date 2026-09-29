import json

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from services.api import config
from services.api.db import get_engine, init_db
from services.api.main import app
from services.api.models_db import (
    DeviationRecord,
    MachineHourRecord,
    ObjectRecord,
    ScheduleWorkRecord,
)
from services.api.scheduler import (
    SchedulerConfig,
    _is_live_mode,
    nightly_recompute_job,
    poll_cameras_job,
    recompute_object,
)

QUALITY = {"blur": 0.1, "night": False, "occlusion": 0.0, "score": 0.9}


def _write_detections(path, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _detection_record(ts: str, state: str = "active") -> dict:
    return {
        "camera_id": "CAM-01",
        "ts": ts,
        "frame_uri": "f.jpg",
        "quality": QUALITY,
        "objects": [
            {
                "track_id": 1,
                "cls": "excavator",
                "conf": 0.9,
                "bbox": [0, 0, 10, 10],
                "zone_id": "Z-PIT",
                "state": state,
                "state_conf": 0.9,
                "features": {"centroid_mad": 0.0, "area_mad": 0.0, "flow_mag": 0.0, "hsv_var": 0.0},
            }
        ],
    }


def test_is_live_mode_reads_hg_mode_env(monkeypatch):
    monkeypatch.delenv("HG_MODE", raising=False)
    assert _is_live_mode() is False
    monkeypatch.setenv("HG_MODE", "live")
    assert _is_live_mode() is True
    monkeypatch.setenv("HG_MODE", "replay")
    assert _is_live_mode() is False


def test_poll_cameras_job_is_noop_in_replay_mode(monkeypatch):
    monkeypatch.setenv("HG_MODE", "replay")
    poll_cameras_job()  # не должно ничего трогать (и тем более не должно падать)


def test_scheduler_config_from_yaml():
    from pathlib import Path

    cfg = SchedulerConfig.from_yaml(Path("config/api.yaml"))
    assert cfg.poll_interval_sec > 0
    assert 0 <= cfg.nightly_hour <= 23


def test_recompute_object_creates_machine_hours_and_deviation(api_env):
    init_db()
    with Session(get_engine()) as session:
        session.add(ObjectRecord(object_id="OBJ-TEST", name="Тест"))
        session.add(
            ScheduleWorkRecord(
                work_id="W-001",
                object_id="OBJ-TEST",
                name="Разработка котлована",
                work_type="earthworks_excavation",
                zone_id="Z-PIT",
                start_plan="2026-09-01",
                finish_plan="2026-09-10",
                planned_mh={"excavator": 20.0},
            )
        )
        session.commit()

    # 6 суток подряд по 20 минут активности — сильно ниже плана (2ч/сут) -> R1
    records = [_detection_record(f"2026-09-0{i + 1}T07:00:00+03:00") for i in range(6)]
    _write_detections(config.detections_path("CAM-01"), records)

    with Session(get_engine()) as session:
        n = recompute_object(session, "OBJ-TEST", ["CAM-01"])
        assert n >= 1

        mh_rows = session.exec(
            select(MachineHourRecord).where(MachineHourRecord.object_id == "OBJ-TEST")
        ).all()
        assert len(mh_rows) > 0
        assert mh_rows[0].equipment_class == "excavator"

        deviations = session.exec(
            select(DeviationRecord).where(DeviationRecord.object_id == "OBJ-TEST")
        ).all()
        assert any(d.type == "R1_resource_gap" for d in deviations)


def test_recompute_object_is_idempotent(api_env):
    """Ночной пересчёт выполняется каждые сутки по одному и тому же объекту.
    У `machine_hours` уникальный ключ (дата, объект, зона, класс), а
    `deviation_id` детерминирован — поэтому второй прогон обязан заместить
    строки первого, а не упасть на constraint и не удвоить их."""
    init_db()
    with Session(get_engine()) as session:
        session.add(ObjectRecord(object_id="OBJ-TWICE", name="Дважды"))
        session.add(
            ScheduleWorkRecord(
                work_id="W-001",
                object_id="OBJ-TWICE",
                name="Разработка котлована",
                work_type="earthworks_excavation",
                zone_id="Z-PIT",
                start_plan="2026-09-01",
                finish_plan="2026-09-10",
                planned_mh={"excavator": 20.0},
            )
        )
        session.commit()

    records = [_detection_record(f"2026-09-0{i + 1}T07:00:00+03:00") for i in range(6)]
    _write_detections(config.detections_path("CAM-01"), records)

    with Session(get_engine()) as session:
        first = recompute_object(session, "OBJ-TWICE", ["CAM-01"])
        mh_after_first = len(
            session.exec(
                select(MachineHourRecord).where(MachineHourRecord.object_id == "OBJ-TWICE")
            ).all()
        )

    with Session(get_engine()) as session:
        second = recompute_object(session, "OBJ-TWICE", ["CAM-01"])
        mh_after_second = session.exec(
            select(MachineHourRecord).where(MachineHourRecord.object_id == "OBJ-TWICE")
        ).all()
        deviations = session.exec(
            select(DeviationRecord).where(DeviationRecord.object_id == "OBJ-TWICE")
        ).all()

    assert second == first
    assert len(mh_after_second) == mh_after_first
    assert len({d.deviation_id for d in deviations}) == len(deviations)


def test_recompute_object_returns_zero_without_detections(api_env):
    init_db()
    with Session(get_engine()) as session:
        session.add(ObjectRecord(object_id="OBJ-EMPTY", name="Пусто"))
        session.commit()
        n = recompute_object(session, "OBJ-EMPTY", ["CAM-DOES-NOT-EXIST"])
    assert n == 0


def test_nightly_recompute_job_processes_seeded_object(api_env):
    with TestClient(app):
        pass  # только чтобы сработал lifespan: init_db() + seed_all() из data/ref/objects.json

    records = [_detection_record(f"2026-09-0{i + 1}T07:00:00+03:00") for i in range(3)]
    _write_detections(config.detections_path("CAM-01"), records)

    nightly_recompute_job()  # не должно падать даже без графика/весов детектора

    with Session(get_engine()) as session:
        mh_rows = session.exec(
            select(MachineHourRecord).where(MachineHourRecord.object_id == "OBJ-001")
        ).all()
    assert len(mh_rows) > 0

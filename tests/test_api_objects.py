import json
from datetime import timedelta, timezone

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from services.api import config
from services.api.db import get_engine
from services.api.main import app
from services.api.models_db import MachineHourRecord

MSK = timezone(timedelta(hours=3))


def test_list_objects_returns_seeded_object(api_env):
    with TestClient(app) as client:
        r = client.get("/api/objects")
    assert r.status_code == 200
    [obj] = r.json()
    assert obj["object_id"] == "OBJ-001"
    assert obj["name"] == "Жилой комплекс, корпус 3"


def test_get_object_detail_includes_cameras_and_zones(api_env):
    with TestClient(app) as client:
        r = client.get("/api/objects/OBJ-001")
    assert r.status_code == 200
    detail = r.json()
    assert detail["cameras"][0]["camera_id"] == "CAM-01"
    zone_ids = {z["zone_id"] for z in detail["cameras"][0]["zones"]}
    assert zone_ids == {"Z-PIT", "Z-FRAME"}


def test_get_unknown_object_is_404(api_env):
    with TestClient(app) as client:
        r = client.get("/api/objects/NOPE")
    assert r.status_code == 404


def test_live_state_empty_when_no_detections_yet(api_env):
    with TestClient(app) as client:
        r = client.get("/api/objects/OBJ-001/live")
    assert r.status_code == 200
    assert r.json()["cameras"] == []


def test_live_state_returns_last_frame(api_env):
    detections_path = config.detections_path("CAM-01")
    detections_path.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "camera_id": "CAM-01",
            "ts": "2026-09-20T07:00:00+03:00",
            "frame_uri": "x1.jpg",
            "quality": {"blur": 0.1, "night": False, "occlusion": 0.0, "score": 0.9},
            "objects": [],
        },
        {
            "camera_id": "CAM-01",
            "ts": "2026-09-20T07:20:00+03:00",
            "frame_uri": "x2.jpg",
            "quality": {"blur": 0.1, "night": False, "occlusion": 0.0, "score": 0.9},
            "objects": [],
        },
    ]
    with detections_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with TestClient(app) as client:
        r = client.get("/api/objects/OBJ-001/live")
    assert r.status_code == 200
    [camera] = r.json()["cameras"]
    assert camera["frame_uri"] == "x2.jpg"  # последняя строка, не первая


def test_import_schedule_xlsx_and_read_gantt(api_env, tmp_path):
    xlsx_path = tmp_path / "schedule.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Наименование работ", "Начало", "Окончание", "Объем", "Ед.изм", "Зона"])
    ws.append(["Разработка котлована", "2026-09-01", "2026-09-10", 12000, "м3", "Z-PIT"])
    wb.save(xlsx_path)

    with TestClient(app) as client:
        with xlsx_path.open("rb") as f:
            r = client.post(
                "/api/objects/OBJ-001/schedule",
                files={
                    "file": (
                        "schedule.xlsx",
                        f,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            )
        assert r.status_code == 200
        result = r.json()
        assert result["imported_count"] == 1
        assert result["works"][0]["work_type"] == "earthworks_excavation"
        assert result["works"][0]["planned_mh"]["excavator"] == pytest.approx(12000 / 66.0, abs=0.01)

        r = client.get("/api/objects/OBJ-001/gantt", params={"from": "2026-09-01", "to": "2026-09-05"})
    assert r.status_code == 200
    gantt = r.json()
    assert len(gantt["works"]) == 1
    assert gantt["works"][0]["work_id"] == "W-001"


def test_import_schedule_rejects_unknown_extension(api_env, tmp_path):
    bogus = tmp_path / "schedule.csv"
    bogus.write_text("a,b,c")
    with TestClient(app) as client:
        with bogus.open("rb") as f:
            r = client.post(
                "/api/objects/OBJ-001/schedule", files={"file": ("schedule.csv", f, "text/csv")}
            )
    assert r.status_code == 400


def test_economics_aggregates_machine_hours(api_env):
    with TestClient(app) as client:
        with Session(get_engine()) as session:
            session.add(
                MachineHourRecord.from_row(
                    {
                        "date": "2026-09-05",
                        "object_id": "OBJ-001",
                        "zone_id": "Z-PIT",
                        "cls": "excavator",
                        "units_seen": 1,
                        "mh_present": 8.0,
                        "mh_active": 2.0,
                        "mh_idle": 6.0,
                        "utilization": 0.25,
                        "coverage": 1.0,
                        "confidence": 0.95,
                    }
                )
            )
            session.commit()

        r = client.get(
            "/api/objects/OBJ-001/economics", params={"from": "2026-09-01", "to": "2026-09-10"}
        )
    assert r.status_code == 200
    economics = r.json()
    assert economics["by_class"][0]["mh_idle"] == 6.0
    assert economics["total_idle_cost_rub"] == 6.0 * 2500

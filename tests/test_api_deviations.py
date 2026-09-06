from fastapi.testclient import TestClient
from sqlmodel import Session

from services.api.db import get_engine
from services.api.main import app
from services.api.models_db import DeviationRecord


def _seed_deviation(**overrides) -> None:
    defaults = dict(
        deviation_id="D-0001",
        object_id="OBJ-001",
        detected_at="2026-09-20T19:05:00+03:00",
        period_from="2026-09-18",
        period_to="2026-09-20",
        work_id="W-014",
        zone_id="Z-PIT",
        type="R1_resource_gap",
        severity="high",
        observed={"excavator": 1, "dump_truck": 2},
        expected={"excavator": 2, "dump_truck": 5},
        spi=0.67,
        delay_days=7,
        idle_cost_rub=0.0,
        explanation="Третьи сутки на Z-PIT работает 1 экскаватор из 2 плановых.",
        recommendation="Вывести на Z-PIT недостающую технику.",
        evidence_frames=["data/replay/CAM-01/20260920T101000.jpg"],
        evidence_chart="mh_plan_vs_fact",
        evidence_confidence=0.88,
    )
    defaults.update(overrides)
    with Session(get_engine()) as session:
        session.add(DeviationRecord(**defaults))
        session.commit()


def test_list_deviations_for_object(api_env):
    with TestClient(app) as client:
        _seed_deviation()
        r = client.get("/api/objects/OBJ-001/deviations")
    assert r.status_code == 200
    [dev] = r.json()
    assert dev["deviation_id"] == "D-0001"
    assert dev["period"] == {"from": "2026-09-18", "to": "2026-09-20"}
    assert dev["impact"]["delay_days"] == 7
    assert dev["status"] == "open"


def test_list_deviations_filters_by_type(api_env):
    with TestClient(app) as client:
        _seed_deviation(deviation_id="D-0001", type="R1_resource_gap")
        _seed_deviation(deviation_id="D-0002", type="R2_idle", zone_id="Z-PIT")
        r = client.get("/api/objects/OBJ-001/deviations", params={"type": "R2_idle"})
    assert [d["deviation_id"] for d in r.json()] == ["D-0002"]


def test_get_deviation_detail(api_env):
    with TestClient(app) as client:
        _seed_deviation()
        r = client.get("/api/deviations/D-0001")
    assert r.status_code == 200
    assert r.json()["explanation"].startswith("Третьи сутки")


def test_get_unknown_deviation_is_404(api_env):
    with TestClient(app) as client:
        r = client.get("/api/deviations/NOPE")
    assert r.status_code == 404


def test_create_act_returns_pdf_and_marks_acted(api_env):
    with TestClient(app) as client:
        _seed_deviation()
        r = client.post("/api/deviations/D-0001/act")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content.startswith(b"%PDF")

        r = client.get("/api/deviations/D-0001")
    assert r.json()["status"] == "acted"


def test_create_act_unknown_deviation_is_404(api_env):
    with TestClient(app) as client:
        r = client.post("/api/deviations/NOPE/act")
    assert r.status_code == 404

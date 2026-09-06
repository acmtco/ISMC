import json

from fastapi.testclient import TestClient

from services.api import config
from services.api.main import app

QUALITY = {"blur": 0.1, "night": False, "occlusion": 0.0, "score": 0.9}


def _write_detections(path, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _frame(ts: str, frame_uri: str) -> dict:
    return {"camera_id": "CAM-01", "ts": ts, "frame_uri": frame_uri, "quality": QUALITY, "objects": []}


def test_replay_streams_frames_in_chronological_order(api_env):
    records = [
        _frame(f"2026-09-20T07:0{i}:00+03:00", f"f{i}.jpg") for i in (2, 0, 1)  # намеренно не по порядку
    ]
    with TestClient(app) as client:
        _write_detections(config.detections_path("CAM-01"), records)
        # огромная скорость — паузы между кадрами практически нулевые, тест быстрый
        r = client.get("/api/objects/OBJ-001/replay", params={"speed": 1_000_000})

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")

    data_lines = [line for line in r.text.splitlines() if line.startswith("data:")]
    assert len(data_lines) == 4  # 3 кадра + событие end
    frame_uris = [json.loads(line[len("data: ") :])["frame_uri"] for line in data_lines[:3]]
    assert frame_uris == ["f0.jpg", "f1.jpg", "f2.jpg"]


def test_replay_filters_by_date_range(api_env):
    records = [
        _frame("2026-09-18T07:00:00+03:00", "old.jpg"),
        _frame("2026-09-20T07:00:00+03:00", "new.jpg"),
    ]
    with TestClient(app) as client:
        _write_detections(config.detections_path("CAM-01"), records)
        r = client.get(
            "/api/objects/OBJ-001/replay", params={"from": "2026-09-19", "speed": 1_000_000}
        )

    assert "old.jpg" not in r.text
    assert "new.jpg" in r.text


def test_replay_empty_when_no_detections(api_env):
    with TestClient(app) as client:
        r = client.get("/api/objects/OBJ-001/replay", params={"speed": 1_000_000})
    data_lines = [line for line in r.text.splitlines() if line.startswith("data:")]
    assert len(data_lines) == 1  # только событие end


def test_replay_unknown_object_is_404(api_env):
    with TestClient(app) as client:
        r = client.get("/api/objects/NOPE/replay")
    assert r.status_code == 404

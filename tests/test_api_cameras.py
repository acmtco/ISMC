from fastapi.testclient import TestClient

from services.api.main import app


def test_update_zones_replaces_existing(api_env):
    payload = [
        {"zone_id": "Z-NEW", "title": "Новая зона", "polygon": [[0, 0], [10, 0], [10, 10]]},
    ]
    with TestClient(app) as client:
        r = client.post("/api/cameras/CAM-01/zones", json=payload)
        assert r.status_code == 200
        result = r.json()
        assert result["camera_id"] == "CAM-01"
        assert [z["zone_id"] for z in result["zones"]] == ["Z-NEW"]

        r = client.get("/api/objects/OBJ-001")
    zones = r.json()["cameras"][0]["zones"]
    assert [z["zone_id"] for z in zones] == ["Z-NEW"]  # старые Z-PIT/Z-FRAME заменены


def test_update_zones_unknown_camera_is_404(api_env):
    with TestClient(app) as client:
        r = client.post("/api/cameras/NOPE/zones", json=[])
    assert r.status_code == 404

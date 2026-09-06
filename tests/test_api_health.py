from fastapi.testclient import TestClient

from services.api.main import app


def test_health(api_env):
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_openapi_has_russian_metadata(api_env):
    with TestClient(app) as client:
        r = client.get("/openapi.json")
    schema = r.json()
    assert schema["info"]["title"] == "Хронограф API"
    assert "машино-часы" in schema["info"]["description"]
    tag_names = {t["name"] for t in schema["tags"]}
    assert {"Объекты", "Отклонения", "Камеры", "Машина времени"} <= tag_names

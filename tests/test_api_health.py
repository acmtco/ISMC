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


def test_spa_routes_fall_back_to_index(tmp_path, monkeypatch):
    """Адреса экранов существуют только внутри интерфейса: на диске файла
    `/deviations` нет. Если отдавать по ним 404, ломаются прямая ссылка на
    экран и обновление страницы — самый заметный для жюри дефект."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>Хронограф</title>", encoding="utf-8")
    monkeypatch.setenv("HG_WEB_DIST", str(dist))

    import importlib

    from services.api import main as main_module

    reloaded = importlib.reload(main_module)
    with TestClient(reloaded.app) as client:
        assert client.get("/deviations").status_code == 200
        assert "Хронограф" in client.get("/gantt").text
        # Пути API подменяться не должны.
        assert client.get("/health").json() == {"status": "ok"}

    monkeypatch.delenv("HG_WEB_DIST", raising=False)
    importlib.reload(main_module)

"""Проверяет, что каркас репозитория собирается: пакеты импортируются,
FastAPI-приложение создаётся. Бизнес-логику не тестирует.
"""


def test_perception_importable() -> None:
    import services.perception  # noqa: F401


def test_analytics_importable() -> None:
    import services.analytics  # noqa: F401


def test_api_app_created() -> None:
    from services.api.main import app

    assert app.title == "Хронограф API"

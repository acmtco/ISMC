"""FastAPI-приложение "Хронограф" (docs/02-data-contract.md, раздел 7).

OpenAPI-схема (`/docs`) — на русском: показывается экспертам на питче
(docs/05-pitch.md, "показать её эксперту на питче").
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from services.api import config
from services.api.db import get_engine, init_db
from services.api.routers import cameras, deviations, objects, replay
from services.api.scheduler import SchedulerConfig, create_scheduler
from services.api.seed import seed_all

logging.basicConfig(level=os.environ.get("HG_LOG_LEVEL", "INFO"))

TAGS_METADATA = [
    {
        "name": "Объекты",
        "description": "Объекты строительства: камеры, зоны, текущее состояние, "
        "график (план vs факт), экономика.",
    },
    {
        "name": "Отклонения",
        "description": "Лента отклонений (Р0-Р4) и карточки с доказательствами и рекомендацией.",
    },
    {"name": "Камеры", "description": "Разметка зон выполнения работ на кадре камеры."},
    {
        "name": "Машина времени",
        "description": "Проигрывание предрассчитанного периода истории через Server-Sent Events.",
    },
    {"name": "Служебное", "description": "Проверка живости сервиса."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with Session(get_engine()) as session:
        seed_all(
            session,
            objects_json_path=config.objects_json_path(),
            schedule_json_path=config.ref_dir() / "schedule.json",
        )

    scheduler_config = SchedulerConfig.from_yaml(config.config_dir() / "api.yaml")
    scheduler = create_scheduler(scheduler_config)
    scheduler.start()
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="Хронограф API",
    description=(
        "Превращаем видеопоток строительной площадки в машино-часы и "
        "автоматически сверяем их с календарным графиком — типизированные "
        "отклонения с доказательствами и прогнозом срыва срока.\n\n"
        "Контракты данных — `docs/02-data-contract.md`, "
        "правила отклонений — `docs/03-deviation-rules.md`."
    ),
    version="0.1.0",
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get(
        "HG_CORS_ORIGINS", f"http://localhost:{os.environ.get('HG_WEB_PORT', '5173')}"
    ).split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(objects.router)
app.include_router(deviations.router)
app.include_router(cameras.router)
app.include_router(replay.router)


@app.get("/health", tags=["Служебное"], summary="Проверка живости сервиса")
def health() -> dict[str, str]:
    return {"status": "ok"}

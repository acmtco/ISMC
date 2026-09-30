"""FastAPI-приложение "Хронограф" (docs/02-data-contract.md, раздел 7).

OpenAPI-схема (`/docs`) — на русском: показывается экспертам на питче
(docs/05-pitch.md, "показать её эксперту на питче").
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select
from starlette.exceptions import HTTPException as StarletteHTTPException

from services.api import config
from services.api.db import get_engine, init_db
from services.api.models_db import CameraRecord, MachineHourRecord, ObjectRecord
from services.api.routers import cameras, deviations, objects, replay
from services.api.scheduler import SchedulerConfig, create_scheduler, recompute_object
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


def _bootstrap_demo(session: Session) -> None:
    """Первый расчёт машино-часов и отклонений при пустой базе.

    Нужно там, где файловая система эфемерна (контейнер, PaaS): база
    создаётся заново при каждом деплое, и без этого шага сервис поднялся бы
    с пустыми экранами. Считается тем же кодом, что и ночной пересчёт, из
    уже накопленного `detections.jsonl` — никакие числа не подставляются.

    Шаг идемпотентен: если строки уже есть, пересчёт не запускается.
    """
    if session.exec(select(MachineHourRecord).limit(1)).first() is not None:
        return
    objects = session.exec(select(ObjectRecord)).all()
    for obj in objects:
        camera_ids = [
            c.camera_id
            for c in session.exec(
                select(CameraRecord).where(CameraRecord.object_id == obj.object_id)
            ).all()
        ]
        if not any(config.detections_path(cid).exists() for cid in camera_ids):
            continue
        n = recompute_object(session, obj.object_id, camera_ids)
        logging.getLogger("hronograf.api").info(
            "стартовый пересчёт %s: %d отклонений", obj.object_id, n
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with Session(get_engine()) as session:
        seed_all(
            session,
            objects_json_path=config.objects_json_path(),
            schedule_json_path=config.ref_dir() / "schedule.json",
        )
        _bootstrap_demo(session)

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


class SpaStaticFiles(StaticFiles):
    """Статика с возвратом `index.html` на неизвестных путях.

    Маршрутизация интерфейса живёт в браузере: адреса вроде `/deviations`
    существуют только внутри приложения, файла с таким именем на диске нет.
    Штатный `StaticFiles` отвечает на них 404, и тогда прямая ссылка на
    экран или обновление страницы ломаются. Отдаём `index.html`, приложение
    само разберёт адрес.

    Флаг `html=True` этого не делает: он подставляет `index.html` только для
    каталогов, а не для произвольных путей.
    """

    async def get_response(self, path: str, scope):
        # `StaticFiles` не возвращает ответ с кодом 404, а выбрасывает
        # исключение, поэтому подменяем именно его.
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


def _mount_web(application: FastAPI) -> None:
    """Раздача собранного интерфейса тем же процессом, если сборка рядом.

    В разработке фронтенд поднимает свой dev-сервер на другом порту, и этой
    папки нет — монтирование просто пропускается. В контейнере сборка лежит
    в `web/dist`, и тогда интерфейс и API отвечают с одного адреса: не нужны
    ни второй сервис, ни настройка CORS.

    Монтируется последним, иначе перехватил бы пути API.
    """
    dist = Path(os.environ.get("HG_WEB_DIST", "web/dist"))
    if not (dist / "index.html").exists():
        return
    application.mount("/", SpaStaticFiles(directory=dist, html=True), name="web")
    logging.getLogger("hronograf.api").info("интерфейс раздаётся из %s", dist)


_mount_web(app)

"""GET /api/objects/{id}/replay — "машина времени" через SSE.

Проигрывает уже накопленные (предрассчитанные) детекции камер объекта за
период, с паузами между кадрами, пропорциональными реальному интервалу их
съёмки, делённому на `speed` — чем выше `speed`, тем быстрее прокрутка
(docs/05-pitch.md: "прокручиваю тридцать суток строительства за десять
секунд").
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from starlette.responses import StreamingResponse

from services.api import config, repositories
from services.api.db import get_session
from services.api.models_db import CameraRecord, ObjectRecord

router = APIRouter(prefix="/api/objects", tags=["Машина времени"])

# Верхняя граница реальной паузы между событиями — иначе редкий разрыв между
# кадрами (например, ночь) "подвесил" бы поток на реальные минуты даже на
# небольшой скорости. Это защита UX, не бизнес-правило — здесь, не в конфиге.
MAX_EVENT_DELAY_SEC = 5.0


async def _sse_stream(
    camera_ids: list[str], date_from: date | None, date_to: date | None, speed: float
) -> AsyncIterator[str]:
    records = []
    for camera_id in camera_ids:
        path = config.detections_path(camera_id)
        records.extend(repositories.iter_detections_range(path, date_from, date_to))
    records.sort(key=lambda r: r["ts"])

    prev_ts: datetime | None = None
    for record in records:
        ts = datetime.fromisoformat(record["ts"])
        if prev_ts is not None and speed > 0:
            delay = (ts - prev_ts).total_seconds() / speed
            if delay > 0:
                await asyncio.sleep(min(delay, MAX_EVENT_DELAY_SEC))
        prev_ts = ts
        yield f"event: frame\ndata: {json.dumps(record, ensure_ascii=False)}\n\n"

    yield "event: end\ndata: {}\n\n"


@router.get(
    "/{object_id}/replay",
    summary="Машина времени: проигрывание предрассчитанного периода",
    description=(
        "Server-Sent Events: кадры с детекциями объекта за период `from`-`to`, "
        "воспроизведённые с ускорением `speed` (во сколько раз быстрее реального "
        "времени; по умолчанию — `HG_REPLAY_SPEED`). Каждое событие `frame` — "
        "один кадр по контракту `detections.jsonl`; в конце — событие `end`."
    ),
)
def replay_endpoint(
    object_id: str,
    speed: float | None = Query(default=None, gt=0, description="Ускорение воспроизведения"),
    date_from: date | None = Query(default=None, alias="from", description="Начало периода"),
    date_to: date | None = Query(default=None, alias="to", description="Конец периода"),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    obj = session.get(ObjectRecord, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"объект {object_id!r} не найден")

    cameras = session.exec(select(CameraRecord).where(CameraRecord.object_id == object_id)).all()
    camera_ids = [c.camera_id for c in cameras]
    effective_speed = speed if speed is not None else config.replay_speed_default()

    return StreamingResponse(
        _sse_stream(camera_ids, date_from, date_to, effective_speed),
        media_type="text/event-stream",
    )

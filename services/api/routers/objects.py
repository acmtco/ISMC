"""GET /api/objects, .../live, .../gantt, .../economics, POST .../schedule
(docs/02-data-contract.md, раздел 7)."""
from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlmodel import Session

from services.analytics import schedule_io
from services.api import config, repositories
from services.api.db import get_session
from services.api.schemas import (
    EconomicsOut,
    GanttOut,
    LiveStateOut,
    ObjectDetailOut,
    ObjectOut,
    ScheduleImportResult,
)

router = APIRouter(prefix="/api/objects", tags=["Объекты"])


@router.get(
    "",
    response_model=list[ObjectOut],
    summary="Список объектов строительства",
    description="Все объекты, зарегистрированные в системе.",
)
def list_objects_endpoint(session: Session = Depends(get_session)) -> list[ObjectOut]:
    return repositories.list_objects(session)


@router.get(
    "/{object_id}",
    response_model=ObjectDetailOut,
    summary="Карточка объекта",
    description="Объект вместе с камерами и зонами выполнения работ.",
)
def get_object_endpoint(object_id: str, session: Session = Depends(get_session)) -> ObjectDetailOut:
    result = repositories.get_object_detail(session, object_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"объект {object_id!r} не найден")
    return result


@router.get(
    "/{object_id}/live",
    response_model=LiveStateOut,
    summary="Текущее состояние площадки",
    description="Последний кадр по каждой камере объекта: детекции, зоны, состояние техники.",
)
def get_live_endpoint(object_id: str, session: Session = Depends(get_session)) -> LiveStateOut:
    result = repositories.get_live_state(session, object_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"объект {object_id!r} не найден")
    return result


@router.get(
    "/{object_id}/gantt",
    response_model=GanttOut,
    summary="План vs факт по работам",
    description="Диаграмма Ганта: плановые и фактические машино-часы, прогноз завершения, SPI.",
)
def get_gantt_endpoint(
    object_id: str,
    date_from: date = Query(alias="from", description="Начало периода"),
    date_to: date = Query(alias="to", description="Конец периода (на эту дату считается прогресс)"),
    session: Session = Depends(get_session),
) -> GanttOut:
    return repositories.get_gantt(
        session, object_id, date_from, date_to, config.forecast_config(), config.spi_thresholds()
    )


@router.get(
    "/{object_id}/economics",
    response_model=EconomicsOut,
    summary="Экономика: КИТ, простои, рубли",
    description="Коэффициент использования техники и стоимость простоя за период.",
)
def get_economics_endpoint(
    object_id: str,
    date_from: date = Query(alias="from", description="Начало периода"),
    date_to: date = Query(alias="to", description="Конец периода"),
    session: Session = Depends(get_session),
) -> EconomicsOut:
    return repositories.get_economics(
        session, object_id, date_from, date_to, config.cost_reference()
    )


@router.post(
    "/{object_id}/schedule",
    response_model=ScheduleImportResult,
    summary="Импорт графика (XLSX / MS Project XML)",
    description="Заменяет график объекта данными из загруженного файла — "
    "нечёткое сопоставление колонок, см. `services/analytics/schedule_io.py`.",
)
async def import_schedule_endpoint(
    object_id: str, file: UploadFile, session: Session = Depends(get_session)
) -> ScheduleImportResult:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".xlsx", ".xml"):
        raise HTTPException(status_code=400, detail=f"неизвестный формат файла: {suffix!r}")

    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        productivity = config.productivity_ref()
        if suffix == ".xlsx":
            entries = schedule_io.import_xlsx(tmp_path, productivity=productivity)
        else:
            entries = schedule_io.import_msp_xml(tmp_path, productivity=productivity)
    finally:
        tmp_path.unlink(missing_ok=True)

    return repositories.import_schedule(session, object_id, entries)

"""GET .../deviations, GET /api/deviations/{id}, POST /api/deviations/{id}/act
(docs/02-data-contract.md, раздел 7)."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlmodel import Session

from services.api import repositories
from services.api.act import render_act_pdf
from services.api.db import get_session
from services.api.schemas import DeviationOut

router = APIRouter(tags=["Отклонения"])


@router.get(
    "/api/objects/{object_id}/deviations",
    response_model=list[DeviationOut],
    summary="Лента отклонений",
    description="Отклонения по объекту, опционально отфильтрованные по типу (R0-R4).",
)
def list_deviations_endpoint(
    object_id: str,
    type: str | None = Query(default=None, description="Фильтр по типу отклонения"),
    session: Session = Depends(get_session),
) -> list[DeviationOut]:
    return repositories.list_deviations(session, object_id, type)


@router.get(
    "/api/deviations/{deviation_id}",
    response_model=DeviationOut,
    summary="Карточка отклонения с доказательствами",
    description="Числа плана и факта, формулировка на русском, рекомендация, кадры-улики.",
)
def get_deviation_endpoint(
    deviation_id: str, session: Session = Depends(get_session)
) -> DeviationOut:
    result = repositories.get_deviation(session, deviation_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"отклонение {deviation_id!r} не найдено")
    return result


@router.post(
    "/api/deviations/{deviation_id}/act",
    summary="Сформировать PDF-акт",
    description="Формирует PDF-акт по отклонению для передачи подрядчику; "
    "отклонение помечается как `acted`.",
    responses={200: {"content": {"application/pdf": {}}}},
)
def create_act_endpoint(deviation_id: str, session: Session = Depends(get_session)) -> Response:
    record = repositories.get_deviation_record(session, deviation_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"отклонение {deviation_id!r} не найдено")

    generated_at = datetime.now(UTC)
    pdf_bytes = render_act_pdf(record, generated_at)
    repositories.mark_deviation_acted(session, record, generated_at)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="act-{deviation_id}.pdf"'},
    )

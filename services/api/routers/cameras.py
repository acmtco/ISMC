"""POST /api/cameras/{id}/zones (docs/02-data-contract.md, раздел 7)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from services.api import repositories
from services.api.db import get_session
from services.api.schemas import ZoneIn, ZonesUpdateResult

router = APIRouter(prefix="/api/cameras", tags=["Камеры"])


@router.post(
    "/{camera_id}/zones",
    response_model=ZonesUpdateResult,
    summary="Сохранить полигоны зон",
    description="Полная замена разметки зон выполнения работ для камеры.",
)
def update_zones_endpoint(
    camera_id: str, zones: list[ZoneIn], session: Session = Depends(get_session)
) -> ZonesUpdateResult:
    result = repositories.update_zones(session, camera_id, zones)
    if result is None:
        raise HTTPException(status_code=404, detail=f"камера {camera_id!r} не найдена")
    return result

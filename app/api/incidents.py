from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models import Incident, Service
from app.schemas import IncidentOut

router = APIRouter(prefix="/api/incidents", tags=["Incidents"])


@router.get("", response_model=List[IncidentOut])
async def list_incidents(
    status: Optional[str] = Query(None, description="Фильтр по статусу (OPEN, RESOLVED)"),
    service_id: Optional[int] = Query(None, description="Фильтр по ID сервиса"),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Список инцидентов недоступности сервисов."""
    stmt = (
        select(Incident)
        .options(joinedload(Incident.service))
        .order_by(desc(Incident.started_at))
    )

    if status and status != "ALL":
        stmt = stmt.where(Incident.status == status)
    if service_id is not None:
        stmt = stmt.where(Incident.service_id == service_id)

    stmt = stmt.limit(limit)
    res = await db.execute(stmt)
    incidents = res.scalars().all()

    output = []
    for inc in incidents:
        s_name = inc.service.name if inc.service else "Удаленный сервис"
        output.append(
            IncidentOut(
                id=inc.id,
                service_id=inc.service_id,
                service_name=s_name,
                status=inc.status,
                started_at=inc.started_at,
                resolved_at=inc.resolved_at,
                duration_seconds=inc.duration_seconds,
                cause=inc.cause,
            )
        )
    return output

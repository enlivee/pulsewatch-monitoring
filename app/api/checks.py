from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import CheckResult
from app.schemas import CheckResultOut

router = APIRouter(prefix="/api/checks", tags=["Checks"])


@router.get("", response_model=List[CheckResultOut])
async def list_checks(
    service_id: Optional[int] = Query(None, description="Фильтр по ID сервиса"),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """История проверок доступности сервисов."""
    stmt = select(CheckResult)
    if service_id is not None:
        stmt = stmt.where(CheckResult.service_id == service_id)
    stmt = stmt.order_by(desc(CheckResult.timestamp)).limit(limit)

    res = await db.execute(stmt)
    checks = res.scalars().all()
    return [CheckResultOut.model_validate(c) for c in checks]

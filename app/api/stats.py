from datetime import datetime, timedelta
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Service, CheckResult
from app.schemas import DashboardStats
from app.stats import get_dashboard_summary

router = APIRouter(prefix="/api/stats", tags=["Stats"])


@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    """Сводные глобальные показатели для карточек дашборда."""
    return await get_dashboard_summary(db)


@router.get("/service/{service_id}/chart")
async def get_service_chart_data(
    service_id: int,
    limit: int = Query(60, ge=10, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Данные временного ряда (время отклика и статус) для графиков Chart.js."""
    service = await db.get(Service, service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Сервис не найден")

    # Получаем последние N проверок (в обратном порядке, чтобы развернуть хронологически)
    stmt = (
        select(CheckResult)
        .where(CheckResult.service_id == service_id)
        .order_by(desc(CheckResult.timestamp))
        .limit(limit)
    )
    res = await db.execute(stmt)
    checks = list(reversed(res.scalars().all()))

    labels = []
    response_times = []
    statuses = []

    for c in checks:
        labels.append(c.timestamp.strftime("%H:%M:%S"))
        response_times.append(c.response_time_ms if c.response_time_ms is not None else 0)
        statuses.append(c.status)

    return {
        "service_id": service_id,
        "service_name": service.name,
        "labels": labels,
        "response_times": response_times,
        "statuses": statuses,
    }

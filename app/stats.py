from datetime import datetime, timedelta
from typing import Dict, Any, List
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Service, CheckResult, Incident
from app.schemas import ServiceStats, DashboardStats


async def calculate_uptime_percentage(
    session: AsyncSession, service_id: int, since: datetime
) -> float:
    """Расчёт процента доступности (Uptime %) с момента `since`."""
    stmt = (
        select(
            func.count(CheckResult.id).label("total"),
            func.sum(
                case(
                    (CheckResult.is_success == True, 1),
                    else_=0
                )
            ).label("successful")
        )
        .where(
            and_(
                CheckResult.service_id == service_id,
                CheckResult.timestamp >= since
            )
        )
    )
    result = await session.execute(stmt)
    row = result.first()

    if not row or not row.total or row.total == 0:
        return 100.0  # По умолчанию, если проверок еще нет

    total = row.total
    successful = row.successful or 0
    return round((successful / total) * 100.0, 2)


async def get_service_stats(session: AsyncSession, service_id: int) -> ServiceStats:
    """Детальная статистика сервиса за разные периоды."""
    now = datetime.utcnow()
    since_24h = now - timedelta(hours=24)
    since_7d = now - timedelta(days=7)
    since_30d = now - timedelta(days=30)

    uptime_24h = await calculate_uptime_percentage(session, service_id, since_24h)
    uptime_7d = await calculate_uptime_percentage(session, service_id, since_7d)
    uptime_30d = await calculate_uptime_percentage(session, service_id, since_30d)

    # Метрики задержки (Latency) за 24 часа для успешных проверок
    lat_stmt = (
        select(
            func.avg(CheckResult.response_time_ms).label("avg_lat"),
            func.min(CheckResult.response_time_ms).label("min_lat"),
            func.max(CheckResult.response_time_ms).label("max_lat"),
            func.count(CheckResult.id).label("total_count"),
        )
        .where(
            and_(
                CheckResult.service_id == service_id,
                CheckResult.timestamp >= since_24h,
                CheckResult.response_time_ms.isnot(None),
                CheckResult.is_success == True
            )
        )
    )
    lat_res = await session.execute(lat_stmt)
    lat_row = lat_res.first()

    avg_lat = round(lat_row.avg_lat, 2) if lat_row and lat_row.avg_lat else None
    min_lat = round(lat_row.min_lat, 2) if lat_row and lat_row.min_lat else None
    max_lat = round(lat_row.max_lat, 2) if lat_row and lat_row.max_lat else None

    # Общее число проверок за все время
    total_checks_stmt = select(func.count(CheckResult.id)).where(CheckResult.service_id == service_id)
    total_checks_res = await session.execute(total_checks_stmt)
    total_checks = total_checks_res.scalar_one() or 0

    # Количество инцидентов
    incidents_stmt = select(func.count(Incident.id)).where(Incident.service_id == service_id)
    incidents_res = await session.execute(incidents_stmt)
    incident_count = incidents_res.scalar_one() or 0

    return ServiceStats(
        uptime_24h=uptime_24h,
        uptime_7d=uptime_7d,
        uptime_30d=uptime_30d,
        avg_latency_ms=avg_lat,
        min_latency_ms=min_lat,
        max_latency_ms=max_lat,
        total_checks=total_checks,
        incident_count=incident_count
    )


async def get_dashboard_summary(session: AsyncSession) -> DashboardStats:
    """Глобальная сводка по всем сервисам для главного дашборда."""
    services_res = await session.execute(select(Service))
    services = services_res.scalars().all()

    total_services = len(services)
    up_count = 0
    down_count = 0
    degraded_count = 0
    paused_count = 0

    uptime_sum = 0.0
    latency_sum = 0.0
    latency_count = 0

    now = datetime.utcnow()
    since_24h = now - timedelta(hours=24)

    for s in services:
        if not s.is_active:
            paused_count += 1
        elif s.current_status == "UP":
            up_count += 1
        elif s.current_status == "DOWN":
            down_count += 1
        elif s.current_status == "DEGRADED":
            degraded_count += 1

        if s.is_active and s.last_response_time_ms is not None:
            latency_sum += s.last_response_time_ms
            latency_count += 1

        # Uptime 24h
        u = await calculate_uptime_percentage(session, s.id, since_24h)
        uptime_sum += u

    avg_uptime = round(uptime_sum / total_services, 2) if total_services > 0 else 100.0
    avg_latency = round(latency_sum / latency_count, 2) if latency_count > 0 else None

    # Активные инциденты
    active_inc_res = await session.execute(
        select(func.count(Incident.id)).where(Incident.status == "OPEN")
    )
    active_incidents = active_inc_res.scalar_one() or 0

    return DashboardStats(
        total_services=total_services,
        up_count=up_count,
        down_count=down_count,
        degraded_count=degraded_count,
        paused_count=paused_count,
        avg_uptime_24h=avg_uptime,
        avg_response_time_ms=avg_latency,
        active_incidents_count=active_incidents
    )

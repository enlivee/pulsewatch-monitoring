import csv
import io
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Service, Incident
from app.stats import get_service_stats

router = APIRouter(prefix="/api/export", tags=["Export"])


@router.get("/csv")
async def export_services_csv(db: AsyncSession = Depends(get_db)):
    """Экспорт отчета о доступности и производительности сервисов в формате CSV."""
    result = await db.execute(select(Service).order_by(Service.name))
    services = result.scalars().all()

    output = io.StringIO()
    # Write UTF-8 BOM so Excel opens Cyrillic characters properly
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")

    # Headers
    writer.writerow([
        "ID",
        "Название сервиса",
        "URL / Хост",
        "Тип проверки",
        "Категория",
        "Текущий статус",
        "Uptime 24ч (%)",
        "Uptime 7д (%)",
        "Uptime 30д (%)",
        "Среднее время отклика (мс)",
        "Последний статус-код",
        "Последняя ошибка",
        "Время последней проверки (UTC)"
    ])

    for s in services:
        stats = await get_service_stats(db, s.id)
        writer.writerow([
            s.id,
            s.name,
            s.url,
            s.check_type,
            s.category,
            s.current_status if s.is_active else "PAUSED",
            stats.uptime_24h,
            stats.uptime_7d,
            stats.uptime_30d,
            stats.avg_latency_ms if stats.avg_latency_ms is not None else "N/A",
            s.last_status_code or "",
            s.last_error_message or "",
            s.last_check_at.strftime("%Y-%m-%d %H:%M:%S") if s.last_check_at else "Нет данных"
        ])

    output.seek(0)
    filename = f"pulsewatch_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/json")
async def export_services_json(db: AsyncSession = Depends(get_db)):
    """Полный экспорт отчета о состоянии инфраструктуры в JSON."""
    result = await db.execute(select(Service).order_by(Service.name))
    services = result.scalars().all()

    services_data = []
    for s in services:
        stats = await get_service_stats(db, s.id)
        services_data.append({
            "id": s.id,
            "name": s.name,
            "url": s.url,
            "check_type": s.check_type,
            "category": s.category,
            "status": s.current_status if s.is_active else "PAUSED",
            "is_active": s.is_active,
            "last_check_at": s.last_check_at.isoformat() if s.last_check_at else None,
            "last_response_time_ms": s.last_response_time_ms,
            "last_status_code": s.last_status_code,
            "last_error_message": s.last_error_message,
            "stats": {
                "uptime_24h": stats.uptime_24h,
                "uptime_7d": stats.uptime_7d,
                "uptime_30d": stats.uptime_30d,
                "avg_latency_ms": stats.avg_latency_ms,
                "min_latency_ms": stats.min_latency_ms,
                "max_latency_ms": stats.max_latency_ms,
                "total_checks": stats.total_checks,
                "incident_count": stats.incident_count
            }
        })

    incidents_res = await db.execute(select(Incident).order_by(Incident.started_at.desc()).limit(100))
    incidents = incidents_res.scalars().all()
    incidents_data = [
        {
            "id": inc.id,
            "service_id": inc.service_id,
            "status": inc.status,
            "started_at": inc.started_at.isoformat() if inc.started_at else None,
            "resolved_at": inc.resolved_at.isoformat() if inc.resolved_at else None,
            "duration_seconds": inc.duration_seconds,
            "cause": inc.cause
        }
        for inc in incidents
    ]

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "total_services": len(services),
        "services": services_data,
        "recent_incidents": incidents_data
    }

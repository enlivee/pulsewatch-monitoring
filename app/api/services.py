from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Service, CheckResult, Incident
from app.schemas import (
    ServiceCreate,
    ServiceUpdate,
    ServiceOut,
    ServiceDetailOut,
    CheckResultOut,
    IncidentOut,
)
from app.stats import get_service_stats, calculate_uptime_percentage
from app.monitor.scheduler import scheduler

router = APIRouter(prefix="/api/services", tags=["Services"])


@router.get("", response_model=List[ServiceOut])
async def list_services(
    search: Optional[str] = Query(None, description="Поиск по имени или URL"),
    category: Optional[str] = Query(None, description="Фильтр по категории"),
    status: Optional[str] = Query(None, description="Фильтр по статусу (UP, DOWN, DEGRADED, PAUSED)"),
    db: AsyncSession = Depends(get_db),
):
    """Получение списка сервисов с фильтрацией и расчётом 24ч аптайма."""
    query = select(Service)

    conditions = []
    if search:
        search_pattern = f"%{search}%"
        conditions.append(
            or_(
                Service.name.ilike(search_pattern),
                Service.url.ilike(search_pattern),
                Service.tags.ilike(search_pattern),
            )
        )
    if category and category != "ALL":
        conditions.append(Service.category == category)
    if status and status != "ALL":
        if status == "PAUSED":
            conditions.append(Service.is_active == False)
        else:
            conditions.append(and_(Service.current_status == status, Service.is_active == True))

    if conditions:
        query = query.where(and_(*conditions))

    query = query.order_by(Service.name)
    result = await db.execute(query)
    services = result.scalars().all()

    now = datetime.utcnow()
    since_24h = now - timedelta(hours=24)

    service_list = []
    for s in services:
        uptime = await calculate_uptime_percentage(db, s.id, since_24h)
        s_out = ServiceOut.model_validate(s)
        s_out.uptime_24h = uptime
        service_list.append(s_out)

    return service_list


@router.post("", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
async def create_service(payload: ServiceCreate, db: AsyncSession = Depends(get_db)):
    """Регистрация нового контролируемого сервиса."""
    service = Service(
        name=payload.name.strip(),
        url=payload.url.strip(),
        description=payload.description,
        check_type=payload.check_type,
        method=payload.method,
        expected_status=payload.expected_status,
        timeout_seconds=payload.timeout_seconds,
        interval_seconds=payload.interval_seconds,
        keyword=payload.keyword,
        category=payload.category,
        tags=payload.tags,
        is_active=payload.is_active,
        current_status="PENDING",
    )
    db.add(service)
    await db.commit()
    await db.refresh(service)

    # Запускаем немедленную первоначальную проверку сервиса
    await scheduler.run_service_check(service.id)
    await db.refresh(service)

    s_out = ServiceOut.model_validate(service)
    s_out.uptime_24h = 100.0
    return s_out


@router.get("/{service_id}", response_model=ServiceDetailOut)
async def get_service_detail(service_id: int, db: AsyncSession = Depends(get_db)):
    """Просмотр детальной информации о сервисе, статистике и последних проверках."""
    service = await db.get(Service, service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Сервис не найден")

    # Статистика
    stats = await get_service_stats(db, service_id)

    # Последние 50 проверок
    checks_stmt = (
        select(CheckResult)
        .where(CheckResult.service_id == service_id)
        .order_by(desc(CheckResult.timestamp))
        .limit(50)
    )
    checks_res = await db.execute(checks_stmt)
    recent_checks = [CheckResultOut.model_validate(c) for c in checks_res.scalars().all()]

    # Последние инциденты
    incidents_stmt = (
        select(Incident)
        .where(Incident.service_id == service_id)
        .order_by(desc(Incident.started_at))
        .limit(10)
    )
    incidents_res = await db.execute(incidents_stmt)
    recent_incidents = [
        IncidentOut(
            id=inc.id,
            service_id=inc.service_id,
            service_name=service.name,
            status=inc.status,
            started_at=inc.started_at,
            resolved_at=inc.resolved_at,
            duration_seconds=inc.duration_seconds,
            cause=inc.cause,
        )
        for inc in incidents_res.scalars().all()
    ]

    s_out = ServiceDetailOut(
        id=service.id,
        name=service.name,
        url=service.url,
        description=service.description,
        check_type=service.check_type,
        method=service.method,
        expected_status=service.expected_status,
        timeout_seconds=service.timeout_seconds,
        interval_seconds=service.interval_seconds,
        keyword=service.keyword,
        category=service.category,
        tags=service.tags,
        is_active=service.is_active,
        current_status=service.current_status,
        last_check_at=service.last_check_at,
        last_response_time_ms=service.last_response_time_ms,
        last_status_code=service.last_status_code,
        last_error_message=service.last_error_message,
        created_at=service.created_at,
        updated_at=service.updated_at,
        uptime_24h=stats.uptime_24h,
        uptime_7d=stats.uptime_7d,
        uptime_30d=stats.uptime_30d,
        stats=stats,
        recent_checks=recent_checks,
        recent_incidents=recent_incidents,
    )
    return s_out


@router.put("/{service_id}", response_model=ServiceOut)
async def update_service(
    service_id: int, payload: ServiceUpdate, db: AsyncSession = Depends(get_db)
):
    """Обновление параметров контролируемого сервиса."""
    service = await db.get(Service, service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Сервис не найден")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(service, field, val)

    service.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(service)

    return ServiceOut.model_validate(service)


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(service_id: int, db: AsyncSession = Depends(get_db)):
    """Удаление сервиса и всей истории его проверок."""
    service = await db.get(Service, service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Сервис не найден")

    await db.delete(service)
    await db.commit()
    return None


@router.post("/{service_id}/pause", response_model=ServiceOut)
async def pause_service(service_id: int, db: AsyncSession = Depends(get_db)):
    """Приостановка мониторинга сервиса."""
    service = await db.get(Service, service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Сервис не найден")

    service.is_active = False
    service.current_status = "PAUSED"
    await db.commit()
    await db.refresh(service)
    return ServiceOut.model_validate(service)


@router.post("/{service_id}/resume", response_model=ServiceOut)
async def resume_service(service_id: int, db: AsyncSession = Depends(get_db)):
    """Возобновление мониторинга сервиса."""
    service = await db.get(Service, service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Сервис не найден")

    service.is_active = True
    await db.commit()

    # Сразу запускаем проверку
    await scheduler.run_service_check(service.id)
    await db.refresh(service)
    return ServiceOut.model_validate(service)


@router.post("/{service_id}/check")
async def trigger_manual_check(service_id: int, db: AsyncSession = Depends(get_db)):
    """Ручной запуск немедленной проверки сервиса."""
    service = await db.get(Service, service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Сервис не найден")

    outcome = await scheduler.run_service_check(service_id)
    await db.refresh(service)
    return {
        "status": service.current_status,
        "response_time_ms": service.last_response_time_ms,
        "status_code": service.last_status_code,
        "error_message": service.last_error_message,
        "last_check_at": service.last_check_at,
    }

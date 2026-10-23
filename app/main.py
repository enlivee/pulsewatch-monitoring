import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import APP_NAME, APP_DESCRIPTION, APP_VERSION
from app.database import init_db, get_db, AsyncSessionLocal
from app.models import Service, Incident
from app.monitor.scheduler import scheduler
from app.stats import get_dashboard_summary, get_service_stats, calculate_uptime_percentage
from app.api.services import router as services_router
from app.api.checks import router as checks_router
from app.api.incidents import router as incidents_router
from app.api.stats import router as stats_router
from app.api.export import router as export_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("pulsewatch")

BASE_DIR = Path(__file__).resolve().parent


async def seed_demo_services_if_empty():
    """Добавление демонстрационных сервисов при первом запуске."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Service))
        existing = result.scalars().first()
        if not existing:
            logger.info("База данных пуста. Заполнение стартовыми демонстрационными сервисами...")
            demo_services = [
                Service(
                    name="GitHub Public API",
                    url="https://api.github.com",
                    description="Публичный API сервиса GitHub",
                    check_type="HTTPS",
                    method="GET",
                    expected_status=200,
                    interval_seconds=20,
                    category="API",
                    is_active=True
                ),
                Service(
                    name="Официальный сайт Python",
                    url="https://www.python.org",
                    description="Портал языка программирования Python",
                    check_type="HTTPS",
                    method="GET",
                    expected_status=200,
                    interval_seconds=30,
                    category="Веб-сайты",
                    is_active=True
                ),
                Service(
                    name="Яндекс Поиск",
                    url="https://ya.ru",
                    description="Стартовая страница Яндекса",
                    check_type="HTTPS",
                    method="GET",
                    expected_status=200,
                    interval_seconds=25,
                    category="Веб-сайты",
                    is_active=True
                ),
                Service(
                    name="Cloudflare DNS (TCP:53)",
                    url="1.1.1.1:53",
                    description="Проверка TCP соединения с публичным DNS Cloudflare",
                    check_type="TCP",
                    expected_status=200,
                    interval_seconds=30,
                    category="Инфраструктура",
                    is_active=True
                ),
                Service(
                    name="Тестовый эндпоинт со сбоем (Демо)",
                    url="https://httpstat.us/500",
                    description="Эндпоинт возвращает HTTP 500 для демонстрации регистрации инцидентов",
                    check_type="HTTPS",
                    method="GET",
                    expected_status=200,
                    interval_seconds=45,
                    category="Тестирование",
                    is_active=True
                )
            ]
            session.add_all(demo_services)
            await session.commit()
            logger.info("Демонстрационные сервисы успешно добавлены.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Инициализация базы данных PulseWatch...")
    await init_db()
    await seed_demo_services_if_empty()

    logger.info("Запуск фонового мониторинга сервисов...")
    await scheduler.start()

    yield

    # Shutdown
    logger.info("Остановка планировщика мониторинга...")
    await scheduler.stop()


app = FastAPI(
    title=APP_NAME,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Static & Templates
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Register API Routers
app.include_router(services_router)
app.include_router(checks_router)
app.include_router(incidents_router)
app.include_router(stats_router)
app.include_router(export_router)


# --- HTML Frontend Views ---
@app.get("/", response_class=HTMLResponse)
async def view_dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    """Главный дашборд со списком сервисов и сводной статистикой."""
    stats = await get_dashboard_summary(db)
    
    # Получаем сервисы с их 24-часовым аптаймом
    services_res = await db.execute(select(Service).order_by(Service.name))
    services = services_res.scalars().all()

    from datetime import datetime, timedelta
    since_24h = datetime.utcnow() - timedelta(hours=24)
    services_data = []
    for s in services:
        uptime = await calculate_uptime_percentage(db, s.id, since_24h)
        s_dict = {
            "id": s.id,
            "name": s.name,
            "url": s.url,
            "description": s.description,
            "check_type": s.check_type,
            "category": s.category,
            "current_status": s.current_status,
            "is_active": s.is_active,
            "last_check_at": s.last_check_at,
            "last_response_time_ms": s.last_response_time_ms,
            "last_status_code": s.last_status_code,
            "last_error_message": s.last_error_message,
            "uptime_24h": uptime
        }
        services_data.append(s_dict)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "active_page": "dashboard",
            "stats": stats,
            "services": services_data
        }
    )


@app.get("/services/{service_id}", response_class=HTMLResponse)
async def view_service_detail(service_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Страница подробной информации о сервисе и графиков."""
    service = await db.get(Service, service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Сервис не найден")

    stats = await get_service_stats(db, service_id)

    from app.models import CheckResult
    from sqlalchemy import desc
    checks_res = await db.execute(
        select(CheckResult)
        .where(CheckResult.service_id == service_id)
        .order_by(desc(CheckResult.timestamp))
        .limit(50)
    )
    recent_checks = checks_res.scalars().all()

    incidents_res = await db.execute(
        select(Incident)
        .where(Incident.service_id == service_id)
        .order_by(desc(Incident.started_at))
        .limit(20)
    )
    recent_incidents = incidents_res.scalars().all()

    return templates.TemplateResponse(
        "service_detail.html",
        {
            "request": request,
            "active_page": "services",
            "service": service,
            "stats": stats,
            "recent_checks": recent_checks,
            "recent_incidents": recent_incidents
        }
    )


@app.get("/incidents", response_class=HTMLResponse)
async def view_incidents(request: Request, db: AsyncSession = Depends(get_db)):
    """Журнал инцидентов недоступности по всей инфраструктуре."""
    from sqlalchemy.orm import joinedload
    stmt = (
        select(Incident)
        .options(joinedload(Incident.service))
        .order_by(Incident.started_at.desc())
        .limit(100)
    )
    res = await db.execute(stmt)
    incidents_db = res.scalars().all()

    incidents_data = []
    for inc in incidents_db:
        incidents_data.append({
            "id": inc.id,
            "service_id": inc.service_id,
            "service_name": inc.service.name if inc.service else "Удаленный сервис",
            "status": inc.status,
            "started_at": inc.started_at,
            "resolved_at": inc.resolved_at,
            "duration_seconds": inc.duration_seconds,
            "cause": inc.cause
        })

    return templates.TemplateResponse(
        "incidents.html",
        {
            "request": request,
            "active_page": "incidents",
            "incidents": incidents_data
        }
    )


@app.get("/health")
async def health_check():
    """Системный эндпоинт самодиагностики сервиса мониторинга."""
    return {
        "status": "healthy",
        "app": APP_NAME,
        "version": APP_VERSION,
        "scheduler_running": scheduler._running
    }

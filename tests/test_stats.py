import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Service, CheckResult
from app.stats import calculate_uptime_percentage, get_service_stats


@pytest.mark.asyncio
async def test_uptime_calculation(db_session: AsyncSession):
    """Тест формулы расчета доступности (Uptime %)."""
    srv = Service(name="Billing API", url="http://billing.local", is_active=True)
    db_session.add(srv)
    await db_session.commit()
    await db_session.refresh(srv)

    now = datetime.utcnow()
    # Добавляем 8 успешных и 2 неуспешных проверки
    for i in range(8):
        db_session.add(CheckResult(
            service_id=srv.id,
            timestamp=now - timedelta(minutes=i * 2),
            status="UP",
            is_success=True,
            response_time_ms=50.0 + i
        ))
    for i in range(2):
        db_session.add(CheckResult(
            service_id=srv.id,
            timestamp=now - timedelta(minutes=20 + i * 2),
            status="DOWN",
            is_success=False,
            response_time_ms=None,
            error_message="500 Internal Error"
        ))
    await db_session.commit()

    since = now - timedelta(hours=1)
    uptime = await calculate_uptime_percentage(db_session, srv.id, since)
    # 8 из 10 проверок успешны -> 80%
    assert uptime == 80.0

    stats = await get_service_stats(db_session, srv.id)
    assert stats.uptime_24h == 80.0
    assert stats.total_checks == 10
    assert stats.avg_latency_ms is not None


@pytest.mark.asyncio
async def test_export_endpoints(db_session: AsyncSession, async_client: AsyncClient):
    """Тест выгрузки отчетов в форматах CSV и JSON."""
    srv = Service(name="Test Service", url="http://test.local", is_active=True)
    db_session.add(srv)
    await db_session.commit()

    # Test CSV export
    csv_resp = await async_client.get("/api/export/csv")
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert "Test Service" in csv_resp.text

    # Test JSON export
    json_resp = await async_client.get("/api/export/json")
    assert json_resp.status_code == 200
    data = json_resp.json()
    assert "services" in data
    assert len(data["services"]) >= 1

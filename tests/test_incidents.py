import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Service, Incident, CheckResult
from app.monitor.scheduler import scheduler
from app.monitor.checker import CheckOutcome


@pytest.mark.asyncio
async def test_incident_lifecycle(db_session: AsyncSession):
    """Тест автоматического открытия и закрытия инцидента планировщиком."""
    srv = Service(
        name="Payment Gateway",
        url="https://pay.company.local/health",
        current_status="UP",
        is_active=True
    )
    db_session.add(srv)
    await db_session.commit()
    await db_session.refresh(srv)

    # 1. Сбой: статус меняется на DOWN
    down_outcome = CheckOutcome(
        status="DOWN",
        is_success=False,
        status_code=503,
        response_time_ms=1200.0,
        error_message="503 Service Unavailable"
    )
    await scheduler._process_check_result(db_session, srv, down_outcome)

    # Проверяем, что открылся инцидент
    inc_stmt = select(Incident).where(Incident.service_id == srv.id)
    res = await db_session.execute(inc_stmt)
    incidents = res.scalars().all()
    assert len(incidents) == 1
    inc = incidents[0]
    assert inc.status == "OPEN"
    assert "503" in inc.cause
    assert srv.current_status == "DOWN"

    # 2. Восстановление: статус возвращается в UP
    up_outcome = CheckOutcome(
        status="UP",
        is_success=True,
        status_code=200,
        response_time_ms=85.0
    )
    await scheduler._process_check_result(db_session, srv, up_outcome)

    await db_session.refresh(inc)
    assert inc.status == "RESOLVED"
    assert inc.resolved_at is not None
    assert inc.duration_seconds is not None
    assert srv.current_status == "UP"


@pytest.mark.asyncio
async def test_incidents_api_endpoint(db_session: AsyncSession, async_client: AsyncClient):
    """Тест получения списка инцидентов через REST API."""
    srv = Service(name="Search Engine", url="https://search.local", is_active=True)
    db_session.add(srv)
    await db_session.commit()
    await db_session.refresh(srv)

    inc1 = Incident(service_id=srv.id, status="OPEN", cause="Timeout 10s")
    inc2 = Incident(service_id=srv.id, status="RESOLVED", duration_seconds=180, cause="500 Error")
    db_session.add_all([inc1, inc2])
    await db_session.commit()

    resp = await async_client.get("/api/incidents")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2

    # Filter by status=OPEN
    open_resp = await async_client.get("/api/incidents?status=OPEN")
    assert open_resp.status_code == 200
    open_data = open_resp.json()
    assert all(i["status"] == "OPEN" for i in open_data)


@pytest.mark.asyncio
async def test_vk_messenger_notification():
    """Тест отправки уведомления в VK Мессенджер через VK API."""
    from unittest.mock import patch, AsyncMock, MagicMock
    from app.monitor.notifier import send_vk_message

    with patch("app.monitor.notifier.VK_ACCESS_TOKEN", "vk1.a.mock_token"), \
         patch("app.monitor.notifier.VK_PEER_ID", "2000000001"), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": 12345}
        mock_post.return_value = mock_resp

        success = await send_vk_message("🚨 [PulseWatch Alert] Сервис недоступен!")
        assert success is True
        mock_post.assert_called_once()


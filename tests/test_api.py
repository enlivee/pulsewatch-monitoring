import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient

from app.models import Service


@pytest.mark.asyncio
async def test_health_endpoint(async_client: AsyncClient):
    """Тест эндпоинта проверки работоспособности самого PulseWatch."""
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "PulseWatch" in data["app"]


@pytest.mark.asyncio
async def test_service_crud_lifecycle(async_client: AsyncClient):
    """Полный цикл создания, чтения, паузы, возобновления и удаления сервиса."""
    with patch("app.api.services.scheduler.run_service_check", new_callable=AsyncMock):
        # 1. Создание сервиса
        payload = {
            "name": "Auth Service",
            "url": "https://auth.company.local/health",
            "description": "Центральный сервис аутентификации",
            "check_type": "HTTPS",
            "method": "GET",
            "expected_status": 200,
            "interval_seconds": 15,
            "timeout_seconds": 5.0,
            "category": "Безопасность",
            "is_active": True
        }
        create_resp = await async_client.post("/api/services", json=payload)
        assert create_resp.status_code == 201
        created = create_resp.json()
        service_id = created["id"]
        assert created["name"] == "Auth Service"
        assert created["current_status"] in ["PENDING", "UP", "DOWN", "DEGRADED"]

        # 2. Получение списка сервисов
        list_resp = await async_client.get("/api/services")
        assert list_resp.status_code == 200
        services = list_resp.json()
        assert any(s["id"] == service_id for s in services)

        # 3. Фильтрация по поиску
        search_resp = await async_client.get("/api/services?search=Auth")
        assert search_resp.status_code == 200
        assert len(search_resp.json()) == 1

        # 4. Просмотр детальной информации
        detail_resp = await async_client.get(f"/api/services/{service_id}")
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert detail["id"] == service_id
        assert "stats" in detail
        assert "uptime_24h" in detail["stats"]

        # 5. Приостановка сервиса (Pause)
        pause_resp = await async_client.post(f"/api/services/{service_id}/pause")
        assert pause_resp.status_code == 200
        assert pause_resp.json()["is_active"] is False

        # 6. Возобновление сервиса (Resume)
        resume_resp = await async_client.post(f"/api/services/{service_id}/resume")
        assert resume_resp.status_code == 200
        assert resume_resp.json()["is_active"] is True

        # 7. Удаление сервиса
        del_resp = await async_client.delete(f"/api/services/{service_id}")
        assert del_resp.status_code == 204

        # Проверка, что сервис удален
        get_deleted = await async_client.get(f"/api/services/{service_id}")
        assert get_deleted.status_code == 404

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.monitor.checker import check_http, check_tcp, execute_check
from app.models import Service


@pytest.mark.asyncio
async def test_check_http_success():
    """Тест успешной HTTP проверки со статусом 200."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = "OK, service is running!"
        mock_get.return_value = mock_resp

        outcome = await check_http(
            url="http://example.com/health",
            expected_status=200,
            timeout=5.0
        )

        assert outcome.status == "UP"
        assert outcome.is_success is True
        assert outcome.status_code == 200
        assert outcome.error_message is None
        assert outcome.response_time_ms is not None


@pytest.mark.asyncio
async def test_check_http_unexpected_status():
    """Тест проверки при получении кода ошибки 500 (DOWN)."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_get.return_value = mock_resp

        outcome = await check_http(
            url="http://example.com/health",
            expected_status=200,
            timeout=5.0
        )

        assert outcome.status == "DOWN"
        assert outcome.is_success is False
        assert outcome.status_code == 500
        assert "500" in outcome.error_message


@pytest.mark.asyncio
async def test_check_http_keyword_mismatch():
    """Тест проверки, когда ключевое слово отсутствует в теле ответа."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = "System is down for maintenance"
        mock_get.return_value = mock_resp

        outcome = await check_http(
            url="http://example.com/health",
            expected_status=200,
            timeout=5.0,
            keyword="healthy"
        )

        assert outcome.status == "DEGRADED"
        assert outcome.is_success is False
        assert "healthy" in outcome.error_message


@pytest.mark.asyncio
async def test_check_tcp_connection():
    """Тест TCP проверки порта."""
    with patch("asyncio.open_connection") as mock_conn:
        mock_reader = AsyncMock()
        mock_writer = AsyncMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        mock_conn.return_value = (mock_reader, mock_writer)

        outcome = await check_tcp("127.0.0.1", 80, timeout=2.0)
        assert outcome.status == "UP"
        assert outcome.is_success is True


@pytest.mark.asyncio
async def test_execute_check_dispatcher():
    """Тест диспетчера проверок сервиса."""
    srv = Service(
        name="Test API",
        url="https://api.test.local/health",
        check_type="HTTP",
        method="GET",
        expected_status=200,
        timeout_seconds=5.0
    )

    with patch("app.monitor.checker.check_http") as mock_check_http:
        from app.monitor.checker import CheckOutcome
        mock_check_http.return_value = CheckOutcome(
            status="UP",
            is_success=True,
            status_code=200,
            response_time_ms=45.2
        )

        outcome = await execute_check(srv)
        assert outcome.status == "UP"
        assert outcome.response_time_ms == 45.2
        mock_check_http.assert_called_once()

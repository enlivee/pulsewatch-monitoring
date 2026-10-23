import asyncio
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse
import httpx


@dataclass
class CheckOutcome:
    status: str              # "UP", "DOWN", "DEGRADED"
    is_success: bool
    status_code: Optional[int] = None
    response_time_ms: Optional[float] = None
    error_message: Optional[str] = None


async def check_tcp(host: str, port: int, timeout: float) -> CheckOutcome:
    """Проверка доступности TCP сокета (порт)."""
    start_time = time.perf_counter()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        latency = (time.perf_counter() - start_time) * 1000.0
        return CheckOutcome(
            status="UP",
            is_success=True,
            status_code=None,
            response_time_ms=round(latency, 2),
            error_message=None
        )
    except asyncio.TimeoutError:
        latency = (time.perf_counter() - start_time) * 1000.0
        return CheckOutcome(
            status="DOWN",
            is_success=False,
            status_code=None,
            response_time_ms=round(latency, 2),
            error_message=f"TCP connection timed out after {timeout:.1f}s"
        )
    except Exception as exc:
        latency = (time.perf_counter() - start_time) * 1000.0
        return CheckOutcome(
            status="DOWN",
            is_success=False,
            status_code=None,
            response_time_ms=round(latency, 2),
            error_message=f"TCP error: {str(exc)}"
        )


async def check_http(
    url: str,
    method: str = "GET",
    expected_status: int = 200,
    timeout: float = 10.0,
    keyword: Optional[str] = None
) -> CheckOutcome:
    """Проверка доступности HTTP / HTTPS эндпоинта."""
    # Ensure scheme
    target_url = url.strip()
    if not (target_url.startswith("http://") or target_url.startswith("https://")):
        target_url = "http://" + target_url

    headers = {
        "User-Agent": "PulseWatch-Monitor/1.0 (+https://github.com/monitoring/pulsewatch)",
        "Accept": "*/*"
    }

    start_time = time.perf_counter()
    try:
        # verify=False for self-signed certificates tolerance or configurable
        async with httpx.AsyncClient(timeout=timeout, verify=False, follow_redirects=True) as client:
            if method.upper() == "HEAD":
                resp = await client.head(target_url, headers=headers)
            elif method.upper() == "POST":
                resp = await client.post(target_url, headers=headers)
            else:
                resp = await client.get(target_url, headers=headers)

            latency = (time.perf_counter() - start_time) * 1000.0
            status_code = resp.status_code

            # Check status code match
            if status_code != expected_status:
                # If 5xx or connection-level error -> DOWN, if 4xx or redirect mismatch -> DEGRADED or DOWN
                status = "DOWN" if status_code >= 500 else "DEGRADED"
                return CheckOutcome(
                    status=status,
                    is_success=False,
                    status_code=status_code,
                    response_time_ms=round(latency, 2),
                    error_message=f"Статус {status_code} (ожидался {expected_status})"
                )

            # Check keyword in body if required
            if keyword:
                body_text = resp.text
                if keyword not in body_text:
                    return CheckOutcome(
                        status="DEGRADED",
                        is_success=False,
                        status_code=status_code,
                        response_time_ms=round(latency, 2),
                        error_message=f"Ключевое слово '{keyword}' не найдено в теле ответа"
                    )

            # Check if latency is very high (degraded)
            status = "UP"
            if latency > 3000.0:  # > 3 seconds latency is considered degraded
                status = "DEGRADED"

            return CheckOutcome(
                status=status,
                is_success=True,
                status_code=status_code,
                response_time_ms=round(latency, 2),
                error_message=None
            )

    except httpx.TimeoutException:
        latency = (time.perf_counter() - start_time) * 1000.0
        return CheckOutcome(
            status="DOWN",
            is_success=False,
            status_code=None,
            response_time_ms=round(latency, 2),
            error_message=f"Таймаут соединения ({timeout:.1f} сек)"
        )
    except httpx.ConnectError as exc:
        latency = (time.perf_counter() - start_time) * 1000.0
        return CheckOutcome(
            status="DOWN",
            is_success=False,
            status_code=None,
            response_time_ms=round(latency, 2),
            error_message="Ошибка подключения: сервер недоступен или хост не найден"
        )
    except Exception as exc:
        latency = (time.perf_counter() - start_time) * 1000.0
        return CheckOutcome(
            status="DOWN",
            is_success=False,
            status_code=None,
            response_time_ms=round(latency, 2),
            error_message=f"Ошибка: {str(exc)}"
        )


async def execute_check(service) -> CheckOutcome:
    """Диспетчер проверки сервиса на основе его настроек."""
    check_type = (service.check_type or "HTTP").upper()

    if check_type == "TCP":
        url = service.url.replace("tcp://", "")
        if ":" in url:
            host, port_str = url.split(":", 1)
            port = int(port_str)
        else:
            host = url
            port = 80
        return await check_tcp(host, port, service.timeout_seconds)

    # HTTP / HTTPS / PING (via HTTP)
    return await check_http(
        url=service.url,
        method=service.method or "GET",
        expected_status=service.expected_status or 200,
        timeout=service.timeout_seconds or 10.0,
        keyword=service.keyword
    )

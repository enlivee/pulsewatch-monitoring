import logging
from datetime import datetime
from typing import Optional
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import NotificationLog
from app.config import VK_ACCESS_TOKEN, VK_PEER_ID, VK_API_VERSION, DEFAULT_WEBHOOK_URL

logger = logging.getLogger("pulsewatch.notifier")


async def send_vk_message(text: str) -> bool:
    """Отправка сообщения в VK Мессенджер через официальный VK API (messages.send)."""
    if not VK_ACCESS_TOKEN or not VK_PEER_ID:
        return False

    url = "https://api.vk.com/method/messages.send"
    params = {
        "access_token": VK_ACCESS_TOKEN,
        "v": VK_API_VERSION,
        "peer_id": VK_PEER_ID,
        "message": text,
        "random_id": int(datetime.utcnow().timestamp() * 1000) % 2147483647
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, data=params)
            data = resp.json()
            if "error" in data:
                logger.error(f"VK API returned error: {data['error'].get('error_msg')}")
                return False
            logger.info(f"VK Messenger alert sent successfully (peer_id: {VK_PEER_ID})")
            return True
    except Exception as exc:
        logger.error(f"Failed to send VK Messenger alert: {exc}")
        return False


async def send_notification(
    db: AsyncSession,
    service_id: int,
    service_name: str,
    event_type: str,  # "INCIDENT_DOWN", "INCIDENT_RESOLVED"
    message: str,
    incident_id: Optional[int] = None,
    webhook_url: Optional[str] = None
):
    """
    Отправляет уведомление об инциденте или восстановлении сервиса:
    1. Логирует в БД
    2. Отправляет в VK Мессенджер (при наличии настроек)
    3. Отправляет на внешний Webhook (при наличии)
    """
    prefix = "🚨 ИНЦИДЕНТ" if event_type == "INCIDENT_DOWN" else "✅ ВОССТАНОВЛЕНИЕ"
    full_message = f"[{prefix}] Сервис: '{service_name}' (ID: {service_id})\n{message}"

    logger.warning(full_message)

    # 1. Log to database
    try:
        log_entry = NotificationLog(
            service_id=service_id,
            incident_id=incident_id,
            channel="SYSTEM_LOG",
            message=full_message,
            success=True,
            sent_at=datetime.utcnow()
        )
        db.add(log_entry)
        await db.commit()
    except Exception as exc:
        logger.error(f"Failed to save notification log: {exc}")

    # 2. VK Messenger notification
    vk_success = await send_vk_message(full_message)
    if vk_success:
        try:
            vk_log = NotificationLog(
                service_id=service_id,
                incident_id=incident_id,
                channel="VK_MESSENGER",
                message=full_message,
                success=True,
                sent_at=datetime.utcnow()
            )
            db.add(vk_log)
            await db.commit()
        except Exception:
            pass

    # 3. Webhook dispatch
    target_webhook = webhook_url or DEFAULT_WEBHOOK_URL
    if target_webhook:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                payload = {
                    "event": event_type,
                    "service_id": service_id,
                    "service_name": service_name,
                    "incident_id": incident_id,
                    "message": full_message,
                    "timestamp": datetime.utcnow().isoformat()
                }
                resp = await client.post(target_webhook, json=payload)
                logger.info(f"Webhook delivered to {target_webhook}: HTTP {resp.status_code}")
        except Exception as exc:
            logger.error(f"Failed to deliver webhook to {target_webhook}: {exc}")


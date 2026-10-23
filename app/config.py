import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR}/monitoring.db")
SYNC_DATABASE_URL = os.getenv("SYNC_DATABASE_URL", f"sqlite:///{BASE_DIR}/monitoring.db")

DEFAULT_CHECK_INTERVAL = int(os.getenv("DEFAULT_CHECK_INTERVAL", "30"))
DEFAULT_TIMEOUT = int(os.getenv("DEFAULT_TIMEOUT", "10"))
SCHEDULER_TICK_SECONDS = 2  # Frequency of scheduler evaluation loop

APP_NAME = "PulseWatch"
APP_DESCRIPTION = "Система мониторинга доступности веб-сервисов и инфраструктуры"
APP_VERSION = "1.0.0"

# Интеграция с VK Мессенджером
VK_ACCESS_TOKEN = os.getenv("VK_ACCESS_TOKEN", "")  # Токен сообщества VK
VK_PEER_ID = os.getenv("VK_PEER_ID", "")            # ID пользователя или беседы VK
VK_API_VERSION = "5.199"

# Общий Webhook
DEFAULT_WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")


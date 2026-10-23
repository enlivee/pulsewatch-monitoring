from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl, ConfigDict


# --- Check Results ---
class CheckResultBase(BaseModel):
    status: str
    is_success: bool
    status_code: Optional[int] = None
    response_time_ms: Optional[float] = None
    error_message: Optional[str] = None


class CheckResultOut(CheckResultBase):
    id: int
    service_id: int
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Incidents ---
class IncidentOut(BaseModel):
    id: int
    service_id: int
    service_name: Optional[str] = None
    status: str
    started_at: datetime
    resolved_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    cause: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# --- Services ---
class ServiceBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=128, description="Название сервиса")
    url: str = Field(..., max_length=512, description="URL или хост:порт для проверки")
    description: Optional[str] = Field(None, max_length=512)
    check_type: str = Field("HTTP", description="Тип проверки: HTTP, HTTPS, TCP")
    method: str = Field("GET", description="HTTP метод: GET, POST, HEAD")
    expected_status: int = Field(200, description="Ожидаемый HTTP статус-код")
    timeout_seconds: float = Field(10.0, ge=1.0, le=60.0, description="Таймаут проверки в секундах")
    interval_seconds: int = Field(30, ge=5, le=3600, description="Интервал между проверками в секундах")
    keyword: Optional[str] = Field(None, max_length=256, description="Ключевое слово, которое должно присутствовать в ответе")
    category: str = Field("Общие", max_length=64, description="Категория сервиса")
    tags: Optional[str] = Field(None, max_length=256, description="Теги через запятую")
    is_active: bool = Field(True, description="Активен ли мониторинг")


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=128)
    url: Optional[str] = Field(None, max_length=512)
    description: Optional[str] = None
    check_type: Optional[str] = None
    method: Optional[str] = None
    expected_status: Optional[int] = None
    timeout_seconds: Optional[float] = Field(None, ge=1.0, le=60.0)
    interval_seconds: Optional[int] = Field(None, ge=5, le=3600)
    keyword: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None
    is_active: Optional[bool] = None


class ServiceOut(ServiceBase):
    id: int
    current_status: str
    last_check_at: Optional[datetime] = None
    last_response_time_ms: Optional[float] = None
    last_status_code: Optional[int] = None
    last_error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    uptime_24h: Optional[float] = None
    uptime_7d: Optional[float] = None
    uptime_30d: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class ServiceStats(BaseModel):
    uptime_24h: float
    uptime_7d: float
    uptime_30d: float
    avg_latency_ms: Optional[float] = None
    min_latency_ms: Optional[float] = None
    max_latency_ms: Optional[float] = None
    total_checks: int
    incident_count: int


class ServiceDetailOut(ServiceOut):
    stats: ServiceStats
    recent_checks: List[CheckResultOut] = []
    recent_incidents: List[IncidentOut] = []


# --- Global Dashboard Stats ---
class DashboardStats(BaseModel):
    total_services: int
    up_count: int
    down_count: int
    degraded_count: int
    paused_count: int
    avg_uptime_24h: float
    avg_response_time_ms: Optional[float] = None
    active_incidents_count: int

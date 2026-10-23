from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Index,
)
from sqlalchemy.orm import relationship
from app.database import Base


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False, index=True)
    url = Column(String(512), nullable=False)
    description = Column(String(512), nullable=True)
    check_type = Column(String(32), default="HTTP", nullable=False)  # HTTP, HTTPS, TCP, PING
    method = Column(String(16), default="GET", nullable=False)        # GET, POST, HEAD
    expected_status = Column(Integer, default=200, nullable=False)
    timeout_seconds = Column(Float, default=10.0, nullable=False)
    interval_seconds = Column(Integer, default=30, nullable=False)
    keyword = Column(String(256), nullable=True)                      # Must be present in body
    category = Column(String(64), default="Общие", nullable=False)
    tags = Column(String(256), nullable=True)                         # Comma-separated
    is_active = Column(Boolean, default=True, nullable=False)

    # Current / Last state
    current_status = Column(String(32), default="PENDING", nullable=False)  # UP, DOWN, DEGRADED, PENDING, PAUSED
    last_check_at = Column(DateTime, nullable=True)
    last_response_time_ms = Column(Float, nullable=True)
    last_status_code = Column(Integer, nullable=True)
    last_error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    checks = relationship("CheckResult", back_populates="service", cascade="all, delete-orphan", order_by="desc(CheckResult.timestamp)")
    incidents = relationship("Incident", back_populates="service", cascade="all, delete-orphan", order_by="desc(Incident.started_at)")


class CheckResult(Base):
    __tablename__ = "check_results"

    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(Integer, ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    status = Column(String(32), nullable=False)       # UP, DOWN, DEGRADED
    is_success = Column(Boolean, nullable=False)
    status_code = Column(Integer, nullable=True)
    response_time_ms = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)

    service = relationship("Service", back_populates="checks")

    __table_args__ = (
        Index("ix_check_service_time", "service_id", "timestamp"),
    )


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(Integer, ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(32), default="OPEN", nullable=False)  # OPEN, RESOLVED
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    resolved_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    cause = Column(Text, nullable=True)

    service = relationship("Service", back_populates="incidents")


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(Integer, ForeignKey("services.id", ondelete="CASCADE"), nullable=False)
    incident_id = Column(Integer, nullable=True)
    channel = Column(String(64), nullable=False)  # LOG, WEBHOOK, TELEGRAM, VK
    message = Column(Text, nullable=False)
    success = Column(Boolean, default=True)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)

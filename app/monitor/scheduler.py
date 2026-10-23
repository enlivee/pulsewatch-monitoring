import asyncio
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import Service, CheckResult, Incident
from app.monitor.checker import execute_check, CheckOutcome
from app.monitor.notifier import send_notification
from app.config import SCHEDULER_TICK_SECONDS

logger = logging.getLogger("pulsewatch.scheduler")


class MonitorScheduler:
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._semaphore = asyncio.Semaphore(15)  # Max concurrent checks

    async def start(self):
        """Запуск фонового цикла мониторинга."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("PulseWatch Monitor Scheduler успешно запущен")

    async def stop(self):
        """Остановка монитора."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("PulseWatch Monitor Scheduler остановлен")

    async def _run_loop(self):
        """Основной цикл проверки расписания."""
        while self._running:
            try:
                await self._check_due_services()
            except Exception as exc:
                logger.error(f"Ошибка в цикле планировщика: {exc}", exc_info=True)

            await asyncio.sleep(SCHEDULER_TICK_SECONDS)

    async def _check_due_services(self):
        """Поиск сервисов, для которых подошло время очередной проверки."""
        now = datetime.utcnow()
        async with AsyncSessionLocal() as session:
            stmt = select(Service).where(Service.is_active == True)
            result = await session.execute(stmt)
            services = result.scalars().all()

            tasks = []
            for service in services:
                is_due = False
                if service.last_check_at is None:
                    is_due = True
                else:
                    elapsed = (now - service.last_check_at).total_seconds()
                    if elapsed >= service.interval_seconds:
                        is_due = True

                if is_due:
                    tasks.append(self.run_service_check(service.id))

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def run_service_check(self, service_id: int) -> Optional[CheckOutcome]:
        """Выполняет проверку одного конкретного сервиса с семафором."""
        async with self._semaphore:
            async with AsyncSessionLocal() as session:
                service = await session.get(Service, service_id)
                if not service:
                    return None

                outcome = await execute_check(service)
                await self._process_check_result(session, service, outcome)
                return outcome

    async def _process_check_result(
        self, session: AsyncSession, service: Service, outcome: CheckOutcome
    ):
        """Сохранение результата проверки, обновление статуса и ведение инцидентов."""
        now = datetime.utcnow()
        old_status = service.current_status
        new_status = outcome.status

        # 1. Запись результата проверки в историю
        check_record = CheckResult(
            service_id=service.id,
            timestamp=now,
            status=new_status,
            is_success=outcome.is_success,
            status_code=outcome.status_code,
            response_time_ms=outcome.response_time_ms,
            error_message=outcome.error_message,
        )
        session.add(check_record)

        # 2. Обновление текущего состояния сервиса
        service.current_status = new_status
        service.last_check_at = now
        service.last_response_time_ms = outcome.response_time_ms
        service.last_status_code = outcome.status_code
        service.last_error_message = outcome.error_message
        service.updated_at = now

        # 3. Обработка перехода состояний и инцидентов
        # Сервис упал: переход из UP/DEGRADED/PENDING -> DOWN
        if new_status == "DOWN" and old_status != "DOWN":
            # Проверим, нет ли уже открытого инцидента
            open_incident_stmt = select(Incident).where(
                and_(Incident.service_id == service.id, Incident.status == "OPEN")
            )
            res = await session.execute(open_incident_stmt)
            open_incident = res.scalars().first()

            if not open_incident:
                new_incident = Incident(
                    service_id=service.id,
                    status="OPEN",
                    started_at=now,
                    cause=outcome.error_message or "Неизвестная ошибка",
                )
                session.add(new_incident)
                await session.flush()

                await send_notification(
                    db=session,
                    service_id=service.id,
                    service_name=service.name,
                    event_type="INCIDENT_DOWN",
                    message=f"Сервис недоступен. Причина: {outcome.error_message}",
                    incident_id=new_incident.id,
                )

        # Сервис восстановился: переход из DOWN -> UP
        elif new_status == "UP" and old_status == "DOWN":
            open_incident_stmt = select(Incident).where(
                and_(Incident.service_id == service.id, Incident.status == "OPEN")
            )
            res = await session.execute(open_incident_stmt)
            open_incident = res.scalars().first()

            if open_incident:
                open_incident.status = "RESOLVED"
                open_incident.resolved_at = now
                duration = int((now - open_incident.started_at).total_seconds())
                open_incident.duration_seconds = max(0, duration)

                minutes = duration // 60
                seconds = duration % 60
                dur_str = f"{minutes} мин {seconds} сек" if minutes > 0 else f"{seconds} сек"

                await send_notification(
                    db=session,
                    service_id=service.id,
                    service_name=service.name,
                    event_type="INCIDENT_RESOLVED",
                    message=f"Сервис восстановил нормальную работу. Длительность простоя: {dur_str}.",
                    incident_id=open_incident.id,
                )

        await session.commit()


# Глобальный инстанс планировщика
scheduler = MonitorScheduler()

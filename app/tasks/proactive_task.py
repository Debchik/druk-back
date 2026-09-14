import asyncio
from typing import Any, Dict
from uuid import UUID

from celery import Task

from app.celery_app import celery_app
from app.database import async_session
from app.logging import logger
from app.services.proactive_message_service import ProactiveMessageService
from app.services.redis_task_service import RedisTaskService
from settings import config


class ScanProactiveCandidatesTask(Task):
    name = 'app.tasks.proactive_task.ScanProactiveCandidatesTask'

    def run(self: 'ScanProactiveCandidatesTask') -> Dict[str, Any]:
        if not config.proactive.enabled:
            logger.info('celery_proactive_scan_skipped reason=disabled')
            return {'status': 'disabled', 'scheduled': 0}
        logger.info('celery_proactive_scan_started task_id=%s', self.request.id)
        scheduled = asyncio.run(self._scan())
        logger.info('celery_proactive_scan_completed task_id=%s scheduled=%s', self.request.id, scheduled)
        return {'status': 'completed', 'scheduled': scheduled}

    async def _scan(self: 'ScanProactiveCandidatesTask') -> int:
        async with async_session() as session:
            return await ProactiveMessageService.scan_candidates(session)


class ProcessProactiveMessageTask(Task):
    name = 'app.tasks.proactive_task.ProcessProactiveMessageTask'

    def run(
        self: 'ProcessProactiveMessageTask',
        proactive_message_id: str,
    ) -> Dict[str, Any]:
        task_id = self.request.id or ''
        logger.info('celery_proactive_task_started proactive_id=%s task_id=%s', proactive_message_id, task_id)
        try:
            result = asyncio.run(self._process(proactive_message_id, task_id))
            return {'proactive_message_id': proactive_message_id, 'status': result}
        except LookupError as error:
            RedisTaskService.save_state(proactive_message_id, task_id, 'failed', str(error))
            raise
        except Exception as error:
            if self.request.retries >= config.celery.max_retries:
                RedisTaskService.save_state(proactive_message_id, task_id, 'failed', str(error))
                logger.exception('celery_proactive_task_failed proactive_id=%s', proactive_message_id)
                raise
            RedisTaskService.save_state(proactive_message_id, task_id, 'retrying', str(error))
            countdown = min(
                config.celery.retry_backoff_seconds * (2 ** self.request.retries),
                config.celery.retry_backoff_max_seconds,
            )
            logger.warning(
                'celery_proactive_task_retrying proactive_id=%s retry=%s countdown=%s',
                proactive_message_id,
                self.request.retries + 1,
                countdown,
            )
            raise self.retry(exc=error, countdown=countdown)

    async def _process(
        self: 'ProcessProactiveMessageTask',
        proactive_message_id: str,
        task_id: str,
    ) -> str:
        async with async_session() as session:
            proactive_message = await ProactiveMessageService.process(
                session,
                UUID(proactive_message_id),
                task_id,
            )
            return proactive_message.status


scan_proactive_candidates_task = celery_app.register_task(ScanProactiveCandidatesTask())
process_proactive_message_task = celery_app.register_task(ProcessProactiveMessageTask())

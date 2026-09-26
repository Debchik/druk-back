import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.proactive_message_dao import ProactiveMessageDao
from app.logging import logger
from app.models.chat import Chat
from app.models.message import Message
from app.models.proactive_message import ProactiveMessage
from app.models.user_profile import UserProfile
from app.services.gemini_service import GeminiAIService
from settings import config


class ReminderService:
    @classmethod
    async def analyze_and_schedule(
        cls: type['ReminderService'],
        db: AsyncSession,
        chat: Chat,
        profile: UserProfile,
        user_message: Message,
    ) -> Optional[ProactiveMessage]:
        logger.info('reminder_analysis_started message_id=%s chat_id=%s', user_message.id, chat.id)
        if not cls._has_explicit_request(user_message.content):
            logger.info('reminder_analysis_skipped reason=no_explicit_request message_id=%s', user_message.id)
            return None
        decision = await cls._analyze(profile, user_message.content)
        if not decision.get('should_schedule'):
            logger.info('reminder_analysis_not_scheduled message_id=%s', user_message.id)
            return None
        scheduled_at = cls._parse_scheduled_at(profile, decision.get('scheduled_at'))
        if scheduled_at is None:
            logger.warning('reminder_analysis_invalid_time message_id=%s value=%s', user_message.id, decision.get('scheduled_at'))
            return None
        reminder_text = str(decision.get('reminder_text') or user_message.content).strip()[:2000]
        deduplication_key = f'reminder:{user_message.id}'
        proactive_message = await ProactiveMessageDao.get_by_deduplication_key(db, deduplication_key)
        if proactive_message is not None:
            return proactive_message
        proactive_message = await ProactiveMessageDao.create(
            db,
            chat.user_id,
            chat.id,
            'reminder',
            deduplication_key,
            scheduled_at.replace(tzinfo=None),
            content=reminder_text,
            source_message_id=user_message.id,
        )
        await db.commit()
        task_id = str(uuid4())
        try:
            from app.tasks.proactive_task import process_proactive_message_task

            process_proactive_message_task.apply_async(
                args=[str(proactive_message.id)],
                task_id=task_id,
                queue='proactive',
                eta=scheduled_at.astimezone(timezone.utc),
            )
            proactive_message.celery_task_id = task_id
            await db.commit()
        except Exception as error:
            await ProactiveMessageDao.mark_failed(db, proactive_message, str(error))
            await db.commit()
            logger.exception('reminder_task_dispatch_failed proactive_id=%s', proactive_message.id)
            raise
        logger.info(
            'reminder_scheduled proactive_id=%s message_id=%s scheduled_at=%s task_id=%s',
            proactive_message.id,
            user_message.id,
            scheduled_at.isoformat(),
            task_id,
        )
        return proactive_message

    @classmethod
    def _has_explicit_request(cls: type['ReminderService'], message: str) -> bool:
        return bool(re.search(r'(?iu)\b(?:напомн\w*|напоминан\w*|remind\w*)\b', message))

    @classmethod
    async def _analyze(
        cls: type['ReminderService'],
        profile: UserProfile,
        message: str,
    ) -> Dict[str, Any]:
        try:
            user_zone = ZoneInfo(profile.timezone)
        except Exception:
            user_zone = timezone.utc
        now = datetime.now(user_zone)
        system_prompt = (
            'Ты классификатор напоминаний. Проанализируй последнее сообщение пользователя и определи, '
            'явно ли он просит создать напоминание на конкретное будущее время.\n'
            'Простое упоминание будущего события, встречи или тревоги не является просьбой напомнить.\n'
            f'Текущая дата и время пользователя: {now.isoformat()}.\n'
            f'Часовой пояс пользователя: {profile.timezone}.\n'
            'Если пользователь просит напомнить, верни should_schedule=true, точное время в ISO 8601 '
            'с часовым поясом пользователя и короткий текст напоминания.\n'
            'Если просьбы о напоминании нет или время невозможно определить, верни should_schedule=false.\n'
            'Верни только JSON без markdown и пояснений в формате: '
            '{"should_schedule":true,"scheduled_at":"...","reminder_text":"..."}'
        )
        try:
            raw_result = await GeminiAIService.generate_reply(
                system_prompt,
                [{'role': 'user', 'content': message}],
            )
            return cls._parse_json(raw_result)
        except Exception:
            logger.exception('reminder_analysis_failed')
            return {'should_schedule': False}

    @classmethod
    def _parse_json(
        cls: type['ReminderService'],
        raw_result: str,
    ) -> Dict[str, Any]:
        cleaned = raw_result.strip()
        cleaned = re.sub(r'^```(?:json)?\s*|\s*```$', '', cleaned, flags=re.IGNORECASE)
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else {'should_schedule': False}

    @classmethod
    def _parse_scheduled_at(
        cls: type['ReminderService'],
        profile: UserProfile,
        value: Any,
    ) -> Optional[datetime]:
        if not isinstance(value, str):
            return None
        try:
            scheduled_at = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if scheduled_at.tzinfo is None:
                scheduled_at = scheduled_at.replace(tzinfo=ZoneInfo(profile.timezone))
            scheduled_at = scheduled_at.astimezone(timezone.utc)
        except (TypeError, ValueError):
            return None
        if scheduled_at <= datetime.now(timezone.utc):
            return None
        return scheduled_at

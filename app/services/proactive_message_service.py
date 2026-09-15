from datetime import datetime, time, timedelta, timezone
from typing import List, Optional, Tuple
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.message_dao import MessageDao
from app.dao.proactive_message_dao import ProactiveMessageDao
from app.logging import logger
from app.models.chat import Chat
from app.models.message import Message
from app.models.proactive_message import ProactiveMessage
from app.models.user import User
from app.models.user_profile import UserProfile
from app.services.gemini_service import GeminiAIService
from app.services.redis_task_service import RedisTaskService
from settings import config


class ProactiveMessageService:
    @classmethod
    def _now(cls: type['ProactiveMessageService']) -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    def _is_quiet_hours(
        cls: type['ProactiveMessageService'],
        profile: UserProfile,
        now: datetime,
    ) -> bool:
        if profile.quiet_hours_start is None or profile.quiet_hours_end is None:
            return False
        try:
            local_now = now.astimezone(ZoneInfo(profile.timezone)).time()
        except Exception:
            logger.warning('proactive_invalid_timezone timezone=%s', profile.timezone)
            local_now = now.time()
        start = profile.quiet_hours_start
        end = profile.quiet_hours_end
        if start <= end:
            return start <= local_now < end
        return local_now >= start or local_now < end

    @classmethod
    def _reason(
        cls: type['ProactiveMessageService'],
        last_message: Optional[Message],
        now: datetime,
    ) -> Optional[str]:
        if last_message is None:
            return None
        created_at = last_message.created_at.replace(tzinfo=timezone.utc)
        age = now - created_at
        if last_message.role == 'user' and age >= timedelta(minutes=config.proactive.follow_up_delay_minutes):
            return 'follow_up'
        if last_message.role == 'assistant' and age >= timedelta(hours=config.proactive.return_after_hours):
            return 'return'
        return None

    @classmethod
    def _deduplication_key(
        cls: type['ProactiveMessageService'],
        user_id: UUID,
        chat_id: UUID,
        reason: str,
        now: datetime,
    ) -> str:
        return f'{user_id}:{chat_id}:{reason}:{now.date().isoformat()}'

    @classmethod
    async def scan_candidates(
        cls: type['ProactiveMessageService'],
        db: AsyncSession,
    ) -> int:
        now = cls._now()
        candidates = await ProactiveMessageDao.list_candidate_chats(db, config.proactive.scan_batch_size)
        scheduled = 0
        for chat, user, profile in candidates:
            reason = await cls._candidate_reason(db, chat, user, profile, now)
            if reason is None:
                continue
            deduplication_key = cls._deduplication_key(user.id, chat.id, reason, now)
            existing = await ProactiveMessageDao.get_by_deduplication_key(db, deduplication_key)
            if existing is not None:
                continue
            proactive_message = await ProactiveMessageDao.create(
                db,
                user.id,
                chat.id,
                reason,
                deduplication_key,
                now.replace(tzinfo=None),
            )
            await db.commit()
            task_id = str(uuid4())
            try:
                from app.tasks.proactive_task import process_proactive_message_task

                process_proactive_message_task.apply_async(
                    args=[str(proactive_message.id)],
                    task_id=task_id,
                    queue='proactive',
                )
                proactive_message.celery_task_id = task_id
                await db.commit()
                RedisTaskService.save_state(str(proactive_message.id), task_id, 'queued')
                scheduled += 1
                logger.info(
                    'proactive_message_scheduled proactive_id=%s user_id=%s chat_id=%s reason=%s task_id=%s',
                    proactive_message.id,
                    user.id,
                    chat.id,
                    reason,
                    task_id,
                )
            except Exception as error:
                await ProactiveMessageDao.mark_failed(db, proactive_message, str(error))
                await db.commit()
                logger.exception('proactive_message_dispatch_failed proactive_id=%s', proactive_message.id)
        return scheduled

    @classmethod
    async def _candidate_reason(
        cls: type['ProactiveMessageService'],
        db: AsyncSession,
        chat: Chat,
        user: User,
        profile: UserProfile,
        now: datetime,
    ) -> Optional[str]:
        if not profile.proactive_enabled or cls._is_quiet_hours(profile, now):
            return None
        since = (now - timedelta(days=1)).replace(tzinfo=None)
        sent_count = await ProactiveMessageDao.count_sent_since(db, user.id, since)
        if sent_count >= profile.daily_proactive_limit:
            return None
        last_message = await ProactiveMessageDao.get_last_message(db, chat.id)
        return cls._reason(last_message, now)

    @classmethod
    async def process(
        cls: type['ProactiveMessageService'],
        db: AsyncSession,
        proactive_message_id: UUID,
        task_id: str,
    ) -> ProactiveMessage:
        proactive_message = await ProactiveMessageDao.get_by_id(db, proactive_message_id)
        if proactive_message is None:
            raise LookupError('Proactive message not found')
        if proactive_message.status == 'sent':
            return proactive_message
        context = await ProactiveMessageDao.get_context(db, proactive_message)
        if context is None:
            await ProactiveMessageDao.mark_skipped(db, proactive_message, 'chat or user not found')
            await db.commit()
            return proactive_message
        chat, user, profile = context
        now = cls._now()
        if proactive_message.reason != 'reminder' and await cls._candidate_reason(db, chat, user, profile, now) != proactive_message.reason:
            await ProactiveMessageDao.mark_skipped(db, proactive_message, 'conditions changed before send')
            await db.commit()
            return proactive_message
        await ProactiveMessageDao.mark_running(db, proactive_message, task_id)
        await db.commit()
        try:
            history = await MessageDao.list_for_chat(db, chat.id)
            prompt_messages = [
                {'role': item.role, 'content': item.content}
                for item in history[-8:]
                if item.status == 'completed' and item.role in {'user', 'assistant'}
            ]
            if proactive_message.reason == 'reminder':
                original_message = None
                if proactive_message.source_message_id is not None:
                    original_message = await MessageDao.get_by_id(db, proactive_message.source_message_id)
                original_text = original_message.content if original_message is not None else proactive_message.content
                system_prompt = (
                    'Сейчас наступило время ранее запланированного напоминания. '
                    'Ответь пользователю живо и естественно, как внимательный компаньон. '
                    'Не утверждай, что ты реальный человек, не говори о технических ограничениях '
                    'и не утверждай, что пользователь уже выполнил действие. '
                    'Сформулируй короткое напоминание на языке пользователя, максимум 2 предложения.\n'
                    f'Изначальная просьба пользователя: {original_text}\n'
                    f'Краткое содержание напоминания: {proactive_message.content}'
                )
            else:
                system_prompt = (
                    'Ты отправляешь короткое ненавязчивое проактивное сообщение пользователю. '
                    'Не утверждай, что ты реальный человек. Не дави и не используй манипуляции. '
                    'Ответь на языке пользователя, максимум 2 предложения. '
                    f'Причина сообщения: {proactive_message.reason}.'
                )
            reply = await GeminiAIService.generate_reply(system_prompt, prompt_messages)
            assistant = await MessageDao.create(
                db,
                chat.id,
                'assistant',
                reply,
                platform=chat.platform,
                message_type='proactive',
                status='completed',
            )
            await db.commit()
            if chat.platform == 'telegram' and user.telegram_id is not None:
                from app.services.telegram_service import TelegramService

                await TelegramService.send_message(user.telegram_id, reply)
            await ProactiveMessageDao.mark_sent(db, proactive_message, assistant.id, cls._now().replace(tzinfo=None))
            await db.commit()
            RedisTaskService.save_state(str(proactive_message.id), task_id, 'completed')
            logger.info('proactive_message_sent proactive_id=%s assistant_id=%s', proactive_message.id, assistant.id)
            return proactive_message
        except Exception as error:
            await ProactiveMessageDao.mark_failed(db, proactive_message, str(error))
            await db.commit()
            logger.exception('proactive_message_processing_failed proactive_id=%s', proactive_message.id)
            raise

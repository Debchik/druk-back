from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chat
from app.models.message import Message
from app.models.proactive_message import ProactiveMessage
from app.models.user import User
from app.models.user_profile import UserProfile


class ProactiveMessageDao:
    @classmethod
    async def get_by_id(
        cls: type['ProactiveMessageDao'],
        db: AsyncSession,
        proactive_message_id: UUID,
    ) -> Optional[ProactiveMessage]:
        return await db.scalar(sa.select(ProactiveMessage).where(ProactiveMessage.id == proactive_message_id))

    @classmethod
    async def get_by_deduplication_key(
        cls: type['ProactiveMessageDao'],
        db: AsyncSession,
        deduplication_key: str,
    ) -> Optional[ProactiveMessage]:
        return await db.scalar(sa.select(ProactiveMessage).where(ProactiveMessage.deduplication_key == deduplication_key))

    @classmethod
    async def create(
        cls: type['ProactiveMessageDao'],
        db: AsyncSession,
        user_id: UUID,
        chat_id: UUID,
        reason: str,
        deduplication_key: str,
        scheduled_at: datetime,
        content: str = '',
        source_message_id: Optional[UUID] = None,
    ) -> ProactiveMessage:
        proactive_message = ProactiveMessage(
            user_id=user_id,
            chat_id=chat_id,
            reason=reason,
            deduplication_key=deduplication_key,
            content=content,
            scheduled_at=scheduled_at,
            status='queued',
            source_message_id=source_message_id,
        )
        db.add(proactive_message)
        await db.flush()
        return proactive_message

    @classmethod
    async def list_candidate_chats(
        cls: type['ProactiveMessageDao'],
        db: AsyncSession,
        limit: int,
    ) -> List[Tuple[Chat, User, UserProfile]]:
        result = await db.execute(
            sa.select(Chat, User, UserProfile)
            .join(User, User.id == Chat.user_id)
            .join(UserProfile, UserProfile.user_id == User.id)
            .where(UserProfile.proactive_enabled.is_(True))
            .order_by(Chat.updated_at.asc())
            .limit(limit)
        )
        return list(result.all())

    @classmethod
    async def get_context(
        cls: type['ProactiveMessageDao'],
        db: AsyncSession,
        proactive_message: ProactiveMessage,
    ) -> Optional[Tuple[Chat, User, UserProfile]]:
        result = await db.execute(
            sa.select(Chat, User, UserProfile)
            .join(User, User.id == Chat.user_id)
            .join(UserProfile, UserProfile.user_id == User.id)
            .where(
                Chat.id == proactive_message.chat_id,
                User.id == proactive_message.user_id,
            )
        )
        return result.one_or_none()

    @classmethod
    async def get_last_message(
        cls: type['ProactiveMessageDao'],
        db: AsyncSession,
        chat_id: UUID,
    ) -> Optional[Message]:
        return await db.scalar(
            sa.select(Message)
            .where(Message.chat_id == chat_id, Message.status == 'completed')
            .order_by(Message.created_at.desc())
            .limit(1)
        )

    @classmethod
    async def count_sent_since(
        cls: type['ProactiveMessageDao'],
        db: AsyncSession,
        user_id: UUID,
        since: datetime,
    ) -> int:
        result = await db.scalar(
            sa.select(sa.func.count(ProactiveMessage.id)).where(
                ProactiveMessage.user_id == user_id,
                ProactiveMessage.status == 'sent',
                ProactiveMessage.sent_at >= since,
            )
        )
        return int(result or 0)

    @classmethod
    async def mark_running(
        cls: type['ProactiveMessageDao'],
        db: AsyncSession,
        proactive_message: ProactiveMessage,
        task_id: str,
    ) -> ProactiveMessage:
        proactive_message.status = 'running'
        proactive_message.celery_task_id = task_id
        proactive_message.error_message = None
        await db.flush()
        return proactive_message

    @classmethod
    async def mark_sent(
        cls: type['ProactiveMessageDao'],
        db: AsyncSession,
        proactive_message: ProactiveMessage,
        assistant_message_id: UUID,
        sent_at: datetime,
    ) -> ProactiveMessage:
        proactive_message.status = 'sent'
        proactive_message.assistant_message_id = assistant_message_id
        proactive_message.sent_at = sent_at
        proactive_message.error_message = None
        await db.flush()
        return proactive_message

    @classmethod
    async def mark_skipped(
        cls: type['ProactiveMessageDao'],
        db: AsyncSession,
        proactive_message: ProactiveMessage,
        reason: str,
    ) -> ProactiveMessage:
        proactive_message.status = 'skipped'
        proactive_message.error_message = reason[:2000]
        await db.flush()
        return proactive_message

    @classmethod
    async def mark_failed(
        cls: type['ProactiveMessageDao'],
        db: AsyncSession,
        proactive_message: ProactiveMessage,
        error: str,
    ) -> ProactiveMessage:
        proactive_message.status = 'failed'
        proactive_message.error_message = error[:2000]
        await db.flush()
        return proactive_message

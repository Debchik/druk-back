from typing import Dict, List, Optional, Tuple
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chat
from app.models.feedback import Feedback
from app.models.message import Message


class FeedbackDao:
    @classmethod
    async def get_message_for_user(
        cls: type['FeedbackDao'],
        db: AsyncSession,
        user_id: UUID,
        chat_id: UUID,
        message_id: UUID,
    ) -> Optional[Message]:
        return await db.scalar(
            sa.select(Message)
            .join(Chat, Chat.id == Message.chat_id)
            .where(
                Message.id == message_id,
                Message.role == 'assistant',
                Message.chat_id == chat_id,
                Chat.user_id == user_id,
            )
        )

    @classmethod
    async def get_by_message_user(
        cls: type['FeedbackDao'],
        db: AsyncSession,
        message_id: UUID,
        user_id: UUID,
    ) -> Optional[Feedback]:
        return await db.scalar(
            sa.select(Feedback).where(
                Feedback.message_id == message_id,
                Feedback.user_id == user_id,
            )
        )

    @classmethod
    async def create(
        cls: type['FeedbackDao'],
        db: AsyncSession,
        message_id: UUID,
        user_id: UUID,
        reaction: str,
        reason: Optional[str],
    ) -> Feedback:
        feedback = Feedback(
            message_id=message_id,
            user_id=user_id,
            reaction=reaction,
            reason=reason,
        )
        db.add(feedback)
        await db.flush()
        return feedback

    @classmethod
    async def update(
        cls: type['FeedbackDao'],
        db: AsyncSession,
        feedback: Feedback,
        reaction: str,
        reason: Optional[str],
    ) -> Feedback:
        feedback.reaction = reaction
        feedback.reason = reason
        await db.flush()
        return feedback

    @classmethod
    async def aggregate_for_user(
        cls: type['FeedbackDao'],
        db: AsyncSession,
        user_id: UUID,
    ) -> Dict[str, int]:
        result = await db.execute(
            sa.select(Feedback.reaction, sa.func.count(Feedback.id))
            .where(Feedback.user_id == user_id)
            .group_by(Feedback.reaction)
        )
        return {reaction: int(count) for reaction, count in result.all()}

    @classmethod
    async def list_for_chat(
        cls: type['FeedbackDao'],
        db: AsyncSession,
        user_id: UUID,
        chat_id: UUID,
        limit: int = 10,
    ) -> List[Tuple[Feedback, Message]]:
        result = await db.execute(
            sa.select(Feedback, Message)
            .join(Message, Message.id == Feedback.message_id)
            .where(
                Feedback.user_id == user_id,
                Message.chat_id == chat_id,
            )
            .order_by(Feedback.updated_at.desc())
            .limit(limit)
        )
        return list(result.all())

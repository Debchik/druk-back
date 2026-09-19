from typing import Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.feedback_dao import FeedbackDao
from app.logging import logger
from app.models.feedback import Feedback


class FeedbackService:
    _reactions = {'like', 'dislike', 'helpful', 'not_helpful'}
    _negative_reasons = {'not_understood', 'too_cold', 'repetitive', 'unsafe', 'out_of_character'}

    @classmethod
    async def save(
        cls: type['FeedbackService'],
        db: AsyncSession,
        user_id: UUID,
        chat_id: UUID,
        message_id: UUID,
        reaction: str,
        reason: Optional[str],
    ) -> Feedback:
        if reaction not in cls._reactions:
            raise ValueError('Недопустимая реакция')
        if reason is not None and reason not in cls._negative_reasons:
            raise ValueError('Недопустимая причина негативной оценки')
        if reaction in {'like', 'helpful'} and reason is not None:
            raise ValueError('Причина доступна только для негативной оценки')
        message = await FeedbackDao.get_message_for_user(db, user_id, chat_id, message_id)
        if message is None:
            raise LookupError('Сообщение для оценки не найдено')
        feedback = await FeedbackDao.get_by_message_user(db, message_id, user_id)
        if feedback is None:
            feedback = await FeedbackDao.create(db, message_id, user_id, reaction, reason)
        else:
            feedback = await FeedbackDao.update(db, feedback, reaction, reason)
        await db.commit()
        await db.refresh(feedback)
        logger.info(
            'Оценка ответа сохранена message_id=%s user_id=%s reaction=%s reason=%s',
            message_id,
            user_id,
            reaction,
            reason,
        )
        return feedback

    @classmethod
    async def analytics(
        cls: type['FeedbackService'],
        db: AsyncSession,
        user_id: UUID,
    ) -> Dict[str, int]:
        return await FeedbackDao.aggregate_for_user(db, user_id)

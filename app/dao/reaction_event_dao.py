from typing import List, Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chat
from app.models.message import Message
from app.models.reaction_event import ReactionEvent


class ReactionEventDao:
    @classmethod
    async def get_message_for_user(
        cls: type['ReactionEventDao'],
        db: AsyncSession,
        user_id: UUID,
        chat_id: UUID,
        external_message_id: str,
    ) -> Optional[Message]:
        return await db.scalar(
            sa.select(Message)
            .join(Chat, Chat.id == Message.chat_id)
            .where(
                Chat.user_id == user_id,
                Message.chat_id == chat_id,
                Message.platform == 'telegram',
                Message.external_id == external_message_id,
            )
        )

    @classmethod
    async def get_by_external_id(
        cls: type['ReactionEventDao'],
        db: AsyncSession,
        external_event_id: str,
    ) -> Optional[ReactionEvent]:
        return await db.scalar(
            sa.select(ReactionEvent).where(ReactionEvent.external_event_id == external_event_id)
        )

    @classmethod
    async def create(
        cls: type['ReactionEventDao'],
        db: AsyncSession,
        user_id: UUID,
        chat_id: UUID,
        message_id: UUID,
        actor_type: str,
        event_type: str,
        emoji: str,
        title: str,
        external_event_id: str,
        metadata_json: Optional[dict] = None,
    ) -> ReactionEvent:
        event = ReactionEvent(
            user_id=user_id,
            chat_id=chat_id,
            message_id=message_id,
            actor_type=actor_type,
            event_type=event_type,
            emoji=emoji,
            title=title,
            external_event_id=external_event_id,
            metadata_json=metadata_json,
        )
        db.add(event)
        await db.flush()
        return event

    @classmethod
    async def list_for_chat(
        cls: type['ReactionEventDao'],
        db: AsyncSession,
        chat_id: UUID,
        limit: int = 50,
    ) -> List[ReactionEvent]:
        result = await db.scalars(
            sa.select(ReactionEvent)
            .where(ReactionEvent.chat_id == chat_id)
            .order_by(ReactionEvent.created_at.desc())
            .limit(limit)
        )
        return list(result)

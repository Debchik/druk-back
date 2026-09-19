from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import Base


class ReactionEvent(Base):
    __tablename__ = 'reaction_events'
    __table_args__ = (
        sa.UniqueConstraint('external_event_id', name='uq_reaction_events_external_event_id'),
        sa.Index('ix_reaction_events_message_id', 'message_id'),
        sa.Index('ix_reaction_events_chat_created_at', 'chat_id', 'created_at'),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), index=True)
    chat_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey('chats.id', ondelete='CASCADE'), index=True)
    message_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey('messages.id', ondelete='CASCADE'), index=True)
    actor_type: Mapped[str] = mapped_column(sa.String(20))
    event_type: Mapped[str] = mapped_column(sa.String(20))
    emoji: Mapped[str] = mapped_column(sa.String(20))
    title: Mapped[str] = mapped_column(sa.String(40))
    external_event_id: Mapped[str] = mapped_column(sa.String(255))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=Base.utcnow, index=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(sa.JSON, nullable=True)

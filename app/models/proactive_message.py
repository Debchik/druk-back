from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import Base


class ProactiveMessage(Base):
    __tablename__ = 'proactive_messages'
    __table_args__ = (
        sa.UniqueConstraint('deduplication_key', name='uq_proactive_messages_deduplication_key'),
        sa.Index('ix_proactive_messages_scheduled_status', 'scheduled_at', 'status'),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), index=True)
    chat_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey('chats.id', ondelete='CASCADE'), index=True)
    reason: Mapped[str] = mapped_column(sa.String(40))
    deduplication_key: Mapped[str] = mapped_column(sa.String(255))
    scheduled_at: Mapped[datetime] = mapped_column(sa.DateTime, index=True)
    status: Mapped[str] = mapped_column(sa.String(20), default='queued', index=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(sa.String(255), nullable=True)
    assistant_message_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey('messages.id', ondelete='SET NULL'),
        nullable=True,
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=Base.utcnow)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, default=Base.utcnow, onupdate=Base.utcnow)

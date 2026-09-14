"""Add proactive message scheduling and delivery state."""
from alembic import op
import sqlalchemy as sa


revision = '008_proactive_messages'
down_revision = '007_media_processing'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'proactive_messages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('chat_id', sa.UUID(), nullable=False),
        sa.Column('reason', sa.String(length=40), nullable=False),
        sa.Column('deduplication_key', sa.String(length=255), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='queued'),
        sa.Column('celery_task_id', sa.String(length=255), nullable=True),
        sa.Column('assistant_message_id', sa.UUID(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['chat_id'], ['chats.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assistant_message_id'], ['messages.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('deduplication_key', name='uq_proactive_messages_deduplication_key'),
    )
    op.create_index('ix_proactive_messages_user_id', 'proactive_messages', ['user_id'])
    op.create_index('ix_proactive_messages_chat_id', 'proactive_messages', ['chat_id'])
    op.create_index('ix_proactive_messages_scheduled_at', 'proactive_messages', ['scheduled_at'])
    op.create_index('ix_proactive_messages_status', 'proactive_messages', ['status'])
    op.create_index(
        'ix_proactive_messages_scheduled_status',
        'proactive_messages',
        ['scheduled_at', 'status'],
    )


def downgrade() -> None:
    op.drop_index('ix_proactive_messages_scheduled_status', table_name='proactive_messages')
    op.drop_index('ix_proactive_messages_status', table_name='proactive_messages')
    op.drop_index('ix_proactive_messages_scheduled_at', table_name='proactive_messages')
    op.drop_index('ix_proactive_messages_chat_id', table_name='proactive_messages')
    op.drop_index('ix_proactive_messages_user_id', table_name='proactive_messages')
    op.drop_table('proactive_messages')

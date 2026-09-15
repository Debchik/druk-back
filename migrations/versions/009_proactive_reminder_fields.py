"""Add reminder payload and source message fields."""
from alembic import op
import sqlalchemy as sa


revision = '009_proactive_reminder_fields'
down_revision = '008_proactive_messages'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'proactive_messages',
        sa.Column('content', sa.Text(), nullable=False, server_default=''),
    )
    op.add_column(
        'proactive_messages',
        sa.Column('source_message_id', sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        'fk_proactive_messages_source_message_id',
        'proactive_messages',
        'messages',
        ['source_message_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_proactive_messages_source_message_id', 'proactive_messages', type_='foreignkey')
    op.drop_column('proactive_messages', 'source_message_id')
    op.drop_column('proactive_messages', 'content')

"""Add Telegram reaction events."""
from alembic import op
import sqlalchemy as sa


revision = '011_reaction_events'
down_revision = '010_feedback'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'reaction_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('chat_id', sa.UUID(), nullable=False),
        sa.Column('message_id', sa.UUID(), nullable=False),
        sa.Column('actor_type', sa.String(length=20), nullable=False),
        sa.Column('event_type', sa.String(length=20), nullable=False),
        sa.Column('emoji', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=40), nullable=False),
        sa.Column('external_event_id', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['chat_id'], ['chats.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('external_event_id', name='uq_reaction_events_external_event_id'),
    )
    op.create_index('ix_reaction_events_message_id', 'reaction_events', ['message_id'])
    op.create_index('ix_reaction_events_user_id', 'reaction_events', ['user_id'])
    op.create_index('ix_reaction_events_chat_id', 'reaction_events', ['chat_id'])
    op.create_index('ix_reaction_events_chat_created_at', 'reaction_events', ['chat_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_reaction_events_chat_created_at', table_name='reaction_events')
    op.drop_index('ix_reaction_events_chat_id', table_name='reaction_events')
    op.drop_index('ix_reaction_events_user_id', table_name='reaction_events')
    op.drop_index('ix_reaction_events_message_id', table_name='reaction_events')
    op.drop_table('reaction_events')

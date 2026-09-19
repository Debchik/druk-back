"""Add message feedback."""
from alembic import op
import sqlalchemy as sa


revision = '010_feedback'
down_revision = '009_proactive_reminder_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'feedback',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('message_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('reaction', sa.String(length=20), nullable=False),
        sa.Column('reason', sa.String(length=40), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('message_id', 'user_id', name='uq_feedback_message_user'),
    )
    op.create_index('ix_feedback_message_id', 'feedback', ['message_id'])
    op.create_index('ix_feedback_user_id', 'feedback', ['user_id'])
    op.create_index('ix_feedback_reaction', 'feedback', ['reaction'])


def downgrade() -> None:
    op.drop_index('ix_feedback_reaction', table_name='feedback')
    op.drop_index('ix_feedback_user_id', table_name='feedback')
    op.drop_index('ix_feedback_message_id', table_name='feedback')
    op.drop_table('feedback')

"""Add media trial limits for users created after this migration."""
from alembic import op
import sqlalchemy as sa


revision = '014_new_user_media_limits'
down_revision = '013_memory_fact_user_controls'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing users remain unlimited. After this migration, the server default
    # is switched to true so every newly created user receives the trial quota.
    op.add_column(
        'users',
        sa.Column(
            'media_trial_limited',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column(
        'users',
        'media_trial_limited',
        server_default=sa.true(),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )
    op.add_column(
        'users',
        sa.Column(
            'media_limit_rejection_count',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'media_limit_rejection_count')
    op.drop_column('users', 'media_trial_limited')

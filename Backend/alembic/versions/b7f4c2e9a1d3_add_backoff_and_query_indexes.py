"""worker backoff column and the indexes real queries need

Revision ID: b7f4c2e9a1d3
Revises: c3f1a8d92b47
Create Date: 2026-10-31 14:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7f4c2e9a1d3'
down_revision: Union[str, Sequence[str], None] = 'c3f1a8d92b47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'materials',
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True),
    )
    # The worker walks unfinished jobs in id order; this partial index is both the
    # order it wants and small enough to stay warm as the archive grows.
    op.create_index(
        'ix_materials_claimable',
        'materials',
        ['id'],
        unique=False,
        postgresql_where=sa.text("status IN ('pending', 'processing')"),
    )
    op.create_index(
        'ix_access_logs_user_created', 'access_logs', ['user_id', 'created_at'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_access_logs_user_created', table_name='access_logs')
    op.drop_index('ix_materials_claimable', table_name='materials', postgresql_where=sa.text("status IN ('pending', 'processing')"))
    op.drop_column('materials', 'next_attempt_at')

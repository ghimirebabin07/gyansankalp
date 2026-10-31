"""add login lockout columns to users and admins

Revision ID: c3f1a8d92b47
Revises: a1b2c3d4e5f6
Create Date: 2026-10-31 11:05:12.481006

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f1a8d92b47'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    for table in ('users', 'admins'):
        op.add_column(table, sa.Column('failed_attempts', sa.Integer(), server_default='0', nullable=False))
        op.add_column(table, sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    for table in ('users', 'admins'):
        op.drop_column(table, 'locked_until')
        op.drop_column(table, 'failed_attempts')

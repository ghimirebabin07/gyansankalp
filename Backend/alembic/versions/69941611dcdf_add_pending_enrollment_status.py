"""add_pending_enrollment_status

Revision ID: 69941611dcdf
Revises: adce14e20153
Create Date: 2026-10-30 19:59:22.903790

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '69941611dcdf'
down_revision: Union[str, Sequence[str], None] = 'adce14e20153'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE enrollmentstatus ADD VALUE 'pending'")


def downgrade() -> None:
    pass

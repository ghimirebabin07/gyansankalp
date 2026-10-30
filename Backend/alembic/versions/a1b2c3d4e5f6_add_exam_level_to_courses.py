"""add_exam_level_to_courses

Revision ID: a1b2c3d4e5f6
Revises: f71d2472a0ba
Create Date: 2026-10-30 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f71d2472a0ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('courses', sa.Column('exam_level', sa.String(50), nullable=True))
    op.execute("UPDATE courses SET exam_level = '' WHERE exam_level IS NULL")
    op.alter_column('courses', 'exam_level', nullable=False, server_default='')
    op.create_index('ix_courses_exam_level', 'courses', ['exam_level'])


def downgrade() -> None:
    op.drop_index('ix_courses_exam_level', table_name='courses')
    op.drop_column('courses', 'exam_level')

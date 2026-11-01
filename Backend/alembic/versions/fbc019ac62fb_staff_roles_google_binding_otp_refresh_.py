"""staff roles, google binding, otp, refresh tokens, assignments and audit

Revision ID: fbc019ac62fb
Revises: d8e5a1b7c3f9
Create Date: 2026-11-01 11:29:59.278024

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'fbc019ac62fb'
down_revision: Union[str, Sequence[str], None] = 'd8e5a1b7c3f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('admin_activity_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('admin_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=60), nullable=False),
    sa.Column('target', sa.String(length=160), nullable=True),
    sa.Column('ip', sa.String(length=45), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['admin_id'], ['admins.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_admin_activity_logs_admin_created', 'admin_activity_logs', ['admin_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_admin_activity_logs_admin_id'), 'admin_activity_logs', ['admin_id'], unique=False)
    op.create_index(op.f('ix_admin_activity_logs_created_at'), 'admin_activity_logs', ['created_at'], unique=False)
    op.create_table('admin_otps',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('admin_id', sa.Integer(), nullable=False),
    # An argon2 hash: a six digit code has only a million values, so a digest
    # would be readable back offline inside the code's own five minutes.
    sa.Column('code_hash', sa.String(length=255), nullable=False),
    sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['admin_id'], ['admins.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code_hash')
    )
    op.create_index(op.f('ix_admin_otps_admin_id'), 'admin_otps', ['admin_id'], unique=False)
    op.create_index('ix_admin_otps_admin_open', 'admin_otps', ['admin_id', 'consumed_at'], unique=False)
    op.create_index(op.f('ix_admin_otps_expires_at'), 'admin_otps', ['expires_at'], unique=False)
    op.create_table('admin_refresh_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('admin_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['admin_id'], ['admins.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_index(op.f('ix_admin_refresh_tokens_admin_id'), 'admin_refresh_tokens', ['admin_id'], unique=False)
    op.create_index(op.f('ix_admin_refresh_tokens_expires_at'), 'admin_refresh_tokens', ['expires_at'], unique=False)
    op.create_table('course_assignments',
    sa.Column('course_id', sa.Integer(), nullable=False),
    sa.Column('admin_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['admin_id'], ['admins.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('course_id', 'admin_id')
    )
    # The type is created by hand: ALTER TABLE ADD COLUMN of a brand new enum
    # otherwise refers to a type that does not exist yet.
    role = postgresql.ENUM(
        'super_admin', 'content_manager', 'editor', name='admin_role', create_type=False
    )
    role.create(op.get_bind(), checkfirst=True)
    # The default is the most privileged role because the rows that already exist
    # are the site owner's. Staff added from here on are created with an explicit
    # role by the seed script or the staff screen.
    op.add_column('admins', sa.Column('role', role, server_default='super_admin', nullable=False))
    op.add_column('admins', sa.Column('google_sub', sa.String(length=32), nullable=True))
    op.create_unique_constraint('admins_google_sub_key', 'admins', ['google_sub'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('admins_google_sub_key', 'admins', type_='unique')
    op.drop_column('admins', 'google_sub')
    op.drop_column('admins', 'role')
    postgresql.ENUM(name='admin_role').drop(op.get_bind(), checkfirst=True)
    op.drop_table('course_assignments')
    op.drop_index(op.f('ix_admin_refresh_tokens_expires_at'), table_name='admin_refresh_tokens')
    op.drop_index(op.f('ix_admin_refresh_tokens_admin_id'), table_name='admin_refresh_tokens')
    op.drop_table('admin_refresh_tokens')
    op.drop_index(op.f('ix_admin_otps_expires_at'), table_name='admin_otps')
    op.drop_index('ix_admin_otps_admin_open', table_name='admin_otps')
    op.drop_index(op.f('ix_admin_otps_admin_id'), table_name='admin_otps')
    op.drop_table('admin_otps')
    op.drop_index(op.f('ix_admin_activity_logs_created_at'), table_name='admin_activity_logs')
    op.drop_index(op.f('ix_admin_activity_logs_admin_id'), table_name='admin_activity_logs')
    op.drop_index('ix_admin_activity_logs_admin_created', table_name='admin_activity_logs')
    op.drop_table('admin_activity_logs')

"""google identity, email verification and single-use google tokens

Revision ID: d8e5a1b7c3f9
Revises: b7f4c2e9a1d3
Create Date: 2026-11-01 10:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8e5a1b7c3f9'
down_revision: Union[str, Sequence[str], None] = 'b7f4c2e9a1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'users',
        sa.Column('google_sub', sa.String(length=32), nullable=True),
    )
    op.add_column(
        'users',
        sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'users',
        sa.Column('email_verify_hash', sa.String(length=64), nullable=True),
    )
    op.add_column(
        'users',
        sa.Column('email_verify_expires_at', sa.DateTime(timezone=True), nullable=True),
    )
    # Google students have no Nepali mobile number.
    op.alter_column('users', 'phone', existing_type=sa.String(length=20), nullable=True)
    op.create_unique_constraint('users_google_sub_key', 'users', ['google_sub'])

    # Existing accounts are deliberately NOT marked verified: the platform has no
    # real students yet, so nobody is locked out, and a Google sign-in cannot be
    # linked to an address that has never proven it is read by its owner.
    op.create_table(
        'google_token_uses',
        sa.Column('sub', sa.String(length=32), nullable=False),
        sa.Column('issued_at', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('sub', 'issued_at'),
    )
    op.create_index(
        op.f('ix_google_token_uses_created_at'),
        'google_token_uses',
        ['created_at'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_google_token_uses_created_at'), table_name='google_token_uses')
    op.drop_table('google_token_uses')
    op.drop_constraint('users_google_sub_key', 'users', type_='unique')
    op.alter_column('users', 'phone', existing_type=sa.String(length=20), nullable=False)
    op.drop_column('users', 'email_verify_expires_at')
    op.drop_column('users', 'email_verify_hash')
    op.drop_column('users', 'email_verified_at')
    op.drop_column('users', 'google_sub')

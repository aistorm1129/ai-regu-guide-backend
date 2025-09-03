"""Add is_verified column to users table

Revision ID: ca1bec26d6cd
Revises: fbdb89703d7d
Create Date: 2025-09-03 23:16:55.031904

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ca1bec26d6cd'
down_revision: Union[str, None] = 'fbdb89703d7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_verified column to users table
    op.add_column('users', sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    # Remove is_verified column from users table
    op.drop_column('users', 'is_verified')

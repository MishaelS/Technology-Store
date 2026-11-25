"""User avatar (own photo)

Revision ID: b7e41f2c9a10
Revises: adcecbaa02dc
Create Date: 2026-11-26 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7e41f2c9a10'
down_revision: Union[str, None] = 'adcecbaa02dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('avatar_url', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'avatar_url')

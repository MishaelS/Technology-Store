"""More photos of a product

Revision ID: c3d58a1e7f42
Revises: b7e41f2c9a10
Create Date: 2026-11-26 11:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c3d58a1e7f42'
down_revision: Union[str, None] = 'b7e41f2c9a10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('products', sa.Column('images', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False))


def downgrade() -> None:
    op.drop_column('products', 'images')

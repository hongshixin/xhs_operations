"""add api_format to model_configs

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-15 11:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('model_configs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('api_format', sa.String(32), server_default='openai', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('model_configs', schema=None) as batch_op:
        batch_op.drop_column('api_format')

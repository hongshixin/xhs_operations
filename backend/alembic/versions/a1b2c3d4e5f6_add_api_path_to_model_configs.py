"""add api_path to model_configs

Revision ID: a1b2c3d4e5f6
Revises: 60cd5c95fde1
Create Date: 2026-07-15 10:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '60cd5c95fde1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('model_configs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('api_path', sa.Text(), server_default='', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('model_configs', schema=None) as batch_op:
        batch_op.drop_column('api_path')

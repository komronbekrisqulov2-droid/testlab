"""anti_cheat_fields

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-23 23:45:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


#  Alembic identifikatorlari
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Bazani oldinga surish."""
    with op.batch_alter_table('attempts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tab_switches_count', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('is_disqualified', sa.Boolean(), server_default='0', nullable=False))


def downgrade() -> None:
    """O'zgarishlarni bekor qilish."""
    with op.batch_alter_table('attempts', schema=None) as batch_op:
        batch_op.drop_column('is_disqualified')
        batch_op.drop_column('tab_switches_count')

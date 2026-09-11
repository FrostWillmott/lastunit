"""baseline

Revision ID: 2dc84dd564d2
Revises:
Create Date: 2026-09-11 11:24:28.302844

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2dc84dd564d2'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

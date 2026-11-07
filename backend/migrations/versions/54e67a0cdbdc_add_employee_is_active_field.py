
"""add employee is_active field

Revision ID: 54e67a0cdbdc
Revises: 4c5a99157b0e
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '54e67a0cdbdc'
down_revision: Union[str, Sequence[str], None] = '4c5a99157b0e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'employees',
        sa.Column(
            'is_active',
            sa.Boolean(),
            nullable=False,
            server_default=sa.true()
        )
    )


def downgrade() -> None:
    op.drop_column('employees', 'is_active')

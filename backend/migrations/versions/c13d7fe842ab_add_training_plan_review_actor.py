"""Add user attribution to training plan reviews."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c13d7fe842ab"
down_revision: Union[str, Sequence[str], None] = "e7c9a50e2d31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "training_plans",
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_training_plans_reviewed_by_user_id_users",
        "training_plans",
        "users",
        ["reviewed_by_user_id"],
        ["user_id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_training_plans_reviewed_by_user_id_users",
        "training_plans",
        type_="foreignkey",
    )
    op.drop_column("training_plans", "reviewed_by_user_id")

"""Add user identity audit references for authenticated actions."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7c9a50e2d31"
down_revision: Union[str, Sequence[str], None] = "bb782d28c337"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


AUDIT_COLUMNS = (
    ("training_plans", "created_by_user_id"),
    ("training_plans", "approved_by_user_id"),
    ("training_plans", "status_updated_by_user_id"),
    ("skill_assessments", "assessed_by_user_id"),
    ("skill_assessments", "reviewed_by_user_id"),
    ("job_skills", "approved_by_user_id"),
    ("course_skills", "approved_by_user_id"),
    ("course_sessions", "cancelled_by_user_id"),
    ("course_sessions", "status_updated_by_user_id"),
    ("session_attendance", "recorded_by_user_id"),
    ("enrollments", "approved_by_user_id"),
    ("enrollments", "status_updated_by_user_id"),
    ("import_batches", "created_by_user_id"),
    ("import_issue_corrections", "reviewed_by_user_id"),
)

EMPLOYEE_ACTOR_COLUMNS = (
    ("training_plans", "status_updated_by"),
    ("course_sessions", "status_updated_by"),
    ("skill_assessments", "assessed_by"),
    ("skill_assessments", "reviewed_by"),
)


def upgrade() -> None:
    for table_name, column_name in EMPLOYEE_ACTOR_COLUMNS:
        op.add_column(
            table_name,
            sa.Column(column_name, sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            f"fk_{table_name}_{column_name}_employees",
            table_name,
            "employees",
            [column_name],
            ["id"],
            ondelete="SET NULL",
        )

    for table_name, column_name in AUDIT_COLUMNS:
        op.add_column(
            table_name,
            sa.Column(column_name, sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            f"fk_{table_name}_{column_name}_users",
            table_name,
            "users",
            [column_name],
            ["user_id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    for table_name, column_name in reversed(AUDIT_COLUMNS):
        op.drop_constraint(
            f"fk_{table_name}_{column_name}_users",
            table_name,
            type_="foreignkey",
        )
        op.drop_column(table_name, column_name)
    for table_name, column_name in reversed(EMPLOYEE_ACTOR_COLUMNS):
        op.drop_constraint(
            f"fk_{table_name}_{column_name}_employees",
            table_name,
            type_="foreignkey",
        )
        op.drop_column(table_name, column_name)

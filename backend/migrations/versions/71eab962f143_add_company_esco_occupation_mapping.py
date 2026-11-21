"""Add company job-title to ESCO occupation mappings.

Revision ID: 71eab962f143
Revises: a47c91e2d6b8
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "71eab962f143"
down_revision: Union[str, Sequence[str], None] = "a47c91e2d6b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_esco_occupation_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id", sa.Integer(),
            sa.ForeignKey("companies.company_id"), nullable=False,
        ),
        sa.Column("job_title", sa.String(150), nullable=False),
        sa.Column(
            "occupation_id", sa.Integer(),
            sa.ForeignKey("esco_occupations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
    )
    op.create_index(
        "uq_company_esco_mapping_title",
        "company_esco_occupation_mappings",
        ["company_id", sa.text("lower(trim(job_title))")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_company_esco_mapping_title",
        table_name="company_esco_occupation_mappings",
    )
    op.drop_table("company_esco_occupation_mappings")

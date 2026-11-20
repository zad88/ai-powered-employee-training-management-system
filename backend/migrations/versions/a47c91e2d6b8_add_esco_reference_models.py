"""Add shared ESCO reference models and Skill source metadata.

Revision ID: a47c91e2d6b8
Revises: d4a9b813c6e2
Create Date: 2026-11-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a47c91e2d6b8"
down_revision: Union[str, Sequence[str], None] = "d4a9b813c6e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "skills",
        sa.Column("esco_skill_type", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "skills",
        sa.Column("esco_reuse_level", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "skills",
        sa.Column("esco_status", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "skills",
        sa.Column(
            "esco_modified_date",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_table(
        "esco_occupations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("esco_concept_uri", sa.String(length=500), nullable=False),
        sa.Column("preferred_label", sa.Text(), nullable=False),
        sa.Column("alternative_labels", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("isco_group", sa.String(length=20), nullable=True),
        sa.Column("code", sa.String(length=50), nullable=True),
        sa.Column("nace_code", sa.Text(), nullable=True),
        sa.Column("regulated_profession_note", sa.Text(), nullable=True),
        sa.Column("scope_note", sa.Text(), nullable=True),
        sa.Column("definition", sa.Text(), nullable=True),
        sa.Column("in_scheme", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=True),
        sa.Column(
            "modified_date",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_esco_occupations"),
        sa.UniqueConstraint(
            "esco_concept_uri",
            name="uq_esco_occupations_concept_uri",
        ),
    )
    op.create_index(
        "ix_esco_occupations_preferred_label",
        "esco_occupations",
        ["preferred_label"],
        unique=False,
    )
    op.create_index(
        "ix_esco_occupations_isco_group",
        "esco_occupations",
        ["isco_group"],
        unique=False,
    )

    op.create_table(
        "esco_skill_hierarchy_nodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("esco_concept_uri", sa.String(length=500), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("hierarchy_level", sa.SmallInteger(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scope_note", sa.Text(), nullable=True),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "hierarchy_level >= 0 AND hierarchy_level <= 3",
            name="ck_esco_skill_hierarchy_nodes_level",
        ),
        sa.CheckConstraint(
            "(hierarchy_level = 0 AND parent_id IS NULL) OR "
            "(hierarchy_level > 0 AND parent_id IS NOT NULL)",
            name="ck_esco_skill_hierarchy_nodes_parent_level",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["esco_skill_hierarchy_nodes.id"],
            name="fk_esco_skill_hierarchy_nodes_parent_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_esco_skill_hierarchy_nodes",
        ),
        sa.UniqueConstraint(
            "esco_concept_uri",
            name="uq_esco_skill_hierarchy_nodes_concept_uri",
        ),
    )
    op.create_index(
        "ix_esco_skill_hierarchy_nodes_hierarchy_level",
        "esco_skill_hierarchy_nodes",
        ["hierarchy_level"],
        unique=False,
    )
    op.create_index(
        "ix_esco_skill_hierarchy_nodes_parent_id",
        "esco_skill_hierarchy_nodes",
        ["parent_id"],
        unique=False,
    )

    op.create_table(
        "esco_occupation_skills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("occupation_id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("relation_type", sa.String(length=16), nullable=False),
        sa.Column("skill_type", sa.String(length=40), nullable=True),
        sa.CheckConstraint(
            "relation_type IN ('essential', 'optional')",
            name="ck_esco_occupation_skills_relation_type",
        ),
        sa.ForeignKeyConstraint(
            ["occupation_id"],
            ["esco_occupations.id"],
            name="fk_esco_occupation_skills_occupation_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.skill_id"],
            name="fk_esco_occupation_skills_skill_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_esco_occupation_skills"),
        sa.UniqueConstraint(
            "occupation_id",
            "skill_id",
            "relation_type",
            name="uq_esco_occupation_skill_relation",
        ),
    )
    op.create_index(
        "ix_esco_occupation_skills_skill_id",
        "esco_occupation_skills",
        ["skill_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("esco_occupation_skills")
    op.drop_table("esco_skill_hierarchy_nodes")
    op.drop_table("esco_occupations")

    op.drop_column("skills", "esco_modified_date")
    op.drop_column("skills", "esco_status")
    op.drop_column("skills", "esco_reuse_level")
    op.drop_column("skills", "esco_skill_type")

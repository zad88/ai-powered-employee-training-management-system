from alembic import op
import sqlalchemy as sa


revision = "c5b63181ece8"
down_revision = "6d581926ea43"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "import_issue_corrections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "issue_id",
            sa.Integer(),
            sa.ForeignKey("import_row_issues.id"),
            nullable=False,
        ),
        sa.Column("original_value", sa.Text(), nullable=True),
        sa.Column("proposed_value", sa.Text(), nullable=True),
        sa.Column("applied_value", sa.Text(), nullable=True),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("method", sa.String(length=100), nullable=False),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="Proposed",
        ),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
    )

    op.create_index(
        "ix_import_issue_corrections_id",
        "import_issue_corrections",
        ["id"],
    )

    op.create_index(
        "ix_import_issue_corrections_issue_id",
        "import_issue_corrections",
        ["issue_id"],
    )


def downgrade():
    op.drop_index(
        "ix_import_issue_corrections_issue_id",
        table_name="import_issue_corrections",
    )
    op.drop_index(
        "ix_import_issue_corrections_id",
        table_name="import_issue_corrections",
    )
    op.drop_table("import_issue_corrections")
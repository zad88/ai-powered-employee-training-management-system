"""Add persistent access-token revocation records."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4a9b813c6e2"
down_revision: Union[str, Sequence[str], None] = "c13d7fe842ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "revoked_access_tokens",
        sa.Column("jti", sa.String(length=36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("jti", name="pk_revoked_access_tokens"),
    )
    op.create_index(
        "ix_revoked_access_tokens_expires_at",
        "revoked_access_tokens",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_revoked_access_tokens_expires_at",
        table_name="revoked_access_tokens",
    )
    op.drop_table("revoked_access_tokens")

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class ImportIssueCorrection(Base):
    __tablename__ = "import_issue_corrections"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    issue_id: Mapped[int] = mapped_column(
        ForeignKey("import_row_issues.id"),
        nullable=False,
        index=True,
    )
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id"),
        nullable=True,
    )

    original_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    action: Mapped[str] = mapped_column(String(30), nullable=False)
    method: Mapped[str] = mapped_column(String(100), nullable=False)

    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Proposed",
    )

    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
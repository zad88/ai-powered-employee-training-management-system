from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class ImportRowIssue(Base):
    __tablename__ = "import_row_issues"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.id"),
        nullable=False,
        index=True
    )

    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    field_name: Mapped[str | None] = mapped_column(String(150), nullable=True)

    issue_type: Mapped[str] = mapped_column(String(30), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    corrected_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="Open",
        server_default="Open"
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    resolution_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

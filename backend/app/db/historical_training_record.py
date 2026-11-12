from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class HistoricalTrainingRecord(Base):
    __tablename__ = "historical_training_records"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.company_id"),
        nullable=False,
        index=True
    )

    import_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_batches.id"),
        nullable=True,
        index=True
    )

    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"),
        nullable=True,
        index=True
    )

    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id"),
        nullable=True,
        index=True
    )

    external_employee_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )

    external_course_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )

    training_program_name: Mapped[str] = mapped_column(
        String(200), nullable=False
    )

    training_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )

    training_status: Mapped[str] = mapped_column(
        String(30), nullable=False
    )

    training_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    duration_value: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2), nullable=True
    )

    duration_unit: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )

    location: Mapped[str | None] = mapped_column(String(150), nullable=True)
    trainer: Mapped[str | None] = mapped_column(String(150), nullable=True)

    cost: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )

    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)

    assessment_score: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2), nullable=True
    )

    assessment_result: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )

    source_record_id: Mapped[str | None] = mapped_column(
        String(150), nullable=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

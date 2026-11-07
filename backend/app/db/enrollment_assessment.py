
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class EnrollmentAssessment(Base):
    __tablename__ = "enrollment_assessments"

    assessment_id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True
    )

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.company_id"),
        nullable=False,
        index=True
    )

    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("enrollments.enrollment_id"),
        nullable=False,
        index=True
    )

    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    assessment_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    assessment_result: Mapped[str] = mapped_column(
        String(30),
        nullable=False
    )

    assessed_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    assessor_comments: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    # Enrollment associated with this assessment
    enrollment = relationship(
        "Enrollment",
        back_populates="assessments"
    )

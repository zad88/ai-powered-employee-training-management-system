
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class Enrollment(Base):
    __tablename__ = "enrollments"

    enrollment_id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True
    )

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.company_id"),
        nullable=False,
        index=True
    )

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"),
        nullable=False,
        index=True
    )

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id"),
        nullable=False
    )

    session_id: Mapped[int] = mapped_column(
        ForeignKey("course_sessions.session_id"),
        nullable=False,
        index=True
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Pending Approval"
    )

    approval_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Pending"
    )

    approved_by: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"),
        nullable=True
    )

    approval_date: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    approval_comments: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    progress_percentage: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )

    expected_completion_date: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    withdrawn_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    withdrawal_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    failure_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    status_updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"),
        nullable=True
    )

    # Course relationship
    course = relationship(
        "Course",
        back_populates="enrollments"
    )

    # Employee relationship
    employee = relationship(
        "Employee",
        back_populates="enrollments",
        foreign_keys=[employee_id]
    )

    # Course session relationship
    session = relationship(
        "CourseSession",
        back_populates="enrollments"
    )

        # Assessment attempts for this enrollment
    assessments = relationship(
        "EnrollmentAssessment",
        back_populates="enrollment"
    )

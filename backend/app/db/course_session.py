
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class CourseSession(Base):
    __tablename__ = "course_sessions"

    session_id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True
    )

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.company_id"),
        nullable=False,
        index=True
    )

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id"),
        nullable=False,
        index=True
    )

    session_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True
    )

    start_datetime: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False
    )

    end_datetime: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False
    )

    registration_deadline: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False
    )

    session_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Scheduled"
    )

    trainer_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True
    )

    location_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False
    )

    location_details: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    max_participants: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True
    )

    completion_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True
    )

    completion_date: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    completion_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    cancellation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    cancelled_by: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"),
        nullable=True
    )
    cancelled_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id"),
        nullable=True,
    )
    status_updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"),
        nullable=True,
    )
    status_updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id"),
        nullable=True,
    )

    # Course relationship
    course = relationship(
        "Course",
        back_populates="sessions"
    )

    # Enrollment relationship
    enrollments = relationship(
        "Enrollment",
        back_populates="session"
    )
    attendance_records = relationship(
        "SessionAttendance",
        back_populates="session"
    )
    feedback_records = relationship(
        "SessionFeedback",
        back_populates="session"
    )
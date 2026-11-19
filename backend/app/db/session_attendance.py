
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class SessionAttendance(Base):
    __tablename__ = "session_attendance"

    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "employee_id",
            name="uq_session_employee_attendance"
        ),
    )

    attendance_id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True
    )

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.company_id"),
        nullable=False,
        index=True
    )

    session_id: Mapped[int] = mapped_column(
        ForeignKey("course_sessions.session_id"),
        nullable=False,
        index=True
    )

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"),
        nullable=False,
        index=True
    )

    attendance_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Pending"
    )

    check_in_time: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    check_out_time: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    recorded_by: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"),
        nullable=True
    )
    recorded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id"),
        nullable=True,
    )

    attendance_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    # Scheduled session associated with this attendance record
    session = relationship(
        "CourseSession",
        back_populates="attendance_records"
    )

    # Employee whose attendance is recorded
    employee = relationship(
        "Employee",
        back_populates="attendance_records",
        foreign_keys=[employee_id]
    )

    # Employee who recorded the attendance
    recorder = relationship(
        "Employee",
        foreign_keys=[recorded_by]
    )

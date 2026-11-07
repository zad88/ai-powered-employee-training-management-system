
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class SessionFeedback(Base):
    __tablename__ = "session_feedback"

    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "employee_id",
            name="uq_session_employee_feedback"
        ),
    )

    feedback_id: Mapped[int] = mapped_column(
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

    training_rating: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    trainer_rating: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True
    )

    content_relevance_rating: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True
    )

    feedback_comments: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    # Training session receiving the feedback
    session = relationship(
        "CourseSession",
        back_populates="feedback_records"
    )

    # Employee who submitted the feedback
    employee = relationship(
        "Employee",
        back_populates="feedback_records",
        foreign_keys=[employee_id]
    )

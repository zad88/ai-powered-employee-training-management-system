
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class TrainingPlan(Base):
    __tablename__ = "training_plans"

    plan_id: Mapped[int] = mapped_column(
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

    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"),
        nullable=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    plan_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Draft"
    )

    plan_start_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True
    )

    target_completion_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True
    )

    actual_completion_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True
    )

    estimated_total_hours: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2),
        nullable=True
    )

    actual_total_hours: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2),
        nullable=True
    )

    estimated_total_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True
    )

    actual_total_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True
    )

    currency: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True
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
    approved_by_user_id: Mapped[int | None] = mapped_column(
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

    approval_date: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    approval_comments: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    plan_review_notes: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True
    )
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id"),
        nullable=True,
    )

    # Employee receiving the training plan
    employee = relationship(
        "Employee",
        back_populates="training_plans",
        foreign_keys=[employee_id]
    )

    # Employee who created the plan
    creator = relationship(
        "Employee",
        foreign_keys=[created_by]
    )

    # Employee who approved the plan
    approver = relationship(
        "Employee",
        foreign_keys=[approved_by]
    )

    # Courses included in this training plan
    plan_courses = relationship(
        "PlanCourse",
        back_populates="training_plan"
    )

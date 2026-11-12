
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Boolean,
    UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class Employee(Base):
    __tablename__ = "employees"

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "employee_id",
            name="uq_employee_company_employee_id"
        ),
        UniqueConstraint(
            "company_id",
            "email",
            name="uq_employee_company_email"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    employee_id: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.company_id"),
        nullable=False,
        index=True
    )

    full_name: Mapped[str] = mapped_column(
        String(150), nullable=False
    )

    email: Mapped[str] = mapped_column(
        String(255), nullable=False
    )

    job_title: Mapped[str] = mapped_column(
        String(150), nullable=False
    )

    department: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    manager_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )

    manager_internal_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )

    employment_status: Mapped[str] = mapped_column(
        String(30), nullable=False
    )

    working_hours_per_week: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    learning_hours_per_week: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    years_of_experience: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    hire_date: Mapped[date] = mapped_column(
        Date, nullable=False
    )

    job_level: Mapped[str] = mapped_column(
        String(50), nullable=False
    )

    employment_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )

    preferred_learning_mode: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    company = relationship(
        "Company", back_populates="employees"
    )

    manager = relationship(
        "Employee",
        remote_side="Employee.id",
        back_populates="direct_reports",
        foreign_keys=[manager_internal_id]
    )

    direct_reports = relationship(
        "Employee",
        back_populates="manager",
        foreign_keys=[manager_internal_id]
    )

    skill_assessments = relationship(
        "SkillAssessment", back_populates="employee"
    )

    enrollments = relationship(
        "Enrollment",
        back_populates="employee",
        foreign_keys="Enrollment.employee_id"
    )

    training_plans = relationship(
        "TrainingPlan",
        back_populates="employee",
        foreign_keys="TrainingPlan.employee_id"
    )

    attendance_records = relationship(
        "SessionAttendance",
        back_populates="employee",
        foreign_keys="SessionAttendance.employee_id"
    )

    feedback_records = relationship(
        "SessionFeedback",
        back_populates="employee",
        foreign_keys="SessionFeedback.employee_id"
    )

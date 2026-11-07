
from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class Course(Base):
    __tablename__ = "courses"

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "course_id",
            name="uq_company_course"
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True
    )

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.company_id"),
        nullable=False,
        index=True
    )

    course_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    course_title: Mapped[str] = mapped_column(
        String(200),
        nullable=False
    )

    course_description: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    course_category: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    course_duration_hours: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    course_provider: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True
    )

    delivery_mode: Mapped[str] = mapped_column(
        String(30),
        nullable=False
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True
    )

    start_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True
    )

    end_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True
    )

    target_job_levels: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True
    )

    prerequisites: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    has_assessment: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )

    provides_certificate: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )

    assessment_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="None"
    )

    course_cost: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    currency: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True
    )

    # Company that owns the course
    company = relationship(
        "Company",
        back_populates="courses"
    )

    # Scheduled sessions for this course
    sessions = relationship(
        "CourseSession",
        back_populates="course"
    )

    # Skills covered by this course
    course_skills = relationship(
        "CourseSkill",
        back_populates="course"
    )

    # Employee enrollments in this course
    enrollments = relationship(
        "Enrollment",
        back_populates="course"
    )

    plan_courses = relationship(
        "PlanCourse",
        back_populates="course"
    )


from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class PlanCourse(Base):
    __tablename__ = "plan_courses"

    __table_args__ = (
        UniqueConstraint(
            "plan_id",
            "course_id",
            name="uq_plan_course"
        ),
    )

    plan_course_id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True
    )

    plan_id: Mapped[int] = mapped_column(
        ForeignKey("training_plans.plan_id"),
        nullable=False,
        index=True
    )

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id"),
        nullable=False
    )

    priority: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Medium"
    )

    sequence_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    recommendation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    expected_outcome: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    # Training plan containing this course
    training_plan = relationship(
        "TrainingPlan",
        back_populates="plan_courses"
    )

    # Actual course recommended in this plan
    course = relationship(
        "Course",
        back_populates="plan_courses"
    )

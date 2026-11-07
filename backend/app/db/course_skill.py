
from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class CourseSkill(Base):
    __tablename__ = "course_skills"

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "course_id",
            "skill_id",
            name="uq_company_course_skill"
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

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id"),
        nullable=False,
        index=True
    )

    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.skill_id"),
        nullable=False,
        index=True
    )

    proficiency_level: Mapped[int | None] = mapped_column(
        Integer,
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

    # Course associated with this skill
    course = relationship(
        "Course",
        back_populates="course_skills"
    )

    # Skill associated with this course
    skill = relationship(
        "Skill",
        back_populates="course_skills"
    )

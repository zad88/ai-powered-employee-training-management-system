
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class Skill(Base):
    __tablename__ = "skills"

    skill_id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True
    )

    skill_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        unique=True
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    # Job roles that require this skill
    job_requirements = relationship(
        "JobSkill",
        back_populates="skill"
    )

    # Employee assessments for this skill
    assessments = relationship(
        "SkillAssessment",
        back_populates="skill"
    )

    # Courses that teach this skill
    course_skills = relationship(
        "CourseSkill",
        back_populates="skill"
    )

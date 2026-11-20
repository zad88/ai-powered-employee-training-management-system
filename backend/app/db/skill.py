
from datetime import datetime

from sqlalchemy import DateTime, String, Text
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

    # ESCO reference identifier
    esco_concept_uri: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        unique=True
    )

    # Alternative names used for matching skills
    alternative_labels: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    esco_skill_type: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True
    )

    esco_reuse_level: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True
    )

    esco_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True
    )

    esco_modified_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    esco_occupation_relations = relationship(
        "ESCOOccupationSkill",
        back_populates="skill"
    )

    job_requirements = relationship(
        "JobSkill",
        back_populates="skill"
    )

    assessments = relationship(
        "SkillAssessment",
        back_populates="skill"
    )

    course_skills = relationship(
        "CourseSkill",
        back_populates="skill"
    )

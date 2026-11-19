from datetime import date

from sqlalchemy import (
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class SkillAssessment(Base):
    __tablename__ = "skill_assessments"

    assessment_id: Mapped[int] = mapped_column(
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

    assessed_by: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"),
        nullable=True,
    )
    assessed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id"),
        nullable=True,
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"),
        nullable=True,
    )
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id"),
        nullable=True,
    )

    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.skill_id"),
        nullable=False
    )

    proficiency_level: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    assessment_source: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    assessment_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    evidence_quality: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Medium"
    )

    evidence_title: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True
    )

    evidence_description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    assessment_date: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )

    expiry_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True
    )

    assessor_comments: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    evidence_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Pending Review"
    )

    employee = relationship(
        "Employee",
        back_populates="skill_assessments",
        foreign_keys=[employee_id],
    )

    skill = relationship(
        "Skill",
        back_populates="assessments"
    )


from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class JobSkill(Base):
    __tablename__ = "job_skills"

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "job_title",
            "skill_id",
            name="uq_company_job_skill"
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

    job_title: Mapped[str] = mapped_column(
        String(150),
        nullable=False
    )

    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.skill_id"),
        nullable=False
    )

    required_proficiency: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    importance: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Medium"
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

    # The skill required by this job
    skill = relationship(
        "Skill",
        back_populates="job_requirements"
    )

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class ESCOOccupationSkill(Base):
    __tablename__ = "esco_occupation_skills"

    __table_args__ = (
        UniqueConstraint(
            "occupation_id",
            "skill_id",
            "relation_type",
            name="uq_esco_occupation_skill_relation",
        ),
        CheckConstraint(
            "relation_type IN ('essential', 'optional')",
            name="ck_esco_occupation_skills_relation_type",
        ),
        Index(
            "ix_esco_occupation_skills_skill_id",
            "skill_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    occupation_id: Mapped[int] = mapped_column(
        ForeignKey(
            "esco_occupations.id",
            ondelete="RESTRICT",
            name="fk_esco_occupation_skills_occupation_id",
        ),
        nullable=False
    )

    skill_id: Mapped[int] = mapped_column(
        ForeignKey(
            "skills.skill_id",
            ondelete="RESTRICT",
            name="fk_esco_occupation_skills_skill_id",
        ),
        nullable=False
    )

    relation_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False
    )

    skill_type: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True
    )

    occupation = relationship(
        "ESCOOccupation",
        back_populates="skill_relations"
    )

    skill = relationship(
        "Skill",
        back_populates="esco_occupation_relations"
    )

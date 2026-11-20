from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class ESCOOccupation(Base):
    __tablename__ = "esco_occupations"

    __table_args__ = (
        UniqueConstraint(
            "esco_concept_uri",
            name="uq_esco_occupations_concept_uri",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    esco_concept_uri: Mapped[str] = mapped_column(
        String(500),
        nullable=False
    )

    preferred_label: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        index=True
    )

    alternative_labels: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    isco_group: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        index=True
    )

    code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True
    )

    nace_code: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    regulated_profession_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    scope_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    definition: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    in_scheme: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True
    )

    modified_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    skill_relations = relationship(
        "ESCOOccupationSkill",
        back_populates="occupation"
    )

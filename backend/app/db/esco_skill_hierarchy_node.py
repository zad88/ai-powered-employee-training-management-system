from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class ESCOSkillHierarchyNode(Base):
    __tablename__ = "esco_skill_hierarchy_nodes"

    __table_args__ = (
        CheckConstraint(
            "hierarchy_level >= 0 AND hierarchy_level <= 3",
            name="ck_esco_skill_hierarchy_nodes_level",
        ),
        CheckConstraint(
            "(hierarchy_level = 0 AND parent_id IS NULL) OR "
            "(hierarchy_level > 0 AND parent_id IS NOT NULL)",
            name="ck_esco_skill_hierarchy_nodes_parent_level",
        ),
        UniqueConstraint(
            "esco_concept_uri",
            name="uq_esco_skill_hierarchy_nodes_concept_uri",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    esco_concept_uri: Mapped[str] = mapped_column(
        String(500),
        nullable=False
    )

    label: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    hierarchy_level: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        index=True
    )

    code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    scope_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "esco_skill_hierarchy_nodes.id",
            ondelete="RESTRICT",
            name="fk_esco_skill_hierarchy_nodes_parent_id",
        ),
        nullable=True,
        index=True
    )

    parent = relationship(
        "ESCOSkillHierarchyNode",
        remote_side="ESCOSkillHierarchyNode.id",
        back_populates="children"
    )

    children = relationship(
        "ESCOSkillHierarchyNode",
        back_populates="parent"
    )

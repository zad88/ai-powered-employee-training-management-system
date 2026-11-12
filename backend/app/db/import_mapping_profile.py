from sqlalchemy import Boolean, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class ImportMappingProfile(Base):
    __tablename__ = "import_mapping_profiles"

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "entity_type",
            "profile_name",
            name="uq_company_import_mapping_profile"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.company_id"),
        nullable=False,
        index=True
    )

    profile_name: Mapped[str] = mapped_column(String(150), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)

    column_mapping: Mapped[dict] = mapped_column(JSON, nullable=False)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

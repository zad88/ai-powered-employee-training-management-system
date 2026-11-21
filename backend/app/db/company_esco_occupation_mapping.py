from sqlalchemy import ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class CompanyESCOOccupationMapping(Base):
    __tablename__ = "company_esco_occupation_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.company_id"), nullable=False
    )
    job_title: Mapped[str] = mapped_column(String(150), nullable=False)
    occupation_id: Mapped[int] = mapped_column(
        ForeignKey("esco_occupations.id", ondelete="RESTRICT"), nullable=False
    )

    __table_args__ = (
        Index(
            "uq_company_esco_mapping_title",
            company_id,
            func.lower(func.trim(job_title)),
            unique=True,
        ),
    )

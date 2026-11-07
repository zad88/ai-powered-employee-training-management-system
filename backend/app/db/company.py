
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class Company(Base):
    __tablename__ = "companies"

    company_id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True
    )

    company_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False
    )

    # Employees belonging to this company
    employees = relationship(
        "Employee",
        back_populates="company"
    )

    # Courses belonging to this company
    courses = relationship(
        "Course",
        back_populates="company"
    )

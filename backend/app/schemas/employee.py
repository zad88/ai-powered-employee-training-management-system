
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class EmployeeBase(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    employee_id: str = Field(min_length=1, max_length=100)
    job_title: str = Field(min_length=1, max_length=150)
    department: str = Field(min_length=1, max_length=100)

    manager_id: str | None = Field(default=None, max_length=100)

    employment_status: str = Field(min_length=1, max_length=30)

    working_hours_per_week: Decimal = Field(ge=0, le=168)
    learning_hours_per_week: Decimal = Field(ge=0, le=168)
    years_of_experience: Decimal = Field(ge=0)

    hire_date: date
    job_level: str = Field(min_length=1, max_length=50)
    employment_type: str = Field(min_length=1, max_length=50)

    preferred_learning_mode: str | None = Field(
        default=None,
        max_length=30
    )


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    email: EmailStr | None = None
    job_title: str | None = Field(default=None, max_length=150)
    department: str | None = Field(default=None, max_length=100)
    manager_id: str | None = Field(default=None, max_length=100)
    employment_status: str | None = Field(default=None, max_length=30)

    working_hours_per_week: Decimal | None = Field(default=None, ge=0, le=168)
    learning_hours_per_week: Decimal | None = Field(default=None, ge=0, le=168)
    years_of_experience: Decimal | None = Field(default=None, ge=0)

    hire_date: date | None = None
    job_level: str | None = Field(default=None, max_length=50)
    employment_type: str | None = Field(default=None, max_length=50)
    preferred_learning_mode: str | None = Field(default=None, max_length=30)


class EmployeeResponse(EmployeeBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    manager_internal_id: int | None = None
    is_active: bool

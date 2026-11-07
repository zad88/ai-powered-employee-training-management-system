from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TrainingPlanCreate(BaseModel):
    employee_id: int = Field(gt=0)

    plan_start_date: date | None = None
    target_completion_date: date | None = None

    estimated_total_hours: Decimal | None = Field(default=None, ge=0)
    estimated_total_cost: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=10)

    @model_validator(mode="after")
    def validate_dates(self):
        if (
            self.plan_start_date
            and self.target_completion_date
            and self.target_completion_date < self.plan_start_date
        ):
            raise ValueError("Target completion date cannot be before start date")

        return self


class TrainingPlanUpdate(BaseModel):
    plan_start_date: date | None = None
    target_completion_date: date | None = None

    estimated_total_hours: Decimal | None = Field(default=None, ge=0)
    estimated_total_cost: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=10)

    plan_review_notes: str | None = Field(default=None, max_length=1000)


class TrainingPlanApproval(BaseModel):
    approval_status: str = Field(pattern="^(Approved|Rejected)$")
    approval_comments: str | None = Field(default=None, max_length=500)


class TrainingPlanReview(BaseModel):
    plan_review_notes: str = Field(min_length=1, max_length=1000)


class TrainingPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_id: int
    company_id: int
    employee_id: int
    created_by: int | None = None
    created_at: datetime

    plan_status: str

    plan_start_date: date | None = None
    target_completion_date: date | None = None
    actual_completion_date: date | None = None

    estimated_total_hours: Decimal | None = None
    actual_total_hours: Decimal | None = None

    estimated_total_cost: Decimal | None = None
    actual_total_cost: Decimal | None = None

    currency: str | None = None

    approval_status: str
    approved_by: int | None = None
    approval_date: datetime | None = None
    approval_comments: str | None = None

    last_reviewed_at: datetime | None = None
    plan_review_notes: str | None = None
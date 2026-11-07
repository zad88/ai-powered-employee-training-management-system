from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EnrollmentCreate(BaseModel):
    employee_id: int = Field(gt=0)
    session_id: int = Field(gt=0)
    expected_completion_date: datetime | None = None


class EnrollmentApproval(BaseModel):
    approval_status: str = Field(
        pattern="^(Approved|Rejected)$"
    )
    approval_comments: str | None = Field(
        default=None,
        max_length=500
    )


class EnrollmentProgressUpdate(BaseModel):
    progress_percentage: int = Field(ge=0, le=100)


class EnrollmentWithdrawal(BaseModel):
    withdrawal_reason: str = Field(min_length=1)


class EnrollmentFailure(BaseModel):
    failure_reason: str = Field(min_length=1)


class EnrollmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    enrollment_id: int
    company_id: int
    employee_id: int
    course_id: int
    session_id: int

    status: str
    approval_status: str

    approved_by: int | None = None
    approval_date: datetime | None = None
    approval_comments: str | None = None

    progress_percentage: int

    expected_completion_date: datetime | None = None
    started_at: datetime | None = None
    last_activity_at: datetime | None = None
    completed_at: datetime | None = None

    withdrawn_at: datetime | None = None
    withdrawal_reason: str | None = None
    failure_reason: str | None = None

    status_updated_by: int | None = None